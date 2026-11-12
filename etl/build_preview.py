"""다음 경기 프리뷰 생성 (통계·규칙 기반, AI 미사용).

사용법:
    python etl/build_preview.py            # 생성 + DB 저장
    python etl/build_preview.py --dry-run  # 결과 JSON 만 출력

저장 테이블
    match_previews  (match_id, generated_utc, data_json)  — 사이트 메인 화면 '매치 프리뷰' 패널

내용 (모두 실제 데이터에서 계산, 문장은 정해진 규칙으로 생성)
    맨유 / 상대 팀   최근 경기 흐름(연승·무패·실점 등), 순위, 핵심 선수
    승부 예측        최근 10경기 득·실점 기반 푸아송 모델 (홈 이점 반영) → 승/무/패 %, 가장 가능성 높은 스코어
    부상·결장        FPL 선수 상태 (PL 팀만 — 상대가 PL 이 아니면 맨유만)
    예상 선발        최근 PL 5경기 선발 기록(최근일수록 가중) + 부상·징계 제외, 직전 경기 포지션 구성 유지
    상대 전적        football-data 맞대결 기록

데이터 출처 / 요청 수
    DB (맨유 경기·순위·선수·라인업), football-data(상대 최근 경기 1회 + 맞대결 1회), FPL bootstrap 1회
"""
import argparse
import json
import math
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import MUFC_FD, SyncLog, connect, get_json, load_env, names_match, utc_now  # noqa: E402

FD = "https://api.football-data.org/v4"
FPL = "https://fantasy.premierleague.com/api/bootstrap-static/"
POS = {1: "GK", 2: "DF", 3: "MF", 4: "FW"}
FPL_ALIAS = {"NOT": "NFO"}  # football-data TLA → FPL short_name 이 다른 팀
AVG = 1.35        # 팀당 경기 평균 득점 (리그 평균 근사)
SHRINK = 6        # 표본이 적을 때 평균 쪽으로 당기는 가상 경기 수
DAMP = 0.8        # 공격·수비 지수를 그대로 곱하면 극단값이 나와서 완화 (지수)
HOME_ADV = 1.12   # 홈 이점 (득점 배수)
FD_COMP = {"CL": "UCL", "EL": "UEL", "ELC": "CHAMP"}  # football-data 대회 코드 → 사이트 코드 (ELC 는 FD 에선 챔피언십)
LINEUP_W = [1.0, 0.8, 0.6, 0.45, 0.3]  # 최근 PL 5경기 선발 가중치 (최신 → 과거)

# ---------------------------------------------------------------- 부상 문구 번역 (FPL 영어 → 한국어)
INJ_KO = [
    (r"hamstring", "햄스트링"), (r"knee", "무릎"), (r"ankle", "발목"), (r"groin", "사타구니"), (r"calf", "종아리"),
    (r"thigh", "허벅지"), (r"foot", "발"), (r"back", "허리"), (r"shoulder", "어깨"), (r"hip", "고관절"),
    (r"achilles", "아킬레스건"), (r"shin", "정강이"), (r"illness", "질병"), (r"muscle", "근육"), (r"adductor", "내전근"), (r"quad", "대퇴사두근"),
    (r"concussion|head", "머리"), (r"toe", "발가락"), (r"hand|wrist|finger", "손"), (r"rib|chest", "갈비뼈"),
]
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def news_ko(news: str, status: str, chance) -> str:
    s = (news or "").strip()
    low = s.lower()
    if status == "s" or "suspend" in low:
        what = "출장 정지"
    elif "illness" in low:
        what = "질병"
    elif "knock" in low:
        what = "가벼운 부상(타박상)"
    elif "injur" in low or status == "i":
        part = next((ko for rx, ko in INJ_KO if re.search(rx, low)), "")
        what = f"{part} 부상".strip()
    elif "loan" in low:
        what = "임대 이적"
    elif "transfer" in low or "left the club" in low:
        what = "이적"
    elif status == "n":
        what = "출전 불가"
    else:
        what = "컨디션 문제"
    when = ""
    m = re.search(r"expected back (\d{1,2}) ([A-Za-z]{3})", s, re.I)
    if m and m.group(2).lower()[:3] in MONTHS:
        when = f"{MONTHS[m.group(2).lower()[:3]]}/{int(m.group(1))} 복귀 예상"
    elif re.search(r"unknown return", low):
        when = "복귀 시점 미정"
    elif m2 := re.search(r"until (\d{1,2}) ([A-Za-z]{3})", s, re.I):
        if m2.group(2).lower()[:3] in MONTHS:
            when = f"{MONTHS[m2.group(2).lower()[:3]]}/{int(m2.group(1))}까지"
    if chance is not None and 0 < chance < 100:
        when = (when + " · " if when else "") + f"출전 가능성 {chance}%"
    return f"{what} ({when})" if when else what


# ---------------------------------------------------------------- 경기 흐름 문장
def record(ms):
    w = sum(m["r"] == "W" for m in ms); d = sum(m["r"] == "D" for m in ms); l_ = sum(m["r"] == "L" for m in ms)
    return w, d, l_, sum(m["gf"] for m in ms), sum(m["ga"] for m in ms)


def form_points(ms: list[dict], label: str) -> list[str]:
    """ms: 최신순 [{r, gf, ga, ...}] → 한국어 핵심 포인트."""
    if not ms:
        return []
    out = []
    first, n = ms[0]["r"], 0
    for m in ms:
        if m["r"] != first:
            break
        n += 1
    if n >= 2:
        out.append({"W": f"공식전 {n}연승 중", "L": f"공식전 {n}연패 중", "D": f"{n}경기 연속 무승부"}[first])
    unbeaten = next((i for i, m in enumerate(ms) if m["r"] == "L"), len(ms))
    winless = next((i for i, m in enumerate(ms) if m["r"] == "W"), len(ms))
    if unbeaten >= 3 and not (first == "W" and n == unbeaten):
        out.append(f"최근 {unbeaten}경기 무패")
    if winless >= 3 and not (first == "L" and n == winless):
        out.append(f"최근 {winless}경기 무승")
    last5 = ms[:5]
    w, d, l_, gf, ga = record(last5)
    out.append(f"최근 {len(last5)}경기 {w}승 {d}무 {l_}패 · {gf}득점 {ga}실점")
    cs = sum(m["ga"] == 0 for m in last5)
    blank = sum(m["gf"] == 0 for m in last5)
    if len(last5) >= 4 and cs == 0:
        out.append(f"최근 {len(last5)}경기 모두 실점")
    elif cs >= 2:
        out.append(f"최근 {len(last5)}경기 중 무실점 {cs}회")
    if blank >= 2:
        out.append(f"최근 {len(last5)}경기 중 {blank}경기 무득점")
    if len(last5) >= 3 and gf / len(last5) >= 2.2:
        out.append(f"경기당 {gf / len(last5):.1f}골의 높은 득점력")
    if len(last5) >= 3 and ga / len(last5) >= 2.0:
        out.append(f"경기당 {ga / len(last5):.1f}실점으로 수비 불안")
    return out


def table_point(tbl: list[dict], team_id, comp: str) -> str | None:
    row = next((r for r in tbl if r["team_id"] == team_id), None)
    if not row:
        return None
    pos, pts = row["position"], row["points"]
    s = f"{'PL' if comp == 'PL' else '챔스 리그 페이즈'} {pos}위 (승점 {pts}, {row['played']}경기)"
    if comp == "PL":
        by = {r["position"]: r for r in tbl}
        if pos >= 15 and 18 in by and 17 in by:
            gap = pts - by[18]["points"] if pos <= 17 else by[17]["points"] - pts
            s += f" · 강등권과 승점 {gap}점 차" if pos <= 17 else f" · 잔류권(17위)과 승점 {gap}점 차"
        elif pos <= 6 and 4 in by and pos > 4:
            s += f" · 4위와 승점 {by[4]['points'] - pts}점 차"
        elif pos == 1 and 2 in by:
            s += f" · 2위와 승점 {pts - by[2]['points']}점 차"
    else:
        s += " · 16강 직행권" if pos <= 8 else " · 플레이오프권" if pos <= 24 else " · 탈락권"
    return s


# ---------------------------------------------------------------- 예측 (푸아송)
def rate(ms):
    n = len(ms)
    gf = sum(m["gf"] for m in ms); ga = sum(m["ga"] for m in ms)
    return (gf + AVG * SHRINK) / (n + SHRINK), (ga + AVG * SHRINK) / (n + SHRINK)


def pois(k, lam):
    return math.exp(-lam) * lam ** k / math.factorial(k)


def predict(mu_ms, op_ms, home_away: str) -> dict:
    a_mu, d_mu = rate(mu_ms[:10]); a_op, d_op = rate(op_ms[:10])
    hf = HOME_ADV if home_away == "H" else 1 / HOME_ADV if home_away == "A" else 1.0
    lam_mu = AVG * (a_mu / AVG) ** DAMP * (d_op / AVG) ** DAMP * hf
    lam_op = AVG * (a_op / AVG) ** DAMP * (d_mu / AVG) ** DAMP / hf
    win = draw = loss = 0.0
    best, best_p = (0, 0), -1
    for i in range(11):
        for j in range(11):
            p = pois(i, lam_mu) * pois(j, lam_op)
            if i > j:
                win += p
            elif i == j:
                draw += p
            else:
                loss += p
            if p > best_p:
                best, best_p = (i, j), p
    tot = win + draw + loss
    pct = [round(100 * x / tot) for x in (win, draw, loss)]
    pct[1] = 100 - pct[0] - pct[2]
    return {"win": pct[0], "draw": pct[1], "loss": pct[2], "xg_mu": round(lam_mu, 2), "xg_opp": round(lam_op, 2),
            "score_mu": best[0], "score_opp": best[1], "sample_mu": len(mu_ms[:10]), "sample_opp": len(op_ms[:10])}


# ---------------------------------------------------------------- 예상 선발
def predicted_xi(con, season: str) -> dict:
    recent = [r["id"] for r in con.execute(
        "SELECT m.id FROM matches m WHERE m.season=? AND m.competition_code='PL' AND m.status='FINISHED' "
        "AND EXISTS (SELECT 1 FROM match_lineups l WHERE l.match_id=m.id) ORDER BY m.kickoff_utc DESC LIMIT 5",
        (season,))]
    if not recent:
        return {"players": [], "basis": 0}
    score, info = {}, {}
    for w, mid in zip(LINEUP_W, recent):
        for r in con.execute("SELECT player_id, player_name, position, is_starter FROM match_lineups "
                             "WHERE match_id=? AND team_side='MU'", (mid,)):
            pid = r["player_id"]
            score[pid] = score.get(pid, 0) + w * (1 if r["is_starter"] else 0.25)
            info.setdefault(pid, {"name": r["player_name"], "pos": r["position"]})
    shape = {}
    for r in con.execute("SELECT position, COUNT(*) n FROM match_lineups WHERE match_id=? AND team_side='MU' "
                         "AND is_starter=1 GROUP BY position", (recent[0],)):
        shape[r["position"]] = r["n"]
    avail = {r["player_id"]: dict(r) for r in con.execute(
        "SELECT a.player_id, a.status, a.chance_next, a.news, m.status AS squad FROM player_availability a "
        "LEFT JOIN squad_memberships m ON m.player_id=a.player_id AND m.season=?", (season,))}
    pool, doubt = [], set()
    for pid, sc in score.items():
        a = avail.get(pid, {})
        if a.get("squad") not in (None, "active") or a.get("status") in ("i", "s", "n", "u"):
            continue
        if a.get("status") == "d" and (a.get("chance_next") or 0) < 50:
            continue
        if a.get("status") == "d":
            doubt.add(pid)
        pool.append((sc, pid))
    pool.sort(reverse=True)
    chosen = []
    for pos in ("GK", "DF", "MF", "FW"):
        want = shape.get(pos, 0)
        chosen += [pid for _, pid in [x for x in pool if info[x[1]]["pos"] == pos][:want]]
    for _, pid in pool:  # 포지션 구성을 못 채우면 남은 선수 중 점수 순
        if len(chosen) >= 11:
            break
        if pid not in chosen:
            chosen.append(pid)
    order = {"GK": 0, "DF": 1, "MF": 2, "FW": 3}
    out = []
    for pid in sorted(chosen[:11], key=lambda p: (order.get(info[p]["pos"], 9), -score[p])):
        sc = score[pid]
        out.append({"name": info[pid]["name"], "pos": info[pid]["pos"],
                    "conf": "높음" if sc >= 2.2 and pid not in doubt else "보통" if sc >= 1.0 else "낮음",
                    "doubt": pid in doubt})
    return {"players": out, "basis": len(recent),
            "shape": " · ".join(f"{p} {shape[p]}" for p in ("GK", "DF", "MF", "FW") if shape.get(p))}


# ---------------------------------------------------------------- 메인
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    env = load_env()
    hdr = {"X-Auth-Token": env.get("FOOTBALL_DATA_TOKEN", "")}

    con = connect()
    season = con.execute("SELECT season FROM seasons WHERE is_current=1").fetchone()["season"]
    now = datetime.now(timezone.utc)
    nxt = con.execute(
        "SELECT m.*, t.team_fd_id AS opp_fd, t.tla AS opp_tla, t.short_name AS opp_short, t.name AS opp_full "
        "FROM matches m LEFT JOIN teams t ON t.id=m.opponent_id WHERE m.status NOT IN "
        "('FINISHED','CANCELLED','POSTPONED','AWARDED') AND m.kickoff_utc > ? ORDER BY m.kickoff_utc LIMIT 1",
        ((now - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ"),)).fetchone()
    if not nxt:
        print("[프리뷰] 다가오는 경기 없음 → 건너뜀")
        return 0
    opp = nxt["opponent_name"]
    print(f"[프리뷰] {nxt['kickoff_utc'][:10]} {nxt['competition_code']} vs {opp}")
    calls, notes = 0, []

    # --- 맨유 최근 경기 (DB, 모든 대회, 최신순)
    mu_ms = [{"date": r["kickoff_utc"][:10], "comp": r["competition_code"], "ha": r["home_away"],
              "opp": r["opponent_name"], "gf": r["mu_score"], "ga": r["opp_score"], "r": r["result"]}
             for r in con.execute("SELECT * FROM matches WHERE status='FINISHED' AND mu_score IS NOT NULL "
                                  "ORDER BY kickoff_utc DESC LIMIT 10")]

    # --- 상대 최근 경기 (football-data, 모든 대회)
    op_ms = []
    if nxt["opp_fd"] and hdr["X-Auth-Token"]:
        try:
            frm = (now - timedelta(days=150)).strftime("%Y-%m-%d")
            res = get_json(f"{FD}/teams/{nxt['opp_fd']}/matches?status=FINISHED&dateFrom={frm}&dateTo={now:%Y-%m-%d}", hdr)
            calls += 1
            for m in sorted(res.get("matches", []), key=lambda x: x["utcDate"], reverse=True)[:10]:
                ft = m["score"]["fullTime"]
                if ft["home"] is None:
                    continue
                home = m["homeTeam"]["id"] == nxt["opp_fd"]
                gf, ga = (ft["home"], ft["away"]) if home else (ft["away"], ft["home"])
                win = m["score"].get("winner")
                r = "D" if win in ("DRAW", None) else "W" if (win == "HOME_TEAM") == home else "L"
                if gf != ga:
                    r = "W" if gf > ga else "L"
                op_ms.append({"date": m["utcDate"][:10], "comp": FD_COMP.get(m["competition"]["code"], m["competition"]["code"]), "ha": "H" if home else "A",
                              "opp": (m["awayTeam"] if home else m["homeTeam"]).get("shortName") or "",
                              "gf": gf, "ga": ga, "r": r})
        except RuntimeError as e:
            print(f"  상대 최근 경기 수집 실패: {str(e)[:100]}")
    if not op_ms:
        notes.append(f"{opp}의 최근 경기 기록이 무료 데이터에 없어 상대 분석·예측이 제한됩니다.")

    # --- 상대 전적 (football-data head2head)
    h2h = []
    if nxt["match_fd_id"] and hdr["X-Auth-Token"]:
        try:
            res = get_json(f"{FD}/matches/{nxt['match_fd_id']}/head2head?limit=10", hdr)
            calls += 1
            for m in sorted(res.get("matches", []), key=lambda x: x["utcDate"], reverse=True):
                ft = m["score"]["fullTime"]
                if ft["home"] is None or m["status"] != "FINISHED":
                    continue
                home = m["homeTeam"]["id"] == MUFC_FD
                gf, ga = (ft["home"], ft["away"]) if home else (ft["away"], ft["home"])
                h2h.append({"date": m["utcDate"][:10], "comp": FD_COMP.get(m["competition"]["code"], m["competition"]["code"]), "ha": "H" if home else "A",
                            "gf": gf, "ga": ga, "r": "W" if gf > ga else "L" if gf < ga else "D"})
        except RuntimeError as e:
            print(f"  맞대결 기록 수집 실패: {str(e)[:100]}")

    # --- 순위
    comp = nxt["competition_code"]
    tcomp = comp if comp in ("PL", "UCL") else "PL"
    tbl = [dict(r) for r in con.execute("SELECT l.*, t.team_fd_id FROM league_table l LEFT JOIN teams t ON t.id=l.team_id "
                                        "WHERE l.season=? AND l.competition_code=?", (season, tcomp))]
    mu_tid = next((r["team_id"] for r in tbl if r["team_fd_id"] == MUFC_FD), None)
    op_tid = next((r["team_id"] for r in tbl if r["team_fd_id"] == nxt["opp_fd"]), None) if nxt["opp_fd"] else None
    if op_tid is None and comp not in ("PL", "UCL"):
        notes.append(f"{opp}은(는) 다른 리그 팀이라 상대 기록의 수준 차이가 예측에 반영되지 않습니다.")

    # --- FPL 부상·핵심 선수
    mu_out, op_out, op_keys = [], None, []  # op_out=None → 상대 부상 정보 없음 (PL 팀 아님)
    try:
        boot = get_json(FPL)
        calls += 1
        teams = {t["id"]: t for t in boot["teams"]}
        mu_fpl = next(t["id"] for t in boot["teams"] if t["code"] == 1)
        want = FPL_ALIAS.get(nxt["opp_tla"] or "", nxt["opp_tla"])
        op_fpl = next((t["id"] for t in teams.values() if t["short_name"] == want), None) or next(
            (t["id"] for t in teams.values() if names_match(t["name"], nxt["opp_short"] or opp)
             or t["name"] == (nxt["opp_short"] or opp)), None)

        def outs(tid):
            rows = [e for e in boot["elements"] if e["team"] == tid and e["status"] in ("i", "s", "d", "n")
                    and not (e["status"] == "d" and (e["chance_of_playing_next_round"] or 0) >= 75)]
            rows.sort(key=lambda e: -e["minutes"])
            return [{"name": e["web_name"], "pos": POS[e["element_type"]], "status": e["status"],
                     "chance": e["chance_of_playing_next_round"], "ko": news_ko(e["news"], e["status"], e["chance_of_playing_next_round"]),
                     "news": e["news"], "minutes": e["minutes"]} for e in rows[:10]]
        mu_out = outs(mu_fpl)
        if op_fpl:
            op_out = outs(op_fpl)
            ks = [e for e in boot["elements"] if e["team"] == op_fpl]
            ks.sort(key=lambda e: (-(e["goals_scored"] + e["assists"]), -e["minutes"]))
            op_keys = [{"name": e["web_name"], "pos": POS[e["element_type"]], "goals": e["goals_scored"],
                        "assists": e["assists"]} for e in ks[:3] if e["goals_scored"] + e["assists"] > 0]
        else:
            notes.append(f"{opp}은(는) PL 팀이 아니라 상대 부상 정보가 없습니다.")
    except (RuntimeError, StopIteration, KeyError) as e:
        print(f"  FPL 수집 실패: {str(e)[:100]}")

    mu_keys = [{"name": r["name"], "pos": r["position"], "goals": r["goals"], "assists": r["assists"]}
               for r in con.execute("SELECT COALESCE(p.known_as, p.full_name) name, p.position, s.goals, s.assists "
                                    "FROM player_season_stats s JOIN players p ON p.id=s.player_id "
                                    "WHERE s.season=? AND s.competition_code='PL' AND s.goals + s.assists > 0 "
                                    "ORDER BY s.goals + s.assists DESC, s.goals DESC LIMIT 3", (season,))]

    # --- 맨유 홈/원정 성적 (이번 시즌)
    ha = nxt["home_away"]
    venue_ms = [m for m in mu_ms if m["ha"] == ha] if ha in ("H", "A") else []
    cur_ha = [dict(r) for r in con.execute("SELECT result r, mu_score gf, opp_score ga FROM matches WHERE season=? "
                                           "AND status='FINISHED' AND home_away=?", (season, ha))] if ha in ("H", "A") else []
    mu_points = form_points(mu_ms, "맨유")
    if cur_ha:
        w, d, l_, gf, ga = record(cur_ha)
        mu_points.append(f"이번 시즌 {'홈' if ha == 'H' else '원정'} {w}승 {d}무 {l_}패 ({gf}득점 {ga}실점)")
    tp = table_point(tbl, mu_tid, tcomp)
    if tp:
        mu_points.insert(0, tp)
    op_points = form_points(op_ms, opp)
    tp = table_point(tbl, op_tid, tcomp) if op_tid else None
    if tp:
        op_points.insert(0, tp)
    del venue_ms

    pred = predict(mu_ms, op_ms, ha) if op_ms else None
    xi = predicted_xi(con, season)

    # 감독 교체 직후·경질 보도가 있으면 예상 선발 신뢰도 낮음 안내
    mgr = con.execute("SELECT name, start_date FROM managers WHERE end_date IS NULL ORDER BY start_date DESC LIMIT 1").fetchone()
    recent_sack = con.execute(
        "SELECT COUNT(*) FROM news_items WHERE published_utc >= ? AND (title LIKE '%sack%' OR title LIKE '%new manager%' "
        "OR title LIKE '%appoint%' OR title LIKE '%interim%' OR title LIKE '%caretaker%')",
        ((now - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ"),)).fetchone()[0] \
        if con.execute("SELECT 1 FROM sqlite_master WHERE name='news_items'").fetchone() else 0
    if (mgr and mgr["start_date"] and mgr["start_date"] >= (now - timedelta(days=30)).strftime("%Y-%m-%d")) or recent_sack >= 3:
        xi["caveat"] = "감독 교체 이슈가 있어, 지난 경기 기준 예상 선발은 실제와 많이 다를 수 있습니다."

    data = {
        "match_id": nxt["id"], "comp": comp, "opponent": opp, "home_away": ha, "kickoff_utc": nxt["kickoff_utc"],
        "mu": {"points": mu_points, "recent": mu_ms[:5], "keys": mu_keys, "out": mu_out},
        "opp": {"points": op_points, "recent": op_ms[:5], "keys": op_keys, "out": op_out},
        "prediction": pred, "lineup": xi, "h2h": h2h[:6],
        "h2h_record": dict(zip(("w", "d", "l", "gf", "ga"), record(h2h[:6]))) if h2h else None,
        "notes": notes, "generated_utc": utc_now(),
    }
    if args.dry_run:
        print(json.dumps(data, ensure_ascii=False, indent=1))
        return 0
    con.execute("""CREATE TABLE IF NOT EXISTS match_previews (
        match_id INTEGER PRIMARY KEY, generated_utc TEXT, data_json TEXT)""")
    with SyncLog(con, "preview", "next match") as log:
        log.api_calls = calls
        con.execute("INSERT INTO match_previews (match_id, generated_utc, data_json) VALUES (?,?,?) "
                    "ON CONFLICT(match_id) DO UPDATE SET generated_utc=excluded.generated_utc, data_json=excluded.data_json",
                    (nxt["id"], data["generated_utc"], json.dumps(data, ensure_ascii=False)))
        log.rows = 1
        log.message = f"match={nxt['id']} vs {opp}"
    p = pred and f"승 {pred['win']}% 무 {pred['draw']}% 패 {pred['loss']}% · 예상 {pred['score_mu']}-{pred['score_opp']}"
    print(f"  맨유 포인트 {len(mu_points)} · 상대 포인트 {len(op_points)} · 예측 {p or '없음'} · 예상 선발 {len(xi['players'])}명 "
          f"· 결장 맨유 {len(mu_out)}/상대 {len(op_out)} · 맞대결 {len(h2h)}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
