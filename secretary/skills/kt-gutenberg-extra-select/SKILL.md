---
name: kt-gutenberg-extra-select
description: "Project Gutenbergの追加取得候補を選ぶ。Karakeep-toolの books/gutenberg_extra_select.py を使う依頼に対応する。"
---

# Project Gutenbergの追加取得候補を選ぶ

EPUBを作成・提供する依頼では、完成後に `secretary_tools__export_epub` を使う。`path` はKarakeep-toolからの相対パス（文書領域なら `source="documents"`）。保存先が不明なら `secretary_tools__list_epubs` で探し、shellのfind/lsを使わない。返る `workspace_path` を成果物として案内し、NanoMuseではカードを開いてダウンロードできると伝える。本文を会話に読み込まず、URLやボタンを捏造しない。進捗確認だけの依頼では実行しない。

対象は `books/gutenberg_extra_select.py`。ソースは固定コミットの `/srv/secretary/karakeep-tool` にある。

1. `secretary_tools__inspect` に `path="books/gutenberg_extra_select.py"` を渡し、最新の導入状態、ソース、引数、必要データを確認する。`--help` を実行するだけで処理が走るツールもあるので、最初はソースを読む。
2. 指定された対象・件数・出力先に絞る。`data/` の原本を上書きせず、成果物の出力先を明示する。Macの絶対パス、NAS・SDカード、別repo、API設定が不足する場合は必要項目を具体的に伝える。
3. `secretary_tools__run` に `path="books/gutenberg_extra_select.py"` と文字列配列 `args` を渡す。シェル文字列を組み立てず、フラグ・値を別々の要素にする。戻るjob IDを `secretary_tools__job_status(job_id=..., wait_seconds=45)` に渡して終了と成果物を確認する。

queued/runningなら同じjob_statusで再確認する。待機のためにshellのsleepや汎用Pythonを使わない。completedを確認してから成果物を報告し、失敗・中断を成功扱いしない。
4. 対応する場合だけdry-run/planを利用する。未対応なのに `--dry-run` を付けない。外部更新・削除・一括処理は具体的な対象を提示して承認を受け、同じ範囲について会話で重複確認しない。健康診断としてバッチを起動しない。

引数候補（適用条件はソースで確認）: `--dry`

ソースの使用説明:

```text
英語の追加選定: ノーベル賞関連・医学(包括的)・歴史・科学・技術。

  .venv/bin/python gutenberg_extra_select.py --dry      # 件数だけ表示(Gutendexは使わない)
  .venv/bin/python gutenberg_extra_select.py            # 選定して cache/pg_selection.jsonl に追記し、変換の進捗を初期化する
- 医学・ノーベル賞: 条件に合うものを全部。歴史・科学・技術: Gutendex(公開API)のダウンロード数順で、上位から quota 冊(条件に合うものに限る)。
- 本のメタデータ(題名・作者・生没年・主題)は、公式カタログ(pg_catalog.csv)から作る。
```
