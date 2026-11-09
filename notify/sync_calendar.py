"""맨유 경기 일정 → Google 캘린더 동기화 (STEP 3).

사용법:  python notify/sync_calendar.py [--dry-run]

- 이번 시즌 맨유 경기 전체를 캘린더 일정으로 유지 (일정마다 fd_match_id 또는 ext_match_id(위키백과 컵 경기) 로 식별 → 중복 없음)
- 바뀐 일정만 수정: 킥오프 시간 변경·연기·결과(스코어) 반영. 취소되거나 DB 에서 사라진 경기는 삭제
- 킥오프 시간 미정(kickoff_confirmed=0)이면 '하루 종일' 일정으로 → 엉뚱한 시간에 알람 울리지 않게
- 알림: 캘린더 '기본 알림' 사용 (구글 캘린더 설정에서 1일 전·1시간 전으로 지정)

자격 증명 (없으면 경고만 출력하고 건너뜀)
  GOOGLE_SERVICE_ACCOUNT_KEY   서비스 계정 JSON '내용' (GitHub Actions 시크릿)
  GOOGLE_SERVICE_ACCOUNT_JSON  서비스 계정 JSON '파일 경로' (로컬 .env)
  GOOGLE_CALENDAR_ID           공유한 캘린더 ID
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "etl"))
from common import ROOT, connect, load_env  # noqa: E402

SEOUL, LONDON = ZoneInfo("Asia/Seoul"), ZoneInfo("Europe/London")
WEEKDAY_KO = "월화수목금토일"
MU = "Man United"
SITE = "https://rolrend25-hub.github.io/manutd/"
SRC = "mufc-site"
MATCH_HOURS = 2


def fmt(dt: datetime, tz) -> str:
    d = dt.astimezone(tz)
    return f"{d:%m/%d}({WEEKDAY_KO[d.weekday()]}) {d:%H:%M}"


def calendar_service(env: dict):
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    scopes = ["https://www.googleapis.com/auth/calendar"]
    if env.get("GOOGLE_SERVICE_ACCOUNT_KEY"):
        creds = service_account.Credentials.from_service_account_info(
            json.loads(env["GOOGLE_SERVICE_ACCOUNT_KEY"]), scopes=scopes)
    elif env.get("GOOGLE_SERVICE_ACCOUNT_JSON") and (ROOT / env["GOOGLE_SERVICE_ACCOUNT_JSON"]).exists():
        creds = service_account.Credentials.from_service_account_file(
            str(ROOT / env["GOOGLE_SERVICE_ACCOUNT_JSON"]), scopes=scopes)
    else:
        return None
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def match_key(m) -> tuple[str, str]:
    """캘린더 일정 식별 속성 (이름, 값). football-data 경기는 기존 fd_match_id 유지."""
    if m["match_fd_id"] is not None:
        return "fd_match_id", str(m["match_fd_id"])
    return "ext_match_id", m["match_ext_id"]


def build_event(m) -> dict:
    ko = datetime.fromisoformat(m["kickoff_utc"].replace("Z", "+00:00"))
    home, away = (MU, m["opponent_name"]) if m["home_away"] != "A" else (m["opponent_name"], MU)
    comp = m["comp_name_ko"] or m["comp_name"] or m["competition_code"]
    status = m["status"]

    if status == "FINISHED" and m["mu_score"] is not None:
        hs, as_ = (m["mu_score"], m["opp_score"]) if m["home_away"] != "A" else (m["opp_score"], m["mu_score"])
        mark = {"W": "✅", "D": "➖", "L": "❌"}.get(m["result"], "⚽")
        summary = f"{mark} {home} {hs}-{as_} {away}"
    elif status == "POSTPONED":
        summary = f"⚠ (연기) {home} vs {away}"
    else:
        summary = f"⚽ {home} vs {away}"

    lines = [comp + (f" · {m['matchday']}라운드" if m["matchday"] and m["competition_code"] == "PL" else "")]
    if m["kickoff_confirmed"]:
        lines += [f"🇰🇷 한국 시간: {fmt(ko, SEOUL)}", f"🇬🇧 영국 시간: {fmt(ko, LONDON)}"]
    else:
        lines += ["⏳ 킥오프 시간 미정 (확정되면 자동으로 시간 일정으로 바뀝니다)"]
    if status == "POSTPONED":
        lines += ["⚠ 경기가 연기되었습니다. 새 일정이 나오면 자동 수정됩니다."]
    lines += [f"{'홈' if m['home_away'] == 'H' else '원정'} 경기" + (f" · {m['venue']}" if m["venue"] else ""),
              "", f"경기 페이지: {SITE}#match/{m['id']}", "(자동 등록 · 맨유 팬 사이트)"]

    if m["kickoff_confirmed"]:
        start = {"dateTime": ko.isoformat().replace("+00:00", "Z"), "timeZone": "Asia/Seoul"}
        end = {"dateTime": (ko + timedelta(hours=MATCH_HOURS)).isoformat().replace("+00:00", "Z"),
               "timeZone": "Asia/Seoul"}
    else:
        d = ko.astimezone(SEOUL).date()
        start, end = {"date": d.isoformat()}, {"date": (d + timedelta(days=1)).isoformat()}

    return {
        "summary": summary,
        "location": m["venue"] or "",
        "description": "\n".join(lines),
        "start": start,
        "end": end,
        "reminders": {"useDefault": True},
        "extendedProperties": {"private": {**dict([match_key(m)]), "src": SRC}},
    }


def _norm_time(t: dict) -> str:
    if "date" in t:
        return "date:" + t["date"]
    return "dt:" + datetime.fromisoformat(t["dateTime"].replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()


def differs(ev: dict, body: dict) -> list[str]:
    diff = []
    for k in ("summary", "description", "location"):
        if (ev.get(k) or "") != (body.get(k) or ""):
            diff.append(k)
    if _norm_time(ev["start"]) != _norm_time(body["start"]) or _norm_time(ev["end"]) != _norm_time(body["end"]):
        diff.append("time")
    return diff


def list_our_events(cal, cal_id: str) -> dict[str, list[dict]]:
    """캘린더에 있는 우리 일정 전체 → {'fd_match_id=123' 또는 'ext_match_id=wiki:..': [event, ...]}"""
    out, token = {}, None
    while True:
        res = cal.events().list(calendarId=cal_id, maxResults=2500, pageToken=token, showDeleted=False,
                                singleEvents=True).execute()
        for ev in res.get("items", []):
            props = ev.get("extendedProperties", {}).get("private", {})
            fid = next((f"{k}={props[k]}" for k in ("fd_match_id", "ext_match_id") if props.get(k)), None)
            if fid:
                out.setdefault(fid, []).append(ev)
        token = res.get("nextPageToken")
        if not token:
            return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    dry = "--dry-run" in sys.argv
    env = load_env()
    cal = calendar_service(env)
    cal_id = env.get("GOOGLE_CALENDAR_ID")
    if cal is None or not cal_id:
        print("⚠ 구글 캘린더 자격 증명이 없어 건너뜀 (GOOGLE_SERVICE_ACCOUNT_KEY/JSON, GOOGLE_CALENDAR_ID)")
        return 0

    con = connect()  # 읽기만 함 (Actions 에서 커밋 이후 단계로 실행 → 저장소 변경 없음)
    rows = con.execute(
        """SELECT m.*, c.name AS comp_name, c.name_ko AS comp_name_ko
           FROM matches m JOIN seasons s ON s.season = m.season AND s.is_current = 1
           LEFT JOIN competitions c ON c.code = m.competition_code
           WHERE m.match_fd_id IS NOT NULL OR m.match_ext_id IS NOT NULL ORDER BY m.kickoff_utc""").fetchall()

    existing = list_our_events(cal, cal_id)
    created = updated = deleted = same = 0
    wanted = set()
    for m in rows:
        fid = "=".join(match_key(m))
        if m["status"] == "CANCELLED":
            continue  # 아래에서 기존 일정 삭제
        wanted.add(fid)
        body = build_event(m)
        evs = existing.get(fid, [])
        if not evs:
            print(f"  + 생성  {body['summary']}")
            if not dry:
                cal.events().insert(calendarId=cal_id, body=body).execute()
            created += 1
            continue
        ev, dups = evs[0], evs[1:]
        for d in dups:  # 혹시 생긴 중복 정리
            print(f"  - 중복 삭제 {d.get('summary')}")
            if not dry:
                cal.events().delete(calendarId=cal_id, eventId=d["id"]).execute()
            deleted += 1
        diff = differs(ev, body)
        if diff:
            note = ""
            if "time" in diff:
                old = ev["start"].get("dateTime") or ev["start"].get("date")
                note = f"  (시간: {old} → {body['start'].get('dateTime') or body['start'].get('date')})"
            print(f"  ~ 수정  {body['summary']}  [{', '.join(diff)}]{note}")
            if not dry:
                cal.events().update(calendarId=cal_id, eventId=ev["id"], body=body).execute()
            updated += 1
        else:
            same += 1

    # 취소된 경기 일정 삭제. 이번 시즌 DB 에 없는 일정(지난 시즌 등)은 손대지 않음
    cancelled = {"=".join(match_key(m)) for m in rows} - wanted
    for fid in cancelled:
        for ev in existing.get(fid, []):
            print(f"  - 삭제  {ev.get('summary')} (취소된 경기)")
            if not dry:
                cal.events().delete(calendarId=cal_id, eventId=ev["id"]).execute()
            deleted += 1

    print(f"OK - 캘린더 {'점검(dry-run)' if dry else '동기화'}: 생성 {created} · 수정 {updated} · 삭제 {deleted} · 변경 없음 {same}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
