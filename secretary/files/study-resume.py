#!/usr/bin/env python3
"""Verified Linux resume without changing the imported Mac library."""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

REPO = Path('/srv/secretary/karakeep-tool')
OLD = REPO / 'data/study/text-reflow-library'
DEST = REPO / 'data/study/text-reflow-linux'
STATE = Path('/home/secretary/.config/secretary/tool-jobs')
INSTALL = Path('/opt/secretary')
PYTHON = '/opt/secretary-tools/bin/python'
PROFILE = dict(engine='yomitoku', adapter_version=5, confidence=0.9, yomitoku='0.15.1',
               models=[], tesseract=False, dpi=300, volume_pages=40)
PROFILE_ID = hashlib.sha256(json.dumps(PROFILE, sort_keys=True).encode()).hexdigest()[:12]


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(path, value):
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def verified_converter():
    target = REPO / 'study/convert_study_materials.py'
    catalog = json.loads((INSTALL / 'catalog.json').read_text())
    entry = next(e for e in catalog['tools'] if e['path'] == 'study/convert_study_materials.py')
    if digest(target) != entry['sha256']:
        raise ValueError('converter differs from the reviewed revision')
    sys.path.insert(0, str(target.parent))
    spec = importlib.util.spec_from_file_location('resume_converter', target)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def current_plan():
    module = verified_converter()
    return module.discover(argparse.Namespace(input=None, catalog=module.DEFAULT_CATALOG,
                                              scope='all', book_title=None))


def source_suffix(path):
    if '/data/study/' not in str(path):
        raise ValueError('unrecognized study source path')
    return str(path).split('/data/study/', 1)[1]


def migration_plan(plan):
    by_source = {source_suffix(j['path']): j for j in plan['jobs']}
    records = []
    for record in sorted(OLD.glob('books/*/3e66ab34f484/job.json')):
        data = json.loads(record.read_text())
        if not data.get('job', {}).get('path', '').startswith('/Users/'):
            continue
        if data.get('status') not in ('converted_draft', 'stopped_low_disk'):
            continue
        profile = dict(data['profile'])
        profile['tesseract'] = False
        if profile != PROFILE:
            raise ValueError('primary OCR settings differ; cannot reuse ' + str(record))
        job = by_source.get(source_suffix(data['job']['path']))
        if job is None:
            raise ValueError('imported source is absent from the current plan: ' + data['job']['path'])
        source = Path(job['path']).resolve()
        if not source.is_relative_to((REPO / 'data/study').resolve()) or not source.is_file():
            raise ValueError('source outside the managed study data')
        if digest(source) != data['source_sha256']:
            raise ValueError('source checksum mismatch: ' + str(source))
        # Skip/reuse decisions also depend on auxiliary source metadata.
        dependencies = {}
        if job.get('exercise_metadata'):
            meta = Path(job['exercise_metadata'])
            dependencies['exercise_metadata_sha256'] = digest(meta)
            values = json.loads(meta.read_text())
            for key in ('source', 'answer_source'):
                dependencies[key] = digest(REPO / 'data/study' / values[key])
        if dependencies != data.get('dependencies', {}):
            raise ValueError('auxiliary source checksum mismatch: ' + str(source))
        old_repo = Path(data['job']['path'].split('/data/study/', 1)[0])
        old_folder = old_repo / 'data/study/text-reflow-library/books' / record.parent.parent.name / record.parent.name
        final = DEST / 'books' / job['id'] / PROFILE_ID
        if data['status'] == 'converted_draft' and not data.get('outputs'):
            raise ValueError('completed record has no outputs')
        for output in data.get('outputs', []):
            mapped = Path(remap(output, old_folder, final, old_repo)).resolve()
            if not mapped.is_relative_to(final.resolve()) or not (record.parent / mapped.relative_to(final.resolve())).is_file():
                raise ValueError('imported output missing or outside its conversion folder: ' + output)
        records.append((record, data, job))
    if not records:
        raise ValueError('no verified imported records found')
    if len({j['id'] for _, _, j in records}) != len(records):
        raise ValueError('multiple imported records map to one current job')
    return records


def copy_independent(source, target):
    """Use filesystem CoW if supported; never share mutable hard links."""
    try:
        with open(source, 'rb') as old, open(target, 'xb') as new:
            fcntl.ioctl(new.fileno(), 0x40049409, old.fileno())  # Linux FICLONE
        shutil.copystat(source, target)
    except OSError:
        Path(target).unlink(missing_ok=True)
        shutil.copy2(source, target)
    return target


def remap(value, old_folder, new_folder, old_repo):
    if isinstance(value, str):
        relative_folder = str(old_folder.relative_to(old_repo))
        if value == relative_folder or value.startswith(relative_folder + '/'):
            return str(new_folder) + value[len(relative_folder):]
        if value == str(old_folder) or value.startswith(str(old_folder) + '/'):
            return str(new_folder) + value[len(str(old_folder)):]
        if value == str(old_repo) or value.startswith(str(old_repo) + '/'):
            return str(REPO) + value[len(str(old_repo)):]
        return value
    if isinstance(value, list):
        return [remap(x, old_folder, new_folder, old_repo) for x in value]
    if isinstance(value, dict):
        return {k: remap(v, old_folder, new_folder, old_repo) for k, v in value.items()}
    return value


def prepare():
    if DEST.exists():
        manifest = DEST / 'migration.json'
        if not manifest.is_file():
            raise ValueError('resume directory already exists without migration metadata; preserve it')
        saved = json.loads(manifest.read_text())
        if saved.get('version') != 1 or saved.get('profile_id') != PROFILE_ID:
            raise ValueError('existing migration uses different settings; preserve and review it')
        return saved
    plan = current_plan()
    records = migration_plan(plan)
    needed = sum(p.stat().st_size for record, _, _ in records
                 for p in record.parent.rglob('*') if p.is_file())
    if shutil.disk_usage(OLD).free < needed + 5 * 1024**3:
        raise ValueError('insufficient free space to preserve the original library and copy its results')
    stage = Path(tempfile.mkdtemp(prefix='.study-linux-', dir=DEST.parent))
    try:
        completed = 0
        for record, data, job in records:
            original = record.parent
            target = stage / 'books' / job['id'] / PROFILE_ID
            final = DEST / 'books' / job['id'] / PROFILE_ID
            old_repo = Path(data['job']['path'].split('/data/study/', 1)[0])
            old_folder = old_repo / 'data/study/text-reflow-library/books' / original.parent.name / original.name
            # No symlinks or external tree references are copied as writable files.
            if any(p.is_symlink() for p in original.rglob('*')):
                raise ValueError('symlink in imported conversion tree')
            shutil.copytree(original, target, copy_function=copy_independent)
            for path in target.rglob('*.json'):
                before = json.loads(path.read_text())
                after = remap(before, old_folder, final, old_repo)
                if path.name == 'input.json' and path.parent.name == 'cache':
                    after['tesseract'] = False
                    if isinstance(after.get('batch_profile'), dict):
                        after['batch_profile']['tesseract'] = False
                if after != before:
                    save(path, after)
            migrated = remap(data, old_folder, final, old_repo)
            migrated.update(job=job, profile=PROFILE,
                            migration={'source_profile': original.name, 'source_job_id': original.parent.name,
                                       'source_sha256_verified': True,
                                       'comparison_ocr_disabled_for_new_pages': True})
            for filename, key in (('review-overrides.json', 'review_overrides_sha256'),
                                  ('reviewed-tables.json', 'reviewed_tables_sha256')):
                path = target / 'cache' / filename
                migrated[key] = digest(path) if path.exists() else None
            for name in migrated.get('outputs', []):
                output = Path(name)
                if not output.is_relative_to(final) or not (target / output.relative_to(final)).is_file():
                    raise ValueError('imported output missing or outside its conversion folder')
            save(target / 'job.json', migrated)
            completed += data['status'] == 'converted_draft'
            print(json.dumps({'phase': 'migrated', 'jobs': completed, 'job_id': job['id']}), flush=True)
        # A fixed available-input catalog makes unavailable sources explicit without
        # converting an otherwise successful available-input batch into exit 2.
        groups = []
        for job in plan['jobs']:
            group = {'sources': [job['path']], 'source_type': job['source_type'], 'sd_epubs': job.get('sd_epubs', [])}
            if job.get('exercise_metadata'):
                group['exercise_metadata'] = job['exercise_metadata']
            groups.append(group)
        save(stage / 'available-catalog.json', {'sources': groups})
        save(stage / 'plan.json', plan)
        save(stage / 'progress.json', {'profile_id': PROFILE_ID, 'phase': '移行済み・再開待ち', 'new_pages': 0})
        manifest = {'version': 1, 'prepared_at': time.time(), 'profile_id': PROFILE_ID,
                    'planned_jobs': len(plan['jobs']), 'retained_completed': completed,
                    'retained_partial': len(records) - completed, 'logical_copy_bytes': needed,
                    'unavailable_inputs': plan.get('missing', []), 'original_library_modified': False,
                    'original_root': str(OLD), 'output_root': str(DEST)}
        save(stage / 'migration.json', manifest)
        os.rename(stage, DEST)
        return manifest
    except BaseException:
        shutil.rmtree(stage)
        raise


def preflight(tesseract=False):
    verified_converter()
    jar = REPO / 'data/study/japan-medical-licensing/work/qa-tools/epubcheck-5.4.0/epubcheck.jar'
    for path in (Path('/usr/bin/java'), Path('/opt/secretary-ocr/bin/python'), jar):
        if not path.is_file():
            raise ValueError('missing runtime dependency: ' + str(path))
    subprocess.run(['/usr/bin/java', '-jar', str(jar), '--version'], check=True, capture_output=True, timeout=45)
    if tesseract:
        langs = subprocess.run(['/usr/bin/tesseract', '--list-langs'], check=True,
                               capture_output=True, text=True, timeout=15).stdout.splitlines()
        if not {'jpn', 'eng'}.issubset(set(langs)):
            raise ValueError('Tesseract Japanese/English language data missing')
    subprocess.run(['/opt/secretary-ocr/bin/python', '-c',
                    'import torch; assert torch.cuda.is_available(); assert (torch.ones(1,device="cuda")+1).item()==2'],
                   check=True, capture_output=True, timeout=45)
    if shutil.disk_usage(OLD).free < 6 * 1024**3:
        raise ValueError('at least 6 GiB free required before resuming')


def run():
    preflight()
    manifest = prepare()
    env = {'HOME': '/home/secretary', 'PATH': '/opt/secretary-tools/bin:/usr/local/bin:/usr/bin:/bin',
           'LANG': 'C.UTF-8', 'TZ': 'Asia/Tokyo', 'PYTHONUNBUFFERED': '1', 'PYTHONDONTWRITEBYTECODE': '1',
           'HF_HUB_OFFLINE': '1', 'HF_HUB_DISABLE_TELEMETRY': '1', 'TRANSFORMERS_OFFLINE': '1'}
    models = REPO / 'data/study/work/yomitoku-models'
    if not models.is_dir():
        raise ValueError('offline OCR models missing')
    command = ['/usr/local/lib/dev-dsh/bin/bwrap', '--die-with-parent', '--unshare-user', '--unshare-pid',
               '--unshare-net', '--ro-bind', '/', '/', '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp',
               '--bind', str(DEST), str(DEST), '--bind', str(models), str(models), '--',
               PYTHON, str(REPO / 'study/convert_study_materials.py'), 'run', '--scope', 'all',
               '--catalog', str(DEST / 'available-catalog.json'), '--output', str(DEST),
               '--engine', 'yomitoku', '--device', 'cuda', '--offline', '--dpi', '300',
               '--yomitoku-python', '/opt/secretary-ocr/bin/python', '--java', '/usr/bin/java',
               '--epubcheck-jar', str(REPO / 'data/study/japan-medical-licensing/work/qa-tools/epubcheck-5.4.0/epubcheck.jar'),
               '--min-free-gib', '5', '--json']
    save(DEST / 'resume-state.json', {'state': 'running', 'started': time.time(), 'pid': os.getpid(),
                                     'unavailable_inputs': len(manifest['unavailable_inputs'])})
    started = time.monotonic()
    with (DEST / 'resume.log').open('ab') as log:
        result = subprocess.run(command, cwd=REPO, env=env, stdout=log, stderr=log)
    save(DEST / 'resume-state.json', {'state': 'completed' if result.returncode == 0 else 'stopped',
                                     'exit_code': result.returncode, 'finished': time.time(),
                                     'elapsed_seconds': time.monotonic() - started,
                                     'unavailable_inputs': len(manifest['unavailable_inputs'])})
    return result.returncode


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['plan', 'prepare', 'run', 'status'])
    args = parser.parse_args()
    if args.command == 'status':
        for name in ('migration.json', 'resume-state.json', 'progress.json', 'run-status.json'):
            path = DEST / name
            if path.is_file():
                print(name, path.read_text())
        return 0
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / 'translation.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        spec = importlib.util.spec_from_file_location('tools', INSTALL / 'secretary-tools.py')
        tools = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tools)
        if any(pid != os.getpid() for pid in tools.active_ocr_processes()):
            raise ValueError('another OCR process is running')
        if args.command == 'run':
            return run()
        if args.command == 'prepare':
            preflight()
            print(json.dumps(prepare(), ensure_ascii=False))
        else:
            plan = current_plan()
            records = migration_plan(plan)
            print(json.dumps({'planned_jobs': len(plan['jobs']), 'reusable_records': len(records),
                              'completed': sum(d['status'] == 'converted_draft' for _, d, _ in records),
                              'unavailable_inputs': plan.get('missing', []), 'profile_id': PROFILE_ID}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as error:
        print(type(error).__name__ + ': ' + str(error), file=sys.stderr)
        sys.exit(1)
