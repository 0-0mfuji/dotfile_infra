---
name: kt-wallpaper-x3
description: "X3端末向け壁紙を生成する。Karakeep-toolの books/wallpaper_x3.py を使う依頼に対応する。"
---

# X3端末向け壁紙を生成する

確認経路: 仕様は `secretary_tools__catalog` / `secretary_tools__inspect`、環境は `secretary_tools__doctor`、原本・保存先のファイル名検索は `secretary_tools__data_files`（`source="repository"` の既定は `directory="data"`、文書は `source="documents"`）を使う。結果が `truncated` ならディレクトリを絞る。本文検索や全件集計は行わないツールなので、件数を総数と解釈しない。準備確認にshellのls/find/grepやrunの--helpを使わない。進捗は専用status、ジョブ待機はjob_statusを使う。専用経路のない実処理は汎用runの通常の承認対象であり、安全扱いに変更しない。

EPUBを作成・提供する依頼では、完成後に `secretary_tools__export_epub` を使う。`path` はKarakeep-toolからの相対パス（文書領域なら `source="documents"`）。保存先が不明なら `secretary_tools__list_epubs` で探し、shellのfind/lsを使わない。返る `workspace_path` を成果物として案内し、NanoMuseではカードを開いてダウンロードできると伝える。本文を会話に読み込まず、URLやボタンを捏造しない。進捗確認だけの依頼では実行しない。

対象は `books/wallpaper_x3.py`。ソースは固定コミットの `/srv/secretary/karakeep-tool` にある。

1. `secretary_tools__inspect` に `path="books/wallpaper_x3.py"` を渡し、最新の導入状態、ソース、引数、必要データを確認する。`--help` を実行するだけで処理が走るツールもあるので、最初はソースを読む。
2. 指定された対象・件数・出力先に絞る。`data/` の原本を上書きせず、成果物の出力先を明示する。Macの絶対パス、NAS・SDカード、別repo、API設定が不足する場合は必要項目を具体的に伝える。
3. `secretary_tools__run` に `path="books/wallpaper_x3.py"` と文字列配列 `args` を渡す。シェル文字列を組み立てず、フラグ・値を別々の要素にする。戻るjob IDを `secretary_tools__job_status(job_id=..., wait_seconds=45)` に渡して終了と成果物を確認する。

queued/runningなら同じjob_statusで再確認する。待機のためにshellのsleepや汎用Pythonを使わない。completedを確認してから成果物を報告し、失敗・中断を成功扱いしない。
4. 対応する場合だけdry-run/planを利用する。未対応なのに `--dry-run` を付けない。外部更新・削除・一括処理は具体的な対象を提示して承認を受け、同じ範囲について会話で重複確認しない。健康診断としてバッチを起動しない。

引数候補（適用条件はソースで確認）: 位置引数またはソース内設定。inspectで確認する。

ソースの使用説明:

```text
画像を、CrossPoint Wallpaper Creator(crosspoint-pxc-converter)の標準設定どおりに、X3向けBMPへ変換する。
  X3=528x792 / 切り抜き(余白なしで画面を埋める・中央) / トーン補正なし / Zhou-Fangディザ / 4階調(0,85,170,255)の4ビットBMP(上から下)
  使い方: python3 wallpaper_x3.py <入力フォルダ> <出力フォルダ> [接頭辞=sleep_]
ソース: https://github.com/itsthisjustin/crosspoint-pxc-converter (src/domain/dither.ts, formats/bmpGray.ts, quantize.ts, devices.ts)
```
