---
name: kt-medical-search
description: "医学関連の公開書籍を検索する。Karakeep-toolの books/medical_search.py を使う依頼に対応する。"
---

# 医学関連の公開書籍を検索する

医学書・学習教材の変換状況は `secretary_tools__study_status`（`scope="medical"|"nonmedical"|"all"`）で確認する。GPU可否は `secretary_tools__gpu_diagnostics` を使う。shell/filesの隔離環境からGPUなし・データなしと断定しない。進捗確認に汎用runのstatusやシェル探索を使わず、変換を再開しない。保存記録と現在の実行状態を分け、移行前のMac絶対パスやパス由来のジョブIDは再開前に整合が必要と伝える。

EPUBを作成・提供する依頼では、完成後に `secretary_tools__export_epub` を使う。`path` はKarakeep-toolからの相対パス（文書領域なら `source="documents"`）。保存先が不明なら `secretary_tools__list_epubs` で探し、shellのfind/lsを使わない。返る `workspace_path` を成果物として案内し、NanoMuseではカードを開いてダウンロードできると伝える。本文を会話に読み込まず、URLやボタンを捏造しない。進捗確認だけの依頼では実行しない。

対象は `books/medical_search.py`。ソースは固定コミットの `/srv/secretary/karakeep-tool` にある。

1. `secretary_tools__inspect` に `path="books/medical_search.py"` を渡し、最新の導入状態、ソース、引数、必要データを確認する。`--help` を実行するだけで処理が走るツールもあるので、最初はソースを読む。
2. 指定された対象・件数・出力先に絞る。`data/` の原本を上書きせず、成果物の出力先を明示する。Macの絶対パス、NAS・SDカード、別repo、API設定が不足する場合は必要項目を具体的に伝える。
3. `secretary_tools__run` に `path="books/medical_search.py"` と文字列配列 `args` を渡す。シェル文字列を組み立てず、フラグ・値を別々の要素にする。戻るjob IDを `secretary_tools__job_status(job_id=..., wait_seconds=45)` に渡して終了と成果物を確認する。

queued/runningなら同じjob_statusで再確認する。待機のためにshellのsleepや汎用Pythonを使わない。completedを確認してから成果物を報告し、失敗・中断を成功扱いしない。
4. 対応する場合だけdry-run/planを利用する。未対応なのに `--dry-run` を付けない。外部更新・削除・一括処理は具体的な対象を提示して承認を受け、同じ範囲について会話で重複確認しない。健康診断としてバッチを起動しない。

引数候補（適用条件はソースで確認）: 位置引数またはソース内設定。inspectで確認する。

ソースの使用説明:

```text
medical_list.py の候補を、Europe PMC / Wikisource(en,de,fr) / Internet Archive で検索し、取得可否を cache/medical_avail.json と medical_candidates.md に出す(取得はしない)。
```
