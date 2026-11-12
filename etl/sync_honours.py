"""우승 기록 자동 계산 — 시즌 기록(season_standings)과 경기 결과(matches)에서 우승을 찾아 honours 를 채운다.

사용법:
    python etl/sync_honours.py            # 매 동기화 (fetch_* 다음, export 전)
    python etl/sync_honours.py --dry-run

근거
- 리그 우승: season_standings 1위 (PL·1부) — 시즌 종료(is_final) 또는 38경기 다 치른 경우만
- FA컵·리그컵: season_standings 결과 'Winners'
- 유럽대회·슈퍼컵·인터컨티넨털컵·클럽월드컵: season_standings europe_result 'Winners'
- 진행 중 시즌: matches 에서 결승(stage=Final) 승리 (승부차기 승 포함) — 커뮤니티실드 포함
시즌 표기는 기존 honours 규칙을 따름: 리그 '2012-13', 컵 대회 = 결승이 열린 해
(FA컵·리그컵·유럽대회 = 시즌 끝 연도, 커뮤니티실드·슈퍼컵·인터컨티넨털컵·클럽월드컵 = 시즌 시작 연도)

- 계산 결과에 있는데 honours 에 없으면 추가 (note='auto: …')
- honours 에 있는데 계산 결과에 없으면 지우지 않고 ⚠ 경고 (커뮤니티실드는 과거 시즌 근거 데이터가 없어 비교 제외)
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import SyncLog, connect  # noqa: E402

NAMES = {"PL": "League Champions", "FL1": "League Champions", "FAC": "FA Cup", "ELC": "League Cup",
         "UCL": "European Cup / Champions League", "UCWC": "European Cup Winners' Cup", "UEL": "UEFA Europa League",
         "USC": "UEFA Super Cup", "ICC": "Intercontinental Cup", "CWC": "FIFA Club World Cup", "CS": "Community Shield"}
START_YEAR_CODES = {"CS", "USC", "ICC", "CWC"}       # 시즌 초(8~12월)에 열리는 대회
DERIVABLE = set(NAMES) - {"CS"}                     # 과거 시즌까지 근거가 있는 대회
EUROPE_MAIN = {"european cup": "UCL", "champions league": "UCL", "uefa champions league": "UCL",
               "cup winners' cup": "UCWC", "europa league": "UEL", "uefa cup": "UEL"}
EUROPE_EXTRA = {"super cup": "USC", "intercontinental cup": "ICC", "club world cup": "CWC",
                "europa league": "UEL", "cup winners' cup": "UCWC"}
MATCH_CODES = {"FAC": "FAC", "ELC": "ELC", "CS": "CS", "UCL": "UCL", "CL": "UCL", "UEL": "UEL", "EL": "UEL"}
ALERTS: list[str] = []


def label(code: str, start_year: int) -> str:
    if code in ("PL", "FL1"):
        return f"{start_year}-{(start_year + 1) % 100:02d}"
    return str(start_year if code in START_YEAR_CODES else start_year + 1)


def derive(con) -> dict:
    """{(code, season_label): 근거}"""
    out = {}
    for r in con.execute("""SELECT s.season, se.start_year, s.division, s.position, s.played, s.is_final,
                                   s.fa_cup_result, s.league_cup_result, s.europe_competition, s.europe_result
                            FROM season_standings s JOIN seasons se ON se.season = s.season"""):
        y = r["start_year"]
        if r["position"] == 1 and (r["is_final"] or (r["played"] or 0) >= 38):
            code = {"Premier League": "PL", "First Division": "FL1"}.get(r["division"])
            if code:
                out[(code, label(code, y))] = f"{r['season']} 리그 1위"
        if r["fa_cup_result"] == "Winners":
            out[("FAC", label("FAC", y))] = f"{r['season']} FA컵 Winners"
        if r["league_cup_result"] == "Winners":
            out[("ELC", label("ELC", y))] = f"{r['season']} 리그컵 Winners"
        parts = [p.strip() for p in (r["europe_result"] or "").split("·")]
        if parts and parts[0] == "Winners":
            code = EUROPE_MAIN.get((r["europe_competition"] or "").lower())
            if code:
                out[(code, label(code, y))] = f"{r['season']} {r['europe_competition']} Winners"
        for p in parts[1:]:
            if "–" in p:
                comp, res = (x.strip() for x in p.split("–", 1))
                code = EUROPE_EXTRA.get(comp.lower())
                if code and res == "Winners":
                    out[(code, label(code, y))] = f"{r['season']} {comp} Winners"
    # 경기 결과: 결승 승리 (진행 중 시즌·커뮤니티실드)
    for m in con.execute("""SELECT m.competition_code, m.stage, m.kickoff_utc, m.result, m.mu_pens, m.opp_pens,
                                   m.opponent_name, m.mu_score, m.opp_score, se.start_year
                            FROM matches m JOIN seasons se ON se.season = m.season WHERE m.status='FINISHED'"""):
        code = MATCH_CODES.get(m["competition_code"])
        stage = (m["stage"] or "").strip().lower()
        is_final = stage in ("final", "the final") or (code == "CS" and stage in ("", "final"))
        won = m["result"] == "W" or (m["result"] == "D" and (m["mu_pens"] or 0) > (m["opp_pens"] or 0))
        if code and is_final and won:
            score = f"{m['mu_score']}-{m['opp_score']}" + (f" ({m['mu_pens']}-{m['opp_pens']} pens)" if m["mu_pens"] is not None else "")
            out[(code, label(code, m["start_year"]))] = f"결승 승리 vs {m['opponent_name']} {score} ({m['kickoff_utc'][:10]})"
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    con = connect()
    have = {(r["competition_code"], r["season"]) for r in con.execute("SELECT competition_code, season FROM honours")}
    got = derive(con)
    new = sorted(k for k in got if k not in have)
    missing = sorted(k for k in have if k[0] in DERIVABLE and k not in got)
    print(f"[우승 기록] 저장 {len(have)}건 · 계산 {len(got)}건 · 새로 추가 {len(new)} · 근거 없음 {len(missing)}")
    for code, season in missing:
        ALERTS.append(f"⚠ 우승 기록 근거 없음: {NAMES.get(code, code)} {season} — 시즌 기록·경기 결과에서 우승이 확인 안 됨 (기존 기록 유지, 확인 필요)")
        print(ALERTS[-1])
    if args.dry_run:
        for k in new:
            print(f"  + {k[0]} {k[1]} ← {got[k]}")
        return 0
    with SyncLog(con, "derived", "honours") as log:
        for code, season in new:
            con.execute("INSERT INTO honours (competition_code, competition_name, season, note) VALUES (?, ?, ?, ?)",
                        (code, NAMES[code], season, f"auto: {got[(code, season)]}"))
            print(f"  🏆 우승 기록 추가: {NAMES[code]} {season} ← {got[(code, season)]}")
            log.rows += 1
        log.message = f"stored={len(have)} derived={len(got)} added={len(new)} unsupported={len(missing)}"
        con.commit()
    rdir = os.environ.get("REPORT_DIR")
    if rdir and ALERTS:
        with open(Path(rdir) / "3_honours.txt", "a", encoding="utf-8") as f:
            f.write("\n".join(ALERTS) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
