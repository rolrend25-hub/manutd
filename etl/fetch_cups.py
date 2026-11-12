"""FA컵·EFL컵·커뮤니티실드 경기 수집 — 위키백과 '<시즌> Manchester United F.C. season' 문서의 컵 대회 표.

사용법:
    python etl/fetch_cups.py                 # 현재 시즌
    python etl/fetch_cups.py --season 2025   # 특정 시즌 (시작 연도)

* football-data 무료 플랜에 없는 국내 컵 대회 보완용. 출처: 위키백과 (CC BY-SA 4.0)
* 시즌 문서 표에는 킥오프 '시각'이 없음 → 대회 문서('<시즌> FA Cup' / '<시즌> EFL Cup' / '<연도> FA Community Shield')의
  경기 박스에서 날짜·시각(BST/GMT)을 찾아 채움 → kickoff_confirmed=1 (캘린더 시간 일정, 카톡 리마인드 발송)
  못 찾으면 kickoff_confirmed=0 (캘린더 종일 일정, 리마인드 없음). 시간 확정·변경은 카톡 안내(KICKOFF_CHANGE) 대기열
* 경기 식별: matches.match_ext_id = 'wiki:<시즌>:<대회>:<라운드>'
* 득점자(분 포함)는 맨유 득점만 표에 있음 → match_events(goal / 상대 자책골)로 저장
"""
import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import SyncLog, connect, season_label, utc_now  # noqa: E402
from fetch_fixtures import queue_schedule_notice  # noqa: E402
import wiki  # noqa: E402

LONDON = ZoneInfo("Europe/London")
HEADINGS = {"FA Cup": "FAC", "EFL Cup": "ELC", "League Cup": "ELC", "FA Community Shield": "CS"}
HOME_VENUE = "Old Trafford"
PLACEHOLDER_HOUR = 15  # 시각 미정 경기의 임시 킥오프 (영국 시간)


def ensure_schema(con) -> None:
    cols = {r[1] for r in con.execute("PRAGMA table_info(matches)")}
    if "match_ext_id" not in cols:
        con.execute("ALTER TABLE matches ADD COLUMN match_ext_id TEXT")
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_matches_ext ON matches(match_ext_id)")
        print("  DB: matches.match_ext_id 칸 추가")


def norm(name: str) -> str:
    n = re.sub(r"\b(A\.?F\.?C|F\.?C)\.?$", "", name.strip(), flags=re.I)
    return re.sub(r"[^a-z0-9]", "", n.lower().replace("&", "and"))


def find_team(con, name: str) -> tuple[int, str]:
    """위키 팀 이름 → (teams.id, 표시 이름). 기존 팀(football-data)과 이름이 같으면 그 팀 사용."""
    key = norm(name)
    for t in con.execute("SELECT id, name, short_name FROM teams"):
        if key in (norm(t["name"] or ""), norm(t["short_name"] or "")):
            return t["id"], t["short_name"] or t["name"]
    cur = con.execute("INSERT INTO teams (name, short_name) VALUES (?, ?)", (name, name))
    return cur.lastrowid, name


def parse_date(text: str) -> datetime | None:
    m = re.search(r"(\d{1,2})(?:/\d{1,2})?\s+([A-Z][a-z]+)\s+(\d{4})", text)
    if not m:
        return None
    d = datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%d %B %Y")
    return d.replace(hour=PLACEHOLDER_HOUR, tzinfo=LONDON).astimezone(timezone.utc)


def parse_scorers(text: str) -> list[dict]:
    """"Mbeumo 75', Maguire 89'" / "Fernandes 12', 55' (pen.)" / "Smith 30' (o.g.)" → 이벤트 목록."""
    out, last = [], None
    for part in re.split(r",\s*|\n", text):
        part = part.strip()
        if not part:
            continue
        mins = re.findall(r"(\d+)(?:\+(\d+))?\s*'", part)
        name = re.sub(r"\d+(\+\d+)?\s*'|\((pen\.?|p|o\.?g\.?)\)|\bpen\.?|\bo\.?g\.?", "", part).strip(" ,()")
        name = name or last
        if not name:
            continue
        last = name
        og = bool(re.search(r"o\.?g\.?", part))
        pen = bool(re.search(r"\bpen\.?|\(p\)", part))
        for mm, extra in mins or [(None, None)]:
            out.append({"team_side": "OPP" if og else "MU", "event_type": "own_goal" if og else "goal",
                        "player_name": name, "minute": int(mm) if mm else None,
                        "extra_minute": int(extra) if extra else None, "detail": "pen" if pen else None})
    return out


def parse_tables(page: str, season: str) -> list[dict]:
    out = []
    for t in wiki.tables(page):
        code = HEADINGS.get(t["heading"])
        if not code or not t["rows"] or [c["text"] for c in t["rows"][0]][:3] != ["Date", "Round", "Opponents"]:
            continue
        head = [c["text"].split("\n")[0] for c in t["rows"][0]]
        idx = {h: i for i, h in enumerate(head)}
        for r in t["rows"][1:]:
            cell = lambda h: r[idx[h]] if h in idx and idx[h] < len(r) else {"text": "", "links": []}  # noqa: E731
            opp_cell = cell("Opponents")
            opp = (opp_cell["links"][0] if opp_cell["links"] else opp_cell["text"]).strip()
            if not opp:
                continue  # 상대 미정 (추첨 전)
            ko = parse_date(cell("Date")["text"])
            if not ko:
                continue
            res = wiki.clean(cell("Result").get("text", ""))
            sc = re.search(r"(\d+)\s*[–-]\s*(\d+)", res)
            pens = re.search(r"\((\d+)\s*[–-]\s*(\d+)\s*p", res)
            ha = cell("H / A")["text"].strip().upper()[:1] or "N"
            rnd = wiki.clean(cell("Round")["text"])
            out.append({
                "code": code, "round": rnd, "kickoff": ko, "opp": re.sub(r"\s+(A\.?F\.?C|F\.?C)\.?$", "", opp),
                "home_away": ha if ha in ("H", "A", "N") else "N",
                "mu": int(sc.group(1)) if sc else None, "op": int(sc.group(2)) if sc else None,
                "mu_pens": int(pens.group(1)) if pens else None, "op_pens": int(pens.group(2)) if pens else None,
                "attendance": wiki.to_int(cell("Attendance")["text"]),
                "events": parse_scorers(wiki.clean(cell("Scorers")["text"])) if sc else [],
                "ext_id": f"wiki:{season}:{code}:{rnd}",
            })
    return out


ZONES = {"BST": LONDON, "GMT": LONDON, "UTC": timezone.utc, "CET": ZoneInfo("Europe/Paris"),
         "CEST": ZoneInfo("Europe/Paris")}
BOX_SPLIT = re.compile(r'<div class="vevent"|<div[^>]*class="footballbox"')


def cup_articles(start: int, codes: set) -> dict:
    yy = f"{start}–{(start + 1) % 100:02d}"
    titles = {"FAC": f"{yy} FA Cup", "ELC": f"{yy} EFL Cup", "CS": f"{start} FA Community Shield"}
    return {c: titles[c] for c in codes if c in titles}


def cup_kickoffs(start: int, codes: set) -> tuple[dict, int]:
    """대회 문서 경기 박스 → {(대회, 영국 날짜 'YYYY-MM-DD'): 킥오프 UTC datetime} (맨유 경기만), 요청 수."""
    out, calls = {}, 0
    for code, title in cup_articles(start, codes).items():
        try:
            page, _ = wiki.page_html(title)
            calls += 1
        except RuntimeError as e:
            print(f"  (킥오프 시각) {title} 문서 없음/오류 → 건너뜀: {str(e)[:80]}")
            continue
        found = 0
        parts = BOX_SPLIT.split(page)[1:]
        for chunk in parts:
            text = wiki.clean(re.sub(r"<[^>]+>", " ", chunk[:6000]))
            text = re.sub(r"\s+", " ", text)
            if "Manchester United" not in text:
                continue
            d = re.search(r"(\d{1,2}) ([A-Z][a-z]+) (\d{4})", text)
            t = re.search(r"\b(\d{1,2}):(\d{2})\s*(BST|GMT|UTC|CEST|CET)\b", text)
            if not (d and t):
                continue
            try:
                day = datetime.strptime(" ".join(d.groups()), "%d %B %Y")
            except ValueError:
                continue
            local = day.replace(hour=int(t.group(1)), minute=int(t.group(2)), tzinfo=ZONES[t.group(3)])
            out[(code, local.astimezone(LONDON).date().isoformat())] = local.astimezone(timezone.utc)
            found += 1
        print(f"  (킥오프 시각) {title}: 맨유 경기 시각 {found}개")
    return out, calls


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int)
    args = ap.parse_args()
    con = connect()
    ensure_schema(con)
    start = args.season or con.execute("SELECT start_year FROM seasons WHERE is_current=1").fetchone()[0]
    season = season_label(start)
    title = f"{start}–{(start + 1) % 100:02d} Manchester United F.C. season"
    page, rev = wiki.page_html(title)
    rows = parse_tables(page, season)
    print(f"[위키백과] {title} (rev {rev}) → 컵 경기 {len(rows)}개")

    now = datetime.now(timezone.utc)
    times, calls = cup_kickoffs(start, {r["code"] for r in rows})
    with SyncLog(con, "wikipedia", f"cups {season}") as log:
        log.api_calls = 1 + calls
        con.execute("INSERT OR IGNORE INTO seasons (season, start_year) VALUES (?, ?)", (season, start))
        for r in rows:
            team_id, opp_name = find_team(con, r["opp"])
            done = r["mu"] is not None
            mu_g, op_g = r["mu"], r["op"]
            # 검증: 맨유 득점 이벤트 수 = 맨유 스코어 (다르면 이벤트는 저장하지 않음)
            n_ev = len(r["events"])
            if done and n_ev and n_ev != mu_g:
                print(f"  ⚠ {r['ext_id']} 득점자 {n_ev}명 ≠ 스코어 {mu_g} → 득점자 생략")
                r["events"] = []
            ko = times.get((r["code"], r["kickoff"].astimezone(LONDON).date().isoformat()))
            row = {
                "season": season, "competition_code": r["code"], "stage": r["round"], "matchday": None,
                "kickoff_utc": (ko or r["kickoff"]).strftime("%Y-%m-%dT%H:%M:%SZ"), "kickoff_confirmed": 1 if ko else 0,
                "home_away": r["home_away"], "opponent_id": team_id, "opponent_name": opp_name,
                "venue": HOME_VENUE if r["home_away"] == "H" else None,
                "status": "FINISHED" if done else "SCHEDULED",
                "mu_score": mu_g, "opp_score": op_g, "mu_pens": r["mu_pens"], "opp_pens": r["op_pens"],
                "result": (None if not done else "W" if mu_g > op_g else "L" if mu_g < op_g else "D"),
                "attendance": r["attendance"], "details_synced": 1 if done else 0, "match_ext_id": r["ext_id"],
            }
            if done and r["kickoff"] > now:
                print(f"  ⚠ {r['ext_id']} 미래 날짜인데 스코어 있음 → 건너뜀")
                continue
            old = con.execute("SELECT * FROM matches WHERE match_ext_id=?", (r["ext_id"],)).fetchone()
            cols = list(row)
            if old is None:
                cur = con.execute(f"INSERT INTO matches ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                                  [row[c] for c in cols])
                mid, state = cur.lastrowid, "신규"
            else:
                mid = old["id"]
                changed = [c for c in cols if old[c] != row[c]]
                if changed:
                    queue_schedule_notice(con, old, row)  # 다가오는 경기 시간 확정·변경 → 카톡 안내
                state = "변경" if changed else "동일"
                if changed:
                    con.execute(f"UPDATE matches SET {', '.join(f'{c}=?' for c in changed)}, updated_at=? WHERE id=?",
                                [row[c] for c in changed] + [utc_now(), mid])
            con.execute("DELETE FROM match_events WHERE match_id=?", (mid,))
            for e in r["events"]:
                con.execute("""INSERT INTO match_events (match_id, minute, extra_minute, team_side, event_type,
                               player_name, detail) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                            (mid, e["minute"], e["extra_minute"], e["team_side"], e["event_type"],
                             e["player_name"], e["detail"]))
            score = f"{mu_g}-{op_g}" + (f" (PK {r['mu_pens']}-{r['op_pens']})" if r["mu_pens"] is not None else "") if done else "예정"
            print(f"  {state} {r['code']:<3} {r['round']:<14} {row['kickoff_utc'][:16] if ko else row['kickoff_utc'][:10] + ' (시각 미정)'} {r['home_away']} vs {opp_name:<22} {score}"
                  + (f"  득점: {', '.join(e['player_name'] for e in r['events'])}" if r["events"] else ""))
            if state != "동일":
                log.rows += 1
        log.message = f"rev={rev} {season} cups={len(rows)}"
        con.commit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
