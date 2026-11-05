---
name: kt-eijiro-to-stardict
description: "英辞郎の原本をStarDict辞書に変換する。Karakeep-toolの tools/dictionaries/eijiro_to_stardict.py を使う依頼に対応する。"
---

# 英辞郎の原本をStarDict辞書に変換する

対象は `tools/dictionaries/eijiro_to_stardict.py`。ソースは固定コミットの `/srv/secretary/karakeep-tool` にある。

変換にはまず `secretary_tools__dictionary` を使う。`kind="eijiro"`、`input_file` はKarakeep-toolの `data/` からの相対パス。出力は専用の新規ディレクトリになり、通常は追加承認なしで実行できる。独自の追加オプションが必要な場合のみ以下の汎用実行を使う。

1. `secretary_tools__inspect` に `path="tools/dictionaries/eijiro_to_stardict.py"` を渡し、最新の導入状態、ソース、引数、必要データを確認する。`--help` を実行するだけで処理が走るツールもあるので、最初はソースを読む。
2. 指定された対象・件数・出力先に絞る。`data/` の原本を上書きせず、成果物の出力先を明示する。Macの絶対パス、NAS・SDカード、別repo、API設定が不足する場合は必要項目を具体的に伝える。
3. `secretary_tools__run` に `path="tools/dictionaries/eijiro_to_stardict.py"` と文字列配列 `args` を渡す。シェル文字列を組み立てず、フラグ・値を別々の要素にする。戻るjob IDを `secretary_tools__job_status` に渡して終了と成果物を確認する。
4. 対応する場合だけdry-run/planを利用する。未対応なのに `--dry-run` を付けない。外部更新・削除・一括処理は具体的な対象を提示して承認を受け、同じ範囲について会話で重複確認しない。健康診断としてバッチを起動しない。

引数候補（適用条件はソースで確認）: 位置引数またはソース内設定。inspectで確認する。

ソースの使用説明:

```text
Convert EIJIRO (英辞郎) text dump to StarDict format.

Usage: eijiro_to_stardict.py EIJIRO144-10.TXT OUT_DIR [basename]
Produces OUT_DIR/<basename>.{ifo,idx,dict} (uncompressed, sametypesequence=m).
```
