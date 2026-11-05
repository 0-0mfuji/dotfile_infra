---
name: kt-build-new-free-materials
description: "Build X3-sized grayscale EPUBs from newly acquired public study PDFs.。Karakeep-toolの study/build_new_free_materials.py に対応する。"
---

# Build X3-sized grayscale EPUBs from newly acquired public study PDFs.

対象: `/srv/secretary/karakeep-tool/study/build_new_free_materials.py`

1. `secretary_tools__inspect` に `path="study/build_new_free_materials.py"` を渡し、ソースの引数・既定値・入出力・必要データを読む。ヘルプ非対応で実処理が始まるスクリプトもあるため、最初から実行しない。
2. ユーザーの指定した原本・件数・保存先に限定する。教材原本や既存EPUBを保全し、新しい出力先または対応するdry-run/planを使う。SDカード・NAS・ファームウェア・別repoが必要なら不足を具体的に示す。
3. `secretary_tools__run` に上記の `path` と文字列配列 `args` を渡す。返るjob IDを `secretary_tools__job_status(job_id=..., wait_seconds=45)` で確認し、終了・成果物・欠落を報告する。外部更新や削除は対象を示してツールの承認を受け、同じ依頼の重複確認はしない。

queued/runningなら同じjob_statusで再確認する。待機のためにshellのsleepや汎用Pythonを使わない。completedを確認してから成果物を報告し、失敗・中断を成功扱いしない。
4. OCRが必要なら `--yomitoku-python /opt/secretary-ocr/bin/python --device cuda` が対象ツールに対応するか確認する。PLaMo翻訳とのGPU同時実行を避ける。外部AIは別の認証・料金・通信が発生するため、ローカル処理から勝手に切り替えない。

制約:
- 必要な教材原本・モデル・端末・NAS・追加ソースをinspectで確認する。データや依存ソースはGit cloneだけでは揃わない

引数候補: 位置引数・ソース内の設定を確認する

ソースの説明:

```text
Build X3-sized grayscale EPUBs from newly acquired public study PDFs.

Only files listed in MATERIALS are processed. Source PDFs stay untouched;
the EPUBs contain page images capped at 528x792 pixels in grayscale JPEG.
Run from the repository root with the documented bundled PyMuPDF path.
```
