---
name: kt-gutenberg-select
description: "Project Gutenbergから取得対象の書籍を選ぶ。Karakeep-toolの books/gutenberg_select.py を使う依頼に対応する。"
---

# Project Gutenbergから取得対象の書籍を選ぶ

対象は `books/gutenberg_select.py`。ソースは固定コミットの `/srv/secretary/karakeep-tool` にある。

1. `secretary_tools__inspect` に `path="books/gutenberg_select.py"` を渡し、最新の導入状態、ソース、引数、必要データを確認する。`--help` を実行するだけで処理が走るツールもあるので、最初はソースを読む。
2. 指定された対象・件数・出力先に絞る。`data/` の原本を上書きせず、成果物の出力先を明示する。Macの絶対パス、NAS・SDカード、別repo、API設定が不足する場合は必要項目を具体的に伝える。
3. `secretary_tools__run` に `path="books/gutenberg_select.py"` と文字列配列 `args` を渡す。シェル文字列を組み立てず、フラグ・値を別々の要素にする。戻るjob IDを `secretary_tools__job_status(job_id=..., wait_seconds=45)` に渡して終了と成果物を確認する。

queued/runningなら同じjob_statusで再確認する。待機のためにshellのsleepや汎用Pythonを使わない。completedを確認してから成果物を報告し、失敗・中断を成功扱いしない。
4. 対応する場合だけdry-run/planを利用する。未対応なのに `--dry-run` を付けない。外部更新・削除・一括処理は具体的な対象を提示して承認を受け、同じ範囲について会話で重複確認しない。健康診断としてバッチを起動しない。

引数候補（適用条件はソースで確認）: `--de-all`, `--en-top`, `--out`

ソースの使用説明:

```text
Project Gutenbergの取得対象を、人気順(Gutendex API の download_count)で選ぶ。

使い方: python3 gutenberg_select.py --de-all --en-top 8000 --out cache/pg_selection.json
- ドイツ語は全点、英語は人気上位N点。Gutendex は公開APIなので、1秒間隔で、必要なページだけ取る。
- 出力: [{id, lang, title, authors:[{name,birth,death}], downloads, subjects, bookshelves}] (人気順)
```
