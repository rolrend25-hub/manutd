"""GitHub Actions 마지막 단계: 점검 결과를 사용자에게 알림.

- 실패/경고가 있으면 'auto-alert' 라벨 이슈를 만들고 저장소 소유자에게 할당
  → GitHub 이메일 + GitHub 모바일 앱 푸시로 알림
  (같은 내용이 반복되면 새 알림을 만들지 않음, 내용이 바뀌면 댓글 추가)
- 모두 정상이면 열려 있는 알림 이슈를 '정상 복구' 댓글과 함께 닫음
- 카톡 '나에게 보내기'로도 알림 (2026-11-15): 새 문제 발생·내용 변경·정상 복구 때만 1회.
  같은 문제가 계속되는 동안은 다시 보내지 않음. 카톡 전송이 실패해도 GitHub 이슈 알림은 그대로 (실행 실패로 보지 않음)

환경변수: GITHUB_TOKEN, GITHUB_REPOSITORY, GITHUB_REPOSITORY_OWNER, GITHUB_RUN_ID, GITHUB_SERVER_URL,
          REPORT_DIR (각 점검 출력 .txt), OUT_<단계>=success|failure|skipped|cancelled
"""
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "etl"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "notify"))

API = "https://api.github.com"
LABEL = "auto-alert"
STEPS = [  # (환경변수, 이름)
    ("OUT_PRIVACY", "개인정보·비밀값 검사 (저장소 전체)"),
    ("OUT_SOURCES", "API 사전 점검"),
    ("OUT_ETL", "데이터 수집(ETL)"),
    ("OUT_KAKAO", "카카오톡 알림 발송"),
    ("OUT_VALIDATE", "데이터 검증"),
    ("OUT_STAGED", "개인정보·비밀값 검사 (커밋 직전)"),
    ("OUT_COMMIT", "커밋·푸시"),
    ("OUT_CALENDAR", "구글 캘린더 동기화"),
    ("OUT_ENCRYPT", "사이트 비밀번호 잠금 (SITE_PASSWORD 확인)"),
]


def gh(method: str, path: str, body=None):
    req = urllib.request.Request(
        f"{API}{path}", method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
                 "Accept": "application/vnd.github+json", "User-Agent": "mufc-fan-site"})
    with urllib.request.urlopen(req, timeout=30) as r:
        txt = r.read().decode()
        return json.loads(txt) if txt else None


def kakao(text: str) -> None:
    """오류 알림 카톡. 실패해도 예외를 밖으로 내지 않음 (GitHub 이슈가 기본 알림 경로)."""
    try:
        from common import load_env
        import kakao as kk
        env = load_env()
        if not env.get("KAKAO_REFRESH_TOKEN"):
            print("카톡 알림 건너뜀 (카카오 토큰 없음)")
            return
        kk.send_memo(kk.access_token(env), text, button="사이트 열기")
        print("카톡 오류 알림 전송")
    except Exception as e:  # noqa: BLE001
        print(f"카톡 오류 알림 실패 (GitHub 이슈로만 알림): {str(e)[:150]}")


def kakao_text(title: str, failed: list, lines: list, number) -> str:
    head = title.replace("**", "")
    body = [f"[맨유 사이트] {head}"]
    body += [f"✗ {n}" for n in failed[:3]]
    body += [ln[:70] for ln in lines[:3]]
    if len(failed) + len(lines) > 6:
        body.append(f"외 {len(failed) + len(lines) - 6}건")
    body.append(f"GitHub 이슈 #{number} 확인")
    return "\n".join(body)


def main() -> int:
    repo = os.environ["GITHUB_REPOSITORY"]
    owner = os.environ.get("GITHUB_REPOSITORY_OWNER", repo.split("/")[0])
    run_url = f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{repo}/actions/runs/{os.environ.get('GITHUB_RUN_ID')}"

    failed = [name for key, name in STEPS if os.environ.get(key) in ("failure", "cancelled")]
    reports = []
    rdir = Path(os.environ.get("REPORT_DIR", "."))
    for f in sorted(rdir.glob("*.txt")):
        reports.append((f.stem, f.read_text(encoding="utf-8", errors="replace")))
    problem_lines = [ln.strip() for _, t in reports for ln in t.splitlines() if ln.strip().startswith(("✗", "⚠"))]
    warn_only = not failed and problem_lines

    open_issues = gh("GET", f"/repos/{repo}/issues?state=open&labels={LABEL}&per_page=20") or []

    if not failed and not problem_lines:
        for iss in open_issues:
            gh("POST", f"/repos/{repo}/issues/{iss['number']}/comments",
               {"body": f"✅ 정상 복구 — 모든 점검 통과\n\n실행 기록: {run_url}"})
            gh("PATCH", f"/repos/{repo}/issues/{iss['number']}", {"state": "closed"})
            print(f"알림 이슈 #{iss['number']} 닫음 (정상 복구)")
        if open_issues:
            kakao(f"[맨유 사이트] ✅ 정상 복구\n자동 점검이 모두 통과했습니다. (이슈 #{open_issues[0]['number']} 닫음)")
        print("모든 점검 통과" + (" — 복구 알림 전송" if open_issues else " — 알림 없음"))
        return 0

    privacy = any("개인정보" in n for n in failed)
    title = ("🔒 [긴급] 개인정보·비밀값 검사 실패 — 커밋 차단됨" if privacy else
             "🚨 자동 동기화 점검 실패 — 사이트 갱신 중단" if failed else
             "⚠ 자동 동기화 경고 — 확인 필요")
    fingerprint = hashlib.sha1(("|".join(failed) + "\n" + "\n".join(problem_lines)).encode()).hexdigest()[:12]
    body = [f"**{title}**", ""]
    if failed:
        body += ["실패한 단계:", *[f"- ✗ {n}" for n in failed], ""]
    if problem_lines:
        body += ["점검 결과:", "```", *problem_lines[:60], "```", ""]
    if privacy:
        body += ["> 공개되면 안 되는 값이 감지되어 **커밋·배포를 중단**했습니다. "
                 "이미 push 된 커밋이라면 해당 키를 즉시 재발급(폐기)하세요.", ""]
    body += [f"실행 기록: {run_url}", "", f"<!-- fp:{fingerprint} -->"]
    text = "\n".join(body)

    if open_issues:
        iss = open_issues[0]
        last = gh("GET", f"/repos/{repo}/issues/{iss['number']}/comments?per_page=100") or []
        last_body = last[-1]["body"] if last else iss.get("body", "")
        if f"fp:{fingerprint}" in (last_body or ""):
            print(f"같은 문제 지속 중 — 이슈 #{iss['number']} 에 중복 알림 생략")
        else:
            gh("POST", f"/repos/{repo}/issues/{iss['number']}/comments", {"body": text})
            gh("PATCH", f"/repos/{repo}/issues/{iss['number']}", {"title": title})
            print(f"이슈 #{iss['number']} 에 새 내용 추가")
            kakao(kakao_text(title, failed, problem_lines, iss["number"]))
    else:
        try:
            gh("POST", f"/repos/{repo}/labels", {"name": LABEL, "color": "DA291C",
                                                 "description": "자동 점검 알림"})
        except urllib.error.HTTPError:
            pass  # 이미 있음
        iss = gh("POST", f"/repos/{repo}/issues",
                 {"title": title, "body": text, "labels": [LABEL], "assignees": [owner]})
        print(f"알림 이슈 생성 #{iss['number']} → {owner} 에게 할당")
        kakao(kakao_text(title, failed, problem_lines, iss["number"]))
    return 0 if warn_only else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
