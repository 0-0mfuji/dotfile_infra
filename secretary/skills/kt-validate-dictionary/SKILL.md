---
name: kt-validate-dictionary
description: "StarDict辞書の構造・文字・語彙を検証する。Karakeep-toolの tools/dictionaries/german-dict/validate_dictionary.py を使う依頼に対応する。"
---

# StarDict辞書の構造・文字・語彙を検証する

対象は `tools/dictionaries/german-dict/validate_dictionary.py`。ソースは固定コミットの `/srv/secretary/karakeep-tool` にある。

1. `secretary_tools__inspect` に `path="tools/dictionaries/german-dict/validate_dictionary.py"` を渡し、最新の導入状態、ソース、引数、必要データを確認する。`--help` を実行するだけで処理が走るツールもあるので、最初はソースを読む。
2. 指定された対象・件数・出力先に絞る。`data/` の原本を上書きせず、成果物の出力先を明示する。Macの絶対パス、NAS・SDカード、別repo、API設定が不足する場合は必要項目を具体的に伝える。
3. `secretary_tools__run` に `path="tools/dictionaries/german-dict/validate_dictionary.py"` と文字列配列 `args` を渡す。シェル文字列を組み立てず、フラグ・値を別々の要素にする。戻るjob IDを `secretary_tools__job_status(job_id=..., wait_seconds=45)` に渡して終了と成果物を確認する。

queued/runningなら同じjob_statusで再確認する。待機のためにshellのsleepや汎用Pythonを使わない。completedを確認してから成果物を報告し、失敗・中断を成功扱いしない。
4. 対応する場合だけdry-run/planを利用する。未対応なのに `--dry-run` を付けない。外部更新・削除・一括処理は具体的な対象を提示して承認を受け、同じ範囲について会話で重複確認しない。健康診断としてバッチを起動しない。

引数候補（適用条件はソースで確認）: `--expect-japanese`, `--expect-umlaut`, `--lookup`

ソースの使用説明:

```text
StarDict辞書(.ifo/.idx/.dict)の整合性検証と検索テスト。

使い方:
  python validate_dictionary.py dictionaries/de/DictCC/dictcc.ifo
  python validate_dictionary.py dictionaries/de/Wadoku/wadoku.ifo --lookup Haus Buch --expect-japanese

終了コード: 0=問題なし / 1=整合性エラーあり
```
