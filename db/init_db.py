"""DB 생성 스크립트.

사용법:
    python db/init_db.py            # data/manutd.db 가 없으면 생성 + 초기 데이터 입력
    python db/init_db.py --reset    # 기존 DB 삭제 후 다시 생성
"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "manutd.db"
SCHEMA = Path(__file__).with_name("schema.sql")
SEED = Path(__file__).with_name("seed.sql")


def main() -> None:
    reset = "--reset" in sys.argv
    if reset and DB_PATH.exists():
        DB_PATH.unlink()
    is_new = not DB_PATH.exists()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    con = sqlite3.connect(DB_PATH)
    try:
        con.executescript(SCHEMA.read_text(encoding="utf-8"))
        if is_new:
            con.executescript(SEED.read_text(encoding="utf-8"))
        con.commit()

        print(f"DB: {DB_PATH} ({'created' if is_new else 'schema checked'})")
        for table in ("seasons", "competitions", "season_standings", "honours",
                      "managers", "history_timeline"):
            n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"  {table:<18} {n:>4} rows")
        print("  honours by competition:")
        for code, name, cnt in con.execute("SELECT * FROM v_honours_count"):
            print(f"    {code:<5} {name:<35} {cnt}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
