/* Red Devils Matchday — 정적 페이지. 데이터는 data/data.js (scripts/export_site_data.py 로 생성)
   표기 규칙: 헤드라인(h1·h2·h3·메뉴)은 한글, 본문은 영문. */
(() => {
  const D = window.MUFC_DATA;
  const app = document.getElementById("app");
  if (!D) {
    app.innerHTML = `<div class="card empty"><b>No data file</b>Run python scripts/export_site_data.py first.</div>`;
    return;
  }

  // ---------- helpers ----------
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  // 헤드라인용(한글) / 본문용(영문) 대회명
  const COMP_KO = { PL: "프리미어리그", UCL: "챔피언스리그", UEL: "유로파리그", UECL: "컨퍼런스리그", FAC: "FA컵", ELC: "EFL컵", CS: "커뮤니티실드" };
  const COMP_EN = { PL: "Premier League", UCL: "Champions League", UEL: "Europa League", UECL: "Conference League", FAC: "FA Cup", ELC: "EFL Cup", CS: "Community Shield" };
  const compKo = (c) => COMP_KO[c] || c;
  const compEn = (c) => COMP_EN[c] || c;
  const fmt = (tz, opts, loc = "en-GB") => new Intl.DateTimeFormat(loc, { timeZone: tz, ...opts });
  const KST = "Asia/Seoul", UK = "Europe/London";
  const dateTime = (iso, tz) => fmt(tz, { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(new Date(iso));
  const shortDate = (iso, tz) => fmt(tz, { weekday: "short", day: "numeric", month: "short" }).format(new Date(iso));
  const hm = (iso, tz) => fmt(tz, { hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(new Date(iso));
  const monthKey = (iso) => fmt(KST, { year: "numeric", month: "long" }, "ko-KR").format(new Date(iso)); // 월 헤드라인(한글)
  const ukZone = (iso) => (fmt(UK, { timeZoneName: "short" }).format(new Date(iso)).includes("BST") ? "BST" : "GMT");
  const ord = (n) => { const s = ["th", "st", "nd", "rd"], v = n % 100; return n + (s[(v - 20) % 10] || s[v] || s[0]); };
  const crestImg = (url, alt) => (url ? `<img src="${esc(url)}" alt="${esc(alt)}" loading="lazy">` : "");
  const chip = (r) => `<span class="chip ${r || "pending"}">${r || "-"}</span>`;
  const ha = (m) => (m.home_away === "H" ? "Home" : m.home_away === "A" ? "Away" : "Neutral");

  // 맨유 공식 엠블럼 (football-data 서버 이미지 링크, 불러오기 실패 시 'MU' 마크로 대체)
  const MU_CREST = D.mu_crest;
  const muCrest = (cls) => MU_CREST
    ? `<img class="${cls}" src="${esc(MU_CREST)}" alt="Manchester United crest" onerror="this.outerHTML='<span class=&quot;${cls} crest-fallback&quot;>MU</span>'">`
    : `<span class="${cls} crest-fallback">MU</span>`;
  const title = (t) => `<h1 class="page-title with-crest">${muCrest("title-crest")}<span>${t}</span></h1>`;

  // 킥오프 시각 미정(위키백과 컵 경기 등)이면 날짜만
  const koTime = (m, tz) => (m.kickoff_confirmed ? dateTime(m.kickoff_utc, tz) : `${shortDate(m.kickoff_utc, tz)} · TBC`);
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
      s += ` <small class="small">(pens ${hp}-${ap})</small>`;
    }
    return s;
  }

  function matchRow(m) {
    const done = m.status === "FINISHED";
    const live = m.status === "IN_PLAY" || m.status === "PAUSED";
    const right = done
      ? `<a class="score score-link" href="#match/${m.id}" title="Match details">${scoreText(m)} ${chip(m.result)}<span class="more">Details ›</span></a>`
      : `<div class="score"><div class="tbd">${m.status === "POSTPONED" ? "Postponed" : m.kickoff_confirmed ? `UK ${hm(m.kickoff_utc, UK)}` : "TBC"}<br>${live ? "<b style='color:var(--red)'>LIVE</b>" : ""}</div></div>`;
    return `<li class="match">
      <div class="when"><b>${shortDate(m.kickoff_utc, KST)}</b><span>${m.kickoff_confirmed ? `KST ${hm(m.kickoff_utc, KST)}` : "Time TBC"}</span></div>
      <div class="who">${crestImg(m.opponent_crest, m.opponent)}
        <div style="min-width:0"><div class="opp">vs ${esc(m.opponent)}</div>
        <div class="sub"><span class="badge ${esc(m.comp)}">${esc(compEn(m.comp))}</span><span class="badge ha">${ha(m)}</span>${m.matchday ? `<span class="small muted">${m.comp === "PL" ? "MW" + m.matchday : "MD" + m.matchday}</span>` : ""}</div></div>
      </div>
      ${right}
    </li>`;
  }

  // ---------- pages ----------
  function heroNext() {
    const m = upcoming[0];
    if (!m) return `<section class="hero"><div class="eyebrow">다음 경기</div><p class="hero-empty">No upcoming fixtures scheduled.</p></section>`;
    const home = m.home_away !== "A";
    const mu = `<div class="side">${muCrest("crest crest-mu-img")}<div class="name">MAN UNITED</div><div class="tag">${home ? "HOME" : "AWAY"}</div></div>`;
    const op = `<div class="side">${m.opponent_crest ? `<img class="crest" src="${esc(m.opponent_crest)}" alt="">` : ""}<div class="name">${esc(m.opponent).toUpperCase()}</div><div class="tag">${home ? "AWAY" : "HOME"}</div></div>`;
    return `<section class="hero">
      <div class="eyebrow">다음 경기 · ${esc(compKo(m.comp))}${m.matchday ? (m.comp === "PL" ? ` ${m.matchday}라운드` : ` 리그 페이즈 ${m.matchday}차전`) : ""}</div>
      <div class="versus">${home ? mu : op}<div class="vs">VS</div>${home ? op : mu}</div>
      <div class="countdown" id="countdown" data-kickoff="${esc(m.kickoff_utc)}"></div>
      <div class="times">
        <div class="time-box"><div class="label">Korea time (KST)</div><div class="val">${koTime(m, KST)}</div></div>
        <div class="time-box"><div class="label">UK time (${ukZone(m.kickoff_utc)})</div><div class="val">${koTime(m, UK)}</div></div>
      </div>
      <div class="meta">${m.venue ? esc(m.venue) + " · " : ""}${m.kickoff_confirmed ? "" : "Kick-off time TBC · "}${home ? "Home match" : "Away match"}</div>
    </section>`;
  }

  function tickCountdown() {
    const el = document.getElementById("countdown");
    if (!el) return;
    const diff = new Date(el.dataset.kickoff).getTime() - Date.now();
    if (diff <= 0) { el.innerHTML = `<div style="min-width:auto;padding:8px 16px"><b style="font-size:22px">KICK OFF</b><span>In play or awaiting result</span></div>`; return; }
    const d = Math.floor(diff / 864e5), h = Math.floor(diff / 36e5) % 24, mi = Math.floor(diff / 6e4) % 60, s = Math.floor(diff / 1e3) % 60;
    const p = (n) => String(n).padStart(2, "0");
    el.innerHTML = [[d, "Days"], [p(h), "Hours"], [p(mi), "Mins"], [p(s), "Secs"]].map(([v, l]) => `<div><b>${v}</b><span>${l}</span></div>`).join("");
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
          <div class="stat hl"><b>${ord(plRow.position)}</b><span>Position</span></div>
          <div class="stat"><b>${plRow.points}</b><span>Points</span></div>
          <div class="stat"><b>${plRow.goal_diff > 0 ? "+" : ""}${plRow.goal_diff}</b><span>Goal diff</span></div></div>
          <p class="small muted" style="margin:10px 0 6px">P${plRow.played} · W${plRow.won} D${plRow.drawn} L${plRow.lost} · Last 5</p>
          <div class="form">${plForm.map((m) => chip(m.result)).join("")}</div>` : `<p class="muted">No standings data</p>`}
        <p style="margin:12px 0 0"><a href="#table" class="small" style="color:var(--red);font-weight:700">Full table →</a></p>
      </div>
      <div class="card span-4">
        <h2>챔피언스리그 <small>리그 페이즈</small></h2>
        ${uclRow ? `<div class="stat-row">
          <div class="stat hl"><b>${ord(uclRow.position)}</b><span>of 36</span></div>
          <div class="stat"><b>${uclRow.points}</b><span>Points</span></div>
          <div class="stat"><b>${uclRow.played}</b><span>Played</span></div></div>
          <p class="small muted" style="margin:10px 0 0">${uclRow.position <= 8 ? "Direct to round of 16" : uclRow.position <= 24 ? "Knockout play-off zone (9th–24th)" : "Elimination zone (25th+)"} · W${uclRow.won} D${uclRow.drawn} L${uclRow.lost}</p>` : `<p class="muted">No standings data</p>`}
      </div>
      <div class="card span-4">
        <h2>시즌 전체 <small>PL + UCL</small></h2>
        <div class="stat-row">
          <div class="stat"><b>${w}</b><span>Won</span></div><div class="stat"><b>${d}</b><span>Drawn</span></div><div class="stat"><b>${l}</b><span>Lost</span></div></div>
        <p class="small muted" style="margin:10px 0 0">${finished.length} matches · ${gf} scored, ${ga} conceded</p>
      </div>
      <div class="card span-6"><div class="section-head"><h2>최근 결과</h2><a href="#fixtures">View all →</a></div>
        <ul class="match-list">${recent.map(matchRow).join("")}</ul></div>
      <div class="card span-6"><div class="section-head"><h2>다가오는 경기</h2><a href="#fixtures">Full schedule →</a></div>
        <ul class="match-list">${next.map(matchRow).join("") || `<li class="empty">No upcoming fixtures</li>`}</ul></div>
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
    return `${title("일정 · 결과")}
      <p class="page-sub">${esc(D.season)} season · Dates in Korea time (KST) with UK time alongside (daylight saving applied automatically)</p>
      <div class="filters">${comps.map((c) => `<button data-filter="${c}" class="${c === fixtureFilter ? "on" : ""}">${c === "ALL" ? "All" : compEn(c)}</button>`).join("")}</div>
      ${html}
      <p class="small muted">* The free data plan only covers the Premier League and Champions League. FA Cup and EFL Cup fixtures will be added later.</p>`;
  }

  let tableComp = "PL";
  function pageTable() {
    const rows = D.tables[tableComp] || [];
    const zone = (p) => tableComp === "PL"
      ? (p <= 4 ? "ucl" : p === 5 ? "uel" : p >= 18 ? "rel" : "")
      : (p <= 8 ? "ucl" : p <= 24 ? "po" : "");
    const legend = tableComp === "PL"
      ? `<span><i class="zone ucl"></i>Champions League</span><span><i class="zone uel"></i>Europa League</span><span><i class="zone rel"></i>Relegation</span>`
      : `<span><i class="zone ucl"></i>Round of 16</span><span><i class="zone po"></i>Knockout play-off</span>`;
    return `${title("순위")}<p class="page-sub">${esc(D.season)} season · Updated automatically every day</p>
      <div class="filters">${["PL", "UCL"].map((c) => `<button data-table="${c}" class="${c === tableComp ? "on" : ""}">${compEn(c)}</button>`).join("")}</div>
      <div class="card"><div class="table-wrap"><table class="data">
        <thead><tr><th class="l">#</th><th class="l">Team</th><th>P</th><th>W</th><th>D</th><th>L</th><th>GF</th><th>GA</th><th>GD</th><th>Pts</th></tr></thead>
        <tbody>${rows.map((r) => `<tr class="${r.is_mu ? "mu" : ""}">
          <td class="l"><i class="zone ${zone(r.position)}"></i>${r.position}</td>
          <td class="team">${crestImg(r.crest, r.team)}${esc(r.team)}</td>
          <td>${r.played}</td><td>${r.won}</td><td>${r.drawn}</td><td>${r.lost}</td><td>${r.goals_for}</td><td>${r.goals_against}</td>
          <td>${r.goal_diff > 0 ? "+" : ""}${r.goal_diff}</td><td class="pts">${r.points}</td></tr>`).join("")}</tbody>
      </table></div><div class="legend">${legend}</div></div>`;
  }

  function pageEmpty(t, sub, msg) {
    return `${title(t)}<p class="page-sub">${sub}</p><div class="card empty"><b>Coming soon</b>${msg}</div>`;
  }

  // ----- 선수 -----
  const POS_EN = { GK: "Goalkeeper", DF: "Defender", MF: "Midfielder", FW: "Forward" };
  const POS_PL = { GK: "Goalkeepers", DF: "Defenders", MF: "Midfielders", FW: "Forwards" };
  const AVAIL = { i: ["Injured", "st-inj"], s: ["Suspended", "st-sus"], d: ["Doubtful", "st-doubt"], n: ["Unavailable", "st-sus"], u: ["Left", "st-doubt"] };
  const age = (dob) => {
    if (!dob) return "";
    const b = new Date(dob), n = new Date();
    return n.getFullYear() - b.getFullYear() - (n < new Date(n.getFullYear(), b.getMonth(), b.getDate()) ? 1 : 0);
  };
  const pName = (p) => p.known_as || p.full_name;
  const photo = (p, cls = "pthumb") => `<img class="${cls}" src="${esc(p.photo_url)}" alt="" loading="lazy" onerror="this.style.visibility='hidden'">`;

  let playerPos = "ALL", playerSort = { key: "goals", dir: -1 };
  const COLS = [
    ["shirt_number", "#", 1], ["appearances", "Apps"], ["starts", "Starts"], ["minutes", "Mins"], ["goals", "Goals"], ["assists", "Assists"],
    ["xg", "xG"], ["xa", "xA"], ["yellow_cards", "YC"], ["red_cards", "RC"],
  ];

  function pagePlayers() {
    if (!D.players.length) return pageEmpty("선수 통계", `${esc(D.season)} season`, "Shown after running python etl/fetch_players.py.");
    const active = D.players.filter((p) => p.squad_status === "active");
    const gone = D.players.filter((p) => p.squad_status !== "active");
    const leader = (key, label, unit) => {
      const p = active.slice().sort((a, b) => (b[key] || 0) - (a[key] || 0) || b.minutes - a.minutes)[0];
      return `<div class="card span-4 leader">${photo(p, "lphoto")}<div><div class="small muted">${label}</div>
        <div class="lval">${p[key]}<small>${unit}</small></div><div class="lname">${esc(pName(p))}</div>
        <div class="small muted">${POS_EN[p.position] || ""}${p.shirt_number ? " · No. " + p.shirt_number : ""}</div></div></div>`;
    };
    const out = active.filter((p) => ["i", "s", "d", "n"].includes(p.avail));

    const list = active.filter((p) => playerPos === "ALL" || p.position === playerPos)
      .sort((a, b) => {
        const k = playerSort.key, va = a[k] ?? -1, vb = b[k] ?? -1;
        return (va - vb) * playerSort.dir || b.minutes - a.minutes;
      });
    const th = ([k, l]) => `<th data-sort="${k}" class="sortable${playerSort.key === k ? " on" : ""}">${l}${playerSort.key === k ? (playerSort.dir < 0 ? " ▾" : " ▴") : ""}</th>`;

    return `${title("선수 통계")}
      <p class="page-sub">${esc(D.season)} Premier League · Manchester United matches only (other competitions excluded)</p>
      <div class="grid">${leader("goals", "Top scorer", " goals")}${leader("assists", "Most assists", " assists")}${leader("minutes", "Most minutes", " mins")}</div>
      ${out.length ? `<div class="card" style="margin-bottom:16px"><h2>부상 · 징계 <small>${out.length}명</small></h2><div class="injuries">
        ${out.map((p) => `<div class="inj-card">${photo(p)}<div style="min-width:0"><b>${esc(pName(p))}</b> <span class="badge ${AVAIL[p.avail][1]}">${AVAIL[p.avail][0]}</span>
          <div class="small muted">${esc(p.news)}</div></div></div>`).join("")}</div></div>` : ""}
      <div class="filters">${["ALL", "GK", "DF", "MF", "FW"].map((c) => `<button data-pos="${c}" class="${c === playerPos ? "on" : ""}">${c === "ALL" ? "All" : POS_PL[c]}</button>`).join("")}</div>
      <div class="card"><div class="table-wrap"><table class="data players">
        <thead><tr>${th(COLS[0])}<th class="l">Player</th>${COLS.slice(1).map(th).join("")}</tr></thead>
        <tbody>${list.map((p) => `<tr class="${p.minutes ? "" : "dim"}">
          <td>${p.shirt_number ?? ""}</td>
          <td class="team">${photo(p)}<div><b>${esc(pName(p))}</b>${p.avail && AVAIL[p.avail] && p.avail !== "u" ? ` <span class="dot ${AVAIL[p.avail][1]}" title="${esc(p.news)}"></span>` : ""}
            <div class="small muted">${p.position}${age(p.date_of_birth) !== "" ? " · Age " + age(p.date_of_birth) : ""}</div></div></td>
          <td>${p.appearances}</td><td>${p.starts}</td><td>${p.minutes}</td><td class="pts">${p.goals}</td><td class="pts">${p.assists}</td>
          <td>${p.xg != null ? p.xg.toFixed(2) : "–"}</td><td>${p.xa != null ? p.xa.toFixed(2) : "–"}</td><td>${p.yellow_cards}</td><td>${p.red_cards}</td></tr>`).join("")}</tbody>
      </table></div><p class="small muted" style="margin:10px 0 0">Click a column header to sort. xG = expected goals, xA = expected assists (FPL figures).</p></div>
      ${gone.length ? `<div class="card" style="margin-top:16px"><h2>임대 · 이적으로 이탈 <small>${gone.length}명</small></h2><ul class="match-list">
        ${gone.map((p) => `<li class="match" style="grid-template-columns:1fr"><div><b>${esc(pName(p))}</b> <span class="small muted">${p.position}</span><div class="small muted">${esc(p.news)}</div></div></li>`).join("")}</ul></div>` : ""}`;
  }

  let transferSeason = null;
  const TT_EN = { permanent: "Transfer", free: "Free", release: "Released", loan: "Loan", loan_return: "Loan return", youth_promotion: "Academy" };
  const VERIFY = { verified: ["vf-ok", "✓ Official"], consistent: ["vf-none", "No conflict"], unverified: ["vf-none", "Unverified"], conflict: ["vf-bad", "⚠ Mismatch"] };
  function verifyBadge(t) {
    const v = VERIFY[t.verify_status];
    return v ? `<span class="badge ${v[0]}" title="${esc(t.verify_note || "")}">${v[1]}</span>` : '<span class="small muted">-</span>';
  }
  const CHECK_EN = { missing_in: "Joined per official data, missing from Wikipedia signings", missing_out: "Left / on loan per official data, missing from Wikipedia departures", conflict: "Wikipedia and official squad disagree" };
  function pageTransfers() {
    if (!D.transfers.length) return pageEmpty("이적 현황", "Signings · Departures · Loans", "No transfer data yet.");
    const seasons = [...new Set(D.transfers.map((t) => t.season).filter(Boolean))].sort().reverse();
    if (!transferSeason || !seasons.includes(transferSeason)) transferSeason = seasons[0];
    const list = D.transfers.filter((t) => t.season === transferSeason);
    const checks = (D.transfer_checks || []).filter((c) => c.season === transferSeason);
    const groups = [
      ["영입", "Signings", list.filter((t) => t.direction === "in" && t.transfer_type !== "loan"), "from_club", "From"],
      ["임대 영입", "Loans in", list.filter((t) => t.direction === "in" && t.transfer_type === "loan"), "from_club", "From"],
      ["방출", "Departures", list.filter((t) => t.direction === "out" && t.transfer_type !== "loan"), "to_club", "To"],
      ["임대 이적", "Loans out", list.filter((t) => t.direction === "out" && t.transfer_type === "loan"), "to_club", "To"],
    ].filter((g) => g[2].length);
    const fromWiki = list.some((t) => (t.source || "").startsWith("wikipedia"));
    return `${title("이적 현황")}<p class="page-sub">${esc(transferSeason)} · ${list.filter((t) => t.direction === "in").length} in · ${list.filter((t) => t.direction === "out").length} out</p>
      <div class="filters">${seasons.map((s) => `<button data-tseason="${esc(s)}" class="${s === transferSeason ? "on" : ""}">${esc(s)}</button>`).join("")}</div>
      ${groups.map(([ko, en, rows, clubKey, clubLabel]) => `<div class="card" style="margin-bottom:16px"><h2>${ko} <small>${en} · ${rows.length}</small></h2>
        <div class="table-wrap"><table class="data"><thead><tr><th class="l">Date</th><th class="l">Pos</th><th class="l">Player</th><th class="l">${clubLabel}</th><th class="l">Type</th><th class="l">Fee / Note</th><th class="l">Check</th></tr></thead>
        <tbody>${rows.slice().sort((a, b) => (a.transfer_date < b.transfer_date ? 1 : -1)).map((t) => `<tr><td class="l small">${esc(t.transfer_date)}</td><td class="l small">${esc(t.position || "")}</td>
          <td class="l"><b>${esc(t.player_name)}</b></td><td class="l">${esc(t[clubKey] || "-")}</td><td class="l small">${esc(TT_EN[t.transfer_type] || t.transfer_type || "")}</td><td class="l small muted">${esc(t.fee_text || "-")}</td><td class="l">${verifyBadge(t)}</td></tr>`).join("")}</tbody></table></div></div>`).join("")}
      ${checks.length ? `<div class="card" style="margin-bottom:16px"><h2>확인 필요 <small>Data checks · ${checks.length}</small></h2><ul class="match-list">${checks.map((c) => `<li class="match" style="grid-template-columns:1fr auto"><div><b>${esc(c.player_name)}</b><div class="small muted">${esc(CHECK_EN[c.kind] || c.kind)}</div></div><div class="small muted">${esc((c.first_seen_utc || "").slice(0, 10))}</div></li>`).join("")}</ul></div>` : ""}
      ${fromWiki ? `<p class="small muted">Source: <a href="${esc(list.find((t) => t.source_url)?.source_url || "https://en.wikipedia.org/")}" target="_blank" rel="noopener">Wikipedia</a> season article (CC BY-SA 4.0), cross-checked daily against the official first-team squad (football-data.org) and Fantasy Premier League player status. <b>✓ Official</b> = confirmed by official squad data · <b>No conflict</b> = departure not contradicted (player not in the official squad), but no direct official record · <b>Unverified</b> = player outside the first-team squad (e.g. academy), cannot be checked · <b>⚠ Mismatch</b> = Wikipedia and official data disagree. Fees are usually undisclosed officially.</p>` : ""}`;
  }

  const TROPHY_EN = { PL: "League titles", FL1: "League titles", FAC: "FA Cup", ELC: "League Cup", UCL: "European Cup / UCL", UEL: "Europa League", UCWC: "Cup Winners' Cup", USC: "UEFA Super Cup", ICC: "Intercontinental Cup", CWC: "Club World Cup", CS: "Community Shield" };
  function pageHistory() {
    const c = D.club;
    const counts = {};
    for (const h of D.honours_count) { const k = TROPHY_EN[h.code] || h.name; counts[k] = (counts[k] || 0) + h.titles; }
    const lastWin = (codes) => D.honours.filter((h) => codes.includes(h.code)).map((h) => h.season).sort().pop();
    const codesOf = (k) => Object.keys(TROPHY_EN).filter((c) => TROPHY_EN[c] === k);
    return `${title("클럽 역사")}
      <p class="page-sub">Founded in ${esc(c.founded_year)} as ${esc(c.founded_as)} · ${esc(c.city)} · Home ground: ${esc(c.stadium)} (approx. ${Number(c.stadium_capacity).toLocaleString("en-GB")} seats)</p>
      <div class="card" style="margin-bottom:16px"><h2>우승 기록</h2><div class="trophies">
        ${Object.entries(counts).map(([k, n]) => `<div class="trophy"><b>${n}</b><span>${esc(k)}</span><small>Last: ${esc(lastWin(codesOf(k)) || "-")}</small></div>`).join("")}
      </div></div>
      <div class="grid">
        <div class="card span-8"><h2>주요 연표</h2><ul class="timeline">
          ${D.timeline.map((t) => `<li class="${t.category === "trophy" ? "trophy-ev" : ""}"><div class="yr">${t.year}</div><div class="ttl">${esc(t.title || t.title_ko)}</div></li>`).join("")}
        </ul></div>
        <div class="card span-4"><h2>역대 감독 <small>${D.managers.length}</small></h2><ul class="match-list managers">
          ${D.managers.slice().reverse().map((m) => `<li class="match" style="grid-template-columns:1fr auto"><div><b>${esc(m.name)}</b>${m.is_caretaker ? ' <span class="badge ha">Interim</span>' : ""}<div class="small muted">${esc([m.nationality, m.matches ? `P${m.matches} W${m.wins} D${m.draws} L${m.losses}` : "", m.note_en].filter(Boolean).join(" · "))}</div></div><div class="small muted" style="text-align:right">${esc(m.start_date)} –<br>${esc(m.end_date || "Present")}</div></li>`).join("")}
        </ul></div>
      </div>`;
  }

  // DB 의 한글 유럽대회 결과 → 영문
  const europeEn = (s) => {
    if (!s) return "";
    const m = s.match(/리그 페이즈 (\d+)위/);
    if (m) return `UCL league phase ${ord(+m[1])}${s.includes("진행") ? " (ongoing)" : ""}`;
    return /[가-힣]/.test(s) ? "" : s;
  };

  let recordsEra = "PL";
  const ERAS = {
    PL: ["Premier League era", (r) => r.season >= "1992"],
    POST: ["1946–1992", (r) => r.season >= "1946" && r.season < "1992"],
    PRE: ["1888–1939", (r) => r.season < "1946"],
    ALL: ["All seasons", () => true],
  };
  const DIV_SHORT = { PL: "PL", FL1: "Div 1", FL2: "Div 2", FALL: "Alliance", COMB: "Combination" };
  const cupTxt = (s) => (!s ? "–" : s === "Winners" ? "🏆 Winners" : esc(s));
  function pageRecords() {
    const all = D.seasons.slice().reverse();
    const rows = all.filter(ERAS[recordsEra][1]);
    const top = (r) => r.comp === "PL" || r.comp === "FL1";
    const cls = (r) => (r.position === 1 && top(r) ? "p1" : top(r) && r.position <= 4 ? "top4" : top(r) && r.position >= 15 ? "low" : "");
    const leagueTitles = all.filter((r) => r.position === 1 && r.is_final && top(r)).length;
    const europe = (r) => (r.is_final ? [r.europe_competition, r.europe_result].filter(Boolean).join(" – ") : europeEn(r.europe_result));
    const fromWiki = all.some((r) => (r.source || "").startsWith("wikipedia"));
    return `${title("시즌별 기록")}<p class="page-sub">${all.length} seasons since ${all.length ? esc(all[all.length - 1].season) : "-"} · ${leagueTitles} league titles</p>
      <div class="filters">${Object.entries(ERAS).map(([k, [label]]) => `<button data-era="${k}" class="${k === recordsEra ? "on" : ""}">${label}</button>`).join("")}</div>
      <div class="card"><div class="table-wrap"><table class="data">
        <thead><tr><th class="l">Season</th><th class="l">Div</th><th class="l">Pos</th><th>P</th><th>W</th><th>D</th><th>L</th><th>GF</th><th>GA</th><th>Pts</th><th class="l">FA Cup</th><th class="l">League Cup</th><th class="l">Europe</th><th class="l">Top scorer</th></tr></thead>
        <tbody>${rows.map((r) => `<tr class="${r.is_final ? "" : "mu"}"><td class="l">${esc(r.season)}</td><td class="l small">${esc(DIV_SHORT[r.comp] || r.comp)}</td>
          <td class="l"><span class="pos ${cls(r)}">${r.position ?? "-"}</span>${r.is_final ? "" : ' <span class="small muted">live</span>'}</td>
          <td>${r.played ?? "–"}</td><td>${r.won ?? "–"}</td><td>${r.drawn ?? "–"}</td><td>${r.lost ?? "–"}</td><td>${r.goals_for ?? "–"}</td><td>${r.goals_against ?? "–"}</td><td class="pts">${r.points ?? "–"}</td>
          <td class="l small">${cupTxt(r.fa_cup)}</td><td class="l small">${cupTxt(r.league_cup)}</td><td class="l small muted">${esc(europe(r)) || "–"}</td>
          <td class="l small">${r.top_scorer ? `${esc(r.top_scorer)} <span class="muted">(${r.top_scorer_goals ?? "?"})</span>` : "–"}</td></tr>`).join("")}</tbody>
      </table></div>
      <p class="small muted" style="margin-top:10px">Div 1 = Football League First Division (top flight before 1992-93), Div 2 = Second Division. Top scorer counts goals in all competitions. No league football 1915–19 and 1939–46 (World Wars).${fromWiki ? ' Historical records: <a href="https://en.wikipedia.org/wiki/List_of_Manchester_United_F.C._seasons" target="_blank" rel="noopener">Wikipedia</a> (CC BY-SA 4.0).' : ""}</p></div>`;
  }

  // ----- 경기 상세 (#match/<id>) -----
  const EV_ROWS = [["goal", "⚽", "Goals"], ["own_goal", "⚽", "Own goals"], ["assist", "🅰️", "Assists"],
    ["missed_penalty", "❌", "Penalties missed"], ["penalty_saved", "🧤", "Penalties saved"],
    ["yellow", "🟨", "Yellow cards"], ["red", "🟥", "Red cards"]];
  const grouped = (list) => {
    const c = new Map();
    for (const n of list) c.set(n, (c.get(n) || 0) + 1);
    return [...c].map(([n, k]) => esc(n) + (k > 1 ? ` <span class="x">×${k}</span>` : "")).join("<br>");
  };
  function pageMatch(id) {
    const m = matches.find((x) => String(x.id) === String(id));
    if (!m) return `${title("경기 상세")}<div class="card empty"><b>Match not found</b><a href="#fixtures">Back to fixtures</a></div>`;
    const det = (D.match_details || {})[String(m.id)] || { events: [] };
    const ev = det.events || [];
    const home = m.home_away !== "A";
    const L = home ? "MU" : "OPP", R = home ? "OPP" : "MU";
    const teamName = (side) => (side === "MU" ? "Man United" : m.opponent);
    const haOf = (side) => ((side === "MU") === home ? "Home" : "Away");
    const crest = (side) => (side === "MU" ? muCrest("crest") : m.opponent_crest ? `<img class="crest" src="${esc(m.opponent_crest)}" alt="">` : "");
    const done = m.status === "FINISHED";
    const minute = (e) => (e.minute != null ? ` ${e.minute}${e.extra_minute ? "+" + e.extra_minute : ""}'` : "");
    const names = (side, type) => ev.filter((e) => e.side === side && e.type === type).map((e) => e.player + minute(e) + (e.detail === "pen" ? " (pen)" : ""));
    const muOnly = m.comp !== "PL";  // 컵 대회(위키백과)는 맨유 득점자만 기록됨
    const rows = EV_ROWS.filter(([t]) => ev.some((e) => e.type === t)).map(([t, ic, label]) => `
      <tr><td class="ev-l">${grouped(names(L, t)) || "–"}</td><th><span class="ic">${ic}</span>${label}</th><td class="ev-r">${grouped(names(R, t)) || (muOnly && R === "OPP" ? '<span class="muted">n/a</span>' : "–")}</td></tr>`).join("");
    const bonus = ev.filter((e) => e.type === "bonus").sort((a, b) => b.detail - a.detail);
    const md = m.matchday ? (m.comp === "PL" ? ` · Matchweek ${m.matchday}` : ` · Matchday ${m.matchday}`) : "";
    const idx = finished.findIndex((x) => x.id === m.id);
    const prev = idx > 0 ? finished[idx - 1] : null, next = idx >= 0 ? finished[idx + 1] : null;
    const emptyMsg = !done ? "This match has not been played yet."
      : m.comp === "PL" ? "Match details will appear after the next data sync."
      : "Scorer and card details are not available for this competition on the free data plan.";
    return `${title("경기 상세")}
      <p class="page-sub"><a href="javascript:history.back()" class="back">← Back</a> · ${esc(compEn(m.comp))}${md}</p>
      <section class="board">
        <div class="board-team">${crest(L)}<b>${esc(teamName(L))}</b><span>${haOf(L)}</span></div>
        <div class="board-score">${done ? scoreText(m) : "vs"}${done ? `<div>${chip(m.result)}</div>` : ""}</div>
        <div class="board-team">${crest(R)}<b>${esc(teamName(R))}</b><span>${haOf(R)}</span></div>
        <div class="board-meta">${m.kickoff_confirmed ? `${dateTime(m.kickoff_utc, KST)} KST · ${dateTime(m.kickoff_utc, UK)} ${ukZone(m.kickoff_utc)}` : `${shortDate(m.kickoff_utc, UK)} · Kick-off time not recorded`}${m.venue ? " · " + esc(m.venue) : ""}</div>
      </section>
      <div class="grid">
        <div class="card span-8"><h2>경기 기록</h2>
          ${rows ? `<table class="events"><thead><tr><th class="ev-l">${esc(teamName(L))}</th><th></th><th class="ev-r">${esc(teamName(R))}</th></tr></thead><tbody>${rows}</tbody></table>
            <p class="small muted" style="margin:10px 0 0">${muOnly
              ? 'Source: <a href="https://en.wikipedia.org/" target="_blank" rel="noopener">Wikipedia</a> season article (CC BY-SA 4.0). Only United scorers are recorded for this competition.'
              : "Source: Fantasy Premier League match stats. Goal times are not available."}</p>`
          : `<p class="muted">${emptyMsg}</p>`}
        </div>
        <div class="card span-4"><h2>최고 활약</h2>
          ${bonus.length ? `<ul class="bonus">${bonus.map((b) => `<li><b>${esc(b.detail)}</b><span>${esc(b.player)}${b.side === "MU" ? "" : ` <small class="muted">(${esc(m.opponent)})</small>`}</span></li>`).join("")}</ul>
            <p class="small muted" style="margin:10px 0 0">FPL bonus points (3 = best in the match).${det.potm ? ` United's best: <b>${esc(det.potm)}</b>.` : ""}</p>` : `<p class="muted">Not available.</p>`}
        </div>
        <div class="card span-12"><h2>경기 요약</h2>
          ${det.summary ? `<p class="summary">${esc(det.summary)}</p><p class="small muted" style="margin:8px 0 0">Automatically generated from match data (${esc(det.model || "template")}).</p>` : `<p class="muted">${done ? "Summary will be generated after the next data sync." : "Available after full time."}</p>`}
        </div>
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
  document.getElementById("sync-info").textContent = `Last data update: ${dateTime(sync, KST)} (KST)`;
  // 우측 상단 동기화 배지 (36시간 넘게 갱신 없으면 노란색 경고)
  const badge = document.getElementById("sync-badge");
  if (sync) {
    const ageH = (Date.now() - new Date(sync).getTime()) / 3600e3;
    const stale = ageH > 36;
    badge.classList.toggle("stale", stale);
    document.getElementById("sync-text").innerHTML =
      `<span class="long">${stale ? "Update delayed · " : "Data synced "}</span><b>${esc(dateTime(sync, KST))}</b> KST`;
    const SRC = { "football-data": "Fixtures & tables", fpl: "Players" };
    badge.title = (D.last_sync || []).map((s) => `${SRC[s.source] || s.source} (${s.job}): ${dateTime(s.finished_utc, KST)} KST`).join("\n");
  } else {
    badge.classList.add("none");
  }
  render();
})();
