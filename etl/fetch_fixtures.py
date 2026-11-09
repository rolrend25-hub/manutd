"""맨유 전 경기 일정·결과 수집 (football-data.org) → matches, teams.

사용법:
    python etl/fetch_fixtures.py                 # 현재 시즌 (seasons.is_current)
    python etl/fetch_fixtures.py --season 2025   # 특정 시즌 (시작 연도)

* football-data 무료 플랜은 PL·챔스(CL) 등 일부 대회만 제공 → FA컵·EFL컵 경기는 들어오지 않음.
* 무료 플랜은 스코어 반영이 지연될 수 있음 (경기 종료 후 상태가 한동안 TIMED 로 남기도 함).
* 같은 경기는 match_fd_id 로 덮어쓰기(upsert) → 여러 번 실행해도 안전.
* 다가오는 경기의 킥오프 시간 변경·확정·연기는 notifications 에 카톡 안내 대기열(KICKOFF_CHANGE)로 넣음
  → notify/send_kakao.py 가 발송. 이미 보낸 리마인드는 새 시간 기준으로 다시 보내도록 초기화.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import MUFC_FD, SyncLog, connect, get_json, load_env, season_label, utc_now  # noqa: E402

BASE = "https://api.football-data.org/v4"

# football-data 대회 코드 → 우리 DB competitions.code
# (주의: football-data 의 'ELC' 는 잉글랜드 챔피언십(2부)이라 EFL컵과 다름)
COMP_MAP = {"PL": "PL", "CL": "UCL", "EL": "UEL", "ECL": "UECL", "FAC": "FAC", "CS": "CS"}
HOME_VENUE = "Old Trafford"


def goals(score: dict, side: str) -> int | None:
    """연장 포함 득점 (승부차기 제외)."""
    dur = score.get("duration")
    if dur == "PENALTY_SHOOTOUT" and score.get("regularTime"):
        reg = score["regularTime"].get(side) or 0
        ext = (score.get("extraTime") or {}).get(side) or 0
        return reg + ext
    return (score.get("fullTime") or {}).get(side)


def upsert_team(con, t: dict) -> int:
    con.execute(
        """INSERT INTO teams (name, short_name, tla, crest_url, team_fd_id)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(team_fd_id) DO UPDATE SET
             name=excluded.name, short_name=excluded.short_name,
             tla=excluded.tla, crest_url=excluded.crest_url""",
        (t["name"], t.get("shortName"), t.get("tla"), t.get("crest"), t["id"]))
    return con.execute("SELECT id FROM teams WHERE team_fd_id=?", (t["id"],)).fetchone()[0]


def to_row(m: dict, season: str, opp_id: int) -> dict:
    is_home = m["homeTeam"]["id"] == MUFC_FD
    mu, op = ("home", "away") if is_home else ("away", "home")
    opp = m["awayTeam"] if is_home else m["homeTeam"]
    sc = m["score"]
    mu_g, op_g = goals(sc, mu), goals(sc, op)
    ht = sc.get("halfTime") or {}
    pens = sc.get("penalties") or {}
    result = None
    if m["status"] == "FINISHED" and mu_g is not None and op_g is not None:
        result = "W" if mu_g > op_g else "L" if mu_g < op_g else "D"
    refs = [r["name"] for r in m.get("referees", []) if r.get("type") == "REFEREE"]
    code = m["competition"]["code"]
    return {
        "season": season,
        "competition_code": COMP_MAP.get(code, code),
        "stage": m.get("stage"),
        "matchday": m.get("matchday"),
        "kickoff_utc": m["utcDate"],
        "kickoff_confirmed": 0 if m["status"] == "SCHEDULED" else 1,  # SCHEDULED = 시간 미확정
        "home_away": "H" if is_home else "A",
        "opponent_id": opp_id,
        "opponent_name": opp.get("shortName") or opp["name"],
        "venue": HOME_VENUE if is_home else None,
        "status": m["status"],
        "mu_score": mu_g,
        "opp_score": op_g,
        "mu_score_ht": ht.get(mu),
        "opp_score_ht": ht.get(op),
        "mu_pens": pens.get(mu),
        "opp_pens": pens.get(op),
        "result": result,
        "referee": refs[0] if refs else None,
        "match_fd_id": m["id"],
    }


def upsert_match(con, row: dict) -> tuple[str, str | None]:
    """반환: ('new'|'updated'|'same', 이전 킥오프(변경된 경우)). 일정 변경 시 카톡 안내 대기열 등록."""
    old = con.execute("SELECT * FROM matches WHERE match_fd_id=?", (row["match_fd_id"],)).fetchone()
    cols = list(row)
    if old is None:
        con.execute(
            f"INSERT INTO matches ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
            [row[c] for c in cols])
        return "new", None
    changed = [c for c in cols if old[c] != row[c]]
    if not changed:
        return "same", None
    con.execute(
        f"UPDATE matches SET {', '.join(f'{c}=?' for c in changed)}, updated_at=? WHERE id=?",
        [row[c] for c in changed] + [utc_now(), old["id"]])
    moved = old["kickoff_utc"] if "kickoff_utc" in changed else None
    queue_schedule_notice(con, old, row)
    return "updated", moved


def queue_schedule_notice(con, old, row: dict) -> None:
    """다가오는 경기의 킥오프 변경·시간 확정·연기 → notifications(KICKOFF_CHANGE, kakao_memo) 대기열."""
    now = utc_now()
    if old["status"] in ("FINISHED", "CANCELLED") or max(old["kickoff_utc"], row["kickoff_utc"]) <= now:
        return
    moved = old["kickoff_utc"] != row["kickoff_utc"] and bool(row["kickoff_confirmed"])
    confirmed = not old["kickoff_confirmed"] and row["kickoff_confirmed"]
    postponed = row["status"] == "POSTPONED" and old["status"] != "POSTPONED"
    rescheduled = old["status"] == "POSTPONED" and row["status"] in ("SCHEDULED", "TIMED")
    if not (moved or confirmed or postponed or rescheduled):
        return
    ref = f"{old['kickoff_utc']}|{old['status']}|{old['kickoff_confirmed']}"
    # 아직 안 보낸 안내가 있으면 '처음 시간 → 최신 시간'으로 보이도록 이전 값 유지
    con.execute(
        """INSERT INTO notifications (match_id, kind, channel, scheduled_utc, status, external_ref)
           VALUES (?, 'KICKOFF_CHANGE', 'kakao_memo', ?, 'pending', ?)
           ON CONFLICT(match_id, kind, channel) DO UPDATE SET
             scheduled_utc=excluded.scheduled_utc, sent_utc=NULL, error=NULL,
             external_ref=CASE WHEN notifications.status='pending' THEN notifications.external_ref
                               ELSE excluded.external_ref END,
             status='pending'""",
        (old["id"], now, ref))
    # 이미 보낸 리마인드는 새 킥오프 기준으로 다시 판단하도록 지움
    con.execute("DELETE FROM notifications WHERE match_id=? AND channel='kakao_memo' AND kind LIKE 'REMIND_%'",
                (old["id"],))
    print(f"  🔔 카톡 일정 안내 대기: vs {row['opponent_name']} ({ref} → {row['kickoff_utc']}|{row['status']})")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, help="시즌 시작 연도 (예: 2026 → 2026-27)")
    args = ap.parse_args()

    env = load_env()
    token = env.get("FOOTBALL_DATA_TOKEN")
    if not token:
        sys.exit("FOOTBALL_DATA_TOKEN 이 .env 에 없습니다.")

    con = connect()
    if args.season:
        start_year = args.season
    else:
        r = con.execute("SELECT start_year FROM seasons WHERE is_current=1").fetchone()
        if not r:
            sys.exit("seasons 테이블에 is_current=1 시즌이 없습니다. --season 으로 지정하세요.")
        start_year = r[0]
    season = season_label(start_year)
    con.execute("INSERT OR IGNORE INTO seasons (season, start_year) VALUES (?, ?)", (season, start_year))

    print(f"[football-data] {season} 시즌 맨유 경기 수집")
    with SyncLog(con, "football-data", "fixtures") as log:
        data = get_json(f"{BASE}/teams/{MUFC_FD}/matches?season={start_year}",
                        {"X-Auth-Token": token})
        log.api_calls += 1
        rs = data.get("resultSet", {})
        print(f"  제공 대회: {rs.get('competitions')}  경기 수: {rs.get('count')}")

        counts = {"new": 0, "updated": 0, "same": 0}
        moved = []
        for m in data.get("matches", []):
            opp = m["awayTeam"] if m["homeTeam"]["id"] == MUFC_FD else m["homeTeam"]
            if not opp.get("id"):  # 대진 미정 (토너먼트 다음 라운드 등)
                continue
            opp_id = upsert_team(con, opp)
            row = to_row(m, season, opp_id)
            state, old_kickoff = upsert_match(con, row)
            counts[state] += 1
            if old_kickoff:
                moved.append((row["opponent_name"], old_kickoff, row["kickoff_utc"]))

        log.rows = counts["new"] + counts["updated"]
        log.message = f"{season} new={counts['new']} updated={counts['updated']} same={counts['same']}"
        con.commit()

    print(f"  신규 {counts['new']} / 변경 {counts['updated']} / 동일 {counts['same']}")
    for name, a, b in moved:
        print(f"  ⚠ 킥오프 변경: vs {name}  {a} → {b}")

    q = """SELECT kickoff_utc, competition_code, home_away, opponent_name, status,
                  mu_score, opp_score, result
           FROM matches WHERE season=? ORDER BY kickoff_utc"""
    rows = con.execute(q, (season,)).fetchall()
    done = [r for r in rows if r["status"] == "FINISHED"]
    todo = [r for r in rows if r["status"] != "FINISHED"]
    w = sum(r["result"] == "W" for r in done)
    d = sum(r["result"] == "D" for r in done)
    lo = sum(r["result"] == "L" for r in done)
    print(f"\n  DB 기준 {season}: 종료 {len(done)}경기 ({w}승 {d}무 {lo}패), 남은 경기 {len(todo)}")
    for r in done[-3:]:
        ha = "홈" if r["home_away"] == "H" else "원정"
        print(f"   최근 {r['kickoff_utc'][:10]} {r['competition_code']:<4} {ha} vs {r['opponent_name']:<14} "
              f"{r['mu_score']}-{r['opp_score']} {r['result']}")
    for r in todo[:3]:
        ha = "홈" if r["home_away"] == "H" else "원정"
        print(f"   예정 {r['kickoff_utc']} {r['competition_code']:<4} {ha} vs {r['opponent_name']}  [{r['status']}]")
    con.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
