"""역대 시즌 기록 수집 (1886-87 ~ 지난 시즌) — 위키백과 'List of Manchester United F.C. seasons'.

사용법:  python etl/backfill_history.py [--dry-run]

→ seasons, season_standings (리그 성적·FA컵·리그컵·유럽대회·최다 득점자)
- 진행 중 시즌(seasons.is_current)은 건드리지 않음 (football-data 가 매일 갱신)
- 기존 행(manual-seed 등)은 위키백과 값으로 채우되, 순위가 다르면 경고 후 위키 값 사용
- 전쟁 기간(1915–19, 1939–46)처럼 리그가 없던 기간은 건너뜀
- 출처: 위키백과 (CC BY-SA 4.0), source='wikipedia:<revid>'
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import SyncLog, connect  # noqa: E402
import wiki  # noqa: E402

TITLE = "List of Manchester United F.C. seasons"
# 위키 표 Division → (competition_code, division 이름)
DIVISIONS = {
    "Prem": ("PL", "Premier League"),
    "Div 1": ("FL1", "First Division"),
    "Div 2": ("FL2", "Second Division"),
    "Alliance": ("FALL", "Football Alliance"),
    "Combination": ("COMB", "The Combination"),
}
EXTRA_COMPS = [("FALL", "Football Alliance", "풋볼 얼라이언스", "league"),
               ("COMB", "The Combination", "더 컴비네이션", "league")]
# 승점 감점 등 공식 예외 (시즌: 감점)
POINT_ADJUST = {"1990-91": -1}  # 1990년 아스널전 집단 난투 → 1점 감점
COLS = ["season", "division", "tier", "played", "won", "drawn", "lost", "goals_for", "goals_against",
        "points", "position", "fa_cup", "league_cup", "community_shield", "europe", "scorers", "goals"]


def cup(text: str) -> str | None:
    t = wiki.clean(text).replace("\n", " ")
    return None if t in ("", "—", "-", "N/A") or t.lower().startswith("not ") else t


def parse_rows(page: str) -> list[dict]:
    t = max(wiki.tables(page), key=lambda t: len(t["rows"]))
    head = [c["text"] for c in t["rows"][1]]
    assert head[:3] == ["Season", "Division", "Tier"] and head[10] == "Pos", f"표 구조 변경: {head}"
    out = []
    for r in t["rows"][2:]:
        if len(r) < len(COLS):
            continue
        c = dict(zip(COLS, r))
        m = re.fullmatch(r"(\d{4})[–-](\d{2}|\d{4})", c["season"]["text"])  # 1999–2000 형식 포함
        div_raw = re.sub(r"\s*[↑↓]", "", c["division"]["text"]).strip()
        if not m or div_raw not in DIVISIONS:
            continue  # 전쟁 기간·리그 없던 시즌(1886-87 등)
        start = int(m.group(1))
        code, div_name = DIVISIONS[div_raw]
        # 유럽·FIFA 대회는 한 시즌에 여러 개일 수 있음 (줄마다 '대회 – 결과')
        comp, res = None, None
        lines = [ln.strip() for ln in wiki.clean(c["europe"]["text"]).split("\n") if cup(ln)]
        if lines and "ban" not in " ".join(lines).lower():
            first = [p.strip() for p in lines[0].split("–", 1)]
            comp = first[0]
            res = " · ".join(([first[1]] if len(first) == 2 else []) + lines[1:]) or None
        scorers = c["scorers"]["links"] or [s for s in c["scorers"]["text"].split("\n") if s]
        pos = wiki.to_int(c["position"]["text"])
        out.append({
            "season": f"{start}-{(start + 1) % 100:02d}", "start_year": start, "competition_code": code,
            "division": div_name, "position": pos,
            **{k: wiki.to_int(c[k]["text"]) for k in ("played", "won", "drawn", "lost",
                                                      "goals_for", "goals_against", "points")},
            "top_scorer": " / ".join(scorers) or None, "top_scorer_goals": wiki.to_int(c["goals"]["text"]),
            "fa_cup_result": cup(c["fa_cup"]["text"]), "league_cup_result": cup(c["league_cup"]["text"]),
            "europe_competition": comp, "europe_result": res,
            "promoted": "↑" in c["division"]["text"], "relegated": "↓" in c["division"]["text"],
        })
    return out


def validate(rows: list[dict]) -> list[str]:
    """W+D+L=Pld, 승점(시대별 2점/3점) 일치 확인."""
    errs = []
    for r in rows:
        if None in (r["played"], r["won"], r["drawn"], r["lost"]):
            errs.append(f"{r['season']} 숫자 누락")
            continue
        if r["won"] + r["drawn"] + r["lost"] != r["played"]:
            errs.append(f"{r['season']} W+D+L≠Pld")
        adj = POINT_ADJUST.get(r["season"], 0)
        pts2, pts3 = 2 * r["won"] + r["drawn"] + adj, 3 * r["won"] + r["drawn"] + adj
        if r["points"] not in (pts2, pts3):
            errs.append(f"{r['season']} 승점 {r['points']} ≠ {pts2}/{pts3}")
    return errs


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    dry = "--dry-run" in sys.argv
    page, rev = wiki.page_html(TITLE)
    rows = parse_rows(page)
    errs = validate(rows)
    print(f"[위키백과] {TITLE} (rev {rev}) → 시즌 {len(rows)}개 ({rows[0]['season']} ~ {rows[-1]['season']})")
    for e in errs:
        print(f"  ⚠ {e}")
    if len(rows) < 110 or len(errs) > 5:
        print("✗ 표 구조가 예상과 달라 중단 (행 수 부족 또는 검증 오류 다수)")
        return 1

    con = connect()
    cur = con.execute("SELECT season FROM seasons WHERE is_current=1").fetchone()
    current = cur[0] if cur else None
    with SyncLog(con, "wikipedia", "history") as log:
        for code, name, ko, typ in EXTRA_COMPS:
            con.execute("INSERT OR IGNORE INTO competitions (code, name, name_ko, type) VALUES (?, ?, ?, ?)",
                        (code, name, ko, typ))
        new = upd = 0
        for r in rows:
            if r["season"] == current:
                continue
            con.execute("INSERT OR IGNORE INTO seasons (season, start_year) VALUES (?, ?)",
                        (r["season"], r["start_year"]))
            old = con.execute("SELECT * FROM season_standings WHERE season=? AND competition_code=?",
                              (r["season"], r["competition_code"])).fetchone()
            if old and old["position"] is not None and old["position"] != r["position"]:
                print(f"  ⚠ {r['season']} 순위 불일치: 기존 {old['position']} ↔ 위키 {r['position']} → 위키 값 사용")
            cols = ["division", "position", "played", "won", "drawn", "lost", "goals_for", "goals_against",
                    "points", "top_scorer", "top_scorer_goals", "fa_cup_result", "league_cup_result",
                    "europe_competition", "europe_result"]
            vals = [r[c] for c in cols]
            con.execute(
                f"""INSERT INTO season_standings (season, competition_code, {', '.join(cols)}, is_final, source, updated_at)
                    VALUES (?, ?, {', '.join('?' * len(cols))}, 1, ?, datetime('now'))
                    ON CONFLICT(season, competition_code) DO UPDATE SET
                    {', '.join(f'{c}=excluded.{c}' for c in cols)}, is_final=1,
                    source=excluded.source, updated_at=excluded.updated_at""",
                [r["season"], r["competition_code"], *vals, f"wikipedia:{rev}"])
            if old:
                upd += 1
            else:
                new += 1
        log.rows = new + upd
        log.api_calls = 1
        log.message = f"rev={rev} new={new} updated={upd}"
        if dry:
            con.rollback()
        else:
            con.commit()
    print(f"OK - 시즌 기록 {'점검(dry-run)' if dry else '저장'}: 신규 {new} · 갱신 {upd}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
