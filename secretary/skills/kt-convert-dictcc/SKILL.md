---
name: kt-convert-dictcc
description: "dict.ccの独英データをStarDict辞書に変換する。Karakeep-toolの tools/dictionaries/german-dict/convert_dictcc.py を使う依頼に対応する。"
---

# dict.ccの独英データをStarDict辞書に変換する

EPUBを作成・提供する依頼では、完成後に `secretary_tools__export_epub` を使う。`path` はKarakeep-toolからの相対パス（文書領域なら `source="documents"`）。保存先が不明なら `secretary_tools__list_epubs` で探し、shellのfind/lsを使わない。返る `workspace_path` を成果物として案内し、NanoMuseではカードを開いてダウンロードできると伝える。本文を会話に読み込まず、URLやボタンを捏造しない。進捗確認だけの依頼では実行しない。

対象は `tools/dictionaries/german-dict/convert_dictcc.py`。ソースは固定コミットの `/srv/secretary/karakeep-tool` にある。

変換にはまず `secretary_tools__dictionary` を使う。`kind="dictcc"`、`input_file` はKarakeep-toolの `data/` からの相対パス。出力は専用の新規ディレクトリになり、通常は追加承認なしで実行できる。独自の追加オプションが必要な場合のみ以下の汎用実行を使う。

1. `secretary_tools__inspect` に `path="tools/dictionaries/german-dict/convert_dictcc.py"` を渡し、最新の導入状態、ソース、引数、必要データを確認する。`--help` を実行するだけで処理が走るツールもあるので、最初はソースを読む。
2. 指定された対象・件数・出力先に絞る。`data/` の原本を上書きせず、成果物の出力先を明示する。Macの絶対パス、NAS・SDカード、別repo、API設定が不足する場合は必要項目を具体的に伝える。
3. `secretary_tools__run` に `path="tools/dictionaries/german-dict/convert_dictcc.py"` と文字列配列 `args` を渡す。シェル文字列を組み立てず、フラグ・値を別々の要素にする。戻るjob IDを `secretary_tools__job_status(job_id=..., wait_seconds=45)` に渡して終了と成果物を確認する。

queued/runningなら同じjob_statusで再確認する。待機のためにshellのsleepや汎用Pythonを使わない。completedを確認してから成果物を報告し、失敗・中断を成功扱いしない。
4. 対応する場合だけdry-run/planを利用する。未対応なのに `--dry-run` を付けない。外部更新・削除・一括処理は具体的な対象を提示して承認を受け、同じ範囲について会話で重複確認しない。健康診断としてバッチを起動しない。

引数候補（適用条件はソースで確認）: `--encoding`, `--swap`

ソースの使用説明:

```text
dict.cc 独英辞典(公式の単語リスト .txt)をStarDict形式に変換する。

使い方:
  python convert_dictcc.py input.txt output/
  python convert_dictcc.py de-en.txt output/ --encoding utf-8

入力: dict.ccの「Vokabeldatenbank」(https://www1.dict.cc/translation_file_request.php から
      利用者自身が申請して入手するUTF-8のテキストファイル)。
      形式(実ファイルで確認): タブ区切り「ドイツ語 <TAB> 英語 <TAB> 品詞 <TAB> 分野」、'#'で始まる行は注釈・ライセンス表示。
      HTML文字参照(&#945; など)が含まれるので文字に戻して保存する。
出力: output/dictionaries/de/DictCC/dictcc.ifo|idx|dict
```
