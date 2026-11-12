"""시즌 전환 자동 처리 — football-data 의 PL '현재 시즌'이 넘어가면 우리 DB 도 새 시즌으로 전환.

사용법:
    python etl/season_rollover.py            # 매 동기화 맨 앞에서 실행 (대부분 '전환 없음')
    python etl/season_rollover.py --dry-run
    python etl/season_rollover.py --force-year 2027   # 테스트용: football-data 응답 대신 이 연도를 현재 시즌으로 간주

전환 조건 (모두 만족해야 함)
- football-data `/competitions/PL` currentSeason 시작 연도 = 우리 현재 시즌 + 1
- 오늘이 새 시즌 시작 연도의 6월 1일 이후

전환 순서
1) seasons: 새 시즌 행 추가 → is_current 전환
2) 지난 시즌 마무리: 최종 순위표(is_final=1)·최종 경기 결과·컵 대회·이적 다시 수집
3) 지난 시즌 컵·유럽대회 결과·최다 득점자: 위키백과 시즌 목록으로 채움 (backfill_history)
4) ⚠ 알림 1회 (GitHub 이슈) — 다음 실행에서 정상이면 자동으로 닫힘
선수(FPL)는 FPL 이 새 시즌으로 넘어간 뒤부터 fetch_players.py 가 알아서 새 시즌 명단을 받음.
"""
import argparse
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import SyncLog, connect, get_json, load_env, season_label  # noqa: E402

ETL = Path(__file__).resolve().parent


def report(msg: str) -> None:
    print(msg)
    rdir = os.environ.get("REPORT_DIR")
    if rdir:
        with open(Path(rdir) / "3_rollover.txt", "a", encoding="utf-8") as f:
            f.write(msg + "\n")


def run(script: str, *args: str) -> bool:
    print(f"  → {script} {' '.join(args)}")
    r = subprocess.run([sys.executable, str(ETL / script), *args])
    if r.returncode != 0:
        report(f"⚠ 시즌 전환 후속 작업 실패: {script} {' '.join(args)} (다음 실행에서 다시 확인 필요)")
    return r.returncode == 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force-year", type=int)
    args = ap.parse_args()

    con = connect()
    cur = con.execute("SELECT start_year FROM seasons WHERE is_current=1").fetchone()
    if not cur:
        report("✗ seasons 에 현재 시즌(is_current=1)이 없음 — 시즌 전환 판단 불가")
        return 1
    y = cur[0]
    if args.force_year:
        fd_year, fd_start = args.force_year, f"{args.force_year}-08-01 (강제)"
    else:
        d = get_json("https://api.football-data.org/v4/competitions/PL",
                     headers={"X-Auth-Token": load_env()["FOOTBALL_DATA_TOKEN"]})
        fd_start = (d.get("currentSeason") or {}).get("startDate") or ""
        if not fd_start[:4].isdigit():
            report("⚠ football-data 에 PL 현재 시즌 정보가 없음 — 시즌 전환 판단 건너뜀")
            return 0
        fd_year = int(fd_start[:4])

    if fd_year == y:
        print(f"[시즌] 현재 {season_label(y)} 유지 (football-data PL 시즌 시작 {fd_start})")
        return 0
    if fd_year != y + 1:
        report(f"⚠ 시즌 불일치: DB 현재 {season_label(y)} / football-data PL {fd_start} — 자동 전환 안 함, 확인 필요")
        return 0
    if date.today() < date(fd_year, 6, 1) and not args.force_year:
        print(f"[시즌] football-data 는 {fd_year} 시즌이지만 6월 1일 전 → 전환 대기")
        return 0

    old, new = season_label(y), season_label(fd_year)
    print(f"[시즌] 전환: {old} → {new} (football-data PL 시즌 시작 {fd_start})")
    if args.dry_run:
        return 0

    with SyncLog(con, "football-data", "season-rollover") as log:
        con.execute("INSERT OR IGNORE INTO seasons (season, start_year) VALUES (?, ?)", (new, fd_year))
        con.execute("UPDATE seasons SET is_current = CASE WHEN season=? THEN 1 ELSE 0 END", (new,))
        log.rows = 1
        log.message = f"{old} -> {new}"
        con.commit()
    con.close()

    # 지난 시즌 마무리 (is_current 가 바뀐 뒤라 순위표는 is_final=1 로 저장됨)
    ok = all([run("fetch_standings.py", "--season", str(y)),
              run("fetch_fixtures.py", "--season", str(y)),
              run("fetch_cups.py", "--season", str(y)),
              run("fetch_transfers.py", "--season", str(y)),
              run("backfill_history.py")])
    report(f"⚠ 시즌 전환 완료: {old} → {new}. 지난 시즌 최종 순위·결과·컵·이적 정리"
           + ("" if ok else " (일부 실패 — 위 경고 참고)")
           + ". 새 시즌 일정·순위는 이번 실행부터, 선수 명단은 FPL 이 새 시즌으로 넘어간 뒤 자동 반영")
    return 0


if __name__ == "__main__":
    sys.exit(main())
