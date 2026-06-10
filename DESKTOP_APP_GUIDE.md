# 現場Link <j>デスクトップアプリ — 使い方ガイド</j><e>Desktop App — User Guide</e>

<j>**工場PC用のアプリ。フォルダにファイルを置くだけで自動でサーバーに送信。印刷・LINE送信もできます。**</j>
<e>**The Windows app for the factory PC. Drop files in a folder → they upload automatically. It also prints reports and sends them to LINE.**</e>

---

## 1. <j>これは何？</j><e>What it is</e>

- 📂 <j>**自動アップロード** — 勤怠PDF・生産Excelを置くだけで送信。</j><e>**Auto-upload** — drop attendance PDFs / production Excel; they're sent automatically.</e>
- 🖥️ <j>**ダッシュボード表示** — 会社のウェブ画面を全画面で。</j><e>**Dashboard** — shows the company web view full-screen.</e>
- 🖨️ <j>**レポート** — 勤怠・集計を印刷／PDF保存。</j><e>**Reports** — print or save the attendance & summary reports.</e>
- 💬 <j>**スケジュール送信** — 毎日決めた時刻にLINEへ自動送信。</j><e>**Scheduled delivery** — sends reports to LINE at a set time daily.</e>

<j>対応OS: **Windows**。</j><e>OS: **Windows**.</e>

---

## 2. <j>インストール</j><e>Install</e>

**Step 1** — <j>ダウンロード</j><e>Download</e>: 🔗 https://link.genbafms.com/download/desktop
**Step 2** — <j>実行（ダブルクリック）</j><e>Run (double-click)</e>

> ⚠️ <j>**「Windows によって PC が保護されました」**が出たら：**「詳細情報」→「実行」**。社内用アプリで署名が無いだけ。安全です。</j><e>If SmartScreen warns: click **"More info" → "Run anyway."** It's an in-house app (not Microsoft-signed) — it's safe.</e>

**Step 3** — <j>デスクトップの**現場Link**アイコンから起動。</j><e>Launch from the **現場Link** desktop icon.</e>

---

## 3. <j>初回設定</j><e>First-time setup</e>

<j>起動すると**パスワード画面**。ユーザー名・パスワードは**管理者から**受け取る。</j><e>On launch you'll see a **password screen** — get the username & password from your admin.</e>

<j>メニュー → **設定** で入力：</j><e>Then open the menu → **Settings** and fill in:</e>

| <j>項目</j><e>Field</e> | <j>内容</j><e>What to enter</e> |
| --- | --- |
| <j>**API キー**</j><e>**API Key**</e> | <j>管理者が発行</j><e>provided by the admin</e> |
| <j>**GenbaLink ログイン**</j><e>**GenbaLink login**</e> | <j>ウェブ画面のユーザー名・パスワード</j><e>your dashboard user + password</e> |
| <j>**PDF / Excel 監視フォルダ**</j><e>**PDF / Excel watch folders**</e> | <j>ファイルが入るフォルダ</j><e>where the files land</e> |
| <j>**プリンター / 保存先**</j><e>**Printer / Save folder**</e> | <j>印刷先 or PDF保存フォルダ</j><e>printer or PDF save folder</e> |
| <j>**言語**</j><e>**Language**</e> | 日本語 / English |

> 🔒 <j>APIキーとパスワードはPC内で暗号化保存（DPAPI）。</j><e>Your API key & password are encrypted on the PC.</e>

---

## 4. <j>毎日の使い方</j><e>Daily use</e>

<j>**何もしなくてOK。** アプリを起動しておくだけ。</j><e>**Nothing to do** — just keep the app running.</e>

1. <j>他のツールが**監視フォルダ**にファイルを保存。</j><e>Files land in the watched folders.</e>
2. <j>アプリが自動検知 → **アップロード**。</j><e>The app auto-detects → uploads.</e>
3. <j>上部の**ステータスバー**で状態・最終送信日を確認。</j><e>The top status bar shows state + last date.</e>

<j>ボタン：🏠 ホーム / ⛶ 全画面 / ✖ 終了。今すぐ送る → **同期 / Sync Now**。</j><e>Buttons: 🏠 Home / ⛶ Full screen / ✖ Exit. Push now → **Sync Now**.</e>

---

## 5. <j>レポートの印刷・保存</j><e>Print or save a report</e>

<j>ダッシュボードでレポートを開く → **印刷**。ブラウザが開き、そこで**印刷**または**PDFダウンロード**。</j><e>Open a report → **Print**. It opens in your browser, where you Print or Download as PDF.</e>

---

## 6. <j>スケジュール送信（LINE）</j><e>Scheduled delivery (LINE)</e>

### 6.1 <j>LINE 友だち登録</j><e>Register on LINE</e>
<j>下のQRをLINEで読み取り、**FMS**を友だち追加 → 「**hi**」と送信。</j><e>Scan with LINE, add **FMS** as a friend, send "**hi**" in the chat.</e>

![LINE QR](https://api.qrserver.com/v1/create-qr-code/?size=190x190&data=https%3A%2F%2Fline.me%2FR%2Fti%2Fp%2F%40229ttzgw)

LINE ID: **@229ttzgw**

### 6.2 <j>スケジュール作成</j><e>Create a schedule</e>
<j>メニュー → **スケジュール**：時刻・曜日・対象レポートを設定 → 保存。毎日その時刻にLINEへ。</j><e>Menu → **Schedule**: set time, days, and report → Save. Delivered to LINE daily.</e>

---

## 7. <j>困ったとき</j><e>Troubleshooting</e>

| <j>症状</j><e>Symptom</e> | <j>対処</j><e>Fix</e> |
| --- | --- |
| <j>画面が古い</j><e>stale screen</e> | <j>設定 → **ハードリフレッシュ**</j><e>Settings → **Hard Refresh**</e> |
| <j>ログイン画面が出る</j><e>login appears</e> | <j>GenbaLinkのユーザー名・パスワードを確認</j><e>check your GenbaLink user/password</e> |
| <j>アップロードされない</j><e>not uploading</e> | <j>フォルダ設定とAPIキーを確認</j><e>check folders + API key</e> |
| <j>送信が止まる</j><e>watcher stopped</e> | <j>サーバーがメンテ中かも。数分で自動再開</j><e>server may be paused; auto-resumes in minutes</e> |

---

### 🔑 <j>はじめに</j><e>Before you start</e>
<j>**管理者から**：①アプリのパスワード ②APIキー ③ログイン情報 を受け取る。</j><e>From your admin: ① the app password, ② the API key, ③ the dashboard login.</e>

<j>*ダウンロード*</j><e>*Download*</e>: https://link.genbafms.com/download/desktop · <j>*ガイド*</j><e>*Guide*</e>: https://link.genbafms.com/guides
