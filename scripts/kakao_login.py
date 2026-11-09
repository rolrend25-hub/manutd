"""카카오 최초 로그인 (1회): 브라우저로 로그인 → 리프레시 토큰을 .env 에 저장 → 시험 메시지 전송.

사용법
  python scripts/kakao_login.py
      브라우저가 열리면 카카오 로그인·동의. Redirect URI 가 localhost 면 자동으로 받아 처리.
  python scripts/kakao_login.py --code <인가코드>
      Redirect URI 가 localhost 가 아닐 때: 로그인 후 주소창의 ...?code=XXXX 값을 붙여 실행

Redirect URI 는 .env 의 KAKAO_REDIRECT_URI (없으면 http://localhost:8765/callback).
카카오 개발자 콘솔 > 내 애플리케이션 > 카카오 로그인 > Redirect URI 에 똑같이 등록돼 있어야 함.

끝나면 GitHub 저장소 Secrets 의 KAKAO_REFRESH_TOKEN 에 같은 값을 넣어야 자동화 로봇이 사용 가능
(값은 화면에 출력하지 않음 → .env 파일에서 복사).
"""
import argparse
import http.server
import sys
import urllib.parse
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "etl"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "notify"))
from common import load_env  # noqa: E402
import kakao  # noqa: E402

DEFAULT_REDIRECT = "http://localhost:8765/callback"


def wait_for_code(redirect_uri: str, url: str) -> str:
    u = urllib.parse.urlparse(redirect_uri)
    got = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            got.update({k: v[0] for k, v in q.items()})
            ok = "code" in q
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            msg = "카카오 로그인 완료. 이 창을 닫고 터미널로 돌아가세요." if ok else f"로그인 실패: {got}"
            self.wfile.write(f"<h2>{msg}</h2>".encode("utf-8"))

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer((u.hostname, u.port or 80), Handler)
    print("브라우저에서 카카오 로그인·동의를 진행하세요. (창이 안 열리면 아래 주소를 직접 여세요)")
    print(f"  {url}")
    webbrowser.open(url)
    while "code" not in got and "error" not in got:
        srv.handle_request()
    srv.server_close()
    if "code" not in got:
        sys.exit(f"로그인 실패: {got.get('error')} {got.get('error_description', '')}")
    return got["code"]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--code", help="인가 코드 (Redirect URI 가 localhost 가 아닐 때)")
    args = ap.parse_args()

    env = load_env()
    if not env.get("KAKAO_REST_API_KEY"):
        sys.exit(".env 에 KAKAO_REST_API_KEY 가 없습니다.")
    redirect = env.get("KAKAO_REDIRECT_URI") or DEFAULT_REDIRECT
    url = kakao.authorize_url(env["KAKAO_REST_API_KEY"], redirect)

    if args.code:
        code = args.code
    elif urllib.parse.urlparse(redirect).hostname in ("localhost", "127.0.0.1"):
        code = wait_for_code(redirect, url)
    else:
        print("Redirect URI 가 localhost 가 아니므로 직접 진행해야 합니다:")
        print(f"  1) 브라우저에서 열기: {url}")
        print(f"  2) 로그인 후 이동한 주소({redirect}?code=...)의 code 값을 복사")
        print("  3) python scripts/kakao_login.py --code <복사한 값>")
        return

    tok = kakao.exchange_code(env, code, redirect)
    if "talk_message" not in (tok.get("scope") or ""):
        print(f"⚠ 동의 범위에 talk_message 가 없습니다 (scope={tok.get('scope')}). 동의항목 설정을 확인하세요.")
    kakao.save_refresh_token(tok["refresh_token"])
    days = int(tok.get("refresh_token_expires_in", 0)) // 86400
    print(f"OK - 리프레시 토큰을 .env 에 저장했습니다 (만료 약 {days}일 후, 이후 자동 갱신)")

    kakao.send_memo(tok["access_token"], "✅ 맨유 팬 사이트 카카오톡 알림 연결 완료\n경기 전날·1시간 전 알림과 경기 시간 변경 안내가 이 채팅으로 옵니다.",
                    button="사이트 열기")
    print("OK - 카카오톡 '나와의 채팅'으로 시험 메시지를 보냈습니다.")
    print("다음: GitHub 저장소 Settings > Secrets and variables > Actions 에서 KAKAO_REFRESH_TOKEN 을 .env 값으로 등록")


if __name__ == "__main__":
    main()
