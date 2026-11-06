---
name: kt-run-all
description: "書籍作成パイプライン全体を実行する。Karakeep-toolの books/run_all.py を使う依頼に対応する。"
---

# 書籍作成パイプライン全体を実行する

EPUBを作成・提供する依頼では、完成後に `secretary_tools__export_epub` を使う。`path` はKarakeep-toolからの相対パス（文書領域なら `source="documents"`）。保存先が不明なら `secretary_tools__list_epubs` で探し、shellのfind/lsを使わない。返る `workspace_path` を成果物として案内し、NanoMuseではカードを開いてダウンロードできると伝える。本文を会話に読み込まず、URLやボタンを捏造しない。進捗確認だけの依頼では実行しない。

対象は `books/run_all.py`。ソースは固定コミットの `/srv/secretary/karakeep-tool` にある。

1. `secretary_tools__inspect` に `path="books/run_all.py"` を渡し、最新の導入状態、ソース、引数、必要データを確認する。`--help` を実行するだけで処理が走るツールもあるので、最初はソースを読む。
2. 指定された対象・件数・出力先に絞る。`data/` の原本を上書きせず、成果物の出力先を明示する。Macの絶対パス、NAS・SDカード、別repo、API設定が不足する場合は必要項目を具体的に伝える。
3. `secretary_tools__run` に `path="books/run_all.py"` と文字列配列 `args` を渡す。シェル文字列を組み立てず、フラグ・値を別々の要素にする。戻るjob IDを `secretary_tools__job_status(job_id=..., wait_seconds=45)` に渡して終了と成果物を確認する。

queued/runningなら同じjob_statusで再確認する。待機のためにshellのsleepや汎用Pythonを使わない。completedを確認してから成果物を報告し、失敗・中断を成功扱いしない。
4. 対応する場合だけdry-run/planを利用する。未対応なのに `--dry-run` を付けない。外部更新・削除・一括処理は具体的な対象を提示して承認を受け、同じ範囲について会話で重複確認しない。健康診断としてバッチを起動しない。

引数候補（適用条件はソースで確認）: `--all`, `--de-all`, `--en-top`, `--host`, `--out`, `--shard`, `--skip-existing`

ソースの使用説明:

```text
取得ジョブの監視・再起動と、完了後の判定→配置→SDカードコピーを、最後まで自動で進める。

  python3 run_all.py            # 起動(長時間。logは cache/pipeline.log)
- 取得ジョブ(青空文庫 / Gutenberg選定 / Gutenberg変換 / 中国語)が落ちたら、続きから再起動する(取得先に止められた時は1時間待つ)。
- 4つとも完了したら: finalize.py tasks -> luna -> place -> sd を順に実行する(SDカードは使わず、books/final/ に保存する)。
```
