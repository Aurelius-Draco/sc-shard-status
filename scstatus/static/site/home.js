/* verseshards.com home page, round 2 (Claude Design, 8 Nov 2026), ported into the site. site.js home() draws the
   markup, loads holo-foil.js and calls VSHome.mount(root, data); it refreshes /api/v1/home every 30 s with
   VSHome.update(data) and VSHome.stop() when the page changes. Runs the shard scanner, the log match, the pillar
   elements, the map, the rivalry and org cards (the site's holo-foil.js), the sharing switch and the maker's card.
   No libraries. Under reduced motion everything shows finished, nothing moves.
   Changes from the design, by Ray (8 Nov): the Microsoft Store badge is the main action everywhere (it goes to /get
   until the listing is live), with GitHub as the second button. The maker section is Design's updated version (a
   full-width scene, live counters, the card front only, no turning over). */
(function () {
  "use strict";
  let ROOT = document;
  const $ = (s, r = ROOT) => r.querySelector(s);
  const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const calm = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const fmt = n => Number(n).toLocaleString("en-AU");
  const ago = m => m < 1 ? "just now" : m < 60 ? `${m} min ago` : m < 1440 ? `${Math.round(m / 60)} h ago` : `${Math.round(m / 1440)} ${Math.round(m / 1440) === 1 ? "day" : "days"} ago`;
  const hcol = s => s >= 80 ? "#4cc4b0" : s >= 60 ? "#c9d1db" : s >= 40 ? "#ffd166" : "#ec7a5e";
  // the words follow the window the API used
  const WIN = { hour: ["in the last hour", "Last hour"], day: ["today", "Today"], week: ["this week", "This week"] };
  const inWin = w => (WIN[w] || WIN.week)[0], winLabel = w => (WIN[w] || WIN.week)[1];
  const winChip = w => `<span class="win${w === "hour" ? " is-hour" : ""}">${winLabel(w)}</span>`;

  function count(el, to, dec = 0) {
    const from = parseFloat(el.dataset.v || "0"); el.dataset.v = to;
    if (calm || from === to) { el.textContent = dec ? to.toFixed(dec) : fmt(to); return; }
    const t0 = performance.now(), d = 900;
    const step = t => { const k = Math.min(1, (t - t0) / d), e = 1 - Math.pow(1 - k, 3), v = from + (to - from) * e;
      el.textContent = dec ? v.toFixed(dec) : fmt(Math.round(v)); if (k < 1) requestAnimationFrame(step); };
    requestAnimationFrame(step);
  }
  const N = (v, dec = 0) => `<b class="num" data-count="${v}" data-dec="${dec}">${dec ? Number(v).toFixed(dec) : fmt(v)}</b>`;
  function counters(root) { root.querySelectorAll("[data-count]").forEach(el => { const to = parseFloat(el.dataset.count), dec = +el.dataset.dec || 0; el.dataset.v = el.dataset.v || (calm ? to : 0); count(el, to, dec); }); }
  const INFO = '<svg viewBox="0 0 24 24"><path d="M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 11v5M12 8h.01"/></svg>';
  const STORE_BADGE = "/img/home/ms-store-badge-dark.svg";
  const IMG = "/img/home/";
  const plural = (n, one, many = one + "s") => `${fmt(n)} ${n === 1 ? one : many}`;

  // ---------------- calls to action: the Store badge leads (to /get until the listing is live), GitHub second ----------------
  function ctas(d, where) {
    // As Design drew it for the Store: the badge, See the board (hero only) and "Free. Or download from GitHub."
    // Until the listing is live the badge leads to /get (countdown and GitHub), so it opens in the same tab (Ray, 8 Nov).
    const s = d.store || {}, live = !!s.live;
    return `<a class="store" href="${esc(s.url || "/get")}"${live ? ` target="_blank" rel="noopener"` : ""}><img src="${STORE_BADGE}" alt="${live ? "Get it from Microsoft" : "Get it from Microsoft (coming shortly)"}" width="161" height="44"></a>
         ${where === "hero" ? `<a class="btn" href="/board">See the board</a>` : ""}<span class="alt">Free. Or <a href="${esc(s.github_url)}" target="_blank" rel="noopener">download from GitHub</a>.</span>`;
  }


  // ---------------- 1. hero ----------------
  function hero(d) {
    const s = d.shards, t = d.totals || {}, p = d.pirates;
    const live = s.regions.filter(r => r.best), local = live.find(r => r.region === (window.HOME_REGION || "Australia")) || live[0];
    const L = [];
    L.push(s.window === "hour"
      ? `<li style="--c:#ffd166"><span>${N(s.watched)} shards being watched by ${N(s.players_sharing)} players right now.</span></li>`
      : `<li style="--c:#ffd166"><span>${N(s.watched)} shards seen ${inWin(s.window)} across ${N(s.regions_count)} regions.</span></li>`);
    if (local) L.push(`<li style="--c:#4cc4b0"><span>Best in ${esc(local.region)} ${inWin(local.window)}: <b>${esc(local.best.shard)}</b>${local.best.fps != null ? ` at ${N(local.best.fps, 1)} fps` : ""}, <span class="t-good">${esc(local.best.word)} ${local.best.score}</span>.</span></li>`);
    if (s.window !== "hour" && t.sessions_shared) L.push(`<li style="--c:#a9c0d8"><span>${N(t.sessions_shared)} sessions shared so far.</span></li>`);
    if (p.count) L.push(`<li style="--c:#ec7a5e"><span><span class="t-bad">${N(p.count)} pirate ${p.count === 1 ? "report" : "reports"}</span> ${inWin(p.window)}, the latest ${/^near /i.test(p.reports[0].area) ? "" : "at "}${esc(p.reports[0].area)}.</span></li>`);
    else L.push(`<li class="quiet" style="--c:#a9c0d8"><span>No pirate reports ${inWin(p.window)}.</span></li>`);
    if (d.queue) L.push(`<li style="--c:#f2a93b"><span>Patch day: ${N(d.queue.waiting)} players in the login queue.</span></li>`);
    $("#now").innerHTML = L.join(""); counters($("#now"));
    $(".live-tag").innerHTML = d.sample ? `<i></i>Sample: a busy Saturday night` : `<i></i>Live from the board`;
    $("#hero-ctas").innerHTML = ctas(d, "hero"); $("#last-ctas").innerHTML = ctas(d, "last");
    const liveP = d.patch.live || (d.patch.live_build ? `LIVE build ${d.patch.live_build}` : "LIVE");
    $("#patch").innerHTML = `<span><b>${esc(liveP)}</b>${d.patch.ptu ? ` · ${esc(d.patch.ptu)}` : ""}</span>` +
      (d.patch.fix_note ? `<span class="fix">${esc(d.patch.fix_note.issue)}: ${esc(d.patch.fix_note.status)}</span>` : "") +
      `<span>Known-issues library: <b>${d.library.known}</b> problems${d.library.added_week != null ? `, <b>${d.library.added_week}</b> added this week` : ""}</span>` +
      (t.blueprint_drops ? `<span><b>${fmt(t.blueprint_drops)}</b> blueprint drops recorded</span>` : "");
    $("#lib-known").textContent = d.library.known;
  }

  // ---------------- the shard scanner ----------------
  // A busy Saturday night, built the same every time. Shown only when the viewer asks, and always labelled as a sample.
  const BUSY = (function () {
    const R = [["Australia", "AU", 14, 95], ["Asia", "AS", 9, 89], ["US West", "USW", 13, 90], ["US East", "USE", 20, 93], ["Europe", "EU", 24, 96]];
    let seed = 7; const rnd = () => (seed = (seed * 9301 + 49297) % 233280) / 233280;
    const regions = R.map(([region, p, n, top]) => { const lights = [{ shard: `${p}-90`, score: top, fps: +(top / 3.9).toFixed(1) }];
      for (let i = 1; i < n; i++) { const sc = Math.round(28 + rnd() * 66); lights.push({ shard: `${p}-${i * 10 + (i > 8 ? 5 : 0)}`, score: sc, fps: +(sc / 4.1).toFixed(1) }); }
      return { region, window: "hour", best: { shard: lights[0].shard, fps: lights[0].fps, score: top, word: "Healthy" }, lights }; });
    return { window: "hour", watched: regions.reduce((a, r) => a + r.lights.length, 0), regions_count: 5, players_sharing: 412, regions };
  })();
  let scanMode = "live";
  function jitter(lights) {   // lights close together on the scale spread up and down so each one shows
    const out = [], placed = [];
    lights.slice().sort((a, b) => a.score - b.score).forEach(l => { const near = placed.filter(x => Math.abs(x - l.score) < 3.2).length; placed.push(l.score);
      out.push(Object.assign({}, l, { j: [0, -12, 12, -6, 6, -16, 16][near % 7] })); });
    return out;
  }
  function scanner(d) {
    const sample = scanMode === "sample", s = sample ? BUSY : d.shards;
    const box = $("#scan"); box.classList.toggle("is-sample", sample || !!d.sample);
    $("#scan-win").outerHTML = `<span id="scan-win" class="win${s.window === "hour" ? " is-hour" : ""}">${sample ? "Sample" : winLabel(s.window)}</span>`;
    $("#scan-cnt").innerHTML = sample ? `<b>${s.watched}</b> shards, <b>${s.players_sharing}</b> players sharing. Not live: what the board looks like once it fills up.`
      : s.watched ? `<b>${s.watched}</b> ${s.watched === 1 ? "shard" : "shards"} across <b>${s.regions_count}</b> ${s.regions_count === 1 ? "region" : "regions"}${s.window === "hour" ? `, <b>${s.players_sharing}</b> players sharing now` : ""}` : "No readings yet";
    $("#scan-rows").innerHTML = scanRows(s, sample);
  }
  function scanRows(s, sample) {
    const zones = [[20, "Bad", "#ec7a5e"], [50, "Struggling", "#ffd166"], [70, "OK", "#c9d1db"], [90, "Healthy", "#4cc4b0"]];
    const scale = `<div class="sr is-scale" aria-hidden="true"><span></span><div class="sr-track">${zones.map(([x, w, c]) => `<span class="zone" style="left:${x}%;color:${c}">${w}</span>`).join("")}</div><span></span></div>`;
    const ticks = [40, 60, 80].map(x => `<span class="tick" style="left:${x}%"></span>`).join("");
    const rows = s.regions.map(r => {
      const ls = jitter(r.lights), best = r.best && ls.find(l => l.shard === r.best.shard);
      const label = r.lights.length ? `${r.lights.length} ${r.lights.length === 1 ? "shard" : "shards"}${!sample && r.window !== s.window ? ` · ${winLabel(r.window).toLowerCase()}` : ""}` : "";
      return `<div class="sr${r.lights.length ? "" : " is-empty"}"><div class="sr-n"><b>${esc(r.region)}</b><span>${label}</span></div>
        <div class="sr-track" role="img" aria-label="${r.lights.length ? `${esc(r.region)}: ${r.lights.length} shards, ${r.lights.filter(l => l.score >= 80).length} healthy, ${r.lights.filter(l => l.score < 40).length} bad` : `${esc(r.region)}: no readings ${inWin(r.window)}`}">${ticks}
          ${ls.map(l => `<i class="lt${l === best ? " is-best" : ""}" style="--s:${Math.max(2, Math.min(98, l.score))};--j:${l.j};--c:${hcol(l.score)}" title="${esc(l.shard)}: ${l.score}"></i>`).join("")}
          ${best ? `<span class="lock" style="--s:${Math.max(2, Math.min(98, best.score))};--j:${best.j}"></span>` : ""}
          ${r.lights.length ? "" : `<span class="sr-none">No readings ${inWin(r.window)}</span>`}</div>
        <div class="sr-best">${r.best ? `<b>${esc(r.best.shard)}<small>Best</small></b><span>${r.best.fps != null ? `${r.best.fps.toFixed(1)} fps · ` : ""}<span class="good">${esc(r.best.word)} ${r.best.score}</span></span>` : `<span>Nothing to lock on</span>`}</div></div>`; }).join("");
    return scale + rows;
  }
  // the scanner on its own, as a labelled sample (a busy Saturday night), for pages other than home
  function scanEl(title) {
    return `<div class="scan is-sample"><div class="scan-in"><div class="scan-head"><h2>${esc(title || "Shard scanner")}</h2><span class="win">Sample</span>
      <span class="cnt"><b>${BUSY.watched}</b> shards, <b>${BUSY.players_sharing}</b> players sharing. A busy Saturday night, not live.</span><span class="grow"></span><a href="/board">Open the live board →</a></div>
      <div class="scan-rows">${scanRows(BUSY, true)}</div>
      <div class="scan-foot"><span class="key"><i style="--c:#4cc4b0"></i>Healthy</span><span class="key"><i style="--c:#c9d1db"></i>OK</span><span class="key"><i style="--c:#ffd166"></i>Struggling</span><span class="key"><i style="--c:#ec7a5e"></i>Bad</span><span>One light per shard, placed by its health out of 100. The healthiest in each region is locked on and named.</span></div></div></div>`;
  }
  function scanControls() {
    ROOT.querySelectorAll(".seg button").forEach(b => b.addEventListener("click", () => {
      scanMode = b.dataset.mode; ROOT.querySelectorAll(".seg button").forEach(x => x.setAttribute("aria-pressed", x === b)); scanner(current());
    }));
  }

  // ---------------- live in the verse strip ----------------
  function ticker(d) {
    const items = [];
    d.pirates.reports.forEach(p => items.push(`<li><span class="k k-pirate">Pirates</span><b>${esc(p.area)}</b>${p.shard ? ` on ${esc(p.shard)}` : ""}, ${ago(p.ago_min)}</li>`));
    d.groups.latest.forEach(g => items.push(`<li><span class="k k-group">Recruiting</span><b>${esc(g.activity)}</b>${g.shard ? ` on ${esc(g.shard)}` : ""}${g.wanted ? `, ${g.wanted} wanted` : ""}, ${ago(g.ago_min)}</li>`));
    d.blueprints.latest.forEach(b => items.push(`<li><span class="k k-bp">Blueprint</span><b>${esc(b.blueprint)}</b> from ${esc(b.contract)}, ${ago(b.ago_min)}</li>`));
    if (d.queue) items.unshift(`<li><span class="k k-queue">Login queue</span><b>${fmt(d.queue.waiting)}</b> waiting, about ${d.queue.estimate_min} min</li>`);
    d.shards.regions.filter(r => r.best).forEach(r => items.push(`<li><span class="k k-shard">Best in ${esc(r.region)} ${inWin(r.window)}</span><b>${esc(r.best.shard)}</b> ${r.best.score}, ${esc(r.best.word)}</li>`));
    const t = d.totals || {};
    if (t.sessions_shared) items.push(`<li><span class="k k-shard">So far</span><b>${fmt(t.sessions_shared)}</b> sessions shared${t.blueprint_drops ? `, <b>${fmt(t.blueprint_drops)}</b> blueprint drops recorded` : ""}</li>`);
    if (!items.length) items.push(`<li><span class="k k-shard">Quiet</span>Nothing reported lately. The board fills in as players share.</li>`);
    const ul = `<ul>${items.join("")}</ul>`;
    $("#ticker-row").innerHTML = ul + ul.replace("<ul>", '<ul aria-hidden="true">');
  }

  // ---------------- 2. the moment: the log, the catch, the match, the verdict ----------------
  const FILL = ["[Notice] <Telemetry> Frame stats sent [Team_GameServices][Telemetry]", "[Notice] <Inventory> Request completed: Move [Team_CoreGameplayFeatures][Inventory]",
    "[Notice] <Actor State> Player entered zone OOC_Stanton_2b_Daymar [Team_CoreGameplayFeatures][Zones]", "[Notice] <StatObjLoad> Streaming group loaded: 214 objects [Team_Engine][Streaming]",
    "[Notice] <Comms> Channel joined: Local [Team_Social][Chat]", "[Notice] <Mission> Objective updated: 2 of 3 [Team_Missions][Contracts]",
    "[Notice] <Vehicle> Seat entered: pilot [Team_Vehicles][Seats]", "[Notice] <Shop> Purchase completed [Team_Economy][Shops]",
    "[Notice] <Physics> Grid transfer complete [Team_Physics][Grids]", "[Notice] <Network> Ping 33 ms, loss 0% [Team_Network][Session]",
    "[Notice] <Party> Member joined the party [Team_Social][Party]", "[Notice] <UI> Mobiglas app opened: Contracts [Team_UI][Mobiglas]"];
  const MOMENTS = [
    { id: "elevator", label: "The elevator won't come", icon: '<svg viewBox="0 0 24 24"><path d="M5 3h14v18H5zM12 3v18M8.5 9l-1.5 2h3zM15.5 13l1.5-2h-3z"/></svg>',
      hit: "[Warning] <CLandingAreaElevatorManager::OnPlatformMissing> Elevator manager [LAM_Orison_Hangar_03] has no platform entity [Team_CoreGameplayFeatures][Elevators]",
      rule: "hangar-elevator-no-platform", verdict: ["The game, not you", "#ffd166"], title: "A hangar or freight elevator has no platform",
      explain: "The elevator is missing its moving platform, so ships or cargo can't go up or down. Pressing the button again won't help.",
      server: null, fixes: ["Use a different hangar or pad.", "Store and re-retrieve your ship.", "If none of that works, it needs a fix from CIG: report it."] },
    { id: "atc", label: "ATC ignores you", icon: '<svg viewBox="0 0 24 24"><path d="M12 12l7-7M12 3a9 9 0 1 0 9 9M12 7a5 5 0 1 0 5 5M12 12h.01"/></svg>',
      hit: "[Notice] <CSCLoadingPlatformManager::RequestTimedOut> ASOP request timed out waiting for ATC: \"Hangar not available\" [Team_CoreGameplayFeatures][ASOP]",
      rule: "asop-atc-timeout", verdict: ["The server", "#ec7a5e"], title: "Ship retrieval timed out waiting for a hangar",
      explain: "The fleet manager kiosk gave up waiting for air traffic control. The ship may not spawn, or may spawn later.",
      server: { shard: "AU-40", score: 15, fps: 4.1, text: "Your server is running at 4 fps. ATC, kiosks and lifts all stall when it's this low." },
      fixes: ["Wait a minute and check the kiosk again before re-requesting.", "If it's stuck as 'in hangar' or 'retrieving', relog.", "Hop to a healthier shard: the scanner above shows the best in your region."] },
    { id: "spawn", label: "Your ship spawns inside the scenery", icon: '<svg viewBox="0 0 24 24"><path d="M3 20l5-9 4 5 3-4 6 8zM9 7l6 2-6 2z"/></svg>',
      hit: "[Warning] <CVehicleSpawnValidator::Overlap> Vehicle RSI_Constellation_Centaurus placed overlapping static geometry [Team_Vehicles][Spawning]",
      rule: "vehicle-bad-spawn", verdict: ["The game, not you", "#ffd166"], title: "Something spawned inside the scenery",
      explain: "The game tried to place your Constellation where it overlaps scenery. Ships spawned like this can get stuck or blow up.",
      server: null, fixes: ["If it's stuck or damaged, store it and retrieve it again.", "Use a different pad or hangar if it keeps happening."] },
    { id: "cargo", label: "Your cargo's gone", icon: '<svg viewBox="0 0 24 24"><path d="M3 8l9-5 9 5v8l-9 5-9-5zM3 8l9 5 9-5M12 13v8"/></svg>',
      hit: "[Error] <FreightElevatorKiosk::BuildRequest> Requested entity 201384197 not present on this server [Team_CargoSystems][Freight]",
      rule: "freight-entity-not-present", verdict: ["You changed server", "#a9c0d8"], title: "The freight elevator is asking for items that aren't there",
      explain: "Items left in the elevator on your old server are still listed, but they don't exist on the server you're on now.",
      server: null, fixes: ["Don't leave items in a freight elevator when you leave the server. Take them back first.", "Close and reopen the kiosk so the list refreshes.", "If you change server, the items stay on the old one. Relogging may put you back there."] },
    { id: "30k", label: "30k", icon: '<svg viewBox="0 0 24 24"><path d="M9 7V3M15 7V3M7 7h10v4a5 5 0 0 1-10 0zM12 16v5M4 4l16 16"/></svg>',
      hit: "[Notice] <Disconnect> Session ended with code 30016: \"player requested\" (view state: in universe) [Team_Network][Session]",
      rule: "disconnect-30016", verdict: ["The server", "#ec7a5e"], title: "Left the server, and you didn't choose to",
      explain: "Code 30016 is written when your session ends. You hadn't quit or picked Exit to Menu, so it came from the server.",
      server: { shard: "USE-55", score: 22, fps: 6.2, text: "Your server node restarted two minutes before. A 30k straight after a restart is the server, not your PC." },
      fixes: ["Rejoin. Anything you were moving or delivering may need redoing.", "Press Mark this moment straight after, so the report has the details CIG ask for."] }
  ];
  const HIT_AT = 13, ROW = 24;
  function ring(score) { const r = 22, C = 2 * Math.PI * r; return `<span class="mini-ring"><svg viewBox="0 0 54 54"><circle cx="27" cy="27" r="${r}" fill="none" stroke="var(--line)" stroke-width="5"/><circle cx="27" cy="27" r="${r}" fill="none" stroke="var(--rust)" stroke-width="5" stroke-linecap="round" stroke-dasharray="${C.toFixed(1)}" stroke-dashoffset="${(C * (1 - score / 100)).toFixed(1)}"/></svg><b>${score}</b></span>`; }
  let moTimers = [], moIndex = 1;
  function setStep(n) { $("#mo-stage").dataset.step = n; }
  function moRender(m, i) {
    const t0 = 9 * 3600 + 41 * 60 + i * 97, ts = k => { const s = t0 + k * 3; return `2026-11-08T${String(Math.floor(s / 3600) % 24).padStart(2, "0")}:${String(Math.floor(s / 60) % 60).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}.${String((k * 137) % 1000).padStart(3, "0")}Z`; };
    const lines = Array.from({ length: HIT_AT + 5 }, (_, k) => k === HIT_AT ? m.hit : FILL[(k * 5 + i) % FILL.length]);
    $("#log-lines").innerHTML = lines.map((l, k) => { const [lv, ...rest] = l.split(" "); return `<li${k === HIT_AT ? ' class="is-hit"' : ""}><span class="t">&lt;${ts(k)}&gt;</span><span class="lv">${esc(lv)}</span><span>${esc(rest.join(" "))}</span></li>`; }).join("");
    $("#mo-match").innerHTML = `<p class="caught"><span>Caught</span>${esc(m.hit.replace(/\s*\[Team_[^\]]*\](\[[^\]]*\])?$/, ""))}</p><span>Matched in the known-issues library</span><code>${esc(m.rule)}</code><span class="bar"><i></i></span>`;
    $("#answer").innerHTML = `<div class="answer-top"><span class="app">What's gone wrong?</span><span class="stamp is-new" style="--vc:${m.verdict[1]}">${esc(m.verdict[0])}</span></div>
      <h3>${esc(m.title)}</h3><p>${esc(m.explain)}</p>
      ${m.server ? `<div class="server">${ring(m.server.score)}<span><b>${esc(m.server.shard)} · ${m.server.fps} fps</b><br>${esc(m.server.text)}</span></div>` : ""}
      <div class="helps"><h4>What actually helps</h4><ol>${m.fixes.map(f => `<li>${esc(f)}</li>`).join("")}</ol></div>
      <span class="from">The log lines are a made-up sample shaped like real ones. The answer is the library's own.</span>`;
  }
  const scrolled = () => `${-(HIT_AT - 3) * ROW}px`;
  function moPlay(i, animate) {
    moTimers.forEach(clearTimeout); moTimers = []; moIndex = i;
    const m = MOMENTS[i]; moRender(m, i);
    ROOT.querySelectorAll("#moments button").forEach((b, k) => b.setAttribute("aria-selected", k === i));
    $("#mo-stage").setAttribute("aria-labelledby", "mo-" + m.id);
    const lines = $("#log-lines");
    if (!animate || calm) { lines.style.transition = "none"; lines.style.setProperty("--ly", scrolled()); setStep(5); return; }
    lines.style.transition = "none"; lines.style.setProperty("--ly", "40px"); setStep(1); void lines.offsetHeight; lines.style.transition = "";
    const at = (ms, f) => moTimers.push(setTimeout(f, ms));
    at(60, () => lines.style.setProperty("--ly", scrolled()));
    at(1750, () => setStep(2)); at(2400, () => setStep(3)); at(3200, () => setStep(4)); at(3700, () => setStep(5));
  }
  function moments() {
    const list = $("#moments");
    list.innerHTML = MOMENTS.map((m, i) => `<li><button type="button" role="tab" id="mo-${m.id}" aria-selected="${i === 1}" aria-controls="mo-stage" data-i="${i}">${m.icon}<span>${esc(m.label)}</span></button></li>`).join("");
    list.addEventListener("click", e => { const b = e.target.closest("button"); if (b) moPlay(+b.dataset.i, true); });
    list.addEventListener("keydown", e => { if (!/Arrow(Up|Down)/.test(e.key)) return; const bs = [...list.querySelectorAll("button")], i = bs.indexOf(document.activeElement); if (i < 0) return;
      const n = (i + (e.key === "ArrowDown" ? 1 : -1) + bs.length) % bs.length; bs[n].focus(); moPlay(n, true); e.preventDefault(); });
    $("#mo-skip").addEventListener("click", () => moPlay(moIndex, false));
    moPlay(1, false);
    onSeen($("#mo-stage"), () => moPlay(moIndex, true), .45);
  }

  // ---------------- 3. pillar elements ----------------
  const below = el => el.getBoundingClientRect().top > innerHeight * .9;
  function onSeen(el, f, th = .35) {
    if (!("IntersectionObserver" in window)) return f();
    const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { io.disconnect(); f(); } }), { threshold: th }); io.observe(el);
  }
  function pillars() { animate(ROOT); }

  // ---------------- the app's own parts as builders (8 Nov): the home page draws them, and so do About, Features and the
  // Guide (VSHome.el), so every page shows the same built element, never a screenshot ----------------
  const ARC = 402.1;
  function ringEl(o) {   // o: score, word, kv [[label, value, bar %]], where, id
    const c = hcol(o.score);
    return `<div class="el glass el-ring"${o.id ? ` id="${o.id}"` : ""} data-score="${o.score}" style="--rc:${c}"><div>
            <div class="row"><div class="big-ring"><svg viewBox="0 0 150 150" aria-hidden="true"><circle cx="75" cy="75" r="64" fill="none" stroke="rgba(255,255,255,.1)" stroke-width="11"/><circle class="arc" cx="75" cy="75" r="64" fill="none" stroke="${c}" stroke-width="11" stroke-linecap="round" stroke-dasharray="${ARC}" stroke-dashoffset="${(ARC * (1 - o.score / 100)).toFixed(1)}"/></svg><b><span class="ring-n">${o.score}</span><small style="color:${c}">${esc(o.word)}</small></b></div>
              <div class="kv">${o.kv.map(([k, v, w]) => `<div><span>${esc(k)}</span><b>${esc(v)}</b><i style="--w:${w}%"></i></div>`).join("")}</div></div>
            ${o.where ? `<div class="where">${esc(o.where)}</div>` : ""}
          </div></div>`;
  }
  const WRONG_HOME = [["Server running very slowly", "8:29 pm · server, 23 times", "high", 2], ["Your server node restarted", "8:53 pm · server", "high", 3],
    ["Packet loss", "8:44 pm · connection", "med", 0], ["Something spawned inside the scenery", "9:11 pm · vehicles", "low", 1]];
  const SEV = { high: "High", med: "Medium", low: "Low" };
  function wrongEl(o) {  // o: id, sub, items [[problem, when, high|med|low, the place it starts in before sorting]]
    return `<div class="el glass el-wrong"${o.id ? ` id="${o.id}"` : ""}><div>
            <div class="hd"><b>What's gone wrong?</b><span>${esc(o.sub)}</span></div>
            <ul class="wl" aria-label="Problems, worst first" style="--n:${o.items.length}">
              ${o.items.map(([t, w, sev, from], i) => `<li data-from="${from}" style="--pos:${i}"${i ? "" : ' class="top"'}><b>${esc(t)}</b><small>${esc(w)}</small><span class="sev ${sev}">${SEV[sev]}</span></li>`).join("")}
            </ul>
          </div></div>`;
  }
  const BP = '<svg viewBox="0 0 32 32" aria-hidden="true"><rect x="2" y="2" width="28" height="28" rx="5" fill="#163a63"/><path d="M2 9.5h28M2 16h28M2 22.5h28M9.5 2v28M16 2v28M22.5 2v28" stroke="#9fd0ff" stroke-opacity=".16" stroke-width=".8"/><rect x="2" y="2" width="28" height="28" rx="5" fill="none" stroke="#9fd0ff" stroke-width="1.3"/><path d="M15 9.5l5.6 3.2v6.6L15 22.5l-5.6-3.2v-6.6z" fill="none" stroke="#e7f3ff" stroke-width="1.7" stroke-linejoin="round"/><circle cx="15" cy="16" r="2.3" fill="none" stroke="#e7f3ff" stroke-width="1.5"/><path d="M22 2h3a5 5 0 0 1 5 5v3z" fill="#ffd166"/></svg>';
  function dealEl(id) {  // the deal: five blueprint cards from the app, then a brag card lands on top
    const cards = [["Oracle Helmet", "Armour"], ["Arden-SL Core", "Armour"], ["P4-AR Rifle", "FPS weapons"], ["Attrition-3 Repeater", "Ship weapons"], ["Aves Arms", "Armour"]];
    return `<div class="el el-deal"${id ? ` id="${id}"` : ""}>${cards.map(([n, g], k) => `<div class="bpc" style="--k:${k};--cx:${k % 2 ? 50 : 0};--cy:${Math.floor(k / 2) * 66 + (k % 2) * 30}"><span>${BP}<span>${esc(n)}<small>${esc(g)}</small></span></span></div>`).join("")}<img class="brag-land" src="${IMG}brag-session-sq-dark.webp" alt="A session brag card the app made" loading="lazy"></div>`;
  }
  // the log catch on its own (a moment from the list below), finished; it plays once when it scrolls into view
  function logEl(id, o = {}) {
    const i = Math.max(0, MOMENTS.findIndex(m => m.id === id)), m = MOMENTS[i];
    const t0 = 9 * 3600 + 41 * 60 + i * 97, ts = k => { const s = t0 + k * 3; return `${String(Math.floor(s / 3600) % 24).padStart(2, "0")}:${String(Math.floor(s / 60) % 60).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`; };
    const lines = Array.from({ length: HIT_AT + 5 }, (_, k) => k === HIT_AT ? m.hit : FILL[(k * 5 + i) % FILL.length]);
    return `<div class="mo-stage el-log" data-step="5">
        <div class="console">
          <div class="con-bar"><span class="rec" aria-hidden="true"></span><b>Game.log</b><span class="path">StarCitizen\\LIVE\\Game.log</span></div>
          <div class="log" aria-hidden="true"><ul class="log-lines" style="--ly:${-(HIT_AT - 3) * ROW}px">${lines.map((l, k) => { const [lv, ...rest] = l.split(" "); return `<li${k === HIT_AT ? ' class="is-hit"' : ""}><span class="t">&lt;${ts(k)}&gt;</span><span class="lv">${esc(lv)}</span><span>${esc(rest.join(" "))}</span></li>`; }).join("")}</ul></div>
          <div class="match"><p class="caught"><span>Caught</span>${esc(m.hit.replace(/\s*\[Team_[^\]]*\](\[[^\]]*\])?$/, ""))}</p><span>Matched in the known-issues library</span><code>${esc(m.rule)}</code><span class="bar"><i></i></span></div>
        </div>
        ${o.answer === false ? "" : `<div class="answer"><div class="answer-in"><div class="answer-top"><span class="app">What's gone wrong?</span><span class="stamp" style="--vc:${m.verdict[1]}">${esc(m.verdict[0])}</span></div>
          <h3>${esc(m.title)}</h3><p>${esc(m.explain)}</p>
          ${m.server ? `<div class="server">${ring(m.server.score)}<span><b>${esc(m.server.shard)} · ${m.server.fps} fps</b><br>${esc(m.server.text)}</span></div>` : ""}
          <div class="helps"><h4>What actually helps</h4><ol>${m.fixes.map(f => `<li>${esc(f)}</li>`).join("")}</ol></div>
          <span class="from">The log lines are a made-up sample shaped like real ones. The answer is the library's own.</span></div></div>`}
      </div>`;
  }
  function playLog(st) {
    const lines = st.querySelector(".log-lines"), end = lines.style.getPropertyValue("--ly"), step = n => st.dataset.step = n;
    lines.style.transition = "none"; lines.style.setProperty("--ly", "40px"); step(1); void lines.offsetHeight; lines.style.transition = "";
    setTimeout(() => lines.style.setProperty("--ly", end), 60);
    setTimeout(() => step(2), 1750); setTimeout(() => step(3), 2400); setTimeout(() => step(4), 3200); setTimeout(() => step(5), 3700);
  }
  // Anything built above that's still below the fold starts unfinished and plays once when it scrolls in.
  // Already on screen, or under reduced motion: shown finished.
  function animate(root) {
    if (calm) return;
    root.querySelectorAll(".el-ring").forEach(el => { if (!below(el)) return; const arc = el.querySelector(".arc"), n = el.querySelector(".ring-n"), off = arc.getAttribute("stroke-dashoffset");
      el.classList.add("go-pre"); arc.style.strokeDashoffset = ARC; n.textContent = "0"; n.dataset.v = 0;
      onSeen(el, () => { el.classList.remove("go-pre"); arc.style.strokeDashoffset = off; count(n, +el.dataset.score); }); });
    root.querySelectorAll(".el-wrong").forEach(el => { if (!below(el)) return; const lis = [...el.querySelectorAll("li")]; lis.forEach(li => { li.dataset.to = li.style.getPropertyValue("--pos"); li.style.setProperty("--pos", li.dataset.from); });
      onSeen(el, () => setTimeout(() => lis.forEach(li => li.style.setProperty("--pos", li.dataset.to)), 500)); });
    root.querySelectorAll(".el-deal").forEach(el => { if (!below(el)) return; el.classList.add("go-pre"); onSeen(el, () => setTimeout(() => el.classList.remove("go-pre"), 200)); });
    root.querySelectorAll(".el-log").forEach(el => { if (!below(el)) return; onSeen(el, () => playLog(el), .45); });
    root.querySelectorAll("[data-play]").forEach(el => { if (!below(el)) return; el.classList.add("go-pre"); onSeen(el, () => setTimeout(() => el.classList.remove("go-pre"), 150)); });
  }

  // ---------------- 4. the verse is alive: rivalry, map, org fan ----------------
  // Our own schematic of Stanton and Pyro (not CIG's starmap). Places the API can name in pirates[].place:
  const SYS = { stanton: { cx: 150, cy: 168, orbits: [38, 60, 84, 110] }, pyro: { cx: 420, cy: 168, orbits: [24, 40, 56, 74, 94, 114] } };
  const pt = (sys, o, deg) => { const S = SYS[sys], rx = S.orbits[o], a = deg * Math.PI / 180; return [S.cx + rx * Math.cos(a), S.cy + rx * .58 * Math.sin(a)]; };
  const PLACES = {
    hurston: ["stanton", ...pt("stanton", 0, 200), "Hurston"], crusader: ["stanton", ...pt("stanton", 1, 315), "Crusader"], arccorp: ["stanton", ...pt("stanton", 2, 135), "ArcCorp"],
    microtech: ["stanton", ...pt("stanton", 3, 25), "microTech"], "pyro-gateway": ["stanton", 252, 96, "Pyro Gateway"],
    "pyro-i": ["pyro", ...pt("pyro", 0, 60), "Pyro I"], monox: ["pyro", ...pt("pyro", 1, 190), "Monox"], bloom: ["pyro", ...pt("pyro", 2, 330), "Bloom"],
    "pyro-iv": ["pyro", ...pt("pyro", 3, 150), "Pyro IV"], "pyro-v": ["pyro", ...pt("pyro", 4, 40), "Pyro V"], terminus: ["pyro", ...pt("pyro", 5, 255), "Terminus"],
    checkmate: ["pyro", pt("pyro", 1, 190)[0] - 6, pt("pyro", 1, 190)[1] - 14, "Checkmate"], orbituary: ["pyro", pt("pyro", 2, 330)[0] + 12, pt("pyro", 2, 330)[1] - 8, "Orbituary"],
    "ruin-station": ["pyro", pt("pyro", 5, 255)[0] + 13, pt("pyro", 5, 255)[1] + 4, "Ruin Station"], "stanton-gateway": ["pyro", 318, 96, "Stanton Gateway"]
  };
  window.HOME_MAP_PLACES = Object.keys(PLACES);
  function map(d) { $("#map").innerHTML = mapSvg(d.pirates.reports, d.pirates.window); }
  function mapSvg(reports, win) {
    const orb = Object.entries(SYS).map(([k, S]) => S.orbits.map(r => `<ellipse class="orb" cx="${S.cx}" cy="${S.cy}" rx="${r}" ry="${(r * .58).toFixed(1)}"/>`).join("") +
      `<circle cx="${S.cx}" cy="${S.cy}" r="${k === "pyro" ? 9 : 8}" fill="${k === "pyro" ? "#ff6a3d" : "#f4f1e6"}" opacity=".95"/><circle cx="${S.cx}" cy="${S.cy}" r="18" fill="${k === "pyro" ? "#ff6a3d" : "#f4f1e6"}" opacity=".12"/>` +
      `<text class="sys" x="${S.cx}" y="${S.cy + (k === "pyro" ? 92 : 92)}" text-anchor="middle">${k.toUpperCase()}</text>`).join("");
    const pl = Object.entries(PLACES).filter(([id]) => !/gateway|checkmate|orbituary|ruin/.test(id)).map(([, [, x, y, n]]) => `<circle class="pl" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="3.2"/><text class="lbl" x="${(x + 6).toFixed(1)}" y="${(y + 3).toFixed(1)}">${n}</text>`).join("");
    const jump = `<path d="M252 96 C 270 70, 300 70, 318 96" fill="none" stroke="#a9c0d8" stroke-opacity=".5" stroke-dasharray="3 4"/><circle cx="252" cy="96" r="3" fill="#a9c0d8"/><circle cx="318" cy="96" r="3" fill="#a9c0d8"/><text class="lbl" x="285" y="62" text-anchor="middle">jump point</text>`;
    const pings = reports.map((p, i) => { const P = PLACES[p.place]; if (!P) return ""; const [, x, y, n] = P;
      return `<g class="ping" style="--d:${(i * .6).toFixed(1)}s"><circle class="ring" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="5"/><circle class="ring" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="5" style="animation-delay:calc(var(--d) + 1.2s)"/><circle class="core" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="3.6"/><text x="${(x + 7).toFixed(1)}" y="${(y - 6).toFixed(1)}">${esc(n)}</text></g>`; }).join("");
    return `<svg viewBox="0 0 560 300" role="img" aria-label="Map of Stanton and Pyro. Pirate reports ${win === "sample" ? "(sample)" : inWin(win)}: ${reports.map(p => esc(p.area)).join(", ") || "none"}.">${orb}${jump}${pl}${pings}</svg>`;
  }
  function alive(d) {
    const H = window.VSHolo;
    $("#pir-win").outerHTML = `<span class="win${d.pirates.window === "hour" ? " is-hour" : ""}" id="pir-win">${winLabel(d.pirates.window)}</span>`;
    map(d);
    const more = $("#pir-more"); if (more) { more.href = d.pirates.page || "/board"; more.textContent = d.pirates.page ? "Hot spots" : "On the board"; }
    const p = d.pirates.reports;
    $("#t-pirates").innerHTML = p.length ? `<ul class="rows">${p.map(x => `<li><span><b>${esc(x.area)}</b>${x.shard ? ` on ${esc(x.shard)}` : x.reports ? `, ${plural(x.reports, "report")}` : ""}</span><span class="ago">${ago(x.ago_min)}</span></li>`).join("")}</ul><span class="map-note">Where, never who. ${d.pirates.window === "hour" ? "Reports clear after 45 minutes on the board." : "Each report clears after 45 minutes; the count is kept by area."}</span>`
      : `<div class="empty">${INFO}<span>No pirate reports ${inWin(d.pirates.window)}. When players report pirates, the area pings on the map. Area only, never who.</span></div>`;
    const all = d.shards.regions.flatMap(r => r.best ? [r.best] : []).sort((a, b) => b.score - a.score).slice(0, 5);
    $("#race-win").outerHTML = `<span class="win${d.shards.window === "hour" ? " is-hour" : ""}" id="race-win">${winLabel(d.shards.window)}</span>`;
    $("#t-race").innerHTML = all.length ? `<div class="race">${all.map(r => `<div class="race-r"><b>${esc(r.shard)}</b><span class="race-bar"><i style="--w:${r.score}%;--c:${hcol(r.score)}"></i></span><span style="--c:${hcol(r.score)}">${r.score}</span></div>`).join("")}</div>`
      : `<div class="empty">${INFO}<span>Not enough readings yet to compare shards.</span></div>`;
    const q = d.queue;
    $("#t-queue").innerHTML = q ? `<div class="queue-big">${N(q.waiting)}<span style="color:#c3cad3">players in the same queue</span></div><div class="queue-dots" aria-hidden="true">${Array.from({ length: 80 }, (_, k) => `<i style="--k:${k}"></i>`).join("")}</div><span style="color:#c3cad3;font-size:.875rem">Typical place ${fmt(q.typical_place)}. The game says about ${q.estimate_min} min.</span>`
      : `<div class="empty">${INFO}<span>No queue today. On patch days this shows how many players are stuck in the same login queue, and how long the game says it'll be.</span></div>`;
    $("#grp-win").outerHTML = `<span class="win${d.groups.window === "hour" ? " is-hour" : ""}" id="grp-win">${winLabel(d.groups.window)}</span>`;
    const g = d.groups.latest;
    $("#t-groups").innerHTML = g.length ? `<ul class="rows groups">${g.map(x => `<li><span class="act" aria-hidden="true">${esc(String(x.activity || "").slice(0, 3).toUpperCase())}</span><span><b>${esc(x.title || x.activity)}</b></span><span class="ago">${ago(x.ago_min)}</span><small>${[x.activity, x.shard, x.wanted ? `${x.wanted} wanted` : ""].filter(Boolean).map(esc).join(" · ")}</small></li>`).join("")}</ul>`
      : `<div class="empty">${INFO}<span>No groups recruiting ${inWin(d.groups.window)}. Post one from the app and it shows here.</span></div>`;
    $("#bp-win").outerHTML = `<span class="win${d.blueprints.window === "hour" ? " is-hour" : ""}" id="bp-win">${winLabel(d.blueprints.window)}</span>`;
    const b = d.blueprints, t = d.totals || {};
    $("#t-bp").innerHTML = b.latest.length ? `<ul class="rows">${b.latest.map(x => `<li><span><b>${esc(x.blueprint)}</b>${x.contract ? ` from ${esc(x.contract)}` : ""}</span><span class="ago">${ago(x.ago_min)}</span></li>`).join("")}</ul>
      <span style="color:#c3cad3;font-size:.875rem">${N(t.blueprint_drops || b.reports)} drops recorded so far, pooled into one table.</span>`
      : `<div class="empty">${INFO}<span>No blueprint drops reported yet. Players who share send which contract gave which blueprint, pooled into one table.</span></div>`;
    $("#org-count").textContent = `${plural(d.orgs.count, "org")} and ${plural(d.orgs.creators, "creator")} listed`;
    if (!H) return counters($("#alive"));
    H.turnOver = false;
    const asOrg = o => Object.assign({ links: [], thanks: [], pageUrl: "/community/orgs/" + o.id, rsiUrl: "https://robertsspaceindustries.com/orgs/" + o.tag }, o);
    if (!d.orgs.cards.length) $("#fan").innerHTML = `<div class="empty">${INFO}<span>No orgs listed yet. <a href="/community/orgs">List your org</a> and it shows here.</span></div>`;
    const cards = d.orgs.cards.slice(0, 6), mid = (cards.length - 1) / 2;
    if (cards.length) $("#fan").innerHTML = cards.map((o, i) => H.card(asOrg(o), { size: "phone", key: "fan" }).replace("<article ", `<article role="listitem" style="--f:${(i - mid).toFixed(1)};--a:${Math.abs(i - mid).toFixed(1)}" `)).join("");
    const r = d.rivalry;
    $("#stage").innerHTML = r
      ? `<div class="stage-h"><b>Rivalry on now</b></div>${H.rivalry(asOrg(r.a), asOrg(r.b), { ends: Date.now() + r.ends_days * 864e5, taunt: r.taunt || {}, clash: r.clash ? { title: r.clash.title, start: Date.parse(r.clash.start_iso), meet: r.clash.meet } : null })}`
      : `<div class="how">${H.VS_LOGO(96)}<div><h3>Two orgs, one rivalry, 60 days</h3><ol><li>One org challenges another from its page.</li><li>The other accepts. Both agreed, so it's role-play, never a ranking of players.</li><li>Clashes go on both calendars and the rivalry shows here until it ends.</li></ol><a href="/community/orgs" style="color:#ffd166">List your org</a></div></div>`;
    H.mount($("#alive"));
    // the cards' entrance waits for them to scroll in; anything already on screen is shown at once
    counters($("#alive"));
  }

  // ---------------- 5. what it does with your PC ----------------
  function trust(d) {
    const sw = $("#share-sw"), set = on => { $("#gate").classList.toggle("is-on", on); $("#net").classList.toggle("is-on", on); $("#sw-word").textContent = on ? "on" : "off";
      $("#gate-lbl").innerHTML = on ? "One summary<br>every 5 min" : "Nothing<br>crosses"; };
    if (!sw.dataset.bound) { sw.dataset.bound = 1; sw.addEventListener("change", () => set(sw.checked)); } set(sw.checked);
    const s = d.store || {};
    const F = (ic, b, t) => `<span class="fact"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="${ic}"/></svg><span><b>${b}</b> ${t}</span></span>`;
    // The Store fact as Design drew it on the Store (Ray, 8 Nov): the full-size badge beside the words. The words stay true
    // until Microsoft certifies the app.
    const badge = `<a class="store" href="${esc(s.url || "/get")}"${s.live ? ` target="_blank" rel="noopener"` : ""}><img src="${STORE_BADGE}" alt="Get it from Microsoft" width="161" height="44"></a>`;
    $("#facts").innerHTML = `<span class="fact store-f">${badge}<span>${s.live ? `<b>On the Microsoft Store.</b> Checked by Microsoft and updated through the Store.`
        : `<b>On the Microsoft Store.</b> Being checked by Microsoft now. Until then, <a href="${esc(s.github_url)}" target="_blank" rel="noopener">download from GitHub</a>.`}</span></span>` +
      F("M12 3v18M17 7.5c-.8-1.5-2.6-2.5-5-2.5-3 0-4.5 1.6-4.5 3.4C7.5 13 17 11 17 16c0 1.8-1.8 3.5-5 3.5-2.4 0-4.4-1-5.3-2.7", "Free,", "no ads") +
      F("M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21c1-4 4.5-6 8-6s7 2 8 6", "No account", "needed") +
      F("M9 19c-4 1.5-4-2-6-2.5M15 21v-3.5c0-1 .1-1.5-.5-2 2.8-.3 5.5-1.4 5.5-6a4.6 4.6 0 0 0-1.3-3.2 4.2 4.2 0 0 0-.1-3.2s-1-.3-3.4 1.3a11.6 11.6 0 0 0-6 0C6.8 2.8 5.8 3.1 5.8 3.1a4.2 4.2 0 0 0-.1 3.2A4.6 4.6 0 0 0 4.4 9.5c0 4.6 2.7 5.7 5.5 6-.6.5-.6 1.1-.5 2V21", "Open", "on GitHub") +
      F("M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 11v5M12 8h.01", "Unofficial and fan-made.", "Not affiliated with Cloud Imperium Games.");
  }

  // ---------------- 6. the maker's card (front only, no turning over) and live counters ----------------
  // Real numbers only: a counter with no value (updates shipped, before GitHub counts are live) is left out.
  let mkSeen = false, mkObs = false;
  function maker(d) {
    const m = d.maker || {}, logo = `--logo:url('/img/aurelius-draco.jpg')`;
    if (!$("#mk")) {
      $("#maker").innerHTML = `<article class="hf-card is-big maker-card is-in" id="mk" data-org="maker" aria-labelledby="mk-n" style="--acc:#f2a93b;--acc-ink:#1a1103;--name-sz:44px">
 <div class="hf-tilt">
  <div class="hf-face hf-front"><div class="hf-inner">
   <div class="hf-banner" aria-hidden="true"><div class="hf-banner-img" style="--banner:url('${IMG}fankit-sc-06-800.webp')"></div></div>
   <div class="hf-chips"><span class="hf-chip is-month">The maker</span></div>
   <div class="hf-body">
    <div class="hf-head"><span class="hf-logo" style="${logo}" role="img" aria-label="Aurelius_Draco's portrait"></span>
     <div class="hf-id"><h3 class="hf-name" id="mk-n">Aurelius_Draco</h3><div class="hf-meta"><span class="hf-tag">MAKER</span><span>Australia · Verse Shards</span></div></div></div>
    <p class="hf-blurb">One player in Australia, plus everyone who sends in readings.</p>
    <div class="hf-foot"><span class="hf-chip">Free</span><span class="hf-chip">Open on GitHub</span><span class="hf-chip">Fan-made</span></div>
   </div><div class="hf-sheen" aria-hidden="true"></div></div></div>
 </div></article>`;
      if (window.VSHolo) window.VSHolo.mount($("#maker"));
    }
    ROOT.querySelectorAll("#mk-count [data-mkbox]").forEach(box => { box.hidden = m[box.dataset.mkbox] == null; });
    // the numbers count up the first time they're seen, then follow the API
    ROOT.querySelectorAll("#mk-count [data-mk]").forEach(el => { if (m[el.dataset.mk] == null) return; const to = +m[el.dataset.mk];
      if (mkSeen || calm) count(el, to); else { el.dataset.v = 0; el.dataset.to = to; el.textContent = fmt(to); } });
    if (!mkSeen && !calm) { if (!mkObs) { mkObs = true; onSeen($("#mk-count"), () => { mkSeen = true; ROOT.querySelectorAll("#mk-count [data-mk]").forEach(el => { if (el.dataset.to === undefined) return; el.dataset.v = 0; el.textContent = "0"; count(el, +el.dataset.to); }); }, .5); } }
    else mkSeen = true;
  }

  // ---------------- 7. the referral code ----------------
  function copyCode() {
    const btn = $("#copy-code"), out = $("#copied");
    btn.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText($("#ref-code").textContent.trim()); out.textContent = "Copied. Paste it in the referral box when you enlist."; }
      catch { const r = document.createRange(); r.selectNodeContents($("#ref-code")); const s = getSelection(); s.removeAllRanges(); s.addRange(r); out.textContent = "Selected. Press Ctrl+C to copy it."; }
    });
  }

  // ---------------- data and lifecycle (site.js drives it) ----------------
  let data = null;
  const current = () => data;
  function render(d) { data = d; hero(d); scanner(d); ticker(d); alive(d); trust(d); maker(d); }
  // The page's markup, from Claude Design's index.html (<main>), with the site's image paths
  const MARKUP = `<div class="hp">

<!-- ======================================== 1. HERO (unchanged words) ======================================== -->
<section class="hero" aria-labelledby="hero-h">
  <picture class="hero-pic"><img src="/img/home/fankit-sc-25.webp" srcset="/img/home/fankit-sc-25-800.webp 800w, /img/home/fankit-sc-25.webp 1200w, /img/home/fankit-sc-25-1600.webp 1600w, /img/home/fankit-sc-25-2400.webp 2400w" sizes="100vw" alt="" fetchpriority="high"></picture>
  <div class="wrap hero-in">
    <div class="hero-copy">
      <span class="live-tag"><i></i>Live from the board</span>
      <h1 id="hero-h">Is it you, or <em>the server?</em></h1>
      <p class="hero-sub">Verse Shards reads your game's log and the overlay on your PC, scores your shard out of 100, and tells you in plain words what just broke. Every player who shares makes the board better for everyone.</p>
      <ul class="now" id="now" aria-live="polite"><li><span>39 shards seen this week across 4 regions.</span></li></ul>
      <div class="ctas" id="hero-ctas"></div>
    </div>
  </div>
</section>

<!-- ======================================== THE SHARD SCANNER (the board's lights) ======================================== -->
<section class="scan-band" aria-labelledby="scan-h">
  <div class="wrap">
    <div class="scan" id="scan">
      <div class="scan-in">
        <div class="scan-head">
          <h2 id="scan-h">Shard scanner</h2>
          <span id="scan-win" class="win">This week</span>
          <span class="cnt" id="scan-cnt"></span>
          <span class="grow"></span>
          <div class="seg" role="group" aria-label="What the scanner shows"><button type="button" data-mode="live" aria-pressed="true">The board now</button><button type="button" data-mode="sample" aria-pressed="false">A busy Saturday night (sample)</button></div>
          <a href="/board">Open the board →</a>
        </div>
        <div id="scan-rows"></div>
        <div class="scan-foot"><span class="key"><i style="--c:#4cc4b0"></i>Healthy</span><span class="key"><i style="--c:#c9d1db"></i>OK</span><span class="key"><i style="--c:#ffd166"></i>Struggling</span><span class="key"><i style="--c:#ec7a5e"></i>Bad</span><span id="scan-note">One light per shard, placed by its health out of 100. The healthiest in each region is locked on and named.</span></div>
      </div>
    </div>
  </div>
</section>
<div class="patch"><div class="wrap patch-in" id="patch"></div></div>

<section class="ticker" aria-label="Live in the verse">
  <span class="ticker-label"><i></i>Live in the verse</span>
  <div class="ticker-row" id="ticker-row"></div>
</section>

<!-- ======================================== 2. THE MOMENT: watch the app catch it ======================================== -->
<section class="moment" id="moment" aria-labelledby="moment-h">
  <div class="moment-bg" aria-hidden="true"><img src="/img/home/fankit-sc-06.webp" alt="" loading="lazy"></div>
  <div class="wrap">
    <div class="sec-head">
      <span class="eyebrow">Every player knows the moment</span>
      <h2 class="h2" id="moment-h">Something breaks. Is it you, or the server?</h2>
      <p class="lede">Pick a moment and watch what the app does: it reads your Game.log as it's written, catches the line that matters, matches it to the known-issues library and gives you the answer in plain words.</p>
    </div>
    <div class="moment-grid">
      <ul class="moments" id="moments" role="tablist" aria-label="Moments"></ul>
      <div class="mo-stage" id="mo-stage" data-step="5" role="tabpanel" aria-labelledby="mo-atc">
        <div class="console">
          <div class="con-bar"><span class="rec" aria-hidden="true"></span><b>Game.log</b><span class="path">StarCitizen\\LIVE\\Game.log</span><button type="button" id="mo-skip">Skip</button></div>
          <div class="log" aria-hidden="true"><ul class="log-lines" id="log-lines"></ul></div>
          <div class="match" id="mo-match"></div>
        </div>
        <div class="answer"><div class="answer-in" id="answer"></div></div>
      </div>
    </div>
  </div>
</section>

<!-- ======================================== 3. THREE PILLARS ======================================== -->
<section class="pillars" aria-labelledby="pillars-h">
  <div class="wrap">
    <div class="sec-head"><span class="eyebrow">What it does</span><h2 class="h2" id="pillars-h">Three things, done properly</h2></div>
    <div class="pillar-list">
      <article class="pillar">
        <div class="pillar-copy">
          <span class="pillar-n">Know your shard</span>
          <h3>A health score out of 100, before you commit to a run</h3>
          <p>Server fps, players on your server, ping and packet loss, rolled into one score. The board pools everyone's readings so you can see which shard and server to hop to.</p>
          <ul><li>Your shard's score, live, beside the game</li><li>The board: every shard players are on, by region</li><li>The healthiest shard and server to hop to</li></ul>
        </div>
        <figure class="scene wm-br" style="margin:0"><img class="bgp" src="/img/home/fankit-sc-14.webp" alt="" loading="lazy">
          ${ringEl({ id: "el-ring", score: 94, word: "Healthy", kv: [["Server fps", "21.5", 86], ["On your server", "37", 62], ["Ping", "33 ms", 90]], where: "AU-90 · server 07 · Seraphim Station, Crusader. Sample reading." })}
          <span class="chip tag">The Now tab</span></figure>
      </article>
      <article class="pillar">
        <div class="pillar-copy">
          <span class="pillar-n">Know what broke</span>
          <h3>The known-issues library grows every week</h3>
          <p>When something goes wrong, the app explains it and lists what helps. What players send in becomes new entries. When it needs CIG, it drafts the Issue Council report with the details they ask for.</p>
          <ul><li><b id="lib-known">41</b>&nbsp;problems it knows, and growing</li><li>Mark this moment: one press, the details are kept</li><li>Issue Council drafts with the log lines filled in</li></ul>
        </div>
        <figure class="scene wm-bl" style="margin:0"><img class="bgp" src="/img/home/fankit-sc-05.webp" alt="" loading="lazy">
          ${wrongEl({ id: "el-wrong", sub: "4 problems this session", items: WRONG_HOME })}
          <span class="chip tag">What's gone wrong?</span></figure>
      </article>
      <article class="pillar">
        <div class="pillar-copy">
          <span class="pillar-n">Know your game</span>
          <h3>Your sessions, blueprints and licences, kept for you</h3>
          <p>Every session gets a report. Blueprints you've earned are collected in one place with a want list. Licences, your week, and a brag card when you've earned one.</p>
          <ul><li>Blueprints earned, and a want list</li><li>Session reports and your week</li><li>Brag cards to post where your mates are</li></ul>
        </div>
        <figure class="scene wm-br" style="margin:0"><img class="bgp" src="/img/home/fankit-sc-34.webp" alt="" loading="lazy">
          ${dealEl("el-deal")}
          <span class="chip tag">Blueprints and brag cards</span></figure>
      </article>
    </div>
  </div>
</section>

<!-- ======================================== 4. THE VERSE IS ALIVE ======================================== -->
<section class="alive hf-scope" id="alive" aria-labelledby="alive-h">
  <div class="alive-bg" aria-hidden="true"><img src="/img/home/fankit-40-03.webp" alt="" loading="lazy"><img src="/img/home/fankit-sc-37.webp" alt="" loading="lazy"></div>
  <div class="wrap">
    <div class="alive-head">
      <span class="eyebrow" style="color:#ffd166">The verse is alive</span>
      <h2 class="h2" id="alive-h">Danger out there. Crew in here.</h2>
      <p class="lede">Pirates working the lanes, patch-day queues, shards fighting for the best health tonight. And the people you'll fly with: orgs, groups recruiting, and everyone's blueprint drops in one table.</p>
      <span class="rule">Shards compete. Players never do.</span>
    </div>
    <div class="stage" id="stage"></div>
    <div class="sides">
      <div class="side tension">
        <div class="side-h"><h3>Tension</h3><span>from the verse, never from players</span></div>
        <div class="tile"><div class="tile-h"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3c-4 0-7 3-7 7 0 2.4 1.1 4.1 3 5v3h8v-3c1.9-.9 3-2.6 3-5 0-4-3-7-7-7zM9 11h.01M15 11h.01M10 21h4"/></svg><h4>Pirate reports</h4><span class="win" id="pir-win">This week</span><a class="more" id="pir-more" href="/board">On the board</a></div>
          <div class="map" id="map"></div><div id="t-pirates"></div></div>
        <div class="two">
          <div class="tile"><div class="tile-h"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20V10M10 20V4M16 20v-8M22 20H2"/></svg><h4>Which shard tonight</h4><span class="win" id="race-win">This week</span></div><div id="t-race"></div></div>
          <div class="tile"><div class="tile-h"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M4 12h10M4 18h6M18 14v6M15 17h6"/></svg><h4>The login queue</h4></div><div id="t-queue"></div></div>
        </div>
      </div>
      <div class="side camaraderie">
        <div class="side-h"><h3>Camaraderie</h3><span id="org-count"></span></div>
        <div class="tile"><div class="tile-h"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/></svg><h4>Orgs flying together</h4><a class="more" href="/community">Community</a></div><div class="fan" id="fan" role="list" aria-label="Orgs"></div></div>
        <div class="two">
          <div class="tile"><div class="tile-h"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM2 20c.8-3.5 3.6-5.5 7-5.5s6.2 2 7 5.5M16 4.5a3.5 3.5 0 0 1 0 6.5M18 14.8c2 .7 3.4 2.4 4 5.2"/></svg><h4>Groups recruiting</h4><span class="win" id="grp-win">This week</span><a class="more" href="/groups">Find a crew</a></div><div id="t-groups"></div></div>
          <div class="tile"><div class="tile-h"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 4h12l4 4v12H4zM8 4v16M4 9h16M4 14h16"/></svg><h4>Where blueprints drop</h4><span class="win" id="bp-win">This week</span></div><div id="t-bp"></div></div>
        </div>
      </div>
    </div>
  </div>
</section>

<!-- ======================================== 5. WHAT IT DOES WITH YOUR PC ======================================== -->
<section class="trust" aria-labelledby="trust-h">
  <div class="wrap">
    <div class="sec-head"><span class="eyebrow">Straight answers</span><h2 class="h2" id="trust-h">What it does with your PC</h2><p class="lede">It reads two things the game already gives you. Nothing crosses the line to the internet unless you switch sharing on. Try the switch.</p></div>
    <div class="flow">
      <div class="pc">
        <div class="pc-h"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 4h18v12H3zM8 20h8M12 16v4"/></svg>Your PC</div>
        <div class="pc-row">
          <div class="src">
            <div class="node"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 3h7l4 4v14H7zM14 3v4h4M10 12h5M10 16h5"/></svg><span><b>Game.log</b><small>the text file the game writes</small></span></div>
            <div class="node"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 5h18v14H3zM7 15l3-4 3 3 4-5"/></svg><span><b>The overlay</b><small>the numbers the game shows (r_displayinfo)</small></span></div>
          </div>
          <div class="wire" aria-hidden="true"></div>
          <div class="app-node"><div><b><svg viewBox="0 0 30 30" fill="none" stroke="#f2a93b" stroke-width="2.4" aria-hidden="true"><circle cx="15" cy="15" r="12"/><path d="M5 17h5l3-7 4 12 3-7h5" stroke-linejoin="round" stroke-linecap="round"/></svg>Verse Shards</b><span>Scores your shard, explains what broke, keeps your sessions and blueprints. All on your PC.</span></div></div>
        </div>
        <p class="stays">It never reads the game's memory or network traffic, and never touches the game itself. <b>Your sessions, blueprints and notes stay on this PC.</b></p>
      </div>
      <div class="gate" id="gate"><span class="gate-lock" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M6 11h12v10H6zM8.5 11V8a3.5 3.5 0 0 1 7 0v3"/></svg></span><span class="gate-lbl" id="gate-lbl">Nothing<br>crosses</span><span class="packet" aria-hidden="true"></span></div>
      <div class="net" id="net">
        <label class="switch"><input type="checkbox" id="share-sw"><span class="sw"></span><span>Sharing <span id="sw-word">off</span></span></label>
        <div class="when-off"><h4>Off by default, and nothing is locked behind it</h4><p>Everything in the app works with sharing off. Switch it on if you'd like your readings to help the board.</p></div>
        <div class="when-on"><h4>One summary every 5 minutes</h4>
          <ul class="goes"><li>The shard and your server's health: fps, players, ping</li><li>Problems the log showed, by kind</li><li class="no">Never your handle</li><li class="no">Never other players' names</li><li class="no">Never screenshots</li></ul></div>
        <p style="font-size:.875rem;color:var(--dim);margin:0">Goes to the board on verseshards.com. Switch it off any time.</p>
      </div>
    </div>
    <div class="facts-row" id="facts"></div>
  </div>
</section>

<!-- ======================================== 6. MADE BY THE COMMUNITY: a full-width scene, the maker's holo card ======================================== -->
<section class="made hf-scope" aria-labelledby="made-h">
  <div class="made-pic" aria-hidden="true"><img src="/img/home/fankit-sc-33.webp" srcset="/img/home/fankit-sc-33-800.webp 800w, /img/home/fankit-sc-33.webp 1200w" sizes="100vw" alt="" loading="lazy"></div>
  <div class="wrap made-in">
    <div class="made-copy">
      <div class="made-top"><img class="mbtc" src="/brag/img/mbtc-white.png" alt="Made by the Community" width="88" height="88"><span class="eyebrow">Made by a player</span></div>
      <h2 id="made-h">Built by <span class="handle">Aurelius_Draco</span>, for everyone in the verse</h2>
      <p>One player in Australia, plus everyone who sends in readings, reviews and ideas.</p>
      <dl class="mk-count" id="mk-count" aria-live="off">
        <div data-mkbox="sharing_week"><dt>Players sharing this week</dt><dd data-mk="sharing_week"></dd></div>
        <div data-mkbox="sessions_shared"><dt>Sessions shared</dt><dd data-mk="sessions_shared"></dd></div>
        <div data-mkbox="updates_shipped"><dt>Updates shipped</dt><dd data-mk="updates_shipped"></dd></div>
      </dl>
      <div class="made-acts">
        <a class="btn primary" href="https://robertsspaceindustries.com/citizens/Aurelius_Draco" target="_blank" rel="noopener"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM2 21c.8-4 3.6-6 7-6s6.2 2 7 6M19 8v6M16 11h6"/></svg>Add me as a friend</a>
        <a class="btn" href="https://discord.gg/8kH5pfHYbe" target="_blank" rel="noopener"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 7.5c3-1.3 7-1.3 10 0l1.5 7.5c-1.8 1.4-3.5 2-5 2l-.8-1.6M7 7.5L5.5 15c1.8 1.4 3.5 2 5 2l.8-1.6M9.5 12h.01M14.5 12h.01"/></svg>Join the Discord</a>
      </div>
    </div>
    <div id="maker" class="made-card"></div>
  </div>
</section>

<!-- ======================================== 7. NEW TO STAR CITIZEN (unchanged) ======================================== -->
<section class="newsc" aria-labelledby="newsc-h">
  <div class="newsc-pic"><img src="/img/home/fankit-sc-30.webp" alt="" loading="lazy"></div>
  <div class="wrap">
    <div class="newsc-card">
      <span class="eyebrow" style="color:#ffd166">New to Star Citizen?</span>
      <h2 id="newsc-h">Start with 50,000 UEC</h2>
      <p>Sign up with the code below and you start with <b>50,000 UEC</b> to spend in game. It's the maker of Verse Shards' referral code.</p>
      <div class="code"><span class="code-box"><span><small>Referral code</small><code id="ref-code">STAR-VD9W-346V</code></span></span><button class="btn" type="button" id="copy-code"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 8h11v12H8zM5 16V4h11"/></svg>Copy</button></div>
      <p class="copied" id="copied" aria-live="polite"></p>
      <div class="ctas" style="margin:0"><a class="btn primary" href="https://www.robertsspaceindustries.com/enlist?referral=STAR-VD9W-346V" target="_blank" rel="noopener">Enlist with the code</a><span class="small">Opens robertsspaceindustries.com. The code is filled in for you.</span></div>
    </div>
  </div>
</section>

<!-- ======================================== 8. LAST CALL ======================================== -->
<section class="last" aria-labelledby="last-h">
  <div class="wrap last-in">
    <div class="last-lights" aria-hidden="true"><i style="--c:#4cc4b0;--k:0"></i><i style="--c:#4cc4b0;--k:1"></i><i style="--c:#c9d1db;--k:2"></i><i style="--c:#4cc4b0;--k:3"></i><i style="--c:#ffd166;--k:4"></i><i style="--c:#4cc4b0;--k:5"></i></div>
    <h2 id="last-h">Get Verse Shards</h2>
    <p>Free for Windows. Next time something breaks, you'll know whether it's you or the server.</p>
    <div class="ctas" id="last-ctas"></div>
  </div>
</section>
</div>`;
  // One section of the home page on its own (About uses "trust" and "made"), in the .hp scope, full width
  function part(cls) {
    const a = MARKUP.search(new RegExp(`<section class="${cls}[ "]`)); if (a < 0) return "";
    const b = MARKUP.indexOf("</section>", a) + "</section>".length;
    return `<div class="hp hp-part">${MARKUP.slice(a, b)}</div>`;
  }
  window.VSHome = {
    markup: () => MARKUP,
    part,
    el: { ring: ringEl, wrong: wrongEl, deal: dealEl, log: logEl, map: mapSvg, scan: scanEl, hcol },
    // draws and wires the parts a page took with part(): trust (the sharing switch, the Store fact) and made (the
    // maker's card and live counters). d is /api/v1/home; without it the counters stay hidden.
    mountParts(root, d, names) {
      ROOT = root; mkSeen = false; mkObs = false; data = d;
      const dd = d || { store: {}, maker: {} };
      if (names.includes("trust") && $("#share-sw")) trust(dd);
      if (names.includes("made") && $("#maker")) maker(dd);
      animate(root);
    },
    animate,
    mount(root, d) {
      ROOT = root; scanMode = "live"; mkSeen = false; mkObs = false;
      moments(); copyCode(); scanControls(); pillars();
      if (d) render(d);
    },
    update(d) { if (d && ROOT !== document && ROOT.isConnected) render(d); },
    stop() { moTimers.forEach(clearTimeout); moTimers = []; ROOT = document; data = null; },
  };
})();
