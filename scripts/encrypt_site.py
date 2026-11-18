"""배포용 사이트를 비밀번호로 잠근다 (GitHub Pages 에는 비밀번호 기능이 없어서 데이터를 암호화).

사용: SITE_PASSWORD=... python scripts/encrypt_site.py site <출력 폴더>

- site/ 를 출력 폴더로 복사한 뒤 data/data.js·archive.js·data.json(평문)을 지우고
  AES-256-GCM 으로 암호화한 data/data.enc·archive.enc 만 남긴다.
- 키 = PBKDF2-SHA256(비밀번호, SALT, ITER) — site/assets/gate.js 와 값이 같아야 한다.
- index.html 의 data.js·app.js 태그를 gate.js 로 바꾼다 (비밀번호 확인 후 gate.js 가 app.js 를 불러옴).
- 비밀번호가 없으면 실패(종료 코드 1) → 평문 사이트가 배포되지 않는다.
"""
import base64
import json
import os
import re
import shutil
import sys
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

SALT = b"manutd-site-gate-v1"
ITER = 310_000
MIN_LEN = 10

ORIG_TAGS = '<script src="data/data.js"></script>\n<script src="assets/app.js"></script>'
GATE_TAG = '<script src="assets/gate.js"></script>'


def derive_key(password: str) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=SALT, iterations=ITER)
    return kdf.derive(password.encode("utf-8"))


def js_to_json(path: Path, var: str) -> str:
    """'window.VAR={...};' → '{...}' (JSON 인지 확인)"""
    text = path.read_text(encoding="utf-8").strip()
    m = re.fullmatch(r"window\." + var + r"\s*=\s*(.*?);?", text, re.S)
    if not m:
        sys.exit(f"✗ {path} 형식이 예상과 다름 (window.{var}=...)")
    body = m.group(1)
    json.loads(body)
    return body


def encrypt(key: bytes, plain: str) -> str:
    iv = os.urandom(12)
    ct = AESGCM(key).encrypt(iv, plain.encode("utf-8"), None)
    return base64.b64encode(iv + ct).decode("ascii")


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    password = os.environ.get("SITE_PASSWORD", "")
    if not password:
        sys.exit("✗ SITE_PASSWORD 가 비어 있음 — 저장소 Secrets 에 등록 필요. 평문 사이트는 배포하지 않음")
    if len(password) < MIN_LEN:
        sys.exit(f"✗ SITE_PASSWORD 가 너무 짧음 ({MIN_LEN}자 이상)")

    key = derive_key(password)
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(src, out)

    data = out / "data"
    (data / "data.enc").write_text(encrypt(key, js_to_json(data / "data.js", "MUFC_DATA")), encoding="ascii")
    if (data / "archive.js").exists():
        (data / "archive.enc").write_text(encrypt(key, js_to_json(data / "archive.js", "MUFC_ARCHIVE")), encoding="ascii")
    for name in ("data.js", "data.json", "archive.js"):
        (data / name).unlink(missing_ok=True)

    index = out / "index.html"
    html = index.read_text(encoding="utf-8")
    if ORIG_TAGS not in html:
        sys.exit("✗ index.html 에서 data.js/app.js 스크립트 태그를 찾지 못함")
    index.write_text(html.replace(ORIG_TAGS, GATE_TAG), encoding="utf-8")

    # 평문 데이터가 하나라도 남아 있으면 실패
    leftovers = [p for p in out.rglob("*") if p.suffix in (".js", ".json") and p.parent.name == "data"]
    if leftovers:
        sys.exit(f"✗ 평문 데이터가 남아 있음: {leftovers}")
    print(f"✓ 사이트 암호화 완료 → {out}")


if __name__ == "__main__":
    main()
