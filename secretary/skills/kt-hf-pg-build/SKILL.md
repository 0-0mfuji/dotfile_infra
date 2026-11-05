---
name: kt-hf-pg-build
description: "Hugging FaceのGutenbergデータからEPUBを作成する。Karakeep-toolの books/hf_pg_build.py を使う依頼に対応する。"
---

# Hugging FaceのGutenbergデータからEPUBを作成する

対象は `books/hf_pg_build.py`。ソースは固定コミットの `/srv/secretary/karakeep-tool` にある。

1. `secretary_tools__inspect` に `path="books/hf_pg_build.py"` を渡し、最新の導入状態、ソース、引数、必要データを確認する。`--help` を実行するだけで処理が走るツールもあるので、最初はソースを読む。
2. 指定された対象・件数・出力先に絞る。`data/` の原本を上書きせず、成果物の出力先を明示する。Macの絶対パス、NAS・SDカード、別repo、API設定が不足する場合は必要項目を具体的に伝える。
3. `secretary_tools__run` に `path="books/hf_pg_build.py"` と文字列配列 `args` を渡す。シェル文字列を組み立てず、フラグ・値を別々の要素にする。戻るjob IDを `secretary_tools__job_status(job_id=..., wait_seconds=45)` に渡して終了と成果物を確認する。

queued/runningなら同じjob_statusで再確認する。待機のためにshellのsleepや汎用Pythonを使わない。completedを確認してから成果物を報告し、失敗・中断を成功扱いしない。
4. 対応する場合だけdry-run/planを利用する。未対応なのに `--dry-run` を付けない。外部更新・削除・一括処理は具体的な対象を提示して承認を受け、同じ範囲について会話で重複確認しない。健康診断としてバッチを起動しない。

引数候補（適用条件はソースで確認）: 位置引数またはソース内設定。inspectで確認する。

ソースの使用説明:

```text
Hugging Face(テキスト)から、Gutenbergの本を、複数コアで並列にEPUB化する。

  .venv/bin/python hf_pg_build.py de      # ドイツ語(取得済みの cache/hf_pg/de.jsonl.gz から)
  .venv/bin/python hf_pg_build.py en      # 英語(52シャードを1つずつ取得 → 変換 → 元ファイルを削除)
  .venv/bin/python hf_pg_build.py all     # de → en
- 対象: cache/pg_selection.jsonl の本のうち、まだ pg_meta.jsonl に無いもの(公式EPUB由来のものは、そのまま使う)。
- 出力: out_pg/<言語>/<ID>_<題名>.epub と、判定用メタ情報 cache/pg_meta.jsonl(追記)。再実行で続きから。
```
