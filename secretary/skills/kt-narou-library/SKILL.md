---
name: kt-narou-library
description: "小説家になろうの取得進捗・完了数・途中保存・停止状況を確認する。なろう取得がどこまで終わったか、再開地点を知りたい依頼で使う。候補収集・取得計画にも対応。"
---

# 公式APIの人気作品候補と、明示実行する逐次EPUB取得コマンド。Python 3.10+。

確認経路: 仕様は `secretary_tools__catalog` / `secretary_tools__inspect`、環境は `secretary_tools__doctor`、原本・保存先のファイル名検索は `secretary_tools__data_files`（`source="repository"` の既定は `directory="data"`、文書は `source="documents"`）を使う。結果が `truncated` ならディレクトリを絞る。本文検索や全件集計は行わないツールなので、件数を総数と解釈しない。準備確認にshellのls/find/grepやrunの--helpを使わない。進捗は専用status、ジョブ待機はjob_statusを使う。専用経路のない実処理は汎用runの通常の承認対象であり、安全扱いに変更しない。

医学書・学習教材の変換状況は `secretary_tools__study_status`（`scope="medical"|"nonmedical"|"all"`）で確認する。GPU可否は `secretary_tools__gpu_diagnostics` を使う。shell/filesの隔離環境からGPUなし・データなしと断定しない。進捗確認に汎用runのstatusやシェル探索を使わず、変換を再開しない。保存記録と現在の実行状態を分け、移行前のMac絶対パスやパス由来のジョブIDは再開前に整合が必要と伝える。

EPUBを作成・提供する依頼では、完成後に `secretary_tools__export_epub` を使う。`path` はKarakeep-toolからの相対パス（文書領域なら `source="documents"`）。保存先が不明なら `secretary_tools__list_epubs` で探し、shellのfind/lsを使わない。返る `workspace_path` を成果物として案内し、NanoMuseではカードを開いてダウンロードできると伝える。本文を会話に読み込まず、URLやボタンを捏造しない。進捗確認だけの依頼では実行しない。

## 進捗を知りたい場合

最初に `secretary_tools__narou_status` を引数なしで呼ぶ。job IDは不要。候補数、completed_candidates、partialの保存話数、last_batch_record、running_process_idsを使って回答する。

- shell/filesは文書workspaceしか見えなくても、専用MCPは固定データ領域を読める。grep/find/lsやマウント全体の探索で代用しない。extra_rootsの変更やシェルの常時許可を依頼しない。
- 状態確認のためにcollect/downloadを実行しない。collectは新規収集、downloadは計画・取得操作であり、進捗集計ではない。
- EPUB数は本文の完全性や最新話までの取得を保証しない。TXTの行数を話数としない。保存話数はチェックポイントで、候補ファイルの総話数は古い場合がある。
- PIDは秘書コンテナ内だけの情報。Mac側のプロセスまで停止と断定しない。記録のUTC時刻は日本時間に直して示す。
- ツールが使えなければ不足を伝えて止める。取得の再実行や無関係なPlane・Karakeep・メモの探索を始めない。

## 新しい収集・取得を依頼された場合

対象: `/srv/secretary/karakeep-tool/books/narou_library.py`

1. `secretary_tools__inspect` に `path="books/narou_library.py"` を渡し、ソースの引数・既定値・入出力・必要データを読む。ヘルプ非対応で実処理が始まるスクリプトもあるため、最初から実行しない。
2. ユーザーの指定した原本・件数・保存先に限定する。教材原本や既存EPUBを保全し、新しい出力先または対応するdry-run/planを使う。SDカード・NAS・ファームウェア・別repoが必要なら不足を具体的に示す。
3. `secretary_tools__run` に上記の `path` と文字列配列 `args` を渡す。返るjob IDを `secretary_tools__job_status(job_id=..., wait_seconds=45)` で確認し、終了・成果物・欠落を報告する。外部更新や削除は対象を示してツールの承認を受け、同じ依頼の重複確認はしない。

queued/runningなら同じjob_statusで再確認する。待機のためにshellのsleepや汎用Pythonを使わない。completedを確認してから成果物を報告し、失敗・中断を成功扱いしない。
4. OCRが必要なら `--yomitoku-python /opt/secretary-ocr/bin/python --device cuda` が対象ツールに対応するか確認する。PLaMo翻訳とのGPU同時実行を避ける。外部AIは別の認証・料金・通信が発生するため、ローカル処理から勝手に切り替えない。

制約:

引数候補: --count, --delay, --downloader, --execute, --limit, --manifest, --output, --reserve-gib

上位コマンドに `--resume` はない。再開が明示された場合も、既存TXTへのresume引数は取得プログラム側が自動設定する。進捗確認だけでは再開しない。

ソースの説明:

```text
公式APIの人気作品候補と、明示実行する逐次EPUB取得コマンド。Python 3.10+。
```
