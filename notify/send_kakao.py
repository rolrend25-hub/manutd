"""카카오톡 경기 알림 발송 (STEP 3) — GitHub Actions 30분마다 실행.

보내는 것
  REMIND_D1       킥오프 24시간 전 (~ 킥오프 3시간 전까지 늦게라도)
  REMIND_H1       킥오프 1시간 전 (실행 주기가 30분이라 90분 전부터 보냄)
  KICKOFF_CHANGE  킥오프 시간 변경·확정·연기 (etl/fetch_fixtures.py 가 notifications 에 대기열로 넣음)

중복 방지: 보낸 기록을 notifications 테이블(match_id, kind, channel 고유)에 남기고 DB 를 커밋.
킥오프 시간이 미정(kickoff_confirmed=0)인 경기는 리마인드하지 않음.

사용법:  python notify/send_kakao.py [--dry-run]
GitHub Actions 에서는 DB 를 바꿨으면 GITHUB_OUTPUT 에 changed=true 기록 (→ 검증·커밋 단계 실행).
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "etl"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import connect, load_env, utc_now  # noqa: E402
import kakao  # noqa: E402

SEOUL, LONDON = ZoneInfo("Asia/Seoul"), ZoneInfo("Europe/London")
WEEKDAY_KO = "월화수목금토일"
MU = "Man United"
CHANNEL = "kakao_memo"
UPCOMING = ("SCHEDULED", "TIMED")

# (kind, 킥오프 기준 보내기 시작 시점, 이 시점 이후로는 안 보냄)
WINDOWS = [
    ("REMIND_D1", timedelta(hours=24), timedelta(hours=3)),
    ("REMIND_H1", timedelta(minutes=90), timedelta(0)),
]


def parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def fmt(dt: datetime, tz) -> str:
    d = dt.astimezone(tz)
    return f"{d:%m/%d}({WEEKDAY_KO[d.weekday()]}) {d:%H:%M}"


def teams(m) -> str:
    return f"{MU} vs {m['opponent_name']}" if m["home_away"] != "A" else f"{m['opponent_name']} vs {MU}"


def comp_line(m) -> str:
    comp = m["comp_name"] or m["competition_code"]
    rnd = f" {m['matchday']}R" if m["matchday"] and m["competition_code"] == "PL" else ""
    return f"{comp}{rnd} · {'홈' if m['home_away'] == 'H' else '원정'}"


def times(ko: datetime) -> str:
    return f"🇰🇷 {fmt(ko, SEOUL)}\n🇬🇧 {fmt(ko, LONDON)}"


def reminder_text(kind: str, m) -> str:
    ko = parse(m["kickoff_utc"])
    head = "⚽ 내일 맨유 경기" if kind == "REMIND_D1" else "⏰ 1시간 후 킥오프!"
    if kind == "REMIND_D1" and ko.astimezone(SEOUL).date() == datetime.now(SEOUL).date():
        head = "⚽ 오늘 맨유 경기"
    return f"{head}\n{teams(m)}\n{comp_line(m)}\n{times(ko)}"


def change_text(m, old_ref: str | None) -> str:
    old_ko, old_status, old_conf = (old_ref or "||").split("|")[:3]
    ko = parse(m["kickoff_utc"])
    if m["status"] == "POSTPONED":
        return f"⚠ 경기 연기\n{teams(m)}\n{comp_line(m)}\n새 일정이 나오면 다시 알려 드립니다."
    if old_status == "POSTPONED":
        head = "📅 연기 경기 새 일정"
    elif old_conf == "0":
        head = "📅 킥오프 시간 확정"
    else:
        head = "🔔 경기 시간 변경"
    lines = [head, teams(m), comp_line(m)]
    if old_ko and old_conf != "0" and old_status != "POSTPONED":
        lines.append(f"이전: {fmt(parse(old_ko), SEOUL)} (한국)")
        lines.append(f"변경: {fmt(ko, SEOUL)} (한국)")
        lines.append(f"🇬🇧 {fmt(ko, LONDON)}")
    else:
        lines.append(times(ko))
    return "\n".join(lines)


def due_messages(con, now: datetime) -> list[tuple]:
    """[(match_row, kind, text, old_ref)] — 지금 보내야 할 것."""
    rows = con.execute(
        """SELECT m.*, c.name AS comp_name FROM matches m
           LEFT JOIN competitions c ON c.code = m.competition_code
           WHERE m.kickoff_utc BETWEEN ? AND ?""",
        ((now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
         (now + timedelta(days=400)).strftime("%Y-%m-%dT%H:%M:%SZ"))).fetchall()
    sent = {(r["match_id"], r["kind"]): r for r in con.execute(
        "SELECT * FROM notifications WHERE channel=?", (CHANNEL,))}
    out = []
    for m in rows:
        ko = parse(m["kickoff_utc"])
        # 1) 일정 변경 안내 (대기열) — 이미 지난 경기면 보내지 않고 건너뜀
        ch = sent.get((m["id"], "KICKOFF_CHANGE"))
        if ch is not None and ch["status"] == "pending":
            if m["status"] == "POSTPONED" or ko > now:
                out.append((m, "KICKOFF_CHANGE", change_text(m, ch["external_ref"]), ch["external_ref"]))
            else:
                out.append((m, "KICKOFF_CHANGE", None, ch["external_ref"]))  # skipped
        # 2) 리마인드
        if m["status"] not in UPCOMING or not m["kickoff_confirmed"]:
            continue
        for kind, start, stop in WINDOWS:
            if (m["id"], kind) in sent and sent[(m["id"], kind)]["status"] in ("sent", "skipped"):
                continue
            if ko - start <= now < ko - stop:
                out.append((m, kind, reminder_text(kind, m), None))
    return out


def record(con, match_id: int, kind: str, status: str, ref: str | None, error: str | None = None) -> None:
    con.execute(
        """INSERT INTO notifications (match_id, kind, channel, scheduled_utc, sent_utc, status, external_ref, error)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(match_id, kind, channel) DO UPDATE SET
             sent_utc=excluded.sent_utc, status=excluded.status, error=excluded.error""",
        (match_id, kind, CHANNEL, utc_now(), utc_now() if status == "sent" else None, status, ref, error))
    con.commit()


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    dry = "--dry-run" in sys.argv
    env = load_env()
    con = connect()
    now = datetime.now(timezone.utc)
    todo = due_messages(con, now)
    changed = False
    try:
        if not todo:
            print("카카오 알림: 보낼 것 없음")
            return 0
        if not env.get("KAKAO_REFRESH_TOKEN") or not env.get("KAKAO_REST_API_KEY"):
            print(f"⚠ 카카오 알림 {len(todo)}건 대기 중이지만 KAKAO_REFRESH_TOKEN/REST_API_KEY 가 없어 보내지 못함")
            return 0
        token = None if dry else kakao.access_token(env)
        for m, kind, text, ref in todo:
            link = f"{kakao.SITE}#match/{m['id']}"
            if text is None:
                print(f"  - 건너뜀 {kind} {teams(m)} (이미 지난 경기)")
                if not dry:
                    record(con, m["id"], kind, "skipped", ref)
                    changed = True
                continue
            print(f"  > {'(dry-run) ' if dry else ''}{kind} {teams(m)}\n    " + text.replace("\n", "\n    "))
            if dry:
                continue
            kakao.send_memo(token, text, link=link)
            record(con, m["id"], kind, "sent", ref)
            changed = True
        print(f"OK - 카카오 알림 {'점검' if dry else '발송'} {len(todo)}건")
        return 0
    finally:
        out = os.environ.get("GITHUB_OUTPUT")
        if out:
            with open(out, "a", encoding="utf-8") as f:
                f.write(f"changed={'true' if changed else 'false'}\n")


if __name__ == "__main__":
    sys.exit(main())
