# Productivity Dashboard — Plan

Compact, responsive productivity panel added to the attendance app.
Labor productivity = `packs ÷ working_hours`, computed server-side.

## Layout changes
- **Processing Protection & Optimization** → move to top of page
- **Daily Attendance chart** → top-right slot
- **Gantt page** → make fully responsive (fluid tab bar, reflow rows <768px)

## Summary cards (row under header)
Four compact cards, single line:
- Total Packs
- Total Hours
- S1 Labor Productivity
- S2 Labor Productivity
- Combined Labor Productivity

Each card shows current value + Δ vs previous period.

## Tabs (after 製造２課)
Add a **Productivity** tab next to existing section tabs.
Content = the 4-chart grid below.

## Charts (2×2 grid, animated reveal)
1. Packs per day
2. LP — 製造１課 (S1)
3. LP — 製造２課 (S2)
4. LP — Combined

Behavior:
- Toggle lines: S1 / S2 / Combined (legend pills)
- Synced hover: crosshair + tooltip across all 4 charts
- Compare mode: overlay previous-period line (dashed)
- All charts animate in together on tab open

## Time range selector
Pill group: **Day · Week · Month · 3 Month**
Applies to all 4 charts + summary cards simultaneously.

## Backend — single endpoint
`GET /api/productivity?range=day|week|month|3month&end=YYYY-MM-DD`

Server handles all calculation (packs, hours, LP).
Response:
```json
{
  "range": "week",
  "current":  { "summary": {...}, "series": {"packs":[], "s1":[], "s2":[], "combined":[]} },
  "previous": { "summary": {...}, "series": {...} }
}
```

- `summary`: total_packs, total_hours, lp_s1, lp_s2, lp_combined
- `series`: aligned x-axis labels + per-metric arrays
- Packs source: TBD (new table or import) — stub with 0 until wired

**Touches:** [main.py](main.py)

## Export
- **PDF**: `window.print()` with print stylesheet (A4 landscape for dashboard)
- **CSV**: client-side dump of current response (`current` + `previous` flat rows)

Both buttons live in the Productivity tab header.

## UI rules
- Clean, compact, professional — match existing theme
- No new JS deps; reuse Chart.js if already loaded, else lightweight canvas
- All layout via CSS grid; mobile: stack cards & charts vertically
- Keep file count minimal: one `productivity.js` + one `productivity.css`

## Build order
1. Backend `/api/productivity` with mock packs data
2. Summary cards + time-range pills
3. 4-chart grid with sync hover + toggle
4. Compare-previous overlay
5. Export PDF/CSV
6. Responsive pass (Gantt + Productivity)
7. Layout reshuffle (Processing top, Daily Attendance top-right)
