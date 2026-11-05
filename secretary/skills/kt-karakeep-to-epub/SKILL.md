---
name: kt-karakeep-to-epub
description: "Karakeepの保存記事をEPUBに変換する。Karakeep-toolの tools/epub/karakeep_to_epub.py を使う依頼に対応する。"
---

# Karakeepの保存記事をEPUBに変換する

対象は `tools/epub/karakeep_to_epub.py`。ソースは固定コミットの `/srv/secretary/karakeep-tool` にある。

1. `secretary_tools__inspect` に `path="tools/epub/karakeep_to_epub.py"` を渡し、最新の導入状態、ソース、引数、必要データを確認する。`--help` を実行するだけで処理が走るツールもあるので、最初はソースを読む。
2. 指定された対象・件数・出力先に絞る。`data/` の原本を上書きせず、成果物の出力先を明示する。Macの絶対パス、NAS・SDカード、別repo、API設定が不足する場合は必要項目を具体的に伝える。
3. `secretary_tools__run` に `path="tools/epub/karakeep_to_epub.py"` と文字列配列 `args` を渡す。シェル文字列を組み立てず、フラグ・値を別々の要素にする。戻るjob IDを `secretary_tools__job_status` に渡して終了と成果物を確認する。
4. 対応する場合だけdry-run/planを利用する。未対応なのに `--dry-run` を付けない。外部更新・削除・一括処理は具体的な対象を提示して承認を受け、同じ範囲について会話で重複確認しない。健康診断としてバッチを起動しない。

引数候補（適用条件はソースで確認）: `--height`, `--img-mode`, `--out`, `--width`

注意:
- Macフォント参照あり。Linux用フォントの互換配置を利用する

ソースの使用説明:

```text
karakeepのブックマークをe-ink向けEPUBに変換する(標準ライブラリ + Pillowのみ)。

使い方:
  python3 karakeep_to_epub.py <bookmark_id または プレビューURL> [...]
  python3 karakeep_to_epub.py ID1 ID2 --out data/epub/output --width 528 --height 792

- 日本語記事: 縦書き(vertical-rl / page-progression-direction=rtl)、縦中横、禁則、ルビ保持
- 英語など  : 横書き。行間・余白をe-ink向けに調整
- 表紙      : ブックマークのバナー画像(なければ記事内の最大画像)をグレースケール化し、
              タイトルを重ねて生成
- 冒頭に karakeep の AI要約(summary)を挿入
接続情報は .env (URL, API_KEY)。
```
