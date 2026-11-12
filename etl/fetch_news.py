"""맨유 주요 뉴스 수집 (매체 공식 RSS 피드, 키 불필요, AI 미사용).

사용법:
    python etl/fetch_news.py            # 수집 + DB 저장
    python etl/fetch_news.py --dry-run  # 수집 결과만 출력

저장 테이블
    news_items  제목·링크·짧은 요약(피드 제공 문구, 200자 이내)·매체·게시 시각·태그·언급 기자·묶음(cluster)

원칙
* 매체가 배포용으로 제공하는 RSS 의 제목·요약 문구만 저장하고 반드시 원문 링크를 붙임 (본문 복사 안 함).
* 기자 표시는 제목·요약에 기자 이름(또는 'The Athletic' 등 소속)이 언급된 경우에만 붙임 — 추측하지 않음.
* 태그(이적·부상·감독·공식 등)는 영어 키워드 규칙으로 분류 → 오분류 가능성 있음 (참고용).
* 같은 소식을 여러 매체가 보도하면 제목 유사도로 하나의 묶음(cluster)으로 표시.
* 21일 지난 기사는 삭제.
"""
import argparse
import email.utils
import html
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import USER_AGENT, SyncLog, connect, utc_now  # noqa: E402

FEEDS = [  # (코드, 매체명, 신뢰 등급, URL)
    ("bbc", "BBC Sport", 1, "https://feeds.bbci.co.uk/sport/football/teams/manchester-united/rss.xml"),
    ("guardian", "The Guardian", 1, "https://www.theguardian.com/football/manchester-united/rss"),
    ("sky", "Sky Sports", 1, "https://www.skysports.com/rss/11667"),
    ("men", "Manchester Evening News", 2, "https://www.manchestereveningnews.co.uk/all-about/manchester-united-fc?service=rss"),
]
KEEP_DAYS = 21

# 공신력 높은 기자 (이름 → 표시명, 소속). 제목·요약에 이름이 나올 때만 표시
JOURNALISTS = [
    (r"\bOrnstein\b", "David Ornstein", "The Athletic"),
    (r"\b(Fabrizio )?Romano\b", "Fabrizio Romano", "Independent"),
    (r"\bSimon Stone\b", "Simon Stone", "BBC Sport"),
    (r"\bLaurie Whitwell\b", "Laurie Whitwell", "The Athletic"),
    (r"\bAndy Mitten\b", "Andy Mitten", "United We Stand"),
    (r"\bSamuel Luckhurst\b", "Samuel Luckhurst", "MEN"),
    (r"\bRob Dawson\b", "Rob Dawson", "ESPN"),
    (r"\bMark Ogden\b", "Mark Ogden", "ESPN"),
    (r"\bJamie Jackson\b", "Jamie Jackson", "The Guardian"),
    (r"\bChris Wheeler\b", "Chris Wheeler", "Daily Mail"),
    (r"\bKaveh Solhekol\b", "Kaveh Solhekol", "Sky Sports"),
    (r"\bDharmesh Sheth\b", "Dharmesh Sheth", "Sky Sports"),
    (r"\bThe Athletic\b", "The Athletic", "The Athletic"),
]
# 태그: (한글 태그, 영어 키워드 정규식) — 앞쪽이 우선순위 높음
TAGS = [
    ("공식", r"\b(officially|announce[sd]|confirmed by (the )?club|club (have |has )?confirm(ed|s)|confirm(s|ed)? (the |his )?(appointment|signing|departure)|completes? (the )?(signing|move|deal)|appointed|unveil(s|ed))\b"),
    ("감독", r"\b(manager|head coach|sack(s|ed|ing)?|boss|caretaker|interim)\b"),
    ("이적", r"\b(transfer(s| window| fee)?|signings?|bids?|fee|loan|swoop|release clause|here we go|want(s|ed)? to sign)\b"),
    ("부상", r"\b(injur(y|ies|ed)|fitness|ruled out|hamstring|knee|ankle|setback|return(s|ed)? to training|sidelined)\b"),
    ("루머", r"\b(linked|considering|interest(ed)? in|eye(s|ing)?|monitor(s|ing)?|weigh(s|ing)? up|in talks|targets?)\b"),
    ("경기", r"(\bpreview\b|player ratings|match report|team news|\bline-?ups?\b|press conference|\bvs?\.? [A-Z]|\b\d-\d\b)"),
]
NOT_CONFIRMED = r"(not|n't|yet to|awaiting|before)\s+(been\s+)?(officially\s+)?(confirm|announc)"
NOISE = r"\b(Transfer Talk|Transfer Centre)\b"  # 방송·코너 이름은 태그 판단에서 제외
STOP = set("the a an and or of to in on for at with by from is are be as it its his her their after before over into "
           "man utd united manchester mufc says say new why how what who will has have not but more".split())


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def clean(s: str | None, limit: int | None = None) -> str:
    t = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    t = re.sub(r"\s+", " ", t).strip()
    if limit and len(t) > limit:
        t = t[: limit - 1].rsplit(" ", 1)[0] + "…"
    return t


def parse_date(s: str | None) -> str | None:
    if not s:
        return None
    try:
        d = email.utils.parsedate_to_datetime(s)
    except (TypeError, ValueError):
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def classify(title: str, summary: str, cats: list[str]) -> tuple[list[str], list[str]]:
    raw = f"{title} {summary}"
    text = re.sub(NOISE, " ", raw)
    tags = [t for t, rx in TAGS if re.search(rx, text, re.I)]
    if "공식" in tags and re.search(NOT_CONFIRMED, text, re.I):
        tags.remove("공식")
    if "공식" in tags and "루머" in tags:
        tags.remove("루머")  # 확정 표현이 있으면 루머 태그는 뺌
    if any(c.lower() == "video" for c in cats):
        tags.append("영상")
    if re.search(r"\blive\b", title, re.I) or any(c.lower() == "liveblog" for c in cats):
        tags.append("라이브")
    names = []
    for rx, name, _org in JOURNALISTS:
        if re.search(rx, raw) and name not in names:
            names.append(name)
    if len(names) > 1 and "The Athletic" in names and "David Ornstein" in names:
        names.remove("The Athletic")
    return tags[:3], names


def words(title: str) -> set[str]:
    return {w for w in re.findall(r"[a-z']+", title.lower()) if len(w) > 2 and w not in STOP}


def cluster(items: list[dict]) -> None:
    """제목 핵심 단어가 많이 겹치고 48시간 이내면 같은 소식으로 묶음 (cluster = 묶음 대표 기사 url)."""
    items.sort(key=lambda x: x["published_utc"] or "")
    reps: list[dict] = []
    for it in items:
        w = words(it["title"])
        it["cluster"] = it["url"]
        for r in reversed(reps):
            if abs(_ts(it) - _ts(r)) > 48 * 3600:
                continue
            rw = words(r["title"])
            if w and rw and len(w & rw) >= 4 and len(w & rw) / len(w | rw) >= 0.5:
                it["cluster"] = r["cluster"]
                break
        reps.append(it)


def _ts(it) -> float:
    try:
        return datetime.strptime(it["published_utc"], "%Y-%m-%dT%H:%M:%SZ").timestamp()
    except (TypeError, ValueError):
        return 0


def ensure_table(con) -> None:
    con.execute("""CREATE TABLE IF NOT EXISTS news_items (
        url TEXT PRIMARY KEY, source TEXT NOT NULL, source_name TEXT, source_tier INTEGER,
        title TEXT NOT NULL, summary TEXT, published_utc TEXT, tags TEXT, journalists TEXT,
        cluster TEXT, fetched_utc TEXT)""")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    items, failed = [], []
    for code, name, tier, url in FEEDS:
        try:
            root = ET.fromstring(fetch(url))
        except Exception as e:  # noqa: BLE001 — 한 매체 실패는 건너뜀
            failed.append(f"{name}: {str(e)[:80]}")
            continue
        n = 0
        for it in root.iter("item"):
            link = (it.findtext("link") or "").strip()
            title = clean(it.findtext("title"))
            if not link.startswith("http") or not title:
                continue
            summary = clean(it.findtext("description"), 200)
            cats = [c.text or "" for c in it.findall("category")]
            tags, names = classify(title, summary, cats)
            items.append({"url": link.split("?")[0] if code != "men" else link, "source": code, "source_name": name,
                          "source_tier": tier, "title": title, "summary": summary,
                          "published_utc": parse_date(it.findtext("pubDate")), "tags": ",".join(tags),
                          "journalists": ",".join(names)})
            n += 1
        print(f"  {name}: {n}건")

    cutoff = (datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    items = [i for i in items if (i["published_utc"] or "9") >= cutoff]
    for f in failed:
        print(f"⚠ 뉴스 피드 수집 실패 — {f}")

    if args.dry_run:
        cluster(items)
        for i in sorted(items, key=lambda x: x["published_utc"] or "", reverse=True)[:25]:
            grp = "  └" if i["cluster"] != i["url"] else "-"
            print(grp, (i["published_utc"] or "")[:16], i["source"], f"[{i['tags']}]", i["journalists"] and f"<{i['journalists']}>", i["title"][:90])
        return 0
    if not items:
        print("✗ 뉴스 피드 전부 실패 — 기존 뉴스 유지")
        return 1

    con = connect()
    ensure_table(con)
    with SyncLog(con, "rss", "news") as log:
        log.api_calls = len(FEEDS)
        # 기존 기사 포함해서 다시 묶음 (새 기사가 이전 소식과 같은 묶음일 수 있음)
        old = {r["url"]: dict(r) for r in con.execute("SELECT * FROM news_items WHERE published_utc >= ?", (cutoff,))}
        for i in items:
            old[i["url"]] = {**old.get(i["url"], {}), **i}
        allit = list(old.values())
        cluster(allit)
        now = utc_now()
        for i in allit:
            con.execute("""INSERT INTO news_items (url, source, source_name, source_tier, title, summary, published_utc,
                               tags, journalists, cluster, fetched_utc) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                           ON CONFLICT(url) DO UPDATE SET title=excluded.title, summary=excluded.summary,
                               published_utc=excluded.published_utc, tags=excluded.tags,
                               journalists=excluded.journalists, cluster=excluded.cluster""",
                        (i["url"], i["source"], i["source_name"], i["source_tier"], i["title"], i["summary"],
                         i["published_utc"], i["tags"], i["journalists"], i["cluster"], i.get("fetched_utc") or now))
        removed = con.execute("DELETE FROM news_items WHERE published_utc < ?", (cutoff,)).rowcount
        log.rows = len(items)
        log.message = f"news={len(items)} total={len(allit)} removed={removed} failed={len(failed)}"
        print(f"[뉴스] 수집 {len(items)}건 · 보관 {len(allit)}건 · 삭제 {removed}건 · 묶음 {len({i['cluster'] for i in allit})}개")
    con.close()
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
