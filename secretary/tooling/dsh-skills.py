#!/usr/bin/env python3
"""Copy managed skills with DSH tool names; preserve customized destination skills."""
import hashlib
import json
from pathlib import Path
import sys


def update_layout_guide(path):
    path = Path(path)
    start, end = '<!-- secretary-data-layout:start -->', '<!-- secretary-data-layout:end -->'
    block = start + '''
## 秘書のデータ配置と操作

作業領域は `/srv/secretary/documents`。原本・OCRキャッシュ・EPUBは
`/srv/secretary/karakeep-tool/data`、スキルは `~/.dsh/skills`、管理プログラムは `/opt/secretary`。
サンドボックス内のshellやファイルツールからdataが見えなくても、消失と判断しない。
所在探しは `mcp__secretary_tools__data_files`、EPUB検索は `mcp__secretary_tools__list_epubs`、
変換進捗は `mcp__secretary_tools__study_status(scope="all")` を使う。
全件再開の依頼でruntimeがstoppedなら `mcp__secretary_tools__study_resume` を1回使い、
`study_status(wait_seconds=45)` で確認する。実行中の重複起動、shellでのコマンド探し、汎用runへの代替は不要。
EPUBの任意修正は対象をexport_epubで作業領域へ独立コピーしてから行う。元EPUBと変換中のキャッシュを直接編集しない。
専用のkt-*スキルがあればinspectで仕様を確認し、そのMCP経路を使う。スキルの配置だけで全処理が検証済みとは扱わない。
NanoMuse専用のカードUIがDSHでも使えると断定せず、返されたworkspace_pathとDSHで利用できるファイルUIを案内する。
''' + end
    text = path.read_text() if path.exists() else ''
    if start in text and end in text:
        first, rest = text.split(start, 1)
        _, tail = rest.split(end, 1)
        text = first + block + tail
    else:
        text = text.rstrip() + '\n\n' + block + '\n'
    path.write_text(text)
    path.chmod(0o600)


def sync(source, destination, runtime='DSH'):
    source, destination = Path(source), Path(destination)
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = destination / '.secretary-managed.json'
    old = json.loads(stamp.read_text()) if stamp.exists() else {}
    new = {}
    planned = []
    for path in sorted(source.glob('*/SKILL.md')):
        target = destination / path.parent.name / 'SKILL.md'
        text = path.read_text().replace('secretary_tools__', 'mcp__secretary_tools__')
        text = text.replace('NanoMuseの会話モデルはOllama Cloud', runtime + 'で設定した会話モデルは外部サービス')
        text = text.replace('ツールの承認画面', runtime + 'の権限設定とユーザーの指示')
        if target.exists():
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            if old.get(path.parent.name) != digest:
                raise ValueError('Customized DSH skill was preserved; reconcile first: ' + path.parent.name)
        planned.append((target, text))
        new[path.parent.name] = hashlib.sha256(text.encode()).hexdigest()
    for target, text in planned:
        target.parent.mkdir(exist_ok=True, mode=0o700)
        target.write_text(text)
        target.chmod(0o600)
    stamp.write_text(json.dumps(new, indent=2))
    stamp.chmod(0o600)
    return len(new)


if __name__ == '__main__':
    runtime = sys.argv[3] if len(sys.argv) > 3 else 'DSH'
    print('DSH secretary skills:', sync(sys.argv[1], sys.argv[2], runtime))
    if runtime == 'DSH':
        update_layout_guide(Path(sys.argv[2]).parent / 'AGENTS.md')
