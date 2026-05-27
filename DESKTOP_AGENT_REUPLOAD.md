# Desktop Agent Task — Re-Upload of Edited Files Must Land New Values

> **Audience:** the AI coding agent that owns the desktop watcher (Windows / Electron app, `watch.js`).
> **Backend version:** Pi server, `attendance_app/main.py`, verified 2026-05-08.
> **Companion doc:** `DESKTOP_AGENT_TASK.md` (SHA precheck integration — assumed already shipped).
> **Goal:** when the operator edits an already-uploaded file (Excel or PDF) and re-saves it, the new values must reach the Pi DB. Today they don't, and the bug is on the desktop side — Pi-side has been tested and works.

---

## 1. What was reported

Symptom: operator edits `夜勤用日報２６．０４．２２.xlsm` (already uploaded earlier),
saves it, the watcher fires, watcher logs `save-batch-ok`, **but DB still shows the old `n_total` / `y_total`**.

## 2. Pi-side verified working (2026-05-08)

End-to-end test driven from outside the watcher proved the server pipeline overwrites correctly:

| Step | Endpoint | Result |
|---|---|---|
| 1 | `POST /api/v1/xlsx/upload` (different SHA bytes) | 200 OK — accepted, new SHA recorded, no false-409 |
| 2 | `POST /api/daily-packs/auto-extract-excel?date=2026-04-22` | 200 OK — parsed 15 products, `n_total=8993, y_total=3464` |
| 3 | `POST /api/daily-packs/save-excel-batch` with **sentinel** `n_total=11111, y_total=22222` | 200 OK — `daily_packs` row updated to those exact values |
| 4 | Repeat step 3 with the original parsed values | 200 OK — row reverted to `8993 / 3464` |

**Conclusion:** the upload → extract → save chain on the Pi is overwrite-safe. Anything missing in the DB after a re-upload is because the watcher either sent the **old bytes**, **skipped the call**, or **never reached step 3**.

## 3. The contract the watcher must implement

For **every** file event from the watched folder (create AND modify):

```
file event
  └─ wait until file is closed by Excel       (see §4.1 — biggest pitfall)
  └─ compute SHA-256 from disk RIGHT NOW       (no cache)
  └─ GET  /api/v1/status/precheck?type=&date=&sha256=
        ├─ action=skip            → do nothing, move local to handled folder
        ├─ action=upload          → continue
        └─ action=confirm_replace → prompt user; on "yes", continue
  └─ POST /api/v1/{pdf,xlsx}/upload                         (gets file onto Pi)
        ├─ 409 duplicate → log + move to handled, STOP
        └─ 200           → continue with returned filename
  └─ POST /api/{daily-packs/auto-extract-excel | attendance/auto-upload}?date=YYYY-MM-DD
        └─ 200 → carry parsed payload forward
  └─ POST /api/daily-packs/save-excel-batch  (Excel only — attendance saves inside auto-upload)
        └─ 200 → emit  save-batch-ok  log line, move local to handled
```

**Step 4 (`save-excel-batch`) is mandatory for Excel.** `auto-extract-excel` only returns a preview — it does **not** write the DB. If the watcher stops after step 3 the user sees no update.

## 4. The three failure modes that cause the reported symptom

### 4.1 Watcher reads the file before Excel finished saving  *(most likely)*

Excel writes via temp file + rename. While Excel is still open, the visible file may be stale and there's a `~$<name>.xlsm` lock file alongside.

**Fix:**
- Ignore filenames starting with `~$`.
- Debounce the event (e.g. `300 ms`) and verify the file size is **stable across two consecutive reads** before hashing.
- If a `~$<name>.xlsm` lock exists in the same folder, defer until it disappears.

```js
async function waitUntilStable(filePath, { intervalMs = 300, tries = 10 } = {}) {
  let last = -1;
  for (let i = 0; i < tries; i++) {
    let s; try { s = await fs.promises.stat(filePath); } catch { return false; }
    if (s.size === last && s.size > 0) return true;
    last = s.size;
    await new Promise(r => setTimeout(r, intervalMs));
  }
  return false;
}
```

### 4.2 Watcher caches SHA / parsed payload across events

If the watcher computed SHA once on first sight and kept it in a Map keyed by filename, an edit-then-save re-fires the same path but the cached SHA still matches the OLD bytes → precheck answers `skip` → nothing is uploaded.

**Fix:** never cache SHA by filename. Hash on every event, after §4.1 stability passes.

### 4.3 Watcher stops after `auto-extract-excel`

Re-read the chain in §3. Step 4 (`/api/daily-packs/save-excel-batch`) is what writes the DB. If the watcher logs `trigger-ok` but no `save-batch-ok`, the new values cannot land. A `save-batch-ok` log on its own is also not enough — confirm the **payload sent** to `save-excel-batch` was built from the FRESH `auto-extract-excel` response, not a stashed copy from an earlier event.

The exact payload shape `save-excel-batch` expects (extracted from the Pi route, all keys come straight from the `auto-extract-excel` response except `source_method`):

```js
const saveBody = {
  production_date:    parsed.meta.production_date,           // "YYYY-MM-DD"
  products:           parsed.products,                       // array
  start_time:         parsed.start.start_time,               // "HH:MM"
  section_totals:     parsed.section_totals,                 // {n_total, y_total, combined}
  fullcast:           parsed.fullcast || [],
  production_plan:    parsed.production_plan || null,
  section_start_time: parsed.production_plan?.section_start_time || null,
  source_filename:    parsed.source_filename,
  source_method:      'excel-auto',                          // tag for the note column
};
```

`section_totals.combined` (or the sum of `n_total + y_total`) becomes `daily_packs.number_of_packs`. That is the one number the user is checking — pass it through unchanged.

## 5. Required watcher behavior (checklist)

- [ ] Treat the watched folder as **content-addressed**: identical bytes = same SHA = `skip`; any byte change = new SHA = upload path.
- [ ] On every FS event for `*.xlsx` / `*.xlsm` / `*.pdf`, run §4.1 stability + lock-file check before hashing.
- [ ] Always SHA from disk on the same tick the upload is made. Never reuse a SHA from a previous event.
- [ ] On precheck → `confirm_replace`, prompt the user (the file has changed). On `skip`, do not upload — but DO move the local file to handled, otherwise the next event re-fires the same skip.
- [ ] Excel pipeline is `upload → auto-extract-excel → save-excel-batch`. PDF pipeline is `upload → pdf/auto-upload?save=true`. Don't mix.
- [ ] Log every transition (`stable-ok`, `sha=…`, `precheck=…`, `upload=…`, `extract-ok`, `save-batch-ok`) so the next time this bug surfaces we can pinpoint which step regressed without writing another investigation script.
- [ ] On any HTTP 5xx, do **not** delete the local file — leave it for the next tick to retry.

## 6. How to verify the fix (run on a real workstation)

1. **First write.** Drop a fresh `夜勤用日報２６.MM.DD.xlsm` into the watched folder. Watcher uploads, extracts, save-batches. Confirm DB row appears via:
   ```
   curl -s "https://rnd.asiakawaii.com/attendance/api/daily-packs/<DATE>"
   ```
2. **No-op re-save.** Open the file in Excel, hit save without changing anything. Watcher should compute the same SHA, get `skip`, and **not** call `save-excel-batch`. DB `updated_at` should NOT change.
3. **Edited re-save.** Open the file, change one cell that feeds `Ｎ合計` or `Ｙ合計`, save. Watcher should:
   - Wait until Excel is closed (no `~$lock`) and size is stable.
   - Compute a NEW SHA.
   - Get precheck `confirm_replace` (data exists, SHA differs).
   - On user confirm, run upload → extract → save-batch.
   - DB row's `n_total` / `y_total` reflect the new value, `updated_at` advances.
4. **Wrong-window race.** Close Excel mid-save (kill it). Confirm the watcher does not upload a partial file (size-stability gate caught it).

If step 3 fails, diff the watcher's log lines against the chain in §3 and identify the missing step. **Do not change anything on the Pi** — the API surface is verified.

## 7. Out of scope

- Anything in the LINE flow (locked — see `feedback_line_flow_locked` in operator memory).
- Adding new server endpoints. The four already in §3 are sufficient.
- Refactoring the auto-update preview UI on the console.

## 8. When done

Reply with:
1. Diff of `watch.js` (and any helper modules touched).
2. Log excerpt from acceptance test 3 (edited re-save) showing the full transition chain.
3. Confirmation that test 2 (no-op re-save) produces no `save-batch-ok` line.
