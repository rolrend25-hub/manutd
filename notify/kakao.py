"""카카오톡 '나에게 보내기' 공용 함수 (STEP 3).

- 토큰: 리프레시 토큰(KAKAO_REFRESH_TOKEN) → 매 실행마다 액세스 토큰 발급
- 카카오는 리프레시 토큰 만료 1개월 전부터 갱신 요청 시 '새 리프레시 토큰'을 돌려줌 → 즉시 저장
    로컬            : .env 의 KAKAO_REFRESH_TOKEN 줄을 교체
    GitHub Actions  : 저장소 Secrets 의 KAKAO_REFRESH_TOKEN 을 교체 (GH_SECRETS_TOKEN 필요)
- 메시지: 텍스트 템플릿 (본문 최대 200자) + 버튼 1개(웹 링크)
"""
import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

from common import ROOT, USER_AGENT

AUTH = "https://kauth.kakao.com"
API = "https://kapi.kakao.com"
SITE = "https://rolrend25-hub.github.io/manutd/"
TEXT_LIMIT = 200


class KakaoError(RuntimeError):
    pass


def _post(url: str, data: dict, token: str | None = None) -> dict:
    headers = {"Content-Type": "application/x-www-form-urlencoded;charset=utf-8", "User-Agent": USER_AGENT}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        raise KakaoError(f"HTTP {e.code} {url}: {body}") from None


def authorize_url(rest_key: str, redirect_uri: str) -> str:
    q = urllib.parse.urlencode({"response_type": "code", "client_id": rest_key,
                                "redirect_uri": redirect_uri, "scope": "talk_message"})
    return f"{AUTH}/oauth/authorize?{q}"


def exchange_code(env: dict, code: str, redirect_uri: str) -> dict:
    return _post(f"{AUTH}/oauth/token", {
        "grant_type": "authorization_code", "client_id": env["KAKAO_REST_API_KEY"],
        "client_secret": env.get("KAKAO_CLIENT_SECRET", ""), "redirect_uri": redirect_uri, "code": code})


def access_token(env: dict) -> str:
    """리프레시 토큰으로 액세스 토큰 발급. 새 리프레시 토큰이 오면 저장까지 처리."""
    if not env.get("KAKAO_REFRESH_TOKEN"):
        raise KakaoError("KAKAO_REFRESH_TOKEN 이 없습니다. 먼저 python scripts/kakao_login.py 로 로그인하세요.")
    res = _post(f"{AUTH}/oauth/token", {
        "grant_type": "refresh_token", "client_id": env["KAKAO_REST_API_KEY"],
        "client_secret": env.get("KAKAO_CLIENT_SECRET", ""), "refresh_token": env["KAKAO_REFRESH_TOKEN"]})
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::add-mask::{res['access_token']}")
    new_rt = res.get("refresh_token")
    if new_rt and new_rt != env["KAKAO_REFRESH_TOKEN"]:
        days = int(res.get("refresh_token_expires_in", 0)) // 86400
        save_refresh_token(new_rt)
        env["KAKAO_REFRESH_TOKEN"] = new_rt
        print(f"  카카오 리프레시 토큰 갱신·저장 완료 (새 만료: 약 {days}일 후)")
    return res["access_token"]


def save_refresh_token(token: str) -> None:
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::add-mask::{token}")
        _update_github_secret("KAKAO_REFRESH_TOKEN", token)
    else:
        _update_env_file("KAKAO_REFRESH_TOKEN", token)


def _update_env_file(key: str, value: str) -> None:
    path = ROOT / ".env"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    line = f"{key}={value}"
    if re.search(rf"^{key}=.*$", text, flags=re.M):
        text = re.sub(rf"^{key}=.*$", lambda _: line, text, flags=re.M)
    else:
        text = text.rstrip("\n") + f"\n{line}\n"
    path.write_text(text, encoding="utf-8")


def _update_github_secret(name: str, value: str) -> None:
    """저장소 Actions 시크릿 교체. GH_SECRETS_TOKEN: 이 저장소 'Secrets: Read and write' 권한만 가진 개인 토큰."""
    from nacl import encoding, public

    pat = os.environ.get("GH_SECRETS_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not pat or not repo:
        raise KakaoError("새 카카오 리프레시 토큰을 받았지만 GH_SECRETS_TOKEN 이 없어 저장하지 못했습니다. "
                         "python scripts/kakao_login.py 로 다시 로그인해 시크릿을 교체하세요.")

    def gh(method, path, body=None):
        req = urllib.request.Request(
            f"https://api.github.com/repos/{repo}{path}", method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": f"Bearer {pat}", "Accept": "application/vnd.github+json",
                     "User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as r:
            t = r.read().decode()
            return json.loads(t) if t else None

    key = gh("GET", "/actions/secrets/public-key")
    box = public.SealedBox(public.PublicKey(key["key"].encode(), encoding.Base64Encoder()))
    enc = base64.b64encode(box.encrypt(value.encode())).decode()
    gh("PUT", f"/actions/secrets/{name}", {"encrypted_value": enc, "key_id": key["key_id"]})


def send_memo(token: str, text: str, link: str = SITE, button: str = "경기 페이지") -> None:
    if len(text) > TEXT_LIMIT:
        text = text[: TEXT_LIMIT - 1] + "…"
    template = {"object_type": "text", "text": text,
                "link": {"web_url": link, "mobile_web_url": link}, "button_title": button}
    res = _post(f"{API}/v2/api/talk/memo/default/send",
                {"template_object": json.dumps(template, ensure_ascii=False)}, token=token)
    if res.get("result_code") != 0:
        raise KakaoError(f"카카오 메시지 전송 실패: {res}")
