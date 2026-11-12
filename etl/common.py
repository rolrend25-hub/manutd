"""ETL 공용 함수: .env 로드, HTTP(JSON) 요청, DB 연결, sync_log 기록."""
import json
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "manutd.db"
USER_AGENT = "mufc-fan-site/0.1"

MUFC_FD = 66  # football-data.org 맨유 team id


def load_env() -> dict:
    """프로젝트 루트 .env 를 읽고, 실제 환경변수(GitHub Actions 시크릿 등)가 있으면 그 값을 우선."""
    import os
    env = {}
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    for k, v in os.environ.items():
        if v:
            env[k] = v
    return env


def get_json(url: str, headers: dict | None = None, retries: int = 3) -> dict:
    """GET → JSON. 429(요청 한도) 이면 잠시 대기 후 재시도."""
    req = urllib.request.Request(url, headers={**(headers or {}), "User-Agent": USER_AGENT})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries - 1:
                wait = int(e.headers.get("X-RequestCounter-Reset", "60") or 60)
                print(f"  요청 한도 초과 → {wait}초 대기 후 재시도")
                time.sleep(wait + 1)
                continue
            body = e.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(f"HTTP {e.code} {url}: {body}") from None
    raise RuntimeError(f"재시도 실패: {url}")


def connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        sys.exit(f"DB 가 없습니다: {DB_PATH}\n먼저 python db/init_db.py 실행")
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def name_tokens(name: str) -> list[str]:
    """'Benjamin Šeško' → ['benjamin', 'sesko'] (악센트·기호 제거, 소문자, 'Sir' 등 호칭 제거)."""
    import re
    import unicodedata
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\(.*?\)", " ", s)
    return [t for t in re.split(r"[^a-z]+", s) if t and t not in ("sir", "jr", "junior")]


def names_match(a: str, b: str) -> bool:
    """같은 사람인지 느슨하게 비교. 'Andrey Santos' ≈ 'Andrey Nascimento dos Santos', 'Diogo Dalot' ≈ 'Diogo Dalot Teixeira'.
    한 단어 이름(Casemiro 등)은 완전히 같을 때만 인정."""
    ta, tb = name_tokens(a), name_tokens(b)
    if not ta or not tb:
        return False
    if ta == tb:
        return True
    short, long_ = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    return len(short) >= 2 and set(short) <= set(long_)


def season_label(start_year: int) -> str:
    return f"{start_year}-{(start_year + 1) % 100:02d}"


class SyncLog:
    """with SyncLog(con, 'football-data', 'fixtures') as log: ... log.rows += n"""

    def __init__(self, con, source: str, job: str):
        self.con, self.source, self.job = con, source, job
        self.rows = 0
        self.api_calls = 0
        self.message = ""

    def __enter__(self):
        cur = self.con.execute(
            "INSERT INTO sync_log (source, job, started_utc) VALUES (?, ?, ?)",
            (self.source, self.job, utc_now()))
        self.id = cur.lastrowid
        self.con.commit()
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type:
            self.con.rollback()
        status = "error" if exc_type else "ok"
        msg = f"{exc_type.__name__}: {exc}" if exc_type else self.message
        self.con.execute(
            "UPDATE sync_log SET finished_utc=?, status=?, rows_upserted=?, api_calls=?, message=? "
            "WHERE id=?",
            (utc_now(), status, self.rows, self.api_calls, msg[:1000], self.id))
        self.con.commit()
        return False  # 예외는 그대로 전달
