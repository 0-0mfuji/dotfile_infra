#!/usr/bin/env python3
"""Refuse service replacement while managed local jobs are running."""
from pathlib import Path
import sys


def active_jobs(proc=Path('/proc')):
    found = []
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            argv = [x.decode(errors='replace') for x in (entry / 'cmdline').read_bytes().split(b'\0') if x]
        except OSError:
            continue
        if not argv or not Path(argv[0]).name.startswith('python'):
            continue
        scripts = [Path(x).name for x in argv[1:3]]
        if (any(x in scripts for x in ('convert_study_materials.py', 'yomitoku_worker.py', 'plamo-translate.py'))
                or ('secretary-tools.py' in scripts and 'worker' in argv[2:4])):
            found.append(entry.name)
    return found


if __name__ == '__main__':
    jobs = active_jobs()
    if jobs:
        print('Active secretary jobs: ' + ', '.join(jobs) +
              '. Wait for completion before provisioning; no services were stopped.', file=sys.stderr)
        sys.exit(1)
