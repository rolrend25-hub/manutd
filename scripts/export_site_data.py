"""DB → 웹페이지용 데이터 내보내기.

사용법:  python scripts/export_site_data.py
출력:    site/data/data.json  (GitHub Pages 등 서버용)
         site/data/data.js    (index.html 을 파일로 바로 열어도 보이도록 window.MUFC_DATA 로 감쌈)
"""
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "manutd.db"
OUT_DIR = ROOT / "site" / "data"


def rows(con, sql, args=()):
    return [dict(r) for r in con.execute(sql, args)]


def main() -> None:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    season = con.execute("SELECT season FROM seasons WHERE is_current=1").fetchone()["season"]

    data = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "season": season,
        "club": dict(con.execute("SELECT name, name_ko, nickname, founded_year, founded_as, stadium, "
                                 "stadium_capacity, city FROM club_info").fetchone()),
        "competitions": {r["code"]: r["name_ko"] for r in rows(con, "SELECT code, name_ko FROM competitions")},
        "matches": rows(con, """
            SELECT m.id, m.competition_code AS comp, m.stage, m.matchday, m.kickoff_utc,
                   m.kickoff_confirmed, m.home_away, m.opponent_name AS opponent,
                   t.crest_url AS opponent_crest, t.tla AS opponent_tla, m.venue, m.status,
                   m.mu_score, m.opp_score, m.mu_score_ht, m.opp_score_ht,
                   m.mu_pens, m.opp_pens, m.result, m.referee
            FROM matches m LEFT JOIN teams t ON t.id = m.opponent_id
            WHERE m.season = ? ORDER BY m.kickoff_utc""", (season,)),
        "tables": {},
        "seasons": rows(con, """
            SELECT season, competition_code AS comp, division, position, played, won, drawn, lost,
                   goals_for, goals_against, points, europe_competition, europe_result, is_final
            FROM season_standings ORDER BY season"""),
        "honours": rows(con, "SELECT competition_code AS code, competition_name AS name, season, "
                             "final_opponent, final_score, note FROM honours ORDER BY season"),
        "honours_count": rows(con, "SELECT competition_code AS code, competition_name AS name, titles "
                                   "FROM v_honours_count"),
        "managers": rows(con, "SELECT name, name_ko, nationality, start_date, end_date, is_caretaker, note "
                              "FROM managers ORDER BY start_date"),
        "timeline": rows(con, "SELECT year, title, title_ko, body_ko, category FROM history_timeline "
                              "ORDER BY year, sort_order"),
        "players": rows(con, """
            SELECT p.id, p.known_as, p.full_name, p.name_ko, p.position, p.date_of_birth, p.photo_url,
                   m.shirt_number, m.status AS squad_status,
                   a.status AS avail, a.chance_next, a.news,
                   COALESCE(s.appearances, 0) AS appearances, COALESCE(s.starts, 0) AS starts,
                   COALESCE(s.minutes, 0) AS minutes, COALESCE(s.goals, 0) AS goals,
                   COALESCE(s.assists, 0) AS assists, COALESCE(s.yellow_cards, 0) AS yellow_cards,
                   COALESCE(s.red_cards, 0) AS red_cards, COALESCE(s.clean_sheets, 0) AS clean_sheets,
                   s.saves, s.xg, s.xa
            FROM squad_memberships m
            JOIN players p ON p.id = m.player_id
            LEFT JOIN player_season_stats s ON s.player_id = p.id AND s.season = m.season
                                            AND s.competition_code = 'PL'
            LEFT JOIN player_availability a ON a.player_id = p.id
            WHERE m.season = ?
            ORDER BY s.goals DESC, s.assists DESC, s.minutes DESC""", (season,)),
        "transfers": rows(con, "SELECT player_name, direction, transfer_type, from_club, to_club, fee_text, "
                               "transfer_date, transfer_window, status FROM transfers "
                               "ORDER BY transfer_date DESC"),
        "last_sync": rows(con, """
            SELECT source, job, MAX(finished_utc) AS finished_utc FROM sync_log
            WHERE status='ok' GROUP BY source, job"""),
    }
    for comp in ("PL", "UCL"):
        data["tables"][comp] = rows(con, """
            SELECT l.position, l.team_name AS team, t.tla, t.crest_url AS crest, l.played, l.won, l.drawn,
                   l.lost, l.goals_for, l.goals_against, l.goal_diff, l.points, l.form,
                   (t.team_fd_id = 66) AS is_mu
            FROM league_table l LEFT JOIN teams t ON t.id = l.team_id
            WHERE l.season = ? AND l.competition_code = ? ORDER BY l.position""", (season, comp))
    con.close()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    (OUT_DIR / "data.json").write_text(text, encoding="utf-8")
    (OUT_DIR / "data.js").write_text(f"window.MUFC_DATA={text};\n", encoding="utf-8")
    print(f"내보내기 완료: {OUT_DIR}  ({len(text) // 1024} KB)")
    print(f"  경기 {len(data['matches'])} · PL 순위 {len(data['tables']['PL'])}팀 · "
          f"시즌 기록 {len(data['seasons'])} · 우승 {len(data['honours'])} · 선수 {len(data['players'])}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
