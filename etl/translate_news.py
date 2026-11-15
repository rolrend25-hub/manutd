"""주요 뉴스 제목·요약 한글 번역 (DeepL API Free — 기계번역, LLM 아님).

사용법:
    python etl/translate_news.py            # 주요 뉴스(featured, 5~8건) 중 아직 번역 안 된(또는 원문이 바뀐) 기사만 번역
    python etl/translate_news.py --usage    # 이번 달 DeepL 사용량만 출력

* 키: 환경변수/.env 의 DEEPL_API_KEY (Free 키는 ':fx' 로 끝남 → api-free.deepl.com)
* 무료 한도 월 50만 자. 한도의 90% 를 넘으면 번역을 멈추고 영어 원문 그대로 표시 (과금 없음)
* 사이트에 보이는 주요 뉴스만 번역 (etl/fetch_news.py 가 고른 featured > 0) → 무료 한도 절약
* 원문(제목+요약)이 바뀐 기사만 다시 번역 → 같은 기사를 두 번 번역하지 않음
* 키가 없거나 DeepL 오류면 경고만 남기고 종료 (사이트는 영어 원문으로 표시)

저장: news_items.title_ko, summary_ko, ko_src(번역한 원문 지문)
"""
import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import USER_AGENT, SyncLog, connect, load_env  # noqa: E402

USAGE_STOP = 0.90   # 월 한도의 90% 넘으면 중단
BATCH = 40          # 한 요청에 보낼 문장 수 (DeepL 최대 50)

# 번역 후 고정 표기 (DeepL 이 매번 다르게 옮기는 이름 정리)
FIX = [("맨체스터 유나이티드", "맨유"), ("맨 유나이티드", "맨유"), ("맨 유티디", "맨유"), ("맨유티디", "맨유"),
       ("올드 트래포드", "올드 트래퍼드"), ("프리미어 리그", "프리미어리그"), ("챔피언스 리그", "챔피언스리그")]


def ensure_columns(con) -> None:
    cols = {r[1] for r in con.execute("PRAGMA table_info(news_items)")}
    for c in ("title_ko", "summary_ko", "ko_src"):
        if c not in cols:
            con.execute(f"ALTER TABLE news_items ADD COLUMN {c} TEXT")
    if "featured" not in cols:
        con.execute("ALTER TABLE news_items ADD COLUMN featured INTEGER DEFAULT 0")


def fingerprint(title: str, summary: str | None) -> str:
    return hashlib.sha1(f"{title}\n{summary or ''}".encode("utf-8")).hexdigest()[:16]


class DeepL:
    def __init__(self, key: str):
        self.key = key
        self.base = "https://api-free.deepl.com/v2" if key.endswith(":fx") else "https://api.deepl.com/v2"

    def _call(self, path: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method="POST" if data else "GET", headers={
            "Authorization": f"DeepL-Auth-Key {self.key}", "User-Agent": USER_AGENT,
            "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            hint = {403: "키 오류", 456: "월 한도 초과", 429: "요청 과다"}.get(e.code, "")
            raise RuntimeError(f"DeepL HTTP {e.code} {hint}".strip()) from None

    def usage(self) -> tuple[int, int]:
        u = self._call("/usage")
        return u["character_count"], u["character_limit"]

    def translate(self, texts: list[str]) -> list[str]:
        r = self._call("/translate", {"text": texts, "source_lang": "EN", "target_lang": "KO"})
        return [t["text"] for t in r["translations"]]


def tidy(s: str) -> str:
    for a, b in FIX:
        s = s.replace(a, b)
    return s.strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--usage", action="store_true")
    args = ap.parse_args()

    key = load_env().get("DEEPL_API_KEY")
    if not key:
        print("⚠ DEEPL_API_KEY 없음 → 뉴스 번역 건너뜀 (영어 원문 표시)")
        return 0
    dl = DeepL(key)
    used, limit = dl.usage()
    print(f"[뉴스 번역] DeepL 이번 달 사용 {used:,} / {limit:,}자 ({used / limit:.0%})")
    if args.usage:
        return 0

    con = connect()
    ensure_columns(con)
    rows = [r for r in con.execute("SELECT url, title, summary, ko_src FROM news_items WHERE featured > 0 "
                                    "ORDER BY featured")
            if r["ko_src"] != fingerprint(r["title"], r["summary"])]
    if not rows:
        print("  새로 번역할 기사 없음")
        con.commit()
        return 0

    budget = int(limit * USAGE_STOP) - used
    with SyncLog(con, "deepl", "news_translate") as log:
        todo = []
        for r in rows:
            n = len(r["title"]) + len(r["summary"] or "")
            if n > budget:
                print(f"⚠ DeepL 월 한도 {USAGE_STOP:.0%} 도달 → 남은 {len(rows) - len(todo)}건은 다음 달에 번역 (영어 원문 표시)")
                break
            budget -= n
            todo.append(r)
        chars = 0
        for i in range(0, len(todo), BATCH):
            chunk = todo[i:i + BATCH]
            texts = []
            for r in chunk:
                texts += [r["title"], r["summary"] or ""]
            out = dl.translate(texts)
            log.api_calls += 1
            for j, r in enumerate(chunk):
                t_ko, s_ko = tidy(out[2 * j]), tidy(out[2 * j + 1]) if r["summary"] else None
                con.execute("UPDATE news_items SET title_ko=?, summary_ko=?, ko_src=? WHERE url=?",
                            (t_ko, s_ko, fingerprint(r["title"], r["summary"]), r["url"]))
                chars += len(r["title"]) + len(r["summary"] or "")
            con.commit()
        log.rows = len(todo)
        log.message = f"translated={len(todo)} chars={chars} month_used={used + chars}/{limit}"
    print(f"  번역 {len(todo)}건 · {chars:,}자 · 이번 달 누적 약 {used + chars:,}자")
    for r in todo[:3]:
        t = con.execute("SELECT title_ko FROM news_items WHERE url=?", (r["url"],)).fetchone()[0]
        print(f"    {r['title'][:60]} → {t[:50]}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        sys.exit(main())
    except RuntimeError as e:
        print(f"⚠ 뉴스 번역 실패 — {e} (영어 원문 유지)")
        sys.exit(1)
