"""종료 경기 요약 생성 → match_analyses (규칙 기반 템플릿, Claude API 미사용).

- analysis_md : 웹페이지용 한글 요약 (2026-11-15 본문 한글화)
- summary_ko  : 카톡 전송용 한글 짧은 요약 (STEP 4 에서 사용)
- model       : 'template-v2' (v1 = 영문)
요약 생성부는 generate() 하나로 분리 → 나중에 Claude API 분석으로 교체 가능.

사용법: python scripts/summarize_match.py          (현재 시즌 종료 경기 전체 재생성 — 결과가 같으면 변경 없음)
"""
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "manutd.db"
MODEL = "template-v2"
COMP_KO = {"PL": "PL", "UCL": "챔스", "UEL": "유로파", "FAC": "FA컵", "ELC": "EFL컵"}
COMP_KO_FULL = {"PL": "프리미어리그", "UCL": "챔피언스리그", "UEL": "유로파리그", "FAC": "FA컵", "ELC": "EFL컵",
                "CS": "커뮤니티 실드"}


def names_ko(lst) -> str:
    """['A','A','B'] → 'A(2), B' (카톡 짧은 요약용)"""
    return ", ".join(f"{n}({k})" if k > 1 else n for n, k in Counter(lst).items())


def stage_ko(stage: str | None) -> str:
    t = (stage or "").lower().replace("_", " ")
    for rx, ko in (("semi", "4강"), ("quarter", "8강"), ("round of 16", "16강"), ("final", "결승"),
                   ("first|1st", "1라운드"), ("second|2nd", "2라운드"), ("third|3rd", "3라운드"),
                   ("fourth|4th", "4라운드"), ("fifth|5th", "5라운드"), ("sixth|6th", "6라운드")):
        if re.search(rx, t):
            return ko
    return stage or ""


def kst_date(iso: str) -> str:
    d = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(ZoneInfo("Asia/Seoul"))
    return f"{d.month}/{d.day} ({'월화수목금토일'[d.weekday()]}) {d:%H:%M} KST"


def generate(ctx: dict) -> dict:
    """경기 정보(ctx) → 요약 (웹페이지용 한글 문단 + 카톡용 한 줄). 다른 생성기로 바꿀 때 이 함수만 교체."""
    m, ev = ctx["match"], ctx["events"]
    opp, mu, op = m["opponent_name"], m["mu_score"], m["opp_score"]
    home = m["home_away"] == "H"
    code = m["competition_code"]
    where = "올드 트래퍼드에서" if home else f"{m['venue']} 원정에서" if m["venue"] else "원정에서"
    comp = COMP_KO_FULL.get(code, code)
    stage = f" {m['matchday']}라운드" if code == "PL" and m["matchday"] else             f" 리그 페이즈 {m['matchday']}차전" if code == "UCL" and m["matchday"] else             f" {stage_ko(m.get('stage'))}" if code in ("FAC", "ELC") and m.get("stage") else ""
    res = "승리" if mu > op else "무승부" if mu == op else "패배"
    pens = ""
    if m.get("mu_pens") is not None:
        pens = f" (승부차기 {m['mu_pens']}-{m['opp_pens']})"
    s = [f"맨유가 {where} 열린 {comp}{stage} {opp}전에서 {mu}-{op}{pens} {res}를 기록했습니다."]

    def of(side, kind):
        return [e["player_name"] for e in ev if e["team_side"] == side and e["event_type"] == kind]

    if ev:
        mu_goals, opp_goals = of("MU", "goal"), of("OPP", "goal")
        og_for_mu, og_for_opp = of("OPP", "own_goal"), of("MU", "own_goal")
        if mu_goals or og_for_mu:
            s.append("맨유 득점: " + ", ".join(filter(None, [names_ko(mu_goals),
                                                         names_ko([f"{x} 자책골" for x in og_for_mu])])) + ".")
        if of("MU", "assist"):
            s.append(f"도움: {names_ko(of('MU', 'assist'))}.")
        if opp_goals or og_for_opp:
            s.append(f"{opp} 득점: " + ", ".join(filter(None, [names_ko(opp_goals),
                                                             names_ko([f"{x} 자책골" for x in og_for_opp])])) + ".")
        for side, team in (("MU", "맨유"), ("OPP", opp)):
            if of(side, "missed_penalty"):
                s.append(f"페널티 실축: {names_ko(of(side, 'missed_penalty'))} ({team}).")
        reds = of("MU", "red") + of("OPP", "red")
        if reds:
            s.append(f"퇴장: {names_ko(reds)}.")
        yel_mu, yel_opp = of("MU", "yellow"), of("OPP", "yellow")
        if yel_mu or yel_opp:
            parts = ([f"{names_ko(yel_mu)} (맨유)"] if yel_mu else []) + ([f"{names_ko(yel_opp)} ({opp})"] if yel_opp else [])
            s.append("경고: " + " / ".join(parts) + ".")
    elif code != "PL":
        s.append("이 대회는 무료 데이터로 득점자·카드 기록을 제공하지 않습니다.")

    bonus = sorted(((int(e["detail"] or 0), e["player_name"], e["team_side"]) for e in ev
                    if e["event_type"] == "bonus"), reverse=True)
    potm = None
    if bonus:
        mu_bonus = [b for b in bonus if b[2] == "MU"]
        potm = mu_bonus[0][1] if mu_bonus else None  # 맨유 선수 중 최고 활약
        s.append("최고 활약 (FPL 보너스 점수): " + ", ".join(
            f"{n}{'(맨유)' if side == 'MU' else ''} {p}" for p, n, side in bonus) + ".")

    if ctx.get("is_latest_pl") and ctx.get("pl_row"):
        r = ctx["pl_row"]
        s.append(f"맨유는 {r['played']}경기 승점 {r['points']}점으로 프리미어리그 {r['position']}위입니다.")
    if ctx.get("next_match"):
        n = ctx["next_match"]
        s.append(f"다음 경기: {n['opponent_name']} ({'홈' if n['home_away'] == 'H' else '원정'}, "
                 f"{COMP_KO_FULL.get(n['competition_code'], n['competition_code'])}, {kst_date(n['kickoff_utc'])}).")

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
