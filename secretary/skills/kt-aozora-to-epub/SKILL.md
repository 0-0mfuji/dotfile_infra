---
name: kt-aozora-to-epub
description: "青空文庫の作品を縦書き・ルビ付きEPUBにする。Karakeep-toolの books/aozora_to_epub.py を使う依頼に対応する。"
---

# 青空文庫の作品を縦書き・ルビ付きEPUBにする

対象は `books/aozora_to_epub.py`。ソースは固定コミットの `/srv/secretary/karakeep-tool` にある。

1. `secretary_tools__inspect` に `path="books/aozora_to_epub.py"` を渡し、最新の導入状態、ソース、引数、必要データを確認する。`--help` を実行するだけで処理が走るツールもあるので、最初はソースを読む。
2. 指定された対象・件数・出力先に絞る。`data/` の原本を上書きせず、成果物の出力先を明示する。Macの絶対パス、NAS・SDカード、別repo、API設定が不足する場合は必要項目を具体的に伝える。
3. `secretary_tools__run` に `path="books/aozora_to_epub.py"` と文字列配列 `args` を渡す。シェル文字列を組み立てず、フラグ・値を別々の要素にする。戻るjob IDを `secretary_tools__job_status` に渡して終了と成果物を確認する。
4. 対応する場合だけdry-run/planを利用する。未対応なのに `--dry-run` を付けない。外部更新・削除・一括処理は具体的な対象を提示して承認を受け、同じ範囲について会話で重複確認しない。健康診断としてバッチを起動しない。

引数候補（適用条件はソースで確認）: `--all`, `--ids`, `--interval`, `--limit`, `--max-chapter-chars`, `--out`, `--ruby`, `--skip-existing`, `--suffix`

注意:
- Macフォント参照あり。Linux用フォントの互換配置を利用する

ソースの使用説明:

```text
青空文庫の作品(公式XHTML)を、縦書き・ルビ付きのEPUBに変換する。

使い方:
  python3 aozora_to_epub.py --ids 127 92 773 --out out/            # 作品IDを指定
  python3 aozora_to_epub.py --all --out out/ --limit 100            # 著作権の切れた全作品(取得は1リクエスト/秒)
出力: out/青空文庫/<ジャンル>/<作者>/<作品ID>_<作品名>.epub   (ジャンルは分類番号NDCから。ファイル名は端末の青空文庫機能と同じ)

- 公式カタログ(list_person_all_extended_utf8.csv, CC BY 4.0)から、作品・人物とも著作権が切れたものだけを対象にする。
- 作品XHTMLは cache/html/ に保存し、再実行時は再取得しない。取得は低速(既定1秒間隔)で、403/429では止まる。
- 底本・入力者などのクレジット(巻末)は残す(青空文庫の取り扱い規準)。
```
