"""종료 경기 요약 생성 → match_analyses (규칙 기반 템플릿, Claude API 미사용).

- analysis_md : 웹페이지용 영문 요약 (본문 영문 규칙)
- summary_ko  : 카톡 전송용 한글 짧은 요약 (STEP 4 에서 사용)
- model       : 'template-v1'
요약 생성부는 generate() 하나로 분리 → 나중에 Claude API 분석으로 교체 가능.

사용법: python scripts/summarize_match.py          (현재 시즌 종료 경기 전체 재생성 — 결과가 같으면 변경 없음)
"""
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "manutd.db"
MODEL = "template-v1"
COMP_EN = {"PL": "Premier League", "UCL": "Champions League", "UEL": "Europa League", "FAC": "FA Cup",
           "ELC": "EFL Cup", "CS": "Community Shield"}
COMP_KO = {"PL": "PL", "UCL": "챔스", "UEL": "유로파", "FAC": "FA컵", "ELC": "EFL컵"}


def ordinal(n: int) -> str:
    return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def names(lst) -> str:
    """['A','B','A'] → 'A (2) and B'"""
    c = Counter(lst)
    parts = [f"{n} ({k})" if k > 1 else n for n, k in c.items()]
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def names_ko(lst) -> str:
    """['A','A','B'] → 'A(2), B' (카톡 짧은 요약용)"""
    return ", ".join(f"{n}({k})" if k > 1 else n for n, k in Counter(lst).items())


def uk_date(iso: str) -> str:
    d = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(ZoneInfo("Europe/London"))
    return d.strftime("%a %d %b").replace(" 0", " ")


def generate(ctx: dict) -> dict:
    """경기 정보(ctx) → 요약. 다른 생성기(예: Claude)로 바꿀 때 이 함수만 교체."""
    m, ev = ctx["match"], ctx["events"]
    opp, mu, op = m["opponent_name"], m["mu_score"], m["opp_score"]
    home = m["home_away"] == "H"
    where = "at Old Trafford" if home else f"away at {m['venue']}" if m["venue"] else "away from home"
    comp = COMP_EN.get(m["competition_code"], m["competition_code"])
    stage = f" (matchweek {m['matchday']})" if m["competition_code"] == "PL" and m["matchday"] else \
            f" league phase (matchday {m['matchday']})" if m["competition_code"] == "UCL" and m["matchday"] else ""
    verb = (f"beat {opp} {mu}-{op}" if mu > op else
            f"drew {mu}-{op} with {opp}" if mu == op else f"lost {mu}-{op} to {opp}")
    s = [f"Manchester United {verb} {where} in the {comp}{stage}."]

    def of(side, kind):
        return [e["player_name"] for e in ev if e["team_side"] == side and e["event_type"] == kind]

    if ev:
        mu_goals, opp_goals = of("MU", "goal"), of("OPP", "goal")
        og_for_mu, og_for_opp = of("OPP", "own_goal"), of("MU", "own_goal")
        if mu_goals or og_for_mu:
            g = f"United's goals came from {names(mu_goals)}" if mu_goals else "United scored"
            if og_for_mu:
                g += (", plus " if mu_goals else " via ") + f"an own goal by {names(og_for_mu)}"
            s.append(g + ".")
        ast = of("MU", "assist")
        if ast:
            s.append(f"Assists: {names(ast)}.")
        if opp_goals or og_for_opp:
            g = f"{opp} scored through {names(opp_goals)}" if opp_goals else f"{opp} scored"
            if og_for_opp:
                g += (", with " if opp_goals else " via ") + f"an own goal by {names(og_for_opp)}"
            s.append(g + ".")
        for side, team in (("MU", "United"), ("OPP", opp)):
            if of(side, "missed_penalty"):
                s.append(f"{names(of(side, 'missed_penalty'))} missed a penalty for {team}.")
        reds = of("MU", "red") + of("OPP", "red")
        if reds:
            s.append(f"Sent off: {names(reds)}.")
        yel_mu, yel_opp = of("MU", "yellow"), of("OPP", "yellow")
        if yel_mu or yel_opp:
            parts = []
            if yel_mu:
                parts.append(f"{names(yel_mu)} (United)")
            if yel_opp:
                parts.append(f"{names(yel_opp)} ({opp})")
            s.append("Booked: " + "; ".join(parts) + ".")
    elif m["competition_code"] != "PL":
        s.append("Scorer and card details are not available for this competition on the free data plan.")

    bonus = sorted(((int(e["detail"] or 0), e["player_name"], e["team_side"]) for e in ev
                    if e["event_type"] == "bonus"), reverse=True)
    potm = None
    if bonus:
        mu_bonus = [b for b in bonus if b[2] == "MU"]
        potm = mu_bonus[0][1] if mu_bonus else None  # 맨유 선수 중 최고 활약
        # 예: "Top performers (FPL bonus points): Alysson 3, Dorgu (United) 2, N.Jackson 2."
        s.append("Top performers (FPL bonus points): " + ", ".join(
            f"{n}{' (United)' if side == 'MU' else ''} {p}" for p, n, side in bonus) + ".")

    if ctx.get("is_latest_pl") and ctx.get("pl_row"):
        r = ctx["pl_row"]
        s.append(f"United sit {ordinal(r['position'])} in the Premier League on {r['points']} points "
                 f"after {r['played']} games.")
    if ctx.get("next_match"):
        n = ctx["next_match"]
        s.append(f"Next: {n['opponent_name']} ({'H' if n['home_away'] == 'H' else 'A'}), "
                 f"{COMP_EN.get(n['competition_code'], n['competition_code'])}, {uk_date(n['kickoff_utc'])} (UK).")

    # 카톡용 한글 짧은 요약
    res_ko = {"W": "승", "D": "무", "L": "패"}.get(m["result"], "")
    ko = [f"맨유 {mu}-{op} {opp} ({COMP_KO.get(m['competition_code'], m['competition_code'])}"
          f"{' ' + str(m['matchday']) + 'R' if m['competition_code'] == 'PL' and m['matchday'] else ''}, "
          f"{'홈' if home else '원정'}) {res_ko}"]
    if ev:
        if of("MU", "goal") or of("OPP", "own_goal"):
            ko.append("득점: " + ", ".join(filter(None, [names_ko(of("MU", "goal")),
                                                         names_ko([f"{x} 자책골" for x in of("OPP", "own_goal")])])))
        cards = of("MU", "yellow") + [f"{x} 퇴장" for x in of("MU", "red")]
        if cards:
            ko.append("카드: " + names_ko(cards))
    return {"analysis_md": " ".join(s), "summary_ko": " · ".join(ko), "player_of_match": potm}


def main() -> None:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    season = con.execute("SELECT season FROM seasons WHERE is_current=1").fetchone()[0]
    fin = con.execute("SELECT * FROM matches WHERE season=? AND status='FINISHED' ORDER BY kickoff_utc",
                      (season,)).fetchall()
    latest_pl = max((m["id"] for m in fin if m["competition_code"] == "PL"),
                    key=lambda i: next(x["kickoff_utc"] for x in fin if x["id"] == i), default=None)
    latest_any = fin[-1]["id"] if fin else None
    pl_row = con.execute("""SELECT l.position, l.points, l.played FROM league_table l JOIN teams t ON t.id=l.team_id
                            WHERE l.season=? AND l.competition_code='PL' AND t.team_fd_id=66""",
                         (season,)).fetchone()
    nxt = con.execute("""SELECT * FROM matches WHERE season=? AND status NOT IN ('FINISHED','CANCELLED','POSTPONED')
                         ORDER BY kickoff_utc LIMIT 1""", (season,)).fetchone()
    changed = 0
    for m in fin:
        ev = [dict(r) for r in con.execute(
            "SELECT team_side, event_type, player_name, detail FROM match_events WHERE match_id=? ORDER BY id",
            (m["id"],))]
        out = generate({"match": dict(m), "events": ev,
                        "is_latest_pl": m["id"] == latest_pl, "pl_row": dict(pl_row) if pl_row else None,
                        "next_match": dict(nxt) if nxt and m["id"] == latest_any else None})
        old = con.execute("SELECT analysis_md, summary_ko, player_of_match, model FROM match_analyses "
                          "WHERE match_id=?", (m["id"],)).fetchone()
        new = (out["analysis_md"], out["summary_ko"], out["player_of_match"], MODEL)
        if old and tuple(old) == new:
            continue
        con.execute("""INSERT INTO match_analyses (match_id, model, summary_ko, analysis_md, player_of_match)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(match_id) DO UPDATE SET model=excluded.model, summary_ko=excluded.summary_ko,
                         analysis_md=excluded.analysis_md, player_of_match=excluded.player_of_match,
                         created_at=datetime('now')""",
                    (m["id"], MODEL, out["summary_ko"], out["analysis_md"], out["player_of_match"]))
        changed += 1
    con.commit()
    con.close()
    print(f"[경기 요약] 종료 {len(fin)}경기 · 새로 생성/갱신 {changed}건 ({MODEL})")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
