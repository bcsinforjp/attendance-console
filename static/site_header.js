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
    // Tabs collapsed to 4: status / reports / setup / intake.
    // Gantt + Summary pages live under Reports — they highlight the Reports tab.
    if (PATH.endsWith("/dashboard")) return "status";
    if (PATH.endsWith("/console") || PATH === BASE || PATH === "" || PATH === "/") return "intake";
    if (PATH.endsWith("/gantt") || PATH.endsWith("/m/report") || PATH.endsWith("/m/gantt")) return "reports";
    if (PATH.endsWith("/summary") || PATH.endsWith("/m/summary")) return "reports";
    if (PATH.endsWith("/reports")) return "reports";
    if (PATH.endsWith("/management")) return "setup";
    return "";
  }

  // ---------- Inject CSS (self-contained, literal colors) ----------
  const style = document.createElement("style");
  style.id = "site-header-css";
  style.textContent = `
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Noto+Sans+JP:wght@400;500;700&display=swap');
    :root{
      --gf-accent:#0d9488; --gf-accent-strong:#0b6f58; --gf-accent-soft:#ecfaf4; --gf-accent-line:#b8e4d8;
      --gf-indigo:#6366f1;
      --gf-bg:#f6f8fa; --gf-surface:#ffffff; --gf-surface-2:#f1f4f7;
      --gf-line:#e3e8ee; --gf-line-soft:#eef2f5;
      --gf-ink:#1f2933; --gf-ink-2:#5a6b73; --gf-ink-3:#8a99a3;
      --gf-ok:#0b6f58; --gf-ok-bg:#ecfaf4; --gf-ok-line:#b8e4d8;
      --gf-warn:#9b640f; --gf-warn-bg:#fff8ea; --gf-warn-line:#f0dbb8;
      --gf-err:#b42318; --gf-err-bg:#fff2f1; --gf-err-line:#f0c8c4;
      --gf-radius:10px; --gf-radius-lg:16px;
      --gf-font:"Inter","Noto Sans JP","Segoe UI",system-ui,sans-serif;
      --gf-mono:"JetBrains Mono","IBM Plex Mono",ui-monospace,monospace;
      --gf-shadow:0 1px 2px rgba(16,32,40,.04),0 8px 24px rgba(16,32,40,.06);
    }
    .site-topbar {
      position: sticky; top: 0; z-index: 50;
      display: grid;
      grid-template-columns: auto 1fr auto;
      align-items: center;
      padding: 0.78rem 1.15rem;
      border-bottom: 1px solid #e3e8ee;
      background: rgba(255,255,255,.92);
      backdrop-filter: saturate(140%) blur(10px);
      -webkit-backdrop-filter: saturate(140%) blur(10px);
      box-shadow: 0 1px 0 rgba(16,32,40,.02), 0 6px 22px rgba(16,32,40,.05);
      gap: 0.9rem;
      font-family: "Inter","Noto Sans JP","Segoe UI",system-ui,sans-serif;
      color: #1f2933;
    }
    .site-topbar .brand { display:flex; align-items:center; gap:.5rem; font-weight: 700; letter-spacing: .015em; color: #0b6f58; font-size: 1rem; font-family:"Inter","Noto Sans JP",system-ui,sans-serif; }
    .site-topbar .brand::before { content:""; width:7px; height:18px; border-radius:3px; background:linear-gradient(160deg,#0d9488,#6366f1); flex:0 0 auto; }
    .site-topbar .topnav { display: flex; flex-wrap: wrap; gap: .6rem; align-items: center; justify-content: flex-start; }
    .site-topbar .topnav a {
      text-decoration: none; color: #5a6b73;
      font-size: .9rem; font-weight: 500;
      border: 1px solid transparent;
      padding: .35rem .55rem; border-radius: 8px;
      transition: all .2s ease;
    }
    .site-topbar .topnav a:hover { color: #0b6f58; border-color: #e3e8ee; background: #f5f9fa; }
    .site-topbar .topnav a.active { color: #0b6f58; border-color: #b8e4d8; background: #ecfaf4; }
    .site-topbar .topnav a.dash-link { background: linear-gradient(135deg,#0d9488,#0b6f58); color: #fff; border-color: transparent; font-weight: 700; box-shadow: 0 2px 8px rgba(13,148,136,.28); }
    .site-topbar .topnav a.dash-link:hover { background: linear-gradient(135deg,#0b6f58,#0a5c49); border-color: transparent; color: #fff; }
    .site-topbar .pill {
      border-radius: 999px; padding: .35rem .7rem; font-size: .76rem;
      border: 1px solid #e3e8ee; background: #f5f9fa; color: #5a6b73;
      font-family: "IBM Plex Mono", monospace; white-space: nowrap;
    }
    .site-topbar .pill.ok   { color: #0b6f58; border-color: #b8e4d8; background: #ecfaf4; }
    .site-topbar .pill.warn { color: #9b640f; border-color: #f0dbb8; background: #fff8ea; }
    .site-topbar .pill.err  { color: #b42318; border-color: #f0c8c4; background: #fff2f1; }
    .site-topbar .clockbox {
      display: flex; align-items: center; gap: .5rem;
      padding: .3rem .55rem .3rem .65rem;
      border: 1px solid #e3e8ee; background: #f5f9fa; border-radius: 12px;
      font-family: "IBM Plex Mono", monospace; font-size: .78rem; color: #1f2933; line-height: 1.2;
    }
    .site-topbar .clockbox .now { display: flex; flex-direction: column; align-items: flex-start; gap: .08rem; padding-right: .55rem; border-right: 1px solid #e3e8ee; }
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

    /* ===== Site-wide announcement banner — driven by /api/announcement,
       edited from /admin#/announcement. Sits directly below the topbar
       on every full page. Hidden on mobile viewers / report popups. ===== */
    .ann-banner {
      display: flex; align-items: center; gap: 0.7rem; flex-wrap: wrap;
      padding: 0.55rem 1rem;
      border-bottom: 1px solid transparent;
      font-size: 0.82rem; line-height: 1.35;
      font-family: "Inter","Noto Sans JP","Segoe UI",system-ui,sans-serif;
    }
    .ann-banner.amber  { background: linear-gradient(90deg,#fff7e6 0%,#fff2d1 100%); border-bottom-color:#f0c67a; color:#6a4a12; }
    .ann-banner.red    { background: linear-gradient(90deg,#fdecec 0%,#fad4d1 100%); border-bottom-color:#e8a39c; color:#7a1c12; }
    .ann-banner.blue   { background: linear-gradient(90deg,#e8f1f8 0%,#d3e2ee 100%); border-bottom-color:#9cc1da; color:#0e3f5f; }
    .ann-banner.green  { background: linear-gradient(90deg,#e6f5f0 0%,#c8ead9 100%); border-bottom-color:#90c9b6; color:#0a5c49; }
    .ann-banner.gray   { background: linear-gradient(90deg,#eef1f3 0%,#dfe6ea 100%); border-bottom-color:#c2ccd2; color:#39474f; }
    .ann-banner.purple { background: linear-gradient(90deg,#efe9fc 0%,#ddd1f7 100%); border-bottom-color:#bba9f1; color:#3d2a76; }
    .ann-banner__badge {
      flex: 0 0 auto; padding: 0.18rem 0.5rem;
      background: rgba(0,0,0,0.55); color: #fff;
      border-radius: 4px; font-family: "IBM Plex Mono", monospace;
      font-size: 0.7rem; font-weight: 700; letter-spacing: 0.08em;
    }
    .ann-banner__text { flex: 1 1 auto; }
    .ann-banner__text b { filter: brightness(0.7); }
    .ann-banner__ja {
      font-family: "Noto Sans JP", "Hiragino Sans", sans-serif;
      margin-left: 0.25rem;
    }
    .ann-banner__close {
      flex: 0 0 auto; cursor: pointer; background: transparent; border: 0;
      color: inherit; opacity: 0.65; font-size: 1rem; padding: 0 0.3rem; line-height: 1;
    }
    .ann-banner__close:hover { opacity: 1; }
    .ann-banner.hidden { display: none; }
    .ann-restore {
      display: none; position: fixed; right: 14px; top: 64px; z-index: 49;
      font-size: 0.72rem; padding: 0.25rem 0.6rem;
      border: 1px solid #d5e2ea; border-radius: 999px;
      background: #f5fbfd; color: #5f7078; cursor: pointer;
      font-family: "Inter","Noto Sans JP",system-ui,sans-serif;
    }
    .ann-restore:hover { color: #12618f; border-color: #12618f; }
    @media (max-width: 680px) { .ann-banner { font-size: 0.75rem; padding: 0.5rem 0.75rem; } }
    body.mobile .ann-banner, body.report-mode .ann-banner,
    body.mobile .ann-restore, body.report-mode .ann-restore { display: none !important; }
    @media print { .ann-banner, .ann-restore { display: none !important; } }
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
    <div class="brand">現場 FMS</div>
    <nav class="topnav">
      ${link("status",  BASE + "/dashboard",  "Status",  "dash-link")}
      ${link("reports", BASE + "/reports",    "Reports")}
      ${link("setup",   BASE + "/management", "Setup")}
      ${link("intake",  BASE + "/console",    "Intake")}
      <span id="healthPill" class="pill">checking…</span>
      <span id="agentPill" class="pill" style="display:none;"></span>
      <span id="userPill" class="pill" style="display:none;"></span>
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

  // ---------- Announcement banner (driven by /api/announcement) ----------
  const annBanner = document.createElement("div");
  annBanner.id = "annBanner";
  annBanner.className = "ann-banner amber hidden";
  annBanner.setAttribute("role", "status");
  annBanner.setAttribute("aria-live", "polite");
  annBanner.innerHTML = `
    <span id="annBadge" class="ann-banner__badge">INFO</span>
    <span class="ann-banner__text">
      <span id="annTextEn"></span>
      <span id="annTextJa" class="ann-banner__ja"></span>
    </span>
    <button id="annClose" class="ann-banner__close" type="button" aria-label="Dismiss" title="Dismiss">✕</button>
  `;
  const annRestore = document.createElement("button");
  annRestore.id = "annRestore";
  annRestore.className = "ann-restore";
  annRestore.type = "button";
  annRestore.title = "Show announcement";
  annRestore.textContent = "show notice";

  // ---------- Floating Action Button (always visible, bottom-right) ----------
  const fab = document.createElement("button");
  fab.id = "feedbackFab";
  fab.type = "button";
  fab.title = "Send feedback / フィードバック送信";
  fab.setAttribute("aria-label", "Send feedback");
  fab.innerHTML = `<span class="fab-icon">💬</span><span class="fab-label">Feedback</span>`;

  // ---------- Feedback modal — polished, professional layout ----------
  const modal = document.createElement("div");
  modal.id = "demoFeedbackModal";
  // Defensive inline style so the modal is hidden even if bannerCss load is
  // delayed or overridden by host page CSS. The .show class will flip it via
  // !important so this attribute does not block opening it.
  modal.setAttribute("style", "display:none;");
  modal.innerHTML = `
    <div class="fb-card" role="dialog" aria-labelledby="fbTitle" aria-modal="true">
      <header class="fb-head">
        <div>
          <h3 id="fbTitle">💬 Send feedback</h3>
          <p class="fb-sub">ご意見・ご要望</p>
        </div>
        <button type="button" class="fb-x" aria-label="Close">×</button>
      </header>
      <p class="fb-help">
        Tell us anything — bugs, slowness, missing features, or just a thank-you.<br>
        <small>不具合、動作の遅さ、欲しい機能、感想など、なんでも歓迎します。</small>
      </p>
      <label class="fb-label">Your name <span class="fb-opt">(optional · 任意)</span></label>
      <input type="text" id="fbName" maxlength="60" placeholder="anonymous">
      <label class="fb-label">Message <span class="fb-req">*</span></label>
      <textarea id="fbMessage" rows="6" maxlength="4000"
        placeholder="What happened? What did you expect? / 何が起きましたか？どうあるべきでしたか？"></textarea>
      <div class="fb-meta">
        <span id="fbCharCount" class="fb-charcount">0 / 4000</span>
        <span class="fb-page-info">📍 <code id="fbPageInfo">—</code></span>
      </div>
      <div class="fb-actions">
        <span id="fbStatus" class="fb-status"></span>
        <button type="button" class="fb-cancel">Cancel</button>
        <button type="button" class="fb-send" disabled>📨 Send</button>
      </div>
    </div>
  `;

  // Inline styles for both pieces (kept here so they live with the script).
  const bannerCss = document.createElement("style");
  bannerCss.textContent = `
    /* ---- Floating Action Button (FAB) for feedback ---- */
    #feedbackFab {
      position: fixed; right: 20px; bottom: 20px; z-index: 9000;
      display: inline-flex; align-items: center; gap: .4rem;
      padding: .6rem 1rem .6rem .9rem;
      background: linear-gradient(135deg, #0d8f71 0%, #0b6f58 100%);
      color: #fff;
      border: 0; border-radius: 999px;
      font-family: "Inter","Noto Sans JP",system-ui,sans-serif;
      font-weight: 700; font-size: .85rem;
      cursor: pointer;
      box-shadow: 0 6px 20px rgba(11, 111, 88, .35), 0 2px 6px rgba(0,0,0,.12);
      transition: transform .18s ease, box-shadow .18s ease;
    }
    #feedbackFab:hover  { transform: translateY(-2px); box-shadow: 0 10px 26px rgba(11, 111, 88, .42), 0 3px 8px rgba(0,0,0,.18); }
    #feedbackFab:active { transform: translateY(0); }
    #feedbackFab .fab-icon { font-size: 1.05rem; line-height: 1; }
    #feedbackFab .fab-label { line-height: 1; }
    @media (max-width: 540px) {
      #feedbackFab { right: 14px; bottom: 14px; padding: .55rem .55rem; }
      #feedbackFab .fab-label { display: none; }
    }
    body.mobile #feedbackFab, body.report-mode #feedbackFab { display: none !important; }
    @media print { #feedbackFab { display: none !important; } }

    #demoFeedbackModal {
      display: none;
      position: fixed; inset: 0; z-index: 10000;
      background: rgba(11, 35, 46, .58);
      backdrop-filter: blur(2px);
      align-items: center; justify-content: center;
      padding: 1rem;
      animation: fbFade .18s ease;
    }
    @keyframes fbFade { from { opacity: 0; } to { opacity: 1; } }
    #demoFeedbackModal.show { display: flex !important; }
    #demoFeedbackModal .fb-card {
      background: #fff; color: #1f2933;
      border-radius: 14px; padding: 1.2rem 1.4rem 1rem;
      max-width: 540px; width: 100%;
      box-shadow: 0 18px 48px rgba(0,0,0,.32), 0 4px 12px rgba(0,0,0,.18);
      font-family: "Inter","Noto Sans JP",system-ui,sans-serif;
      animation: fbSlide .22s ease;
    }
    @keyframes fbSlide { from { transform: translateY(8px) scale(.985); opacity: .85; } to { transform: none; opacity: 1; } }
    #demoFeedbackModal .fb-head {
      display: flex; align-items: flex-start; gap: .5rem;
      margin: -.2rem 0 .4rem; padding-bottom: .5rem;
      border-bottom: 1px solid #eef3f5;
    }
    #demoFeedbackModal .fb-head > div { flex: 1; }
    #demoFeedbackModal h3 {
      margin: 0; font-size: 1.1rem; font-weight: 700; color: #1f2933;
      letter-spacing: -.01em;
    }
    #demoFeedbackModal .fb-sub { margin: .1rem 0 0; font-size: .78rem; color: #5a6b73; font-weight: 500; }
    #demoFeedbackModal .fb-x {
      flex: 0 0 auto; width: 32px; height: 32px;
      border: 0; border-radius: 8px; background: #f0f5f7;
      color: #5a6b73; font-size: 1.4rem; line-height: 1;
      cursor: pointer; padding: 0;
    }
    #demoFeedbackModal .fb-x:hover { background: #e2eaee; color: #1f2933; }
    #demoFeedbackModal .fb-help { font-size: .82rem; color: #5a6b73; margin: 0 0 .8rem; line-height: 1.45; }
    #demoFeedbackModal .fb-help small { display: block; margin-top: .15rem; opacity: .85; }
    #demoFeedbackModal .fb-label {
      display: block; font-size: .72rem; font-weight: 700;
      color: #5a6b73; text-transform: uppercase; letter-spacing: .06em;
      margin: .55rem 0 .25rem;
    }
    #demoFeedbackModal .fb-opt { color: #98a8b1; font-weight: 500; text-transform: none; letter-spacing: 0; }
    #demoFeedbackModal .fb-req { color: #b42318; font-weight: 800; }
    #demoFeedbackModal input, #demoFeedbackModal textarea {
      width: 100%;
      padding: .55rem .7rem;
      border: 1px solid #e3e8ee; border-radius: 8px;
      font: inherit; color: #1f2933; background: #f9fbfc;
      box-sizing: border-box;
      transition: border-color .15s, background .15s, box-shadow .15s;
    }
    #demoFeedbackModal input:focus, #demoFeedbackModal textarea:focus {
      outline: none; border-color: #0d8f71; background: #fff;
      box-shadow: 0 0 0 3px rgba(13, 143, 113, .14);
    }
    #demoFeedbackModal textarea { resize: vertical; min-height: 110px; line-height: 1.5; }
    #demoFeedbackModal .fb-meta {
      display: flex; justify-content: space-between; align-items: center;
      margin: .3rem 0 .2rem; font-size: .72rem; color: #98a8b1;
    }
    #demoFeedbackModal .fb-charcount.warn { color: #9b640f; font-weight: 700; }
    #demoFeedbackModal .fb-charcount.over { color: #b42318; font-weight: 700; }
    #demoFeedbackModal .fb-page-info code {
      background: #f0f5f7; padding: 1px 6px; border-radius: 4px;
      font-family: "IBM Plex Mono", monospace; font-size: .68rem; color: #5a6b73;
    }
    #demoFeedbackModal .fb-actions { display: flex; align-items: center; gap: .5rem; margin-top: 1rem; }
    #demoFeedbackModal .fb-status { flex: 1; font-size: .8rem; color: #5a6b73; }
    #demoFeedbackModal .fb-status.ok  { color: #0b6f58; font-weight: 700; }
    #demoFeedbackModal .fb-status.err { color: #b42318; font-weight: 700; }
    #demoFeedbackModal button {
      padding: .5rem 1rem; border-radius: 8px; font-weight: 600;
      font-size: .85rem; cursor: pointer;
      border: 1px solid #e3e8ee; background: #fff; color: #1f2933;
      transition: all .15s;
    }
    #demoFeedbackModal .fb-cancel:hover { background: #f0f5f7; }
    #demoFeedbackModal .fb-send {
      background: linear-gradient(135deg, #0d8f71 0%, #0b6f58 100%);
      color: #fff; border-color: #0b6f58; padding: .55rem 1.2rem;
    }
    #demoFeedbackModal .fb-send:hover:not(:disabled) {
      transform: translateY(-1px);
      box-shadow: 0 4px 12px rgba(13, 143, 113, .35);
    }
    #demoFeedbackModal .fb-send:disabled { opacity: .45; cursor: not-allowed; }
  `;

  // ---------- Inject into DOM ----------
  function placeHeader() {
    const slot = document.getElementById("siteHeader");
    if (slot) {
      slot.replaceWith(header);
    } else {
      document.body.insertBefore(header, document.body.firstChild);
    }
    // Announcement banner sits directly below the topbar.
    header.insertAdjacentElement("afterend", annBanner);
    document.body.appendChild(annRestore);
    document.head.appendChild(bannerCss);
    document.body.appendChild(fab);
    document.body.appendChild(modal);
    wireFeedbackButtons();
    wireAnnouncement();
    startClock();
    pingHealth();
  }

  // ---------- Announcement banner ----------
  function wireAnnouncement() {
    const COLORS = ["amber","red","blue","green","gray","purple"];
    const dismissedKey = (id) => "annDismissed:" + id;
    const $a = (id) => document.getElementById(id);

    async function load() {
      try {
        const r = await fetch(api("/api/announcement"), { cache: "no-store" });
        const a = await r.json();
        if (!a || a.enabled === false || (!a.text_en && !a.text_ja)) {
          annBanner.classList.add("hidden");
          annRestore.style.display = "none";
          return;
        }
        const id = a.updated_at || (a.badge + "|" + a.text_en);
        const dismissed = a.dismissible !== false && localStorage.getItem(dismissedKey(id)) === "1";

        annBanner.classList.remove("hidden", ...COLORS);
        annBanner.classList.add(COLORS.includes(a.color) ? a.color : "amber");
        $a("annBadge").textContent = a.badge || "INFO";
        $a("annTextEn").textContent = a.text_en || "";
        $a("annTextJa").textContent = a.text_ja || "";
        $a("annClose").style.display = (a.dismissible !== false) ? "" : "none";
        annBanner.dataset.annId = id;

        if (dismissed) {
          annBanner.classList.add("hidden");
          annRestore.style.display = "inline-block";
        } else {
          annRestore.style.display = "none";
        }
      } catch (_e) { /* network error — leave banner hidden */ }
    }

    annBanner.addEventListener("click", (ev) => {
      if (ev.target && ev.target.id === "annClose") {
        const id = annBanner.dataset.annId;
        if (id) localStorage.setItem(dismissedKey(id), "1");
        annBanner.classList.add("hidden");
        annRestore.style.display = "inline-block";
      }
    });
    annRestore.addEventListener("click", () => {
      const id = annBanner.dataset.annId;
      if (id) localStorage.removeItem(dismissedKey(id));
      annBanner.classList.remove("hidden");
      annRestore.style.display = "none";
    });

    load();
    setInterval(load, 5 * 60 * 1000);
  }

  // ---------- Feedback modal ----------
  function wireFeedbackButtons() {
    const cancel = modal.querySelector(".fb-cancel");
    const xBtn   = modal.querySelector(".fb-x");
    const send   = modal.querySelector(".fb-send");
    const txt    = modal.querySelector("#fbMessage");
    const name   = modal.querySelector("#fbName");
    const status = modal.querySelector("#fbStatus");
    const cnt    = modal.querySelector("#fbCharCount");
    const pinfo  = modal.querySelector("#fbPageInfo");
    const showStatus = (text, kind) => { status.textContent = text || ""; status.className = "fb-status" + (kind ? " " + kind : ""); };
    const openModal = () => {
      pinfo.textContent = location.pathname + (location.search || "");
      modal.classList.add("show");
      setTimeout(() => txt.focus(), 50);
    };
    const closeModal = () => { modal.classList.remove("show"); showStatus(""); };

    fab.addEventListener("click", openModal);
    cancel.addEventListener("click", closeModal);
    xBtn.addEventListener("click", closeModal);
    modal.addEventListener("click", e => { if (e.target === modal) closeModal(); });

    // Live char counter + send-button enable/disable
    function updateCounter() {
      const n = txt.value.length;
      cnt.textContent = `${n.toLocaleString()} / 4000`;
      cnt.classList.toggle("warn", n >= 3000 && n < 3900);
      cnt.classList.toggle("over", n >= 3900);
      send.disabled = !txt.value.trim();
    }
    txt.addEventListener("input", updateCounter);
    updateCounter();

    send.addEventListener("click", async () => {
      const message = txt.value.trim();
      if (!message) return;
      send.disabled = true; showStatus("sending…");
      try {
        const r = await fetch(api("/api/feedback"), {
          method: "POST", headers: {"Content-Type":"application/json"},
          body: JSON.stringify({ message, name: name.value.trim(), page: location.pathname + location.search }),
        });
        const j = await r.json().catch(() => ({}));
        if (!r.ok) { showStatus(j.detail || ("HTTP " + r.status), "err"); send.disabled = false; return; }
        showStatus("✅ Thanks! Your feedback was saved. / 送信ありがとうございます。", "ok");
        txt.value = ""; name.value = ""; updateCounter();
        setTimeout(closeModal, 1500);
      } catch (e) {
        showStatus("Send error: " + e.message, "err"); send.disabled = false;
      }
    });

    document.addEventListener("keydown", e => {
      if (e.key === "Escape" && modal.classList.contains("show")) closeModal();
      // Ctrl/⌘ + Enter from inside the textarea sends
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && document.activeElement === txt) {
        if (!send.disabled) send.click();
      }
    });
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
    const ap = header.querySelector("#agentPill");
    fetch(api("/api/health")).then(r => r.json()).then(j => {
      p.classList.remove("ok","warn","err");
      if (j.status === "healthy") { p.textContent = "API healthy"; p.classList.add("ok"); }
      else { p.textContent = "API degraded"; p.classList.add("warn"); }
      if (ap && j.agent) {
        ap.style.display = "";
        ap.classList.remove("ok","warn","err");
        if (j.agent.deactivated || j.agent.paused) { ap.textContent = "agent: deactivated (idle)"; ap.classList.add("err"); }
        else if (j.agent.online) { ap.textContent = "agent ● online"; ap.classList.add("ok"); }
        else                     { ap.textContent = "agent offline"; ap.classList.add("warn"); }
      } else if (ap) {
        ap.style.display = "none";
      }
    }).catch(() => {
      p.classList.remove("ok","warn","err");
      p.textContent = "API offline"; p.classList.add("err");
    });
  }
  setInterval(() => pingHealth(), 60_000);

  // ---------- GenbaLink user pill (only shows when logged in via genbafms.com) ----------
  // The /api/auth/whoami endpoint returns {authenticated:false} when accessed
  // via the unauthenticated /attendance/ vhost — in that case we hide the pill.
  function refreshUserPill() {
    const p = header.querySelector("#userPill");
    if (!p) return;
    fetch("/api/auth/whoami").then(r => r.ok ? r.json() : null).then(j => {
      if (!j || !j.authenticated) { p.style.display = "none"; return; }
      p.style.display = "";
      p.textContent = `👤 ${j.username}${j.is_admin ? " ★" : ""}  ↪`;
      p.title = "Click to log out";
      p.style.cursor = "pointer";
      p.onclick = () => {
        fetch("/api/auth/logout", { method: "POST" }).finally(() => location.href = "/login");
      };
    }).catch(() => { p.style.display = "none"; });
  }
  refreshUserPill();

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", placeHeader);
  } else {
    placeHeader();
  }
})();
