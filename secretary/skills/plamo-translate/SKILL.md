---
name: plamo-translate
description: PLaMo 3 Translateで日英・多言語の文章やMarkdown文書をサーバーGPUで翻訳し、新しい文書へ保存する。用語集や文体を指定するローカル翻訳の依頼で使う。
---

# ローカルPLaMo翻訳

確認経路: 仕様は `secretary_tools__catalog` / `secretary_tools__inspect`、環境は `secretary_tools__doctor`、原本・保存先のファイル名検索は `secretary_tools__data_files`（`source="repository"` の既定は `directory="data"`、文書は `source="documents"`）を使う。結果が `truncated` ならディレクトリを絞る。本文検索や全件集計は行わないツールなので、件数を総数と解釈しない。準備確認にshellのls/find/grepやrunの--helpを使わない。進捗は専用status、ジョブ待機はjob_statusを使う。専用経路のない実処理は汎用runの通常の承認対象であり、安全扱いに変更しない。

`secretary_tools__translate` を使う。汎用shell/pythonやクラウド翻訳に置き換えない。

- `text` または `input_file` のどちらか一方を指定。ファイルは `/srv/secretary/documents` 内の相対パス。
- `output_file` には同じ文書領域内の新しい保存先を指定する。原文や既存訳は上書きできない。
- `target_lang` は既定ja。`source_lang` は省略時自動判定。文体は日本語訳のとき `form=plain|polite`。
- `glossary` は `[{"source":"原語","target":"訳語"}]`。指示を原文に混ぜず専用引数を使う。
- `context` は短い補足。1要求は10万文字まで。長文は内部でトークン数に基づき分割される。
- job IDを `secretary_tools__job_status(job_id=..., wait_seconds=45)` で待機・確認する。queued/runningなら同じツールで再確認し、shellの `sleep` や待機用Pythonを使わない。ツールが利用できない場合はその旨を伝え、シェルで代用しない。
- completedになってから保存先を案内する。中断、出力上限、OOMを成功扱いしない。
- 翻訳プロセスは要求ごとに終了してVRAMを解放する。他用途でGPUが埋まっている場合は並列起動しない。
- ローカル完結を求められた場合、訳文をfilesで読んで会話に貼らず、保存先だけ返す。会話モデルはOllama Cloudなので、内容を読み込むとその本文は外部に送られる。
