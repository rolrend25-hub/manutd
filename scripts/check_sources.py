"""데이터 출처(API) 사전 점검 — 동기화 전에 매번 실행.

- 키/토큰이 설정돼 있고 유효한지 (football-data 401/403 감지)
- 응답 구조가 ETL 이 기대하는 형태 그대로인지 (필드 이름 변경·삭제 감지)
- 맨유가 응답 안에 정상적으로 존재하는지

사용법: python scripts/check_sources.py      문제 있으면 종료코드 1
"""
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "etl"))
from common import DB_PATH, MUFC_FD, get_json, load_env  # noqa: E402

FD = "https://api.football-data.org/v4"
FPL = "https://fantasy.premierleague.com/api"

errors: list[str] = []
warns: list[str] = []


def fetch(url: str, headers=None):
    """일시적 네트워크 오류는 3번까지 재시도. 실패 시 None + 오류 기록."""
    last = None
    for i in range(3):
        try:
            return get_json(url, headers)
        except Exception as e:  # noqa: BLE001
            last = e
            if "HTTP 401" in str(e) or "HTTP 403" in str(e):
                break
            time.sleep(5 * (i + 1))
    msg = str(last)
    if "HTTP 401" in msg or "HTTP 403" in msg:
        errors.append(f"{url.split('?')[0]}: 인증 실패 — 토큰이 만료/잘못됨 또는 플랜 권한 없음")
    else:
        errors.append(f"{url.split('?')[0]}: 요청 실패 — {msg[:200]}")
    return None


def need(obj, path: str, where: str):
    """obj 에 a.b.c 경로가 있는지 확인. 없으면 구조 변경 오류."""
    cur = obj
    for k in path.split("."):
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            errors.append(f"{where}: 응답에 '{path}' 필드 없음 (API 구조 변경 의심)")
            return None
    return cur


def current_start_year() -> int:
    con = sqlite3.connect(DB_PATH)
    y = con.execute("SELECT start_year FROM seasons WHERE is_current=1").fetchone()
    con.close()
    if not y:
        errors.append("DB: is_current=1 시즌이 없음")
        return 0
    return y[0]


def check_football_data(year: int) -> None:
    token = load_env().get("FOOTBALL_DATA_TOKEN")
    if not token:
        errors.append("FOOTBALL_DATA_TOKEN 미설정 (.env 또는 GitHub Secrets)")
        return
    h = {"X-Auth-Token": token}

    d = fetch(f"{FD}/teams/{MUFC_FD}/matches?season={year}", h)
    if d is not None:
        ms = need(d, "matches", "football-data matches")
        if isinstance(ms, list):
            if not ms:
                errors.append(f"football-data matches: {year} 시즌 경기 0건")
            else:
                m = ms[0]
                for f in ("id", "utcDate", "status", "competition.code", "homeTeam.id", "awayTeam.id",
                          "score.fullTime.home", "score.fullTime.away"):
                    need(m, f, "football-data matches[0]")
                if not any(x.get("homeTeam", {}).get("id") == MUFC_FD or
                           x.get("awayTeam", {}).get("id") == MUFC_FD for x in ms):
                    errors.append("football-data matches: 맨유(id 66) 경기가 응답에 없음")
            print(f"  football-data 경기: {len(ms)}건 OK")

    d = fetch(f"{FD}/competitions/PL/standings?season={year}", h)
    if d is not None:
        st = need(d, "standings", "football-data standings")
        if isinstance(st, list):
            total = [s for s in st if s.get("type") == "TOTAL"]
            rows = total[0].get("table", []) if total else []
            if len(rows) != 20:
                errors.append(f"football-data PL 순위: TOTAL 표가 20팀이 아님 ({len(rows)})")
            elif not any(r.get("team", {}).get("id") == MUFC_FD for r in rows):
                errors.append("football-data PL 순위: 맨유가 없음")
            else:
                for f in ("position", "team.id", "playedGames", "won", "draw", "lost", "points",
                          "goalsFor", "goalsAgainst"):
                    need(rows[0], f, "football-data standings.table[0]")
                print("  football-data PL 순위: 20팀 OK")


def check_fpl() -> None:
    b = fetch(f"{FPL}/bootstrap-static/")
    if b is not None:
        for f in ("events", "teams", "elements", "element_types"):
            need(b, f, "FPL bootstrap")
        teams = b.get("teams") or []
        mu = [t for t in teams if t.get("code") == 1]  # etl/fetch_players.py MUFC_FPL_CODE 와 동일
        if not mu:
            errors.append("FPL bootstrap: 맨유 팀(code 1)이 없음 (구조 변경 의심)")
        elif mu[0].get("name") not in ("Man Utd", "Manchester United"):
            errors.append(f"FPL bootstrap: code 1 팀 이름이 맨유가 아님 ({mu[0].get('name')})")
        else:
            tid = mu[0]["id"]
            squad = [e for e in b.get("elements", []) if e.get("team") == tid]
            if not 15 <= len(squad) <= 60:
                errors.append(f"FPL bootstrap: 맨유 선수 수 비정상 ({len(squad)})")
            if squad:
                for f in ("id", "code", "web_name", "element_type", "minutes", "goals_scored", "assists",
                          "status", "news"):
                    need(squad[0], f, "FPL elements[0]")
            print(f"  FPL 선수: 맨유 {len(squad)}명 OK")
        if not any(e.get("is_current") for e in b.get("events", [])):
            warns.append("FPL bootstrap: 현재 라운드(is_current) 없음 — 시즌 사이 기간이면 정상")

    f = fetch(f"{FPL}/fixtures/")
    if f is not None:
        if not isinstance(f, list) or not f:
            errors.append("FPL fixtures: 목록이 비어 있음")
        else:
            for k in ("id", "event", "team_h", "team_a", "kickoff_time", "finished", "stats"):
                need(f[0], k, "FPL fixtures[0]")
            print(f"  FPL 경기: {len(f)}건 OK")


def main() -> int:
    print("[API 사전 점검]")
    year = current_start_year()
    if year:
        check_football_data(year)
    check_fpl()
    for w in warns:
        print("  ⚠", w)
    if errors:
        print(f"[API 사전 점검] 실패 — {len(errors)}건")
        for e in errors:
            print("  ✗", e)
        return 1
    print("[API 사전 점검] 통과" + (f" (경고 {len(warns)}건)" if warns else ""))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
