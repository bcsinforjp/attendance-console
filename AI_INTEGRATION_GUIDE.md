# GENBA FMS × ChatGPT — <j>セットアップガイド</j><e>Setup Guide</e>

<j>**ChatGPT を工場システムにつなぐだけ。あとは、どの言語でも「データちょうだい」「レポート作って」「こんな機能ほしい」と話すだけ。**</j>
<e>**Connect ChatGPT to the factory system, then just ask — for data, reports, or a new feature — in any language.**</e>

---

## 1. <j>できること</j><e>What you get</e>

- 📊 <j>**データ取得** — 「今日の生産数は？」</j><e>**Get data** — "What was today's production?"</e>
- 🧮 <j>**計算** — 「従業員00000376の今月の合計時間は？」</j><e>**Calculations** — "This person's monthly hours?"</e>
- 📄 <j>**レポート（いつでも）** — 「製造２課の週次まとめを作って」</j><e>**Reports anytime** — "Weekly summary for line 2."</e>
- 🧩 <j>**プロジェクト依頼** — 「両ラインを1画面で見たい」→ サーバーへ送信（§4）</j><e>**Request a project** — "I need a one-screen view of both lines." → server (§4)</e>

<j>インストール不要・研修不要。話すだけ。</j><e>No install, no training — just chat.</e>

---

## 2. <j>システム構成（5つ）</j><e>The system (5 parts)</e>

### ① 🖥️ <j>Linux サーバー（中心）</j><e>Linux Server (core)</e>
<j>常時稼働の頭脳。すべてがここにつながる。データ保存・API・依頼ワークフロー。`link.genbafms.com`。</j><e>The always-on brain; everything connects here. Stores data, runs the API + the request workflow. link.genbafms.com.</e>

### ② 💻 <j>デスクトップアプリ（事務所PC）</j><e>Desktop App (office PC)</e>
<j>ファイルを自動送信、全画面表示、全機能・印刷。</j><e>Auto-sends files, shows the dashboard, all features + print.</e>
- 🔗 <j>**ダウンロード**</j><e>**Download (Windows)**</e>: https://link.genbafms.com/download/desktop

### ③ 🌐 <j>ウェブサイト（全デバイス）</j><e>Website (any device)</e>
<j>同じシステムをブラウザで。スマホ・タブレット・PC。</j><e>The same system in a browser — phone, tablet, or PC.</e>
- 🔗 <j>**開く**</j><e>**Open**</e>: https://link.genbafms.com · <j>ライン監視</j><e>Line overview</e>: https://link.genbafms.com/dashboard

### ④ 🤖 ChatGPT (AI)
<j>人のための窓口。どの言語でも。データ・計算・レポート・依頼。</j><e>The easy front door — data, calculations, reports, requests, in any language.</e>
- 🔗 <j>**設定リンク（管理者がキー付きで送付）**</j><e>**Setup link (admin sends with key)**</e>: https://link.genbafms.com/chatgpt-setup

### ⑤ 🛠️ <j>管理者 / BUDDHIKA</j><e>Admin / BUDDHIKA</e>
<j>依頼を確認→承認→実装。キー発行（取消可・安全）。システム全体を管理。</j><e>Reviews → approves → builds requests. Issues keys (revocable). Manages the system.</e>

---

## 3. <j>ChatGPT 接続手順</j><e>Connect ChatGPT — steps</e>

> <j>**ChatGPT Plus（または Team）** が必要。1回だけ、約3分。まず**管理者からキー**をもらう。</j><e>Needs ChatGPT Plus/Team. One-time ~3 min. Ask Buddhika for your key first.</e>

![QR](https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=https%3A%2F%2Flink.genbafms.com%2Fguides)

**Step 1** — <j>GPTを新規作成</j><e>New GPT</e>: `Explore GPTs → + Create → Configure`
**Step 2** — <j>アクション追加</j><e>Add an Action</e>: `Actions → Create new action`
**Step 3** — <j>スキーマを取込</j><e>Import the schema</e>: `Schema → Import from URL`
```
https://link.genbafms.com/api/agent/v1/openapi.json
```
**Step 4** — <j>キーを入力</j><e>Add your key</e>: `Authentication → API Key → Bearer`
```
at_xxxxxxxxxxxxxxxxxxxxxxxx
```
**Step 5** — <j>保存して使う</j><e>Save & use</e>:
> <j>「GENBA FMS で今日の生産数を見せて」</j><e>"Use GENBA FMS to show today's production."</e>

✅ <j>完了</j><e>Done</e>

---

## 4. <j>プロジェクト依頼（言葉の壁をなくす）</j><e>Request a project (kills the language barrier)</e>

<j>誰でも自分の言語でAIに依頼 → サーバーに登録 → BUDDHIKA が確認・実装 → 進捗確認。</j><e>Anyone asks in their language → server → Buddhika reviews & builds → track status.</e>

```
You: "Submit a request: add a CSV export of pack counts."  (any language)
  → Change Request #N (submitted)
  → BUDDHIKA: /admin ▸ Change Requests → evaluate → approve → build
  → "What's the status?" → submitted ▸ approved ▸ in_progress ▸ completed
```

<j>「依頼：〜」「私の依頼一覧」「依頼5を見せて」と言うだけ。</j><e>Just say "Submit a request: …", "List my requests", "Show request 5."</e>

---

## 5. <j>大事な注意</j><e>Important</e>

<j>**普通の ChatGPT チャットでは API を呼べません。** ChatGPT が自動で結果を出すには、上の §3 の **Custom GPT（ChatGPT Plus 必要）** を作る必要があります。Plus が無い場合、ChatGPT からは利用できません。</j><e>**A normal ChatGPT chat cannot call the API.** For ChatGPT to fetch results automatically you must build the **Custom GPT (needs ChatGPT Plus)** in §3. Without Plus, ChatGPT can't be used for this.</e>

---

## 6. <j>安全</j><e>Safety</e>

- <j>**デフォルト拒否** — 管理者がキーを発行するまで何も動かない（取消可・通信制限可・読取専用可）。</j><e>**Deny-by-default** — nothing works until the admin issues a key (revocable, rate-limited, read-only option).</e>
- <j>ChatGPTは**閲覧**と**パック数・派遣の記録**のみ。削除・名簿変更・管理設定は不可。</j><e>ChatGPT can **read** and **record pack counts / temp staff** only. No deletes, no roster/admin changes.</e>
- <j>依頼は**提案** — 実装は人（Buddhika）が決定。</j><e>Requests are **proposals** — a human decides and builds.</e>

<j>*ガイド*</j><e>*Guide*</e>: https://link.genbafms.com/guides
