"""이적 현황 수집 — 위키백과 '<시즌> Manchester United F.C. season' 문서의 Transfers 표 (In / Out / Loan in / Loan out).

사용법:
    python etl/fetch_transfers.py                 # 현재 시즌
    python etl/fetch_transfers.py --season 2025   # 특정 시즌 (시작 연도)

→ transfers (source='wikipedia:<revid>')
- 위키에서 사라진 행(오기 정정 등)은 같은 시즌의 위키 출처 행에서 삭제. 직접 입력한 행(source 가 다른 것)은 보존
- 이적 시장: 5~9월 = '<연도>-summer', 그 외 = '<연도>-winter'
- 출처: 위키백과 (CC BY-SA 4.0)
"""
import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import SyncLog, connect, season_label  # noqa: E402
import wiki  # noqa: E402

# 표 제목 → (direction, 기본 transfer_type)
SECTIONS = {"In": ("in", "permanent"), "Out": ("out", "permanent"),
            "Loan in": ("in", "loan"), "Loan out": ("out", "loan")}


def ensure_schema(con) -> None:
    cols = {r[1] for r in con.execute("PRAGMA table_info(transfers)")}
    if "position" not in cols:
        con.execute("ALTER TABLE transfers ADD COLUMN position TEXT")
        print("  DB: transfers.position 칸 추가")


def parse_date(text: str) -> str | None:
    m = re.search(r"(\d{1,2})\s+([A-Z][a-z]+)\s+(\d{4})", text)
    if not m:
        return None
    return datetime.strptime(" ".join(m.groups()), "%d %B %Y").date().isoformat()


def ttype(base: str, fee: str) -> str:
    f = fee.lower()
    if base == "loan":
        return "loan"
    if "released" in f or "end of contract" in f:
        return "release"
    if "free" in f:
        return "free"
    if "loan return" in f or "end of loan" in f:
        return "loan_return"
    if "promot" in f or "academy" in f:
        return "youth_promotion"
    return "permanent"


def parse(page: str, season: str) -> list[dict]:
    out = []
    for t in wiki.tables(page):
        if t["heading"] not in SECTIONS or not t["rows"]:
            continue
        head = [c["text"] for c in t["rows"][0]]
        if "Name" not in head or "Date" not in head:
            continue
        idx = {h: i for i, h in enumerate(head)}
        direction, base = SECTIONS[t["heading"]]
        for r in t["rows"][1:]:
            get = lambda h: wiki.clean(r[idx[h]]["text"]) if h in idx and idx[h] < len(r) else ""  # noqa: E731
            name, date = get("Name"), parse_date(get("Date"))
            if not name or not date:
                continue
            club = get("From") if direction == "in" else get("To")
            fee = get("Fee") or (f"Loan until {get('Until')}" if get("Until") else "Loan" if base == "loan" else "")
            d = datetime.fromisoformat(date)
            window = f"{d.year}-summer" if 5 <= d.month <= 9 else f"{d.year if d.month >= 10 else d.year}-winter"
            out.append({
                "player_name": name, "position": get("Pos.") or get("Pos") or None, "direction": direction,
                "transfer_type": ttype(base, fee),
                "from_club": club if direction == "in" else "Manchester United",
                "to_club": "Manchester United" if direction == "in" else club,
                "fee_text": fee or None, "transfer_date": date, "transfer_window": window, "season": season,
            })
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int)
    args = ap.parse_args()
    con = connect()
    ensure_schema(con)
    start = args.season or con.execute("SELECT start_year FROM seasons WHERE is_current=1").fetchone()[0]
    season = season_label(start)
    title = f"{start}–{(start + 1) % 100:02d} Manchester United F.C. season"
    page, rev = wiki.page_html(title)
    rows = parse(page, season)
    by = {d: sum(r["direction"] == d for r in rows) for d in ("in", "out")}
    print(f"[위키백과] {title} (rev {rev}) → 이적 {len(rows)}건 (영입 {by['in']} · 방출 {by['out']})")
    if not rows:
        print("⚠ 이적 표를 찾지 못함 (문서 구조 변경?) → 기존 데이터 유지")
        return 0

    with SyncLog(con, "wikipedia", f"transfers {season}") as log:
        log.api_calls = 1
        keep = set()
        for r in rows:
            pid = con.execute("SELECT id FROM players WHERE full_name=? OR known_as=?",
                              (r["player_name"], r["player_name"])).fetchone()
            cols = ["player_id", *r.keys(), "source", "source_url", "status"]
            vals = [pid[0] if pid else None, *r.values(), f"wikipedia:{rev}", wiki.page_url(title), "confirmed"]
            cur = con.execute(
                f"""INSERT INTO transfers ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})
                    ON CONFLICT(player_name, direction, transfer_date) DO UPDATE SET
                    {', '.join(f'{c}=excluded.{c}' for c in cols if c not in ('player_name', 'direction', 'transfer_date'))}""",
                vals)
            log.rows += cur.rowcount
            keep.add((r["player_name"], r["direction"], r["transfer_date"]))
        stale = [s for s in con.execute(
            "SELECT id, player_name, direction, transfer_date FROM transfers WHERE season=? AND source LIKE 'wikipedia%'",
            (season,)) if (s["player_name"], s["direction"], s["transfer_date"]) not in keep]
        for s in stale:
            print(f"  - 위키에서 사라진 행 삭제: {s['player_name']} ({s['direction']}, {s['transfer_date']})")
            con.execute("DELETE FROM transfers WHERE id=?", (s["id"],))
        log.message = f"rev={rev} {season} rows={len(rows)} removed={len(stale)}"
        con.commit()
    print(f"OK - 이적 저장 {len(rows)}건" + (f", 삭제 {len(stale)}건" if stale else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
