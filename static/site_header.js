/* ============================================================
 * site_header.js — unified header for V3 Attendance Console.
 * Single source of truth. Inject this script on any page; it:
 *   • Builds the topbar (brand + nav + health pill + live clock)
 *   • Owns its own CSS (literal colors, no host vars required)
 *   • Sets the active nav link based on location.pathname
 *   • Polls /api/health every 60s to update the pill
 *   • Ticks the clock + computed Shift / Prod dates every second
 *
 * Pages must NOT define their own conflicting #healthPill / #clkTime
 * elements — this script owns those IDs.
 * ============================================================ */
(function() {
  if (window.__siteHeaderInited) return;
  window.__siteHeaderInited = true;

  // Bail out early when this page was opened as a report popup (?report=1):
  // the operator wants a focused view with no top nav. Also remove the
  // <div id="siteHeader"> placeholder so it doesn't reserve space.
  const _sp = new URLSearchParams(location.search);
  if (_sp.get("report") === "1") {
    const drop = () => {
      document.body && document.body.classList.add("report-mode");
      const slot = document.getElementById("siteHeader");
      if (slot) slot.remove();
    };
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", drop);
    } else {
      drop();
    }
    return;
  }

  // ---------- BASE path resolution (works under /attendance/* via nginx) ----------
  const PATH = location.pathname.replace(/\/+$/, "");
  // Strip the trailing /<page> to get the API base. Recognised pages: console,
  // dashboard, gantt, summary, reports, management, logs, m/report, m/summary
  const BASE = (() => {
    const m = PATH.match(/^(\/.*?)(?:\/m)?\/(?:dashboard|console|gantt|summary|reports|management|logs|report|summary)$/);
    return (m && m[1]) || "";
  })();
  const api = (p) => BASE + (p.startsWith("/") ? p : "/" + p);

  // ---------- Date helpers — production cycle 10:00 → next 08:30 ----------
  const pad = (n) => String(n).padStart(2, "0");
  const toISO = (d) => `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;
  function shiftDateForNow() {
    const n = new Date();
    if (n.getHours() < 10) { const y = new Date(n); y.setDate(y.getDate()-1); return toISO(y); }
    return toISO(n);
  }
  function productionDateForNow() {
    const [y,m,d] = shiftDateForNow().split("-").map(Number);
    const t = new Date(y, m-1, d); t.setDate(t.getDate()+1);
    return toISO(t);
  }

  // ---------- Report-popup mode (called from Reports launcher with ?report=1) ----------
  const SP = new URLSearchParams(location.search);
  if (SP.get("report") === "1") {
    document.documentElement.classList.add("report-mode");
    if (document.body) document.body.classList.add("report-mode");
    else document.addEventListener("DOMContentLoaded", () => document.body.classList.add("report-mode"));
  }

  // ---------- Active link detection ----------
  function activeKey() {
    if (PATH.endsWith("/dashboard")) return "dashboard";
    if (PATH.endsWith("/console") || PATH === BASE || PATH === "" || PATH === "/") return "console";
    if (PATH.endsWith("/gantt") || PATH.endsWith("/m/report")) return "gantt";
    if (PATH.endsWith("/summary") || PATH.endsWith("/m/summary")) return "summary";
    if (PATH.endsWith("/reports")) return "reports";
    if (PATH.endsWith("/management")) return "management";
    return "";
  }

  // ---------- Inject CSS (self-contained, literal colors) ----------
  const style = document.createElement("style");
  style.id = "site-header-css";
  style.textContent = `
    .site-topbar {
      position: sticky; top: 0; z-index: 50;
      display: grid;
      grid-template-columns: auto 1fr auto;
      align-items: center;
      padding: 0.7rem 1rem;
      border-bottom: 1px solid #d4e2e8;
      background: rgba(255,255,255,.94);
      backdrop-filter: blur(8px);
      gap: 0.9rem;
      font-family: "Space Grotesk", "Segoe UI", system-ui, sans-serif;
      color: #132026;
    }
    .site-topbar .brand { font-weight: 700; letter-spacing: .03em; color: #0b6f58; font-size: .95rem; }
    .site-topbar .topnav { display: flex; flex-wrap: wrap; gap: .6rem; align-items: center; justify-content: flex-start; }
    .site-topbar .topnav a {
      text-decoration: none; color: #5a6b73;
      font-size: .9rem; font-weight: 500;
      border: 1px solid transparent;
      padding: .35rem .55rem; border-radius: 8px;
      transition: all .2s ease;
    }
    .site-topbar .topnav a:hover { color: #0b6f58; border-color: #d4e2e8; background: #f7fbfc; }
    .site-topbar .topnav a.active { color: #0b6f58; border-color: #b8e4d8; background: #ecfaf4; }
    .site-topbar .topnav a.dash-link { background: #10b981; color: #fff; border-color: #10b981; font-weight: 700; }
    .site-topbar .topnav a.dash-link:hover { background: #059669; border-color: #059669; color: #fff; }
    .site-topbar .pill {
      border-radius: 999px; padding: .35rem .7rem; font-size: .76rem;
      border: 1px solid #d4e2e8; background: #f7fbfc; color: #5a6b73;
      font-family: "IBM Plex Mono", monospace; white-space: nowrap;
    }
    .site-topbar .pill.ok   { color: #0b6f58; border-color: #b8e4d8; background: #ecfaf4; }
    .site-topbar .pill.warn { color: #9b640f; border-color: #f0dbb8; background: #fff8ea; }
    .site-topbar .pill.err  { color: #b42318; border-color: #f0c8c4; background: #fff2f1; }
    .site-topbar .clockbox {
      display: flex; align-items: center; gap: .5rem;
      padding: .3rem .55rem .3rem .65rem;
      border: 1px solid #d4e2e8; background: #f7fbfc; border-radius: 12px;
      font-family: "IBM Plex Mono", monospace; font-size: .78rem; color: #132026; line-height: 1.2;
    }
    .site-topbar .clockbox .now { display: flex; flex-direction: column; align-items: flex-start; gap: .08rem; padding-right: .55rem; border-right: 1px solid #d4e2e8; }
    .site-topbar .clockbox .now .tm { font-size: .95rem; font-weight: 600; color: #0b6f58; }
    .site-topbar .clockbox .now .dt { font-size: .7rem; color: #5a6b73; }
    .site-topbar .clockbox .pair { display: flex; flex-direction: column; gap: .08rem; }
    .site-topbar .clockbox .pair b { color: #125e91; font-weight: 600; }
    .site-topbar .clockbox .pair span { color: #5a6b73; font-size: .7rem; }
    @media (max-width: 900px) {
      .site-topbar { grid-template-columns: 1fr auto; grid-template-areas: "brand clock" "nav nav"; gap: .5rem; }
      .site-topbar > .brand   { grid-area: brand; }
      .site-topbar > .topnav  { grid-area: nav;   justify-self: start; }
      .site-topbar > .clockbox{ grid-area: clock; }
    }
    @media (max-width: 680px) {
      .site-topbar .clockbox { font-size: .72rem; padding: .25rem .4rem; }
      .site-topbar .clockbox .now .tm { font-size: .85rem; }
    }
    /* When mobile-only viewer is active (/m/report, /m/summary) or the page
       was opened as a report popup (?report=1) hide the unified nav so the
       view stays focused. */
    body.mobile .site-topbar,
    body.report-mode .site-topbar { display: none !important; }
  `;
  document.head.appendChild(style);

  // ---------- Build header element ----------
  const cur = activeKey();
  const link = (key, href, label, extraClass = "") => {
    const cls = (cur === key ? "active " : "") + extraClass;
    return `<a href="${href}"${cls.trim() ? ` class="${cls.trim()}"` : ""}>${label}</a>`;
  };
  const header = document.createElement("header");
  header.className = "site-topbar";
  header.innerHTML = `
    <div class="brand">V3 Attendance Console</div>
    <nav class="topnav">
      ${link("dashboard", BASE + "/dashboard", "🌐 Dashboard", "dash-link")}
      ${link("console",   BASE + "/console",   "Console")}
      ${link("gantt",     BASE + "/gantt",     "Gantt")}
      ${link("summary",   BASE + "/summary",   "Summary")}
      ${link("reports",   BASE + "/reports",   "Reports")}
      ${link("management",BASE + "/management","Management")}
      <span id="healthPill" class="pill">checking…</span>
    </nav>
    <div class="clockbox" id="clockBox" title="Live clock and computed shift / production dates">
      <div class="now">
        <span class="tm" id="clkTime">--:--:--</span>
        <span class="dt" id="clkDate">----/--/--</span>
      </div>
      <div class="pair"><span>Shift</span><b id="clkShift">—</b></div>
      <div class="pair"><span>Prod</span><b id="clkProd">—</b></div>
    </div>
  `;

  // ---------- Inject into DOM ----------
  function placeHeader() {
    const slot = document.getElementById("siteHeader");
    if (slot) {
      slot.replaceWith(header);
    } else {
      document.body.insertBefore(header, document.body.firstChild);
    }
    startClock();
    pingHealth();
  }

  // ---------- Live clock + computed Shift/Prod ----------
  function startClock() {
    const $t = header.querySelector("#clkTime");
    const $d = header.querySelector("#clkDate");
    const $s = header.querySelector("#clkShift");
    const $p = header.querySelector("#clkProd");
    function tick() {
      const n = new Date();
      $t.textContent = `${pad(n.getHours())}:${pad(n.getMinutes())}:${pad(n.getSeconds())}`;
      $d.textContent = `${n.getFullYear()}/${pad(n.getMonth()+1)}/${pad(n.getDate())}`;
      $s.textContent = shiftDateForNow();
      $p.textContent = productionDateForNow();
    }
    tick();
    setInterval(tick, 1000);
  }

  // ---------- Health pill ----------
  function pingHealth() {
    const p = header.querySelector("#healthPill");
    fetch(api("/api/health")).then(r => r.json()).then(j => {
      p.classList.remove("ok","warn","err");
      if (j.status === "healthy") { p.textContent = "API healthy"; p.classList.add("ok"); }
      else { p.textContent = "API degraded"; p.classList.add("warn"); }
    }).catch(() => {
      p.classList.remove("ok","warn","err");
      p.textContent = "API offline"; p.classList.add("err");
    });
  }
  setInterval(() => pingHealth(), 60_000);

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", placeHeader);
  } else {
    placeHeader();
  }
})();
