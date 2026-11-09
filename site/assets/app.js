/* Red Devils Matchday — 정적 페이지. 데이터는 data/data.js (scripts/export_site_data.py 로 생성) */
(() => {
  const D = window.MUFC_DATA;
  const app = document.getElementById("app");
  if (!D) {
    app.innerHTML = `<div class="card empty"><b>데이터 파일이 없습니다</b>python scripts/export_site_data.py 를 먼저 실행하세요.</div>`;
    return;
  }

  // ---------- helpers ----------
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const COMP = { PL: "프리미어리그", UCL: "챔피언스리그", UEL: "유로파리그", UECL: "컨퍼런스리그", FAC: "FA컵", ELC: "EFL컵", CS: "커뮤니티실드" };
  const compName = (c) => COMP[c] || D.competitions[c] || c;
  const fmt = (tz, opts) => new Intl.DateTimeFormat("ko-KR", { timeZone: tz, ...opts });
  const KST = "Asia/Seoul", UK = "Europe/London";
  const dateTime = (iso, tz) => fmt(tz, { month: "long", day: "numeric", weekday: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(new Date(iso));
  const shortDate = (iso, tz) => fmt(tz, { month: "numeric", day: "numeric", weekday: "short" }).format(new Date(iso));
  const hm = (iso, tz) => fmt(tz, { hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(new Date(iso));
  const monthKey = (iso) => fmt(KST, { year: "numeric", month: "long" }).format(new Date(iso));
  const ukZone = (iso) => (new Intl.DateTimeFormat("en-GB", { timeZone: UK, timeZoneName: "short" }).format(new Date(iso)).includes("BST") ? "BST" : "GMT");
  const crestImg = (url, alt) => (url ? `<img src="${esc(url)}" alt="${esc(alt)}" loading="lazy">` : "");
  const chip = (r) => `<span class="chip ${r || "pending"}">${{ W: "승", D: "무", L: "패" }[r] || "-"}</span>`;
  const ha = (m) => (m.home_away === "H" ? "홈" : m.home_away === "A" ? "원정" : "중립");

  const matches = D.matches.slice().sort((a, b) => a.kickoff_utc.localeCompare(b.kickoff_utc));
  const finished = matches.filter((m) => m.status === "FINISHED");
  const now = Date.now();
  const upcoming = matches.filter((m) => m.status !== "FINISHED" && !["CANCELLED"].includes(m.status) && new Date(m.kickoff_utc).getTime() > now - 3 * 3600e3);
  const plRow = (D.tables.PL || []).find((r) => r.is_mu);
  const uclRow = (D.tables.UCL || []).find((r) => r.is_mu);

  function scoreText(m) {
    if (m.mu_score == null) return "";
    const [h, a] = m.home_away === "A" ? [m.opp_score, m.mu_score] : [m.mu_score, m.opp_score];
    let s = `${h} - ${a}`;
    if (m.mu_pens != null) {
      const [hp, ap] = m.home_away === "A" ? [m.opp_pens, m.mu_pens] : [m.mu_pens, m.opp_pens];
      s += ` <small class="small">(PK ${hp}-${ap})</small>`;
    }
    return s;
  }

  function matchRow(m) {
    const done = m.status === "FINISHED";
    const right = done
      ? `<div class="score">${scoreText(m)} ${chip(m.result)}</div>`
      : `<div class="score"><div class="tbd">${m.status === "POSTPONED" ? "연기" : m.kickoff_confirmed ? `영국 ${hm(m.kickoff_utc, UK)}` : "시간 미정"}<br>${m.status === "IN_PLAY" || m.status === "PAUSED" ? "<b style='color:var(--red)'>경기 중</b>" : ""}</div></div>`;
    return `<li class="match">
      <div class="when"><b>${shortDate(m.kickoff_utc, KST)}</b><span>한국 ${hm(m.kickoff_utc, KST)}</span></div>
      <div class="who">${crestImg(m.opponent_crest, m.opponent)}
        <div style="min-width:0"><div class="opp">vs ${esc(m.opponent)}</div>
        <div class="sub"><span class="badge ${esc(m.comp)}">${esc(compName(m.comp))}</span><span class="badge ha">${ha(m)}</span>${m.matchday ? `<span class="small muted">${m.comp === "PL" ? m.matchday + "R" : "MD" + m.matchday}</span>` : ""}</div></div>
      </div>
      ${right}
    </li>`;
  }

  // ---------- pages ----------
  function heroNext() {
    const m = upcoming[0];
    if (!m) return `<section class="hero"><div class="eyebrow">다음 경기</div><h2 class="page-title" style="color:#fff">예정된 경기가 없습니다</h2></section>`;
    const home = m.home_away !== "A";
    const mu = `<div class="side"><div class="crest-mu">MU</div><div class="name">MAN UNITED</div><div class="tag">${home ? "HOME" : "AWAY"}</div></div>`;
    const op = `<div class="side">${m.opponent_crest ? `<img class="crest" src="${esc(m.opponent_crest)}" alt="">` : ""}<div class="name">${esc(m.opponent).toUpperCase()}</div><div class="tag">${home ? "AWAY" : "HOME"}</div></div>`;
    return `<section class="hero">
      <div class="eyebrow">다음 경기 · ${esc(compName(m.comp))}${m.matchday ? (m.comp === "PL" ? ` ${m.matchday}라운드` : ` 리그 페이즈 ${m.matchday}차전`) : ""}</div>
      <div class="versus">${home ? mu : op}<div class="vs">VS</div>${home ? op : mu}</div>
      <div class="countdown" id="countdown" data-kickoff="${esc(m.kickoff_utc)}"></div>
      <div class="times">
        <div class="time-box"><div class="label">한국 시간 (KST)</div><div class="val">${dateTime(m.kickoff_utc, KST)}</div></div>
        <div class="time-box"><div class="label">영국 시간 (${ukZone(m.kickoff_utc)})</div><div class="val">${dateTime(m.kickoff_utc, UK)}</div></div>
      </div>
      <div class="meta">${m.venue ? esc(m.venue) + " · " : ""}${m.kickoff_confirmed ? "" : "킥오프 시간 미확정 · "}${home ? "홈 경기" : "원정 경기"}</div>
    </section>`;
  }

  function tickCountdown() {
    const el = document.getElementById("countdown");
    if (!el) return;
    const diff = new Date(el.dataset.kickoff).getTime() - Date.now();
    if (diff <= 0) { el.innerHTML = `<div style="min-width:auto;padding:8px 16px"><b style="font-size:22px">KICK OFF</b><span>경기 진행 중이거나 결과 반영 대기</span></div>`; return; }
    const d = Math.floor(diff / 864e5), h = Math.floor(diff / 36e5) % 24, mi = Math.floor(diff / 6e4) % 60, s = Math.floor(diff / 1e3) % 60;
    const p = (n) => String(n).padStart(2, "0");
    el.innerHTML = [[d, "일"], [p(h), "시간"], [p(mi), "분"], [p(s), "초"]].map(([v, l]) => `<div><b>${v}</b><span>${l}</span></div>`).join("");
  }

  function pageHome() {
    const plForm = finished.filter((m) => m.comp === "PL").slice(-5);
    const recent = finished.slice(-5).reverse();
    const next = upcoming.slice(1, 6);
    const w = finished.filter((m) => m.result === "W").length, d = finished.filter((m) => m.result === "D").length, l = finished.filter((m) => m.result === "L").length;
    const gf = finished.reduce((a, m) => a + (m.mu_score || 0), 0), ga = finished.reduce((a, m) => a + (m.opp_score || 0), 0);
    return `${heroNext()}
    <div class="grid">
      <div class="card span-4">
        <h2>프리미어리그 <small>${esc(D.season)}</small></h2>
        ${plRow ? `<div class="stat-row">
          <div class="stat hl"><b>${plRow.position}위</b><span>순위</span></div>
          <div class="stat"><b>${plRow.points}</b><span>승점</span></div>
          <div class="stat"><b>${plRow.goal_diff > 0 ? "+" : ""}${plRow.goal_diff}</b><span>득실차</span></div></div>
          <p class="small muted" style="margin:10px 0 6px">${plRow.played}경기 ${plRow.won}승 ${plRow.drawn}무 ${plRow.lost}패 · 최근 5경기</p>
          <div class="form">${plForm.map((m) => chip(m.result)).join("")}</div>` : `<p class="muted">순위 데이터 없음</p>`}
        <p style="margin:12px 0 0"><a href="#table" class="small" style="color:var(--red);font-weight:700">전체 순위 →</a></p>
      </div>
      <div class="card span-4">
        <h2>챔피언스리그 <small>리그 페이즈</small></h2>
        ${uclRow ? `<div class="stat-row">
          <div class="stat hl"><b>${uclRow.position}위</b><span>36팀 중</span></div>
          <div class="stat"><b>${uclRow.points}</b><span>승점</span></div>
          <div class="stat"><b>${uclRow.played}</b><span>경기</span></div></div>
          <p class="small muted" style="margin:10px 0 0">${uclRow.position <= 8 ? "16강 직행권" : uclRow.position <= 24 ? "플레이오프권 (9~24위)" : "탈락권 (25위 이하)"} · ${uclRow.won}승 ${uclRow.drawn}무 ${uclRow.lost}패</p>` : `<p class="muted">순위 데이터 없음</p>`}
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
        <ul class="match-list">${next.map(matchRow).join("") || `<li class="empty">예정 경기 없음</li>`}</ul></div>
    </div>`;
  }

  let fixtureFilter = "ALL";
  function pageFixtures() {
    const comps = ["ALL", ...new Set(matches.map((m) => m.comp))];
    const list = matches.filter((m) => fixtureFilter === "ALL" || m.comp === fixtureFilter);
    let html = "", cur = "";
    for (const m of list) {
      const k = monthKey(m.kickoff_utc);
      if (k !== cur) { if (cur) html += "</ul>"; html += `<h3 class="month">${k}</h3><ul class="match-list card" style="padding:4px 14px">`; cur = k; }
      html += matchRow(m);
    }
    if (cur) html += "</ul>";
    return `<h1 class="page-title">일정 · 결과</h1>
      <p class="page-sub">${esc(D.season)} 시즌 · 날짜는 한국 시간 기준, 영국 시간 병기 (서머타임 자동 반영)</p>
      <div class="filters">${comps.map((c) => `<button data-filter="${c}" class="${c === fixtureFilter ? "on" : ""}">${c === "ALL" ? "전체" : compName(c)}</button>`).join("")}</div>
      ${html}
      <p class="small muted">※ 무료 데이터 플랜은 프리미어리그·챔피언스리그만 제공합니다. FA컵·EFL컵 일정은 추후 추가 예정.</p>`;
  }

  let tableComp = "PL";
  function pageTable() {
    const rows = D.tables[tableComp] || [];
    const zone = (p) => tableComp === "PL"
      ? (p <= 4 ? "ucl" : p === 5 ? "uel" : p >= 18 ? "rel" : "")
      : (p <= 8 ? "ucl" : p <= 24 ? "po" : "");
    const legend = tableComp === "PL"
      ? `<span><i class="zone ucl"></i>챔피언스리그</span><span><i class="zone uel"></i>유로파리그</span><span><i class="zone rel"></i>강등</span>`
      : `<span><i class="zone ucl"></i>16강 직행</span><span><i class="zone po"></i>녹아웃 플레이오프</span>`;
    return `<h1 class="page-title">순위</h1><p class="page-sub">${esc(D.season)} 시즌 · 매일 자동 갱신</p>
      <div class="filters">${["PL", "UCL"].map((c) => `<button data-table="${c}" class="${c === tableComp ? "on" : ""}">${compName(c)}</button>`).join("")}</div>
      <div class="card"><div class="table-wrap"><table class="data">
        <thead><tr><th class="l">#</th><th class="l">팀</th><th>경기</th><th>승</th><th>무</th><th>패</th><th>득점</th><th>실점</th><th>득실</th><th>승점</th></tr></thead>
        <tbody>${rows.map((r) => `<tr class="${r.is_mu ? "mu" : ""}">
          <td class="l"><i class="zone ${zone(r.position)}"></i>${r.position}</td>
          <td class="team">${crestImg(r.crest, r.team)}${esc(r.team)}</td>
          <td>${r.played}</td><td>${r.won}</td><td>${r.drawn}</td><td>${r.lost}</td><td>${r.goals_for}</td><td>${r.goals_against}</td>
          <td>${r.goal_diff > 0 ? "+" : ""}${r.goal_diff}</td><td class="pts">${r.points}</td></tr>`).join("")}</tbody>
      </table></div><div class="legend">${legend}</div></div>`;
  }

  function pageEmpty(title, sub, msg) {
    return `<h1 class="page-title">${title}</h1><p class="page-sub">${sub}</p><div class="card empty"><b>데이터 준비 중</b>${msg}</div>`;
  }

  // ----- 선수 -----
  const POS_KO = { GK: "골키퍼", DF: "수비수", MF: "미드필더", FW: "공격수" };
  const AVAIL = { i: ["부상", "st-inj"], s: ["징계", "st-sus"], d: ["출전 불확실", "st-doubt"], n: ["출전 불가", "st-sus"], u: ["이탈", "st-doubt"] };
  const MONTHS = { Jan: 1, Feb: 2, Mar: 3, Apr: 4, May: 5, Jun: 6, Jul: 7, Aug: 8, Sep: 9, Oct: 10, Nov: 11, Dec: 12 };
  function newsKo(s) {
    if (!s) return "";
    let m;
    if ((m = s.match(/^Suspended until (\d+) (\w{3})/))) return `${MONTHS[m[2]] || m[2]}월 ${m[1]}일까지 출전 정지`;
    if ((m = s.match(/^Has joined (.+?) on loan/))) return `${m[1]}(으)로 임대`;
    if ((m = s.match(/^Has joined (.+?) permanently/))) return `${m[1]}(으)로 완전 이적`;
    return s.replace(/Unknown return date/i, "복귀 시점 미정").replace(/Expected back (\d+) (\w{3})/, (_, d, mo) => `${MONTHS[mo] || mo}월 ${d}일 복귀 예상`)
      .replace(/(\d+)% chance of playing/, "출전 가능성 $1%")
      .replace(/Hamstring injury/i, "햄스트링 부상").replace(/Knee injury/i, "무릎 부상").replace(/Ankle injury/i, "발목 부상")
      .replace(/Hip injury/i, "엉덩이(고관절) 부상").replace(/Shin injury/i, "정강이 부상").replace(/Groin injury/i, "사타구니 부상")
      .replace(/Calf injury/i, "종아리 부상").replace(/Thigh injury/i, "허벅지 부상").replace(/Foot injury/i, "발 부상")
      .replace(/Back injury/i, "허리 부상").replace(/Muscle injury/i, "근육 부상").replace(/Illness/i, "질병")
      .replace(/Unspecified injury/i, "부상(부위 미공개)").replace(/Knock/i, "타박상");
  }
  const age = (dob) => {
    if (!dob) return "";
    const b = new Date(dob), n = new Date();
    return n.getFullYear() - b.getFullYear() - (n < new Date(n.getFullYear(), b.getMonth(), b.getDate()) ? 1 : 0);
  };
  const pName = (p) => p.name_ko || p.known_as || p.full_name;
  const photo = (p, cls = "pthumb") => `<img class="${cls}" src="${esc(p.photo_url)}" alt="" loading="lazy" onerror="this.style.visibility='hidden'">`;

  let playerPos = "ALL", playerSort = { key: "goals", dir: -1 };
  const COLS = [
    ["shirt_number", "#", 1], ["appearances", "출전"], ["starts", "선발"], ["minutes", "분"], ["goals", "골"], ["assists", "도움"],
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
        <div class="small muted">${POS_KO[p.position] || ""}${p.shirt_number ? " · " + p.shirt_number + "번" : ""}</div></div></div>`;
    };
    const out = active.filter((p) => ["i", "s", "d", "n"].includes(p.avail));

    const list = active.filter((p) => playerPos === "ALL" || p.position === playerPos)
      .sort((a, b) => {
        const k = playerSort.key, va = a[k] ?? -1, vb = b[k] ?? -1;
        return (va - vb) * playerSort.dir || b.minutes - a.minutes;
      });
    const th = ([k, l]) => `<th data-sort="${k}" class="sortable${playerSort.key === k ? " on" : ""}">${l}${playerSort.key === k ? (playerSort.dir < 0 ? " ▾" : " ▴") : ""}</th>`;

    return `<h1 class="page-title">선수 통계</h1>
      <p class="page-sub">${esc(D.season)} 프리미어리그 · 맨유 경기 기록만 집계 (챔스 등 다른 대회 제외)</p>
      <div class="grid">${leader("goals", "팀 내 최다 득점", "골")}${leader("assists", "팀 내 최다 도움", "도움")}${leader("minutes", "최다 출전 시간", "분")}</div>
      ${out.length ? `<div class="card" style="margin-bottom:16px"><h2>부상 · 징계 <small>${out.length}명</small></h2><div class="injuries">
        ${out.map((p) => `<div class="inj-card">${photo(p)}<div style="min-width:0"><b>${esc(pName(p))}</b> <span class="badge ${AVAIL[p.avail][1]}">${AVAIL[p.avail][0]}</span>
          <div class="small muted">${esc(newsKo(p.news))}</div></div></div>`).join("")}</div></div>` : ""}
      <div class="filters">${["ALL", "GK", "DF", "MF", "FW"].map((c) => `<button data-pos="${c}" class="${c === playerPos ? "on" : ""}">${c === "ALL" ? "전체" : POS_KO[c]}</button>`).join("")}</div>
      <div class="card"><div class="table-wrap"><table class="data players">
        <thead><tr>${th(COLS[0])}<th class="l">선수</th>${COLS.slice(1).map(th).join("")}</tr></thead>
        <tbody>${list.map((p) => `<tr class="${p.minutes ? "" : "dim"}">
          <td>${p.shirt_number ?? ""}</td>
          <td class="team">${photo(p)}<div><b>${esc(pName(p))}</b>${p.avail && AVAIL[p.avail] && p.avail !== "u" ? ` <span class="dot ${AVAIL[p.avail][1]}" title="${esc(newsKo(p.news))}"></span>` : ""}
            <div class="small muted">${p.position}${age(p.date_of_birth) !== "" ? " · " + age(p.date_of_birth) + "세" : ""}</div></div></td>
          <td>${p.appearances}</td><td>${p.starts}</td><td>${p.minutes}</td><td class="pts">${p.goals}</td><td class="pts">${p.assists}</td>
          <td>${p.xg != null ? p.xg.toFixed(2) : "–"}</td><td>${p.xa != null ? p.xa.toFixed(2) : "–"}</td><td>${p.yellow_cards}</td><td>${p.red_cards}</td></tr>`).join("")}</tbody>
      </table></div><p class="small muted" style="margin:10px 0 0">열 제목을 누르면 정렬됩니다. xG = 기대 득점, xA = 기대 도움 (FPL 제공 수치)</p></div>
      ${gone.length ? `<div class="card" style="margin-top:16px"><h2>임대 · 이적으로 이탈 <small>${gone.length}명</small></h2><ul class="match-list">
        ${gone.map((p) => `<li class="match" style="grid-template-columns:1fr"><div><b>${esc(pName(p))}</b> <span class="small muted">${p.position}</span><div class="small muted">${esc(newsKo(p.news))}</div></div></li>`).join("")}</ul></div>` : ""}`;
  }

  function pageTransfers() {
    if (!D.transfers.length) return pageEmpty("이적 현황", "영입 · 방출 · 임대", "이적 데이터 수집(etl/fetch_transfers.py) 이후 표시됩니다.");
    return `<h1 class="page-title">이적 현황</h1><div class="card"><div class="table-wrap"><table class="data"><thead><tr><th class="l">날짜</th><th class="l">선수</th><th class="l">구분</th><th class="l">이전 → 이후</th><th>이적료</th></tr></thead>
      <tbody>${D.transfers.map((t) => `<tr><td class="l">${esc(t.transfer_date)}</td><td class="l">${esc(t.player_name)}</td><td class="l">${t.direction === "in" ? "영입" : "방출"}</td><td class="l">${esc(t.from_club)} → ${esc(t.to_club)}</td><td>${esc(t.fee_text || "-")}</td></tr>`).join("")}</tbody></table></div></div>`;
  }

  const TROPHY_KO = { PL: "리그 우승", FL1: "리그 우승", FAC: "FA컵", ELC: "리그컵", UCL: "유러피언컵 · 챔스", UEL: "유로파리그", UCWC: "컵위너스컵", USC: "UEFA 슈퍼컵", ICC: "인터콘티넨털컵", CWC: "클럽월드컵", CS: "커뮤니티실드" };
  function pageHistory() {
    const c = D.club;
    const counts = {};
    for (const h of D.honours_count) { const k = TROPHY_KO[h.code] || h.name; counts[k] = (counts[k] || 0) + h.titles; }
    const lastWin = (codes) => D.honours.filter((h) => codes.includes(h.code)).map((h) => h.season).sort().pop();
    const codesOf = (k) => Object.keys(TROPHY_KO).filter((c) => TROPHY_KO[c] === k);
    return `<h1 class="page-title">클럽 역사</h1>
      <p class="page-sub">${esc(c.founded_year)}년 ${esc(c.founded_as)}로 창단 · ${esc(c.city)} · 홈구장 ${esc(c.stadium)} (약 ${Number(c.stadium_capacity).toLocaleString()}석)</p>
      <div class="card" style="margin-bottom:16px"><h2>우승 기록</h2><div class="trophies">
        ${Object.entries(counts).map(([k, n]) => `<div class="trophy"><b>${n}</b><span>${esc(k)}</span><small>최근 ${esc(lastWin(codesOf(k)) || "-")}</small></div>`).join("")}
      </div></div>
      <div class="grid">
        <div class="card span-8"><h2>주요 연표</h2><ul class="timeline">
          ${D.timeline.map((t) => `<li class="${t.category === "trophy" ? "trophy-ev" : ""}"><div class="yr">${t.year}</div><div class="ttl">${esc(t.title_ko || t.title)}</div>${t.body_ko ? `<div class="small muted">${esc(t.body_ko)}</div>` : ""}</li>`).join("")}
        </ul></div>
        <div class="card span-4"><h2>역대 주요 감독</h2><ul class="match-list">
          ${D.managers.slice().reverse().map((m) => `<li class="match" style="grid-template-columns:1fr auto"><div><b>${esc(m.name_ko || m.name)}</b>${m.is_caretaker ? ' <span class="badge ha">대행</span>' : ""}<div class="small muted">${esc(m.note && !m.note.startsWith("end_date") ? m.note : "")}</div></div><div class="small muted" style="text-align:right">${esc(m.start_date)} ~<br>${esc(m.end_date || "")}</div></li>`).join("")}
        </ul></div>
      </div>`;
  }

  function pageRecords() {
    const rows = D.seasons.filter((s) => s.comp === "PL").slice().reverse();
    const cls = (p) => (p === 1 ? "p1" : p <= 4 ? "top4" : p >= 15 ? "low" : "");
    const titles = rows.filter((r) => r.position === 1 && r.is_final).length;
    return `<h1 class="page-title">시즌별 기록</h1><p class="page-sub">프리미어리그 출범(1992-93) 이후 · PL 우승 ${titles}회</p>
      <div class="card"><div class="table-wrap"><table class="data">
        <thead><tr><th class="l">시즌</th><th class="l">순위</th><th>경기</th><th>승</th><th>무</th><th>패</th><th>득점</th><th>실점</th><th>승점</th><th class="l">비고</th></tr></thead>
        <tbody>${rows.map((r) => `<tr class="${r.is_final ? "" : "mu"}"><td class="l">${esc(r.season)}</td><td class="l"><span class="pos ${cls(r.position)}">${r.position ?? "-"}</span></td>
          <td>${r.played ?? "–"}</td><td>${r.won ?? "–"}</td><td>${r.drawn ?? "–"}</td><td>${r.lost ?? "–"}</td><td>${r.goals_for ?? "–"}</td><td>${r.goals_against ?? "–"}</td><td class="pts">${r.points ?? "–"}</td>
          <td class="l small muted">${r.is_final ? (r.position === 1 ? "🏆 우승" : "") : "진행 중"}${r.europe_result ? " · " + esc(r.europe_result) : ""}</td></tr>`).join("")}</tbody>
      </table></div>
      <p class="small muted" style="margin-top:10px">※ 과거 시즌 상세 수치(승·무·패·승점)는 백필 스크립트로 채울 예정입니다. 1992 이전 기록도 추가 예정.</p></div>`;
  }

  // ---------- router ----------
  const PAGES = { home: pageHome, fixtures: pageFixtures, table: pageTable, players: pagePlayers, transfers: pageTransfers, history: pageHistory, records: pageRecords };
  function render() {
    const page = (location.hash.slice(1) || "home").split("/")[0];
    const fn = PAGES[page] || pageHome;
    app.innerHTML = fn();
    document.querySelectorAll(".nav a").forEach((a) => a.classList.toggle("active", a.dataset.page === (PAGES[page] ? page : "home")));
    document.querySelector(".nav").classList.remove("open");
    tickCountdown();
  }
  app.addEventListener("click", (e) => {
    const f = e.target.closest("[data-filter]");
    if (f) { fixtureFilter = f.dataset.filter; render(); }
    const t = e.target.closest("[data-table]");
    if (t) { tableComp = t.dataset.table; render(); }
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

  const sync = (D.last_sync || []).map((s) => s.finished_utc).sort().pop() || D.generated_utc;
  document.getElementById("sync-info").textContent = `마지막 데이터 갱신: ${dateTime(sync, KST)} (한국 시간)`;
  render();
})();
