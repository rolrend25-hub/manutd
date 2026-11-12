"""감독 동기화 + 이적 교차검증 — football-data.org 팀 정보(공식 감독·1군 명단) 기준.

사용법:
    python etl/fetch_club.py            # 감독 + 이적 검증 (fetch_players.py·fetch_transfers.py 다음에 실행)
    python etl/fetch_club.py --dry-run  # DB 저장 없이 결과만 출력

1) 감독 (managers)
   - 현직 감독: football-data `/teams/66` 의 coach (공식 기준)
   - 역대 감독·재임 기간·전적: 위키백과 'List of Manchester United F.C. managers'
   - 위키 현직 감독 = 공식 감독일 때만 위키 목록으로 교체 (한글 이름·비고는 기존 행에서 이어받음)
   - 다르면 DB 는 그대로 두고 ⚠ 경고. 현직 감독이 바뀌면 ⚠ 알림 (1회)
2) 이적 검증 (transfers.verify_status / verify_note, transfer_checks)
   - 위키 이적 기록을 공식 1군 명단(football-data) + FPL 선수 상태(입단일·이탈·임대)와 대조
     verified   공식 데이터로 직접 확인 (영입 → 1군 명단에 있음 / 방출·임대 → FPL 이탈·임대 상태)
     consistent 방출인데 공식 1군 명단에 없음 → 모순은 없지만 직접 확인한 기록은 아님 (유스 선수 등)
     unverified 공식 명단으로 확인 불가 (유스·B팀 등 1군 명단 밖 선수)
     conflict   위키와 공식 명단이 어긋남 (예: 방출됐다는데 아직 1군 명단에 있음)
   - 위키 누락 의심: 이번 시즌 FPL 입단 선수인데 영입 기록 없음 / FPL 이탈·임대인데 방출 기록 없음
   - 새로 생긴 conflict·누락만 ⚠ 알림 (같은 문제는 반복 알림 안 함), 해소되면 resolved 처리

REPORT_DIR 환경변수(Actions)가 있으면 ⚠ 줄을 3_club.txt 로 남김 → notify_status.py 가 GitHub 이슈로 알림.
"""
import argparse
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import MUFC_FD, SyncLog, connect, get_json, load_env, names_match, utc_now  # noqa: E402
import wiki  # noqa: E402

MANAGERS_PAGE = "List of Manchester United F.C. managers"
ALERTS: list[str] = []


def alert(msg: str) -> None:
    line = f"⚠ {msg}"
    ALERTS.append(line)
    print(line)


def ensure_schema(con) -> None:
    mcols = {r[1] for r in con.execute("PRAGMA table_info(managers)")}
    for col, typ in (("matches", "INTEGER"), ("wins", "INTEGER"), ("draws", "INTEGER"),
                     ("losses", "INTEGER"), ("source", "TEXT")):
        if col not in mcols:
            con.execute(f"ALTER TABLE managers ADD COLUMN {col} {typ}")
    tcols = {r[1] for r in con.execute("PRAGMA table_info(transfers)")}
    for col in ("verify_status", "verify_note", "verified_utc"):
        if col not in tcols:
            con.execute(f"ALTER TABLE transfers ADD COLUMN {col} TEXT")
    con.execute("""CREATE TABLE IF NOT EXISTS transfer_checks (
        season TEXT NOT NULL, player_name TEXT NOT NULL,
        kind TEXT NOT NULL,            -- conflict / missing_in / missing_out
        detail TEXT, first_seen_utc TEXT, last_seen_utc TEXT, resolved_utc TEXT,
        PRIMARY KEY (season, player_name, kind))""")


# ---------------------------------------------------------------- 감독
def parse_wiki_date(text: str) -> str | None:
    t = wiki.clean(text)
    if not t or t.lower().startswith("present"):
        return None
    for fmt, out in (("%d %B %Y", "%Y-%m-%d"), ("%B %Y", "%Y-%m"), ("%Y", "%Y")):
        m = re.search({"%d %B %Y": r"\d{1,2} [A-Z][a-z]+ \d{4}", "%B %Y": r"[A-Z][a-z]+ \d{4}", "%Y": r"\d{4}"}[fmt], t)
        if m:
            try:
                return datetime.strptime(m.group(), fmt).strftime(out)
            except ValueError:
                continue
    return None


def wiki_managers() -> tuple[list[dict], int]:
    page, rev = wiki.page_html(MANAGERS_PAGE)
    for t in wiki.tables(page):
        if not t["rows"]:
            continue
        head = [wiki.clean(c["text"]) for c in t["rows"][0]]
        if not {"Manager", "From", "To"} <= set(head):
            continue
        idx = {h: i for i, h in enumerate(head)}
        out = []
        for r in t["rows"][1:]:
            get = lambda h: wiki.clean(r[idx[h]]["text"]) if h in idx and idx[h] < len(r) else ""  # noqa: E731
            raw = get("Manager")
            if not raw or raw == "Manager":
                continue
            to_txt = get("To")
            out.append({
                "name": re.sub(r"\s*\(.*$", "", raw).strip(),
                "is_caretaker": int(bool(re.search(r"\((interim|caretaker)", raw, re.I))),
                "nationality": get("Nationality") or None,
                "start_date": parse_wiki_date(get("From")),
                "end_date": parse_wiki_date(to_txt),
                "current": to_txt.lower().startswith("present"),
                "matches": wiki.to_int(get("M")), "wins": wiki.to_int(get("W")),
                "draws": wiki.to_int(get("D")), "losses": wiki.to_int(get("L")),
                "honours": ", ".join(x.strip() for x in get("Honours").splitlines() if x.strip()) or None,
            })
        return out, rev
    return [], rev


def sync_managers(con, coach: dict | None, dry: bool) -> None:
    official = (coach or {}).get("name")
    old_cur = con.execute("SELECT name FROM managers WHERE end_date IS NULL ORDER BY start_date DESC").fetchone()
    old_cur = old_cur[0] if old_cur else None
    print(f"[감독] 공식(football-data): {official or '정보 없음'} · DB 현직: {old_cur or '-'}")

    rows, rev = wiki_managers()
    cur = [r for r in rows if r["current"]]
    print(f"[감독] 위키백과 (rev {rev}): {len(rows)}명, 현직 {cur[0]['name'] if cur else '없음'}")
    if len(rows) < 20 or len(cur) != 1:
        alert(f"감독 목록(위키백과) 형식이 예상과 다름 ({len(rows)}명, 현직 {len(cur)}명) → 기존 데이터 유지")
        return
    if not official:
        alert("football-data 에 감독 정보가 없음 → 위키 현직 감독을 공식 확인 못 함, 기존 데이터 유지")
        return
    if not names_match(cur[0]["name"], official):
        alert(f"감독 정보 불일치: 위키백과 현직 '{cur[0]['name']}' ≠ 공식 '{official}' → 기존 데이터 유지, 확인 필요")
        return

    # 기존 행의 한글 이름·비고 이어받기 (이름 + 부임 연도가 같은 행 우선)
    prev = [dict(r) for r in con.execute("SELECT name, name_ko, start_date, note, note_en FROM managers")]

    def carry(w):
        same = [p for p in prev if names_match(p["name"], w["name"])]
        exact = [p for p in same if (p["start_date"] or "")[:4] == (w["start_date"] or "")[:4]]
        pick = exact[0] if exact else (same[0] if len(same) == 1 and len([x for x in rows if names_match(x["name"], w["name"])]) == 1 else None)
        if not pick:
            return None, None, w["honours"]
        note = pick["note"] if pick["note"] and not pick["note"].startswith("end_date:") else None
        return pick["name_ko"], note, pick["note_en"] or w["honours"]

    if old_cur and not names_match(old_cur, cur[0]["name"]):
        alert(f"감독 변경 반영: {old_cur} → {cur[0]['name']} ({cur[0]['start_date']} 부임, 공식 확인)")
    if dry:
        for w in rows[-5:]:
            print("  ", w["name"], w["start_date"], "~", w["end_date"] or "현직", carry(w))
        return
    with SyncLog(con, "wikipedia+football-data", "managers") as log:
        log.api_calls = 1
        con.execute("DELETE FROM managers")
        for w in rows:
            name_ko, note, note_en = carry(w)
            vals = (w["name"], name_ko, w["nationality"], w["start_date"], w["end_date"], w["is_caretaker"],
                    note, note_en, w["matches"], w["wins"], w["draws"], w["losses"], f"wikipedia:{rev}")
            con.execute("""INSERT INTO managers (name, name_ko, nationality, start_date, end_date, is_caretaker,
                               note, note_en, matches, wins, draws, losses, source)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", vals)
            log.rows += 1
        log.message = f"rev={rev} managers={len(rows)} current={cur[0]['name']} official={official}"
        con.commit()
    print(f"OK - 감독 {len(rows)}명 저장, 현직 {cur[0]['name']} (공식 일치)")


# ---------------------------------------------------------------- 이적 검증
def verify_transfers(con, fd_squad: list[str], dry: bool) -> None:
    season, start = con.execute("SELECT season, start_year FROM seasons WHERE is_current=1").fetchone()
    window_open = f"{start}-06-01"
    fpl = [dict(r) for r in con.execute(
        """SELECT p.id, p.full_name, p.known_as, s.status, s.joined_date FROM squad_memberships s
           JOIN players p ON p.id = s.player_id WHERE s.season=?""", (season,))]
    trs = [dict(r) for r in con.execute(
        "SELECT id, player_id, player_name, direction, transfer_type, transfer_date FROM transfers WHERE season=?",
        (season,))]
    if len(fd_squad) < 15 or len(fpl) < 15:
        alert(f"공식 명단이 너무 적음 (football-data {len(fd_squad)}명, FPL {len(fpl)}명) → 이적 검증 건너뜀")
        return

    def in_fd(name):
        return any(names_match(name, n) for n in fd_squad)

    def fpl_row(name, pid):
        for p in fpl:
            if (pid and p["id"] == pid) or names_match(name, p["full_name"]) or names_match(name, p["known_as"] or ""):
                return p
        return None

    def later(t, direction):
        return any(names_match(o["player_name"], t["player_name"]) and o["direction"] == direction
                   and o["transfer_date"] > t["transfer_date"] for o in trs)

    issues = {}  # (player, kind) -> detail
    counts = {"verified": 0, "consistent": 0, "unverified": 0, "conflict": 0}
    results = []
    for t in trs:
        name, f = t["player_name"], fpl_row(t["player_name"], t["player_id"])
        listed = in_fd(name) or (f and f["status"] == "active")
        if t["direction"] == "in":
            if listed:
                st, note = "verified", "In the official first-team squad"
            elif f and f["status"] in ("left", "loaned_out") and later(t, "out"):
                st, note = "verified", "Signed, then left / loaned out later"
            else:
                st, note = "unverified", "Not in the official first-team squad (academy / U21 signing?)"
            if f and f["joined_date"] and t["transfer_date"]:
                gap = abs((date.fromisoformat(f["joined_date"]) - date.fromisoformat(t["transfer_date"])).days)
                if gap > 31:
                    note += f" · official join date {f['joined_date']}"
        else:
            if listed and not later(t, "in"):
                st, note = "conflict", "Listed as departed, but still in the official first-team squad"
                issues[(name, "conflict")] = f"위키: {t['transfer_type']} 이적 ({t['transfer_date']}) / 공식 1군 명단에는 아직 있음"
            elif f and f["status"] in ("left", "loaned_out"):
                st, note = "verified", "Official data shows the player left / on loan"
            else:
                st, note = "consistent", "Not in the official first-team squad — consistent with departure, but no direct official record"
        counts[st] += 1
        results.append((st, note, t["id"]))

    # 위키 누락 의심
    for p in fpl:
        nm = p["known_as"] if p["known_as"] and len(p["known_as"].split()) > 1 else p["full_name"]
        has = lambda d: any(t["direction"] == d and (t["player_id"] == p["id"] or names_match(t["player_name"], p["full_name"])  # noqa: E731
                                                    or names_match(t["player_name"], p["known_as"] or "")) for t in trs)
        if p["status"] == "active" and (p["joined_date"] or "") >= window_open and not has("in"):
            issues[(nm, "missing_in")] = f"공식(FPL) {p['joined_date']} 입단인데 위키 영입 기록 없음"
        if p["status"] in ("left", "loaned_out") and not has("out"):
            issues[(nm, "missing_out")] = f"공식(FPL) 상태 '{p['status']}' 인데 위키 방출·임대 기록 없음"

    print(f"[이적 검증] {season} {len(trs)}건 → 공식 확인 {counts['verified']} · 모순 없음 {counts['consistent']} · "
          f"확인불가 {counts['unverified']} · "
          f"불일치 {counts['conflict']} · 누락 의심 {sum(k[1] != 'conflict' for k in issues)}")
    if dry:
        for (n, k), d in issues.items():
            print(f"  [{k}] {n}: {d}")
        return

    now = utc_now()
    with SyncLog(con, "football-data+fpl", f"transfer-verify {season}") as log:
        log.api_calls = 0
        for st, note, tid in results:
            con.execute("UPDATE transfers SET verify_status=?, verify_note=?, verified_utc=? WHERE id=?", (st, note, now, tid))
            log.rows += 1
        known = {(r[0], r[1]): r[2] for r in con.execute(
            "SELECT player_name, kind, resolved_utc FROM transfer_checks WHERE season=?", (season,))}
        for (n, k), d in issues.items():
            if (n, k) not in known or known[(n, k)] is not None:  # 새로 생겼거나 해소 후 재발
                label = {"conflict": "이적 불일치", "missing_in": "위키 영입 누락 의심", "missing_out": "위키 방출 누락 의심"}[k]
                alert(f"{label}: {n} — {d}")
            con.execute("""INSERT INTO transfer_checks (season, player_name, kind, detail, first_seen_utc, last_seen_utc)
                           VALUES (?,?,?,?,?,?) ON CONFLICT(season, player_name, kind) DO UPDATE SET
                           detail=excluded.detail, last_seen_utc=excluded.last_seen_utc, resolved_utc=NULL,
                           first_seen_utc=CASE WHEN transfer_checks.resolved_utc IS NULL THEN transfer_checks.first_seen_utc
                                               ELSE excluded.first_seen_utc END""", (season, n, k, d, now, now))
        for (n, k), res in known.items():
            if res is None and (n, k) not in issues:
                con.execute("UPDATE transfer_checks SET resolved_utc=? WHERE season=? AND player_name=? AND kind=?",
                            (now, season, n, k))
                print(f"  해소됨: [{k}] {n}")
        log.message = (f"verified={counts['verified']} consistent={counts['consistent']} "
                       f"unverified={counts['unverified']} conflict={counts['conflict']} "
                       f"open_issues={len(issues)}")
        con.commit()


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    env = load_env()
    con = connect()
    ensure_schema(con)
    team = get_json(f"https://api.football-data.org/v4/teams/{MUFC_FD}",
                    headers={"X-Auth-Token": env["FOOTBALL_DATA_TOKEN"]})
    fd_squad = [p["name"] for p in team.get("squad") or [] if p.get("name")]
    print(f"[football-data] 감독 {team.get('coach', {}).get('name')} · 1군 명단 {len(fd_squad)}명")

    sync_managers(con, team.get("coach"), args.dry_run)
    verify_transfers(con, fd_squad, args.dry_run)

    rdir = os.environ.get("REPORT_DIR")
    if rdir and ALERTS and not args.dry_run:
        with open(Path(rdir) / "3_club.txt", "a", encoding="utf-8") as f:
            f.write("\n".join(ALERTS) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
