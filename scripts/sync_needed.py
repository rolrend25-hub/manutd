"""GitHub Actions 게이트: 지금 동기화가 필요한지 판단해 GITHUB_OUTPUT 에 run=true/false 기록.

- 매일 정기 실행·수동 실행·push 는 항상 동기화
- 30분 주기 실행은 '킥오프 후 2시간 지났는데 DB 상 아직 종료 안 된 경기'(최근 3일)가 있을 때만
"""
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "manutd.db"
FREQUENT_CRON = "*/30 * * * *"
DONE = ("FINISHED", "POSTPONED", "CANCELLED", "AWARDED", "SUSPENDED")


def decide() -> tuple[bool, str]:
    event = os.environ.get("GITHUB_EVENT_NAME", "manual")
    schedule = os.environ.get("EVENT_SCHEDULE", "")
    if event != "schedule" or schedule != FREQUENT_CRON:
        return True, f"event={event} schedule={schedule or '-'} → 항상 동기화"

    now = datetime.now(timezone.utc)
    lo = (now - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    hi = (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    con = sqlite3.connect(DB_PATH)
    rows = con.execute(
        f"SELECT kickoff_utc, competition_code, opponent_name, status FROM matches "
        f"WHERE kickoff_utc BETWEEN ? AND ? AND status NOT IN ({','.join('?' * len(DONE))})",
        (lo, hi, *DONE),
    ).fetchall()
    # 결과는 들어왔지만 FPL 경기 상세(보너스 등)가 아직 확정 안 된 PL 경기
    rows += con.execute(
        "SELECT kickoff_utc, competition_code, opponent_name, 'details pending' FROM matches "
        "WHERE kickoff_utc BETWEEN ? AND ? AND competition_code='PL' AND status='FINISHED' "
        "AND COALESCE(details_synced, 0) = 0", (lo, hi)).fetchall()
    con.close()
    if rows:
        return True, "결과 대기 경기: " + ", ".join(f"{k} {c} vs {o} [{s}]" for k, c, o, s in rows)
    return False, "결과 대기 경기 없음 → 건너뜀"


def main() -> None:
    run, reason = decide()
    print(reason)
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"run={'true' if run else 'false'}\n")
    else:
        sys.exit(0 if run else 1)


if __name__ == "__main__":
    main()
