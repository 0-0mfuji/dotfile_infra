---
name: kt-karakeep-lists-to-epub
description: "Karakeepのリスト別にEPUB出力を計画・生成・修復する。Karakeep-toolの tools/epub/karakeep_lists_to_epub.py を使う依頼に対応する。"
---

# Karakeepのリスト別にEPUB出力を計画・生成・修復する

対象は `tools/epub/karakeep_lists_to_epub.py`。ソースは固定コミットの `/srv/secretary/karakeep-tool` にある。

1. `secretary_tools__inspect` に `path="tools/epub/karakeep_lists_to_epub.py"` を渡し、最新の導入状態、ソース、引数、必要データを確認する。`--help` を実行するだけで処理が走るツールもあるので、最初はソースを読む。
2. 指定された対象・件数・出力先に絞る。`data/` の原本を上書きせず、成果物の出力先を明示する。Macの絶対パス、NAS・SDカード、別repo、API設定が不足する場合は必要項目を具体的に伝える。
3. `secretary_tools__run` に `path="tools/epub/karakeep_lists_to_epub.py"` と文字列配列 `args` を渡す。シェル文字列を組み立てず、フラグ・値を別々の要素にする。戻るjob IDを `secretary_tools__job_status(job_id=..., wait_seconds=45)` に渡して終了と成果物を確認する。

runningなら同じjob_statusで再確認する。待機のためにshellのsleepや汎用Pythonを使わない。completedを確認してから成果物を報告し、失敗・中断を成功扱いしない。
4. 対応する場合だけdry-run/planを利用する。未対応なのに `--dry-run` を付けない。外部更新・削除・一括処理は具体的な対象を提示して承認を受け、同じ範囲について会話で重複確認しない。健康診断としてバッチを起動しない。

引数候補（適用条件はソースで確認）: `--dry-run`, `--height`, `--limit`, `--list`, `--max-link-ratio`, `--min-chars`, `--no-unclassified`, `--out`, `--width`, `--workers`

ソースの使用説明:

```text
karakeepのスマートリストごとに、読み物になる記事を1記事1冊のEPUBとして出力する。

使い方:
  python3 karakeep_lists_to_epub.py plan                 # 割り当て結果だけ表示(出力しない)
  python3 karakeep_lists_to_epub.py plan --list Rust     # 指定リスト(部分一致)のみ
  python3 karakeep_lists_to_epub.py build --list Rust    # EPUBを出力 (data/epub/output/<リスト名>/)
  python3 karakeep_lists_to_epub.py build --limit 5      # 各リスト最大5冊(試運転)

ルール:
- スマートリストのみ。タグ条件を持たないリスト(url:/is:だけ)は対象外
- 動画/SNS/通販などのドメイン、リンク以外(画像/PDF/メモ)は除外
- 本文が --min-chars 未満、リンク集(リンク文字の割合が高い)は除外
- 複数リストに該当する記事は、記事のタグとリスト検索条件のタグの一致率が最も高い1リストにだけ出力
  (同点は 一致数 > リストの絞り込みの細かさ > 名前順)
- 出力済みの記事は data/state/epub/epub_done.json に記録し、再実行時はスキップ
```
