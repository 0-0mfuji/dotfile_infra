---
name: kt-luna-batch
description: "外部AI APIを使った書籍のバッチ処理を行う。Karakeep-toolの books/luna_batch.py を使う依頼に対応する。"
---

# 外部AI APIを使った書籍のバッチ処理を行う

対象は `books/luna_batch.py`。ソースは固定コミットの `/srv/secretary/karakeep-tool` にある。

1. `secretary_tools__inspect` に `path="books/luna_batch.py"` を渡し、最新の導入状態、ソース、引数、必要データを確認する。`--help` を実行するだけで処理が走るツールもあるので、最初はソースを読む。
2. 指定された対象・件数・出力先に絞る。`data/` の原本を上書きせず、成果物の出力先を明示する。Macの絶対パス、NAS・SDカード、別repo、API設定が不足する場合は必要項目を具体的に伝える。
3. `secretary_tools__run` に `path="books/luna_batch.py"` と文字列配列 `args` を渡す。シェル文字列を組み立てず、フラグ・値を別々の要素にする。戻るjob IDを `secretary_tools__job_status` に渡して終了と成果物を確認する。
4. 対応する場合だけdry-run/planを利用する。未対応なのに `--dry-run` を付けない。外部更新・削除・一括処理は具体的な対象を提示して承認を受け、同じ範囲について会話で重複確認しない。健康診断としてバッチを起動しない。

引数候補（適用条件はソースで確認）: `--effort`, `--max-tokens`, `--n`

注意:
- 外部AI APIを利用。別途APIキーと利用料金が必要

ソースの使用説明:

```text
GPT-Luna(OpenAI)で、外国語の本の「難易度(初級/中級/上級)・ジャンル・一言説明」を付ける。Batch APIで安く一括処理する。

使い方(books/.venv で実行):
  .venv/bin/python luna_batch.py prepare tasks.jsonl          # リクエストを作る(送信しない)。トークン数と費用の目安を表示
  .venv/bin/python luna_batch.py estimate tasks.jsonl         # 見積もりだけ
  .venv/bin/python luna_batch.py submit                       # Batch APIに送信
  .venv/bin/python luna_batch.py status                       # 進捗を確認
  .venv/bin/python luna_batch.py collect                      # 完了したバッチの結果を取り込む -> luna/results.json
  .venv/bin/python luna_batch.py sample tasks.jsonl --n 3     # 同期APIで数件だけ試す(動作確認用)

tasks.jsonl の1行(メタデータのみ。本文は含めない):
  {"key":"gutenberg-1342","lang":"en","title":"Pride and Prejudice","author":"Jane Austen","years":"1775-1817","chars":690000,"subjects":[...]}
APIキーは環境変数 OPENAI_API_KEY か books/.env から読む(コードやチャットには書かない)。
送るのは作品名・作者・生没年・長さ・分類だけ。本文も抜粋も送らない。
```
