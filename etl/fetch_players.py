"""맨유 선수·PL 스탯 수집 (Fantasy Premier League 비공식 API, 키 불필요).

사용법:
    python etl/fetch_players.py            # 스쿼드 + 시즌 합계 + 경기별 기록
    python etl/fetch_players.py --quick    # 스쿼드·부상 정보만 (선수별 요청 생략, 호출 2회)

저장 테이블
    players              선수 기본 정보 (player_fpl_code 로 매칭 — 시즌이 바뀌어도 유지되는 값)
    squad_memberships    이번 시즌 등번호·상태(active / loaned_out / left)
    player_availability  부상·징계·출전 가능성
    player_season_stats  PL 시즌 합계 (competition_code='PL')
    player_match_stats   PL 경기별 출전시간·골·도움·카드·태클
    matches.match_fpl_id FPL 경기 id 연결 (경기 상세 수집용)

* 시즌 합계는 '맨유 경기'만 더해서 계산 → 시즌 중 이적해 온 선수의 전 소속팀 기록은 제외됨.
* FPL 은 PL 경기만 제공 → 챔스 등 다른 대회 선수 기록은 없음.
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import SyncLog, connect, get_json, utc_now  # noqa: E402

BASE = "https://fantasy.premierleague.com/api"
MUFC_FPL_CODE = 1  # FPL team 'code' (id 는 시즌마다 바뀔 수 있음)
POS = {1: "GK", 2: "DF", 3: "MF", 4: "FW"}
PHOTO = "https://resources.premierleague.com/premierleague/photos/players/110x140/p{}.png"


def squad_status(e: dict) -> str:
    if e["status"] != "u":
        return "active"
    news = (e.get("news") or "").lower()
    return "loaned_out" if "loan" in news else "left"


def to_float(v):
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="선수별 경기 기록 요청 생략")
    args = ap.parse_args()

    con = connect()
    season = con.execute("SELECT season FROM seasons WHERE is_current=1").fetchone()["season"]

    with SyncLog(con, "fpl", "players") as log:
        boot = get_json(f"{BASE}/bootstrap-static/")
        log.api_calls += 1
        team = next(t for t in boot["teams"] if t["code"] == MUFC_FPL_CODE)
        squad = [e for e in boot["elements"] if e["team"] == team["id"]]
        print(f"[FPL] {season} {team['name']} 선수 {len(squad)}명")

        # ---- 1) FPL 경기 id ↔ 우리 matches 연결 (PL, 킥오프 시각으로 매칭) ----
        fixtures = get_json(f"{BASE}/fixtures/")
        log.api_calls += 1
        mu_fx = {f["id"]: f for f in fixtures if team["id"] in (f["team_h"], f["team_a"])}
        fx_to_match, linked = {}, 0
        for f in mu_fx.values():
            if not f.get("kickoff_time"):
                continue
            r = con.execute(
                "SELECT id, match_fpl_id FROM matches WHERE season=? AND competition_code='PL' "
                "AND kickoff_utc=?", (season, f["kickoff_time"])).fetchone()
            if r:
                fx_to_match[f["id"]] = r["id"]
                if r["match_fpl_id"] != f["id"]:
                    con.execute("UPDATE matches SET match_fpl_id=? WHERE id=?", (f["id"], r["id"]))
                    linked += 1
        print(f"  PL 경기 연결: {len(fx_to_match)}/{len(mu_fx)} (신규 {linked})")

        # ---- 2) 선수 기본 정보 / 스쿼드 / 출전 가능 여부 ----
        pid_by_element = {}
        for e in squad:
            full = f"{e['first_name']} {e['second_name']}".strip()
            con.execute(
                """INSERT INTO players (full_name, known_as, position, date_of_birth, photo_url,
                       player_fpl_code, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                   ON CONFLICT(player_fpl_code) DO UPDATE SET
                     full_name=excluded.full_name, known_as=excluded.known_as,
                     position=excluded.position, date_of_birth=excluded.date_of_birth,
                     photo_url=excluded.photo_url, updated_at=excluded.updated_at""",
                (full, e["web_name"], POS.get(e["element_type"]), e.get("birth_date"),
                 PHOTO.format(e["code"]), e["code"]))
            pid = con.execute("SELECT id FROM players WHERE player_fpl_code=?", (e["code"],)).fetchone()[0]
            pid_by_element[e["id"]] = pid

            con.execute(
                """INSERT INTO squad_memberships (player_id, season, shirt_number, joined_date, status)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(player_id, season) DO UPDATE SET
                     shirt_number=COALESCE(excluded.shirt_number, shirt_number),
                     joined_date=COALESCE(excluded.joined_date, joined_date), status=excluded.status""",
                (pid, season, e.get("squad_number"), e.get("team_join_date"), squad_status(e)))
            con.execute(
                """INSERT INTO player_availability (player_id, status, chance_next, news, news_added_utc, updated_at)
                   VALUES (?, ?, ?, ?, ?, datetime('now'))
                   ON CONFLICT(player_id) DO UPDATE SET status=excluded.status,
                     chance_next=excluded.chance_next, news=excluded.news,
                     news_added_utc=excluded.news_added_utc, updated_at=excluded.updated_at""",
                (pid, e["status"], e.get("chance_of_playing_next_round"), e.get("news") or None,
                 e.get("news_added")))
            log.rows += 1

        if args.quick:
            log.message = f"{season} quick players={len(squad)}"
            con.commit()
            print("  --quick: 스쿼드·부상 정보만 갱신")
            con.close()
            return

        # ---- 3) 선수별 경기 기록 → 경기별 스탯 + 시즌 합계 ----
        print("  선수별 경기 기록 수집 중", end="", flush=True)
        for e in squad:
            pid = pid_by_element[e["id"]]
            summary = get_json(f"{BASE}/element-summary/{e['id']}/")
            log.api_calls += 1
            print(".", end="", flush=True)
            time.sleep(0.3)  # 비공식 API 예의상 간격

            tot = dict(app=0, starts=0, minutes=0, goals=0, assists=0, yc=0, rc=0, cs=0, saves=0, xg=0.0, xa=0.0)
            for h in summary.get("history", []):
                if h["fixture"] not in mu_fx:  # 다른 팀 소속 시절 경기 제외
                    continue
                tot["minutes"] += h["minutes"]
                tot["app"] += 1 if h["minutes"] > 0 else 0
                tot["starts"] += h.get("starts", 0)
                tot["goals"] += h["goals_scored"]
                tot["assists"] += h["assists"]
                tot["yc"] += h["yellow_cards"]
                tot["rc"] += h["red_cards"]
                tot["cs"] += h["clean_sheets"]
                tot["saves"] += h["saves"]
                tot["xg"] += to_float(h.get("expected_goals")) or 0
                tot["xa"] += to_float(h.get("expected_assists")) or 0

                match_id = fx_to_match.get(h["fixture"])
                if match_id and h["minutes"] > 0:
                    con.execute(
                        """INSERT INTO player_match_stats (match_id, player_id, minutes, goals, assists,
                               tackles, yellow, red)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                           ON CONFLICT(match_id, player_id) DO UPDATE SET minutes=excluded.minutes,
                             goals=excluded.goals, assists=excluded.assists, tackles=excluded.tackles,
                             yellow=excluded.yellow, red=excluded.red""",
                        (match_id, pid, h["minutes"], h["goals_scored"], h["assists"], h.get("tackles"),
                         h["yellow_cards"], h["red_cards"]))

            con.execute(
                """INSERT INTO player_season_stats (player_id, season, competition_code, appearances, starts,
                       minutes, goals, assists, yellow_cards, red_cards, clean_sheets, saves, xg, xa,
                       source, updated_at)
                   VALUES (?, ?, 'PL', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'fpl', datetime('now'))
                   ON CONFLICT(player_id, season, competition_code) DO UPDATE SET
                     appearances=excluded.appearances, starts=excluded.starts, minutes=excluded.minutes,
                     goals=excluded.goals, assists=excluded.assists, yellow_cards=excluded.yellow_cards,
                     red_cards=excluded.red_cards, clean_sheets=excluded.clean_sheets, saves=excluded.saves,
                     xg=excluded.xg, xa=excluded.xa, source=excluded.source, updated_at=excluded.updated_at""",
                (pid, season, tot["app"], tot["starts"], tot["minutes"], tot["goals"], tot["assists"],
                 tot["yc"], tot["rc"], tot["cs"],
                 tot["saves"] if POS.get(e["element_type"]) == "GK" else None,
                 round(tot["xg"], 2), round(tot["xa"], 2)))
        print()
        log.message = f"{season} players={len(squad)} fixtures_linked={len(fx_to_match)}"
        con.commit()

    # ---- 요약 출력 ----
    print("\n  득점 상위")
    for r in con.execute(
            """SELECT p.known_as, p.position, s.appearances, s.minutes, s.goals, s.assists, s.xg
               FROM player_season_stats s JOIN players p ON p.id=s.player_id
               WHERE s.season=? AND s.competition_code='PL' AND s.minutes>0
               ORDER BY s.goals DESC, s.assists DESC, s.minutes DESC LIMIT 6""", (season,)):
        print(f"   {r['known_as']:<14} {r['position']}  {r['appearances']}경기 {r['minutes']:>4}분  "
              f"{r['goals']}골 {r['assists']}도움  xG {r['xg']}")
    out = con.execute(
        """SELECT p.known_as, a.status, a.news FROM player_availability a JOIN players p ON p.id=a.player_id
           JOIN squad_memberships m ON m.player_id=p.id AND m.season=?
           WHERE a.status IN ('i','s','d') AND m.status='active' ORDER BY a.status""", (season,)).fetchall()
    print(f"\n  부상·징계·불확실 {len(out)}명")
    for r in out:
        print(f"   [{r['status']}] {r['known_as']}: {r['news']}")
    n = con.execute("SELECT COUNT(*) FROM player_match_stats").fetchone()[0]
    print(f"\n  경기별 선수 기록 {n}행 · 완료 {utc_now()}")
    con.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
