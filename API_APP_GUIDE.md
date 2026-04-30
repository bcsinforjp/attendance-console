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
curl -s -H "X-API-Key: YOUR_KEY" https://rnd.asiakawaii.com/attendance/api/v1/pdf/list
curl -s -H "X-API-Key: YOUR_KEY" -O https://rnd.asiakawaii.com/attendance/api/v1/pdf/retrieve/就業日報2026.01.05.pdf
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

ipcMain.handle('auto-update', async (_e, kind /* 'attendance' | 'daily_packs' */) => {
  const url = kind === 'daily_packs'
    ? `${SERVER}/api/daily-packs/auto-extract`
    : `${SERVER}/api/v1/pdf/auto-upload?save=true`;
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'X-API-Key': process.env.ATTENDANCE_API_KEY }
  });
  return res.json();
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
  autoUpdate: (kind) => ipcRenderer.invoke('auto-update', kind),
});
```

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

## 7. Quick smoke-test (copy-paste)

```cmd
set KEY=YOUR_KEY
set BASE=https://rnd.asiakawaii.com/attendance

curl -s -H "X-API-Key: %KEY%" %BASE%/api/v1/ping
curl -s %BASE%/api/auto-upload/config/all
curl -s -X POST -H "X-API-Key: %KEY%" %BASE%/api/v1/pdf/auto-upload
```

If all three return `200 OK` JSON, your keys, folders, and routes are wired correctly and the Electron app will work end-to-end.
