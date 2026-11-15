"""API-Football 무료 플랜으로 과거 시즌(2022-23~2024-25) 경기 상세 백필.

사용법:
    python etl/backfill_apif.py                 # 하루 한도 안에서 이어서 수집 (기본 최대 90회 호출)
    python etl/backfill_apif.py --max-calls 20
    python etl/backfill_apif.py --status        # 진행 상황만 출력 (API 호출 없음)

무료 플랜 제약 (2026-11-15 확인)
* 2022~2024 시즌만 조회 가능 (2025 이후 차단) → 2025-26 이후는 football-data·FPL·위키백과로 수집 중
* 하루 100회, `ids`(여러 경기 묶음) 파라미터 불가 → 경기당 1회 `/fixtures?id=` (이벤트·라인업·팀 스탯·선수 스탯 포함)
* 3시즌 공식 경기 약 190경기 → 2~3일에 나눠 수집. 끝나면 API 호출 없이 바로 종료

저장
* matches          시즌 경기 목록 (친선전 제외, match_af_id 로 식별, details_synced=1 이면 상세 완료)
* match_events     골(분·PK)·도움·자책골·경고·퇴장 — 승부차기 킥은 제외
* match_lineups    양 팀 선발 + 실제 교체 출전 (포메이션 포함, 미출전 벤치 제외)
* match_team_stats 점유율·슈팅·코너·파울·오프사이드·패스·선방
* player_match_stats 맨유 선수 출전시간·골·도움·슈팅·키패스·태클·평점·카드
* players          과거 선수는 player_af_id 로 추가 (현재 선수는 이름으로 기존 행에 연결)
검증: 골 이벤트 수 = 스코어(승부차기 제외). 다르면 경고만 출력.
"""
import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import USER_AGENT, SyncLog, connect, load_env, name_tokens, season_label, utc_now  # noqa: E402

BASE = "https://v3.football.api-sports.io"
MUFC_AF = 33
SEASONS = (2022, 2023, 2024)
LEAGUE_CODE = {39: "PL", 45: "FAC", 48: "ELC", 2: "UCL", 3: "UEL", 848: "UECL", 528: "CS", 531: "USC"}
DONE_STATUS = {"FT", "AET", "PEN"}
POS = {"G": "GK", "D": "DF", "M": "MF", "F": "FW"}
RESERVE = 3  # 하루 한도 중 남겨 둘 호출 수 (수동 점검용)


class Quota(Exception):
    pass


class Api:
    def __init__(self, key: str, max_calls: int):
        self.key, self.max_calls, self.calls, self.remaining = key, max_calls, 0, None

    def get(self, path: str) -> dict:
        if self.calls >= self.max_calls:
            raise Quota(f"이번 실행 호출 상한 {self.max_calls}회 도달")
        if self.remaining is not None and self.remaining <= RESERVE:
            raise Quota(f"오늘 남은 호출 {self.remaining}회 → 내일 이어서")
        req = urllib.request.Request(BASE + path, headers={"x-apisports-key": self.key, "User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                rem = r.headers.get("x-ratelimit-requests-remaining")
                body = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"HTTP {e.code} {path}") from None
        self.calls += 1
        if rem is not None and rem.isdigit():
            self.remaining = int(rem)
        errs = body.get("errors")
        if errs:
            msg = json.dumps(errs, ensure_ascii=False)
            if "limit" in msg.lower() or "requests" in msg.lower():
                raise Quota(f"API 한도: {msg[:150]}")
            raise RuntimeError(f"API 오류 {path}: {msg[:200]}")
        time.sleep(6.5)  # 무료 플랜 분당 10회 제한
        return body


# ---------- 팀·선수 연결 ----------
TEAM_ALIAS = {"wolves": "wolverhampton", "utd": "united", "spurs": "tottenham", "nott'm": "nottingham",
              "munich": "munchen", "copenhagen": "kbenhavn", "bodo": "bod"}  # ø 는 악센트 제거 시 빠짐
TEAM_DROP = {"fc", "afc", "cf", "sc", "fk", "sk", "kv", "and", "hove", "albion", "hotspur", "wanderers", "town", "forest"}


def team_key(name: str) -> set[str]:
    toks = [TEAM_ALIAS.get(t, t) for t in name_tokens(name.replace("&", " "))]
    core = {t for t in toks if t not in TEAM_DROP}
    return core or set(toks)


def find_team(con, af_id: int, name: str, logo: str | None) -> int:
    r = con.execute("SELECT id FROM teams WHERE team_af_id=?", (af_id,)).fetchone()
    if r:
        return r[0]
    k = team_key(name)
    cands = [t["id"] for t in con.execute("SELECT id, name, short_name FROM teams WHERE team_af_id IS NULL")
             if k and any(k <= team_key(n) or team_key(n) <= k for n in (t["name"], t["short_name"] or "") if n)]
    if len(cands) == 1:
        con.execute("UPDATE teams SET team_af_id=? WHERE id=?", (af_id, cands[0]))
        return cands[0]
    cur = con.execute("INSERT INTO teams (name, short_name, crest_url, team_af_id) VALUES (?, ?, ?, ?)",
                      (name, name, logo, af_id))
    print(f"    팀 추가: {name}")
    return cur.lastrowid


def af_name_match(af: str, full: str) -> bool:
    """'H. Maguire' ≈ 'Harry Maguire', 'Bruno Fernandes' ≈ 'Bruno Miguel Borges Fernandes'."""
    a, f = name_tokens(af), name_tokens(full)
    if not a or not f:
        return False
    if re.match(r"^[A-Za-z]\. ", af.strip()):  # 이니셜 + 성
        return a[-1] == f[-1] and f[0].startswith(a[0])
    if len(a) == 1:
        return a == f or a[0] == f[-1] and len(f) == 1
    return set(a) <= set(f)


def best_names(f: dict) -> dict[int, str]:
    """선수 id → 가장 온전한 이름 ('S. McTominay' 보다 'Scott McTominay')."""
    seen: dict[int, list[str]] = {}
    for team in f.get("players", []):
        for p in team["players"]:
            seen.setdefault(p["player"]["id"], []).append(p["player"]["name"])
    for e in f.get("events", []):
        for k in ("player", "assist"):
            x = e.get(k) or {}
            if x.get("id") and x.get("name"):
                seen.setdefault(x["id"], []).append(x["name"])
    return {i: max(ns, key=lambda n: (not re.match(r"^[A-Za-z]\. ", n), len(n))) for i, ns in seen.items()}


def find_player(con, af_id: int, name: str, pos: str | None, photo_cache: dict) -> int:
    r = con.execute("SELECT id FROM players WHERE player_af_id=?", (af_id,)).fetchone()
    if r:
        return r[0]
    cands = [p["id"] for p in con.execute("SELECT id, full_name, known_as FROM players WHERE player_af_id IS NULL")
             if af_name_match(name, p["full_name"]) or (p["known_as"] and af_name_match(name, p["known_as"]))]
    if len(cands) == 1:
        con.execute("UPDATE players SET player_af_id=? WHERE id=?", (af_id, cands[0]))
        return cands[0]
    full = photo_cache.get(("name", af_id)) or name
    cur = con.execute("INSERT INTO players (full_name, known_as, position, photo_url, player_af_id) VALUES (?,?,?,?,?)",
                      (full, full, pos, photo_cache.get(af_id), af_id))
    return cur.lastrowid


# ---------- 경기 목록 ----------
def stage_of(round_: str) -> tuple[str, int | None]:
    m = re.match(r"Regular Season - (\d+)", round_ or "")
    if m:
        return "REGULAR_SEASON", int(m.group(1))
    m = re.match(r"(League Stage|Group Stage|Group [A-H]) - (\d+)", round_ or "")
    if m:
        return "GROUP_STAGE" if "Group" in m.group(1) else "LEAGUE_STAGE", int(m.group(2))
    return re.sub(r"[^A-Z0-9]+", "_", (round_ or "").upper()).strip("_") or None, None


def save_fixture_list(con, season: str, fixtures: list[dict]) -> int:
    n = 0
    for f in fixtures:
        code = LEAGUE_CODE.get(f["league"]["id"])
        if not code or f["fixture"]["status"]["short"] not in DONE_STATUS:
            continue
        home = f["teams"]["home"]["id"] == MUFC_AF
        opp = f["teams"]["away" if home else "home"]
        g, sc = f["goals"], f["score"]
        mu, op = (g["home"], g["away"]) if home else (g["away"], g["home"])
        ht = sc["halftime"]
        pen = sc["penalty"]
        mu_ht, op_ht = (ht["home"], ht["away"]) if home else (ht["away"], ht["home"])
        mu_p, op_p = ((pen["home"], pen["away"]) if home else (pen["away"], pen["home"])) if pen["home"] is not None else (None, None)
        res = "W" if mu > op else "L" if mu < op else ("W" if (mu_p or 0) > (op_p or 0) else "L") if mu_p is not None else "D"
        rnd = f["league"]["round"] or ""
        neutral = (code in ("CS", "USC") or (rnd == "Final" and code in ("FAC", "ELC", "UEL", "UCL"))
                   or (rnd == "Semi-finals" and code == "FAC"))  # FA컵 준결승·결승은 웸블리
        stage, md = stage_of(f["league"]["round"])
        row = dict(season=season, competition_code=code, stage=stage, matchday=md,
                   kickoff_utc=f["fixture"]["date"][:19] + "Z", kickoff_confirmed=1,
                   home_away="N" if neutral else "H" if home else "A",
                   opponent_id=find_team(con, opp["id"], opp["name"], opp.get("logo")), opponent_name=opp["name"],
                   venue=(f["fixture"]["venue"] or {}).get("name"), status="FINISHED",
                   mu_score=mu, opp_score=op, mu_score_ht=mu_ht, opp_score_ht=op_ht, mu_pens=mu_p, opp_pens=op_p,
                   result=res, referee=f["fixture"].get("referee"), match_af_id=f["fixture"]["id"])
        cols = list(row)
        con.execute(f"""INSERT INTO matches ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})
                        ON CONFLICT(match_af_id) DO UPDATE SET {', '.join(f'{c}=excluded.{c}' for c in cols if c != 'match_af_id')},
                        updated_at=datetime('now')""", [row[c] for c in cols])
        n += 1
    return n


# ---------- 경기 상세 ----------
def num(v):
    if v is None:
        return None
    if isinstance(v, str):
        v = v.rstrip("%")
        try:
            return float(v) if "." in v else int(v)
        except ValueError:
            return None
    return v


def save_detail(con, m, f: dict) -> str:
    mid = m["id"]
    side_of = lambda team_id: "MU" if team_id == MUFC_AF else "OPP"  # noqa: E731
    for t in ("match_events", "match_lineups", "match_team_stats", "player_match_stats"):
        con.execute(f"DELETE FROM {t} WHERE match_id=?", (mid,))

    # 선수 스탯 (출전 여부·포지션 판단에도 사용)
    pstats, photos = {}, {}
    for team in f.get("players", []):
        for p in team["players"]:
            st = p["statistics"][0] if p["statistics"] else {}
            pstats[p["player"]["id"]] = st
            photos[p["player"]["id"]] = p["player"].get("photo")
    photos.update({("name", i): n for i, n in best_names(f).items()})

    # 라인업 (선발 + 실제 교체 출전)
    mu_pid = {}
    for lu in f.get("lineups", []):
        side = side_of(lu["team"]["id"])
        for starter, key in ((1, "startXI"), (0, "substitutes")):
            for x in lu.get(key) or []:
                p = x["player"]
                mins = ((pstats.get(p["id"]) or {}).get("games") or {}).get("minutes")
                if not starter and not mins:
                    continue
                pid = None
                if side == "MU" and p.get("id"):
                    pid = find_player(con, p["id"], p["name"], POS.get(p.get("pos")), photos)
                    mu_pid[p["id"]] = pid
                con.execute("""INSERT OR REPLACE INTO match_lineups (match_id, team_side, player_name, player_id,
                               shirt_number, position, is_starter, formation) VALUES (?,?,?,?,?,?,?,?)""",
                            (mid, side, p["name"], pid, p.get("number"), POS.get(p.get("pos")), starter, lu.get("formation")))

    # 이벤트
    goals = {"MU": 0, "OPP": 0}
    for e in f.get("events", []):
        if (e.get("comments") or "") == "Penalty Shootout":
            continue
        side = side_of(e["team"]["id"])
        mi, ex = e["time"].get("elapsed"), e["time"].get("extra")
        typ, det = e.get("type"), e.get("detail") or ""
        name = (e.get("player") or {}).get("name")
        pid = mu_pid.get((e.get("player") or {}).get("id")) if side == "MU" else None
        if not name:
            continue
        if typ == "Goal" and det in ("Normal Goal", "Penalty"):
            assist = (e.get("assist") or {}).get("name")
            con.execute("""INSERT INTO match_events (match_id, minute, extra_minute, team_side, event_type, player_name,
                           player_id, assist_name, detail) VALUES (?,?,?,?, 'goal', ?,?,?,?)""",
                        (mid, mi, ex, side, name, pid, assist, "pen" if det == "Penalty" else None))
            goals[side] += 1
            if assist:
                apid = mu_pid.get(e["assist"].get("id")) if side == "MU" else None
                con.execute("""INSERT INTO match_events (match_id, minute, extra_minute, team_side, event_type,
                               player_name, player_id) VALUES (?,?,?,?, 'assist', ?, ?)""", (mid, mi, ex, side, assist, apid))
        elif typ == "Goal" and det == "Own Goal":
            # API-Football 은 자책골을 '득점 인정 팀' 쪽 이벤트로 기록 → 자책한 선수는 상대 팀 소속
            own_side = "OPP" if side == "MU" else "MU"
            con.execute("""INSERT INTO match_events (match_id, minute, extra_minute, team_side, event_type, player_name)
                           VALUES (?,?,?,?, 'own_goal', ?)""", (mid, mi, ex, own_side, name))
            goals[side] += 1
        elif typ == "Card":
            kind = "yellow" if det == "Yellow Card" else "red" if det in ("Red Card", "Second Yellow card") else None
            if kind:
                con.execute("""INSERT INTO match_events (match_id, minute, extra_minute, team_side, event_type,
                               player_name, player_id, detail) VALUES (?,?,?,?,?,?,?,?)""",
                            (mid, mi, ex, side, kind, name, pid, "2nd yellow" if det.startswith("Second") else None))

    # 팀 스탯
    for t in f.get("statistics", []):
        s = {x["type"]: num(x["value"]) for x in t["statistics"]}
        con.execute("""INSERT INTO match_team_stats (match_id, team_side, possession_pct, shots, shots_on_target, xg,
                       corners, fouls, offsides, passes, pass_accuracy_pct, saves) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (mid, side_of(t["team"]["id"]), s.get("Ball Possession"), s.get("Total Shots"), s.get("Shots on Goal"),
                     s.get("expected_goals"), s.get("Corner Kicks"), s.get("Fouls"), s.get("Offsides"),
                     s.get("Total passes"), s.get("Passes %"), s.get("Goalkeeper Saves")))

    # 맨유 선수 스탯
    for team in f.get("players", []):
        if team["team"]["id"] != MUFC_AF:
            continue
        for p in team["players"]:
            st = p["statistics"][0] if p["statistics"] else {}
            g = st.get("games") or {}
            if not g.get("minutes"):
                continue
            pid = mu_pid.get(p["player"]["id"]) or find_player(con, p["player"]["id"], p["player"]["name"],
                                                               POS.get(g.get("position")), photos)
            cards = st.get("cards") or {}
            con.execute("""INSERT OR REPLACE INTO player_match_stats (match_id, player_id, minutes, goals, assists, shots,
                           key_passes, tackles, rating, yellow, red) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                        (mid, pid, g["minutes"], (st.get("goals") or {}).get("total") or 0,
                         (st.get("goals") or {}).get("assists") or 0, (st.get("shots") or {}).get("total"),
                         (st.get("passes") or {}).get("key"), (st.get("tackles") or {}).get("total"),
                         num(g.get("rating")), cards.get("yellow") or 0, cards.get("red") or 0))

    con.execute("UPDATE matches SET details_synced=1, updated_at=datetime('now') WHERE id=?", (mid,))
    ok = goals["MU"] == m["mu_score"] and goals["OPP"] == m["opp_score"]
    return "" if ok else f" ⚠ 골 이벤트 {goals['MU']}-{goals['OPP']} ≠ 스코어 {m['mu_score']}-{m['opp_score']}"


def status(con) -> tuple[list[int], int]:
    need_list, pending = [], 0
    for y in SEASONS:
        s = season_label(y)
        n, done = con.execute("SELECT COUNT(*), COALESCE(SUM(details_synced=1),0) FROM matches "
                              "WHERE season=? AND match_af_id IS NOT NULL", (s,)).fetchone()
        print(f"  {s}: 경기 {n} · 상세 완료 {done}" + ("  (목록 미수집)" if n == 0 else ""))
        if n == 0:
            need_list.append(y)
        pending += n - done
    return need_list, pending


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-calls", type=int, default=90)
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()

    con = connect()
    print("[API-Football 과거 시즌 백필]")
    need_list, pending = status(con)
    if args.status or (not need_list and pending == 0):
        print("  완료 — API 호출 없음" if not need_list and pending == 0 else "")
        return 0
    key = load_env().get("API_FOOTBALL_KEY")
    if not key:
        print("⚠ API_FOOTBALL_KEY 없음 → 과거 시즌 백필 건너뜀")
        return 0

    api = Api(key, args.max_calls)
    warns = []
    with SyncLog(con, "api-football", "backfill") as log:
        try:
            for y in need_list:
                body = api.get(f"/fixtures?team={MUFC_AF}&season={y}")
                n = save_fixture_list(con, season_label(y), body["response"])
                con.commit()
                print(f"  {season_label(y)} 경기 목록 저장: {n}경기 (친선전 제외)")
            todo = con.execute(f"""SELECT * FROM matches WHERE match_af_id IS NOT NULL AND COALESCE(details_synced,0)=0
                                   AND season IN ({','.join('?' * len(SEASONS))}) ORDER BY kickoff_utc""",
                               [season_label(y) for y in SEASONS]).fetchall()
            for m in todo:
                body = api.get(f"/fixtures?id={m['match_af_id']}")
                if not body["response"]:
                    print(f"  {m['kickoff_utc'][:10]} vs {m['opponent_name']}: 응답 없음 → 건너뜀")
                    continue
                w = save_detail(con, m, body["response"][0])
                con.commit()
                log.rows += 1
                if w:
                    warns.append(f"{m['kickoff_utc'][:10]} vs {m['opponent_name']}{w}")
                print(f"  {m['kickoff_utc'][:10]} {m['competition_code']:<4} vs {m['opponent_name']:<22} "
                      f"{m['mu_score']}-{m['opp_score']}{w}")
        except Quota as q:
            print(f"  ⏸ {q}")
        log.api_calls = api.calls
        _, left = status(con)
        log.message = f"calls={api.calls} detailed={log.rows} remaining_matches={left} warns={len(warns)}"
        con.commit()
    print(f"  호출 {api.calls}회 · 상세 {log.rows}경기 · 남은 경기 {left}"
          + (f" · 오늘 남은 한도 {api.remaining}" if api.remaining is not None else ""))
    for w in warns:
        print(f"⚠ 백필 검증: {w}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
