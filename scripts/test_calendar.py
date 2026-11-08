"""Google 캘린더 연결 테스트: football-data 에서 맨유 다음 경기 1개를 가져와 캘린더에 등록.

사용법:  python scripts/test_calendar.py
- 같은 경기를 다시 실행하면 새로 만들지 않고 기존 일정을 갱신함 (중복 방지)
- 알림은 캘린더 "기본 알림"(1일 전·1시간 전)을 사용
"""
import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from google.oauth2 import service_account
from googleapiclient.discovery import build

ROOT = Path(__file__).resolve().parent.parent
LONDON, SEOUL = ZoneInfo("Europe/London"), ZoneInfo("Asia/Seoul")
WEEKDAY_KO = "월화수목금토일"


def load_env():
    env = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def next_match(token):
    req = urllib.request.Request(
        "https://api.football-data.org/v4/teams/66/matches?status=SCHEDULED,TIMED",
        headers={"X-Auth-Token": token, "User-Agent": "mufc-fan-site/0.1"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        matches = json.loads(r.read().decode("utf-8"))["matches"]
    now = datetime.now(timezone.utc)
    future = sorted(
        (m for m in matches if datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00")) > now),
        key=lambda m: m["utcDate"],
    )
    if not future:
        sys.exit("예정된 경기를 찾지 못했습니다.")
    return future[0]


def fmt(dt, tz):
    d = dt.astimezone(tz)
    return f"{d:%m/%d}({WEEKDAY_KO[d.weekday()]}) {d:%H:%M}"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    env = load_env()
    m = next_match(env["FOOTBALL_DATA_TOKEN"])
    ko = datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00"))
    home, away = m["homeTeam"]["shortName"], m["awayTeam"]["shortName"]
    comp = m["competition"]["name"]

    creds = service_account.Credentials.from_service_account_file(
        str(ROOT / env["GOOGLE_SERVICE_ACCOUNT_JSON"]),
        scopes=["https://www.googleapis.com/auth/calendar"],
    )
    cal = build("calendar", "v3", credentials=creds, cache_discovery=False)
    cal_id = env["GOOGLE_CALENDAR_ID"]

    body = {
        "summary": f"⚽ {home} vs {away}",
        "location": m.get("venue") or "",
        "description": (
            f"{comp}\n"
            f"🇰🇷 한국 시간: {fmt(ko, SEOUL)}\n"
            f"🇬🇧 영국 시간: {fmt(ko, LONDON)}\n"
            f"(자동 등록 · football-data match {m['id']})"
        ),
        "start": {"dateTime": ko.isoformat(), "timeZone": "Asia/Seoul"},
        "end": {"dateTime": (ko + timedelta(hours=2)).isoformat(), "timeZone": "Asia/Seoul"},
        "reminders": {"useDefault": True},
        "extendedProperties": {"private": {"fd_match_id": str(m["id"])}},
    }

    existing = cal.events().list(
        calendarId=cal_id, privateExtendedProperty=f"fd_match_id={m['id']}", maxResults=1
    ).execute().get("items", [])
    if existing:
        ev = cal.events().update(calendarId=cal_id, eventId=existing[0]["id"], body=body).execute()
        action = "갱신"
    else:
        ev = cal.events().insert(calendarId=cal_id, body=body).execute()
        action = "생성"

    print(f"OK - 일정 {action}: {body['summary']}")
    print(f"  {comp} | 한국 {fmt(ko, SEOUL)} | 영국 {fmt(ko, LONDON)}")
    print(f"  링크: {ev.get('htmlLink')}")


if __name__ == "__main__":
    main()
