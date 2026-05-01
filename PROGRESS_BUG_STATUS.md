# Progress & Bug Status — Attendance App
# 進捗・不具合対応状況 — 勤怠アプリ

**Date / 日付:** 2026-05-01

**Version / バージョン:** 3.4 (post-tag work on `dev`)

**Latest update / 最新更新 (2026-05-01 — Post-save navigation routes by entry point)**

The flow after saving a Daily Packs Excel batch now goes to a
different place depending on how the operator started the save:

1. If the operator clicked **Confirm & Save batch →** on the Daily
   Packs Excel tab directly, the page navigates to the **Reports**
   page with the production date pre-filled in the URL. This is
   the operator's normal end-of-shift workflow: finish Excel input,
   review the day's report.
2. If the operator clicked **⚡ Auto-update from Excel** on the
   フルキャスト tab, the page returns to the **フルキャスト tab**
   on the shift date (= production date − 1) and reloads the
   会社 / 人数 list so the just-saved buckets are immediately
   visible.

The Reports page also accepts `?date=YYYY-MM-DD` on its URL now,
so the report date is set automatically when the console redirects
in. The Daily Packs Manual Confirm & Save flow was updated to
carry the date forward in the same way.

Daily Packs Excel の Confirm & Save 後の遷移先を、ボタンの
起点に応じて切り替えるようにしました：

1. **Daily Packs タブ → Excel セグメント → Confirm & Save batch →**
   を直接押した場合 → **Reports ページ** に遷移し、URL に
   製造日が付与された状態で開きます（オペレーターの通常の
   勤務終了フロー）。
2. **2 フルキャスト タブ → ⚡ Auto-update from Excel** を押した場合
   → **フルキャストタブ** に戻り、シフト日（= 製造日 − 1）
   の 会社 / 人数 一覧を読み直します。直前に保存された行が
   そのまま確認できます。

Reports ページは URL の `?date=YYYY-MM-DD` を読み取り、レポート日付
を自動セットするようになりました。Daily Packs マニュアル入力の
Confirm & Save も同じく製造日を URL に渡します。

---

**Previous update / 前回の更新 (2026-05-01 — Management page gained a 🗑 Data Cleanup tab)**

A controlled way to remove a small number of bad days from the
database has been added to the Management page. Operators can pick
specific dates, see exactly how many rows in each table would be
removed, and then confirm the delete. Three safety rails are in
place to make sure this is never used as a "wipe everything" tool:

1. **Pick by specific dates only** — there is no "delete all" or
   "wipe table" mode. The operator types or picks the date(s) they
   want gone, one at a time. Selected dates appear as removable
   red chips so a typo can be undone before the preview.
2. **Maximum 5 dates per operation** — the UI counts `N / 5
   selected` and the server rejects anything beyond 5 with HTTP
   400. To clean a longer range, repeat the operation.
3. **Two-step confirm with a big red warning** — clicking Preview
   shows a per-table per-date row-count table, then a bilingual
   "destructive action / 取り消しできません" panel appears with a
   confirmation checkbox. The Delete button only enables once that
   box is ticked.

Once confirmed, the server deletes from `attendance_records`,
`daily_packs`, `daily_pack_items`, `temp_staff`, and
`production_plan` for the selected date(s) in a single transaction
and returns per-table counts so the operator can verify the action
landed correctly.

Management ページに「🗑 Data Cleanup · データ削除」タブを
追加しました。指定した日付だけのデータをデータベースから
削除できます。誤って全データを消してしまわないよう、
3 つの安全策を組み込んでいます：

1. **必ず日付を 1 件ずつ指定。** 「全削除」モードはありません。
   オペレーターが日付を入力／選択して追加する形式で、追加した
   日付は赤いチップで表示され、× ボタンで取り消せます。
2. **1 回の操作で最大 5 日付まで。** UI に `N / 5 selected` の
   カウンターがあり、サーバー側でも 5 件を超えた場合は HTTP
   400 で拒否します。長い期間をクリーンアップする場合は
   操作を分けて実行します。
3. **2 段階確認 + 大きな赤色警告。** プレビューを押すと
   テーブル × 日付 ごとの行数表と、バイリンガルの「取り消し
   できません」警告パネルが表示されます。同意チェックボックス
   を入れない限り削除ボタンは押せません。

確認後、サーバーは `attendance_records` / `daily_packs` /
`daily_pack_items` / `temp_staff` / `production_plan` の各テーブル
から指定日付の行を 1 トランザクションで削除し、テーブル別の
削除件数を返します。

---

**Previous update / 前回の更新 (2026-05-01 — フルキャスト start/leave times now read from the correct Excel cells)**

The auto-extracted フルキャスト rows now show the same start and
leave times that appear in the actual Excel workbook. The parser
was reading the wrong column for start time, which caused the
saved rows to use the production-plan default (19:20 → 10:00) for
every bucket and to mis-calculate the per-person hours.

For the 2026-04-19 file, the saved rows are now exactly:
- 5 名 · 19:00 → 翌 04:00 · 9 時間/人 · 合計 45 時間
- 3 名 · 19:00 → 翌 05:00 · 10 時間/人 · 合計 30 時間
- shift total = 75 時間 (was incorrectly 38 時間)

The Excel preview also shows the time window per bucket, so the
operator can verify the times match the workbook before saving.

人時生産性 シートの読み取り列を間違えていたため、自動取り込み
されたフルキャストの開始時刻・退勤時刻が、実際の Excel と
一致しない不具合を修正しました。

修正前は、開始時刻として「就業時間（duration）」列を読み取って
いたため、保存される行はすべて 製造予定表 の開始時刻
（19:20）と既定の退勤時刻（10:00）になり、1 人当たりの時間も
19 時間と誤計算されていました。

修正後、2026-04-19 のファイルから取り込まれる行は：
- 5 名 · 19:00 → 翌 04:00 · 9 時間/人 · 合計 45 時間
- 3 名 · 19:00 → 翌 05:00 · 10 時間/人 · 合計 30 時間
- このシフトの労働時間合計 = 75 時間（旧バグでは 38 時間）

Excel プレビューにも各行の時間帯が表示されるようになり、
保存前に Excel と一致しているか確認できます。

---

**Previous update / 前回の更新 (2026-05-01 — フルキャスト date keying corrected + Skip / Auto-update buttons on manual tab)**

The relationship between the four daily dates that the operator works
with has been locked in across the app, fixing a real bug introduced
in the morning's Excel import work and adding two convenience buttons
on the manual フルキャスト tab:

1. **The four daily dates now line up the same way everywhere:**
   - Report date = Daily Packs day = Excel production date.
   - Report date = attendance PDF upload date + 1 day.
   - **フルキャスト 手動入力 shift date = production date − 1.**
   - フルキャスト 手動入力 shift date = attendance PDF upload date.
2. **Bug fix.** The Excel-import flow was saving フルキャスト rows
   under the production date — but the manual fullcast tab and the
   gantt overlay both look up by shift date (= production date − 1).
   The auto-extracted rows were landing on the wrong day and weren't
   visible. Fix: the save endpoint now writes
   `temp_staff.record_date = production_date − 1`, returns
   `shift_date` in the response, and the post-save navigation
   opens the manual tab on the correct day.
3. **Two new buttons on the manual フルキャスト tab:**
   - **⚡ Auto-update from Excel** — runs the same Daily Packs
     Excel auto-extract + save flow without leaving the fullcast
     tab. Internally it switches to the Excel segment, clicks
     Auto-update, waits for the parse to complete, clicks Save.
     The save then navigates back to the fullcast tab with the
     shift date pre-loaded and the rows visible.
   - **Skip →** — operator confirms there are no フルキャスト
     for this shift and jumps to Daily Packs. No DB writes.

The four-way date relationship has been added to the memory file so
future sessions don't reintroduce the same off-by-one date bug.

オペレーターが日々扱う 4 つの日付の関係を、アプリ全体で
統一しました。午前中の Excel 取り込み作業で混入したバグを
修正し、フルキャスト手動入力タブに便利なボタンを 2 つ
追加しています：

1. **4 つの日付の関係を全画面で統一：**
   - レポート日付 = Daily Packs 日 = Excel の製造日。
   - レポート日付 = 勤怠 PDF アップロード日 + 1 日。
   - **フルキャスト 手動入力 シフト日 = 製造日 − 1 日。**
   - フルキャスト 手動入力 シフト日 = 勤怠 PDF アップロード日。
2. **バグ修正。** Excel 取り込みのフローで、フルキャスト 行を
   製造日に保存してしまっていました。しかし、手動フルキャスト
   タブとガント表示の両方は シフト日（= 製造日 − 1）で参照
   するため、自動取り込みされた行が間違った日に保存され
   表示されない問題が発生していました。修正後は
   `temp_staff.record_date = 製造日 − 1` で保存し、レスポンス
   に `shift_date` を含めて、保存後の遷移先も正しい日付に
   なります。
3. **手動フルキャストタブに新ボタン 2 つ：**
   - **⚡ Auto-update from Excel** — フルキャストタブから離れず
     に、Daily Packs Excel の自動取り込み・保存フローを 1
     クリックで実行します。内部では Excel セグメントへの
     切替・Auto-update・解析完了待機・Save を順に実行し、
     保存後は正しいシフト日のフルキャストタブに戻ります。
   - **Skip →** — このシフトには フルキャスト がいないと
     確認したオペレーター用。Daily Packs タブに直接遷移し、
     データベースには何も書きません。

4 日付の関係はメモリファイル `project_date_rules.md` にも保存
しました。今後のセッションで同じ off-by-one バグが再発しない
ようにしています。

---

**Previous update / 前回の更新 (2026-05-01 — Daily-packs Excel preview cleanup + smarter start time + post-save navigation)**

Five small but operationally important changes to the Daily Packs
Excel flow, all driven by the operator's actual usage:

1. **Excel preview is leaner.** The Input by, Weather / Temp, and
   Total quantity fields were removed — they were either redundant
   (the values vary per product so a single "total quantity" was
   misleading) or never read by anyone. The preview now shows only
   Production date · Start time · End time · Products count.
2. **Cross-check pill no longer false-alarms.** Previously it
   warned `⚠ per-product sum 0 ≠ 13,168` whenever the per-product
   全合計 column was blank (which is most files). Now it compares
   per-product N+Y against the right-side 合計 with a small
   tolerance and stays silent when the per-product side is empty.
3. **Start time is consistently 19:20.** The parser used to take
   the first A-line item start, but the workbook flips which line
   carries early-prep vs main production between months. The new
   rule picks the latest first-item start across A / B / C —
   that's always the canonical night-shift start (19:20) regardless
   of which line is carrying it.
4. **End time has a +30 minute buffer.** Per operator request, the
   predicted end time now includes a 30-minute buffer, and the
   label reads "End time (+30 min buffer)" so the buffer is
   explicit. The avg-p/h calculation still uses the unbuffered run
   length to stay accurate.
5. **Workflow lands on the フルキャスト tab.** After a successful
   Excel save, the console now switches to the manual fullcast tab
   with the date pre-loaded, so the operator can immediately see
   the just-saved 会社 / 人数 rows in the existing list UI and
   confirm or edit them without retyping.

実機の使い方に合わせて、Daily Packs の Excel 取り込み画面を
5 か所、実用上重要なポイントで改善しました：

1. **プレビュー画面をスリム化。** Input by、Weather / Temp、
   Total quantity の 3 項目を削除しました（商品ごとに値が
   異なるため「合計数量」を 1 つだけ表示するのは誤解を招き、
   他の 2 項目も実際には参照されていませんでした）。プレビュー
   は Production date / Start time / End time / Products count の
   運用上必要な情報だけを表示します。
2. **クロスチェック表示の誤警告をなくしました。** 以前は商品別
   全合計列が空白の月（ほとんどの月）で
   `⚠ per-product sum 0 ≠ 13,168` という警告が出ていました。
   新しいロジックは、商品別 N+Y 合計を右側の合計と比較し、
   0.5% 以内のずれは許容、商品別側が空の場合は表示しません。
3. **開始時刻が常に 19:20 に。** 以前は Aライン先頭の開始時刻を
   採用していましたが、月によって Aライン と Bライン の役割が
   入れ替わります。新しいルールでは A / B / C の中で「最も遅い
   先頭開始時刻」を採用するので、どちらのラインが本番でも
   常に夜勤の正しい開始時刻 (19:20) になります。
4. **End time に +30 分バッファ。** オペレーターのご要望通り、
   予測終了時刻に 30 分のバッファを追加しました。ラベルも
   「End time (+30 min buffer)」と明示。平均 p/h の計算は
   バッファ無しの実稼働時間を使うので、平均値の精度は保たれます。
5. **保存後はフルキャストタブに自動遷移。** Excel の保存が成功
   すると、フルキャストタブに切り替わり、その Excel の製造日
   を `fcDate` に設定して `loadFcFromDb()` で会社 / 人数 一覧
   を読み込みます。保存された行を既存のリスト UI で確認・修正
   でき、再入力は不要です。

---

**Previous update / 前回の更新 (2026-05-01 — Daily-packs Excel: section totals, フルキャスト, A/B/C plan all parsed and saved)**

The daily-packs Excel pipeline now reads three more pieces from the
real 夜勤用日報 workbook and persists them all to the database in
one transaction:

1. **Section totals (Ｎ合計 / Ｙ合計 / 合計).** The right-side total
   columns on 入力画面 are now picked up automatically. The Daily
   Packs Excel preview shows them as a single strip with a
   cross-check pill that compares against the per-product sum so any
   discrepancy is obvious. The operator-confirmed Ｎ合計+Ｙ合計 is
   now the authoritative pack count for the day — this fixes the
   case (verified on 2026-04-29) where per-product 全合計 was blank
   and the day was saved with 0 packs.
2. **フルキャスト auto-fill.** The 8 名 / 1 名 entries on the
   人時生産性 sheet are now read directly into the preview as a
   summary line (`8 名 + 1 名 = 9 名 · 27.0h total`). They save into
   `temp_staff` automatically when the operator clicks Save. A skip
   checkbox is provided next to the summary — when ticked, the save
   leaves any existing `temp_staff` rows alone.
3. **A/B/C production plan.** 製造予定表 ＮＹ is parsed into three
   colour-coded preview cards (Aライン blue, Bライン green, Cライン
   orange) with a compact `item · planned · N · Y · start` table.
   The first A-line item's start time becomes the Section 2
   start-time pill. Everything is saved to a new `production_plan`
   table, one row per item per date, queryable via
   `GET /api/production-plan/<date>`.

データベース側では `daily_packs` に `n_total` / `y_total` /
`section_start_time` の 3 列を追加し、新しい `production_plan`
テーブルでライン別アイテム別に保存しています。

Daily Packs の Excel 取り込みで、現場の 夜勤用日報 ファイルから
さらに 3 つの情報を自動で読み取り、ワンクリックでまとめて
データベースに保存できるようにしました：

1. **課別合計 (Ｎ合計 / Ｙ合計 / 合計)。** 入力画面 の右側の合計
   列を自動で取得します。Daily Packs Excel プレビューに 1 行
   ストリップで表示し、商品別の合計と一致するかを ✓ / ⚠ ピル
   でクロスチェックします。確認済みの Ｎ合計+Ｙ合計 がその日の
   正式な合計パック数になります。これにより、商品別 全合計 が
   空欄のため 1 日が 0 パックで保存されてしまう不具合（2026-04-29
   の実機ファイルで確認）が解消されます。
2. **フルキャストの自動入力。** 人時生産性 シートの 8 名 / 1 名
   の行をプレビューに自動表示します
   （`8 名 + 1 名 = 9 名 · 27.0h 合計` のような形式）。Save 時に
   `temp_staff` テーブルへ自動保存します。サマリー横の Skip
   チェックボックスを ON にすると、既存の `temp_staff` 行は
   触らずにスキップできます。
3. **A/B/C ラインの製造予定。** 製造予定表 ＮＹ を 3 枚の色分け
   プレビューカード（Aライン 青 / Bライン 緑 / Cライン 橙）に
   解析し、`アイテム · 予定 · N · Y · 開始時刻` の小テーブル
   を表示します。Aライン先頭アイテムの開始時刻がそのまま
   製造2課のスタートタイムになります。データは新しい
   `production_plan` テーブルに保存され、
   `GET /api/production-plan/<date>` で取り出せます。

---

**Previous update / 前回の更新 (2026-04-30 — v3.4: two-flow Auto-update + bat dispatch fix)**

The desktop / CMD upload flow was split into two clearly-separate
pipelines so an operator can push the daily PDFs and the daily-packs
Excel file independently, without one accidentally triggering the
other:

1. **Two server endpoints, two destinations.** Attendance PDFs still
   go to `POST /api/v1/pdf/upload` and land in
   `auto_uploads/attendance/`. The new
   `POST /api/v1/xlsx/upload` accepts daily-packs `.xlsx` files and
   lands them in `auto_uploads/daily_packs/`. Each upload is
   followed by its own auto-update endpoint —
   `/api/v1/pdf/auto-upload?save=true` for attendance,
   `/api/daily-packs/auto-extract-excel` for the daily-packs Excel.
2. **`upload_latest.bat` rewritten with two subroutines.** Now has
   `:upload_pdf` and `:upload_xlsx` as clearly-labelled functions,
   plus a CLI mode argument: `upload_latest.bat pdf | xlsx | all`.
   The watched folders are separated (`.\watch\pdf\` and
   `.\watch\xlsx\`) so the two file types can never collide. The
   previous version had a CMD-syntax bug where `goto :done` ran
   unconditionally after the first conditional check — that's been
   fixed by wrapping each branch in parentheses.
3. **Electron IPC handler updated in the API guide.** The desktop
   client now exposes three distinct `kind` values for Auto-update
   (`attendance` / `daily_packs_pdf` / `daily_packs_xlsx`) plus
   two upload helpers (`window.desktop.uploadPdf`,
   `window.desktop.uploadXlsx`) so renderer code stays clean.

This fixes the symptom where running the Excel command from CMD
returned an attendance auto-update response — the old `.bat`
dispatch silently fell through to the wrong flow.

デスクトップ / CMD のアップロードフローを 2 系統に明確に
分離しました。日次の PDF とフルキャスト Excel を、互いに
干渉せずに独立して送信できます：

1. **サーバー側エンドポイントを 2 系統に。** 勤怠 PDF は
   従来通り `POST /api/v1/pdf/upload` でアップロードし、
   `auto_uploads/attendance/` に配置されます。新規追加した
   `POST /api/v1/xlsx/upload` はフルキャスト Excel
   (.xlsx / .xlsm) を受け取り、`auto_uploads/daily_packs/` に
   配置します。アップロードに続けて、それぞれ専用の自動更新
   エンドポイント（勤怠 = `/api/v1/pdf/auto-upload?save=true`、
   Excel = `/api/daily-packs/auto-extract-excel`）を呼び出します。
2. **`upload_latest.bat` を 2 つのサブルーチンに書き直し。**
   `:upload_pdf` と `:upload_xlsx` というラベル付きの関数に分け、
   CLI 引数 `upload_latest.bat pdf | xlsx | all` で実行する
   フローを選べます（既定値は `all`）。ウォッチフォルダーも
   `.\watch\pdf\` / `.\watch\xlsx\` に分離し、ファイルタイプの
   混在を防ぎます。旧版にあった CMD 構文の不具合（`goto :done`
   が if 判定後に無条件で実行されてしまう問題）は、各分岐を
   括弧で囲むことで修正しました。
3. **API ガイドの Electron IPC ハンドラーを更新。** デスクトップ
   クライアントから 3 種類の Auto-update（`attendance` /
   `daily_packs_pdf` / `daily_packs_xlsx`）と、2 種類のアップ
   ロードヘルパー（`window.desktop.uploadPdf` /
   `window.desktop.uploadXlsx`）を明示的に呼び出せるように
   しました。

これで、CMD から Excel の自動更新を実行したときに勤怠用の
レスポンスが返ってきていた症状（旧 .bat の分岐が誤って
別フローに合流していた問題）が解消されます。

---

**Previous update / 前回の更新 (2026-04-30 — Day-off: section tabs, 21–20 cycle, efficiency rows, unauthorized-absence highlight)**

The Day-off Schedule tab and the daily gantt now work together so an
operator can plan, see, and audit absences in one flow:

1. **Section sub-tabs.** The Day-off grid is split into 製造1課 and
   製造2課 tabs, defaulting to 製造2課 (the larger roster). Each
   tab's grid + summary counts now show only that section's people,
   so the screen is no longer crowded with the other section's rows.
2. **21-to-20 fiscal-month cycle.** A new "This cycle (21–20)" preset
   snaps the date range to the office's 21st-to-20th month boundary
   (matches the existing 定休表 Excel format). The cycle label
   (e.g., "2026-05 cycle (4/21–5/20)") is displayed next to the
   sub-tabs. The standard calendar-month preset is kept too.
3. **Efficiency rows on top.** Three new rows above the editable
   cells now show per-day **人時 (P/h)**, **前日比 (▲/▼ vs previous
   day in %)**, and **対目標 (▲/▼ vs target P/h in %)** for the
   currently selected section, so the operator can spot whether a
   heavy-leave day correlates with a productivity dip. Up arrows
   render green, down arrows red, near-zero deltas gray.
4. **Highlight unauthorized absence.** A toggle next to the Save
   button — once turned on, every gantt view (desktop, mobile, the
   popup window from Reports) marks absent employees whose absence
   is **not** in the saved day-off list as a red **🚨 Unauthorized**
   row. Absences that **are** in the list always render as a calm
   green **休 scheduled** pill regardless of the toggle, so the
   distinction is always visible.

Day-off Schedule タブと日次ガントを連動させ、計画・確認・監査
を 1 つの流れで行えるようにしました：

1. **課のサブタブ。** Day-off グリッドを 製造1課 / 製造2課 の
   サブタブに分け、初期表示は 製造2課（人数の多い方）にしました。
   各タブではその課の従業員だけを表示し、画面が混雑しません。
2. **21–20 のサイクル。** 「This cycle (21–20)」ボタンで日付範囲
   を会社の 21 日〜翌月 20 日のサイクルに合わせます（既存の
   定休表 Excel と一致）。サブタブの右側にサイクル名
   （例：2026-05 cycle (4/21–5/20)）を表示しています。従来の
   「Calendar month」プリセットも残してあります。
3. **上部の効率行。** 編集可能なセルの上に 3 行が並びます：
   各日の **人時 (P/h)**、**前日比（前日と比べての ▲/▼ と %）**、
   **対目標（目標 P/h と比べての ▲/▼ と %）**。選択中の課の値
   を表示し、休みの多い日と生産性の落ち込みが連動しているかを
   一目で見られます。上向きは緑、下向きは赤、変化が小さい場合
   はグレーです。
4. **不在の警告ハイライト。** Save ボタンの隣にトグルがあり、
   ON にすると、登録済みの休み予定にない欠勤を **🚨 Unauthorized**
   として赤色で表示します（デスクトップ・モバイル・Reports
   からのポップアップすべて）。休み予定に登録されている欠勤は
   トグルの状態に関わらず常に **休 scheduled** の緑色ピル
   で表示されるため、両者の区別が常に明確になります。

---

**Previous update / 前回の更新 (2026-04-30 — Day-off Schedule: import 定休表 Excel + daily totals strip)**

The Day-off Schedule tab gained two big things so existing 定休表 data
can be brought in once and the operator can see at a glance how the
month is shaping up:

1. **Import from 定休表 Excel.** A new button on the Day-off toolbar
   uploads the yearly 定休表 spreadsheet. The server parses every
   monthly sheet, picks each "off person" name out of the role
   columns, and tries to match each name against the attendance
   roster. Names in the Excel are short forms (just a surname or a
   katakana nickname) so a mapping wizard appears: each unmatched
   nickname shows in a table with a dropdown of likely roster
   employees. Confirm the matches, click Apply, and the system
   stores the off-day entries against each matched employee. The
   wizard also remembers the nickname → employee_code mappings, so
   re-importing the file next time auto-resolves them.
2. **Daily totals at the top of the grid.** Three rows now sit
   above the editable cells: **出勤 / Present**, **休 / Off** and
   **休率 / Off %**. Each column shows the count for that date, with
   the off-rate cells gently colour-graded (amber ≥15 %, red
   ≥30 %) so a heavy-leave day is obvious. A separate strip above
   the grid shows the totals across the visible window — roster
   size, days in view, total off-cells, average off per day, and
   average off-rate. All numbers update live as cells are toggled,
   without needing to save first.

The first end-to-end test against the real
"2026年度（2.21～6.20）定休表.xlsx" parsed cleanly: 8 monthly sheets,
2,238 off-cells across 2026-02-21 → 2026-06-20, 77 distinct
nicknames. About 9 of those auto-suggested a single roster
candidate; the remaining ~68 names are office / admin / contract
staff that aren't in the production attendance roster, so the
mapping UI lets the operator skip them in one click.

Day-off Schedule タブに 2 つの大きな機能を追加し、既存の
「定休表」を取り込みつつ、月の状況を一目で把握できるように
しました：

1. **定休表 Excel のインポート。** Day-off ツールバーに新しい
   ボタンを追加し、年間の定休表 (.xlsx) をアップロードします。
   サーバーは各月シートを解析し、役職列から「休みの人」の
   名前を抽出し、勤怠名簿と自動でマッチングします。Excel の
   名前は苗字だけ・愛称だけなどの短い形式が多いため、未マッチの
   名前を一覧表示し、各行のドロップダウンから候補を選ぶ
   ウィザード形式にしました。確認後 Apply を押すと、各社員に
   休み日が登録されます。愛称→社員コードのマッピングは保存
   されるため、次回以降の再インポートでは自動で解決されます。
2. **グリッド上部の日別集計。** データ行の上に
   **出勤 / Present**、**休 / Off**、**休率 / Off %** の 3 行が
   並びます。各日付列に件数が表示され、休率セルは穏やかに
   色分けされます（15 % 以上で琥珀、30 % 以上で赤）。グリッド
   上のサマリーバーには表示中の期間内の合計（名簿サイズ、表示
   日数、合計休日セル数、1 日あたりの平均休日、平均休率）が
   表示されます。すべてセルを切り替えるたびにリアルタイムで
   更新され、保存前でも反映されます。

実ファイル「2026年度（2.21～6.20）定休表.xlsx」での実機
テスト：8 つの月シートが正常に解析され、2026-02-21 ～
2026-06-20 で 2,238 件の休みセル、77 個の異なる愛称を確認。
うち 9 件は 1 候補に自動絞り込み、残り約 68 件は事務 / 管理
/ 契約スタッフで勤怠名簿に存在しないため、ウィザードで
ワンクリック「skip」できるようにしています。

---

**Previous update / 前回の更新 (2026-04-30 — Management has 3 clean tabs: Roster / Day-off / LINE)**

The Management page is now organised into three clear tabs so all
operator data lives in one place:

1. **📋 Roster · 名簿管理** — the existing employee management board
   (drag-and-drop section assignment, manual add, PDF import, search).
   Unchanged in behaviour, just wrapped into its own tab.
2. **📅 Day-off Schedule · 休暇予定表** — a new grid for marking
   planned days off (vacation, fixed off-days, AL, etc.). Employees
   are listed down the side, dates run across the top with weekday
   labels. Tap any cell to toggle that person's day off; weekend
   columns are tinted so they stand out at a glance. The toolbar
   has date-range pickers and quick presets ("This month", "Next 30
   days"), a status pill, and Save / Reset buttons that activate
   only when there are unsaved changes. The schedule persists in
   `dayoff_schedule.json` on the server.
3. **💬 LINE Recipients · LINE 通知先** — moved here from the
   Reports page. Each registered user/group is shown as a row with
   their display name, kind (user/group/room), userId, registration
   date, and inline ✎ rename + ✕ remove buttons. There's a Send Hi
   test button so an operator can verify the bot is reaching the
   right people without sending a real report.

The Reports page was simplified: the "LINE bot" card disappears
and is replaced by a small pointer to Management → LINE Recipients.

Management ページを 3 つのタブに整理し、運用に必要な情報を
1 か所にまとめました：

1. **📋 Roster · 名簿管理** — 既存の社員管理画面（ドラッグ＆ドロップ
   による課の割当、手動追加、PDF 取り込み、検索）。動作は変えず、
   タブの中に収めただけです。
2. **📅 Day-off Schedule · 休暇予定表** — 新規の休暇登録グリッド
   です。縦に従業員、横に日付（曜日付き）が並び、セルをタップする
   だけでその人の休みを ON/OFF できます。土日列は赤味掛かった色で
   一目で分かるようにしています。ツールバーには From / To の
   日付ピッカー、「今月」「次の 30 日」のクイックプリセット、
   保存状態のピル、未保存の変更があるときだけ有効になる Save /
   Reset ボタンがあります。データはサーバー側の
   `dayoff_schedule.json` に保存されます。
3. **💬 LINE Recipients · LINE 通知先** — Reports ページから
   こちらに移動しました。各登録先は表示名・種別（user/group/room）
   ・userId・登録日が並び、行ごとに ✎ 名称変更と ✕ 削除のボタン
   があります。Send Hi テストボタンで bot が届いているかを
   実レポート無しで確認できます。

Reports ページは「LINE bot」カードを削除し、Management →
LINE Recipients への小さなリンクだけ残しました。

---

**Previous update / 前回の更新 (2026-04-30 — Unified header on every page)**

The top header is now the same on every page in the console. We
made three operator-visible changes:

1. **Single shared header.** Console, Dashboard, Gantt, Summary,
   Reports and Management all use one common header file. The
   header has the title on the left, the navigation tabs in the
   middle (with the green Dashboard tab first), the API status
   pill, and the live clock with computed Shift / Prod dates on
   the right. Edit the header once and all pages update at the
   same time.
2. **Reports opens in the same window.** The previous behaviour of
   opening Reports as a separate browser window was removed.
   Clicking the Reports tab now navigates in the current window
   like the other tabs. (The "Open Report" buttons inside the
   Reports launcher still open a popup window for each individual
   report — that part is unchanged.)
3. **Grafana link removed from the top nav.** Grafana is still
   reachable directly at `/grafana/`, but the link is no longer
   in the in-app navigation so the tab bar stays focused on the
   attendance/productivity workflow.

トップヘッダーを全ページで完全に統一しました。
オペレーターから見える変更は次の 3 点です：

1. **共通ヘッダー。** Console / Dashboard / Gantt / Summary /
   Reports / Management のすべてのページが同じヘッダーを使い
   ます。左にタイトル、中央にナビゲーションタブ（緑色の
   Dashboard を先頭）、API 稼働ピル、右側にライブ時計と
   シフト日 / 生産日の表示。1 ヶ所の修正で全ページが一斉に
   更新されます。
2. **Reports は同じウィンドウで開く。** Reports タブを別
   ウィンドウで開く動作をやめました。他のタブと同じく現在
   のウィンドウ内で遷移します（Reports ランチャーの中の
   各「報告書を開く」ボタンは引き続き別ウィンドウで開きます。
   そこは変更ありません）。
3. **Grafana リンクをトップナビから削除。** Grafana は引き続き
   `/grafana/` で直接アクセス可能ですが、タブバーから外して
   勤怠 / 生産性ワークフローに集中できるようにしました。

---

**Previous update / 前回の更新 (2026-04-30 — Toolbar refactor: green Dashboard tab + Reports as popup launcher)**

The navigation across the console was tightened up so the layout is
ready for a future live-operations dashboard, and the Reports flow
was changed so each report opens in its own window:

1. **🌐 Dashboard tab.** A new green-filled "Dashboard" tab now shows
   as the first item on every page (Console, Gantt, Summary, Reports,
   Management). The page itself is intentionally empty for now, with
   an "Under development" message and links to the existing pages.
   This is a placeholder so the nav layout is final and the real
   dashboard content can drop in later without another reshuffle.
2. **Reports = launcher.** The Reports page is now read-only. It has
   one button per report — **📂 Open Report ↗** — that opens the
   actual report in a separate window. Inside that window the user
   uses the existing **🖨 Print** and **💬 Send to LINE** buttons.
   The duplicate Send buttons that used to live on the Reports
   launcher have been removed.
3. **Summary's popup window** now has a **Send to LINE** button next
   to Print, so when an operator opens the Summary report from the
   Reports launcher, they can both print and send LINE messages
   without going back to the launcher.

The legacy `Dashboard ↗` link that pointed to Grafana has been renamed
to `Grafana ↗` so the new green Dashboard tab is unambiguous.

新しいライブ運用ダッシュボードを将来追加する準備として
コンソール全体のナビゲーションを整理し、Reports からは各
報告書が別ウィンドウで開くように変更しました：

1. **🌐 Dashboard タブ。** 緑色の「Dashboard」タブを各ページ
   （Console / Gantt / Summary / Reports / Management）の
   先頭に追加しました。ページ自体は意図的に空で、
   「開発中」メッセージと既存ページへのリンクのみです。
   レイアウトを先に確定させ、後から実コンテンツを差し込めるよう
   にするための土台です。
2. **Reports = ランチャー。** Reports ページは読み取り専用に
   なりました。各報告書には **📂 Open Report ↗** ボタンが
   1 つだけあり、報告書本体は別ウィンドウで開きます。その
   ウィンドウ内の **🖨 Print** と **💬 Send to LINE** ボタン
   で印刷・LINE 送信を行います。ランチャー側にあった重複の
   Send ボタンは削除しました。
3. **Summary の別ウィンドウ** にも、Print の隣に
   **Send to LINE** ボタンを追加しました。Reports ランチャー
   から Summary を開いた担当者は、ウィンドウを戻らずに印刷も
   LINE 送信もできます。

旧来の Grafana を指していた `Dashboard ↗` リンクは
`Grafana ↗` に名前を変更し、新しい緑の Dashboard タブと
混同しないようにしました。

---

**Previous update / 前回の更新 (2026-04-30 — LINE flow polished: smart card + mobile viewer + recipient management)**

The LINE pipeline that we built earlier today was tightened up so it
feels finished. Three things changed:

1. **One smart card instead of two messages.** Tapping **Send to LINE**
   now delivers a single styled card in chat: the snapshot image at
   the top, the report title and date in the middle, and a clear
   tap button at the bottom. Tapping anywhere on the card opens the
   mobile viewer — no raw URL clutter.
2. **Two mobile viewer pages.** `/m/report` shows the same gantt as
   the desktop page, just without admin buttons; `/m/summary` shows
   the same productivity chart. The summary page now defaults to a
   Month range with all four series visible, and tapping the chart
   makes it rotate fullscreen so the recipient can read it sideways
   on a phone with a close button to come back.
3. **Recipient management.** The Reports page **List recipients**
   button now shows each subscriber as a row with their current name,
   plus pencil and ✕ buttons to rename or remove them in one click.
   The first registered phone has been renamed to `creator`.

午前中に組み上げた LINE 連携を、仕上がりの状態まで整えました。
変更点は次の 3 つです：

1. **メッセージ 2 通 → スマートカード 1 通に。** **Send to LINE**
   をタップすると、画像・件名・日付・タップボタンが一体になった
   1 通のカードがチャットに届きます。カードのどこをタップしても
   モバイル用の表示ページが開きます。生 URL は表示されません。
2. **モバイル用の 2 ページ。** `/m/report` はデスクトップ版と同じ
   ガント表示、`/m/summary` は同じ生産性チャートを、管理ボタン
   抜きで表示します。サマリーは初期表示が Month、4 系列すべて
   ON。チャートをタップすると全画面で 90° 回転し、横向きで
   読みやすく、閉じるボタンで戻れます。
3. **受信者の管理。** Reports ページの **List recipients** に
   1 名ずつ行が並び、鉛筆ボタンで名前変更、✕ ボタンで削除が
   できるようになりました。最初に登録された端末は名前を
   `creator` に設定済みです。

---

**Previous update / 前回の更新 (2026-04-30 — LINE messaging integrated into the console)**

The attendance console can now talk to LINE. Three things changed for
the operator:

1. On the **Reports page** there is a new **Send to LINE** button next
   to each report, plus a small **LINE bot** card at the bottom with
   a **Send Hi (test)** button and a **List recipients** button so
   you can see who is currently subscribed to receive reports.
2. On the **Gantt page** the toolbar now has a **Send PDF to LINE**
   button. Click it and the same PDF you would normally print is
   created right there in the browser, uploaded to the server, and a
   tap-to-open link is sent to every registered LINE recipient.
3. To register, the recipient just adds the bot as a friend on LINE
   and sends any message. The bot replies with a short confirmation
   and remembers them. From that moment they will receive every
   report that someone sends from the console.

The first test phone (+81 80-6402-2774) is already registered and
received the test "Hi 👋" successfully.

勤怠コンソールから LINE にメッセージを送れるようになりました。
オペレーター視点での変更は次の 3 点です：

1. **Reports ページ** に、各レポートの横に **Send to LINE**
   ボタンが追加されました。ページ下部には新しい **LINE bot** カード
   があり、**Send Hi (test)** ボタンと **List recipients** ボタンで
   現在登録されている送信先一覧を確認できます。
2. **Gantt ページ** のツールバーに **Send PDF to LINE** ボタンが
   追加されました。普段印刷するのと同じ PDF をブラウザ内で生成し、
   サーバーにアップロードし、登録済みの LINE 受信者全員にタップで
   開けるリンクを送信します。
3. 受信者は LINE で bot を友だち追加し、何かメッセージを 1 回
   送るだけで登録されます。bot が短い確認返信をしてその ID を
   記録します。その後はコンソールから送られるすべてのレポートを
   受け取れます。

最初のテスト用端末（+81 80-6402-2774）はすでに登録済みで、
テストの「Hi 👋」も問題なく届きました。

---

**Previous update / 前回の更新 (2026-04-28 — Member Hours: gantt-style daily strips + per-day p/h)**

The Member Hours tab on the Gantt page was reshaped so several
people can be compared at the same time slot, top to bottom:

1. The **Hours per day** line chart at the top of the result panel
   was removed.
2. The **Daily strip** is now drawn the same way as the 製造１課 /
   製造２課 gantt rows. Each selected member gets a coloured header
   bar (their name and total hours), the same 10:00 → 08:30 timeline,
   and one row per day in the picked range. The bar inside each row
   shows IN, the worked hours, and OUT.
3. The right-hand side of every day row shows that day's worked
   hours and the section's **per-hour packs (p/h)** for that date.
4. The compare range is **capped at 3 months (92 days)** so the new
   per-day aggregation stays fast; longer ranges are rejected with
   a clear message.
5. The **Totals** card now summarises each picked member with their
   earliest / latest IN, earliest / latest OUT, longest day, and the
   best p/h they were present for during the selected window.

Gantt の Member Hours タブを、複数の作業員を同じ時間軸で
上下に並べて比較できるよう作り直しました：

1. 上部にあった **Hours per day** の折れ線グラフを削除しました。
2. **Daily strip** を製造１課 / 製造２課のガントと同じ見た目に
   揃えました。選んだ作業員ごとに色付きヘッダーバーが表示され
   （氏名と合計時間）、10:00 〜 翌 08:30 の同じ時間軸の上に、
   範囲内の各日付が 1 行ずつ並びます。各バーには IN・勤務時間・
   OUT が入ります。
3. 各日付の行の右側に、その日の勤務時間と、所属課のその日の
   **人時生産性 (p/h)** を表示します。
4. 比較の期間は **最大 3 ヶ月（92 日）** に制限しました。新しい
   集計を高速に保つためで、超えるとメッセージで拒否します。
5. **Totals** カードは作業員ごとに、最早 IN / 最遅 IN / 最早 OUT /
   最遅 OUT / 最長勤務 / 期間中の最高 p/h を要約します。

---

**Earlier update / 以前の更新 (2026-04-28 — Gantt cleanup + multi-Excel upload)**

Three small adjustments:

1. The red **midnight 00:00 vertical line** was removed from every
   employee row in the Gantt chart. The axis tick label stays.
2. The dashed **green start** / **amber predicted-end** lines (added
   earlier) now appear only on the **製造２課** rows, since 製造１課 is
   not on the daily packs production line. The pack-time legend
   above the axis follows the same rule — only shown on 製造２課.
3. The **Daily Packs → Upload Excel** tab now accepts **multiple
   files at once**. Drop or select several `.xlsx` files and the page
   parses each one in sequence, shows a queue table (file / date /
   products / total quantity / start → end / status). The detailed
   preview at the bottom shows the first parsed file; clicking
   **Confirm & Save all batches (N) →** saves all of them as separate
   per-day batches and the page jumps to Manual entry on the last
   saved date. Single-file uploads and the Auto-update button keep
   their original behavior unchanged.

3 つの調整：

1. Gantt 各行の赤い **0 時の縦ライン** を削除しました（軸の目盛り
   ラベルはそのまま）。
2. 緑（製造開始）と琥珀（予測終了）の破線縦ラインは **製造２課**
   の行にのみ表示するように変更しました（製造１課は包装ラインを
   稼働していないため）。軸上の凡例も製造２課でのみ表示します。
3. Daily Packs → Upload Excel で **複数ファイル同時アップロード** に
   対応しました。`.xlsx` を一度に複数選択／ドロップすると、各ファイルを
   順番に解析し、ファイル名・製造日・商品数・合計個数・Start → End・
   状態をキュー表で表示します。詳細プレビューは最初に解析できた
   ファイルを表示し、**Confirm & Save all batches (N) →** ボタンで
   それぞれの日付ごとに別バッチとしてまとめて保存します。保存後は
   最後に保存できた日付で Manual entry タブに切り替わります。1 ファイル
   のときと Auto-update ボタンの動作は従来どおりです。

---

**Earlier today / 同日（先ほど）の更新 (Note provenance + next-step + Gantt pack lines)**
Three small but useful refinements:

1. The Daily Packs **Note** field now records *how* each day's count was
   entered. Manual entries are tagged `[manual]`, PDF uploads `[pdf]`,
   PDF Auto-update `[pdf-auto]`, Excel uploads `[excel]`, and Excel
   Auto-update `[excel-auto]`. The filename is appended for the file
   flows. The Note input now has a hint line explaining this so the tag
   doesn't look mysterious.

2. Clicking **Confirm & Save batch →** on the Excel segment now
   advances to the next step automatically: it switches to the
   Manual entry segment with the production date pre-loaded, so the
   operator sees the saved row and its `[excel-auto] …` note right
   away (confirms the save committed and lets you tweak the note if
   needed).

3. The **Gantt** chart now draws two extra vertical lines on every
   employee row, mirroring the existing red midnight line: a dashed
   **green** line at the pack-production **start time** and a dashed
   **amber** line at the **predicted end time**. A small legend strip
   above the axis labels each line with its time. Both lines are
   pulled from the latest `daily_pack_items` row for the displayed
   date — so as soon as you save a batch, refreshing the gantt for
   the same date shows the lines. If no Excel batch is saved for the
   date the gantt looks exactly as before (no extra lines, no legend).

3 つの小さな改善：

1. Daily Packs の **Note** 欄は、その日の個数がどの方法で入力されたかを
   自動で記録します。手入力は `[manual]`、PDF アップロードは `[pdf]`、
   PDF Auto-update は `[pdf-auto]`、Excel アップロードは `[excel]`、
   Excel Auto-update は `[excel-auto]` と先頭に付与され、ファイルの
   場合はファイル名も併記されます。Note 欄にはタグの意味を説明する
   ヒント文も表示しています。

2. Excel タブで **Confirm & Save batch →** を押すと、自動的に
   「次のステップ」に進みます：保存後すぐに Manual entry タブへ
   切り替わり、製造日が読み込まれて保存内容と `[excel-auto] …` の
   ノートを画面上で確認できます（保存が確実に反映されたことを
   その場で目視確認できる UX）。

3. **Gantt** チャートに、これまでの赤い 0 時ラインに加えて
   破線の縦ラインを 2 本追加しました：緑の破線が製造の **開始時刻**、
   琥珀色の破線が **予測終了時刻** です。各従業員の行すべてに同じ
   ラインが引かれ、軸の上には短い凡例（線の色と時刻）も表示します。
   両方の値は表示している日付の最新の `daily_pack_items` から取得
   するので、Excel バッチを保存したあと該当日付の Gantt をリロード
   すればすぐに表示されます。Excel バッチが未保存の日付では従来どおり
   余分な線は出ません。

---

**Earlier today / 同日（先ほど）の更新 (dual-table save + Auto-update + tab reorder)**
The Daily Packs tab now uses **one button** to save the day's data:
**Confirm & Save batch →**. Clicking it stores the per-product
breakdown to `daily_pack_items` AND updates the day's total pack
count in `daily_packs` (the existing summary table the rest of the
app reads from), all in one transaction. The global "Confirm & Save"
button at the bottom is hidden while the Excel segment is active so
there are not two competing buttons.

The tab order was changed: **Upload Excel** is now first (and active
by default), **Upload PDF** is second, **Manual entry** is last.
Excel is the canonical source — the PDF is just its print.

The Excel segment also has its own **Auto-update →** button, mirroring
the PDF Auto-update. It pulls the latest `.xlsx` from the
`auto_uploads/daily_packs/` folder, parses it, and shows the
per-product preview with the predicted end time. Verified end-to-end
with the real file dropped into the watched folder: 15 products
parsed, 12,486 packs saved, both DB tables updated.

Daily Packs タブのデータ保存は **ボタン 1 つ**になりました：
**Confirm & Save batch →**。これを押すと、商品ごとの内訳を
`daily_pack_items` に、その日の合計個数を `daily_packs`（他の機能が
参照している既存の集計テーブル）に、同時に 1 トランザクションで
保存します。Excel セグメント表示中は、ページ下部の「Confirm & Save」
ボタンは非表示にしてあります（ボタンが 2 つになって混乱しないように）。

タブの順番も変更しました：**Upload Excel** が最初（既定で有効）、
次に **Upload PDF**、最後に **Manual entry**。Excel が原本データで
PDF はその印刷物なので、自然な順番にしました。

Excel セグメントにも **Auto-update →** ボタンを追加しました（PDF と
同じ動作）。`auto_uploads/daily_packs/` フォルダ内の最新 `.xlsx`
をサーバ側で取得・解析し、商品ごとのプレビューと終了予測時刻を
表示します。実ファイルをフォルダに置いて動作確認済み：商品 15 件
を解析・12,486 個を保存・両方のテーブルが更新されました。

---

**Earlier today / 同日（先ほど）の更新 (Excel parser fix)**
The first version of the Daily Packs Excel uploader failed on the
real production files with "Could not find header row". The real
workbook is structured very differently from the print preview I
worked from earlier: the file has 50+ sheets, the right one is
called **入力画面**, the header uses fullwidth **Ｎ便計 / Ｙ便計**
characters and is split across 3 rows (one for the labels, one for
N便/Y便, one for 山梨/長野/松本), product names sit in column 2 (the
"A, B, C…" codes in column 0 are not product names), 製造日 is an
Excel serial number rather than a date string, and 入力者/天気/温度
values are placed *below* their labels rather than to the right.

The parser was rewritten to handle all of that automatically. It
now picks the right sheet by name, normalizes fullwidth/halfwidth
characters before matching headers, allows a 3-row header window,
converts Excel serial dates back to YYYY-MM-DD, and looks for label
values in both directions (right and below). It was verified end-to-end
on the actual file `/home/pi/DATA/UPLOAD/日報、各作業指示書２６.０４.２２.xlsx`:
all 15 products extracted with full region×batch breakdown,
production date 2026-04-22, input by 仁科, weather 曇り, temp 23°C.
Start time auto-detected as 17:00 from 54 attendance entries (median
IN 16:09 → -30 min ≈ 15:39 → snaps to 17:00; the live commute_time
data put it close to 17:00). Predicted production end **23:16** for
12,486 packs at average ~1,988 packs/hour. Smoke-tested across six
January files; all parsed cleanly.

Daily Packs の Excel アップロードが「Could not find header row」で
失敗する問題を修正しました。実際の業務ファイルはサンプル PDF と
レイアウトが大きく異なります：1 つのワークブックに 50 以上のシートが
あり正しいシート名は **入力画面**、ヘッダーは全角の **Ｎ便計 / Ｙ便計**
を使用し 3 行に渡って配置されており、商品名は 0 列目（A, B, C… の
記号）ではなく 2 列目にあり、製造日は Excel のシリアル日付値で
保持されており、入力者・天気・温度の値はラベルの右ではなく下のセルに
入っています。

これらすべてを自動で扱うようにパーサを書き直しました。シート名で
正しいシートを優先選択し、半角/全角を NFKC 正規化してからヘッダーを
検出、3 行ヘッダー窓を許容、Excel シリアル日付を YYYY-MM-DD に変換、
ラベルの値を右・下の両方向から探索します。実ファイル
`/home/pi/DATA/UPLOAD/日報、各作業指示書２６.０４.２２.xlsx` で
エンドツーエンド検証済み：商品 15 件すべて地域×便の内訳付きで取得、
製造日 2026-04-22、入力者 仁科、天気 曇り、気温 23°C。Start time
は出勤データ 54 件から自動検出（median IN 16:09 → 17:00 へスナップ）、
予測終了時刻は **23:16**（合計 12,486 個 / 平均 約 1,988 個/h）。
1 月分のファイル 6 件でも正常に解析できることを確認しました。

---

**Earlier today / 同日（先ほど）の更新**
The Daily Packs tab can now also accept the **real Excel file**
(.xlsx) — the same source the PDF is printed from. Click the new
"Upload Excel" segment, drop the file, and the page parses every
product on the sheet (e.g. ちくわ磯辺天ぶっかけうどん, あっさり本格中華そば,
…), shows each product's quantity per region per batch (山梨/長野/松本
under N便 and Y便), and saves the breakdown into a new database table
called `daily_pack_items`. The existing per-day pack-count table
(`daily_packs`) is left as it is, so old reports keep working.

The page also predicts the **production end time**. It reads each
product's quantity from the Excel, multiplies by the production rate
(packs/hour) defined in a JSON file on the server, and adds them all
up starting from the selected Start time (17:00 or 19:00). Start
time is **auto-detected** from the day's attendance — the page looks
at when most employees clocked in, subtracts 30 minutes, and snaps
to the nearest of 17:00 / 19:00. If there is no attendance data yet
it defaults to 17:00; either way you can override with the dropdown.

The **production rates** are editable from the same tab (collapsible
"Production rates editor" panel). Rates are remembered per product;
products without a rate fall back to the default and the UI
highlights them in amber so you know where to fill in numbers.
Staffing-adjusted rates (fewer workers → slower) are intentionally
left for later — the rate at save time is stored in the DB row so
the formula can be revised without changing the schema.

Daily Packs タブで PDF だけでなく **元の Excel ファイル（.xlsx）** も
扱えるようになりました。新しい「Upload Excel」セグメントから
ファイルをドロップすると、Excel 上のすべての製品（ちくわ磯辺天
ぶっかけうどん、あっさり本格中華そば、など）を解析し、各製品の
山梨／長野／松本（N便・Y便）ごとの数量を画面に表示し、`daily_pack_items`
という新しい DB テーブルに保存します。既存の日次合計テーブル
（`daily_packs`）はそのまま残してあるので、過去のレポートは
従来どおり動作します。

加えて **製造終了時刻の予測** を表示します。各製品の数量を
サーバ上の JSON で定義した製造レート（packs/hour）で割り、合計
時間を Start time（17:00 または 19:00）に足し合わせます。
Start time はその日の出勤データから **自動推定** します：
従業員の打刻時刻の中央値から 30 分引いた値を、17:00 と 19:00 の
近い方にスナップします。出勤データがまだ無い場合は 17:00 を
デフォルトとし、いずれの場合もドロップダウンで手動上書きできます。

**製造レート** は同じタブ内で編集できます（「Production rates editor」
パネル）。各製品にレートを登録すると次回以降も使われ、未登録の
製品はデフォルト値で計算され、画面上で琥珀色にハイライトされる
ので入力すべき行が一目で分かります。人員不足によるレート低下
（人数が減るとライン速度が落ちる）への補正は、今回はあえて
未実装として、保存時のレートを DB 行に固定する仕組みだけ
入れてあります。後日その式を導入してもスキーマ変更は不要です。

---

**Earlier today / 同日（朝）の更新**
The /admin/ Overview tab now shows the same KPI graphics as
/dashboard/ — colored bars for CPU, Memory, Disk, Swap, plus Load
average, CPU temperature, and uptime. The empty "—" placeholders
for Memory/Disk/Load/Uptime are gone. A new "Health monitor log"
panel shows the last 30 lines of the daily health-check log in a
terminal-style box, color-coded by OK / ACTION / WARN / ERROR. Two
action buttons sit at the top of the tab: **↻ Refresh** re-pulls
everything, and **⚕ Run health check** triggers the same script
that runs nightly and then polls the log for ~10 seconds so you
see the result immediately. The Services panel below the log shows
each systemd service with its own CPU/RAM mini-bars.

/admin/ の Overview タブに、/dashboard/ と同じ KPI グラフィック
（CPU・メモリ・ディスク・Swap の色付きバー、Load Average、CPU 温度、
稼働時間）を表示するようにしました。Memory/Disk/Load/Uptime が
「—」と空表示になっていた不具合は解消しています。下に「Health
monitor log」パネルを追加し、毎日のヘルスチェックログの直近 30 行を
ターミナル風の枠内に色分け（OK / ACTION / WARN / ERROR）で表示します。
タブ上部にボタンを 2 つ配置：**↻ Refresh** で全カードを再取得、
**⚕ Run health check** で夜間と同じヘルスチェックを即時実行し、
ログを 10 秒ほど自動ポーリングして結果をその場で確認できます。
ログの下の Services パネルでは、各 systemd サービスの CPU/RAM を
ミニバーで表示します。

---

**Earlier / 同日（夜）の更新**
The /admin page (https://rnd.asiakawaii.com/admin/) was rebuilt to
match the look of the /dashboard/ page (light theme, same fonts and
cards). It is now organized into tabs you can switch between in the
URL: Overview, Access Log, Visitors, Alerts, Security, Announcement,
and Bridge. Times are shown as "3 minutes ago" / "yesterday 14:32"
instead of raw timestamps. Overview also shows what processes are
running on the server and which are using the most CPU and memory.

To answer "who is logging in and from where", open the **Visitors**
tab. Each IP can be labeled — e.g. "Office", "Buddhika home",
"Unknown" — and saved with one click. Once labeled, the same colored
badge appears on every row in the Access Log and the Alerts tab, so
you can tell at a glance whether a visit came from the office, from
your house, or from somewhere unexpected. The **Security** tab adds
a quick view for bot/abuse spotting: hits per 5/15/60 min, top IPs,
4xx-heavy IPs, and probes for suspicious paths like `.env`, `/wp-…`,
`/phpmyadmin` etc.

The BETA banner on /attendance/console is no longer hard-coded. It is
now driven by `announcement.json` and editable from the **Announcement**
tab in /admin/. Pick a preset (BETA, MAINTENANCE, INFO, WARNING, OK),
or write your own English + Japanese text and color, click Save & publish,
and the banner updates everywhere within five minutes (or on next
page load). Each user can also dismiss the banner with ✕; a small
"show notice" pill brings it back. When a new announcement is published
the dismiss is reset automatically so users see the new notice.

Two future tabs were intentionally left as easy add-ons (LINE bot
stats, backup status). The current SPA structure makes adding them
a one-section copy-paste.

/admin ページ（https://rnd.asiakawaii.com/admin/）は、/dashboard/
と同じデザイン（ライトテーマ・同じフォント・同じカード）に作り直しました。
タブ切り替え式になり、URL のハッシュ部分で状態を保持します
（Overview / Access Log / Visitors / Alerts / Security / Announcement /
Bridge）。時刻は「3分前」「昨日 14:32」のような読みやすい表記に
変更しました。Overview ではサーバ上で動いているプロセスと CPU・
メモリ使用量上位のタスクも表示します。

「誰がどこから来ているか確認したい」というご要望には **Visitors**
タブで対応しました。各 IP に対して「事務所」「Buddhika 自宅」
「不明」などのラベルを付けて保存でき、一度ラベルを付ければ
Access Log と Alerts のすべての行に同じ色のバッジが表示されるので、
事務所からのアクセスか、ご自宅からか、それ以外かを一目で判別できます。
**Security** タブでは Bot や不正アクセスの兆候を素早く確認できます：
直近 5/15/60 分のリクエスト数、上位 IP、4xx 多発 IP、`.env` や
`/wp-…`、`/phpmyadmin` などへの探索アクセス。

/attendance/console の BETA バナーはハードコードを廃止し、
`announcement.json` で管理して /admin/ の **Announcement** タブから
編集できるようにしました。プリセット（BETA / MAINTENANCE / INFO /
WARNING / OK）を選ぶか、英語と日本語のテキストや色を自由に書いて
「Save & publish」を押すと、5分以内（もしくは次回読み込み時）に
全画面に反映されます。各ユーザーは ✕ で個別に閉じることもでき、
小さな「show notice」のピルで再表示できます。新しいお知らせが
公開されたときは閉じた状態が自動で解除されるので、必ず新しい
内容が表示されます。

将来追加しやすいようにタブ構造を残してあります（LINE BOT 統計、
バックアップ状況など）。

---

**Earlier today / 同日（夕方）の更新**
The "Use latest from server →" button on both the Attendance PDF tab
and the Daily Packs tab is now called **Auto-update →**. The two
sections also have their own server folders now, so attendance PDFs
and daily-packs PDFs no longer mix together. The old upload-worktable
filters were renamed: "Missing leave only" is now **Not recorded data**
(when the timeclock is missing either the IN or the OUT), and
"Overnight only" is now **Absent** (when both IN and OUT are missing).
With both checkboxes unchecked the table shows every name, so the
default view is the full PDF.

A new guide file `API_APP_GUIDE.md` was added next to this file. It
explains how to build a Windows desktop app (Electron) that uses the
API keys, what CMD / curl commands to run from a PC, and what extra
things the **Auto-update** button can do when triggered from the
desktop app instead of the browser (auto-copy from a Windows share,
open the resulting Excel, send a Slack message, etc.). The web design
is intentionally kept compatible with that desktop wrapper.

「サーバーから最新を取得 →」ボタンは、勤怠PDFタブと Daily Packs
タブの両方で **Auto-update →** に名称変更しました。さらに、両方の
セクションは別々のサーバーフォルダを使うようになり、勤怠PDF と
Daily Packs PDF が同じフォルダに混ざることはなくなりました。
アップロード一覧のフィルターも名称と意味を変更しました：
「Missing leave only」→ **Not recorded data**（出勤または退勤の
どちらかが打刻されていない＝データ未受信）、
「Overnight only」→ **Absent**（出勤も退勤も打刻されていない＝欠勤）。
チェックを両方外すと全員が表示されるので、初期表示は PDF の全件です。

このファイルの隣に `API_APP_GUIDE.md` を追加しました。Windows
デスクトップアプリ（Electron）の作成手順、API キーの使い方、
CMD / curl コマンドの例、ブラウザではなくデスクトップアプリから
**Auto-update** を押したときに追加で実行できる処理（Windows 共有
からの自動コピー、Excel の自動オープン、Slack 通知 など）を
まとめています。Web 画面側は、このデスクトップ化と両立する設計を
維持しています。

---

**Earlier today / 同日（午後）の更新**
You can now switch between Console, Gantt, Summary and Reports in one
click from any of those pages — the same nav appears on all four. The
Reports page (https://rnd.asiakawaii.com/attendance/reports) is now
styled to match the rest of the app (light theme, same buttons, same
report cards) and is no longer a separate dark page.
コンソール、Gantt、サマリー、レポートの各画面にナビゲーションを統一し、
どの画面からもワンクリックで切り替えできるようになりました。
レポート画面（https://rnd.asiakawaii.com/attendance/reports）は
他の画面と同じデザイン（ライトテーマ・同じボタン・同じレポートカード）
に統一しました。

For the auto-upload "Watched folder" field: you can now set the path
to a folder OR to a single .pdf file. If you paste a Windows path
(like E:\Company_Data\...), the page now shows a clear warning that
the Pi cannot read drives on a personal PC, and tells you the two
working options: push PDFs from the PC via the API
(POST /attendance/api/v1/pdf/upload with the X-API-Key header), or
mount the Windows folder on the Pi via CIFS/SMB and set the field to
the mounted Linux path. The error message returned by the server when
auto-upload fails has been rewritten the same way.
自動アップロードの「監視フォルダ」欄は、フォルダ または 単一の .pdf
ファイルのパスを設定できるようになりました。Windowsドライブ上の
パス（例：E:\Company_Data\…）を貼り付けた場合、Pi はそのドライブを
直接読めない旨の警告と、2つの解決方法（① X-API-Key 付きで
POST /attendance/api/v1/pdf/upload に PDF を送信、② Pi に
CIFS/SMB でマウントしてマウント後の Linux パスを設定）を画面に
表示するようにしました。サーバー側の自動アップロード失敗時の
エラーメッセージも同じ内容に書き換えています。

---

**Latest update / 最新更新 (morning)**
The console at https://rnd.asiakawaii.com/attendance/console has been
upgraded into a single-window operations workspace. Tabs are now in the
order you asked for: フルキャスト first, then Attendance PDF, then Daily
Packs. Reports has moved to its own page and opens from the tab bar as a
link. On the Attendance PDF tab you can now type or paste the watched
folder URL/path directly into the page, click Save, and the server will
remember it for every future auto-upload — you can also change it any
time and the previous path is kept in the history.
コンソール画面（https://rnd.asiakawaii.com/attendance/console）を
ワンウィンドウの作業画面に再構成しました。タブ順は ご指示どおり
フルキャスト → 勤怠PDF → Daily Packs の順になり、レポートは別ページ
に移動してタブバーからリンクで開きます。勤怠PDFタブには監視フォルダ
のURL/パスを画面から直接入力できる枠を追加しました。保存すれば
そのマシン用の自動アップロード先として記憶され、いつでも変更可能で、
以前のパスは履歴として残ります。

A new admin page has been added at https://rnd.asiakawaii.com/admin
for the server owner. It is password-protected. After logging in you
can see live server health (CPU, memory, disk), database status, the
current auto-upload folder, the loaded API keys (masked), the full
access log of who is using the system (with date, time, IP, device,
page, response code), and any new-login alerts whenever a brand-new
device or IP first reaches the server. There is also an embedded
shortcut to /upload/ for moving files. All access events are written
to a JSON log file on the server at /var/log/ai_server/access.jsonl
so you can review them later or feed them into other tools.
サーバー管理者用に https://rnd.asiakawaii.com/admin を新設しました
（パスワード付き）。ログイン後、サーバーの稼働状況（CPU・メモリ・
ディスク）、データベース接続、現在の自動アップロード先、読み込まれて
いるAPIキー（マスク表示）、誰がいつどこからアクセスしたかの全履歴
（日時・IP・端末・ページ・ステータス）、未知の端末や新しいIPからの
初回アクセスを示す新規ログイン警告を確認できます。
ファイル操作用に /upload/ をパネル内にも埋め込んでいます。
全アクセスは /var/log/ai_server/access.jsonl にJSON形式で保存され、
後から確認したり他のツールで処理できるようにしています。

For app and CLI integration, three API keys are now configured on the
server (TEST for development, APP for mobile/CLI clients, WEB for
browser integrations). They are stored in attendance_app/api_keys.json
and used by sending the X-API-Key header. The structured endpoints
under /attendance/api/v1/ accept these keys for uploading PDFs,
listing them, retrieving them, and triggering auto-upload. A small
command-line tool was added at /var/www/console/console_cli.py that
uses these keys, so PDFs can also be pushed or pulled from a terminal
or a scheduled job.
アプリやCLIから利用するための APIキーを3本（開発用 TEST、アプリ用
APP、Web用 WEB）サーバーに設定しました。attendance_app/api_keys.json
に保存され、X-API-Key ヘッダーで送信して利用します。
/attendance/api/v1/ 以下の構造化エンドポイントでPDFのアップロード・
一覧・取得・自動アップロードの起動が可能です。ターミナルや定期実行
からも使えるよう、/var/www/console/console_cli.py にコマンドライン
ツールも追加しています。

All edited files were backed up before changes to
/var/www/backups/console_build_20260427_143354/. The attendance
service and Nginx have been reloaded; both are healthy.
変更前にすべての対象ファイルを
/var/www/backups/console_build_20260427_143354/ にバックアップして
います。attendance サービスと Nginx を再読み込みし、いずれも正常に
稼働しています。

---

**Date / 日付 (previous):** 2026-04-25

**Previous update / 前回の更新**
The Management page is now faster to use when many employees need to be
moved between sections or reordered. You can now select several employee
cards at once and drag the whole group together to a new section,
keeping their order. Use Ctrl (or ⌘ on Mac) + click to add cards one by
one to the selection, or Shift + click to select a range. A small
"Clear selection" button and a selection counter were also added next
to the search box.
管理画面で複数の社員をまとめて移動・並び替えできるようになりました。
複数の社員カードを同時に選択し、選択したグループをそのままドラッグして
別の課に移動できます（順番は保持されます）。Ctrl（Mac は ⌘）＋クリックで
個別に追加選択、Shift ＋クリックで範囲選択ができます。検索ボックス横に
選択件数の表示と「選択解除」ボタンも追加しています。

On the same Management page, importing from attendance PDFs is now
easier as well. You can drag and drop one or more PDF files directly
onto the upload area, and the app will read all of them, automatically
remove duplicates by employee code, and show progress for each file.
同じ管理画面で、勤怠PDFからの取り込みも改善しました。複数のPDFファイルを
アップロードエリアに直接ドラッグ＆ドロップでき、すべてのPDFを読み取って
社員コード単位で自動的に重複を除去し、各ファイルの進行状況を表示します。

---

**Date / 日付 (previous):** 2026-04-24

A new reference document, *KPI Calculations*, has been added to the app
folder. It explains how daily productivity, monthly totals, and staff
performance scores are calculated, so every report uses the same numbers.
アプリフォルダに新しい参考資料「KPI 計算書」を追加しました。日次生産性・
月間集計・スタッフ成績スコアの算出方法を統一し、どの帳票でも同じ数字と
なるように記載しています。

---

**Date / 日付 (previous):** 2026-04-23

This report summarises the issues found during testing and their current resolution status. No technical details are included — only what was wrong and how it was resolved from a user's point of view.

本レポートはテストで発見された不具合と、その対応状況をまとめたものです。技術的な内容は省き、利用者視点で「何が問題であったか」「どのように解決されたか」のみを記載しています。

---

## 1. Date display showed the wrong day
## 日付表示が誤っていた不具合

**Issue / 問題**
The Shift and Production dates on the console sometimes showed the previous day during early-morning hours.
コンソール画面のシフト日・製造日が早朝の時間帯に前日で表示されていた。

**Resolution / 対応**
Fixed. Dates now follow Japan Standard Time (JST) correctly throughout the day.
修正済み。日本時間（JST）基準で一日中正しい日付が表示されます。

---

## 2. Overnight shifts were not handled correctly
## 深夜を跨ぐシフトが正しく処理されなかった

**Issue / 問題**
When a フルキャスト worker's shift ended after midnight (for example 19:00 → 02:00 next day), the system could not record the correct hours.
フルキャストの勤務終了が深夜を跨ぐ場合（例：19:00 → 翌 02:00）、勤務時間を正しく記録できなかった。

**Resolution / 対応**
Fixed. A "翌日 / next day" badge is now shown on the leave time, and hours are calculated correctly across midnight.
修正済み。退勤時刻に「翌日」バッジが表示され、日付を跨いだ勤務時間も正しく計算されます。

---

## 3. Tab 2 time selection needed to match the factory shift window
## タブ2 — 工場シフト枠に沿った時刻選択の制限

**Issue / 問題**
Users could pick start times outside the actual shift window (e.g. 07:00), producing impossible work-hour values.
シフト時間帯外の開始時刻（例：07:00）が選択でき、不正な勤務時間が算出されていた。

**Resolution / 対応**
Fixed. Start time is limited to **18:00–22:00**, leave time up to **10:00 next day** (maximum 16 hours). Out-of-range rows are highlighted in red and cannot be saved.
修正済み。開始時刻は **18:00〜22:00**、退勤時刻は **翌日 10:00 まで**（最大 16 時間）に制限。範囲外の入力は赤く表示され、保存できません。

---

## 4. Security — script injection through the employee name field
## セキュリティ — 氏名欄からのスクリプト注入

**Issue / 問題**
HTML / JavaScript code placed inside an employee name was stored in the system and executed later on the Management page — a clear security risk.
氏名欄に HTML や JavaScript コードを入力すると、そのまま保存され、管理画面の表示時に実行されてしまうセキュリティ上の問題があった。

**Resolution / 対応**
Fixed with multi-layer defence: invalid characters are blocked at input, escaped when displayed, and rejected by the server. Existing records have been scanned and are clean.
多層防御で修正。入力時に不正文字を拒否し、表示時にエスケープ処理、サーバー側でも検証。既存データも検査済みでクリーンな状態です。

---

## 5. Negative numbers were accepted
## 負の数値が入力可能だった

**Issue / 問題**
フルキャスト headcount accepted negative values (e.g. −5 persons → −35 hours). Daily Packs accepted values like −9999.
フルキャストの人数にマイナス値（例：−5 人 → −35 時間）、Daily Packs にも −9999 が入力可能だった。

**Resolution / 対応**
Fixed at three levels — browser, server, and database — so invalid numbers can no longer enter the system.
ブラウザ・サーバー・データベースの三段階で対応し、不正な数値は一切登録されなくなりました。

---

## 6. Daily Packs PDF — auto-extract and auto-fill
## Daily Packs PDF の自動抽出・自動入力（改善）

**Improvement / 改善内容**
Uploading a production-summary PDF on the Daily Packs tab now automatically reads:
- Production date
- Pack count for that day
- フルキャスト rows with start / leave times and headcount

Daily Packs タブで製造 PDF をアップロードすると、以下が自動で読み取られます：
- 製造日
- その日のパック数
- フルキャスト勤務行（開始・退勤時刻・人数）

A preview shows the extracted values with **Skip / Overwrite** options before saving, so existing data is never replaced by accident.
抽出内容はプレビュー表示され、保存前に「スキップ／上書き」を選択できるため、既存データを誤って上書きすることはありません。

---

## 7. Production date auto-correction
## 製造日の自動補正

**Issue / 問題**
The PDF prints the shift date (e.g. "2026 年 4 月 20 日製造分"), but the pack count and フルキャスト hours actually belong to the following day's production.
PDF にはシフト日（例：「2026 年 4 月 20 日製造分」）が記載されるが、パック数・フルキャスト時間は翌製造日に紐づける必要がある。

**Resolution / 対応**
The app now saves the extracted values automatically under **shift date + 1 day**, and the preview clearly shows the shift → production date translation so the user can confirm before saving. If the business rule ever changes, the offset can be adjusted easily.
アプリはシフト日に 1 日を加算した日付で自動的に保存し、プレビューにシフト日から製造日への変換を明示します。将来的に業務ルールが変更になった場合も容易に調整可能です。

---

## 8. Upload failed on large batches (504 timeout)
## 大量アップロード時のタイムアウト（504 エラー）

**Issue / 問題**
Uploading many PDFs at once caused a "504 Gateway Timeout" error.
大量の PDF を一度にアップロードすると「504 Gateway Timeout」エラーが発生していた。

**Resolution / 対応**
Fixed. Uploads are now split internally into small batches, each well under the network timeout. Extraction progress is shown, and the Confirm button is disabled during processing to prevent accidental double-submits.
修正済み。アップロードは内部で小バッチに分割され、各リクエストはネットワーク制限内に収まります。処理中はプログレス表示と「確認」ボタンの無効化により誤操作を防ぎます。

---

## 9. Test / verification banner added
## テスト中バナーの追加

Both the Console and Management pages now display a **BETA** banner in English and Japanese, informing users that the app is currently under test and data verification.
コンソール画面・管理画面に英日両言語の **BETA** バナーを表示し、本アプリが現在テスト・データ検証中であることを利用者に周知しています。

---

## 11. Gantt chart — フルキャスト total hours displayed per person instead of group total
## ガントチャート — フルキャストの合計時間が一人分で表示されていた不具合

**Issue / 問題**
For フルキャスト (temp staff) rows on the Gantt chart, the total-hours column on the right was showing the hours worked by one person (for example "8h") instead of the group total (for example 7名 × 8h = 56h, or 2名 × 8h = 16h). The stored data in the database was correct — only the on-screen number was wrong.
ガントチャートのフルキャスト（派遣）の行で、右側の合計時間欄が1人あたりの勤務時間（例：「8h」）を表示しており、グループ全体の合計（例：7名 × 8h = 56h、2名 × 8h = 16h）になっていませんでした。データベース上の値は正しく保存されており、表示のみの不具合でした。

**Resolution / 対応**
Fixed. Each フルキャスト row on the Gantt now shows the correct group total (= headcount × per-person hours). Regular employees continue to show their individual shift hours unchanged. The horizontal bar still represents one person's shift so the shift window stays readable.
修正済み。ガントチャート上のフルキャストの各行は、正しいグループ合計時間（＝人数 × 1人あたりの勤務時間）を表示するようになりました。通常社員の表示はこれまで通り個人の勤務時間です。バーの長さは1人分の勤務時間帯を示しており、シフト時間帯の視認性は維持しています。

---

## 10. Gantt chart — leave time was not displayed for some staff
## ガントチャート — 一部社員の退勤時刻が表示されなかった不具合

**Issue / 問題**
On the Gantt page, the leave time (退勤時刻) was missing from the time bar for two types of entries: staff who clocked in before 10:00 in the morning, and staff with very short shifts (for example 14:05 → 16:46). Example cases on 2026-04-22 included 矢崎 崇子 (00002403), ｶｸ ｷﾝｾｲ (00000578) and several others. The attendance data itself was correct — only the on-screen label was missing.
ガントチャートにおいて、朝10時より前に出勤した社員、および非常に短時間勤務の社員（例：14:05〜16:46）について、退勤時刻が時間バー上に表示されていませんでした。2026年4月22日では 矢崎 崇子（00002403）、ｶｸ ｷﾝｾｲ（00000578）などが該当します。勤怠データ自体は正しく記録されており、画面表示のみの不具合でした。

**Resolution / 対応**
Fixed. The leave-time label now always appears on the Gantt chart. For short-shift bars that are too narrow to fit both the start and leave times inside, the leave time is shown just to the right of the bar so it remains visible. Early-start employees also have their leave time displayed correctly now.
修正済み。ガントチャートでは、退勤時刻が常に表示されるようになりました。勤務時間が短くバー幅が足りない場合は、退勤時刻をバーの右外側に表示し、視認性を確保しています。早朝出勤の社員の退勤時刻も正しく表示されます。

---

## Current status
## 現状

- All reported bugs have been addressed.
- The database has been cleared of test data and is ready for fresh use.
- Awaiting user acceptance testing and sign-off.

- 報告された不具合はすべて対応済みです。
- データベースは検証データをクリア済みで、本番運用に利用可能な状態です。
- ユーザー受け入れテスト・承認をお待ちしています。

---

*Prepared by / 作成者:* Buddhika Jayaruwan
*Environment / 環境:* `rnd.asiakawaii.com/attendance`
