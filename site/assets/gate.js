/* 비밀번호 잠금 (배포본 전용 — scripts/encrypt_site.py 가 index.html 에 이 파일을 넣는다).
   data/*.enc 는 AES-256-GCM, 키 = PBKDF2-SHA256(비밀번호, SALT, ITER). 값은 encrypt_site.py 와 같아야 한다.
   맞는 비밀번호면 키를 이 기기 localStorage 에 기억 (푸터 '잠그기'로 지움). */
(() => {
  const SALT = "manutd-site-gate-v1", ITER = 310000, STORE = "mufc_gate_key";
  const app = document.getElementById("app");
  const enc = new TextEncoder(), dec = new TextDecoder();
  const b64 = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
  const ub64 = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf)));
  const store = {
    get() { try { return localStorage.getItem(STORE); } catch (e) { return null; } },
    set(v) { try { localStorage.setItem(STORE, v); } catch (e) {} },
    clear() { try { localStorage.removeItem(STORE); } catch (e) {} },
  };

  async function deriveKey(password) {
    const base = await crypto.subtle.importKey("raw", enc.encode(password), "PBKDF2", false, ["deriveKey"]);
    return crypto.subtle.deriveKey(
      { name: "PBKDF2", hash: "SHA-256", salt: enc.encode(SALT), iterations: ITER },
      base, { name: "AES-GCM", length: 256 }, true, ["decrypt"]);
  }
  const importRaw = (raw) => crypto.subtle.importKey("raw", b64(raw), "AES-GCM", true, ["decrypt"]);

  async function fetchDecrypt(path, key) {
    const r = await fetch(path, { cache: "no-cache" });
    if (!r.ok) throw new Error("fetch " + r.status);
    const bytes = b64((await r.text()).trim());
    const plain = await crypto.subtle.decrypt({ name: "AES-GCM", iv: bytes.slice(0, 12) }, key, bytes.slice(12));
    return JSON.parse(dec.decode(plain));
  }

  function start(key) {
    window.MUFC_LOAD_ARCHIVE = () =>
      fetchDecrypt("data/archive.enc", key).then((a) => { window.MUFC_ARCHIVE = a; });
    const lock = document.createElement("p");
    lock.innerHTML = '<a href="#" id="gate-lock">잠그기 (이 기기에서 비밀번호 지우기)</a>';
    document.querySelector(".site-footer .wrap").appendChild(lock);
    lock.querySelector("a").addEventListener("click", (e) => { e.preventDefault(); store.clear(); location.reload(); });
    const s = document.createElement("script");
    s.src = "assets/app.js";
    document.body.appendChild(s);
  }

  async function unlock(key) {
    window.MUFC_DATA = await fetchDecrypt("data/data.enc", key);
    document.body.classList.remove("locked");
    start(key);
  }

  function showForm(msg) {
    document.body.classList.add("locked");
    app.innerHTML = `
      <form class="card gate" autocomplete="on">
        <h2>비밀번호</h2>
        <p class="muted">개인용 페이지입니다. 비밀번호를 입력하세요.</p>
        <input type="text" name="username" value="manutd" autocomplete="username" hidden>
        <input type="password" name="pw" autocomplete="current-password" aria-label="비밀번호" required autofocus>
        <label class="gate-remember"><input type="checkbox" name="remember" checked> 이 기기에서 기억하기</label>
        <button type="submit">들어가기</button>
        <p class="gate-msg" role="alert">${msg || ""}</p>
      </form>`;
    const form = app.querySelector("form");
    const msgEl = form.querySelector(".gate-msg");
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const btn = form.querySelector("button");
      btn.disabled = true; msgEl.textContent = "확인 중…";
      try {
        const key = await deriveKey(form.pw.value);
        await unlock(key);
        if (form.remember.checked) store.set(ub64(await crypto.subtle.exportKey("raw", key)));
      } catch (err) {
        btn.disabled = false;
        msgEl.textContent = err.name === "OperationError" ? "비밀번호가 맞지 않습니다." : "불러오지 못했습니다. 새로고침해 주세요.";
        form.pw.select();
      }
    });
  }

  if (!window.crypto || !crypto.subtle) {
    app.innerHTML = '<div class="card empty"><b>이 브라우저에서는 열 수 없습니다</b>HTTPS 주소로 접속해 주세요.</div>';
    return;
  }
  const saved = store.get();
  if (!saved) { showForm(); return; }
  importRaw(saved).then(unlock).catch((err) => {
    if (err.name === "OperationError" || err.name === "DataError") { store.clear(); showForm("비밀번호가 바뀌었습니다. 다시 입력하세요."); }
    else app.innerHTML = '<div class="card empty"><b>불러오지 못했습니다</b>새로고침해 주세요.</div>';
  });
})();
