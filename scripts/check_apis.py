"""API 키 점검: football-data.org 토큰 + API-Football 무료 플랜의 현재 시즌 접근 여부.

사용법:  py scripts/check_apis.py
키는 프로젝트 루트의 .env 에서 읽음 (화면에 키 값은 출력하지 않음).
API-Football 요청은 4회만 사용 (무료 100회/일).
"""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEASON = 2026          # API-Football 은 시즌 시작 연도 사용 (2026-27 → 2026)
MUFC_APIF = 33         # API-Football 맨유 team id
MUFC_FD = 66           # football-data.org 맨유 team id


def load_env():
    env = {}
    path = ROOT / ".env"
    if not path.exists():
        sys.exit(".env 파일이 없습니다. .env.example 을 복사해 .env 로 저장 후 키를 입력하세요.")
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def get(url, headers):
    req = urllib.request.Request(url, headers={**headers, "User-Agent": "mufc-fan-site/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode("utf-8"))
        except Exception:
            body = {}
        return e.code, body


def check_football_data(token):
    print("\n[football-data.org]")
    if not token:
        print("  FOOTBALL_DATA_TOKEN 비어 있음 → 건너뜀")
        return
    h = {"X-Auth-Token": token}
    code, body = get(f"https://api.football-data.org/v4/teams/{MUFC_FD}/matches?status=SCHEDULED&limit=3", h)
    if code != 200:
        print(f"  실패 HTTP {code}: {body.get('message', body)}")
        return
    print("  OK - 토큰 정상")
    for m in body.get("matches", [])[:3]:
        print(f"  다음 경기: {m['utcDate']}  {m['homeTeam']['shortName']} vs {m['awayTeam']['shortName']}  ({m['competition']['name']})")


def check_api_football(key):
    print("\n[API-Football]")
    if not key:
        print("  API_FOOTBALL_KEY 비어 있음 → 건너뜀")
        return
    h = {"x-apisports-key": key}
    base = "https://v3.football.api-sports.io"

    code, body = get(f"{base}/status", h)
    resp = body.get("response") or {}
    if code != 200 or body.get("errors"):
        print(f"  키 오류 HTTP {code}: {body.get('errors')}")
        return
    sub = resp.get("subscription", {})
    req = resp.get("requests", {})
    print(f"  OK - 플랜: {sub.get('plan')}  오늘 사용: {req.get('current')}/{req.get('limit_day')}")

    tests = {
        "일정/결과 (fixtures)": f"{base}/fixtures?team={MUFC_APIF}&season={SEASON}",
        "선수 시즌 스탯 (players)": f"{base}/players?team={MUFC_APIF}&season={SEASON}",
        "PL 순위 (standings)": f"{base}/standings?league=39&season={SEASON}",
    }
    ok_all = True
    for name, url in tests.items():
        code, body = get(url, h)
        errs = body.get("errors")
        if errs:
            ok_all = False
            print(f"  ✗ {name}: {errs}")
        else:
            print(f"  ✓ {name}: {body.get('results', 0)}건")
    print()
    if ok_all:
        print(f"  ⇒ 무료 플랜으로 {SEASON} 시즌 접근 가능 → API-Football 사용")
    else:
        print(f"  ⇒ 무료 플랜으로 {SEASON} 시즌 차단 → football-data + FPL 로 구성 (계획대로)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    env = load_env()
    check_football_data(env.get("FOOTBALL_DATA_TOKEN"))
    check_api_football(env.get("API_FOOTBALL_KEY"))
