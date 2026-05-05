# Desktop Agent Task — Wire SHA + Status Pre-Check Into `watch.js`

> **Audience:** the AI coding agent that owns the desktop watcher (the Electron / Node app on the Windows machine that has `watch.js`).
> **Backend version this targets:** Pi server, `attendance_app/main.py`, updated 2026-05-06.
> **Goal:** stop re-uploading files the server has already processed, stop blindly overwriting DB rows for dates that already have data, and self-heal when DB rows were deleted manually.

---

## 1. What the Pi server now exposes

### 1a. `GET /api/v1/status/precheck?type=&date=&sha256=` — single decision call

Replaces the previous `/api/v1/status/check` and `/api/v1/status/check-sha` (both **removed**).

The server probes the data table first (source of truth), then reconciles `uploaded_file_registry` against it, and returns one of three `action` values. **Always returns 200** (or 400/401). Treat any non-200 as fail-open.

```
GET https://<pi-host>/api/v1/status/precheck
    ?type=attendance        ← or 'production'
    &date=2026-04-28        ← the production / record date the file is FOR (ISO)
    &sha256=<64-hex>        ← lowercase SHA-256 of the bytes you're about to send
X-API-Key: <key>
```

Three possible responses:

```
→ 200 { "action": "upload",          "reason": "no_data",        "type": "...", "date": "...", "sha256": "..." }
→ 200 { "action": "skip",            "reason": "same_file",      "type": "...", "date": "...", "sha256": "...", "uploaded_at": "..." }
→ 200 { "action": "confirm_replace", "reason": "different_file", "type": "...", "date": "...", "sha256": "...", "existing_records": 42, "uploaded_at": "..." }
```

What each action means:

| `action`            | Server state                                       | Desktop behavior                                                              |
| ------------------- | -------------------------------------------------- | ----------------------------------------------------------------------------- |
| `upload`            | Data table empty for this date. Stale registry rows for this date or hash were deleted server-side. | Send the file (`POST /api/v1/{pdf,xlsx}/upload`).                              |
| `skip`              | Data is in the DB AND the same SHA is already registered for this date. | Do nothing. Move local file to handled folder.                              |
| `confirm_replace`   | Data is in the DB but the SHA differs (the file changed). | Ask the user "replace existing data for date X?" — only upload on confirm.  |

### 1b. Existing upload endpoints — **new behaviour**
`POST /api/v1/pdf/upload` and `POST /api/v1/xlsx/upload` now compute SHA-256 server-side and **reject duplicates with HTTP 409**:

```
→ 409 {
    "detail": {
      "status": "duplicate",
      "reason": "sha256 already registered",
      "sha256": "...",
      "registry": {
        "file_name": "...",
        "file_type": "attendance",
        "target_date": "2026-04-28",
        "status": "loaded",
        "received_at": "...",
        "loaded_at": "...",
        "moved_path": "/var/www/.../auto_uploads/attendance/done/<file>",
        "record_count": 42
      }
    }
  }
```

Successful upload responses now include a `"sha256"` field.

---

## 2. Required changes to `watch.js`

### 2.1 Compute SHA on the desktop
You **must** SHA-256 the file before sending. Node's stdlib is enough — no new dependency.

```js
const crypto = require('crypto');
const fs = require('fs');

function sha256OfFile(filePath) {
  return new Promise((resolve, reject) => {
    const hash = crypto.createHash('sha256');
    const stream = fs.createReadStream(filePath);
    stream.on('data', (chunk) => hash.update(chunk));
    stream.on('end', () => resolve(hash.digest('hex')));
    stream.on('error', reject);
  });
}
```

### 2.2 Replace the existing pre-upload stub
Find the block guarded by `CHECK_API_BEFORE_UPLOAD` (currently `false`). Replace with the flow below and **flip the flag to `true`**.

```js
const CHECK_API_BEFORE_UPLOAD = true;

/**
 * Decide whether to upload `filePath`.
 * Returns one of:
 *   { action: 'upload',          sha }                  — go ahead and upload
 *   { action: 'skip',            reason, info, sha }    — server already has this exact file
 *   { action: 'confirm_replace', reason, info, sha }    — different file for a date that already has data
 *   { action: 'upload',          warn: '...', sha? }    — pre-check failed; fail-open per spec
 */
async function decidePreUpload({ filePath, fileType, parsedDate, baseUrl, apiKey }) {
  let sha;
  try { sha = await sha256OfFile(filePath); }
  catch (e) { return { action: 'upload', warn: 'sha-compute-failed: ' + e.message }; }

  if (!parsedDate) {
    return { action: 'upload', sha, warn: 'no-date-parsed' };
  }

  try {
    const url = `${baseUrl}/api/v1/status/precheck`
              + `?type=${encodeURIComponent(fileType)}`
              + `&date=${encodeURIComponent(parsedDate)}`
              + `&sha256=${sha}`;
    const r = await fetch(url, {
      headers: { 'X-API-Key': apiKey },
      signal: AbortSignal.timeout(5000),
    });
    if (r.ok) {
      const j = await r.json();
      // j.action ∈ {'upload', 'skip', 'confirm_replace'}
      return { ...j, sha, info: j };
    }
  } catch (e) { /* fall through — fail-open */ }

  return { action: 'upload', sha, warn: 'precheck-failed' };
}
```

### 2.3 Handle the new 409 response on the actual upload
The `POST /api/v1/{pdf,xlsx}/upload` call needs a 409 branch:

```js
const resp = await uploadFile(/* ... */);
if (resp.status === 409) {
  const body = await resp.json();
  log.info('Server rejected as duplicate', body.detail);
  // Treat exactly like decidePreUpload returned skip(sha-duplicate).
  // Do NOT retry. Do NOT delete the local file unless your existing
  // post-success cleanup already handles it.
  return { skipped: true, reason: 'sha-duplicate', info: body.detail };
}
```

### 2.4 Map `fileType` from filename
- `*.pdf` → `attendance`
- `*.xlsx` / `*.xlsm` → `production`

### 2.5 Date parsing
Existing `watch.js` already extracts date from filenames like `就業日報2026.04.28.pdf`. Pass that ISO string straight through.

---

## 3. End-to-end flow (pseudo-code)

```js
async function processWatchedFile(filePath) {
  const fileType   = filePath.toLowerCase().endsWith('.pdf') ? 'attendance' : 'production';
  const parsedDate = parseDateFromFilename(path.basename(filePath));   // 'YYYY-MM-DD' or null

  const decision = await decidePreUpload({
    filePath, fileType, parsedDate,
    baseUrl: CFG.baseUrl,
    apiKey:  CFG.apiKey,
  });

  if (decision.action === 'skip') {
    log.info(`Skip ${path.basename(filePath)} — ${decision.reason}`, decision.info);
    moveLocalToHandledFolder(filePath);   // your existing post-success cleanup
    return;
  }

  if (decision.action === 'confirm_replace') {
    const ok = await askUserToReplace({
      file: path.basename(filePath),
      date: decision.date,
      existingRecords: decision.existing_records,
      uploadedAt: decision.uploaded_at,
    });
    if (!ok) {
      log.info(`User declined replace for ${path.basename(filePath)}`);
      return;
    }
    // fall through and upload — server will overwrite
  }

  if (decision.warn) log.warn(decision.warn);

  const resp = await uploadFile(filePath, fileType, CFG);

  if (resp.status === 409) {
    log.info(`Server says duplicate — ${path.basename(filePath)}`);
    moveLocalToHandledFolder(filePath);
    return;
  }
  if (!resp.ok) {
    log.error('Upload failed', resp.status, await resp.text());
    return;     // do NOT delete local file; let next watch tick retry
  }

  const body = await resp.json();
  log.info(`Uploaded ${body.filename} sha=${body.sha256.slice(0,12)}…`);
  moveLocalToHandledFolder(filePath);
}
```

---

## 4. Things the desktop agent must NOT do

- **Do not** SHA the file twice. Compute once, pass it through.
- **Do not** retry on 409. The server is intentionally rejecting it.
- **Do not** delete the local file on a 5xx — only on success or 409.
- **Do not** add timeouts > 5 s on the pre-check calls (spec budget).
- **Do not** change anything in the LINE-send flow. That is locked.

---

## 5. Acceptance test

After integration, run these manually:

| # | Setup | Expected |
|---|-------|----------|
| 1 | Drop a brand-new PDF for date X into the watched folder | precheck → `action: upload` (`reason: no_data`); upload succeeds, response includes `sha256`, file moves to handled folder |
| 2 | Drop the **exact same PDF** again | precheck → `action: skip` (`reason: same_file`); no network upload happens |
| 3 | Drop a **different PDF for the same date X** | precheck → `action: confirm_replace` (`reason: different_file`); the user is prompted; on "yes" the upload proceeds |
| 4 | Manually `DELETE FROM attendance_records WHERE record_date='X'` on the Pi, then drop the original PDF again | precheck → `action: upload` (`reason: no_data`); the stale registry row is auto-cleaned and the file re-ingests |
| 5 | Stop the Pi (network unreachable), drop a new PDF | precheck fails fail-open, upload is attempted, fails, file is **not** deleted |
| 6 | Wrong API key | precheck returns 401; treat as fail-open, upload then fails 401, file is **not** deleted |

---

## 6. Out of scope for this task

- Anything in the LINE flow (locked).
- The Grafana stack.
- Refactoring the watcher's restart / queue logic.
- Adding a UI surface for "skipped: duplicate" — log line is enough for now.

---

## 7. When done

Reply back with:
1. Diff of `watch.js`.
2. Confirmation that `CHECK_API_BEFORE_UPLOAD` is now `true`.
3. Output of acceptance tests 1-3 (test 4 and 5 are nice-to-have).
