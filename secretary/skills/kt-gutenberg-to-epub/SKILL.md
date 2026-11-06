---
name: kt-gutenberg-to-epub
description: "Project Gutenbergの本文をEPUBに変換する。Karakeep-toolの books/gutenberg_to_epub.py を使う依頼に対応する。"
---

# Project Gutenbergの本文をEPUBに変換する

確認経路: 仕様は `secretary_tools__catalog` / `secretary_tools__inspect`、環境は `secretary_tools__doctor`、原本・保存先のファイル名検索は `secretary_tools__data_files`（`source="repository"` の既定は `directory="data"`、文書は `source="documents"`）を使う。結果が `truncated` ならディレクトリを絞る。本文検索や全件集計は行わないツールなので、件数を総数と解釈しない。準備確認にshellのls/find/grepやrunの--helpを使わない。進捗は専用status、ジョブ待機はjob_statusを使う。専用経路のない実処理は汎用runの通常の承認対象であり、安全扱いに変更しない。

EPUBを作成・提供する依頼では、完成後に `secretary_tools__export_epub` を使う。`path` はKarakeep-toolからの相対パス（文書領域なら `source="documents"`）。保存先が不明なら `secretary_tools__list_epubs` で探し、shellのfind/lsを使わない。返る `workspace_path` を成果物として案内し、NanoMuseではカードを開いてダウンロードできると伝える。本文を会話に読み込まず、URLやボタンを捏造しない。進捗確認だけの依頼では実行しない。

対象は `books/gutenberg_to_epub.py`。ソースは固定コミットの `/srv/secretary/karakeep-tool` にある。

1. `secretary_tools__inspect` に `path="books/gutenberg_to_epub.py"` を渡し、最新の導入状態、ソース、引数、必要データを確認する。`--help` を実行するだけで処理が走るツールもあるので、最初はソースを読む。
2. 指定された対象・件数・出力先に絞る。`data/` の原本を上書きせず、成果物の出力先を明示する。Macの絶対パス、NAS・SDカード、別repo、API設定が不足する場合は必要項目を具体的に伝える。
3. `secretary_tools__run` に `path="books/gutenberg_to_epub.py"` と文字列配列 `args` を渡す。シェル文字列を組み立てず、フラグ・値を別々の要素にする。戻るjob IDを `secretary_tools__job_status(job_id=..., wait_seconds=45)` に渡して終了と成果物を確認する。

queued/runningなら同じjob_statusで再確認する。待機のためにshellのsleepや汎用Pythonを使わない。completedを確認してから成果物を報告し、失敗・中断を成功扱いしない。
4. 対応する場合だけdry-run/planを利用する。未対応なのに `--dry-run` を付けない。外部更新・削除・一括処理は具体的な対象を提示して承認を受け、同じ範囲について会話で重複確認しない。健康診断としてバッチを起動しない。

引数候補（適用条件はソースで確認）: 位置引数またはソース内設定。inspectで確認する。

ソースの使用説明:

```text
Project GutenbergのEPUBを、e-ink向けに再構成する(言語タグ、画像のグレースケール化、章分割、画像は章の先頭)。

- 元EPUBの本文(spine順)を取り出し、Karakeep記事と同じ整形(Sanitizer)で XHTML を作り直す。
- 画像は 528x792 以内・グレースケール・JPEG に変換(容量削減)。画像は章の先頭に置く(端末での表示対策)。
- 章は見出しで区切り、長い章は分割。目次は見出しから作る。
- Gutenbergのライセンス表記(本文の頭と末尾)は、そのまま残す。
- 副産物として、難易度判定用のメタ情報(長さ・文の長さ・抜粋)を返す。
```
