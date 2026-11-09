/* Verse Shards for PC · My pilot (Claude Design, My pilot round, 9 Nov 2026). Ported for 1.6: the logbook classes are
   mlb-*, mpc-*, mtop and mcnt (the app already had lb-*, pc-*, .top for its header and .cnt); otherwise as designed.
   render(data) returns the page's HTML; mount(root) wires the counters, the card's tilt (holo-foil.js) and the PC fold.
   Everything here is the player's own record, worked out on this PC. Nothing is sent anywhere.

   data = {
     profile: null | {handle, name, org, exp: "new"|"regular"|"veteran", voice: "voice"|"text", region, times, bio,
                      ships: [..], main, acts: [..], fav, pic: dataURL | "", verified: null | {at: unix seconds}},
     shipPics: {"Ship name": "img/ship-....webp"},          // the 13 Fankit renders only
     hours, sessions, contractsDone, contractsTaken, shards: ["AU-90", ..], fpsAvg, fed: null | number (sharing on only),
     logbook: null | {quantum, waits, waitTypical, waitLongest, jurisdictions: [..], downed, injuries, medbed,
                      spent, purchases, sent, received},
     places: [{name, readings, fps}],                       // plain names (Orison, not Crusader_Orison)
     retrieved: [{ship, times}],
     pc: {cpu, threads, gpu, vram, ram, cpuTest, gpuTest, vramUsed}
   } */
(function () {
  "use strict";
  const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const n = v => Number(v || 0).toLocaleString("en-AU");
  const plural = (v, w, ws) => `${n(v)} ${v === 1 ? w : (ws || w + "s")}`;
  const calm = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
  const ic = (d, cls = "ic") => `<svg class="${cls}" viewBox="0 0 24 24" aria-hidden="true"><path d="${d}"/></svg>`;
  const I = {
    card: "M3 6h18v12H3zM3 10h18M7 15h4",
    edit: "M4 20h4l11-11-4-4L4 16zM13 7l4 4",
    tick: "M5 12l5 5 9-10",
    lock: "M6 11h12v9H6zM8.5 11V8a3.5 3.5 0 0 1 7 0v3",
    map: "M9 4L3 6v14l6-2 6 2 6-2V4l-6 2zM9 4v14M15 6v14",
    bed: "M3 18V7M3 14h18v4M21 14v-2a3 3 0 0 0-3-3h-7v5M7 11.5a1.5 1.5 0 1 0 0-.01",
    cart: "M3 4h2l2.4 11h11L21 8H6.3M9 20h.01M17 20h.01",
    pin: "M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11zM12 12.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5z",
    clock: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 7v5l3 2",
    ship: "M3 13l7-2 4-6h3l-2 6 6 2-6 2 2 6h-3l-4-6-7-2z",
    chip: "M7 7h10v10H7zM10 3v4M14 3v4M10 17v4M14 17v4M3 10h4M3 14h4M17 10h4M17 14h4",
    down: "M6 9l6 6 6-6",
    user: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21c1-4 4.5-6 8-6s7 2 8 6"
  };
  const SEAL = `<svg class="seal" viewBox="0 0 24 24" aria-hidden="true"><path class="seal-b" d="M12 2.8l2.4 1.7 2.9-.1.9 2.8 2.3 1.8-.9 2.8.9 2.8-2.3 1.8-.9 2.8-2.9-.1L12 21.2l-2.4-1.7-2.9.1-.9-2.8-2.3-1.8.9-2.8-.9-2.8 2.3-1.8.9-2.8 2.9.1z"/><path class="seal-t" d="M8.5 12.2l2.4 2.4 4.6-4.8"/></svg>`;
  const EXP = { new: "New", regular: "Regular", veteran: "Veteran" }, VOICE = { voice: "Voice", text: "Text only" };
  const initials = h => String(h || "").replace(/[^A-Za-z]/g, "").slice(0, 2).toUpperCase() || "?";
  const day = ts => new Date(ts * 1000).toLocaleDateString("en-AU", { day: "numeric", month: "short", year: "numeric" });
  const mmss = s => s == null ? "" : s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${String(s % 60).padStart(2, "0")} s`;
  // a number that counts up the first time it's seen; the real value is always in the text for screen readers and stills
  const count = (v, dec = 0) => { const t = dec ? Number(v).toFixed(dec) : n(v); return `<span class="vh">${t}</span><span class="mcnt" aria-hidden="true" data-count="${v}" data-dec="${dec}">${t}</span>`; };

  // ---------- the pilot's ID card: the org cards' holo family, front only ----------
  function idCard(p) {
    const ver = p.verified && p.verified.at;
    const picUrl = p.pic ? (/^data:/.test(p.pic) ? p.pic : new URL(p.pic, location.href).href) : "";   // a url() in a custom property resolves against the stylesheet, so make it absolute
    const logo = p.pic ? `style="--logo:url('${esc(picUrl)}')" role="img" aria-label="${esc(p.handle)}'s picture"` : `aria-hidden="true"`;
    const meta = [EXP[p.exp], VOICE[p.voice]].filter(Boolean).map(esc).join(" · ");
    const where = [p.region, p.times].filter(Boolean).map(esc).join(" · ");
    const nameSz = p.handle.length <= 12 ? 40 : p.handle.length <= 18 ? 34 : 28;
    return `<article class="hf-card is-big pilot-card is-in" aria-labelledby="pid-n" style="--acc:#f2a93b;--acc-ink:#1a1103;--name-sz:${nameSz}px">
 <div class="hf-tilt"><div class="hf-face hf-front"><div class="hf-inner">
  <div class="hf-banner" aria-hidden="true"><div class="hf-banner-img is-gen"></div><span class="hf-wm">PILOT</span></div>
  <div class="hf-chips">${ver ? `<span class="hf-chip pid-ver">${SEAL}Verified on RSI</span>` : `<span class="hf-chip pid-unver">Not verified yet</span>`}</div>
  <div class="hf-body">
   <div class="hf-head"><span class="hf-logo${p.pic ? " has-pic" : ""}" ${logo}>${p.pic ? "" : esc(initials(p.handle))}</span>
    <div class="hf-id"><h2 class="hf-name" id="pid-n">${esc(p.handle)}</h2>
     ${p.name ? `<div class="pid-name">${esc(p.name)}</div>` : ""}
     <div class="hf-meta">${p.org ? `<span class="hf-tag">${esc(p.org)}</span>` : ""}${meta ? `<span>${meta}</span>` : ""}</div></div></div>
   ${p.bio ? `<p class="hf-blurb">${esc(p.bio)}</p>` : ""}
   <dl class="pid-facts">
    ${where ? `<div><dt>${ic(I.clock)}Plays</dt><dd>${where}</dd></div>` : ""}
    ${p.fav ? `<div><dt>${ic(I.pin)}Favourite place</dt><dd>${esc(p.fav)}</dd></div>` : ""}
    ${ver ? `<div><dt>${ic(I.tick)}Verified</dt><dd>On RSI, ${esc(day(ver))}</dd></div>` : ""}
   </dl>
   ${(p.acts || []).length ? `<div class="pid-acts" aria-label="What they do in the 'verse">${p.acts.map(a => `<span class="hf-chip is-sm">${esc(a)}</span>`).join("")}</div>` : ""}
  </div><div class="hf-sheen" aria-hidden="true"></div></div></div></div></article>`;
  }

  // the card before there's a profile: the same shape, waiting to be filled in
  function ghostCard() {
    return `<div class="pilot-ghost" aria-hidden="true"><div class="pg-banner"><span>PILOT</span></div>
  <div class="pg-body"><div class="pg-head"><span class="pg-logo">${ic(I.user)}</span><div><span class="pg-line is-name"></span><span class="pg-line is-meta"></span></div></div>
  <span class="pg-line"></span><span class="pg-line is-short"></span><div class="pg-chips"><i></i><i></i><i></i></div></div></div>`;
  }

  // ---------- the main ship: a hangar bay, with the Fankit render on the pad when there is one ----------
  function hangar(p, d) {
    const main = p && p.main, pic = main && d.shipPics && Object.entries(d.shipPics).find(([k]) => k.toLowerCase() === main.toLowerCase());
    const rank = main ? (d.retrieved || []).findIndex(r => r.ship.toLowerCase() === main.toLowerCase()) : -1, ret = rank >= 0 ? d.retrieved[rank].times : 0;
    const others = ((p && p.ships) || []).filter(s => s !== main);
    const facts = [];
    if (ret) facts.push(`<li><b>${count(ret)}</b><span>${ret === 1 ? "time" : "times"} called from a terminal</span></li>`);
    if (rank === 0 && (d.retrieved || []).length > 1) facts.push(`<li><b>No. 1</b><span>your most-called ship</span></li>`);
    if (!ret && main) facts.push(`<li class="is-wait"><span>Calls from a terminal show here once the game logs one.</span></li>`);
    return `<section class="hangar${pic ? " has-pic" : " no-pic"}" aria-labelledby="hg-n">
  <div class="hg-bay" aria-hidden="true"><div class="hg-floor"></div><div class="hg-lights"><i></i><i></i><i></i><i></i><i></i><i></i></div>
   ${pic ? `<img class="hg-ship" src="${esc(pic[1])}" alt="">` : hgPad()}</div>
  <div class="hg-copy"><span class="t-eyebrow">Main ship</span><h2 class="hg-name" id="hg-n">${esc(main || "No main ship yet")}</h2>
   ${main ? (facts.length ? `<ul class="hg-facts">${facts.join("")}</ul>` : "") : `<p class="hg-hint">Pick one in Edit profile: tap a ship you fly to make it your main.</p>`}</div>
  ${others.length ? `<div class="hg-also"><span class="t-label">Also flies</span><div class="hg-chips">${others.map(s => `<span class="chip">${esc(s)}</span>`).join("")}</div></div>` : ""}
  ${pic ? `<p class="hg-credit">Ship render from the Star Citizen Fankit</p>` : ""}
</section>`;
  }
  // the empty pad: landing markings, drawn here, no ship art
  function hgPad() {
    return `<svg class="hg-pad" viewBox="0 0 600 220" aria-hidden="true">
  <g fill="none" stroke-linecap="round">
   <ellipse cx="300" cy="120" rx="250" ry="70" stroke="rgba(242,169,59,.16)" stroke-width="1.5"/>
   <ellipse cx="300" cy="120" rx="190" ry="53" stroke="rgba(242,169,59,.5)" stroke-width="3"/>
   <ellipse cx="300" cy="120" rx="190" ry="53" stroke="rgba(242,169,59,.95)" stroke-width="3" stroke-dasharray="36 22" class="hg-run"/>
   <ellipse cx="300" cy="120" rx="118" ry="33" stroke="rgba(255,209,102,.4)" stroke-width="2"/>
   <path d="M300 82v76M222 120h156" stroke="rgba(255,209,102,.3)" stroke-width="2"/>
   <path d="M142 120l-26-9v18zM458 120l26-9v18z" fill="rgba(242,169,59,.75)" stroke="none"/>
   <path d="M300 62l-10 -14h20zM300 178l-10 14h20z" fill="rgba(242,169,59,.45)" stroke="none"/>
  </g></svg>`;
  }

  // ---------- the logbook ----------
  function ledger(d) {
    const cells = [];
    cells.push(`<div class="lg-c"><dt>Hours played</dt><dd>${d.hours ? count(d.hours) : "<span class='lg-wait'>Under 1</span>"}</dd><p>${plural(d.sessions, "session")}</p></div>`);
    if (d.contractsTaken) {
      const pc = Math.round(d.contractsDone / d.contractsTaken * 100);
      cells.push(`<div class="lg-c"><dt>Contracts completed</dt><dd>${count(d.contractsDone)}</dd><p>of ${n(d.contractsTaken)} taken</p><span class="lg-bar" role="img" aria-label="${d.contractsDone} of ${d.contractsTaken} completed"><i style="--w:${pc}%"></i></span></div>`);
    } else cells.push(`<div class="lg-c is-wait"><dt>Contracts completed</dt><dd><span class="lg-wait">None yet</span></dd><p>Fills in when you finish your first contract.</p></div>`);
    cells.push(`<div class="lg-c"><dt>Shards played on</dt><dd>${count(d.shards.length)}</dd><p>${esc(d.shards.slice(0, 3).join(", "))}${d.shards.length > 3 ? ` and ${d.shards.length - 3} more` : ""}</p></div>`);
    if (d.fpsAvg != null) {
      const at = Math.min(100, d.fpsAvg / 30 * 100);
      cells.push(`<div class="lg-c"><dt>Server fps on your sessions</dt><dd>${count(d.fpsAvg, 1)}</dd><p>Average. About 20 is normal.</p><span class="lg-scale" role="img" aria-label="${d.fpsAvg} against a normal of about 20"><i class="lg-norm" style="--at:${20 / 30 * 100}%"></i><i class="lg-you" style="--at:${at}%"></i></span></div>`);
    }
    if (d.fed) cells.push(`<div class="lg-c is-fed"><dt>Fed the board</dt><dd>${count(d.fed)}</dd><p>summaries shared this week. Thanks.</p></div>`);
    return `<dl class="ledger glass is-edge"><div class="glass-in lg-in">${cells.join("")}</div></dl>`;
  }
  function groups(d) {
    const lb = d.logbook || {};
    const verse = lb.quantum || lb.waits || (lb.jurisdictions || []).length ? `
      <div class="mlb-pair">
       ${lb.quantum ? `<div class="mlb-fig"><b>${count(lb.quantum)}</b><span>quantum ${lb.quantum === 1 ? "jump" : "jumps"}</span></div>` : `<div class="mlb-fig is-wait"><span>Quantum jumps show after your first one.</span></div>`}
       ${lb.waits ? `<div class="mlb-fig"><b>${esc(mmss(lb.waitTypical))}</b><span>typical wait for your ship. Longest ${esc(mmss(lb.waitLongest))}, over ${plural(lb.waits, "wait")}.</span></div>` : `<div class="mlb-fig is-wait"><span>Your wait for your ship shows once you've called it from a terminal.</span></div>`}
      </div>
      ${(lb.jurisdictions || []).length ? `<div class="mlb-jur-h">Jurisdictions you've been in <b>${lb.jurisdictions.length}</b></div><div class="mlb-jur">${lb.jurisdictions.map(j => `<span class="jur${/^ungoverned$/i.test(j) ? " is-lawless" : ""}"><i></i>${esc(j)}</span>`).join("")}</div>` : ""}`
      : `<p class="mlb-wait">Quantum jumps, waits for your ship and the jurisdictions you've been in fill in as you fly.</p>`;
    const wear = lb.injuries || lb.downed || lb.medbed ? `
      <div class="mlb-fig"><b>${count(lb.downed || 0)}</b><span>${lb.downed === 1 ? "time" : "times"} downed</span></div>
      <dl class="mlb-rows"><div><dt>Injuries the game reported</dt><dd>${n(lb.injuries)}</dd></div><div><dt>Healed at a med bed</dt><dd>${n(lb.medbed)}</dd></div></dl>`
      : `<p class="mlb-wait">Nothing yet. Times downed, injuries and med bed visits show here when the game logs them.</p>`;
    const money = lb.spent || lb.sent || lb.received ? `
      <div class="mlb-fig"><b>${count(lb.spent || 0)}</b><span>spent at shops, ${plural(lb.purchases, "purchase")}</span></div>
      <dl class="mlb-rows"><div><dt>Sent to players</dt><dd>${n(lb.sent)}</dd></div><div><dt>Received</dt><dd>${n(lb.received)}</dd></div></dl>
      <p class="mlb-note">Contract pay and sales aren't logged.</p>`
      : `<p class="mlb-wait">Shop purchases and aUEC sent or received show once the game logs one. Contract pay and sales aren't logged.</p>`;
    return `<div class="mlb-groups">
     <section class="mlb-g is-verse"><h3>${ic(I.map)}Out in the 'verse</h3>${verse}</section>
     <section class="mlb-g is-wear"><h3>${ic(I.bed)}Wear and tear</h3>${wear}</section>
     <section class="mlb-g is-money"><h3>${ic(I.cart)}aUEC the game logged</h3>${money}</section></div>`;
  }
  function tops(d) {
    const pl = (d.places || []).slice(0, 4), rt = (d.retrieved || []).slice(0, 4);
    const maxP = Math.max(1, ...pl.map(x => x.readings)), maxR = Math.max(1, ...rt.map(x => x.times));
    return `<div class="lb-tops">
     <section class="mtop"><h3>${ic(I.pin)}Most-visited places</h3>${pl.length ? `<ol>${pl.map(x => `<li><span class="top-n">${esc(x.name)}</span><span class="top-v">${plural(x.readings, "reading")} · <b>${n(x.fps)} fps</b></span><span class="top-bar"><i style="--w:${x.readings / maxP * 100}%"></i></span></li>`).join("")}</ol>` : `<p class="mlb-wait">Shows once the overlay has been read in a few places.</p>`}</section>
     <section class="mtop"><h3>${ic(I.ship)}Ships retrieved most</h3>${rt.length ? `<ol>${rt.map(x => `<li><span class="top-n">${esc(x.ship)}</span><span class="top-v"><b>${plural(x.times, "time")}</b></span><span class="top-bar"><i style="--w:${x.times / maxR * 100}%"></i></span></li>`).join("")}</ol>` : `<p class="mlb-wait">Shows once you've called a ship from a terminal.</p>`}</section></div>`;
  }
  function pcFold(d) {
    const h = d.pc; if (!h) return "";
    const loc = (d.places || []).concat(d.morePlaces || []);
    return `<details class="pc-fold"><summary><span class="pc-sum">${ic(I.chip)}<span><b>Your PC</b><span class="mpc-sub">${esc(h.cpu)} · ${esc(h.gpu)} · as the game reports it at start-up</span></span></span><span class="pc-open"><span class="o-show">Show</span><span class="o-hide">Hide</span>${ic(I.down)}</span></summary>
     <div class="pc-body">
      <dl class="pc-hw"><div><dt>CPU</dt><dd>${esc(h.cpu)}</dd><p>${h.threads} threads</p></div><div><dt>Graphics</dt><dd>${esc(h.gpu)}</dd><p>${esc(h.vram)} video memory</p></div><div><dt>Memory</dt><dd>${esc(h.ram)}</dd></div>
       <div><dt>Game's CPU test</dt><dd>${h.cpuTest}<small>ms</small></dd><p>lower is faster</p></div><div><dt>Game's GPU test</dt><dd>${h.gpuTest}<small>ms</small></dd><p>lower is faster</p></div></dl>
      ${loc.length ? `<h3 class="mpc-h">Your frame rate by location <span>from overlay readings this run</span></h3><div class="scrollbox"><table class="dt"><thead><tr><th>Location</th><th class="num">Your fps</th><th class="num">Readings</th></tr></thead><tbody>${loc.map(x => `<tr><td>${esc(x.name)}</td><td class="num">${n(x.fps)}</td><td class="num">${n(x.readings)}</td></tr>`).join("")}</tbody></table></div>` : ""}
      ${h.vramUsed ? `<p class="mpc-note">Video memory in use: ${esc(h.vramUsed)}.</p>` : ""}</div></details>`;
  }

  // ---------- the page ----------
  function render(d) {
    const p = d.profile, ver = p && p.verified;
    const acts = `<div class="mp-acts">
      ${p && !ver ? `<button class="btn" type="button" data-act="verify">${SEAL}Verify on RSI</button>` : ""}
      ${p ? `<button class="btn" type="button" data-act="edit">${ic(I.edit)}Edit profile</button>` : ""}
      <button class="btn is-primary mp-make" type="button" data-act="brag">${ic(I.card)}<span><b>Make a pilot card</b><small>${p ? "A picture to post for your mates" : "Works from your logbook alone"}</small></span></button></div>`;
    const head = `<header class="mp-head"><div class="mp-title"><span class="t-eyebrow">My pilot</span><h1>${p ? "Your ID card and logbook" : "Your logbook, and a card to go with it"}</h1>
      <p class="mp-local">${ic(I.lock)}Your profile stays on this PC. It's never sent anywhere.</p></div>${acts}</header>`;
    const hero = p ? `<div class="mp-hero">${idCard(p)}${hangar(p, d)}</div>` : `<div class="mp-hero is-empty">${ghostCard()}
      <section class="mp-setup" aria-labelledby="su-h"><span class="t-eyebrow">Pilot card</span><h2 id="su-h">Put your name on this page</h2>
       <p>Your handle, your main ship and what you fly for. It shows here and on the pilot cards you make for your mates. About a minute, and all of it's optional apart from your handle.</p>
       <ul class="su-list"><li>${ic(I.user)}<span><b>Handle and picture</b>Your initials if you'd rather not add a picture</span></li><li>${ic(I.ship)}<span><b>Main ship</b>Plus the others you fly</span></li><li>${ic(I.map)}<span><b>What you do</b>Hauling, mining, medical and the rest</span></li></ul>
       <div class="su-acts"><button class="btn su-go" type="button" data-act="edit">Set up my pilot card</button><span class="su-note">The logbook below fills in by itself either way.</span></div></section></div>`;
    const thin = d.sessions <= 1;
    return `<div class="mp hf-scope">${head}${hero}
     <section class="mp-log" aria-labelledby="lg-h"><div class="sh"><h2 id="lg-h">Logbook</h2><p>${thin ? "Your first session is in. The rest fills in from Game.log as you play." : "Worked out from Game.log and your readings on this patch. It updates as you play."}</p></div>
      ${ledger(d)}${groups(d)}${tops(d)}</section>
     ${pcFold(d)}</div>`;
  }

  function mount(root) {
    if (window.VSHolo) window.VSHolo.mount(root);
    // numbers count up once, the first time they're on screen
    const run = el => {
      const to = +el.dataset.count, dec = +el.dataset.dec || 0, t0 = performance.now(), D = 900;
      const step = t => { const k = Math.min(1, (t - t0) / D), e = 1 - Math.pow(1 - k, 3), v = to * e;
        el.textContent = dec ? v.toFixed(dec) : Math.round(v).toLocaleString("en-AU"); if (k < 1) requestAnimationFrame(step); else el.textContent = dec ? to.toFixed(dec) : to.toLocaleString("en-AU"); };
      requestAnimationFrame(step);
    };
    const cs = root.querySelectorAll(".mcnt[data-count]");
    if (calm() || !("IntersectionObserver" in window)) return;
    const io = new IntersectionObserver(es => es.forEach(en => { if (en.isIntersecting) { run(en.target); io.unobserve(en.target); } }), { threshold: .6 });
    cs.forEach(el => io.observe(el));
  }
  window.VSPilot = { render, mount };
})();
