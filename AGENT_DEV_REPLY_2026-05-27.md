# Re: `/api/v1/app-pdf/` endpoint — server team reply

**From:** Pi-server dev.
**To:** desktop agent dev.
**Date:** 2026-05-27.
**Re:** your spec request of 2026-05-27 ("Spec request — `/api/v1/app-pdf/` endpoint").

---

## TL;DR

The spec is well-reasoned and the architectural direction is right in principle, but I can't ship it on this Pi right now — Chromium-headless can render `about:blank` but **hangs on every network fetch** (tried both 127.0.0.1 and localhost, with and without `--single-process`, `--proxy-server=direct://`, `--headless=new`, etc.). All known-good Pi-friendly flag combinations timed out at 30–90s without producing a PDF. The root cause looks like a `rpi-chromium-mods` / Chromium-148 interaction on Raspberry Pi OS, possibly aggravated by ~387 MB free RAM and ~2.4 GB swap pressure. Gotenberg + Docker would add a separate daemon to maintain on the same RAM-tight Pi, so I'd rather not go there as a first move.

**Good news**: there's a much smaller fix that addresses your actual symptom ("narrow content / ~50% blank page"). The real problem isn't container CSS — it's that **your `printToPDF` page dimensions don't match what the server pages are actually designed for**. Match them and the narrow-content issue should disappear without injecting any overrides.

---

## 1. Page-size contract — the part of the spec that's wrong

Your spec assumes the server renders **gantt = JIS B3 portrait, summary = A3 portrait**. The actual `@page` CSS on the server today:

| Page | Actual `@page` rule | Source |
| --- | --- | --- |
| `/pdf/gantt` (renders `gantt.html`) | `@page { size: A4 portrait; margin: 4mm; }` | `static/gantt.html:299` |
| `/pdf/summary` (renders `summary.html`) | `@page { size: B3 landscape; margin: 10mm; }` | `static/summary.html:234` |

`gantt.html` also constrains its main `.page` div to `width: 210mm` (= A4 width) inside `@media print`. `summary.html` resets `.wrap { max-width: none; }` in `@media print` so it fills the paper.

So when v2.4.28 sends `{ width: '14.331in', height: '20.276in' }` (B3 portrait) to `printToPDF` for the gantt, the page renders its 210 mm content centred on a much wider sheet — that's your ~50% blank. Switch the gantt dimensions to A4 portrait (`'210mm' × '297mm'`) and the content should fill the page without needing CSS injection.

Same for summary: send B3 landscape (`'515mm' × '364mm'`) instead of A3 portrait.

**Suggested concrete change in `main.js`:**

```js
// gantt — was: { width: 14.331, height: 20.276 } (B3 portrait, inches)
const ganttPdfOptions = {
  pageSize: { width: 8.27, height: 11.69 },   // A4 portrait, inches
  margins: { top: 0.16, bottom: 0.16, left: 0.16, right: 0.16 }, // ≈4mm
  printBackground: true,
};

// summary — was: A3 portrait
const summaryPdfOptions = {
  pageSize: { width: 20.276, height: 14.331 }, // B3 landscape, inches
  margins: { top: 0.39, bottom: 0.39, left: 0.39, right: 0.39 }, // ≈10mm
  printBackground: true,
};
```

This is the same content the operator sees when they hit "Print" in a real Chrome via `shell.openExternal` — which you correctly noted in §1.2 "already produces correct PDFs". The only difference is that the manual-print path lets Chrome pick up the page's `@page` rule automatically; in `printToPDF` you have to send matching dimensions yourself.

If our `@page` rules ever change (e.g. you actually need B3 portrait for the gantt for production printing reasons), we can update them together — let me know what the operator needs and I'll change `gantt.html` + `summary.html` rather than have the agent compensate.

---

## 2. Why the server-side endpoint isn't viable on this Pi right now

### 2.1 Pi memory budget

```
total 2.0 GiB · used 1.6 GiB · available 387 MiB
swap 6.0 GiB · used 2.4 GiB
```

The existing services (FastAPI attendance app, PostgreSQL, nginx, cloudflared tunnel, a few smaller helpers) already consume most of the RAM. A persistent Chromium would be in the 400–500 MB RSS range, putting us into hard memory pressure. A per-request launch would touch swap on cold start and add 2–5 s of warm-up to every PDF call.

### 2.2 Pi-OS chromium quirks

Chromium 148 ships from `rpi-chromium-mods 20260211` — a Raspberry-Pi-specific patched build. We confirmed:

- `chromium --headless=new --print-to-pdf=out.pdf about:blank` → works in 1.8 s (7.5 KB PDF).
- `chromium --headless=new --print-to-pdf=out.pdf http://127.0.0.1:8002/api/health` → hangs to timeout (30, 60, 90 s — all killed without producing output).

Flag combinations tried (none unblocked the network fetch):

- `--headless` and `--headless=new`
- `--no-sandbox`, `--disable-gpu`, `--disable-dev-shm-usage`, `--disable-software-rasterizer`
- `--single-process` (conflicts with `--proxy-server` in single-process mode)
- `--proxy-server="direct://" --proxy-bypass-list="*"`
- `--virtual-time-budget=10000`, `--run-all-compositor-stages-before-draw`
- 127.0.0.1 vs localhost (no DNS variation)

Meanwhile `curl` to the same URL returns instantly, confirming the FastAPI side is healthy. This is consistent with several reports of Pi-OS Chromium-148 hanging in headless network mode that haven't been resolved upstream yet.

### 2.3 Gotenberg-in-Docker alternative

Would work in principle (different Chromium build, container-managed pool). But it adds a long-running daemon to the same RAM-tight Pi and an extra service to monitor. I don't want to commit to that as a first move when there's a smaller fix (§1) that closes the actual symptom you're chasing.

---

## 3. Answers to your §7 questions

> **Hosting**: which §4 option fits the Pi best?

None right now — see §2 above. Local chromium hangs; gotenberg+docker is heavy. If the §1 page-size fix doesn't fully close the issue and we still need server-side rendering, we'd revisit gotenberg with explicit RAM headroom (e.g. throttle other services or upgrade the Pi).

> **Caching**: PDFs for past dates rarely change. Worth caching?

Moot for now, but yes — if/when we build this, last-N-day PDFs hit via a content-hash key would be a sensible cache.

> **Concurrency**: serialize?

Moot for now. If we ever build it on a Pi, yes — one render at a time, mutex on the rendering process, others queue.

> **Naming**: `/api/v1/app-pdf/` OK?

Fine, no objection. If we ever build it.

> **B3 paper availability**: name vs explicit dimensions?

Explicit `364mm × 515mm` is safer than `B3` — same advice as for your printToPDF call.

> **Auth header propagation**: server-internal call needs `X-API-Key`?

When called from the Pi itself (loopback 127.0.0.1:8002 with no Host header pointing at a GenbaLink vhost), the host-auth wall doesn't fire, so no session/key is needed. From outside the Pi, `/pdf/*` requires a `gbl_session` cookie — but server-side rendering wouldn't go that route.

---

## 4. Suggested next steps

1. **You ship v2.4.29 with the page-size correction from §1** (A4 portrait for gantt, B3 landscape for summary). Confirm content fills the page without the CSS injection workaround. If that closes it, you can also revert the planned `<style>` injection — cleaner.
2. **If that's not enough**, send me a screenshot of the resulting PDF + what you'd expect — there may be additional CSS rules I missed in our `@media print` block that I can adjust on the server side.
3. **If we still need server-side rendering after that**, I'll revisit either (a) chromium with a different package source, or (b) gotenberg in a constrained container. We'll co-ordinate the cutover then.

Either way, the existing `DESKTOP_AGENT_INTEGRATION.md` will be updated to call out the actual `@page` targets so future revisions don't drift again.

---

## 5. Side notes — things you might want to know

- **`X-Agent-Version` is now visible in `/admin/api/agent`** — the agent's last-reported build appears in the admin Agent tab. Useful for confirming a fleet upgrade landed.
- **Real client IP is now logged** — as of this morning, `CF-Connecting-IP` is captured server-side, so each upload's source PC is traceable in `agent_requests.jsonl`. Past entries that show `ip=::1` were before this fix (loopback exit of the Cloudflare tunnel).
- **Doctor's auto-ingest is live** — xlsm files left in `auto_uploads/daily_packs/` are now auto-extracted and saved by `attendance-doctor.timer` every 5 h. Your agent's upload alone (POST `/api/v1/xlsx/upload`) is now sufficient end-to-end; the operator no longer needs to click "Auto-update" in the Console afterwards. Optional faster path: chain `auto-extract-excel` → `save-excel-batch` yourself right after the upload (same two-step doctor does) — covered in `DESKTOP_AGENT_INTEGRATION.md §8.1`.
- **Pack-count audit trail** — every change to `daily_packs` is now logged in a `daily_packs_history` table (Postgres trigger). If you ever want a "verify upload landed" view in the agent UI, `GET /api/daily-packs/{date}/history` returns the change log.

Happy to discuss any of this further.

— Pi-server dev (auto-generated reply via Claude Code session, 2026-05-27)
