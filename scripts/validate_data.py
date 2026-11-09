"""동기화 후 데이터 검증 — 통과해야만 커밋·배포.

사용법
  python scripts/validate_data.py                       # 현재 DB + site/data 검증
  python scripts/validate_data.py --baseline old.db     # 직전 커밋 DB 와 비교 검증 추가

✗ 오류 → 종료코드 1 (커밋·배포 중단 + 알림)
⚠ 경고 → 배포는 진행, 알림만
"""
import json
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "manutd.db"
SITE_DATA = ROOT / "site" / "data"
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
MU_FD = 66

errors: list[str] = []
warns: list[str] = []


def err(m): errors.append(m)
def warn(m): warns.append(m)


def q(con, sql, args=()):
    return con.execute(sql, args).fetchall()


def check_matches(con, season):
    ms = q(con, "SELECT id, competition_code, matchday, kickoff_utc, status, mu_score, opp_score, result, "
                "opponent_name, match_fd_id, match_fpl_id FROM matches WHERE season=?", (season,))
    if not 30 <= len(ms) <= 80:
        err(f"경기 수 비정상: {len(ms)}경기 (정상 범위 30~80)")
    pl = [m for m in ms if m[1] == "PL"]
    if len(pl) > 38:
        err(f"PL 경기가 38경기 초과: {len(pl)}")
    for d in q(con, "SELECT match_fd_id, COUNT(*) FROM matches WHERE match_fd_id IS NOT NULL "
                    "GROUP BY match_fd_id HAVING COUNT(*)>1"):
        err(f"중복 경기: match_fd_id={d[0]} {d[1]}건")
    now = datetime.now(timezone.utc)
    for (mid, comp, md, ko, st, mu, op, res, opp, fd, fpl) in ms:
        tag = f"{(ko or '')[:10]} {comp} vs {opp}"
        if not ko or not ISO.match(ko):
            err(f"{tag}: 킥오프 시각 형식 오류 ({ko})")
            continue
        if comp == "PL" and md is not None and not 1 <= md <= 38:
            err(f"{tag}: PL 라운드 범위 오류 ({md})")
        if st == "FINISHED":
            if mu is None or op is None:
                err(f"{tag}: 종료 경기인데 스코어 없음")
                continue
            if not (0 <= mu <= 15 and 0 <= op <= 15):
                err(f"{tag}: 스코어 비정상 ({mu}-{op})")
            exp = "W" if mu > op else "L" if mu < op else "D"
            if res not in (exp, None) and comp == "PL":
                err(f"{tag}: 결과(result={res})가 스코어 {mu}-{op} 와 불일치")
        else:
            kt = datetime.fromisoformat(ko.replace("Z", "+00:00"))
            if st not in ("POSTPONED", "CANCELLED", "SUSPENDED") and kt < now - timedelta(hours=6):
                warn(f"{tag}: 킥오프 6시간 지났는데 아직 '{st}' (API 결과 지연 가능)")


def check_tables(con, season):
    for comp, n in (("PL", 20), ("UCL", 36)):
        rows = q(con, "SELECT position, team_name, played, won, drawn, lost, goals_for, goals_against, "
                      "goal_diff, points FROM league_table WHERE season=? AND competition_code=?",
                 (season, comp))
        if len(rows) != n:
            (err if comp == "PL" else warn)(f"{comp} 순위표 팀 수 {len(rows)} (기대 {n})")
        if sorted(r[0] for r in rows) != list(range(1, len(rows) + 1)):
            err(f"{comp} 순위표 순위 번호가 1~{len(rows)} 연속이 아님")
        for (pos, team, p, w, d, l, gf, ga, gd, pts) in rows:
            if p != w + d + l:
                err(f"{comp} {team}: 경기수 {p} ≠ 승+무+패 {w + d + l}")
            if gd is not None and gd != gf - ga:
                err(f"{comp} {team}: 득실차 {gd} ≠ {gf}-{ga}")
            if pts != 3 * w + d:
                warn(f"{comp} {team}: 승점 {pts} ≠ 3×승+무 {3 * w + d} (승점 삭감이면 정상)")
        if comp == "PL" and rows and sum(r[6] for r in rows) != sum(r[7] for r in rows):
            err("PL 순위표: 전체 득점 합 ≠ 전체 실점 합")


def check_mu_cross(con, season):
    """football-data 경기 결과 ↔ 순위표 ↔ FPL 선수 기록 교차 검증."""
    mu = q(con, "SELECT l.played, l.won, l.drawn, l.lost, l.goals_for, l.goals_against, l.points, l.position "
                "FROM league_table l JOIN teams t ON t.id=l.team_id "
                "WHERE l.season=? AND l.competition_code='PL' AND t.team_fd_id=?", (season, MU_FD))
    if not mu:
        err("PL 순위표에 맨유가 없음")
        return
    p, w, d, l, gf, ga, pts, pos = mu[0]
    fin = q(con, "SELECT mu_score, opp_score FROM matches WHERE season=? AND competition_code='PL' "
                 "AND status='FINISHED' AND mu_score IS NOT NULL AND opp_score IS NOT NULL", (season,))
    cw = sum(a > b for a, b in fin); cd = sum(a == b for a, b in fin); cl = sum(a < b for a, b in fin)
    cgf = sum(a for a, _ in fin); cga = sum(b for _, b in fin)
    if (p, w, d, l, gf, ga) != (len(fin), cw, cd, cl, cgf, cga):
        warn(f"맨유 PL: 순위표({p}경기 {w}승{d}무{l}패 {gf}-{ga}) ≠ 경기결과 집계"
             f"({len(fin)}경기 {cw}승{cd}무{cl}패 {cgf}-{cga}) — 순위표 갱신 지연 가능")

    ss = q(con, "SELECT position, played, won, drawn, lost, points FROM season_standings "
                "WHERE season=? AND competition_code='PL'", (season,))
    if ss and ss[0] != (pos, p, w, d, l, pts):
        err(f"season_standings 맨유 행 {ss[0]} ≠ 순위표 {(pos, p, w, d, l, pts)}")

    # FPL 선수 득점 합은 팀 득점 이하 (상대 자책골 때문에 같거나 작음)
    fpl_goals = q(con, "SELECT COALESCE(SUM(goals),0) FROM player_season_stats WHERE season=? "
                       "AND competition_code='PL'", (season,))[0][0]
    if fpl_goals > cgf:
        err(f"FPL 선수 득점 합 {fpl_goals} > 맨유 PL 득점 {cgf} (FPL↔football-data 불일치)")

    for (ko, opp, mus, fid, n, g, a, maxmin) in q(con, """
            SELECT m.kickoff_utc, m.opponent_name, m.mu_score, m.match_fpl_id,
                   COUNT(s.player_id), COALESCE(SUM(s.goals),0), COALESCE(SUM(s.assists),0), MAX(s.minutes)
            FROM matches m LEFT JOIN player_match_stats s ON s.match_id=m.id
            WHERE m.season=? AND m.competition_code='PL' AND m.status='FINISHED'
            GROUP BY m.id""", (season,)):
        tag = f"{ko[:10]} PL vs {opp}"
        if mus is None:
            continue  # check_matches 에서 이미 오류 처리
        if fid is None:
            warn(f"{tag}: FPL 경기와 연결 안 됨")
            continue
        if n == 0:
            warn(f"{tag}: 선수 경기 기록 없음 (FPL 반영 지연 가능)")
            continue
        if g > mus:
            err(f"{tag}: 선수 득점 합 {g} > 팀 득점 {mus}")
        if a > mus:
            err(f"{tag}: 도움 합 {a} > 팀 득점 {mus}")
        if not 11 <= n <= 16:
            warn(f"{tag}: 출전 선수 {n}명 (보통 11~16명)")
        if maxmin and maxmin > 130:
            err(f"{tag}: 출전 시간 {maxmin}분 비정상")


def check_players(con, season):
    n = q(con, "SELECT COUNT(*) FROM squad_memberships WHERE season=? AND status='active'", (season,))[0][0]
    if not 20 <= n <= 45:
        err(f"현재 스쿼드 인원 비정상: {n}명 (정상 20~45)")
    for (name, c) in q(con, "SELECT COALESCE(known_as, full_name), COUNT(*) FROM players "
                            "WHERE player_fpl_code IS NOT NULL GROUP BY player_fpl_code HAVING COUNT(*)>1"):
        err(f"선수 중복: {name} {c}건")
    bad = q(con, "SELECT COUNT(*) FROM player_season_stats WHERE season=? AND "
                 "(goals<0 OR assists<0 OR minutes<0 OR appearances<0 OR starts>appearances)", (season,))[0][0]
    if bad:
        err(f"선수 시즌 기록 음수/모순 {bad}건")


def check_sync_log(con):
    for (src, job, st, msg) in q(con, """
            SELECT source, job, status, message FROM sync_log s
            WHERE id = (SELECT MAX(id) FROM sync_log WHERE source=s.source AND job=s.job)"""):
        if st != "ok":
            err(f"최근 동기화 실패: {src}/{job} — {(msg or '')[:150]}")


def check_baseline(con, base_path, season):
    b = sqlite3.connect(base_path)
    try:
        old = {r[0]: r[1:] for r in q(b, "SELECT match_fd_id, mu_score, opp_score, status, kickoff_utc, "
                                         "opponent_name FROM matches WHERE season=? AND match_fd_id IS NOT NULL",
                                      (season,))}
        old_squad = q(b, "SELECT COUNT(*) FROM squad_memberships WHERE season=? AND status='active'",
                      (season,))[0][0]
    except sqlite3.Error as e:
        warn(f"이전 DB 비교 불가: {e}")
        return
    finally:
        b.close()
    new = {r[0]: r[1:] for r in q(con, "SELECT match_fd_id, mu_score, opp_score, status, kickoff_utc, "
                                       "opponent_name FROM matches WHERE season=? AND match_fd_id IS NOT NULL",
                                  (season,))}
    if len(new) < len(old) - 3:
        err(f"경기 수가 급감: {len(old)} → {len(new)}")
    for fd, (ms, os_, st, ko, opp) in old.items():
        if st != "FINISHED":
            continue
        if fd not in new:
            err(f"이전에 종료된 경기가 사라짐: {ko[:10]} vs {opp}")
        elif new[fd][:2] != (ms, os_):
            warn(f"종료 경기 스코어 변경: {ko[:10]} vs {opp} {ms}-{os_} → {new[fd][0]}-{new[fd][1]} (공식 정정 여부 확인)")
        elif new[fd][2] != "FINISHED":
            err(f"종료 경기 상태가 되돌아감: {ko[:10]} vs {opp} → {new[fd][2]}")
    new_squad = q(con, "SELECT COUNT(*) FROM squad_memberships WHERE season=? AND status='active'",
                  (season,))[0][0]
    if new_squad < old_squad - 5:
        err(f"스쿼드 인원 급감: {old_squad} → {new_squad}")


def check_export(con, season):
    try:
        j = json.loads((SITE_DATA / "data.json").read_text(encoding="utf-8"))
        js = (SITE_DATA / "data.js").read_text(encoding="utf-8")
    except (OSError, ValueError) as e:
        err(f"사이트 데이터 파일 읽기 실패: {e}")
        return
    for k in ("generated_utc", "synced_utc", "season", "matches", "tables", "players", "last_sync"):
        if k not in j:
            err(f"data.json 에 '{k}' 없음")
    if j.get("season") != season:
        err(f"data.json 시즌 {j.get('season')} ≠ DB 현재 시즌 {season}")
    n = q(con, "SELECT COUNT(*) FROM matches WHERE season=?", (season,))[0][0]
    if len(j.get("matches", [])) != n:
        err(f"data.json 경기 수 {len(j.get('matches', []))} ≠ DB {n} (내보내기 누락)")
    if not js.startswith("window.MUFC_DATA=") or js.strip()[len("window.MUFC_DATA="):-1] != \
            json.dumps(j, ensure_ascii=False, separators=(",", ":")):
        err("data.js 내용이 data.json 과 다름")


def main() -> int:
    base = None
    if "--baseline" in sys.argv:
        base = sys.argv[sys.argv.index("--baseline") + 1]
    con = sqlite3.connect(DB_PATH)
    try:
        ok = q(con, "PRAGMA integrity_check")[0][0]
        if ok != "ok":
            err(f"DB 무결성 검사 실패: {ok}")
        r = q(con, "SELECT season FROM seasons WHERE is_current=1")
        if len(r) != 1:
            err(f"현재 시즌(is_current=1)이 {len(r)}개")
            return report()
        season = r[0][0]
        check_matches(con, season)
        check_tables(con, season)
        check_mu_cross(con, season)
        check_players(con, season)
        check_sync_log(con)
        if base and Path(base).exists() and Path(base).stat().st_size > 0:
            check_baseline(con, base, season)
        check_export(con, season)
    finally:
        con.close()
    return report()


def report() -> int:
    print("[데이터 검증]")
    for w in warns:
        print("  ⚠", w)
    for e in errors:
        print("  ✗", e)
    if errors:
        print(f"[데이터 검증] 실패 — 오류 {len(errors)}건, 경고 {len(warns)}건")
        return 1
    print("[데이터 검증] 통과" + (f" (경고 {len(warns)}건)" if warns else ""))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
