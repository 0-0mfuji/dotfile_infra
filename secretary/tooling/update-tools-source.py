"""Apply an additive study-only source update; retain dirty trees and running jobs."""
from pathlib import Path
import subprocess
import sys

repo=Path('/srv/secretary/karakeep-tool')
def git(*args):
    return subprocess.check_output(['git','-c','safe.directory='+str(repo),'-C',str(repo),*args],text=True).strip()
if git('status','--porcelain','--untracked-files=normal'):
    raise SystemExit('Tool worktree has changes; preserve and reconcile them on Mac first')
bundle,commit=sys.argv[1:]
git('fetch',bundle,'refs/heads/secretary-release')
subprocess.run(['git','-c','safe.directory='+str(repo),'-C',str(repo),'merge-base','--is-ancestor','HEAD',commit],check=True)
changed=git('diff','--name-only','HEAD',commit).splitlines()
if any(not name.startswith('study/') for name in changed):
    raise SystemExit('This updater only supports study/ changes; use the full provisioner')
active={'convert_study_materials.py','build_gemini_reflow.py','repair_study_display.py','readable_epub_prose.py','study-resume.py'}
for process in Path('/proc').iterdir():
    if not process.name.isdigit():continue
    try:args=process.joinpath('cmdline').read_bytes().split(b'\0')
    except (OSError,PermissionError):continue
    if any(Path(a.decode(errors='replace')).name in active for a in args if a):
        raise SystemExit('Study conversion/repair is active; retry after it finishes (not stopped)')
git('checkout','--detach',commit)
if git('status','--porcelain','--untracked-files=normal'):
    raise SystemExit('Unexpected source changes after update')
print('Updated pinned study source:',git('rev-parse','HEAD'))
