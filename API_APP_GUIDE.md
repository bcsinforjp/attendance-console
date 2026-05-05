# API_APP_GUIDE.md
**Desktop App (Electron) + CMD recipes for the Attendance / Daily Packs server**

This guide covers two things side-by-side:

1. How to talk to the server from a Windows/macOS/Linux desktop app (Electron) using the API keys.
2. The exact CMD / PowerShell / curl commands so you can also drive it without an app.

The same web UI you use today (`/attendance/console`) is being designed to load inside an Electron window unchanged — the only difference is that the desktop app gets to do **extra things the browser cannot**: watch a local Windows folder, drop PDFs into the right server folder automatically, and run shell commands when you click **Auto-update**.

---

## 1. Server overview (split watch-folders)

The server now keeps **two independent watched folders**:

| Section      | Path on the Pi                                          | Endpoint                                                      |
|--------------|---------------------------------------------------------|---------------------------------------------------------------|
| Attendance   | `/var/www/attendance_app/auto_uploads/attendance`       | `POST /api/attendance/auto-upload?save=true`                  |
| Daily Packs  | `/var/www/attendance_app/auto_uploads/daily_packs`      | `POST /api/daily-packs/auto-extract`                          |

Both paths live in `auto_upload_config.json`. The console UI's **Auto-update** button on each tab now reads only from its own folder, so attendance PDFs and pack PDFs no longer collide.

Switch a folder programmatically:

```
POST /api/auto-upload/config
Content-Type: application/json
X-API-Key: <key>

{ "kind": "attendance",  "path": "/mnt/share/AttendancePDF" }
{ "kind": "daily_packs", "path": "/mnt/share/PacksPDF" }
```

Inspect both at once: `GET /api/auto-upload/config/all`.

---

## 2. API keys

`api_keys.json` ships with three labels:

| Label  | Purpose                          | Where to use                                  |
|--------|----------------------------------|-----------------------------------------------|
| `TEST` | Local development & curl tests   | Your laptop, CMD scripts                      |
| `APP`  | Electron desktop client          | Bundled inside the desktop app                |
| `WEB`  | Browser-side console             | Already wired into `console.html`             |

Send the key as **`X-API-Key: <secret>`** on every `/api/v1/...` call. Endpoints under `/api/v1/` are key-protected; the legacy `/api/...` endpoints used by the web UI are not.

> **Never ship `api_keys.json` itself.** In Electron, read the key from an OS-level env var (`ATTENDANCE_API_KEY`) or from the Electron `safeStorage` API at first run.

---

## 3. CMD / PowerShell / curl recipes

### Ping (sanity check)
```cmd
curl -s -H "X-API-Key: YOUR_KEY" https://rnd.asiakawaii.com/attendance/api/v1/ping
```

### Push one PDF up to the server (attendance folder)
```cmd
curl -s -X POST ^
  -H "X-API-Key: YOUR_KEY" ^
  -F "file=@C:\Company_Data\03_就業日報PDF\就業日報2026.01.05.pdf;type=application/pdf" ^
  https://rnd.asiakawaii.com/attendance/api/v1/pdf/upload
```

### Two-flow Auto-update (PDF + Excel) — recommended

The console has **two** Auto-update buttons: one for the attendance PDFs, one for the daily-packs Excel (`btnXlsxAuRun`). The desktop / CMD client must mirror that split — each file type goes to its own upload endpoint, and each flow triggers its own auto-update.

**Flow [A] — Attendance PDF:** drops the PDF into the attendance watched folder, then asks the server to extract it.

```cmd
:: A1. Upload the latest attendance PDF
curl -s -X POST ^
  -H "X-API-Key: YOUR_KEY" ^
  -F "file=@C:\Company_Data\03_就業日報PDF\就業日報2026.04.30.pdf;type=application/pdf" ^
  https://rnd.asiakawaii.com/attendance/api/v1/pdf/upload

:: A2. Trigger attendance auto-update (preview + save to DB)
curl -s -X POST -H "X-API-Key: YOUR_KEY" ^
  "https://rnd.asiakawaii.com/attendance/api/v1/pdf/auto-upload?save=true"
```

**Flow [B] — Daily-packs Excel:** drops the .xlsx into the daily-packs watched folder, then asks the server to parse the latest .xlsx and return preview + start-time + prediction (same response the **Auto-update →** button on the Daily Packs Excel tab gets).

```cmd
:: B1. Upload the latest daily-packs Excel
curl -s -X POST ^
  -H "X-API-Key: YOUR_KEY" ^
  -F "file=@C:\Company_Data\07_FullCast\２６.０４.３０.xlsx" ^
  https://rnd.asiakawaii.com/attendance/api/v1/xlsx/upload

:: B2. Trigger daily-packs Excel auto-extract (no save flag — preview only;
::     the console-side workflow saves via /api/daily-packs/save-excel-batch
::     after the operator confirms in the UI)
curl -s -X POST -H "X-API-Key: YOUR_KEY" ^
  https://rnd.asiakawaii.com/attendance/api/daily-packs/auto-extract-excel
```

The bundled `upload_latest.bat` ships both flows as separate subroutines (`:upload_pdf` and `:upload_xlsx`) and accepts a CLI mode:

```cmd
upload_latest.bat              :: both flows (default)
upload_latest.bat pdf          :: only flow [A]
upload_latest.bat xlsx         :: only flow [B]
```

It also has separate watch folders so the two file types never collide:

```
.\watch\pdf\    ← attendance PDFs
.\watch\xlsx\   ← daily-packs Excel
```

### Push the whole folder (PowerShell)
```powershell
$key = $env:ATTENDANCE_API_KEY
Get-ChildItem 'C:\Company_Data\03_就業日報PDF\*.pdf' | ForEach-Object {
  curl.exe -s -X POST -H "X-API-Key: $key" `
    -F "file=@$($_.FullName);type=application/pdf" `
    https://rnd.asiakawaii.com/attendance/api/v1/pdf/upload
}
```

### Trigger Auto-update remotely (no UI click needed)
```cmd
:: Attendance — preview only
curl -s -X POST -H "X-API-Key: YOUR_KEY" ^
  https://rnd.asiakawaii.com/attendance/api/v1/pdf/auto-upload

:: Attendance — preview + save to DB
curl -s -X POST -H "X-API-Key: YOUR_KEY" ^
  "https://rnd.asiakawaii.com/attendance/api/v1/pdf/auto-upload?save=true"
```

### List & retrieve files already on the server
```cmd
:: PDFs already on the server (attendance watched folder)
curl -s -H "X-API-Key: YOUR_KEY" https://rnd.asiakawaii.com/attendance/api/v1/pdf/list
curl -s -H "X-API-Key: YOUR_KEY" -O https://rnd.asiakawaii.com/attendance/api/v1/pdf/retrieve/就業日報2026.01.05.pdf

:: Excel files already on the server (daily-packs watched folder) — v3.4
curl -s -H "X-API-Key: YOUR_KEY" https://rnd.asiakawaii.com/attendance/api/v1/xlsx/list
```

`/api/v1/xlsx/list` response shape — note `extracted_date` is the date parsed
out of the filename so the desktop client can match a target report_date to a
specific file before triggering `auto-extract-excel`:

```json
{
  "path": "/var/www/attendance_app/auto_uploads/daily_packs",
  "exists": true,
  "count": 2,
  "files": [
    { "filename": "２６.０４.３０.xlsx", "size": 84210,
      "modified": "2026-04-30T18:42:01", "extracted_date": "2026-04-30" },
    { "filename": "２６.０４.２３.xlsx", "size": 83910,
      "modified": "2026-04-23T18:55:11", "extracted_date": "2026-04-23" }
  ]
}
```

### Back-fill a specific date with files already on the server (v3.4)

The auto-update triggers now accept an optional `?date=YYYY-MM-DD` query
parameter. When omitted, both endpoints fall back to "pick the latest file"
(the original behavior, fully backward-compatible — no existing caller has to
change). When supplied, the server picks the file whose filename encodes that
date.

If the requested date has no matching file on the server, the response is a
**structured 404** carrying `error="file_not_available"`, the missing date,
the kind, and the watched folder so the client can show "PDF / Excel for
2026-04-23 is not on the server — please upload it first":

```json
{
  "detail": {
    "error": "file_not_available",
    "kind": "attendance_pdf",
    "requested_date": "2026-04-23",
    "watched_folder": "/var/www/attendance_app/auto_uploads/attendance",
    "message": "No attendance PDF for 2026-04-23 in /var/www/attendance_app/auto_uploads/attendance. Upload the PDF first via POST /api/v1/pdf/upload."
  }
}
```

```cmd
:: Back-fill attendance for 2026-04-23 from a PDF already on the server
curl -s -X POST -H "X-API-Key: YOUR_KEY" ^
  "https://rnd.asiakawaii.com/attendance/api/v1/pdf/auto-upload?save=true&date=2026-04-23"

:: Re-extract daily-packs for 2026-04-23 from an Excel already on the server
curl -s -X POST ^
  "https://rnd.asiakawaii.com/attendance/api/daily-packs/auto-extract-excel?date=2026-04-23"
```

---

## 4. Building the Electron desktop app

### 4.1 Project skeleton
```
attendance-desktop/
  package.json
  main.js          ← Electron main process (Node)
  preload.js       ← bridge between main and renderer
  renderer/
    index.html     ← can simply <iframe src="https://rnd.asiakawaii.com/attendance/console"></iframe>
                     OR a custom UI that calls the API directly
  watch.js         ← optional folder-watcher
```

### 4.2 `package.json`
```json
{
  "name": "attendance-desktop",
  "version": "0.1.0",
  "main": "main.js",
  "scripts": {
    "start": "electron .",
    "build:win": "electron-builder --win",
    "build:mac": "electron-builder --mac"
  },
  "devDependencies": {
    "electron": "^33.0.0",
    "electron-builder": "^25.0.0"
  },
  "dependencies": {
    "chokidar": "^3.6.0",
    "form-data": "^4.0.0",
    "node-fetch": "^3.3.2"
  }
}
```

### 4.3 `main.js` (minimal)
```js
const { app, BrowserWindow, ipcMain, safeStorage } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const { startWatcher } = require('./watch');

const SERVER = 'https://rnd.asiakawaii.com/attendance';

function createWindow () {
  const win = new BrowserWindow({
    width: 1280,
    height: 860,
    title: 'Attendance & Daily Packs',
    webPreferences: { preload: path.join(__dirname, 'preload.js') }
  });
  // Load the existing console straight from the server — zero re-implementation.
  win.loadURL(`${SERVER}/console`);
}

// Three modes — match the three console buttons:
//   'attendance'       — Auto-update on the Attendance tab    (PDF flow)
//   'daily_packs_pdf'  — Auto-update on the Daily Packs PDF tab
//   'daily_packs_xlsx' — Auto-update on the Daily Packs Excel tab (btnXlsxAuRun)
ipcMain.handle('auto-update', async (_e, kind) => {
  const ROUTES = {
    attendance:        `${SERVER}/api/v1/pdf/auto-upload?save=true`,
    daily_packs_pdf:   `${SERVER}/api/daily-packs/auto-extract`,
    daily_packs_xlsx:  `${SERVER}/api/daily-packs/auto-extract-excel`,
  };
  const url = ROUTES[kind];
  if (!url) throw new Error(`unknown auto-update kind: ${kind}`);
  // Only the v1 endpoint requires the API key; the daily-packs ones are
  // browser-facing and unauthenticated.
  const headers = url.includes('/api/v1/')
    ? { 'X-API-Key': process.env.ATTENDANCE_API_KEY }
    : {};
  const res = await fetch(url, { method: 'POST', headers });
  return res.json();
});

// Two upload IPC handlers — one per file kind — so the Electron renderer
// can push files into the correct watched folder before triggering the
// matching auto-update above.
ipcMain.handle('upload-pdf', async (_e, localPath) => {
  const fs = require('fs'); const FormData = require('form-data');
  const fd = new FormData();
  fd.append('file', fs.createReadStream(localPath), { contentType: 'application/pdf' });
  const r = await fetch(`${SERVER}/api/v1/pdf/upload`, {
    method: 'POST',
    headers: { 'X-API-Key': process.env.ATTENDANCE_API_KEY, ...fd.getHeaders() },
    body: fd,
  });
  return r.json();
});

ipcMain.handle('upload-xlsx', async (_e, localPath) => {
  const fs = require('fs'); const FormData = require('form-data');
  const fd = new FormData();
  fd.append('file', fs.createReadStream(localPath));
  const r = await fetch(`${SERVER}/api/v1/xlsx/upload`, {
    method: 'POST',
    headers: { 'X-API-Key': process.env.ATTENDANCE_API_KEY, ...fd.getHeaders() },
    body: fd,
  });
  return r.json();
});

app.whenReady().then(() => {
  createWindow();
  startWatcher(); // optional, see §4.5
});
```

### 4.4 `preload.js`
```js
const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('desktop', {
  autoUpdate:  (kind)      => ipcRenderer.invoke('auto-update', kind),
  uploadPdf:   (localPath) => ipcRenderer.invoke('upload-pdf', localPath),
  uploadXlsx:  (localPath) => ipcRenderer.invoke('upload-xlsx', localPath),
});
```

Renderer use:
```js
// Push the latest attendance PDF then trigger attendance auto-update
await window.desktop.uploadPdf('C:/Company_Data/03_就業日報PDF/就業日報2026.04.30.pdf');
const r1 = await window.desktop.autoUpdate('attendance');

// Push the latest daily-packs Excel then trigger Excel auto-extract
await window.desktop.uploadXlsx('C:/Company_Data/07_FullCast/２６.０４.３０.xlsx');
const r2 = await window.desktop.autoUpdate('daily_packs_xlsx');
```

The two flows are independent — never mix endpoints across them or you'll see the wrong response shape (e.g., the attendance flow returns `{ saved, records_processed, batch_id, mismatches, … }` while the Excel flow returns `{ source_filename, meta, products, start, prediction }`).

### 4.5 `watch.js` — watch a Windows folder, mirror to server
```js
const chokidar  = require('chokidar');
const fs        = require('fs');
const FormData  = require('form-data');

const KEY = process.env.ATTENDANCE_API_KEY;

function pushPdf(localPath) {
  const fd = new FormData();
  fd.append('file', fs.createReadStream(localPath), { contentType: 'application/pdf' });
  fetch('https://rnd.asiakawaii.com/attendance/api/v1/pdf/upload', {
    method: 'POST',
    headers: { 'X-API-Key': KEY, ...fd.getHeaders() },
    body: fd,
  }).then(r => r.json()).then(j => console.log('uploaded', j.filename));
}

exports.startWatcher = function () {
  chokidar
    .watch('C:/Company_Data/03_就業日報PDF', { ignoreInitial: false })
    .on('add', p => p.toLowerCase().endsWith('.pdf') && pushPdf(p));
};
```

### 4.6 Build a one-file installer
```cmd
npm install
npm run build:win    :: outputs   dist\Attendance-Desktop-Setup-0.1.0.exe
```

Ship the `.exe` to the office PC. First launch: prompt for the API key, save it via `safeStorage.encryptString(...)` into `%APPDATA%/attendance-desktop/key.bin`.

---

## 5. What else can the **Auto-update** button do?

Because the desktop app sits between the click and the server, you can chain *local* actions before/after the HTTP call. Suggestions, ranked by usefulness:

1. **Pre-sync from a Windows share** — before calling the API, run `robocopy` or `rsync` to copy the day's PDFs from the office share to the watched folder. One click instead of two manual steps.
   ```cmd
   robocopy "\\OFFICE\Share\AttendancePDF" "C:\app\watched\attendance" *.pdf /MIR /NJH /NJS
   ```
2. **Open the resulting Excel automatically** — after `?save=true`, the response includes `download_url`. Have Electron `shell.openExternal(url)` so the file pops up in Excel.
3. **Toast + sound on mismatch** — if `mismatch_count > 0`, fire a Windows toast notification with the offending names so the operator notices.
4. **Auto-print** — pipe the saved Excel to the default printer with `print /D:"\\PRINTER01\HR" file.xlsx`.
5. **Slack / Teams webhook** — POST a one-line summary (`record_date`, `records_processed`, `mismatch_count`) to a webhook. Useful if the operator works alone and management wants visibility.
6. **Backup** — `xcopy` the picked PDF to `D:\Archive\YYYY\MM\` so you have a local copy independent of the Pi's disk.
7. **Schedule, then trigger** — let Windows Task Scheduler call the same `auto-update` IPC on a cron, so even if nobody clicks the button you still get the daily import.

Pick whichever matches your workflow; each of them is ~10 lines of Node added to the IPC handler in §4.3.

---

## 6. Web design ↔ desktop app compatibility checklist

The plan is to keep one codebase: the web UI **is** the desktop UI (loaded via `win.loadURL`). To avoid surprises when wrapping it in Electron:

- ✅ Stay vanilla HTML/CSS/JS (already true) — no service workers, no PWA-only APIs.
- ✅ Use **relative API paths** (`/attendance/api/...`) — already done in `console.html`.
- ✅ All file pickers are `<input type="file">` — works inside Electron's renderer.
- ✅ Use `window.desktop?.autoUpdate?.()` if present, else fall back to `fetch()` — that single conditional is the only browser-vs-desktop branch.
- ⚠️ Avoid `window.alert/prompt` for production flows — they look out of place inside a chrome-less Electron window. Stick with the existing `showMsg("msgUpload", …)` toasts.
- ⚠️ Don't rely on cookies for auth on Electron; use the API key header for any `/api/v1/*` call.
- ⚠️ Test at 1280×800 (Electron default) and 1920×1080 — mobile breakpoints are nice but the desktop app will mostly run fullscreen.

Enhancement hook for the web side:
```js
// console.html, inside the existing $btnAuRun click handler:
if (window.desktop?.autoUpdate) {
  await window.desktop.autoUpdate('attendance'); // gives the desktop app a chance to robocopy first
} else {
  await fetch(api("/api/attendance/auto-upload?save=false"), { method: "POST" });
}
```
If the page is loaded in a normal browser, `window.desktop` is `undefined` and the existing fetch path runs unchanged.

---

## 6.5 Desktop-client update guide — back-fill any date (v3.4)

This is the recipe for the `watch.js` flow described in §1 of the desktop
guide ("REST pre-check → upload-if-missing → trigger → verify"), now extended
to back-fill **any** report_date — not just today — using files already on the
server.

### 6.5.1 New / changed endpoints

| Method | Path                                                        | What changed                                                                                              |
|--------|-------------------------------------------------------------|------------------------------------------------------------------------------------------------------------|
| GET    | `/api/v1/xlsx/list`                                         | **New.** Lists Excel files already on the server. Each entry includes `extracted_date` parsed from the filename. |
| POST   | `/api/v1/pdf/auto-upload?save=true&date=YYYY-MM-DD`         | `date` is **new and optional**. Without it, picks latest (legacy). With it, picks the matching file or returns `file_not_available`. |
| POST   | `/api/daily-packs/auto-extract-excel?date=YYYY-MM-DD`       | `date` is **new and optional**. Same semantics as above.                                                  |

Backward-compatibility: every existing caller (legacy `watch.js`, `upload_latest.bat`, the console buttons) keeps working unchanged because `date` is optional.

### 6.5.2 Updated decision tree for `_getDataStatus()` callers

```
GET /api/data-status/{date}
   ↓
For each missing block (attendance, daily_packs):
   ├─ Is the file for {date} already on the server?
   │     • PDFs:  GET /api/v1/pdf/list   → check `extracted_date`
   │     • Excel: GET /api/v1/xlsx/list  → check `extracted_date`
   │
   ├─ YES → call the trigger with ?date={date} only (skip upload)
   │     • POST /api/v1/pdf/auto-upload?save=true&date={date}
   │     • POST /api/daily-packs/auto-extract-excel?date={date}
   │
   └─ NO  → upload, THEN trigger with ?date={date}
         • POST /api/v1/pdf/upload    (file)
         • POST /api/v1/pdf/auto-upload?save=true&date={date}
         • POST /api/v1/xlsx/upload   (file)
         • POST /api/daily-packs/auto-extract-excel?date={date}

GET /api/data-status/{date}   ← verify (still up to 6 polls)
```

The `?date=` parameter ensures that even if the server has a *newer* file
sitting in the watched folder, the back-fill ingests the correct one for the
target date instead of overshooting to "latest."

### 6.5.3 Drop-in `watch.js` patch

```js
// 1) Pre-check + decide which blocks to fix.
const status = await _getDataStatus(targetDate);
if (status.all_present) return { ok: true, skipped: true };

// 2) For each missing block, ask the server first whether the file for
//    targetDate is already there. If yes, skip the upload step entirely.
async function _hasOnServer(kind, targetDate) {
  const url = kind === 'pdf'
    ? `${BASE}/api/v1/pdf/list`
    : `${BASE}/api/v1/xlsx/list`;
  const r = await fetch(url, { headers: { 'X-API-Key': KEY } });
  if (!r.ok) return false;
  const j = await r.json();
  return (j.files || []).some(f => f.extracted_date === targetDate);
}

// 3) Attendance block
if (status.missing.includes('attendance')) {
  if (!await _hasOnServer('pdf', targetDate)) {
    await _uploadOne('pdf', localPdfPath);                  // POST /api/v1/pdf/upload
  }
  const r = await fetch(
    `${BASE}/api/v1/pdf/auto-upload?save=true&date=${targetDate}`,
    { method: 'POST', headers: { 'X-API-Key': KEY } }
  );
  if (r.status === 404) {
    const j = await r.json().catch(() => ({}));
    const d = j.detail || {};
    if (d.error === 'file_not_available') {
      throw new Error(`Attendance PDF for ${d.requested_date} not on server. Upload it first.`);
    }
  }
}

// 4) Daily-packs block (mirror of the attendance branch)
if (status.missing.includes('daily_packs')) {
  if (!await _hasOnServer('xlsx', targetDate)) {
    await _uploadOne('xlsx', localXlsxPath);                // POST /api/v1/xlsx/upload
  }
  const r = await fetch(
    `${BASE}/api/daily-packs/auto-extract-excel?date=${targetDate}`,
    { method: 'POST' }   // no key — endpoint is browser-facing
  );
  if (r.status === 404) {
    const j = await r.json().catch(() => ({}));
    const d = j.detail || {};
    if (d.error === 'file_not_available') {
      throw new Error(`Daily-packs Excel for ${d.requested_date} not on server. Upload it first.`);
    }
  }
}

// 5) Verify (existing poll loop, unchanged)
```

Two reminders that survive from §3:
- Send `X-API-Key` only to `/api/v1/...` endpoints. The Excel trigger
  (`/api/daily-packs/auto-extract-excel`) is **browser-facing and unauthenticated** — sending the key is harmless, omitting it is correct.
- The `date` parameter is the **report_date** (production date). Per
  `project_date_rules.md` the server keys attendance internally on
  `record_date = report_date − 1`. The same `date` value goes to every endpoint
  in the chain (`data-status`, `auto-upload`, `auto-extract-excel`).

### 6.5.4 Smoke test (back-fill 2026-04-23)

```cmd
set KEY=YOUR_KEY
set BASE=https://rnd.asiakawaii.com/attendance
set DATE=2026-04-23

:: Is anything missing for that date?
curl -s %BASE%/api/data-status/%DATE%

:: What attendance PDFs / packs Excels does the server already have?
curl -s -H "X-API-Key: %KEY%" %BASE%/api/v1/pdf/list
curl -s -H "X-API-Key: %KEY%" %BASE%/api/v1/xlsx/list

:: Back-fill attendance from server-side PDF (no upload needed)
curl -s -X POST -H "X-API-Key: %KEY%" ^
  "%BASE%/api/v1/pdf/auto-upload?save=true&date=%DATE%"

:: Back-fill daily packs from server-side Excel (no upload needed)
curl -s -X POST "%BASE%/api/daily-packs/auto-extract-excel?date=%DATE%"

:: Verify
curl -s %BASE%/api/data-status/%DATE%
```

If a file isn't on the server, the trigger returns the structured
`file_not_available` 404 from §3 — upload first via `/api/v1/pdf/upload` or
`/api/v1/xlsx/upload`, then retry the trigger with the same `?date=`.

---

## 6.6 Move-to-Done warnings (v3.4)

After a successful DB save the server moves the source PDF / Excel into a
`done/` subfolder so the next Auto-update doesn't re-pick it. If that file
move fails (filesystem error, cross-device rename, file removed mid-flight,
etc.), the API call still **succeeds** — the DB write already committed and
must not be rolled back by a filesystem hiccup. The successful response simply
carries `moved_to_done: false`.

Each such warning is appended to `logs/done_warnings.log` (one JSON entry
per line) and can be retrieved by the desktop client over a key-protected
endpoint:

```cmd
:: Latest 200 warnings (default), oldest first
curl -s -H "X-API-Key: YOUR_KEY" ^
  https://rnd.asiakawaii.com/attendance/api/v1/done-files/warnings

:: Filter by kind, custom limit
curl -s -H "X-API-Key: YOUR_KEY" ^
  "https://rnd.asiakawaii.com/attendance/api/v1/done-files/warnings?kind=daily_packs&limit=50"
```

Response shape:

```json
{
  "path":   "/var/www/attendance_app/logs/done_warnings.log",
  "exists": true,
  "count":  2,
  "warnings": [
    { "ts": "2026-05-02T03:14:19", "kind": "attendance",
      "filename": "就業日報2026.04.23.pdf",
      "src_path": "/var/www/attendance_app/auto_uploads/attendance/就業日報2026.04.23.pdf",
      "error":    "PermissionError: [Errno 13] Permission denied" },
    { "ts": "2026-05-02T03:18:02", "kind": "daily_packs",
      "filename": "２６.０４.２３.xlsx",
      "src_path": "/var/www/attendance_app/auto_uploads/daily_packs/２６.０４.２３.xlsx",
      "error":    "OSError: [Errno 18] Invalid cross-device link" }
  ]
}
```

Recommended desktop client behavior: after every save call where
`moved_to_done === false`, poll `/api/v1/done-files/warnings?kind=…&limit=10`
once and surface the most recent matching entry to the operator with a hint
("the file did not auto-archive — please drag it from the watched folder into
done/ manually, or retry by deleting the source"). Auth: `X-API-Key`,
identical to every other `/api/v1/*` call.

---

## 7. Quick smoke-test (copy-paste)

```cmd
set KEY=YOUR_KEY
set BASE=https://rnd.asiakawaii.com/attendance

curl -s -H "X-API-Key: %KEY%" %BASE%/api/v1/ping
curl -s %BASE%/api/auto-upload/config/all
curl -s -X POST -H "X-API-Key: %KEY%" %BASE%/api/v1/pdf/auto-upload
```

If all three return `200 OK` JSON, your keys, folders, and routes are wired correctly and the Electron app will work end-to-end.

---

## 8. LINE Messaging API integration (v3.2)

The app pushes attendance reports to phones over LINE. Three things happen:

1. **A LINE bot** sits at `https://rnd.asiakawaii.com/attendance/api/line/webhook`. When anyone messages the bot, their `userId` (or `groupId`/`roomId` if it's in a chat) is auto-registered into the recipient list. The bot replies with a confirmation. They will then receive any report that someone sends from the console.
2. **Mobile-only viewer pages** at `/m/report` and `/m/summary` — these serve the **same** files as `/gantt` and `/summary` so the graphics are 100% identical, but a `body.mobile` CSS class hides admin chrome (top nav, print/PDF buttons, Member Hours tab, compare/target toggles).
3. **Send buttons** on the Reports page (`/reports`) and the Gantt page (`/gantt`) compose a thumbnail image of the productivity 4-box, upload it to the server, and push a single LINE **Buttons Template card** (image + title + tap button → mobile viewer) to every registered recipient.

### 8.1 Configuration

- File: `attendance_app/line_config.json` (chmod 600, **gitignored**)
- Schema:
  ```json
  {
    "channel_id": "...",
    "channel_secret": "...",
    "channel_access_token": "...",
    "public_base_url": "https://rnd.asiakawaii.com/attendance",
    "recipients": [
      { "id": "U…", "kind": "user|group|room", "display_name": "…", "registered_at": "ISO-8601" }
    ]
  }
  ```
- Credentials come from **LINE Developers Console** (`developers.line.biz`) → channel → Messaging API tab. Webhook toggle must be **ON**, and Auto-reply / Greeting messages must be **OFF** in `manager.line.biz` (Settings → Response settings) — otherwise LINE intercepts user messages before they reach our webhook.

### 8.2 LINE endpoints

All `/api/line/...` endpoints are **unauthenticated** (no `X-API-Key`) — same convention as the browser-facing `/api/gantt/*` endpoints. The webhook is protected by HMAC signature verification.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/line/webhook` | LINE → us. Verifies `X-Line-Signature` (HMAC-SHA256, channel secret, base64). Auto-registers any sender's id (user / group / room). On `message` events: replies with their id; on `report` / `report YYYY-MM-DD`: replies with the gantt URL. Empty/probe payloads (LINE's "Verify" button) return 200. |
| `POST` | `/api/line/send` | Body `{report_date, type}`. Pushes a plain text message with the gantt URL to every recipient. Older flow — kept for compatibility; UI now uses `send-mobile-link`. |
| `POST` | `/api/line/upload-and-send` | Multipart: `file` (PDF, ≤12 MB, must start with `%PDF-`), `report_date`, `type`. Saves to `static/line_pdfs/<type>_<date>.pdf` and pushes the public URL. Used by the gantt-page **💬 Send PDF to LINE** button. |
| `POST` | `/api/line/send-mobile-link` | Multipart: `file` (PNG or JPEG, ≤5 MB), `report_date`, `type`. Saves to `static/line_images/<type>_<date>.<ext>`, sends a single **Buttons Template card** (`thumbnail + title + body + tap button`) per recipient with `defaultAction = uri to /m/<type>`. Used by Reports-page **💬 Send to LINE** buttons. |
| `POST` | `/api/line/send-message` | JSON body `{report_date, type}`. **No upload** — uses the branded default thumbnail at `static/line_card_default/{attendance,summary}_card.jpg`. Sends the same Buttons Template card per recipient with the tap target on `/m/report` or `/m/summary`. Designed for **desktop app integrations** that don't have a snapshot image to upload. |
| `POST` | `/api/line/test-hi` | Pushes "Hi 👋 (test from V3 Attendance Console)" to all recipients. No body. |
| `GET` | `/api/line/recipients` | Lists registered recipients (id, kind, display_name, registered_at). |
| `POST` | `/api/line/recipients/rename` | Body `{id, display_name}`. Renames a recipient (max 60 chars). |
| `POST` | `/api/line/recipients/delete` | Body `{id}`. Removes a recipient — they no longer receive reports unless they re-message the bot. |

#### `send-mobile-link` response

```json
{
  "ok": true,
  "image_url": "https://rnd.asiakawaii.com/attendance/static/line_images/attendance_2026-04-28.png",
  "link_url":  "https://rnd.asiakawaii.com/attendance/m/report?date=2026-04-28",
  "results": [
    { "id": "U…", "card_status": 200, "response": "{}" }
  ]
}
```

### 8.3 Mobile viewer endpoints

| Method | Path | Serves | Notes |
|---|---|---|---|
| `GET` | `/m/report?date=YYYY-MM-DD` | `static/gantt.html` | Same gantt page; mobile-mode JS detects `/m/...` path and adds `body.mobile`, hides admin chrome, drops the **Member Hours** tab, and injects a `<base href="/attendance/">` so relative `fetch('api/...')` resolves correctly under the new path. |
| `GET` | `/m/summary?date=YYYY-MM-DD` | `static/summary.html` | Same summary page; mobile-mode JS hides admin chrome, defaults to **Month** range with all four legend chips ON (S1/S2/Combined/Packs), short legend labels (`S1 / S2 / 合計 / Packs`) with `translate="no"` to defeat browser auto-translate. **Tap chart** → fullscreen rotated landscape with ✕ close + ↻ re-rotate buttons. Tap-to-show tooltip works in both portrait and rotated views (uses `getScreenCTM().inverse()` for rotation-aware hit testing). |
| `GET` | `/api/m/summary?date=YYYY-MM-DD&days=30` | JSON | Rolling-N-day aggregate (1..92). Iterates `gantt_for_date()` per day, returns `{anchor, start, days, days_with_data, total_packs, s1/s2/combined_total_hours, s1/s2/combined_avg_lp, rows[]}`. Currently used internally by the Reports page snapshot builder. |

### 8.4 Bootstrapping a new recipient

1. Operator opens the bot on LINE (scan QR from Developers Console → Messaging API tab → QR code) and taps **Add Friend**.
2. They send any message to the bot.
3. LINE forwards it to our webhook. We verify the signature, extract `userId` from `events[].source.userId`, append it to `recipients[]` with `display_name=""`, and reply confirming registration.
4. Operator on the Reports page clicks **List recipients**, then **✎** to rename them to a human label like `creator`, `factory_manager`, etc.
5. From then on, every **💬 Send to LINE** click reaches that person.

### 8.5 LINE quick-test (copy-paste)

```cmd
set BASE=https://rnd.asiakawaii.com/attendance

:: List who is currently subscribed to receive reports
curl -s %BASE%/api/line/recipients

:: Send a Hi to everyone (no payload required)
curl -s -X POST %BASE%/api/line/test-hi

:: Rename a recipient
curl -s -X POST -H "Content-Type: application/json" ^
  -d "{\"id\":\"Ube67de00fe2a3e138cc46e34ae46914f\",\"display_name\":\"creator\"}" ^
  %BASE%/api/line/recipients/rename
```

---

## 9. Day-off Schedule (v3.3+)

The Day-off Schedule tab on `/management` lets an operator plan everyone's planned absences (vacation, fixed off-days, AL) in one grid, persists them to `dayoff_schedule.json`, and feeds those dates back into the daily gantt so the report can distinguish *scheduled* from *unauthorized* absences.

### 9.1 Storage

- `attendance_app/dayoff_schedule.json` (gitignored). Shape:
  ```json
  {
    "schedule": {
      "00000320": ["2026-02-25", "2026-02-26", "2026-03-04", ...],
      "00000401": ["2026-03-08", ...]
    },
    "updated_at": "2026-04-30T05:23:54Z",
    "highlight_unauthorized": false
  }
  ```
- `attendance_app/nickname_map.json` (gitignored). Excel nicknames → 8-digit employee codes, populated by the import wizard so future imports auto-match.

### 9.2 Endpoints (all unauthenticated, browser-facing)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/dayoff/schedule` | Returns the full schedule + `highlight_unauthorized` flag. |
| `PUT` | `/api/dayoff/schedule` | Replaces the schedule. Validates each date matches `^\d{4}-\d{2}-\d{2}$`; silently drops codes not in `EMPLOYEE_ROSTER`. Preserves `highlight_unauthorized` if not in body. |
| `POST` | `/api/dayoff/highlight-unauthorized` | Body `{enabled: bool}`. Flips just the toggle. The gantt page picks this up on next load and renders absent-not-on-list rows in red. |
| `POST` | `/api/dayoff/import-excel` | Multipart `file` (.xlsx, ≤25 MB, must start with `PK\x03\x04`). Parses every monthly sheet (`初期設定` skipped), drops 30 known column-header strings (工場長 / 昼社員 / 2課役職 / 製造1課 / 製麺社員 / 行事・備考 / 祝日 / …), resolves each remaining name via saved nickname map → exact normalized match. Returns `{matched:[{code,name,raw,date,sheet}], unmatched:[{raw,norm,count,first_date,suggestions:[{code,name,section_label}]}]}`. |
| `POST` | `/api/dayoff/apply-import` | Body `{entries:[{code,date}], mappings:{nickname:code}, mode:"merge"\|"replace_range"}`. Persists mappings into `nickname_map.json`, then folds entries into `dayoff_schedule.json` (merge = union; replace_range = wipe affected codes' entries within `[date_min..date_max]` first). |

### 9.3 Excel import workflow (UI on `/management` → 📅 Day-off Schedule)

1. Click **`📤 Import 定休表 (.xlsx)`** in the toolbar.
2. Pick the file, click **🔍 Parse + match**. Server returns matched + unmatched stats.
3. The unmatched table lists each distinct nickname with: count, first-seen date, and a `<select>` dropdown grouped into **Suggested** (auto-suggestions, single-suggestion case is preselected with an "auto" pill) and **All employees**. Pick the right person for each, or leave as **— skip —** for office/admin staff that aren't in the attendance roster.
4. Pick **Merge** (union onto existing schedule) or **Replace existing entries in window** (wipe the imported window first).
5. Click **✅ Apply to schedule**. The wizard saves your nickname mappings, re-parses with mappings, and folds the matched (code, date) entries into `dayoff_schedule.json`. Subsequent imports auto-resolve those nicknames.

### 9.4 Gantt highlighting (read-only consumer)

`/gantt`, `/m/report`, and the `?report=1` popup all do `fetch('api/dayoff/schedule')` on each load. Inside `renderRow()` the `cls === 'absent'` branch:

- date ∈ employee's day-off list → calm green **`休 scheduled`** pill (always shown, regardless of toggle);
- toggle ON + date ∉ list → red **`🚨 Unauthorized`** pill + `#fff2f1` row background + `#b42318` left border;
- toggle OFF + date ∉ list → existing faint "Absent" label.

Sections that don't run the daily packs line (製造1課) are unaffected.

### 9.5 Day-off quick-test (copy-paste)

```cmd
set BASE=https://rnd.asiakawaii.com/attendance

:: Read schedule + flag
curl -s %BASE%/api/dayoff/schedule

:: Flip the global toggle ON / OFF (drives all gantt views)
curl -s -X POST -H "Content-Type: application/json" -d "{\"enabled\":true}"  %BASE%/api/dayoff/highlight-unauthorized
curl -s -X POST -H "Content-Type: application/json" -d "{\"enabled\":false}" %BASE%/api/dayoff/highlight-unauthorized

:: Save schedule (merge with what's already there)
curl -s -X PUT -H "Content-Type: application/json" ^
  -d "{\"schedule\":{\"00000320\":[\"2026-05-01\",\"2026-05-02\"]}}" ^
  %BASE%/api/dayoff/schedule

:: Import a 定休表 Excel and inspect the matched / unmatched preview
curl -s -X POST -F "file=@C:\path\to\定休表.xlsx" %BASE%/api/dayoff/import-excel
```
