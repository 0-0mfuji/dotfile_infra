#!/usr/bin/env python3
"""Seed the official web locale preference before the dashboard app starts.

Hermes v0.22.5 ships Japanese but defaults to English unless hermes-locale is
present in browser storage. Leave user choices intact; do not patch the agent
source or rebuild its bundles. Reapply to the generated HTML after upgrades.
"""
from pathlib import Path
import argparse
import os
import tempfile

MARKER = '<!-- secretary default web locale -->'
SCRIPT = '''<!-- secretary default web locale -->
    <script>
      try {
        if (localStorage.getItem("hermes-locale") === null) {
          localStorage.setItem("hermes-locale", "ja");
        }
      } catch { /* Browser storage may be unavailable. */ }
    </script>'''


def seed(index):
    text = index.read_text()
    if MARKER in text:
        return False
    if '<head>' not in text:
        raise ValueError('Hermes dashboard HTML has no head; locale seed was not applied')
    stat = index.stat()
    updated = text.replace('<head>', '<head>\n    ' + SCRIPT, 1)
    fd, temporary = tempfile.mkstemp(dir=index.parent)
    try:
        with os.fdopen(fd, 'w') as out:
            out.write(updated)
        os.chmod(temporary, stat.st_mode & 0o777)
        os.replace(temporary, index)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('index', type=Path)
    args = parser.parse_args()
    print('Japanese web default: ' + ('applied' if seed(args.index) else 'already applied'))
