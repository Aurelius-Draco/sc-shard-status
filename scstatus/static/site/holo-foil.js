/* Verse Shards · Holo foil cards (Claude Design, Orgs page round 2b, 1a Holo foil).
   Ported from the handoff's reference/holo-foil.js v1 (4 Nov 2026). Render functions return HTML strings, mount() wires
   behaviour. site.js maps the live orgs onto the spec's data shapes (section 4) and fills VSHolo.hooks.
   Changes from the reference, all for live data:
   - o7 and I'm a member start pressed for this browser and are saved through hooks.toggle; every copy of the same org
     on the page (month card, rivalry, grid, deck) changes together, and a failed save puts the press back
   - Add to calendar uses hooks.cal (the site's calendar file, with the notes and links) when it's there
   - RSI focus areas the design has no drawing for use RSI's own icon in the org's colour
   - no meeting point, no RSI member count, no taunt or a missing type, commitment or region leaves that part out
   - Muster call doesn't throw when the browser refuses the clipboard
   - after turning over, focus moves to the other side again if that side wasn't showing yet the first time
   - Turn over can be switched off (VSHolo.turnOver = false: no button, no back), which the site does for now (Ray, 3 Nov)
   - the org's name and the event's title are links to the org's page, so the card opens it from the keyboard too */
(function () {
  "use strict";
  const MIN = 60000, SOON = 120 * MIN;
  const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const ICON = {
    medical: "M9 3h6v6h6v6h-6v6H9v-6H3V9h6z", security: "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z",
    transport: "M3 7l9-4 9 4v10l-9 4-9-4zM3 7l9 4 9-4M12 11v10", mining: "M4 20l7-7M9 6l6-3 6 6-3 6M9 6l9 9M9 6L6 9l9 9 3-3",
    exploration: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM15.5 8.5l-2 5-5 2 2-5z", piracy: "M5 10a7 6 0 0 1 14 0c0 3-2 4-2 6H7c0-2-2-3-2-6zM9 11h.01M15 11h.01M8 20h8",
    racing: "M5 21V4M5 4h13l-3 4 3 4H5", bounty: "M12 3v4M12 17v4M3 12h4M17 12h4M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10z",
    discord: "M7 7.5c3-1.3 7-1.3 10 0l1.5 7.5c-1.8 1.4-3.5 2-5 2l-.8-1.6M7 7.5L5.5 15c1.8 1.4 3.5 2 5 2l.8-1.6M9.5 12h.01M14.5 12h.01",
    youtube: "M3 8.5C3 7 4 6 5.5 6h13C20 6 21 7 21 8.5v7c0 1.5-1 2.5-2.5 2.5h-13C4 18 3 17 3 15.5zM10 9.5v5l4.5-2.5z",
    twitch: "M5 3h15v10l-4 4h-4l-3 3v-3H5zM11 7v4M15 7v4", x: "M5 4l14 16M19 4L5 20",
    web: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18"
  };
  const TYPES = {
    Op: { c: "#ec7a5e", d: "M12 3v4M12 17v4M3 12h4M17 12h4M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z" },
    Meetup: { c: "#4cc4b0", d: "M8 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM16 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM3 20c0-3 2.5-5 5-5s5 2 5 5M11 20c0-3 2.5-5 5-5s5 2 5 5" },
    Race: { c: "#ffd166", d: "M5 21V4M5 4h14v9H5M5 4h3.5v3H12V4h3.5v3H19M8.5 7v3H5M12 7v3h3.5V7M15.5 10v3M8.5 10v3" },
    Training: { c: "#a9c0d8", d: "M3 9l9-5 9 5-9 5zM7 11.5V16c3 2 7 2 10 0v-4.5M21 9v5" },
    Social: { c: "#f2a93b", d: "M5 8h11v6a4 4 0 0 1-4 4H9a4 4 0 0 1-4-4zM16 9h2a2 2 0 0 1 0 4h-2M8 3v2M11 3v2" },
    Other: { c: "#c3cad3", d: "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z" }
  };
  const svg = (d, w = 1.8) => `<svg viewBox="0 0 24 24" fill="none" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${d}"/></svg>`;
  const NEWTAB = `<span class="vh">(opens in a new tab)</span>`;

  // Time
  const stateOf = (e, now = Date.now()) => !e ? "none" : now >= e.start + e.dur * MIN ? "done" : now >= e.start ? "now" : e.start - now <= SOON ? "soon" : "upcoming";
  const fmtWhen = ms => new Intl.DateTimeFormat("en-AU", { weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit", hour12: true, timeZoneName: "short" }).format(ms).replace(/\s?(am|pm)/i, m => " " + m.trim().toLowerCase());
  const countdown = ms => { const s = Math.max(0, Math.floor(ms / 1000)); return `${Math.floor(s / 3600)}:${String(Math.floor(s % 3600 / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`; };
  const minsIn = (e, now) => { const m = Math.max(1, Math.round((now - e.start) / MIN)); return m < 60 ? `${m} min in` : `${Math.floor(m / 60)} h ${m % 60} min in`; };
  const dur = m => m < 60 ? `${m} min` : m % 60 ? `${Math.floor(m / 60)} h ${m % 60} min` : `${m / 60} h`;
  const progOf = (e, now) => Math.max(.02, Math.min(1, 1 - (e.start - now) / SOON));

  // Colour: pick dark or white text for the accent (WCAG contrast 4.5:1 either way)
  const lum = hex => [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255).map(v => v <= .03928 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4).reduce((a, v, i) => a + v * [.2126, .7152, .0722][i], 0);
  const inkFor = hex => lum(hex) > .19 ? "#0b0e12" : "#ffffff";
  const nameSize = (name, base) => { const n = name.length; return Math.round(base * (n <= 14 ? 1 : n <= 24 ? .86 : n <= 32 ? .74 : .66)); };
  const meta = o => [o.type, o.commit, o.region].filter(Boolean).map(esc).join(" · ");
  const mono = o => o.logo ? "" : esc(o.tag.slice(0, 3));
  const logoVar = o => o.logo ? `--logo:url('${esc(o.logo)}');` : "";

  function fleet(members, max) {
    const n = Math.max(3, Math.min(max, Math.round(Math.log2(members + 1) * 1.7)));
    let s = ""; for (let i = 0; i < n; i++) s += `<svg style="--i:${i};--o:${(.4 + .6 * i / Math.max(1, n - 1)).toFixed(2)}" viewBox="0 0 13 10"><path d="M1 5L12 1L9.4 5L12 9Z"/></svg>`;
    return s;
  }
  function whenText(e, st, now, style) {
    if (st === "soon") return style === "line" ? `Starts in ${countdown(e.start - now)}` : countdown(e.start - now);
    if (st === "now") return `On now · ${minsIn(e, now)}`;
    return fmtWhen(e.start);
  }
  const kicker = (e, st) => `${e.type} · ${st === "soon" ? "starting soon" : st === "now" ? "live" : "next"}`;

  // ---------- org card ----------
  // opt: { size: "normal" | "big" | "phone", events: [upcoming events for this org, soonest first], month, rival, face: "14deg", members (your count), reacts }
  function card(o, opt = {}) {
    const turn = H.turnOver !== false;
    const size = opt.size || "normal", big = size === "big", phone = size === "phone";
    const evs = (opt.events || []).filter(e => stateOf(e) !== "done"), e = evs[0], now = Date.now(), st = stateOf(e, now);
    const T = e ? (TYPES[e.type] || TYPES.Other) : TYPES.Other, id = "hf-" + esc(o.id) + "-" + (opt.key || size);
    const chips = [
      opt.month ? `<span class="hf-chip is-month">Org of the month</span>` : "",
      o.recruiting ? `<span class="hf-chip is-rec"><i></i>Recruiting</span>` : "",
      e ? `<span class="hf-chip is-soon" role="timer"><i></i><span data-when="line">${whenText(e, "soon", now, "line")}</span></span><span class="hf-chip is-now"><i></i>On now</span>` : "",
      opt.rival ? `<span class="hf-chip is-rival">Rivals</span>` : ""
    ].join("");
    const thx = (o.thanks || [])[0];
    const memberBtn = `<button type="button" class="hf-pill" data-toggle="member" aria-pressed="${!!o.mineMember}"><span class="hf-ic hf-pop-target">${o.mineMember ? "✓" : "+"}</span><span data-label>${o.mineMember ? "You're a member" : "I'm a member"}</span><b data-n>${o.vsMembers || 0}</b></button>`;
    const o7Btn = `<button type="button" class="hf-pill is-o7" data-toggle="o7" aria-pressed="${!!o.mineO7}" aria-label="o7"><span class="hf-ic hf-pop-target">o7</span><b data-n>${o.o7 || 0}</b></button>`;
    const links = (o.links || []).map(([n, k, href]) => `<a href="${esc(href || "#")}" target="_blank" rel="noopener" aria-label="${esc(n)} (opens in a new tab)" title="${esc(n)}">${svg(ICON[k] || ICON.web)}</a>`).join("");
    const backList = evs.slice(0, 3).map(v => { const s = stateOf(v, now); return `<li style="--tc:${(TYPES[v.type] || TYPES.Other).c}"><i></i><span><b>${esc(v.title)}</b></span><span>${esc(whenText(v, s, now, "line"))}</span></li>`; }).join("");
    return `<article class="hf-card is-${size}" id="${id}" data-org="${esc(o.id)}" aria-labelledby="${id}-n" data-state="${st}" ${e ? `data-start="${e.start}" data-dur="${e.dur}" data-type="${esc(e.type)}"` : ""}
  style="--acc:${o.accent};--acc-ink:${inkFor(o.accent)};--name-sz:${nameSize(o.name, big ? 46 : phone ? 25 : 29)}px;${opt.face ? `--face:${opt.face};` : ""}">
 <div class="hf-tilt">
  <div class="hf-face hf-front"><div class="hf-inner">
   <div class="hf-banner" aria-hidden="true"><div class="hf-banner-img${o.banner ? "" : " is-gen"}"${o.banner ? ` style="--banner:url('${esc(o.banner)}')"` : ""}></div>${o.banner ? "" : `<span class="hf-wm">${esc(o.tag)}</span>`}</div>
   <div class="hf-chips">${chips}</div>
   <div class="hf-body">
    <div class="hf-head"><span class="hf-logo" style="${logoVar(o)}" ${o.logo ? `role="img" aria-label="${esc(o.name)} logo"` : 'aria-hidden="true"'}>${mono(o)}</span>
     <div class="hf-id"><h3 class="hf-name" id="${id}-n">${o.pageUrl ? `<a class="hf-open" href="${esc(o.pageUrl)}">${esc(o.name)}</a>` : esc(o.name)}</h3><div class="hf-meta"><span class="hf-tag">${esc(o.tag)}</span><span>${meta(o)}</span></div></div></div>
    <div class="hf-focus">${(o.focus || []).map(([n, k, pic]) => `<span>${ICON[k] ? svg(ICON[k], 2) : pic ? `<i class="hf-fi" style="--i:url('${esc(pic)}')" aria-hidden="true"></i>` : ""}${esc(n)}</span>`).join("")}</div>
    <p class="hf-blurb">${esc(o.blurb)}</p>
    <div class="hf-crew">${o.members ? `<div class="hf-fleet" aria-hidden="true">${fleet(o.members, big ? 32 : 22)}</div>` : ""}
     <div class="hf-counts">${o.members ? `<span><b>${o.members.toLocaleString("en-AU")}</b> members on RSI</span>` : ""}<span><span data-vs>${o.vsMembers || 0}</span> say they're members</span>${thx ? `<span class="hf-thx">“${esc(thx[0])}” · ${thx[1]}</span>` : ""}</div></div>
    ${e ? `<div class="hf-ev" style="--tc:${T.c}"><span class="hf-ev-kick">${svg(T.d, 2.1)}<span data-kicker>${esc(kicker(e, st))}</span></span><b class="hf-ev-title">${esc(e.title)}</b><span class="hf-ev-when" data-when="box">${esc(whenText(e, st, now, "box"))}</span><span class="hf-ev-bar" aria-hidden="true"></span></div>` : ""}
    <div class="hf-noev">No events coming up</div>
    ${big ? `<div class="hf-row">${o7Btn}${memberBtn}</div>` : ""}
    <div class="hf-actions">
     <a class="hf-btn is-join" href="${esc(o.rsiUrl || "#")}" target="_blank" rel="noopener">Join on RSI ↗${NEWTAB}</a>
     ${o.discordUrl ? `<a class="hf-btn" href="${esc(o.discordUrl)}" target="_blank" rel="noopener">Discord ↗${NEWTAB}</a>` : ""}
     <button type="button" class="hf-btn is-quiet" data-share="${esc(o.id)}">Share</button>
     <span class="hf-grow"></span>
     ${turn ? `<button type="button" class="hf-more" data-flip aria-expanded="false" aria-controls="${id}-back">Turn over</button>` : ""}
    </div>
   </div>
   <div class="hf-sheen" aria-hidden="true"></div>
  </div></div>
  ${turn ? `<div class="hf-face hf-back" id="${id}-back"><div class="hf-inner">
   <div class="hf-back-head"><span class="hf-logo" style="${logoVar(o)}" aria-hidden="true">${mono(o)}</span><div><h3 tabindex="-1">${esc(o.name)}</h3><span class="hf-tag">${esc(o.tag)}</span></div></div>
   <span class="hf-label">Next out</span>
   ${backList ? `<ul class="hf-list">${backList}</ul>` : `<span style="font-size:14px;color:var(--muted)">Nothing on the calendar yet.</span>`}
   ${(o.thanks || []).length ? `<span class="hf-label">Thanks</span><div class="hf-thanks">${o.thanks.slice(0, 3).map(t => `<span>${esc(t[0])} <b>${t[1]}</b></span>`).join("")}</div>` : ""}
   ${links ? `<div class="hf-links">${links}</div>` : ""}
   <div class="hf-row">${memberBtn}${o7Btn}</div>
   <div class="hf-back-foot"><a href="${esc(o.pageUrl || "#")}" style="font-size:14px;font-weight:600">Open the org page →</a><span class="hf-grow"></span><button type="button" class="hf-btn" data-flip aria-expanded="true">Turn back</button></div>
  </div></div>` : ""}
 </div>
</article>`;
  }

  // ---------- event card ----------
  function eventCard(e, o, opt = {}) {
    const now = Date.now(), st = stateOf(e, now), T = TYPES[e.type] || TYPES.Other, id = "hfe-" + esc(e.id) + (opt.narrow ? "-n" : "");
    return `<article class="hf-evcard${opt.narrow ? " is-narrow" : ""}" id="${id}" data-org="${esc(o.id)}" data-ev="${esc(e.id)}" aria-labelledby="${id}-t" data-state="${st}" data-start="${e.start}" data-dur="${e.dur}" data-type="${esc(e.type)}"
  data-muster="${esc(`Muster: ${o.name} [${o.tag}], ${e.title}. ${fmtWhen(e.start)}${e.meet ? `, meet at ${e.meet}` : ""}. Details: verseshards.com/community/orgs/${o.slug || o.id}`)}"
  data-ics-title="${esc(o.name + ": " + e.title)}" data-meet="${esc(e.meet)}" style="--acc:${o.accent};--tc:${T.c}">
 <div class="hf-ev-tilt"><div class="hf-ev-edge"><div class="hf-ev-inner">
  <div class="hf-ev-pic" aria-hidden="true"><div class="hf-ev-pic-img${o.banner ? "" : " is-gen"}"${o.banner ? ` style="--banner:url('${esc(o.banner)}')"` : ""}></div><span class="hf-ev-type">${svg(T.d, 2.2)}${esc(e.type)}</span></div>
  <div class="hf-ev-body">
   <div class="hf-ev-top"><span class="hf-chip is-sm is-soon"><i></i>Starting soon</span><span class="hf-chip is-sm is-now"><i></i>On now</span><span class="hf-tag">${esc(o.tag)}</span><span class="hf-ev-org">${esc(o.name)}</span></div>
   <h3 id="${id}-t">${o.pageUrl ? `<a class="hf-open" href="${esc(o.pageUrl)}" data-ev-open="${esc(e.id)}">${esc(e.title)}</a>` : esc(e.title)}</h3>
   <span class="hf-ev-when" data-when="line" role="timer">${esc(whenText(e, st, now, "line"))}</span>
   <span class="hf-ev-sub">${dur(e.dur)}${e.meet ? ` · ${esc(e.meet)}` : ""}</span>
   <span class="hf-ev-note" data-note hidden>Muster line copied. Paste it in global or org chat.</span>
   <div class="hf-ev-acts"><button type="button" class="hf-btn" data-cal>Add to calendar</button><button type="button" class="hf-btn" data-muster-btn>Muster call</button><button type="button" class="hf-btn is-quiet" data-share-event="${esc(e.id)}">Share</button></div>
  </div>
  <div class="hf-sheen hf-ev-sheen" aria-hidden="true"></div>
 </div></div></div>
</article>`;
  }

  // ---------- rivalry: two cards face off, the 3D Verse Shards logo is the VS ----------
  const VS_LOGO = sz => `<span class="hf-vs" aria-hidden="true"><span><svg width="${sz}" height="${sz}" viewBox="0 0 30 30" fill="none">${[["#3a1a12", 2.6], ["#a84a35", 1.3], ["#f2a93b", 0]].map(([c, d], i) =>
    `<g transform="translate(${d} ${d})" stroke="${c}" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="15" cy="15" r="12" fill="${i === 2 ? "#0b0e12" : "none"}"/><path d="M5 17h5l3-7 4 12 3-7h5"/></g>`).join("")}</svg></span></span>`;
  function rivalry(a, b, r, opt = {}) {
    const days = Math.ceil((r.ends - Date.now()) / 86400000), clash = r.clash;
    return `<section class="hf-riv" aria-label="${esc(a.name)} and ${esc(b.name)} are rivals">
 <div class="hf-riv-side">${card(a, { events: opt.eventsA, rival: true, face: "14deg", key: "riv" })}${r.taunt[a.id] ? `<div class="hf-taunt is-a">“${esc(r.taunt[a.id])}”</div>` : ""}</div>
 <div class="hf-riv-mid">${VS_LOGO(110)}<span class="vh">versus</span><b class="hf-riv-left">${days} days left</b>
  ${clash ? `<span class="hf-label" style="color:var(--muted)">Next clash</span><b style="font-size:16px;font-weight:600">${esc(clash.title)}</b><span style="font-size:13px;color:var(--muted)">${esc(fmtWhen(clash.start))}${clash.meet ? ` · ${esc(clash.meet)}` : ""}</span>` : ""}</div>
 <div class="hf-riv-side">${card(b, { events: opt.eventsB, rival: true, face: "-14deg", key: "riv" })}${r.taunt[b.id] ? `<div class="hf-taunt is-b">“${esc(r.taunt[b.id])}”</div>` : ""}</div>
</section>`;
  }

  // ---------- plain list row (List view) ----------
  function listRow(o, e) {
    const st = stateOf(e);
    return `<div class="hf-listrow" data-org="${esc(o.id)}" style="--acc:${o.accent}"><span class="hf-logo" style="${logoVar(o)}" aria-hidden="true">${mono(o)}</span>
 <div style="min-width:0"><b style="font-size:16px">${esc(o.name)}</b> <span class="hf-tag">${esc(o.tag)}</span><div style="font-size:13px;color:var(--muted)">${meta(o)}</div></div>
 <div style="font-size:13px;color:var(--muted)">${esc((o.focus || []).map(f => f[0]).join(", "))}${o.recruiting ? ` · <span style="color:var(--teal-text);font-weight:600">Recruiting</span>` : ""}</div>
 <div style="font-size:13px;color:${st === "soon" ? "var(--amber-text)" : st === "now" ? "var(--teal-text)" : "var(--muted)"}">${e ? `${esc(e.title)} · ${st === "soon" ? "starting soon" : st === "now" ? "on now" : esc(fmtWhen(e.start))}` : "No events coming up"}</div>
 <div style="display:flex;gap:8px;align-items:center"><a class="hf-btn is-join" style="height:34px;--acc-ink:${inkFor(o.accent)}" href="${esc(o.rsiUrl || "#")}" target="_blank" rel="noopener">Join on RSI ↗${NEWTAB}</a><a href="${esc(o.pageUrl || "#")}" style="font-size:13px;font-weight:600">Open</a></div>
</div>`;
  }

  // ---------- behaviour ----------
  const calm = () => matchMedia("(prefers-reduced-motion: reduce)").matches || document.documentElement.classList.contains("hf-calm");
  const clamp = v => Math.max(-1, Math.min(1, v));
  function setXY(el, x, y) {
    el.style.setProperty("--x", x.toFixed(3)); el.style.setProperty("--y", y.toFixed(3));
    el.style.setProperty("--ang", (x || y) ? (Math.atan2(y, x) * 180 / Math.PI + 90).toFixed(0) + "deg" : "135deg");
  }
  function bindTilt(el) {
    let raf = 0, px = 0, py = 0;
    el.addEventListener("pointermove", ev => {
      if (ev.pointerType === "touch" || calm() || el.closest(".hf-deck")) return;
      const r = el.getBoundingClientRect(); px = clamp((ev.clientX - r.left) / r.width * 2 - 1); py = clamp((ev.clientY - r.top) / r.height * 2 - 1);
      if (!raf) raf = requestAnimationFrame(() => { raf = 0; el.classList.add("is-on"); setXY(el, px, py); });
    });
    el.addEventListener("pointerleave", () => { cancelAnimationFrame(raf); raf = 0; if (el.closest(".hf-deck")) return; el.classList.remove("is-on"); setXY(el, 0, 0); });
  }
  function bindFlip(el) {
    const front = el.querySelector(".hf-front"), back = el.querySelector(".hf-back"); if (!back) return;
    back.inert = true;
    el.querySelectorAll("[data-flip]").forEach(b => b.addEventListener("click", () => {
      const on = !el.hasAttribute("data-flipped");
      el.classList.add("is-flipping"); setTimeout(() => el.classList.remove("is-flipping"), 800);
      el.toggleAttribute("data-flipped", on); el.style.setProperty("--flip", on ? 1 : 0);
      front.inert = on; back.inert = !on;
      el.querySelectorAll("[data-flip]").forEach(x => x.setAttribute("aria-expanded", String(on)));
      const to = on ? back.querySelector("h3") : front.querySelector("[data-flip]"), go = () => to.focus({ preventScroll: true });
      let n = 0; const tryIt = () => { go(); if (document.activeElement !== to && ++n < 8) setTimeout(tryIt, 100); };   // again until that side is showing
      setTimeout(tryIt, calm() ? 0 : 350);
    }));
  }
  function bindDeck(deck) {
    const cards = [...deck.querySelectorAll(".hf-card")], dots = deck.parentElement.querySelectorAll(".hf-dots span"); let raf = 0;
    const upd = () => {
      raf = 0; if (!cards.length) return;
      const step = cards[1] ? cards[1].offsetLeft - cards[0].offsetLeft : 314, sl = deck.scrollLeft;
      let act = 0;
      cards.forEach((c, i) => {
        const d = (c.offsetLeft - cards[0].offsetLeft - sl) / step, a = Math.min(1, Math.abs(d));
        if (Math.abs(d) < .5) act = i;
        if (calm()) { c.style.removeProperty("--ds"); c.style.removeProperty("--do"); setXY(c, 0, 0); return; }
        setXY(c, clamp(-d * .9), 0); c.style.setProperty("--ds", (1 - a * .08).toFixed(3)); c.style.setProperty("--do", (1 - a * .35).toFixed(2));
      });
      dots.forEach((dot, i) => dot.classList.toggle("is-on", i === act));
    };
    deck.addEventListener("scroll", () => { if (!raf) raf = requestAnimationFrame(upd); }, { passive: true });
    upd();
  }
  function bindSpot(host) {
    let raf = 0, p = [0, 0];
    host.addEventListener("pointermove", ev => { if (calm() || ev.pointerType === "touch") return; const r = host.getBoundingClientRect(); p = [ev.clientX - r.left, ev.clientY - r.top];
      if (!raf) raf = requestAnimationFrame(() => { raf = 0; host.style.setProperty("--sx", p[0].toFixed(0) + "px"); host.style.setProperty("--sy", p[1].toFixed(0) + "px"); }); });
    host.addEventListener("pointerleave", () => { host.style.setProperty("--sx", "-2000px"); host.style.setProperty("--sy", "-2000px"); });
  }
  function ics(el) {
    const z = ms => new Date(ms).toISOString().replace(/[-:]/g, "").replace(/\.\d+/, ""), s = +el.dataset.start, e = s + el.dataset.dur * MIN;
    const body = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Verse Shards//Orgs//EN", "BEGIN:VEVENT", `UID:${el.id}@verseshards.com`, `DTSTAMP:${z(Date.now())}`, `DTSTART:${z(s)}`, `DTEND:${z(e)}`,
      `SUMMARY:${el.dataset.icsTitle}`, `LOCATION:${el.dataset.meet}`, "END:VEVENT", "END:VCALENDAR"].join("\r\n");
    const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([body], { type: "text/calendar" })); a.download = el.id + ".ics"; a.click();
  }

  // One shared ticker for the whole page: updates every countdown once a second, flips states at the right moment
  let live;
  function tick() {
    const now = Date.now();
    document.querySelectorAll(".hf-card[data-start], .hf-evcard[data-start]").forEach(el => {
      const e = { start: +el.dataset.start, dur: +el.dataset.dur, type: el.dataset.type }, st = stateOf(e, now);
      if (el.dataset.state !== st) el.dataset.state = st;
      if (st === "soon") el.style.setProperty("--prog", progOf(e, now).toFixed(4));
      el.querySelectorAll(".hf-front [data-when], .hf-ev-body [data-when]").forEach(w => { const t = whenText(e, st, now, w.dataset.when); if (w.textContent !== t) w.textContent = t; });
      const k = el.querySelector("[data-kicker]"); if (k) k.textContent = kicker(e, st);
      // Screen readers hear it at 10 min, 1 min and the start, not every second
      const left = Math.round((e.start - now) / MIN), say = left === 10 ? "10" : left === 1 ? "1" : st === "now" ? "now" : "";
      if (say && el.dataset.said !== say && live) { el.dataset.said = say; const title = el.querySelector("h3,.hf-ev-title"); live.textContent = `${title ? title.textContent : "Event"}: ${say === "now" ? "on now" : `starts in ${say} ${say === "1" ? "minute" : "minutes"}`}`; }
    });
  }

  function mount(root = document) {
    document.documentElement.classList.add("hf-js");
    if (!live) { live = document.createElement("div"); live.className = "vh"; live.setAttribute("aria-live", "polite"); document.body.appendChild(live); }
    root.querySelectorAll(".hf-card, .hf-evcard").forEach(el => { if (el.dataset.bound) return; el.dataset.bound = "1"; bindTilt(el); if (el.classList.contains("hf-card")) bindFlip(el); });
    root.querySelectorAll(".hf-deck").forEach(d => { if (!d.dataset.bound) { d.dataset.bound = "1"; bindDeck(d); } });
    root.querySelectorAll(".hf-spot-host").forEach(h => { if (!h.dataset.bound) { h.dataset.bound = "1"; bindSpot(h); } });
    // Entrance as cards scroll in, staggered 70 ms within each batch of six
    const io = new IntersectionObserver(es => { let i = 0; es.forEach(en => { if (!en.isIntersecting) return; const c = en.target;
      if (!calm()) c.style.setProperty("--delay", ((i++ % 6) * .07).toFixed(2) + "s"); c.classList.add("is-in"); io.unobserve(c); }); }, { threshold: .15 });
    root.querySelectorAll(".hf-card:not(.is-in), .hf-evcard:not(.is-in)").forEach(c => calm() ? c.classList.add("is-in") : io.observe(c));
    if (!mount.ticking) { mount.ticking = setInterval(tick, 1000); tick(); }
    if (!mount.clicks) {
      mount.clicks = true;
      document.addEventListener("click", ev => {
        const t = ev.target.closest("[data-toggle]");
        if (t) {
          const c = t.closest(".hf-card"), kind = t.dataset.toggle, on = t.getAttribute("aria-pressed") !== "true", org = c && c.dataset.org;
          if (t.dataset.busy) return;   // a save still on its way
          const cards = org ? [...document.querySelectorAll(".hf-card")].filter(x => x.dataset.org === org) : c ? [c] : [];
          const set = (on, pop, count) => {
            (cards.length ? cards.flatMap(x => [...x.querySelectorAll(`[data-toggle="${kind}"]`)]) : [t]).forEach(b => {
              b.setAttribute("aria-pressed", String(on)); const n = b.querySelector("[data-n]"); if (n) n.textContent = count != null ? count : +n.textContent + (on ? 1 : -1);
              const ic = b.querySelector(".hf-pop-target"); if (ic) { if (kind === "member") ic.textContent = on ? "✓" : "+"; ic.classList.remove("hf-pop"); if (pop) { void ic.offsetWidth; if (!calm()) ic.classList.add("hf-pop"); } }
              const l = b.querySelector("[data-label]"); if (l) l.textContent = on ? "You're a member" : "I'm a member";
            });
            if (kind === "member") cards.forEach(x => { const vs = x.querySelector("[data-vs]"); if (vs) vs.textContent = count != null ? count : +vs.textContent + (on ? 1 : -1); });
          };
          set(on, true);
          if (H.hooks.toggle && org) {
            const btns = cards.flatMap(x => [...x.querySelectorAll(`[data-toggle="${kind}"]`)]); btns.forEach(b => b.dataset.busy = "1");
            Promise.resolve(H.hooks.toggle(org, kind, on)).then(n => { if (n != null) set(on, false, n); }, () => set(!on, false)).finally(() => btns.forEach(b => delete b.dataset.busy));
          }
          return;
        }
        const cal = ev.target.closest("[data-cal]"); if (cal) { const el = cal.closest(".hf-evcard"); return H.hooks.cal ? H.hooks.cal(el.dataset.ev) : ics(el); }
        const mu = ev.target.closest("[data-muster-btn]");
        if (mu) { const el = mu.closest(".hf-evcard"), note = el.querySelector("[data-note]"); try { navigator.clipboard.writeText(el.dataset.muster).catch(() => {}); } catch (x) {}
          note.hidden = false; clearTimeout(note._t); note._t = setTimeout(() => note.hidden = true, 5000); }
      });
    }
  }

  const H = window.VSHolo = { card, eventCard, rivalry, listRow, mount, stateOf, fmtWhen, inkFor, nameSize, TYPES, ICON, VS_LOGO, hooks: {} };
})();
