"""개인정보·비밀값·미허가 파일 검사 (GitHub 공개 저장소 보호용).

사용법
  python scripts/check_privacy.py              # git 이 추적 중인 전체 파일 + DB 내용
  python scripts/check_privacy.py --staged     # 커밋 예정(staged) 파일만 (pre-commit 훅·Actions 커밋 직전)
  python scripts/check_privacy.py --history    # 모든 커밋 이력의 파일까지 (최초 push 전 1회)

검사 항목
  1. 금지 파일   : .env, 서비스 계정·OAuth 자격증명, 개인키 등은 어떤 경우에도 커밋 불가
  2. 허용 경로   : 정해진 폴더/파일 외에는 커밋 불가 (모르는 파일이 실수로 올라가는 것 차단)
  3. 미디어 승인 : 이미지·폰트·영상 등은 docs/approved_assets.txt 에 출처·권리를 적은 것만 허용
                   (구단 엠블럼·사진 등 허가 없는 저작물 업로드 차단)
  4. 내용 패턴   : API 키·토큰·개인키·서비스 계정 이메일·캘린더 ID·이메일 주소·전화번호·
                   주민등록번호·로컬 사용자 경로 등
  5. 실제 비밀값 : .env / 환경변수에 들어 있는 실제 키 값이 어디에든 그대로 들어갔는지 (정확 일치)
  6. DB 내용     : data/manutd.db 의 모든 텍스트 칸에 대해 4·5 검사

문제 발견 시 종료코드 1 (커밋·동기화 중단).
"""
import fnmatch
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APPROVED_ASSETS = ROOT / "docs" / "approved_assets.txt"

# 1. 절대 커밋하면 안 되는 파일
FORBIDDEN = [
    ".env", "*.env", ".env.*", "service-account*.json", "credentials*.json", "client_secret*.json",
    "token*.json", "*.pem", "*.key", "*.p12", "*.pfx", "id_rsa*", "id_ed25519*", "*.keystore",
    "kakao_token*", "*secret*",
]
FORBIDDEN_EXCEPT = {".env.example"}

# 2. 커밋 허용 경로
ALLOWED = [
    ".github/workflows/*.yml", ".githooks/*", ".gitignore", ".gitattributes", ".env.example",
    ".vscode/settings.json", "README.md", "requirements.txt",
    "db/*.sql", "db/*.py", "data/manutd.db",
    "etl/*.py", "scripts/*.py", "notify/*.py",
    "docs/*.md", "docs/*.txt", "docs/*/*.html", "docs/*/*.md", "docs/*/*.png",
    "site/index.html", "site/*.html", "site/assets/*.css", "site/assets/*.js", "site/assets/img/*",
    "site/data/data.json", "site/data/data.js",
]

MEDIA_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".bmp", ".tif", ".tiff",
             ".mp4", ".mov", ".webm", ".mp3", ".wav", ".ogg", ".woff", ".woff2", ".ttf", ".otf", ".pdf"}
BINARY_OK = MEDIA_EXT | {".db"}

# 4. 내용 패턴 (이름, 정규식)
PATTERNS = [
    ("개인키(PEM)", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ("Google API 키", r"AIza[0-9A-Za-z_\-]{35}"),
    ("Google OAuth 토큰", r"ya29\.[0-9A-Za-z_\-]{20,}"),
    ("Google OAuth 클라이언트 시크릿", r"GOCSPX-[0-9A-Za-z_\-]{20,}"),
    ("서비스 계정 이메일", r"[a-z0-9\-]+@[a-z0-9\-]+\.iam\.gserviceaccount\.com"),
    ("Google 캘린더 ID", r"[a-z0-9]{20,}@group\.calendar\.google\.com"),
    ("GitHub 토큰", r"\b(gh[pousr]_[0-9A-Za-z]{30,}|github_pat_[0-9A-Za-z_]{30,})"),
    ("JWT", r"\beyJ[0-9A-Za-z_\-]{10,}\.eyJ[0-9A-Za-z_\-]{10,}\.[0-9A-Za-z_\-]{10,}"),
    ("Slack/기타 토큰", r"\bxox[abpors]-[0-9A-Za-z\-]{10,}"),
    ("Anthropic API 키", r"\bsk-ant-[0-9A-Za-z_\-]{20,}"),
    ("키=값 형태 비밀값", r"(?i)\b(api[_-]?key|secret|token|password|passwd|refresh_token|access_token)"
                       r"\s*[:=]\s*['\"]?[0-9A-Za-z_\-\.]{16,}"),
    ("32자리 hex 토큰", r"(?<![0-9a-fA-F])[0-9a-f]{32}(?![0-9a-fA-F])"),
    ("이메일 주소", r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}"),
    ("휴대전화 번호", r"(?<!\d)01[016789][-. ]?\d{3,4}[-. ]?\d{4}(?!\d)"),
    ("주민등록번호", r"(?<!\d)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])-?[1-4]\d{6}(?!\d)"),
    ("로컬 사용자 경로", r"(?i)([A-Z]:\\\\?Users\\\\?[^\\\s\"']+|/Users/[^/\s\"']+|/home/[^/\s\"']+)"),
]
# 이메일 중 공개해도 되는 것
EMAIL_ALLOW = [
    r"[0-9]+\+[A-Za-z0-9\-]+@users\.noreply\.github\.com",   # GitHub noreply
    r"noreply@anthropic\.com",
    r"[^@\s]+@example\.(com|org)",
]
# 패턴 검사를 건너뛸 파일 (검사 규칙 자체를 담고 있는 파일)
SKIP_CONTENT = {"scripts/check_privacy.py"}

SECRET_ENV_KEYS = ("TOKEN", "KEY", "SECRET", "PASSWORD", "CALENDAR_ID")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", check=True).stdout


def match_any(path: str, patterns) -> bool:
    name = path.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatchcase(path, p) or fnmatch.fnmatchcase(name, p) for p in patterns)


def real_secret_values() -> dict[str, str]:
    """.env + 환경변수에서 비밀값(8자 이상)만 모음. 값 자체는 절대 출력하지 않음."""
    vals: dict[str, str] = {}
    env_file = ROOT / ".env"
    pairs = []
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                pairs.append((k.strip(), v.strip().strip('"').strip("'")))
    pairs += list(os.environ.items())
    for k, v in pairs:
        if any(s in k.upper() for s in SECRET_ENV_KEYS) and len(v) >= 8 and not k.startswith("GITHUB_"):
            vals[v] = k
    sa = ROOT / "service-account.json"
    if sa.exists():
        import json
        try:
            j = json.loads(sa.read_text(encoding="utf-8"))
            for f in ("private_key_id", "client_email", "client_id"):
                if j.get(f):
                    vals[str(j[f])] = f"service-account.{f}"
        except ValueError:
            pass
    return vals


def scan_text(label: str, text: str, secrets: dict[str, str]) -> list[str]:
    found = []
    for value, key in secrets.items():
        if value in text:
            found.append(f"{label}: 실제 비밀값({key}) 포함")
    for name, pat in PATTERNS:
        for m in re.finditer(pat, text):
            s = m.group(0)
            if name == "이메일 주소" and any(re.fullmatch(a, s) for a in EMAIL_ALLOW):
                continue
            line = text.count("\n", 0, m.start()) + 1
            shown = s[:4] + "…"  # Actions 로그도 공개되므로 값은 앞 4자만
            found.append(f"{label}:{line}: {name} 의심 ({shown})")
            break
    return found


def load_approved() -> set[str]:
    if not APPROVED_ASSETS.exists():
        return set()
    out = set()
    for line in APPROVED_ASSETS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.add(line.split("|", 1)[0].strip())
    return out


def check_files(paths: list[str], read, secrets) -> list[str]:
    problems = []
    approved = load_approved()
    for p in paths:
        ext = os.path.splitext(p)[1].lower()
        if match_any(p, FORBIDDEN) and p not in FORBIDDEN_EXCEPT:
            problems.append(f"{p}: 금지 파일 (비밀값/자격증명 파일은 커밋 불가)")
            continue
        if not match_any(p, ALLOWED):
            problems.append(f"{p}: 허용 목록에 없는 경로 (필요하면 scripts/check_privacy.py ALLOWED 에 추가 후 재검토)")
            continue
        if ext in MEDIA_EXT and p not in approved:
            problems.append(f"{p}: 승인되지 않은 미디어 파일 (docs/approved_assets.txt 에 출처·권리 기재 필요)")
        if p in SKIP_CONTENT:
            continue
        data = read(p)
        if data is None:
            continue
        if ext == ".db":
            problems += scan_db_bytes(p, data, secrets)
            continue
        if ext in BINARY_OK:
            text = data.decode("latin-1")
            problems += [x for x in scan_text(p, text, secrets) if "실제 비밀값" in x or "개인키" in x]
            continue
        problems += scan_text(p, data.decode("utf-8", "replace"), secrets)
    return problems


def scan_db_bytes(label: str, data: bytes, secrets) -> list[str]:
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "scan.db"
        f.write_bytes(data)
        con = sqlite3.connect(f)
        problems = []
        try:
            tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            for t in tables:
                cols = [r[1] for r in con.execute(f'PRAGMA table_info("{t}")')]
                for row in con.execute(f'SELECT * FROM "{t}"'):
                    for c, v in zip(cols, row):
                        if isinstance(v, str) and v:
                            for x in scan_text(f"{label}[{t}.{c}]", v, secrets):
                                problems.append(x.replace(":1:", ":"))
        finally:
            con.close()
        # 삭제된 페이지에 남은 잔여 데이터까지: 원본 바이트에서 실제 비밀값 검사
        raw = data.decode("latin-1")
        for value, key in secrets.items():
            if value in raw:
                problems.append(f"{label}: DB 바이너리에 실제 비밀값({key}) 잔존 (VACUUM 필요)")
        return sorted(set(problems))


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "--all"
    secrets = real_secret_values()
    problems: list[str] = []

    if mode == "--staged":
        paths = [p for p in git("diff", "--cached", "--name-only", "--diff-filter=ACMR").splitlines() if p]
        read = lambda p: subprocess.run(["git", "show", f":{p}"], cwd=ROOT, capture_output=True).stdout
        problems += check_files(paths, read, secrets)
    elif mode == "--history":
        commits = git("rev-list", "--all").split()
        seen: set[str] = set()
        for c in commits:
            for line in git("ls-tree", "-r", c).splitlines():
                meta, path = line.split("\t", 1)
                blob = meta.split()[2]
                if blob in seen:
                    continue
                seen.add(blob)
                read = lambda p, b=blob: subprocess.run(["git", "cat-file", "-p", b], cwd=ROOT,
                                                        capture_output=True).stdout
                problems += [f"[{c[:7]}] {x}" for x in check_files([path], read, secrets)]
        # 커밋 작성자 이메일
        for email in set(git("log", "--all", "--format=%ae%n%ce").split()):
            if not any(re.fullmatch(a, email) for a in EMAIL_ALLOW + [r"41898282\+github-actions\[bot\]@users\.noreply\.github\.com"]):
                problems.append(f"커밋 작성자 이메일이 공개됨: {email[:3]}… (GitHub noreply 이메일 사용 권장)")
    else:
        paths = [p for p in git("ls-files").splitlines() if p]
        read = lambda p: (ROOT / p).read_bytes() if (ROOT / p).exists() else None
        problems += check_files(paths, read, secrets)

    # git 설정 이메일 (다음 커밋에 들어갈 값)
    try:
        email = git("config", "user.email").strip()
        if email and not any(re.fullmatch(a, email) for a in EMAIL_ALLOW + [r"41898282\+github-actions\[bot\]@users\.noreply\.github\.com"]):
            problems.append(f"git user.email 이 개인 이메일로 보임: {email[:3]}… (커밋에 공개됨)")
    except subprocess.CalledProcessError:
        pass

    problems = sorted(set(problems))
    if problems:
        print(f"[개인정보·비밀값 검사] 실패 — {len(problems)}건")
        for p in problems:
            print("  ✗", p)
        return 1
    print(f"[개인정보·비밀값 검사] 통과 ({mode}, 비밀값 {len(secrets)}개 대조)")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
