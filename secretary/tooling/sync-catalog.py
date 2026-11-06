#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Catalog tracked scripts and add per-entrypoint skills without overwriting hand edits."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess


def sync(repo, secretary):
    catalog_path = secretary / 'tooling/catalog.json'
    old = json.loads(catalog_path.read_text())
    previous = {x['path']: x for x in old['tools']}
    files = subprocess.check_output(['git', '-C', str(repo), 'ls-files'], text=True).splitlines()
    files = [x for x in files if Path(x).suffix in {'.py', '.sh', '.cjs', '.swift', '.java'}]
    sources = {x: subprocess.check_output(['git', '-C', str(repo), 'show', 'HEAD:' + x], text=True) for x in files}
    imported = set()
    for path, source in sources.items():
        if path.endswith('.py'):
            for node in ast.walk(ast.parse(source)):
                if isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split('.')[0])
                elif isinstance(node, ast.Import):
                    imported.update(x.name.split('.')[0] for x in node.names)
    entries = []
    for path, source in sources.items():
        stem = Path(path).stem
        doc = ast.get_docstring(ast.parse(source)) or '' if path.endswith('.py') else ''
        helper = '/tests/' in path or stem.startswith('test_') or stem == '__init__'
        if path in previous:
            helper = previous[path]['helper']
        elif stem in imported and '__main__' not in source:
            helper = True
        name = 'kt-' + stem.replace('_', '-').lower()
        if Path(path).suffix != '.py':
            name += '-' + {'.sh': 'shell', '.cjs': 'node', '.swift': 'swift', '.java': 'java'}[Path(path).suffix]
        description = previous.get(path, {}).get('description') or (doc.splitlines()[0] if doc else '教材・書籍処理: ' + stem.replace('_', ' '))
        notes = previous.get(path, {}).get('notes', [])
        if path.endswith('.swift'):
            notes = ['macOS Visionを使うSwiftツール。Debian上では実行不可。Mac側の処理として利用する']
        elif path.startswith('study/'):
            notes = ['必要な教材原本・モデル・端末・NAS・追加ソースをinspectで確認する。データや依存ソースはGit cloneだけでは揃わない']
            if '/Volumes/' in source or '/Applications/' in source or '/Users/' in source:
                notes += ['Mac固有パスあり。引数または環境変数でLinux用に変更できることを確認する']
        entry = {'path': path, 'name': name, 'description': description[:350], 'helper': helper,
                 'sha256': hashlib.sha256(source.encode()).hexdigest(),
                 'options': sorted(set(re.findall(r'[\"\'](--[a-z][a-z0-9-]*)[\"\']', source))), 'notes': notes}
        entries.append(entry)
        if helper:
            continue
        folder = secretary / 'skills' / name
        if (folder / 'SKILL.md').exists():
            continue
        folder.mkdir(parents=True, exist_ok=True)
        text = f'''---
name: {name}
description: {json.dumps(description[:350]+'。Karakeep-toolの '+path+' に対応する。',ensure_ascii=False)}
---

# {description.splitlines()[0]}

対象: `/srv/secretary/karakeep-tool/{path}`

1. `secretary_tools__inspect` に `path="{path}"` を渡し、ソースの引数・既定値・入出力・必要データを読む。ヘルプ非対応で実処理が始まるスクリプトもあるため、最初から実行しない。
2. ユーザーの指定した原本・件数・保存先に限定する。教材原本や既存EPUBを保全し、新しい出力先または対応するdry-run/planを使う。SDカード・NAS・ファームウェア・別repoが必要なら不足を具体的に示す。
3. `secretary_tools__run` に上記の `path` と文字列配列 `args` を渡す。返るjob IDを `secretary_tools__job_status(job_id=..., wait_seconds=45)` で確認し、終了・成果物・欠落を報告する。外部更新や削除は対象を示してツールの承認を受け、同じ依頼の重複確認はしない。
queued/runningなら同じjob_statusで再確認する。待機のためにshellのsleepや汎用Pythonを使わない。completedを確認してから成果物を報告し、失敗・中断を成功扱いしない。
4. OCRが必要なら `--yomitoku-python /opt/secretary-ocr/bin/python --device cuda` が対象ツールに対応するか確認する。PLaMo翻訳とのGPU同時実行を避ける。外部AIは別の認証・料金・通信が発生するため、ローカル処理から勝手に切り替えない。

EPUBを作成・提供する依頼では、完成後に `secretary_tools__export_epub` を使う。`path` はKarakeep-toolからの相対パス（文書領域なら `source="documents"`）。保存先が不明なら `secretary_tools__list_epubs` で探し、shellのfind/lsを使わない。返る `workspace_path` を成果物として案内し、NanoMuseではカードを開いてダウンロードできると伝える。本文を会話に読み込まず、URLやボタンを捏造しない。進捗確認だけの依頼では実行しない。

医学書・学習教材の変換状況は `secretary_tools__study_status`（`scope="medical"|"nonmedical"|"all"`）で確認する。GPU可否は `secretary_tools__gpu_diagnostics` を使う。shell/filesの隔離環境からGPUなし・データなしと断定しない。進捗確認に汎用runのstatusやシェル探索を使わず、変換を再開しない。保存記録と現在の実行状態を分け、移行前のMac絶対パスやパス由来のジョブIDは再開前に整合が必要と伝える。

制約:
'''+''.join('- '+n+'\n' for n in notes)+f'\n引数候補: {", ".join(entry["options"]) or "位置引数・ソース内の設定を確認する"}\n'
        if doc:
            text += '\nソースの説明:\n\n```text\n' + doc[:4500] + '\n```\n'
        (folder / 'SKILL.md').write_text(text)
    names = [x['name'] for x in entries if not x['helper']]
    if len(names) != len(set(names)):
        raise ValueError('skill name collision')
    old.update(commit=subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip(), tools=entries)
    catalog_path.write_text(json.dumps(old, ensure_ascii=False, indent=2) + '\n')
    print(len(entries), 'scripts;', len(names), 'entrypoint skills')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('repository', type=Path)
    args = parser.parse_args()
    sync(args.repository, Path(__file__).resolve().parents[1])
