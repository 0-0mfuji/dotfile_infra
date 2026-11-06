---
name: kt-convert-study-materials
description: "医学書・学習教材EPUBの変換進捗、完了数・停止位置とGPU対応を専用ツールで確認する。変換計画・実行・再開の依頼にも対応。"
---

# Plan/run/resume all study-material OCR. Personal noncommercial use; no SD writes.

確認経路: 仕様は `secretary_tools__catalog` / `secretary_tools__inspect`、環境は `secretary_tools__doctor`、原本・保存先のファイル名検索は `secretary_tools__data_files`（`source="repository"` の既定は `directory="data"`、文書は `source="documents"`）を使う。結果が `truncated` ならディレクトリを絞る。本文検索や全件集計は行わないツールなので、件数を総数と解釈しない。準備確認にshellのls/find/grepやrunの--helpを使わない。進捗は専用status、ジョブ待機はjob_statusを使う。専用経路のない実処理は汎用runの通常の承認対象であり、安全扱いに変更しない。

医学書・学習教材の変換状況は `secretary_tools__study_status`（`scope="medical"|"nonmedical"|"all"`）で確認する。GPU可否は `secretary_tools__gpu_diagnostics` を使う。shell/filesの隔離環境からGPUなし・データなしと断定しない。進捗確認に汎用runのstatusやシェル探索を使わず、変換を再開しない。保存記録と現在の実行状態を分け、移行前のMac絶対パスやパス由来のジョブIDは再開前に整合が必要と伝える。

EPUBを作成・提供する依頼では、完成後に `secretary_tools__export_epub` を使う。`path` はKarakeep-toolからの相対パス（文書領域なら `source="documents"`）。保存先が不明なら `secretary_tools__list_epubs` で探し、shellのfind/lsを使わない。返る `workspace_path` を成果物として案内し、NanoMuseではカードを開いてダウンロードできると伝える。本文を会話に読み込まず、URLやボタンを捏造しない。進捗確認だけの依頼では実行しない。

対象: `/srv/secretary/karakeep-tool/study/convert_study_materials.py`

1. `secretary_tools__inspect` に `path="study/convert_study_materials.py"` を渡し、ソースの引数・既定値・入出力・必要データを読む。ヘルプ非対応で実処理が始まるスクリプトもあるため、最初から実行しない。
2. ユーザーの指定した原本・件数・保存先に限定する。教材原本や既存EPUBを保全し、新しい出力先または対応するdry-run/planを使う。SDカード・NAS・ファームウェア・別repoが必要なら不足を具体的に示す。
3. 速度確認・見本変換は `secretary_tools__study_sample(input_file="data/study/...pdf", first_page=1, page_count=8, dpi=300, device="cuda")` を1回だけ使う。input_fileはdata_filesで確認した相対パス。1回1〜16ページに限定し、新しい出力先、オフラインOCR、Linux Java、EPUB検査はツールが固定する。汎用runに--pagesを渡さない。300dpiを既定に保ち、200dpiへの変更は品質差を伴うので依頼がある場合だけ行う。
4. 返るjob_idを `secretary_tools__job_status(job_id=..., wait_seconds=45)` で待つ。完了後、elapsed_seconds、新規OCRページ数、DPI、成否を報告する。秒/ページにはモデル読込・EPUB作成と検査を含む。同条件の重複要求は既存job_idを返すので、再実行せず既存結果を確認する。
5. 「どうですか」は進捗確認。新しい試験や再試行を開始しない。最初の測定1件で結果を返し、並列数を2→4→6→8と自動拡大しない。OOM、引数エラー、入力不足、ツール上限で停止したら、その状態・job_id・完了分を報告する。追加実験はユーザーが具体的に依頼した範囲に限定する。
6. 速度比較は同じページ・DPI・新規キャッシュ・成功をそろえる。別ページの処理時間、キャッシュ再利用、並列ジョブの一部失敗から倍率を断定しない。EPUBCheck合格はOCR精度の保証ではない。
7. 全冊変換・残り全部・正式再開の依頼では、まず `secretary_tools__study_status(scope="all")` のruntimeを確認する。running/preparingなら既存処理を案内し、追加起動しない。stoppedなら `secretary_tools__study_resume` を1回だけ呼ぶ。引数は不要。queued/claimed/dispatchedは完了ではなく起動要求の状態であり、`study_status(scope="all", wait_seconds=45)` で最大2回確認する。ホスト未起動やfailedならその状態を伝えて止め、shellや汎用runで代用しない。管理者コマンドの所在探し、PATH確認、/opt探索、study-resume.pyのソース読取りも不要。保存済みrunningとruntime.stoppedが異なる場合はruntimeを優先する。626は利用可能な計画件数で、634という旧件数との差やmigrationの入力不足も明示する。

ツール呼出し上限に近づいたら追加処理を開始せず、job_id・条件・完了分・未完了を短い進捗文書へ保存する。履歴が不明でも「未実施」「依頼なし」と断定せず、study_statusのrecent_sample_jobsからjob_idを回復し、job_statusを確認する。

制約:
- 必要な教材原本・モデル・端末・NAS・追加ソースをinspectで確認する。データや依存ソースはGit cloneだけでは揃わない
- Mac固有パスあり。引数または環境変数でLinux用に変更できることを確認する

引数候補: --book-title, --catalog, --confidence, --device, --dpi, --engine, --epubcheck-jar, --gemini-models, --input, --java, --json, --max-new-pages, --min-free-gib, --offline, --output, --pages, --scope, --tesseract, --title, --volume-pages, --yomitoku-python

ソースの説明:

```text
Plan/run/resume all study-material OCR. Personal noncommercial use; no SD writes.

Default: local YomiToku. Gemini image requests occur only with --engine gemini
or hybrid. Existing EPUB text, links, spine order and question/answer separation
are preserved. PDFs are emitted as bounded, ordered volumes, never summarized.
```
