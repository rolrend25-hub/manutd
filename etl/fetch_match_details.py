"""PL 종료 경기 상세 (득점·도움·자책골·PK·카드·보너스) 수집 → match_events.

출처: Fantasy Premier League fixtures 의 경기별 stats (키 불필요, 호출 2회).
- 양 팀 모두 제공. 단, 득점 '분' 정보는 없음 → minute 은 NULL.
- 챔스 등 PL 외 대회는 무료 데이터에 상세가 없어 수집하지 않음 (스코어만).

details_synced
  0 = 아직 확정 전 (FPL 보너스 미확정 등) → 다음 동기화 때 다시 수집
  1 = FPL 이 경기 기록을 확정(finished=true) → 더 이상 바뀌지 않음

사용법: python etl/fetch_match_details.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import SyncLog, connect, get_json  # noqa: E402

BASE = "https://fantasy.premierleague.com/api"
MUFC_FPL_CODE = 1
# FPL stats identifier → match_events.event_type
EVENT_MAP = {
    "goals_scored": "goal",
    "assists": "assist",
    "own_goals": "own_goal",
    "penalties_missed": "missed_penalty",
    "penalties_saved": "penalty_saved",
    "yellow_cards": "yellow",
    "red_cards": "red",
}


def main() -> None:
    con = connect()
    season = con.execute("SELECT season FROM seasons WHERE is_current=1").fetchone()["season"]
    with SyncLog(con, "fpl", "match_details") as log:
        boot = get_json(f"{BASE}/bootstrap-static/")
        fixtures = get_json(f"{BASE}/fixtures/")
        log.api_calls += 2
        mu_team = next(t for t in boot["teams"] if t["code"] == MUFC_FPL_CODE)["id"]
        el = {e["id"]: e for e in boot["elements"]}
        pid_by_code = {r[0]: r[1] for r in con.execute(
            "SELECT player_fpl_code, id FROM players WHERE player_fpl_code IS NOT NULL")}
        fx_by_id = {f["id"]: f for f in fixtures}

        targets = con.execute(
            """SELECT id, match_fpl_id, opponent_name, kickoff_utc, mu_score, opp_score FROM matches
               WHERE season=? AND competition_code='PL' AND status='FINISHED' AND match_fpl_id IS NOT NULL
                 AND COALESCE(details_synced, 0) = 0""", (season,)).fetchall()
        done = 0
        for m in targets:
            f = fx_by_id.get(m["match_fpl_id"])
            if not f or not (f.get("finished") or f.get("finished_provisional")) or not f.get("stats"):
                print(f"  {m['kickoff_utc'][:10]} vs {m['opponent_name']}: FPL 상세 아직 없음 → 다음에 재시도")
                continue
            mu_is_home = f["team_h"] == mu_team
            con.execute("DELETE FROM match_events WHERE match_id=?", (m["id"],))
            n = 0
            for st in f["stats"]:
                ident = st["identifier"]
                if ident not in EVENT_MAP and ident != "bonus":
                    continue
                for side_key in ("h", "a"):
                    side = "MU" if (side_key == "h") == mu_is_home else "OPP"
                    for item in st.get(side_key, []):
                        e = el.get(item["element"], {})
                        name = e.get("web_name") or f"Player #{item['element']}"
                        pid = pid_by_code.get(e.get("code")) if side == "MU" else None
                        if ident == "bonus":  # 보너스는 1행 + 점수
                            con.execute(
                                "INSERT INTO match_events (match_id, team_side, event_type, player_name, "
                                "player_id, detail) VALUES (?, ?, 'bonus', ?, ?, ?)",
                                (m["id"], side, name, pid, str(item["value"])))
                            n += 1
                            continue
                        for _ in range(int(item["value"])):  # 2골이면 2행
                            con.execute(
                                "INSERT INTO match_events (match_id, team_side, event_type, player_name, "
                                "player_id) VALUES (?, ?, ?, ?, ?)",
                                (m["id"], side, EVENT_MAP[ident], name, pid))
                            n += 1
            final = 1 if f.get("finished") else 0
            con.execute("UPDATE matches SET details_synced=? WHERE id=?", (final, m["id"]))
            log.rows += n
            done += 1
            print(f"  {m['kickoff_utc'][:10]} vs {m['opponent_name']} {m['mu_score']}-{m['opp_score']}: "
                  f"이벤트 {n}건{'' if final else ' (FPL 미확정 → 다음에 갱신)'}")
        log.message = f"{season} matches={done}/{len(targets)} events={log.rows}"
        con.commit()
    print(f"[FPL 경기 상세] 대상 {len(targets)}경기 중 {done}경기 수집")
    con.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
