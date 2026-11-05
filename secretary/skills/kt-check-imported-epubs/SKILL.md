---
name: kt-check-imported-epubs
description: "Validate EPUB structure, all-source coverage, image profiles and EPUBCheck.。Karakeep-toolの study/check_imported_epubs.py に対応する。"
---

# Validate EPUB structure, all-source coverage, image profiles and EPUBCheck.

対象: `/srv/secretary/karakeep-tool/study/check_imported_epubs.py`

1. `secretary_tools__inspect` に `path="study/check_imported_epubs.py"` を渡し、ソースの引数・既定値・入出力・必要データを読む。ヘルプ非対応で実処理が始まるスクリプトもあるため、最初から実行しない。
2. ユーザーの指定した原本・件数・保存先に限定する。教材原本や既存EPUBを保全し、新しい出力先または対応するdry-run/planを使う。SDカード・NAS・ファームウェア・別repoが必要なら不足を具体的に示す。
3. `secretary_tools__run` に上記の `path` と文字列配列 `args` を渡す。返るjob IDを `secretary_tools__job_status` で確認し、終了・成果物・欠落を報告する。外部更新や削除は対象を示してツールの承認を受け、同じ依頼の重複確認はしない。
4. OCRが必要なら `--yomitoku-python /opt/secretary-ocr/bin/python --device cuda` が対象ツールに対応するか確認する。PLaMo翻訳とのGPU同時実行を避ける。外部AIは別の認証・料金・通信が発生するため、ローカル処理から勝手に切り替えない。

制約:
- 必要な教材原本・モデル・端末・NAS・追加ソースをinspectで確認する。データや依存ソースはGit cloneだけでは揃わない

引数候補: --epubcheck, --partial

ソースの説明:

```text
Validate EPUB structure, all-source coverage, image profiles and EPUBCheck.
```
