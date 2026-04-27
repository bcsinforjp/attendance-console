# Progress & Bug Status — Attendance App
# 進捗・不具合対応状況 — 勤怠アプリ

**Date / 日付:** 2026-04-25

**Latest update / 最新更新**
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
