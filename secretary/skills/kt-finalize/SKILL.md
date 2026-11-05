---
name: kt-finalize
description: "書籍の出力・配置・仕上げ処理を行う。Karakeep-toolの books/finalize.py を使う依頼に対応する。"
---

# 書籍の出力・配置・仕上げ処理を行う

対象は `books/finalize.py`。ソースは固定コミットの `/srv/secretary/karakeep-tool` にある。

1. `secretary_tools__inspect` に `path="books/finalize.py"` を渡し、最新の導入状態、ソース、引数、必要データを確認する。`--help` を実行するだけで処理が走るツールもあるので、最初はソースを読む。
2. 指定された対象・件数・出力先に絞る。`data/` の原本を上書きせず、成果物の出力先を明示する。Macの絶対パス、NAS・SDカード、別repo、API設定が不足する場合は必要項目を具体的に伝える。
3. `secretary_tools__run` に `path="books/finalize.py"` と文字列配列 `args` を渡す。シェル文字列を組み立てず、フラグ・値を別々の要素にする。戻るjob IDを `secretary_tools__job_status` に渡して終了と成果物を確認する。
4. 対応する場合だけdry-run/planを利用する。未対応なのに `--dry-run` を付けない。外部更新・削除・一括処理は具体的な対象を提示して承認を受け、同じ範囲について会話で重複確認しない。健康診断としてバッチを起動しない。

引数候補（適用条件はソースで確認）: `--all`, `--dry`, `--max-tokens`, `--out`, `--skip-existing`

注意:
- Macのマウントパスあり。Linux側のマウント先を指定・移植する

ソースの使用説明:

```text
取得・変換が終わった本を、GPT-Lunaで難易度判定し、フォルダ配置してSDカードへコピーする。

  python3 finalize.py tasks     # 判定用のメタデータ(題名・作者・生没年・長さ・分類のみ。本文なし)を作る
  python3 finalize.py luna      # Batch APIで判定(送信→完了待ち→取り込み→失敗分の再送)
  python3 finalize.py place     # 難易度(言語ごとの四分位)・ジャンル・作者でフォルダ配置し、題名を「作品　紹介」(全角スペース区切り)に付け替える
  python3 finalize.py sd        # SDカードへコピー(空き容量を確認し、検証する)
配置: <言語>の本/<初級|中級|上級>/<ジャンル>/<作者>/題名　紹介.epub    (青空文庫は 青空文庫/<ジャンル>/<作者>/…)
```
