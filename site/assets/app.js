/* Red Devils Matchday — 정적 페이지. 데이터는 data/data.js (scripts/export_site_data.py 로 생성)
   표기 규칙 (2026-11-15 변경): 화면 문구는 모두 한글. 팀·선수·매체 이름은 원문(영문) 그대로. */
(() => {
  const D = window.MUFC_DATA;
  const app = document.getElementById("app");
  if (!D) {
    app.innerHTML = `<div class="card empty"><b>데이터 파일 없음</b>먼저 python scripts/export_site_data.py 를 실행하세요.</div>`;
    return;
  }

  // ---------- helpers ----------
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  // 대회명 (한글)
  const COMP_KO = { PL: "프리미어리그", UCL: "챔피언스리그", UEL: "유로파리그", UECL: "컨퍼런스리그", FAC: "FA컵", ELC: "EFL컵", CS: "커뮤니티실드" };
  const compKo = (c) => COMP_KO[c] || c;
  const fmt = (tz, opts, loc = "en-GB") => new Intl.DateTimeFormat(loc, { timeZone: tz, ...opts });
  const KST = "Asia/Seoul", UK = "Europe/London";
  // 한국식 날짜: "11/23 (월)" · "11/23 (월) 01:30"
  const parts = (iso, tz) => Object.fromEntries(fmt(tz, { month: "numeric", day: "numeric", weekday: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }, "ko-KR")
    .formatToParts(new Date(iso)).map((x) => [x.type, x.value]));
  const shortDate = (iso, tz) => { const p = parts(iso, tz); return `${p.month}/${p.day} (${p.weekday})`; };
  const dateTime = (iso, tz) => { const p = parts(iso, tz); return `${p.month}/${p.day} (${p.weekday}) ${p.hour}:${p.minute}`; };
  const hm = (iso, tz) => fmt(tz, { hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(new Date(iso));
  const monthKey = (iso) => fmt(KST, { year: "numeric", month: "long" }, "ko-KR").format(new Date(iso)); // 월 헤드라인(한글)
  const ukZone = (iso) => (fmt(UK, { timeZoneName: "short" }).format(new Date(iso)).includes("BST") ? "BST" : "GMT");
  const ord = (n) => `${n}위`;
  const crestImg = (url, alt) => (url ? `<img src="${esc(url)}" alt="${esc(alt)}" loading="lazy">` : "");
  const RES_KO = { W: "승", D: "무", L: "패" };
  const chip = (r) => `<span class="chip ${r || "pending"}">${RES_KO[r] || "-"}</span>`;
  const ha = (m) => (m.home_away === "H" ? "홈" : m.home_away === "A" ? "원정" : "중립");

  // 맨유 공식 엠블럼 (football-data 서버 이미지 링크, 불러오기 실패 시 'MU' 마크로 대체)
  const MU_CREST = D.mu_crest;
  const muCrest = (cls) => MU_CREST
    ? `<img class="${cls}" src="${esc(MU_CREST)}" alt="맨유 엠블럼" onerror="this.outerHTML='<span class=&quot;${cls} crest-fallback&quot;>MU</span>'">`
    : `<span class="${cls} crest-fallback">MU</span>`;
  const title = (t) => `<h1 class="page-title with-crest">${muCrest("title-crest")}<span>${t}</span></h1>`;

  // 킥오프 시각 미정(위키백과 컵 경기 등)이면 날짜만
  const koTime = (m, tz) => (m.kickoff_confirmed ? dateTime(m.kickoff_utc, tz) : `${shortDate(m.kickoff_utc, tz)} · 시간 미정`);
  const matches = D.matches.slice().sort((a, b) => a.kickoff_utc.localeCompare(b.kickoff_utc));
  const finished = matches.filter((m) => m.status === "FINISHED");
  // 지난 시즌 (data/archive.js — 일정·결과에서 지난 시즌을 고를 때만 불러옴)
  const ARCH_SEASONS = D.archive_seasons || [];
  let fixtureSeason = D.season, archiveState = window.MUFC_ARCHIVE ? "ready" : "none";
  const archMatches = () => (window.MUFC_ARCHIVE ? window.MUFC_ARCHIVE.matches : []);
  const detailsOf = (id) => (D.match_details || {})[String(id)] || ((window.MUFC_ARCHIVE || {}).match_details || {})[String(id)];
  function loadArchive() {
    if (archiveState !== "none" || !ARCH_SEASONS.length) return;
    archiveState = "loading";
    const s = document.createElement("script");
    s.src = "data/archive.js?v=" + encodeURIComponent(D.generated_utc || "");
    s.onload = () => { archiveState = "ready"; render(); };
    s.onerror = () => { archiveState = "error"; render(); };
    document.head.appendChild(s);
  }
  const now = Date.now();
  const upcoming = matches.filter((m) => m.status !== "FINISHED" && !["CANCELLED"].includes(m.status) && new Date(m.kickoff_utc).getTime() > now - 3 * 3600e3);
  const plRow = (D.tables.PL || []).find((r) => r.is_mu);
  const uclRow = (D.tables.UCL || []).find((r) => r.is_mu);

  // muFirst: 경기 목록에서는 홈/원정과 관계없이 맨유 점수를 앞에 (예: 헐 원정 0-2 패 → "0 - 2 L")
  function scoreText(m, muFirst) {
    if (m.mu_score == null) return "";
    const flip = !muFirst && m.home_away === "A";
    const [h, a] = flip ? [m.opp_score, m.mu_score] : [m.mu_score, m.opp_score];
    let s = `${h} - ${a}`;
    if (m.mu_pens != null) {
      const [hp, ap] = flip ? [m.opp_pens, m.mu_pens] : [m.mu_pens, m.opp_pens];
      s += ` <small class="small">(승부차기 ${hp}-${ap})</small>`;
    }
    return s;
  }

  function matchRow(m) {
    const done = m.status === "FINISHED";
    const live = m.status === "IN_PLAY" || m.status === "PAUSED";
    const right = done
      ? `<a class="score score-link" href="#match/${m.id}" title="맨유 점수 먼저 · 경기 상세">${scoreText(m, true)} ${chip(m.result)}<span class="more">상세 ›</span></a>`
      : `<div class="score"><div class="tbd">${m.status === "POSTPONED" ? "연기" : m.kickoff_confirmed ? `영국 ${hm(m.kickoff_utc, UK)}` : "미정"}<br>${live ? "<b style='color:var(--red)'>진행 중</b>" : ""}</div></div>`;
    return `<li class="match">
      <div class="when"><b>${shortDate(m.kickoff_utc, KST)}</b><span>${m.kickoff_confirmed ? `${hm(m.kickoff_utc, KST)}` : "시간 미정"}</span></div>
      <div class="who">${crestImg(m.opponent_crest, m.opponent)}
        <div style="min-width:0"><div class="opp">vs ${esc(m.opponent)}</div>
        <div class="sub"><span class="badge ${esc(m.comp)}">${esc(compKo(m.comp))}</span><span class="badge ha">${ha(m)}</span>${m.matchday ? `<span class="small muted">${m.comp === "PL" ? m.matchday + "R" : m.matchday + "차전"}</span>` : ""}</div></div>
      </div>
      ${right}
    </li>`;
  }

  // ---------- pages ----------
  function tickCountdown() {
    const el = document.getElementById("countdown");
    if (!el) return;
    const diff = new Date(el.dataset.kickoff).getTime() - Date.now();
    if (diff <= 0) { el.innerHTML = `<div style="min-width:auto;padding:8px 16px"><b style="font-size:22px">킥오프</b><span>경기 중 또는 결과 대기</span></div>`; return; }
    const d = Math.floor(diff / 864e5), h = Math.floor(diff / 36e5) % 24, mi = Math.floor(diff / 6e4) % 60, s = Math.floor(diff / 1e3) % 60;
    const p = (n) => String(n).padStart(2, "0");
    if (el.classList.contains("compact")) { el.innerHTML = `<b>D-${d}</b> ${p(h)}:${p(mi)}:${p(s)}`; return; }
    el.innerHTML = [[d, "일"], [p(h), "시간"], [p(mi), "분"], [p(s), "초"]].map(([v, l]) => `<div><b>${v}</b><span>${l}</span></div>`).join("");
  }

  // ----- 메인: 상단 다음 경기 바 + 매치 프리뷰(왼쪽) + 주요 뉴스(오른쪽) -----
  const koDT = (iso) => fmt(KST, { month: "numeric", day: "numeric", weekday: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }, "ko-KR").format(new Date(iso));
  const koD = (iso) => fmt(KST, { month: "numeric", day: "numeric", weekday: "short" }, "ko-KR").format(new Date(iso));
  const ago = (iso) => {
    const m = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 6e4));
    return m < 60 ? `${m}분 전` : m < 1440 ? `${Math.floor(m / 60)}시간 전` : `${Math.floor(m / 1440)}일 전`;
  };
  const COMP_SHORT = { PL: "PL", UCL: "UCL", UEL: "UEL", FAC: "FA컵", ELC: "EFL컵", CS: "실드", CHAMP: "챔피언십", PPL: "포르투갈", PD: "라리가", SA: "세리에A", BL1: "분데스", FL1: "리그1", DED: "네덜란드" };

  // 이 사이트는 하루 몇 번만 갱신 → 경기 중에는 실시간 스코어를 바깥 링크로 안내
  const BBC_LIVE = "https://www.bbc.com/sport/football/teams/manchester-united/scores-fixtures";
  function liveNote(m) {
    const k = new Date(m.kickoff_utc).getTime(), t = Date.now();
    if (!m.kickoff_confirmed || t < k - 15 * 6e4 || t > k + 150 * 6e4) return "";
    return `<p class="live-note">⚽ 지금 경기 중이에요. 이 사이트는 경기 후 30분~1시간 뒤에 결과가 반영됩니다. 실시간 스코어: <a href="${BBC_LIVE}" target="_blank" rel="noopener">BBC Sport</a></p>`;
  }

  function nextBar() {
    const m = upcoming[0];
    if (!m) return `<section class="nextbar empty"><span class="nb-label">다음 경기</span><span>예정된 경기가 없습니다</span></section>`;
    const home = m.home_away !== "A";
    const opCrest = m.opponent_crest ? `<img class="nb-crest" src="${esc(m.opponent_crest)}" alt="">` : "";
    const mu = `${muCrest("nb-crest")}<b>맨유</b>`, op = `${opCrest}<b>${esc(m.opponent)}</b>`;
    const round = m.matchday ? (m.comp === "PL" ? ` ${m.matchday}R` : ` ${m.matchday}차전`) : "";
    return `<a class="nextbar" href="#match/${m.id}">
      <span class="nb-label">다음 경기</span>
      <span class="badge ${esc(m.comp)}">${esc(compKo(m.comp))}${round}</span>
      <span class="nb-teams">${home ? mu : op}<span class="nb-vs">vs</span>${home ? op : mu}</span>
      <span class="nb-time">${m.kickoff_confirmed ? `${koDT(m.kickoff_utc)} KST` : `${koD(m.kickoff_utc)} · 시간 미정`}<small>${m.kickoff_confirmed ? ` · UK ${hm(m.kickoff_utc, UK)} ${ukZone(m.kickoff_utc)}` : ""}${m.venue ? " · " + esc(m.venue) : ""} · ${home ? "홈" : "원정"}</small></span>
      <span class="nb-cd compact" id="countdown" data-kickoff="${esc(m.kickoff_utc)}"></span>
    </a>${liveNote(m)}`;
  }

  const formChips = (ms) => `<div class="form">${(ms || []).slice().reverse().map((x) => `<span class="chip ${x.r}" title="${esc(`${x.date} ${COMP_SHORT[x.comp] || x.comp} ${x.ha === "H" ? "홈" : "원정"} vs ${x.opp}  ${x.gf}-${x.ga}`)}">${{ W: "승", D: "무", L: "패" }[x.r]}</span>`).join("")}</div>`;
  const keyList = (ks) => (ks && ks.length ? `<p class="pv-keys"><span>핵심 선수</span> ${ks.map((k) => `<b>${esc(k.name)}</b> <small class="muted">${k.goals}골 ${k.assists}도움</small>`).join(" · ")}</p>` : "");
  function teamCol(name, crest, t, fixed) {
    return `<div class="pv-team"><h3>${crest}${esc(name)} ${fixed ? '<small class="muted">우리 팀</small>' : '<small class="muted">상대 팀</small>'}</h3>
      ${t.recent && t.recent.length ? formChips(t.recent) : '<p class="muted small">최근 경기 기록 없음</p>'}
      <ul class="pv-points">${(t.points || []).map((p) => `<li>${esc(p)}</li>`).join("")}</ul>${keyList(t.keys)}</div>`;
  }
  function outList(list) {
    if (!list) return '<p class="muted small">정보 없음</p>';
    if (!list.length) return '<p class="muted small">결장 예상 선수 없음</p>';
    return `<ul class="pv-out">${list.map((p) => `<li><span class="pos">${esc(p.pos)}</span><b>${esc(p.name)}</b><span class="badge ${p.status === "s" ? "st-sus" : p.status === "d" ? "st-doubt" : "st-inj"}" title="${esc(p.news)}">${esc(p.ko)}</span></li>`).join("")}</ul>`;
  }
  const XI_POS = { GK: "GK", DF: "수비", MF: "중원", FW: "공격" };
  function previewPanel() {
    const m = upcoming[0], P = D.preview;
    if (!m) return `<div class="card"><h2>매치 프리뷰</h2><p class="muted">다가오는 경기가 없습니다.</p></div>`;
    if (!P || P.match_id !== m.id) return `<div class="card"><h2>매치 프리뷰</h2><p class="muted">다음 데이터 동기화 때 프리뷰가 생성됩니다.</p></div>`;
    const opCrest = m.opponent_crest ? `<img class="pv-crest" src="${esc(m.opponent_crest)}" alt="">` : "";
    const pr = P.prediction, hr = P.h2h_record;
    const xi = P.lineup || {};
    const byPos = ["GK", "DF", "MF", "FW"].map((pos) => [pos, (xi.players || []).filter((p) => p.pos === pos)]).filter(([, l]) => l.length);
    return `<div class="card pv">
        <div class="section-head"><h2>매치 프리뷰 <small>vs ${esc(P.opponent)}</small></h2><span class="pv-tag">통계 기반 자동 분석</span></div>
        <div class="pv-teams">${teamCol("맨유", muCrest("pv-crest"), P.mu, true)}${teamCol(P.opponent, opCrest, P.opp, false)}</div>
        ${(P.notes || []).map((n) => `<p class="pv-note">${esc(n)}</p>`).join("")}
      </div>
      <div class="card pv">
        <h2>승부 예측</h2>
        ${pr ? `<div class="pv-bar"><span class="w" style="flex:${pr.win}">${pr.win >= 12 ? "맨유 승 " : ""}${pr.win}%</span><span class="d" style="flex:${pr.draw}">${pr.draw >= 12 ? "무 " : ""}${pr.draw}%</span><span class="l" style="flex:${pr.loss}">${pr.loss >= 12 ? esc(P.opponent) + " 승 " : ""}${pr.loss}%</span></div>
          <div class="pv-score"><div><small>가장 가능성 높은 스코어</small><b>맨유 ${pr.score_mu} - ${pr.score_opp} ${esc(P.opponent)}</b></div>
          <div><small>기대 득점</small><b>${pr.xg_mu.toFixed(1)} : ${pr.xg_opp.toFixed(1)}</b></div></div>
          <p class="small muted" style="margin:8px 0 0">양 팀 최근 ${Math.min(pr.sample_mu, pr.sample_opp)}경기 득·실점과 ${P.home_away === "H" ? "맨유 홈" : P.home_away === "A" ? "상대 홈" : "중립 경기장"} 이점으로 계산한 푸아송 모델입니다. 상대한 팀의 수준·전술·부상은 반영되지 않는 참고용 수치입니다.</p>`
          : '<p class="muted">상대 기록이 부족해 예측하지 않습니다.</p>'}
        ${P.h2h && P.h2h.length ? `<h3 class="pv-sub">최근 맞대결 <small class="muted">${P.h2h.length}경기 ${hr.w}승 ${hr.d}무 ${hr.l}패 · ${hr.gf}득점 ${hr.ga}실점</small></h3>
          <div class="pv-h2h">${P.h2h.map((x) => `<span class="h2h-item"><span class="chip ${x.r}">${{ W: "승", D: "무", L: "패" }[x.r]}</span><small>${esc(x.date.slice(0, 7).replace("-", "."))} ${x.ha === "H" ? "홈" : "원정"} <b>${x.gf}-${x.ga}</b></small></span>`).join("")}</div>` : ""}
      </div>
      <div class="card pv">
        <h2>부상 · 결장</h2>
        <div class="pv-teams"><div class="pv-team"><h3>${muCrest("pv-crest")}맨유</h3>${outList(P.mu.out)}</div>
          <div class="pv-team"><h3>${opCrest}${esc(P.opponent)}</h3>${outList(P.opp.out)}</div></div>
        <p class="small muted" style="margin:8px 0 0">출처: Fantasy Premier League 선수 상태 (PL 팀만, 출전 가능성 75% 이상은 제외). 마우스를 올리면 원문이 보입니다.</p>
      </div>
      <div class="card pv">
        <h2>예상 선발 <small>${esc(xi.shape || "")}</small></h2>
        ${xi.caveat ? `<p class="pv-note">${esc(xi.caveat)}</p>` : ""}
        ${byPos.length ? `<div class="pv-xi">${byPos.map(([pos, l]) => `<div class="xi-row"><span class="pos">${XI_POS[pos]}</span>${l.map((p) => `<span class="xi-p conf-${p.conf === "높음" ? "hi" : p.conf === "보통" ? "mid" : "lo"}" title="선발 가능성 ${p.conf}${p.doubt ? " · 출전 불투명" : ""}">${esc(p.name)}${p.doubt ? " ?" : ""}</span>`).join("")}</div>`).join("")}</div>
          <p class="small muted" style="margin:8px 0 0">최근 PL ${xi.basis}경기 선발 기록(최근 경기일수록 가중)에서 부상·징계 선수를 빼고, 직전 경기 포지션 구성을 유지해 고른 명단입니다. 진한 색일수록 선발 가능성이 높습니다. 포지션은 FPL 분류 기준이며${xi.adjusted ? ", FPL이 미드필더로 분류한 선수 중 공격 기록(xG+xA)이 높은 선수를 공격 줄로 올려 포메이션을 추정했습니다" : ""}. 실제 포메이션과 다를 수 있습니다.</p>`
          : '<p class="muted">선발 기록이 아직 없습니다.</p>'}
      </div>`;
  }

  function newsPanel() {
    // 사이트에는 규칙 점수로 고른 주요 뉴스 5~8건만 옴 (etl/fetch_news.py, 같은 소식은 한 건으로 묶음)
    const list = D.news || [];
    const card = (n) => `<article class="news">
        <div class="news-meta"><span class="src t${n.tier}">${esc(n.source_name)}</span>${n.journalists ? n.journalists.split(",").map((j) => `<span class="jr">✎ ${esc(j)}</span>`).join("") : ""}<span class="muted">${n.published_utc ? ago(n.published_utc) : ""}</span></div>
        <a class="news-title" href="${esc(n.url)}" target="_blank" rel="noopener"${n.title_ko ? ` title="${esc(n.title)}"` : ""}>${esc(n.title_ko || n.title)}</a>
        ${n.title_ko ? `<div class="news-orig">${esc(n.title)}</div>` : ""}
        ${n.summary ? `<p class="news-sum">${esc(n.summary_ko || n.summary)}</p>` : ""}
        <div class="news-tags">${(n.tags || "").split(",").filter(Boolean).map((t) => `<span class="ntag ${t === "공식" ? "official" : t === "루머" ? "rumour" : ""}">${esc(t)}</span>`).join("")}${n.related > 0 ? `<span class="small muted">같은 소식 다른 기사 ${n.related}건</span>` : ""}</div>
      </article>`;
    return `<div class="card news-card">
      <div class="section-head"><h2>주요 뉴스</h2><span class="small muted">${list.length}건 · 중요도 순</span></div>
      ${list.map(card).join("") || '<p class="muted">표시할 뉴스가 없습니다.</p>'}
      <p class="small muted" style="margin:10px 0 0">BBC Sport · The Guardian · Sky Sports · Manchester Evening News 공식 RSS에서 최근 7일 기사 중 여러 매체 보도·공식 발표·감독·이적·부상·기자 언급 등을 점수로 매겨 상위 5~8건만 골랐습니다(자동 규칙이라 중요한 기사를 놓칠 수 있음). ${list.some((n) => n.title_ko) ? "한글 제목·요약은 DeepL 기계번역이라 어색하거나 틀릴 수 있습니다(영어 원제는 아래 회색 글씨). " : ""}태그와 기자 표시는 키워드 규칙으로 자동 분류해 틀릴 수 있습니다.</p>
    </div>`;
  }

  function pageHome() {
    const plForm = finished.filter((m) => m.comp === "PL").slice(-5);
    const recent = finished.slice(-5).reverse();
    const next = upcoming.slice(1, 6);
    const w = finished.filter((m) => m.result === "W").length, d = finished.filter((m) => m.result === "D").length, l = finished.filter((m) => m.result === "L").length;
    const gf = finished.reduce((a, m) => a + (m.mu_score || 0), 0), ga = finished.reduce((a, m) => a + (m.opp_score || 0), 0);
    return `${nextBar()}
    <div class="grid home-main">
      <div class="span-7 col">${previewPanel()}</div>
      <div class="span-5 col">${newsPanel()}</div>
    </div>
    <div class="grid">
      <div class="card span-4">
        <h2>프리미어리그 <small>${esc(D.season)}</small></h2>
        ${plRow ? `<div class="stat-row">
          <div class="stat hl"><b>${ord(plRow.position)}</b><span>순위</span></div>
          <div class="stat"><b>${plRow.points}</b><span>승점</span></div>
          <div class="stat"><b>${plRow.goal_diff > 0 ? "+" : ""}${plRow.goal_diff}</b><span>득실차</span></div></div>
          <p class="small muted" style="margin:10px 0 6px">${plRow.played}경기 ${plRow.won}승 ${plRow.drawn}무 ${plRow.lost}패 · 최근 5경기</p>
          <div class="form">${plForm.map((m) => chip(m.result)).join("")}</div>` : `<p class="muted">순위 정보 없음</p>`}
        <p style="margin:12px 0 0"><a href="#table" class="small" style="color:var(--red);font-weight:700">전체 순위 →</a></p>
      </div>
      <div class="card span-4">
        <h2>챔피언스리그 <small>리그 페이즈</small></h2>
        ${uclRow ? `<div class="stat-row">
          <div class="stat hl"><b>${ord(uclRow.position)}</b><span>36팀 중</span></div>
          <div class="stat"><b>${uclRow.points}</b><span>승점</span></div>
          <div class="stat"><b>${uclRow.played}</b><span>경기</span></div></div>
          <p class="small muted" style="margin:10px 0 0">${uclRow.position <= 8 ? "16강 직행권 (1~8위)" : uclRow.position <= 24 ? "플레이오프권 (9~24위)" : "탈락권 (25위 이하)"} · ${uclRow.won}승 ${uclRow.drawn}무 ${uclRow.lost}패</p>` : `<p class="muted">순위 정보 없음</p>`}
      </div>
      <div class="card span-4">
        <h2>시즌 전체 <small>PL + UCL</small></h2>
        <div class="stat-row">
          <div class="stat"><b>${w}</b><span>승</span></div><div class="stat"><b>${d}</b><span>무</span></div><div class="stat"><b>${l}</b><span>패</span></div></div>
        <p class="small muted" style="margin:10px 0 0">${finished.length}경기 · ${gf}득점 ${ga}실점</p>
      </div>
      <div class="card span-6"><div class="section-head"><h2>최근 결과</h2><a href="#fixtures">전체 보기 →</a></div>
        <ul class="match-list">${recent.map(matchRow).join("")}</ul></div>
      <div class="card span-6"><div class="section-head"><h2>다가오는 경기</h2><a href="#fixtures">전체 일정 →</a></div>
        <ul class="match-list">${next.map(matchRow).join("") || `<li class="empty">예정된 경기가 없습니다</li>`}</ul></div>
    </div>`;
  }

  let fixtureFilter = "ALL";
  function pageFixtures() {
    const past = fixtureSeason !== D.season;
    if (past) loadArchive();
    const src = past ? archMatches().filter((m) => m.season === fixtureSeason) : matches;
    const comps = ["ALL", ...new Set(src.map((m) => m.comp))];
    if (!comps.includes(fixtureFilter)) fixtureFilter = "ALL";
    const list = src.filter((m) => fixtureFilter === "ALL" || m.comp === fixtureFilter);
    const seasonBar = ARCH_SEASONS.length
      ? `<div class="filters season-filters">${[D.season, ...ARCH_SEASONS].map((s) => `<button data-fseason="${s}" class="${s === fixtureSeason ? "on" : ""}">${s}</button>`).join("")}</div>` : "";
    if (past && archiveState !== "ready") {
      return `${title("일정 · 결과")}<p class="page-sub">${esc(fixtureSeason)} 시즌</p>${seasonBar}
        <div class="card empty">${archiveState === "error" ? "<b>지난 시즌을 불러오지 못했습니다</b>페이지를 새로고침해 주세요." : "<b>불러오는 중…</b>"}</div>`;
    }
    let html = "", cur = "";
    for (const m of list) {
      const k = monthKey(m.kickoff_utc);
      if (k !== cur) { if (cur) html += "</ul>"; html += `<h3 class="month">${k}</h3><ul class="match-list card" style="padding:4px 14px">`; cur = k; }
      html += matchRow(m);
    }
    if (cur) html += "</ul>";
    return `${title("일정 · 결과")}
      <p class="page-sub">${esc(fixtureSeason)} 시즌 · 날짜·시각은 한국 시간, 오른쪽은 영국 시간 (서머타임 자동 반영) · 점수는 맨유 점수가 앞</p>
      ${seasonBar}
      <div class="filters">${comps.map((c) => `<button data-filter="${c}" class="${c === fixtureFilter ? "on" : ""}">${c === "ALL" ? "전체" : compKo(c)}</button>`).join("")}</div>
      ${html || '<p class="muted">이 시즌에 기록된 경기가 아직 없습니다.</p>'}
      <p class="small muted">${past
        ? `* 공식 경기만 (친선경기 제외). ${fixtureSeason >= "2025" ? "출처: football-data.org (프리미어리그), 위키백과 (컵 대회)." : "출처: API-Football — 점수·득점 시간·카드·출전 선수·팀 기록."}`
        : "* 프리미어리그·챔피언스리그는 football-data.org, FA컵·EFL컵은 위키백과 기준."}</p>`;
  }

  let tableComp = "PL";
  function pageTable() {
    const rows = D.tables[tableComp] || [];
    const zone = (p) => tableComp === "PL"
      ? (p <= 4 ? "ucl" : p === 5 ? "uel" : p >= 18 ? "rel" : "")
      : (p <= 8 ? "ucl" : p <= 24 ? "po" : "");
    const legend = tableComp === "PL"
      ? `<span><i class="zone ucl"></i>챔피언스리그</span><span><i class="zone uel"></i>유로파리그</span><span><i class="zone rel"></i>강등</span>`
      : `<span><i class="zone ucl"></i>16강 직행</span><span><i class="zone po"></i>플레이오프</span>`;
    return `${title("순위")}<p class="page-sub">${esc(D.season)} 시즌 · 매일 자동 갱신</p>
      <div class="filters">${["PL", "UCL"].map((c) => `<button data-table="${c}" class="${c === tableComp ? "on" : ""}">${compKo(c)}</button>`).join("")}</div>
      <div class="card"><div class="table-wrap"><table class="data">
        <thead><tr><th class="l">#</th><th class="l">팀</th><th>경기</th><th>승</th><th>무</th><th>패</th><th>득점</th><th>실점</th><th>득실</th><th>승점</th></tr></thead>
        <tbody>${rows.map((r) => `<tr class="${r.is_mu ? "mu" : ""}">
          <td class="l"><i class="zone ${zone(r.position)}"></i>${r.position}</td>
          <td class="team">${crestImg(r.crest, r.team)}${esc(r.team)}</td>
          <td>${r.played}</td><td>${r.won}</td><td>${r.drawn}</td><td>${r.lost}</td><td>${r.goals_for}</td><td>${r.goals_against}</td>
          <td>${r.goal_diff > 0 ? "+" : ""}${r.goal_diff}</td><td class="pts">${r.points}</td></tr>`).join("")}</tbody>
      </table></div><div class="legend">${legend}</div></div>`;
  }

  function pageEmpty(t, sub, msg) {
    return `${title(t)}<p class="page-sub">${sub}</p><div class="card empty"><b>준비 중</b>${msg}</div>`;
  }

  // ----- 선수 -----
  const POS_EN = { GK: "골키퍼", DF: "수비수", MF: "미드필더", FW: "공격수" };
  const POS_PL = POS_EN;
  const AVAIL = { i: ["부상", "st-inj"], s: ["출장 정지", "st-sus"], d: ["출전 불투명", "st-doubt"], n: ["출전 불가", "st-sus"], u: ["이탈", "st-doubt"] };
  const age = (dob) => {
    if (!dob) return "";
    const b = new Date(dob), n = new Date();
    return n.getFullYear() - b.getFullYear() - (n < new Date(n.getFullYear(), b.getMonth(), b.getDate()) ? 1 : 0);
  };
  const pName = (p) => p.known_as || p.full_name;
  // 사진이 없거나 못 불러오면 기본 실루엣 (#6)
  const SIL = "data:image/svg+xml," + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 50"><rect width="40" height="50" fill="#ece7e1"/><circle cx="20" cy="18" r="8" fill="#c9c1b8"/><path d="M5 50c0-10 7-17 15-17s15 7 15 17z" fill="#c9c1b8"/></svg>');
  const photo = (p, cls = "pthumb") => `<img class="${cls}" src="${esc(p.photo_url || SIL)}" alt="" loading="lazy" onerror="this.onerror=null;this.src='${SIL}'">`;
  const pNews = (p) => p.news_ko || p.news || "";

  let playerPos = "ALL", playerSort = { key: "goals", dir: -1 };
  const COLS = [
    // 골·도움을 선수 이름 바로 옆에 → 모바일에서 옆으로 밀지 않아도 보임
    ["shirt_number", "#", 1], ["goals", "골"], ["assists", "도움"], ["appearances", "출전"], ["starts", "선발"], ["minutes", "출전 시간"],
    ["xg", "xG"], ["xa", "xA"], ["yellow_cards", "경고"], ["red_cards", "퇴장"],
  ];

  function pagePlayers() {
    if (!D.players.length) return pageEmpty("선수 통계", `${esc(D.season)} 시즌`, "python etl/fetch_players.py 실행 후 표시됩니다.");
    const active = D.players.filter((p) => p.squad_status === "active");
    const gone = D.players.filter((p) => p.squad_status !== "active");
    const leader = (key, label, unit) => {
      const p = active.slice().sort((a, b) => (b[key] || 0) - (a[key] || 0) || b.minutes - a.minutes)[0];
      return `<div class="card span-4 leader">${photo(p, "lphoto")}<div><div class="small muted">${label}</div>
        <div class="lval">${p[key]}<small>${unit}</small></div><div class="lname">${esc(pName(p))}</div>
        <div class="small muted">${POS_EN[p.position] || ""}${p.shirt_number ? " · 등번호 " + p.shirt_number : ""}</div></div></div>`;
    };
    const out = active.filter((p) => ["i", "s", "d", "n"].includes(p.avail));

    const list = active.filter((p) => playerPos === "ALL" || p.position === playerPos)
      .sort((a, b) => {
        const k = playerSort.key, va = a[k] ?? -1, vb = b[k] ?? -1;
        return (va - vb) * playerSort.dir || b.minutes - a.minutes;
      });
    const th = ([k, l]) => `<th data-sort="${k}" class="sortable${playerSort.key === k ? " on" : ""}">${l}${playerSort.key === k ? (playerSort.dir < 0 ? " ▾" : " ▴") : ""}</th>`;

    return `${title("선수 통계")}
      <p class="page-sub">${esc(D.season)} 프리미어리그 기록만 (컵 대회·챔피언스리그 제외)</p>
      <div class="grid">${leader("goals", "최다 득점", "골")}${leader("assists", "최다 도움", "도움")}${leader("minutes", "최다 출전 시간", "분")}</div>
      ${out.length ? `<div class="card" style="margin-bottom:16px"><h2>부상 · 징계 <small>${out.length}명</small></h2><div class="injuries">
        ${out.map((p) => `<div class="inj-card">${photo(p)}<div style="min-width:0"><b>${esc(pName(p))}</b> <span class="badge ${AVAIL[p.avail][1]}">${AVAIL[p.avail][0]}</span>
          <div class="small muted" title="${esc(p.news)}">${esc(pNews(p))}</div></div></div>`).join("")}</div></div>` : ""}
      <div class="filters">${["ALL", "GK", "DF", "MF", "FW"].map((c) => `<button data-pos="${c}" class="${c === playerPos ? "on" : ""}">${c === "ALL" ? "전체" : POS_PL[c]}</button>`).join("")}</div>
      <div class="card"><div class="table-wrap"><table class="data players">
        <thead><tr>${th(COLS[0])}<th class="l">선수</th>${COLS.slice(1).map(th).join("")}</tr></thead>
        <tbody>${list.map((p) => `<tr class="${p.minutes ? "" : "dim"}">
          <td class="num">${p.shirt_number ?? ""}</td>
          <td class="team">${photo(p)}<div><b>${esc(pName(p))}</b>${p.avail && AVAIL[p.avail] && p.avail !== "u" ? ` <span class="dot ${AVAIL[p.avail][1]}" title="${esc(pNews(p))}"></span>` : ""}
            <div class="small muted">${p.position}${age(p.date_of_birth) !== "" ? " · 만 " + age(p.date_of_birth) + "세" : ""}</div></div></td>
          <td class="pts">${p.goals}</td><td class="pts">${p.assists}</td><td>${p.appearances}</td><td>${p.starts}</td><td>${p.minutes}</td>
          <td>${p.xg != null ? p.xg.toFixed(2) : "–"}</td><td>${p.xa != null ? p.xa.toFixed(2) : "–"}</td><td>${p.yellow_cards}</td><td>${p.red_cards}</td></tr>`).join("")}</tbody>
      </table></div><p class="small muted" style="margin:10px 0 0">열 제목을 누르면 정렬됩니다. xG = 기대 득점, xA = 기대 도움 (FPL 수치). 출전 시간은 분 단위입니다.</p></div>
      ${gone.length ? `<div class="card" style="margin-top:16px"><h2>임대 · 이적으로 이탈 <small>${gone.length}명</small></h2><ul class="match-list">
        ${gone.map((p) => `<li class="match" style="grid-template-columns:1fr"><div><b>${esc(pName(p))}</b> <span class="small muted">${p.position}</span><div class="small muted" title="${esc(p.news)}">${esc(pNews(p))}</div></div></li>`).join("")}</ul></div>` : ""}`;
  }

  let transferSeason = null;
  const TT_EN = { permanent: "완전 이적", free: "자유 이적", release: "방출", loan: "임대", loan_return: "임대 복귀", youth_promotion: "유스 승격" };
  const VERIFY = { verified: ["vf-ok", "✓ 공식 확인"], consistent: ["vf-none", "모순 없음"], unverified: ["vf-none", "확인 불가"], conflict: ["vf-bad", "⚠ 불일치"] };
  const MON = { january: 1, february: 2, march: 3, april: 4, may: 5, june: 6, july: 7, august: 8, september: 9, october: 10, november: 11, december: 12 };
  // 위키백과 이적료·비고 → 한글 (예: "Loan until 5 January 2027" → "2027.1.5까지 임대")
  const feeKo = (f) => {
    if (!f) return "-";
    const fixed = { Free: "자유 이적", Undisclosed: "비공개", Released: "방출", Retired: "은퇴" };
    if (fixed[f]) return fixed[f];
    const m = f.match(/^Loan until (\d{1,2}) ([A-Za-z]+) (\d{4})$/);
    if (m && MON[m[2].toLowerCase()]) return `${m[3]}.${MON[m[2].toLowerCase()]}.${m[1]}까지 임대`;
    if (/^Loan until end of season$/i.test(f)) return "시즌 종료까지 임대";
    return f;
  };
  function verifyBadge(t) {
    const v = VERIFY[t.verify_status];
    return v ? `<span class="badge ${v[0]}" title="${esc(t.verify_note || "")}">${v[1]}</span>` : '<span class="small muted">-</span>';
  }
  const CHECK_EN = { missing_in: "공식 데이터에는 합류, 위키백과 영입 목록에는 없음", missing_out: "공식 데이터에는 이탈·임대, 위키백과 방출 목록에는 없음", conflict: "위키백과와 공식 선수단 정보가 다름" };
  function pageTransfers() {
    if (!D.transfers.length) return pageEmpty("이적 현황", "영입 · 방출 · 임대", "이적 데이터가 아직 없습니다.");
    const seasons = [...new Set(D.transfers.map((t) => t.season).filter(Boolean))].sort().reverse();
    if (!transferSeason || !seasons.includes(transferSeason)) transferSeason = seasons[0];
    const list = D.transfers.filter((t) => t.season === transferSeason);
    const checks = (D.transfer_checks || []).filter((c) => c.season === transferSeason);
    const groups = [
      ["영입", list.filter((t) => t.direction === "in" && t.transfer_type !== "loan"), "from_club", "이전 팀"],
      ["임대 영입", list.filter((t) => t.direction === "in" && t.transfer_type === "loan"), "from_club", "원소속 팀"],
      ["방출", list.filter((t) => t.direction === "out" && t.transfer_type !== "loan"), "to_club", "이적 팀"],
      ["임대 이적", list.filter((t) => t.direction === "out" && t.transfer_type === "loan"), "to_club", "임대 팀"],
    ].filter((g) => g[1].length);
    const fromWiki = list.some((t) => (t.source || "").startsWith("wikipedia"));
    return `${title("이적 현황")}<p class="page-sub">${esc(transferSeason)} · 영입 ${list.filter((t) => t.direction === "in").length}명 · 방출 ${list.filter((t) => t.direction === "out").length}명</p>
      <div class="filters">${seasons.map((s) => `<button data-tseason="${esc(s)}" class="${s === transferSeason ? "on" : ""}">${esc(s)}</button>`).join("")}</div>
      ${groups.map(([ko, rows, clubKey, clubLabel]) => `<div class="card" style="margin-bottom:16px"><h2>${ko} <small>${rows.length}명</small></h2>
        <div class="table-wrap"><table class="data"><thead><tr><th class="l">날짜</th><th class="l">포지션</th><th class="l">선수</th><th class="l">${clubLabel}</th><th class="l">유형</th><th class="l">이적료 · 비고</th><th class="l">검증</th></tr></thead>
        <tbody>${rows.slice().sort((a, b) => (a.transfer_date < b.transfer_date ? 1 : -1)).map((t) => `<tr><td class="l small">${esc(t.transfer_date)}</td><td class="l small">${esc(t.position || "")}</td>
          <td class="l"><b>${esc(t.player_name)}</b></td><td class="l">${esc(t[clubKey] === "Unattached" ? "무소속" : t[clubKey] || "-")}</td><td class="l small">${esc(TT_EN[t.transfer_type] || t.transfer_type || "")}</td><td class="l small muted">${esc(feeKo(t.fee_text))}</td><td class="l">${verifyBadge(t)}</td></tr>`).join("")}</tbody></table></div></div>`).join("")}
      ${checks.length ? `<div class="card" style="margin-bottom:16px"><h2>확인 필요 <small>데이터 점검 · ${checks.length}건</small></h2><ul class="match-list">${checks.map((c) => `<li class="match" style="grid-template-columns:1fr auto"><div><b>${esc(c.player_name)}</b><div class="small muted">${esc(CHECK_EN[c.kind] || c.kind)}</div></div><div class="small muted">${esc((c.first_seen_utc || "").slice(0, 10))}</div></li>`).join("")}</ul></div>` : ""}
      ${fromWiki ? `<p class="small muted">출처: <a href="${esc(list.find((t) => t.source_url)?.source_url || "https://en.wikipedia.org/")}" target="_blank" rel="noopener">위키백과</a> 시즌 문서 (CC BY-SA 4.0). 매일 공식 1군 선수단(football-data.org)과 Fantasy Premier League 선수 상태로 대조합니다. <b>✓ 공식 확인</b> = 공식 선수단 데이터로 확인 · <b>모순 없음</b> = 공식 선수단에 없어 이탈과 모순되지 않지만 직접 공식 기록은 없음 · <b>확인 불가</b> = 1군 밖 선수(유스 등)라 대조 불가 · <b>⚠ 불일치</b> = 위키백과와 공식 데이터가 다름. 이적료는 대부분 공식 발표되지 않습니다.</p>` : ""}`;
  }

  const TROPHY_EN = { PL: "리그 우승", FL1: "리그 우승", FAC: "FA컵", ELC: "리그컵", UCL: "유러피언컵 · 챔피언스리그", UEL: "유로파리그", UCWC: "컵위너스컵", USC: "UEFA 슈퍼컵", ICC: "인터콘티넨털컵", CWC: "클럽 월드컵", CS: "커뮤니티 실드" };
  const NAT_KO = { England: "잉글랜드", Scotland: "스코틀랜드", Wales: "웨일스", Ireland: "아일랜드", "Northern Ireland": "북아일랜드", Netherlands: "네덜란드", Norway: "노르웨이", Portugal: "포르투갈", Germany: "독일", Argentina: "아르헨티나", Spain: "스페인", France: "프랑스", Italy: "이탈리아" };
  const PLACE_KO = { "Old Trafford": "올드 트래퍼드", Manchester: "맨체스터" };
  const todayIso = new Date().toISOString().slice(0, 10);
  function pageHistory() {
    const c = D.club;
    const counts = {};
    for (const h of D.honours_count) { const k = TROPHY_EN[h.code] || h.name; counts[k] = (counts[k] || 0) + h.titles; }
    const lastWin = (codes) => D.honours.filter((h) => codes.includes(h.code)).map((h) => h.season).sort().pop();
    const codesOf = (k) => Object.keys(TROPHY_EN).filter((c) => TROPHY_EN[c] === k);
    return `${title("클럽 역사")}
      <p class="page-sub">${esc(c.founded_year)}년 ${esc(c.founded_as)}로 창단 · ${esc(PLACE_KO[c.city] || c.city)} · 홈구장 ${esc(PLACE_KO[c.stadium] || c.stadium)} (약 ${Number(c.stadium_capacity).toLocaleString("ko-KR")}석)</p>
      <div class="card" style="margin-bottom:16px"><h2>우승 기록</h2><div class="trophies">
        ${Object.entries(counts).map(([k, n]) => `<div class="trophy"><b>${n}</b><span>${esc(k)}</span><small>최근 ${esc(lastWin(codesOf(k)) || "-")}</small></div>`).join("")}
      </div></div>
      <div class="grid">
        <div class="card span-8"><h2>주요 연표</h2><ul class="timeline">
          ${D.timeline.map((t) => `<li class="${t.category === "trophy" ? "trophy-ev" : ""}"><div class="yr">${t.year}</div><div class="ttl">${esc(t.title_ko || t.title)}</div></li>`).join("")}
        </ul></div>
        <div class="card span-4"><h2>역대 감독 <small>${D.managers.length}</small></h2><ul class="match-list managers">
          ${D.managers.slice().reverse().map((m) => `<li class="match" style="grid-template-columns:1fr auto"><div><b>${esc(m.name_ko || m.name)}</b>${m.name_ko ? ` <span class="small muted">${esc(m.name)}</span>` : ""}${m.is_caretaker ? ' <span class="badge ha">대행</span>' : ""}<div class="small muted">${esc([NAT_KO[m.nationality] || m.nationality, m.matches ? `${m.matches}경기 ${m.wins}승 ${m.draws}무 ${m.losses}패` : "", m.note].filter(Boolean).join(" · "))}</div></div><div class="small muted" style="text-align:right">${esc(m.start_date)} –<br>${m.start_date > todayIso ? "<b>부임 예정</b>" : esc(m.end_date || "현재")}</div></li>`).join("")}
        </ul></div>
      </div>`;
  }

  // 위키백과 영문 대회 성적 → 한글 (긴 이름부터 바꿈)
  const EURO_KO = [["UEFA Champions League", "챔피언스리그"], ["Champions League", "챔피언스리그"], ["European Cup", "유러피언컵"], ["UEFA Cup", "UEFA컵"],
    ["Europa League", "유로파리그"], ["Cup Winners' Cup", "컵위너스컵"], ["Inter-Cities Fairs Cup", "페어스컵"], ["Super Cup", "슈퍼컵"],
    ["Intercontinental Cup", "인터콘티넨털컵"], ["Club World Championship", "클럽 월드 챔피언십"], ["Club World Cup", "클럽 월드컵"],
    ["Round of 16", "16강"], ["Runners-up", "준우승"], ["Winners", "우승"], ["Third place", "3위"], ["Group", "조별리그"],
    [/\bQF\b/g, "8강"], [/\bSF\b/g, "4강"], [/\bQR(\d)\b/g, "예선 $1라운드"], [/\bRInt\b/g, "중간 라운드"], [/\bR(\d)\b/g, "$1라운드"],
    ["(in progress)", "(진행 중)"]];
  const resultKo = (s) => EURO_KO.reduce((t, [a, b]) => (typeof a === "string" ? t.split(a).join(b) : t.replace(a, b)), s || "");

  let recordsEra = "PL";
  const ERAS = {
    PL: ["프리미어리그 시대", (r) => r.season >= "1992"],
    POST: ["1946–1992", (r) => r.season >= "1946" && r.season < "1992"],
    PRE: ["1888–1939", (r) => r.season < "1946"],
    ALL: ["전체 시즌", () => true],
  };
  const DIV_SHORT = { PL: "PL", FL1: "1부", FL2: "2부", FALL: "얼라이언스", COMB: "컴비네이션" };
  const cupTxt = (s) => (!s ? "–" : s === "Winners" ? "🏆 우승" : esc(resultKo(s)));
  function pageRecords() {
    const all = D.seasons.slice().reverse();
    const rows = all.filter(ERAS[recordsEra][1]);
    const top = (r) => r.comp === "PL" || r.comp === "FL1";
    const cls = (r) => (r.position === 1 && top(r) ? "p1" : top(r) && r.position <= 4 ? "top4" : top(r) && r.position >= 15 ? "low" : "");
    const leagueTitles = all.filter((r) => r.position === 1 && r.is_final && top(r)).length;
    const europe = (r) => (r.is_final ? resultKo([r.europe_competition, r.europe_result].filter(Boolean).join(" – "))
      : (r.europe_result || "").replace("리그 페이즈", `${r.europe_competition ? resultKo(r.europe_competition) + " " : ""}리그 페이즈`));
    const fromWiki = all.some((r) => (r.source || "").startsWith("wikipedia"));
    return `${title("시즌별 기록")}<p class="page-sub">${all.length ? esc(all[all.length - 1].season) : "-"} 시즌부터 ${all.length}시즌 · 리그 우승 ${leagueTitles}회</p>
      <div class="filters">${Object.entries(ERAS).map(([k, [label]]) => `<button data-era="${k}" class="${k === recordsEra ? "on" : ""}">${label}</button>`).join("")}</div>
      <div class="card"><div class="table-wrap"><table class="data">
        <thead><tr><th class="l">시즌</th><th class="l">리그</th><th class="l">순위</th><th>경기</th><th>승</th><th>무</th><th>패</th><th>득점</th><th>실점</th><th>승점</th><th class="l">FA컵</th><th class="l">리그컵</th><th class="l">유럽대항전</th><th class="l">최다 득점</th></tr></thead>
        <tbody>${rows.map((r) => `<tr class="${r.is_final ? "" : "mu"}"><td class="l">${esc(r.season)}</td><td class="l small">${esc(DIV_SHORT[r.comp] || r.comp)}</td>
          <td class="l"><span class="pos ${cls(r)}">${r.position ?? "-"}</span>${r.is_final ? "" : ' <span class="small muted">진행 중</span>'}</td>
          <td>${r.played ?? "–"}</td><td>${r.won ?? "–"}</td><td>${r.drawn ?? "–"}</td><td>${r.lost ?? "–"}</td><td>${r.goals_for ?? "–"}</td><td>${r.goals_against ?? "–"}</td><td class="pts">${r.points ?? "–"}</td>
          <td class="l small">${cupTxt(r.fa_cup)}</td><td class="l small">${cupTxt(r.league_cup)}</td><td class="l small muted wrap">${esc(europe(r)) || "–"}</td>
          <td class="l small">${r.top_scorer ? `${esc(r.top_scorer)} <span class="muted">(${r.top_scorer_goals ?? "?"}${r.top_scorer_note ? ", PL 기준" : ""})</span>` : "–"}</td></tr>`).join("")}</tbody>
      </table></div>
      <p class="small muted" style="margin-top:10px">1부 = 풋볼 리그 1부 (1992-93 이전 최상위 리그), 2부 = 2부 리그. 최다 득점은 모든 대회 합계입니다 (진행 중인 시즌은 시즌이 끝날 때까지 프리미어리그 득점 기준). 진행 중인 시즌의 컵 성적은 경기 결과로 계산합니다. 1915–19년과 1939–46년은 세계대전으로 리그가 열리지 않았습니다.${fromWiki ? ' 과거 기록: <a href="https://en.wikipedia.org/wiki/List_of_Manchester_United_F.C._seasons" target="_blank" rel="noopener">위키백과</a> (CC BY-SA 4.0).' : ""}</p></div>`;
  }

  // ----- 경기 상세 (#match/<id>) -----
  const EV_ROWS = [["goal", "⚽", "득점"], ["own_goal", "⚽", "자책골"], ["assist", "🅰️", "도움"],
    ["missed_penalty", "❌", "페널티 실축"], ["penalty_saved", "🧤", "페널티 선방"],
    ["yellow", "🟨", "경고"], ["red", "🟥", "퇴장"]];
  const grouped = (list) => {
    const c = new Map();
    for (const n of list) c.set(n, (c.get(n) || 0) + 1);
    return [...c].map(([n, k]) => esc(n) + (k > 1 ? ` <span class="x">×${k}</span>` : "")).join("<br>");
  };
  function lineupCard(det, m) {
    const lu = det.lineup || [];
    const apif = det.src === "apif";
    if ((m.comp !== "PL" && !apif) || m.status !== "FINISHED") return "";
    if (!lu.length) return `<div class="card span-12"><h2>출전 선수 <small>맨유</small></h2><p class="muted">다음 데이터 동기화 후 표시됩니다.</p></div>`;
    const ic = (p) => [p.goals ? "⚽".repeat(p.goals) : "", p.assists ? `<small class="muted">A${p.assists > 1 ? p.assists : ""}</small>` : "",
      p.yellow ? '<span class="card-y"></span>' : "", p.red ? '<span class="card-r"></span>' : ""].join(" ");
    const li = (p) => `<li><span class="pos">${esc(p.pos || "")}</span><b>${esc(p.name)}</b> ${ic(p)}<span class="min">${p.rating ? `<small class="muted">${Number(p.rating).toFixed(1)}</small> ` : ""}${p.minutes != null ? p.minutes + "'" : ""}</span></li>`;
    const xi = lu.filter((p) => p.starter), subs = lu.filter((p) => !p.starter);
    if (apif) {
      return `<div class="card span-12"><h2>출전 선수 <small>맨유${det.formation ? " · " + esc(det.formation) : ""}${det.opp_formation ? ` <span class="muted">(${esc(m.opponent)} ${esc(det.opp_formation)})</span>` : ""}</small></h2>
      <div class="lineup"><div><h3>선발 <small>${xi.length}</small></h3><ul>${xi.map(li).join("")}</ul></div>
      <div><h3>교체 출전 <small>${subs.length}</small></h3><ul>${subs.map(li).join("") || '<li class="muted">없음</li>'}</ul></div></div>
      <p class="small muted" style="margin:10px 0 0">출처: API-Football (출전 선수·출전 시간·평점). 출전하지 않은 교체 선수는 표시하지 않습니다.</p></div>`;
    }
    return `<div class="card span-12"><h2>출전 선수 <small>맨유</small></h2>
      <div class="lineup"><div><h3>선발 <small>${xi.length}</small></h3><ul>${xi.map(li).join("")}</ul></div>
      <div><h3>교체 출전 <small>${subs.length}</small></h3><ul>${subs.map(li).join("") || '<li class="muted">없음</li>'}</ul></div></div>
      <p class="small muted" style="margin:10px 0 0">출처: Fantasy Premier League (선발·출전 시간). 출전하지 않은 교체 선수와 포메이션 정보는 없습니다${xi.length !== 11 ? ". 이후 팀을 떠난 선수는 빠져 있을 수 있습니다" : ""}.</p></div>`;
  }
  function pageMatch(id) {
    const m = matches.find((x) => String(x.id) === String(id)) || archMatches().find((x) => String(x.id) === String(id));
    if (!m && archiveState === "none" && ARCH_SEASONS.length) { loadArchive(); }
    if (!m && archiveState === "loading") return `${title("경기 상세")}<div class="card empty"><b>불러오는 중…</b></div>`;
    if (!m) return `${title("경기 상세")}<div class="card empty"><b>경기를 찾을 수 없습니다</b><a href="#fixtures">일정으로 돌아가기</a></div>`;
    const det = detailsOf(m.id) || { events: [] };
    const apif = det.src === "apif";
    const seasonFinished = m.season && m.season !== D.season ? archMatches().filter((x) => x.season === m.season && x.status === "FINISHED") : finished;
    const ev = det.events || [];
    const home = m.home_away !== "A";
    const L = home ? "MU" : "OPP", R = home ? "OPP" : "MU";
    const teamName = (side) => (side === "MU" ? "맨유" : m.opponent);
    const haOf = (side) => (m.home_away === "N" ? "중립" : (side === "MU") === home ? "홈" : "원정");
    const crest = (side) => (side === "MU" ? muCrest("crest") : m.opponent_crest ? `<img class="crest" src="${esc(m.opponent_crest)}" alt="">` : "");
    const done = m.status === "FINISHED";
    const minute = (e) => (e.minute != null ? ` ${e.minute}${e.extra_minute ? "+" + e.extra_minute : ""}'` : "");
    const names = (side, type) => ev.filter((e) => e.side === side && e.type === type).map((e) => e.player + minute(e) + (e.detail === "pen" ? " (PK)" : ""));
    const muOnly = m.comp !== "PL" && !apif;  // 컵 대회(위키백과)는 맨유 득점자만 기록됨
    const rows = EV_ROWS.filter(([t]) => ev.some((e) => e.type === t)).map(([t, ic, label]) => `
      <tr><td class="ev-l">${grouped(names(L, t)) || "–"}</td><th><span class="ic">${ic}</span>${label}</th><td class="ev-r">${grouped(names(R, t)) || (muOnly && R === "OPP" ? '<span class="muted">기록 없음</span>' : "–")}</td></tr>`).join("");
    const bonus = ev.filter((e) => e.type === "bonus").sort((a, b) => b.detail - a.detail);
    const md = m.matchday ? (m.comp === "PL" ? ` · ${m.matchday}라운드` : ` · ${m.matchday}차전`) : (m.stage && /[a-z]/.test(m.stage) ? ` · ${esc(resultKo(m.stage.replace(/^Third round$/i, "R3").replace(/^Second round$/i, "R2").replace(/^Fourth round$/i, "R4").replace(/^Fifth round$/i, "R5").replace(/^Quarter-finals?$/i, "QF").replace(/^Semi-finals?$/i, "SF").replace(/^Final$/i, "결승")))}` : "");
    const idx = seasonFinished.findIndex((x) => x.id === m.id);
    const prev = idx > 0 ? seasonFinished[idx - 1] : null, next = idx >= 0 ? seasonFinished[idx + 1] : null;
    const st = det.stats || {};
    const STAT_ROWS = [["poss", "점유율", "%"], ["shots", "슈팅", ""], ["sot", "유효 슈팅", ""], ["corners", "코너킥", ""],
      ["fouls", "파울", ""], ["offsides", "오프사이드", ""], ["passes", "패스", ""], ["pass_pct", "패스 성공률", "%"], ["saves", "선방", ""]];
    const statCard = st.MU && st.OPP ? `<div class="card span-4"><h2>팀 기록</h2><table class="events"><thead><tr><th class="ev-l">${esc(teamName(L))}</th><th></th><th class="ev-r">${esc(teamName(R))}</th></tr></thead><tbody>
      ${STAT_ROWS.filter(([k]) => st.MU[k] != null || st.OPP[k] != null).map(([k, label, u]) => `<tr><td class="ev-l">${st[L][k] ?? "–"}${st[L][k] != null ? u : ""}</td><th>${label}</th><td class="ev-r">${st[R][k] ?? "–"}${st[R][k] != null ? u : ""}</td></tr>`).join("")}
      </tbody></table><p class="small muted" style="margin:10px 0 0">출처: API-Football.</p></div>` : "";
    const emptyMsg = !done ? "아직 열리지 않은 경기입니다."
      : m.comp === "PL" ? "다음 데이터 동기화 후 표시됩니다."
      : "이 대회는 무료 데이터로 득점자·카드 기록을 제공하지 않습니다.";
    return `${title("경기 상세")}
      <p class="page-sub"><a href="javascript:history.back()" class="back">← 뒤로</a> · ${esc(compKo(m.comp))}${md}</p>
      <section class="board">
        <div class="board-team">${crest(L)}<b>${esc(teamName(L))}</b><span>${haOf(L)}</span></div>
        <div class="board-score">${done ? scoreText(m) : "vs"}${done ? `<div>${chip(m.result)}</div>` : ""}</div>
        <div class="board-team">${crest(R)}<b>${esc(teamName(R))}</b><span>${haOf(R)}</span></div>
        <div class="board-meta">${m.kickoff_confirmed ? `한국 ${dateTime(m.kickoff_utc, KST)} · 영국 ${dateTime(m.kickoff_utc, UK)} ${ukZone(m.kickoff_utc)}` : `${shortDate(m.kickoff_utc, UK)} · 킥오프 시각 기록 없음`}${m.venue ? " · " + esc(m.venue) : ""}</div>
      </section>
      <div class="grid">
        <div class="card span-8"><h2>경기 기록</h2>
          ${rows ? `<table class="events"><thead><tr><th class="ev-l">${esc(teamName(L))}</th><th></th><th class="ev-r">${esc(teamName(R))}</th></tr></thead><tbody>${rows}</tbody></table>
            <p class="small muted" style="margin:10px 0 0">${apif ? "출처: API-Football 경기 기록 (승부차기 키커는 표시하지 않음)."
              : muOnly
              ? '출처: <a href="https://en.wikipedia.org/" target="_blank" rel="noopener">위키백과</a> 시즌 문서 (CC BY-SA 4.0). 이 대회는 맨유 득점자만 기록됩니다.'
              : "출처: Fantasy Premier League 경기 기록. 득점 시간 정보는 없습니다."}</p>`
          : `<p class="muted">${emptyMsg}</p>`}
        </div>
        ${apif ? statCard : `<div class="card span-4"><h2>최고 활약</h2>
          ${bonus.length ? `<ul class="bonus">${bonus.map((b) => `<li><b>${esc(b.detail)}</b><span>${esc(b.player)}${b.side === "MU" ? "" : ` <small class="muted">(${esc(m.opponent)})</small>`}</span></li>`).join("")}</ul>
            <p class="small muted" style="margin:10px 0 0">FPL 보너스 점수 (3점 = 경기 최고 활약).${det.potm ? ` 맨유 최고 활약: <b>${esc(det.potm)}</b>.` : ""}</p>` : `<p class="muted">정보 없음</p>`}
        </div>`}
        ${lineupCard(det, m)}
        ${m.season && m.season !== D.season && !det.summary ? "" : `<div class="card span-12"><h2>경기 요약</h2>
          ${det.summary ? `<p class="summary">${esc(det.summary)}</p><p class="small muted" style="margin:8px 0 0">경기 데이터로 자동 작성한 요약입니다 (${esc(det.model || "template")}).</p>` : `<p class="muted">${done ? "다음 데이터 동기화 후 요약이 생성됩니다." : "경기 종료 후 표시됩니다."}</p>`}
        </div>`}
      </div>
      <div class="pager">${prev ? `<a href="#match/${prev.id}">← vs ${esc(prev.opponent)}</a>` : "<span></span>"}${next ? `<a href="#match/${next.id}">vs ${esc(next.opponent)} →</a>` : "<span></span>"}</div>`;
  }

  // ---------- router ----------
  const PAGES = { home: pageHome, fixtures: pageFixtures, table: pageTable, players: pagePlayers, transfers: pageTransfers, history: pageHistory, records: pageRecords, match: pageMatch };
  function render() {
    const [page, arg] = (location.hash.slice(1) || "home").split("/");
    const fn = PAGES[page] || pageHome;
    app.innerHTML = fn(arg);
    const navPage = page === "match" ? "fixtures" : PAGES[page] ? page : "home";
    document.querySelectorAll(".nav a").forEach((a) => a.classList.toggle("active", a.dataset.page === navPage));
    document.querySelector(".nav").classList.remove("open");
    tickCountdown();
  }
  app.addEventListener("click", (e) => {
    const f = e.target.closest("[data-filter]");
    if (f) { fixtureFilter = f.dataset.filter; render(); }
    const fs = e.target.closest("[data-fseason]");
    if (fs) { fixtureSeason = fs.dataset.fseason; fixtureFilter = "ALL"; render(); }
    const t = e.target.closest("[data-table]");
    if (t) { tableComp = t.dataset.table; render(); }
    const ts = e.target.closest("[data-tseason]");
    if (ts) { transferSeason = ts.dataset.tseason; render(); }
    const era = e.target.closest("[data-era]");
    if (era) { recordsEra = era.dataset.era; render(); }
    const pos = e.target.closest("[data-pos]");
    if (pos) { playerPos = pos.dataset.pos; render(); }
    const s = e.target.closest("[data-sort]");
    if (s) {
      const k = s.dataset.sort;
      playerSort = playerSort.key === k ? { key: k, dir: -playerSort.dir } : { key: k, dir: k === "shirt_number" ? 1 : -1 };
      render();
    }
  });
  document.querySelector(".nav-toggle").addEventListener("click", (e) => {
    const nav = document.querySelector(".nav");
    nav.classList.toggle("open");
    e.currentTarget.setAttribute("aria-expanded", nav.classList.contains("open"));
  });
  window.addEventListener("hashchange", () => { render(); window.scrollTo(0, 0); });
  setInterval(tickCountdown, 1000);

  // 헤더 팀 명칭 옆 공식 엠블럼
  document.querySelector(".brand-mark").outerHTML = muCrest("brand-mark");

  const sync = D.synced_utc || (D.last_sync || []).map((s) => s.finished_utc).sort().pop() || D.generated_utc;
  document.getElementById("sync-info").textContent = `마지막 데이터 갱신: ${dateTime(sync, KST)} (한국 시간)`;
  // 다음 동기화 예상 시각 — .github/workflows/sync-and-deploy.yml + scripts/sync_needed.py 규칙과 동일
  //   매일 05:00 UTC 전체 동기화 / 30분마다 점검하되 '킥오프+2시간 지났는데 미종료 경기(최근 3일)'가 있을 때만 동기화
  const SYNC_DONE = ["FINISHED", "POSTPONED", "CANCELLED", "AWARDED", "SUSPENDED"];
  const nextSync = (now) => {
    const open = matches.filter((m) => !SYNC_DONE.includes(m.status) && m.kickoff_confirmed !== 0);
    const kick = (m) => new Date(m.kickoff_utc).getTime();
    if (open.some((m) => kick(m) + 2 * 3600e3 <= now && kick(m) >= now - 3 * 864e5)) return { kind: "awaiting" };
    const d = new Date(now);
    let daily = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate(), 5, 0);
    if (daily <= now) daily += 864e5;
    const nm = open.find((m) => kick(m) + 2 * 3600e3 > now);
    if (nm) {
      const slot = Math.ceil((kick(nm) + 2 * 3600e3) / 1800e3) * 1800e3; // 킥오프+2시간 이후 첫 30분 점검
      if (slot < daily) return { kind: "result", t: slot, m: nm };
    }
    return { kind: "daily", t: daily };
  };

  // 우측 상단 동기화 배지: 지금 보는 데이터의 기준 시각 + 다음 갱신 예정 (36시간 넘게 갱신 없으면 노란색 경고)
  const badge = document.getElementById("sync-badge");
  const renderSync = () => {
    if (!sync) { badge.classList.add("none"); return; }
    const now = Date.now();
    const stale = (now - new Date(sync).getTime()) / 3600e3 > 36;
    badge.classList.toggle("stale", stale);
    const n = nextSync(now);
    const next = n.kind === "awaiting"
      ? `<span class="sb-next">결과 반영 대기<span class="long"> · 30분마다 확인</span></span>`
      : `<span class="sb-next">다음 갱신 <b>~${esc(dateTime(new Date(n.t).toISOString(), KST))}</b>${n.kind === "result" ? `<span class="long"> (${esc(n.m.opponent)}전 후)</span>` : ""}</span>`;
    document.getElementById("sync-text").innerHTML =
      `<span>${stale ? "갱신 지연 · " : ""}데이터 기준 <b>${esc(dateTime(sync, KST))}</b><span class="long"> · ${ago(sync)}</span></span><span class="sb-sep" aria-hidden="true">|</span>${next}`;
    const SRC = { "football-data": "일정·순위", fpl: "선수", rss: "뉴스", deepl: "뉴스 번역", wikipedia: "위키백과", "api-football": "과거 시즌" };
    badge.title = [
      "데이터 기준 = 이 페이지 데이터가 마지막으로 갱신된 시각, 다음 갱신 = 예상 갱신 시각 (모두 한국 시간).",
      "일정: 매일 14:00 전체 갱신 + 경기 후에는 결과가 들어올 때까지 30분마다 확인.",
      "GitHub 예약 실행은 몇 분에서 30분 넘게 늦게 시작될 수 있습니다.",
      "",
      ...(D.last_sync || []).map((s) => `${SRC[s.source] || s.source} (${s.job}): ${dateTime(s.finished_utc, KST)}`),
    ].join("\n");
  };
  renderSync();
  setInterval(renderSync, 60e3);
  render();
})();
