"""DB → 웹페이지용 데이터 내보내기.

사용법:  python scripts/export_site_data.py
출력:    site/data/data.json  (GitHub Pages 등 서버용)
         site/data/data.js    (index.html 을 파일로 바로 열어도 보이도록 window.MUFC_DATA 로 감쌈)
         site/data/archive.js (지난 시즌 경기·상세, window.MUFC_ARCHIVE — '일정·결과'에서 지난 시즌 고를 때만 불러옴)
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


MATCH_COLS = """m.id, m.season, m.competition_code AS comp, m.stage, m.matchday, m.kickoff_utc,
                   m.kickoff_confirmed, m.home_away, m.opponent_name AS opponent,
                   t.crest_url AS opponent_crest, t.tla AS opponent_tla, m.venue, m.status,
                   m.mu_score, m.opp_score, m.mu_score_ht, m.opp_score_ht,
                   m.mu_pens, m.opp_pens, m.result, m.referee"""


def season_matches(con, seasons: list[str]) -> list[dict]:
    q = ",".join("?" * len(seasons))
    return rows(con, f"""SELECT {MATCH_COLS} FROM matches m LEFT JOIN teams t ON t.id = m.opponent_id
                         WHERE m.season IN ({q}) ORDER BY m.kickoff_utc""", seasons)


def match_details(con, seasons: list[str]) -> dict:
    """경기 상세 (#match/<id>): 이벤트 + 요약 + 출전 선수 + 팀 스탯. 키는 matches.id (JSON 이라 문자열)."""
    q = ",".join("?" * len(seasons))
    details: dict = {}
    d = lambda mid: details.setdefault(str(mid), {"events": []})  # noqa: E731
    for r in rows(con, f"""SELECT e.match_id, e.team_side AS side, e.event_type AS type, e.player_name AS player,
                                 e.detail, e.minute, e.extra_minute
                          FROM match_events e JOIN matches m ON m.id = e.match_id
                          WHERE m.season IN ({q}) ORDER BY e.match_id, COALESCE(e.minute, 0), e.id""", seasons):
        d(r.pop("match_id"))["events"].append(r)
    for r in rows(con, f"""SELECT a.match_id, a.analysis_md AS summary, a.player_of_match AS potm, a.model
                          FROM match_analyses a JOIN matches m ON m.id = a.match_id WHERE m.season IN ({q})""",
                  seasons):
        d(r.pop("match_id")).update(r)
    # 출전 선수: 선발/교체 + 출전시간·골·도움·카드 (현재 시즌 PL = FPL, 지난 시즌 = API-Football)
    for r in rows(con, f"""SELECT l.match_id, l.player_name AS name, l.position AS pos, l.shirt_number AS no,
                                 l.is_starter AS starter, l.formation, s.minutes, s.goals, s.assists, s.yellow, s.red,
                                 s.rating
                          FROM match_lineups l JOIN matches m ON m.id = l.match_id
                          LEFT JOIN player_match_stats s ON s.match_id = l.match_id AND s.player_id = l.player_id
                          WHERE m.season IN ({q}) AND l.team_side = 'MU'
                          ORDER BY l.match_id, l.is_starter DESC,
                                   CASE l.position WHEN 'GK' THEN 1 WHEN 'DF' THEN 2 WHEN 'MF' THEN 3 ELSE 4 END,
                                   s.minutes DESC""", seasons):
        mid, form = r.pop("match_id"), r.pop("formation")
        if r["rating"] is None:
            r.pop("rating")
        x = d(mid)
        x.setdefault("lineup", []).append(r)
        if form:
            x["formation"] = form
    for r in rows(con, f"""SELECT l.match_id, MAX(l.formation) AS f FROM match_lineups l JOIN matches m ON m.id = l.match_id
                          WHERE m.season IN ({q}) AND l.team_side = 'OPP' GROUP BY l.match_id""", seasons):
        if r["f"]:
            d(r["match_id"])["opp_formation"] = r["f"]
    for r in rows(con, f"""SELECT s.match_id, s.team_side AS side, s.possession_pct AS poss, s.shots,
                                 s.shots_on_target AS sot, s.corners, s.fouls, s.offsides, s.passes,
                                 s.pass_accuracy_pct AS pass_pct, s.saves
                          FROM match_team_stats s JOIN matches m ON m.id = s.match_id WHERE m.season IN ({q})""",
                  seasons):
        d(r.pop("match_id")).setdefault("stats", {})[r.pop("side")] = r
    for r in rows(con, f"SELECT id FROM matches WHERE season IN ({q}) AND match_af_id IS NOT NULL "
                       "AND details_synced=1", seasons):
        d(r["id"])["src"] = "apif"
    return details


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
        "matches": season_matches(con, [season]),
        "tables": {},
        "seasons": rows(con, """
            SELECT season, competition_code AS comp, division, position, played, won, drawn, lost,
                   goals_for, goals_against, points, europe_competition, europe_result, is_final,
                   fa_cup_result AS fa_cup, league_cup_result AS league_cup,
                   top_scorer, top_scorer_goals, source
            FROM season_standings ORDER BY season"""),
        "honours": rows(con, "SELECT competition_code AS code, competition_name AS name, season, "
                             "final_opponent, final_score, note FROM honours ORDER BY season"),
        "honours_count": rows(con, "SELECT competition_code AS code, competition_name AS name, titles "
                                   "FROM v_honours_count"),
        # 맨유 공식 엠블럼: 저장소에 파일로 올리지 않고 football-data 서버 이미지를 링크만 함
        "mu_crest": (con.execute("SELECT crest_url FROM teams WHERE team_fd_id = 66").fetchone() or [None])[0],
        "managers": rows(con, "SELECT name, name_ko, nationality, start_date, end_date, is_caretaker, note, note_en, "
                              "matches, wins, draws, losses FROM managers ORDER BY start_date"),
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
        "transfers": rows(con, "SELECT player_name, position, direction, transfer_type, from_club, to_club, fee_text, "
                               "transfer_date, transfer_window, season, status, source, source_url, verify_status, verify_note FROM transfers "
                               "ORDER BY transfer_date DESC"),
        "transfer_checks": rows(con, "SELECT season, player_name, kind, detail, first_seen_utc FROM transfer_checks "
                                     "WHERE resolved_utc IS NULL ORDER BY first_seen_utc")
                           if con.execute("SELECT 1 FROM sqlite_master WHERE name='transfer_checks'").fetchone() else [],
        "last_sync": rows(con, """
            SELECT source, job, MAX(finished_utc) AS finished_utc FROM sync_log
            WHERE status='ok' GROUP BY source, job"""),
    }
    data["match_details"] = match_details(con, [season])
    # 지난 시즌 (경기 기록이 있는 시즌만) → archive.js 로 따로 (첫 화면 용량 유지)
    past = [r[0] for r in con.execute("SELECT DISTINCT season FROM matches WHERE season <> ? AND status='FINISHED' "
                                      "ORDER BY season DESC", (season,))]
    data["archive_seasons"] = past
    archive = {"matches": season_matches(con, past), "match_details": match_details(con, past)} if past else None

    # 메인 화면: 다음 경기 프리뷰 (etl/build_preview.py) + 주요 뉴스 (etl/fetch_news.py)
    has = lambda t: con.execute("SELECT 1 FROM sqlite_master WHERE name=?", (t,)).fetchone()  # noqa: E731
    pv = con.execute("SELECT data_json FROM match_previews p JOIN matches m ON m.id=p.match_id "
                     "WHERE m.status NOT IN ('FINISHED','CANCELLED') ORDER BY m.kickoff_utc LIMIT 1").fetchone() \
        if has("match_previews") else None
    data["preview"] = json.loads(pv[0]) if pv else None
    ko = {r[1] for r in con.execute("PRAGMA table_info(news_items)")} >= {"title_ko", "summary_ko"} if has("news_items") else False
    ko_cols = "title_ko, summary_ko" if ko else "NULL AS title_ko, NULL AS summary_ko"  # etl/translate_news.py (DeepL)
    data["news"] = rows(con, f"""SELECT url, source, source_name, source_tier AS tier, title, summary, {ko_cols},
                                      published_utc, tags, journalists, cluster FROM news_items
                               ORDER BY published_utc DESC LIMIT 40""") if has("news_items") else []

    # 화면 우측 상단 표시용: 모든 수집 작업 중 가장 최근 성공 완료 시각
    data["synced_utc"] = max((s["finished_utc"] for s in data["last_sync"] if s["finished_utc"]),
                             default=None)
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
    if archive:
        atext = json.dumps(archive, ensure_ascii=False, separators=(",", ":"))
        (OUT_DIR / "archive.js").write_text("window.MUFC_ARCHIVE=" + atext + ";" + chr(10), encoding="utf-8")
        print(f"  지난 시즌 {', '.join(past)}: 경기 {len(archive['matches'])} ({len(atext) // 1024} KB, archive.js)")
    print(f"  경기 {len(data['matches'])} · PL 순위 {len(data['tables']['PL'])}팀 · "
          f"시즌 기록 {len(data['seasons'])} · 우승 {len(data['honours'])} · 선수 {len(data['players'])}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
