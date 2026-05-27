# GENBA FMS — Board Review Submission

**Submitted to:** Company Director Board
**Date:** 2026-05-20
**Author:** GENBA FMS Operations
**Decision requested:** Permission to install the **GENBA FMS Daily-Report Helper** on **one (1)** dedicated company computer.

> To save as PDF: open this file in any document viewer → Print → Save as PDF.

---

## 1. What this is — in one paragraph

GENBA FMS (Genba Factory Management System) is an in-house management
console for daily attendance and production data. The central system is
already in service at **`genbafms.com`** and currently does three things:

1. Picks up the daily 就業日報 PDF and 夜勤用日報 Excel files we already
   produce and turns them into clean, reviewable data.
2. Generates printable **Gantt** and **Productivity Summary** reports with
   labor-productivity KPIs.
3. Lets approved external companies look up agreed production figures
   through a private, key-controlled link at **`api.genbafms.com`**.

## 2. Permission requested

Install the **GENBA FMS Daily-Report Helper** — a small Windows application
delivered as a single installer — on **one (1) dedicated company computer**
located near where the daily report files are saved. The helper only watches
that one folder and sends each new file to our own central system.

## 3. Safety — no impact on existing company systems

| Concern | Reality |
|---|---|
| Does it change anything on the host computer or the network? | **No.** It only watches one folder and sends files out over an encrypted internet connection. It does not touch printers, ERP, file servers, the domain, or any other computer. |
| Special privileges needed? | Only for the one-time install. After that it runs as a normal user. |
| Where does it send data? | Only to our own central system at `*.genbafms.com`. Every connection carries an access key that we issue. |
| Who controls access? | We do. Each external company gets its own access key; we can switch it off or revoke any key instantly from the management page. |
| Can it be removed? | Yes — uninstall the application like any other Windows program; no trace remains on the host or its network. |
| Network impact? | Negligible — a few small daily file uploads (typically under 5 MB total per day). No incoming connections opened on the company computer. |
| Where is the data stored? | All data stays on **our own central system**. Only the limited figures we choose to share are reachable through the external link, and only by companies we issue a key to. |

## 4. Review access (for the directors)

> Please treat these credentials as confidential. They are issued **for this
> review only** and will be rotated/disabled by operations afterwards.

### 4a) Web Dashboard (live operations view)

| Item | Value |
|---|---|
| Address | **`https://link.genbafms.com/dashboard`** |
| Sign-in page | `https://link.genbafms.com/login` |
| Username | `director` |
| Password | `Director-caQFz57q` |

After sign-in you can browse: Dashboard · Reports · Gantt · Productivity
Summary · Today's Production Plan · 30-Day Productivity Trend.

### 4b) Management page (operations / on-off switches / audit)

| Item | Value |
|---|---|
| Address | **`https://link.genbafms.com/admin`** |
| Password | `GenbaAdmin-3GtPMicE` |

The management page shows: overall status · access history ·
**Daily-Report Helper** controls (turn it on/off, see what it is doing) ·
**External Data Link** (turn it on/off, list of partner companies, request
history, monthly usage quotas) · alerts · announcements.

### 4c) On-site upload page (used only on the local network)

Address (local network only): **`http://192.168.0.2/lan-upload`**
Used by operations to install a new version of the Helper without going
through the internet. Requires the management password above.

### 4d) Inter-company Data Link (for external partner companies)

| Item | Value |
|---|---|
| Address | **`https://api.genbafms.com/v1`** |
| Access key (for this review) | `pt_34TmLBJgkY_C6jin-L7MOx6puvEp06ybD6xfTQ` |
| One-page reference | `https://api.genbafms.com/v1/docs.md` |
| Interactive try-it page | `https://api.genbafms.com/v1/docs` |

The interactive page lets you paste the access key and click **Try it out**
to see live answers.

#### What an external company can look up (read-only)

| Information | Example address |
|---|---|
| Service health check | `/v1/ping` |
| List of available datasets | `/v1/datasets` |
| Daily production + section summary | `/v1/production?date=2026-05-19` |
| Labor-productivity trend (day / week / month / 3 months) | `/v1/productivity?range=month` |
| Per-item produced packs for a date | `/v1/packs?date=2026-05-19` |
| Per-employee attendance (name, in/out, hours) + totals | `/v1/attendance?date=2026-05-19` |

The link is **off by default**. Each partner has its own access key with a
per-minute rate limit and optional monthly quota. Any key can be revoked
instantly from the management page.

## 5. How to view a report — quick guide

### Daily Attendance Gantt (PDF)
1. Open `https://link.genbafms.com/gantt?date=2026-05-19`.
2. Press **PDF View** — a new tab opens with the printable page.
3. Press **Download PDF** — a saved file appears.
   Filename: `attendance_report_2026-05-19.pdf`. Both 製造１課 and 製造２課
   are included; rows are not split across page breaks.

### Productivity Summary (PDF)
1. Open `https://link.genbafms.com/summary?date=2026-05-19&report=1`.
2. Press **PDF View** → **Download PDF** → `summary_2026-05-19_r1.pdf`.

### Live Dashboard
- `https://link.genbafms.com/dashboard` shows:
  - Today's Packs (with a day-by-day bar chart)
  - 30-Day Labor Productivity Trend (with target lines: S1 85 / S2 35 / Combined 25)
  - Today's Production Plan (Line A / Line B, side by side)
  - 🌤 Weather (animated icon)
  - Three live KPI cards (Dept 1 / Dept 2 / Combined productivity)

### Trying the external data link
1. Open `https://api.genbafms.com/v1/docs`.
2. Press **Authorize**, paste the access key from §4d, press **Authorize** → **Close**.
3. Pick an endpoint (e.g. `/v1/production`) → **Try it out** → enter the date → **Execute** → see the answer.

## 6. What we ask the board to approve

- [ ] **Install the GENBA FMS Daily-Report Helper on one (1) company computer** in the production-report area.
- [ ] **Continue to operate** the central system at `genbafms.com` and the external link at `api.genbafms.com` as currently deployed.
- [ ] **Continue to issue access keys** to partner companies on a per-company basis, with the right to switch off or revoke any key at any time.

There is **no other change** requested. No domain controllers, file servers,
printers, ERP, or other computers are touched.

## 7. After the review — operations checklist

Operations will, after the board's decision:

- Change the management password.
- Disable or remove the `director` sign-in.
- Revoke the **Board Review** access key.
- Confirm the Daily-Report Helper is online again on its production computer.

## 8. Contact

GENBA FMS Operations · `support@asiakawaii.com` · response within 1 business day.

---

*End of submission. Approve / Decline / Request changes:*

Director name: ____________________   Signature: ____________________   Date: __________
