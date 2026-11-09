"""현재 시즌 순위 수집 (football-data.org) → league_table(전체 순위표), season_standings(맨유 행).

사용법:
    python etl/fetch_standings.py                # 현재 시즌, PL + 챔스 리그 페이즈
    python etl/fetch_standings.py --season 2025  # 특정 시즌
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import MUFC_FD, SyncLog, connect, get_json, load_env, season_label  # noqa: E402

BASE = "https://api.football-data.org/v4"
# football-data 대회 코드 → (DB 코드, 시즌 종료 여부 판단에 쓸 리그 여부)
TARGETS = {"PL": "PL", "CL": "UCL"}


def team_id(con, t: dict) -> int:
    con.execute(
        """INSERT INTO teams (name, short_name, tla, crest_url, team_fd_id) VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(team_fd_id) DO UPDATE SET
             name=excluded.name, short_name=excluded.short_name,
             tla=excluded.tla, crest_url=excluded.crest_url""",
        (t["name"], t.get("shortName"), t.get("tla"), t.get("crest"), t["id"]))
    return con.execute("SELECT id FROM teams WHERE team_fd_id=?", (t["id"],)).fetchone()[0]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int)
    args = ap.parse_args()

    token = load_env().get("FOOTBALL_DATA_TOKEN")
    if not token:
        sys.exit("FOOTBALL_DATA_TOKEN 이 .env 에 없습니다.")
    con = connect()
    if args.season:
        start_year = args.season
    else:
        start_year = con.execute("SELECT start_year FROM seasons WHERE is_current=1").fetchone()[0]
    season = season_label(start_year)
    is_current = con.execute("SELECT is_current FROM seasons WHERE season=?", (season,)).fetchone()
    is_final = 0 if (is_current and is_current[0]) else 1

    with SyncLog(con, "football-data", "standings") as log:
        msgs = []
        for fd_code, code in TARGETS.items():
            data = get_json(f"{BASE}/competitions/{fd_code}/standings?season={start_year}",
                            {"X-Auth-Token": token})
            log.api_calls += 1
            total = next((s for s in data.get("standings", []) if s.get("type") == "TOTAL"), None)
            if not total:
                print(f"[{code}] 순위 데이터 없음")
                continue

            con.execute("DELETE FROM league_table WHERE season=? AND competition_code=?", (season, code))
            mu = None
            for r in total["table"]:
                tid = team_id(con, r["team"])
                con.execute(
                    """INSERT INTO league_table (season, competition_code, position, team_id, team_name,
                         played, won, drawn, lost, goals_for, goals_against, goal_diff, points, form)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (season, code, r["position"], tid, r["team"].get("shortName") or r["team"]["name"],
                     r["playedGames"], r["won"], r["draw"], r["lost"], r["goalsFor"],
                     r["goalsAgainst"], r["goalDifference"], r["points"], r.get("form")))
                log.rows += 1
                if r["team"]["id"] == MUFC_FD:
                    mu = r

            n = len(total["table"])
            if mu and code == "PL":
                con.execute(
                    """INSERT INTO season_standings (season, competition_code, division, position, played,
                         won, drawn, lost, goals_for, goals_against, points, is_final, source, updated_at)
                       VALUES (?, 'PL', 'Premier League', ?, ?, ?, ?, ?, ?, ?, ?, ?, 'football-data',
                               datetime('now'))
                       ON CONFLICT(season, competition_code) DO UPDATE SET
                         position=excluded.position, played=excluded.played, won=excluded.won,
                         drawn=excluded.drawn, lost=excluded.lost, goals_for=excluded.goals_for,
                         goals_against=excluded.goals_against, points=excluded.points,
                         is_final=excluded.is_final, source=excluded.source,
                         updated_at=excluded.updated_at""",
                    (season, mu["position"], mu["playedGames"], mu["won"], mu["draw"], mu["lost"],
                     mu["goalsFor"], mu["goalsAgainst"], mu["points"], is_final))
            if mu and code == "UCL":
                con.execute(
                    """UPDATE season_standings SET europe_competition='UEFA Champions League',
                         europe_result=? WHERE season=? AND competition_code='PL'""",
                    (f"리그 페이즈 {mu['position']}위 (진행 중)" if not is_final else None, season))

            label = f"{mu['position']}위 {mu['points']}점 ({mu['won']}승 {mu['draw']}무 {mu['lost']}패)" if mu else "맨유 없음"
            print(f"[{code}] {season} {n}팀 순위표 저장 · 맨유 {label}")
            msgs.append(f"{code}:{n}")
        log.message = f"{season} " + " ".join(msgs)
        con.commit()

    print("\n  PL 상위 5위 + 맨유")
    for r in con.execute(
            """SELECT position, team_name, played, goal_diff, points FROM league_table
               WHERE season=? AND competition_code='PL'
                 AND (position<=5 OR team_name LIKE 'Man United%') ORDER BY position""", (season,)):
        print(f"   {r['position']:>2}. {r['team_name']:<16} {r['played']}경기  득실 {r['goal_diff']:+d}  {r['points']}점")
    con.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
