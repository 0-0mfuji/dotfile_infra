---
name: kt-zh-hf
description: "Hugging Faceの中国語書籍データをEPUB化する。Karakeep-toolの books/zh_hf.py を使う依頼に対応する。"
---

# Hugging Faceの中国語書籍データをEPUB化する

EPUBを作成・提供する依頼では、完成後に `secretary_tools__export_epub` を使う。`path` はKarakeep-toolからの相対パス（文書領域なら `source="documents"`）。保存先が不明なら `secretary_tools__list_epubs` で探し、shellのfind/lsを使わない。返る `workspace_path` を成果物として案内し、NanoMuseではカードを開いてダウンロードできると伝える。本文を会話に読み込まず、URLやボタンを捏造しない。進捗確認だけの依頼では実行しない。

対象は `books/zh_hf.py`。ソースは固定コミットの `/srv/secretary/karakeep-tool` にある。

1. `secretary_tools__inspect` に `path="books/zh_hf.py"` を渡し、最新の導入状態、ソース、引数、必要データを確認する。`--help` を実行するだけで処理が走るツールもあるので、最初はソースを読む。
2. 指定された対象・件数・出力先に絞る。`data/` の原本を上書きせず、成果物の出力先を明示する。Macの絶対パス、NAS・SDカード、別repo、API設定が不足する場合は必要項目を具体的に伝える。
3. `secretary_tools__run` に `path="books/zh_hf.py"` と文字列配列 `args` を渡す。シェル文字列を組み立てず、フラグ・値を別々の要素にする。戻るjob IDを `secretary_tools__job_status(job_id=..., wait_seconds=45)` に渡して終了と成果物を確認する。

queued/runningなら同じjob_statusで再確認する。待機のためにshellのsleepや汎用Pythonを使わない。completedを確認してから成果物を報告し、失敗・中断を成功扱いしない。
4. 対応する場合だけdry-run/planを利用する。未対応なのに `--dry-run` を付けない。外部更新・削除・一括処理は具体的な対象を提示して承認を受け、同じ範囲について会話で重複確認しない。健康診断としてバッチを起動しない。

引数候補（適用条件はソースで確認）: 位置引数またはソース内設定。inspectで確認する。

ソースの使用説明:

```text
中国語版Wikisourceの作品を、Hugging Face(wikimedia/wikisource, 20231201.zh)の本文から、高速にEPUB化する。

  .venv/bin/python zh_hf.py scan      # 11シャードを順に取得し、対象作品(とサブページ)の本文を抜き出す(元ファイルは削除)
  .venv/bin/python zh_hf.py authors   # 作者を、MediaWiki APIで50件まとめて取得(ヘッダーの author = …)
  .venv/bin/python zh_hf.py build     # 簡体字のEPUBを作る
  .venv/bin/python zh_hf.py all       # 上の3つを順に実行
対象: wikisource_zh_crawl.py と同じカテゴリ(PD-old-80-1996 / 白話長篇小說 / 白話短篇小說 / 散文集)から決めた2,320作品。
文章は CC BY-SA 4.0。EPUBの巻末に出典(維基文庫のURL)とライセンスを記載する。
```
