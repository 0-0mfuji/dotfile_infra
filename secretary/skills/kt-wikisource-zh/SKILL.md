---
name: kt-wikisource-zh
description: "中国語Wikisourceの本文をEPUB化する。Karakeep-toolの books/wikisource_zh.py を使う依頼に対応する。"
---

# 中国語Wikisourceの本文をEPUB化する

確認経路: 仕様は `secretary_tools__catalog` / `secretary_tools__inspect`、環境は `secretary_tools__doctor`、原本・保存先のファイル名検索は `secretary_tools__data_files`（`source="repository"` の既定は `directory="data"`、文書は `source="documents"`）を使う。結果が `truncated` ならディレクトリを絞る。本文検索や全件集計は行わないツールなので、件数を総数と解釈しない。準備確認にshellのls/find/grepやrunの--helpを使わない。進捗は専用status、ジョブ待機はjob_statusを使う。専用経路のない実処理は汎用runの通常の承認対象であり、安全扱いに変更しない。

EPUBを作成・提供する依頼では、完成後に `secretary_tools__export_epub` を使う。`path` はKarakeep-toolからの相対パス（文書領域なら `source="documents"`）。保存先が不明なら `secretary_tools__list_epubs` で探し、shellのfind/lsを使わない。返る `workspace_path` を成果物として案内し、NanoMuseではカードを開いてダウンロードできると伝える。本文を会話に読み込まず、URLやボタンを捏造しない。進捗確認だけの依頼では実行しない。

対象は `books/wikisource_zh.py`。ソースは固定コミットの `/srv/secretary/karakeep-tool` にある。

1. `secretary_tools__inspect` に `path="books/wikisource_zh.py"` を渡し、最新の導入状態、ソース、引数、必要データを確認する。`--help` を実行するだけで処理が走るツールもあるので、最初はソースを読む。
2. 指定された対象・件数・出力先に絞る。`data/` の原本を上書きせず、成果物の出力先を明示する。Macの絶対パス、NAS・SDカード、別repo、API設定が不足する場合は必要項目を具体的に伝える。
3. `secretary_tools__run` に `path="books/wikisource_zh.py"` と文字列配列 `args` を渡す。シェル文字列を組み立てず、フラグ・値を別々の要素にする。戻るjob IDを `secretary_tools__job_status(job_id=..., wait_seconds=45)` に渡して終了と成果物を確認する。

queued/runningなら同じjob_statusで再確認する。待機のためにshellのsleepや汎用Pythonを使わない。completedを確認してから成果物を報告し、失敗・中断を成功扱いしない。
4. 対応する場合だけdry-run/planを利用する。未対応なのに `--dry-run` を付けない。外部更新・削除・一括処理は具体的な対象を提示して承認を受け、同じ範囲について会話で重複確認しない。健康診断としてバッチを起動しない。

引数候補（適用条件はソースで確認）: `--author`, `--out`, `--seeds`, `--titles`

ソースの使用説明:

```text
中国語版Wikisource(維基文庫)の作品を、簡体字のEPUBに変換する。

使い方(books/.venv で実行):
  .venv/bin/python wikisource_zh.py --seeds zh_seeds.json --out out_zh
  .venv/bin/python wikisource_zh.py --titles 孔乙己 故鄉 --author 魯迅 --out out_zh
- 取得はMediaWiki API(action=parse)で、1リクエスト/秒。カテゴリ(PD-old等)も一緒に保存する。
- 文章は CC BY-SA 4.0。EPUBの巻末に、出典(維基文庫のURL)とライセンスを記載する。
- 繁体字→簡体字は OpenCC(t2s)で変換する。ページ番号・ライセンス表示などの付随要素は取り除く。
```
