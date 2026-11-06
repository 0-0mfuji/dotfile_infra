---
name: kt-gutenberg-fetch
description: "Project Gutenbergの書籍本文を取得する。Karakeep-toolの books/gutenberg_fetch.py を使う依頼に対応する。"
---

# Project Gutenbergの書籍本文を取得する

EPUBを作成・提供する依頼では、完成後に `secretary_tools__export_epub` を使う。`path` はKarakeep-toolからの相対パス（文書領域なら `source="documents"`）。保存先が不明なら `secretary_tools__list_epubs` で探し、shellのfind/lsを使わない。返る `workspace_path` を成果物として案内し、NanoMuseではカードを開いてダウンロードできると伝える。本文を会話に読み込まず、URLやボタンを捏造しない。進捗確認だけの依頼では実行しない。

対象は `books/gutenberg_fetch.py`。ソースは固定コミットの `/srv/secretary/karakeep-tool` にある。

1. `secretary_tools__inspect` に `path="books/gutenberg_fetch.py"` を渡し、最新の導入状態、ソース、引数、必要データを確認する。`--help` を実行するだけで処理が走るツールもあるので、最初はソースを読む。
2. 指定された対象・件数・出力先に絞る。`data/` の原本を上書きせず、成果物の出力先を明示する。Macの絶対パス、NAS・SDカード、別repo、API設定が不足する場合は必要項目を具体的に伝える。
3. `secretary_tools__run` に `path="books/gutenberg_fetch.py"` と文字列配列 `args` を渡す。シェル文字列を組み立てず、フラグ・値を別々の要素にする。戻るjob IDを `secretary_tools__job_status(job_id=..., wait_seconds=45)` に渡して終了と成果物を確認する。

queued/runningなら同じjob_statusで再確認する。待機のためにshellのsleepや汎用Pythonを使わない。completedを確認してから成果物を報告し、失敗・中断を成功扱いしない。
4. 対応する場合だけdry-run/planを利用する。未対応なのに `--dry-run` を付けない。外部更新・削除・一括処理は具体的な対象を提示して承認を受け、同じ範囲について会話で重複確認しない。健康診断としてバッチを起動しない。

引数候補（適用条件はソースで確認）: 位置引数またはソース内設定。inspectで確認する。

ソースの使用説明:

```text
選定したGutenbergの本を、公式ミラー(gutenberg.pglaf.org。aleph.gutenberg.orgはHTTPS証明書が不一致のため使わない)から、2秒間隔で取得する(画像付きEPUB)。

使い方: python3 gutenberg_fetch.py cache/pg_selection.json
- 取得先: https://gutenberg.pglaf.org/cache/epub/<id>/pg<id>-images.epub (公式の robot/harvest が示すミラーのURL形式)
- 保存: cache/pg_epub/<id>.epub。取得済みはスキップ(再開できる)。403/429では止まる(回避しない)。
```
