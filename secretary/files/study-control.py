#!/usr/bin/env python3
"""Consume a local fixed resume request; never execute request-supplied strings."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import time
import tempfile

STATE = Path('/home/secretary/.config/secretary/tool-jobs')


def update(action):
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / 'study-control.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = STATE / 'study-resume-request.json'
        if not path.is_file() or path.is_symlink() or path.stat().st_size > 4096:
            return 'none'
        request = json.loads(path.read_text())
        if not isinstance(request, dict) or set(request) - {'request_id', 'state', 'created', 'updated_at', 'error'}:
            return 'none'
        if not re.fullmatch('[a-f0-9]{32}', str(request.get('request_id', ''))):
            return 'none'
        if action == 'claim':
            if request.get('state') != 'queued':
                return 'none'
            if not isinstance(request.get('created'), (float, int)) or not 0 <= time.time() - request['created'] <= 600:
                request.update(state='failed', error='request expired')
                result = 'none'
            else:
                request['state'] = 'claimed'
                result = 'start'
        else:
            if request.get('state') != 'claimed':
                return 'none'
            request['state'] = 'dispatched' if action == 'started' else 'failed'
            if action == 'failed':
                request['error'] = 'host could not start the managed service; operator check required'
            result = 'none'
        request['updated_at'] = time.time()
        fd, temporary = tempfile.mkstemp(dir=STATE)
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump(request, stream)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['claim', 'started', 'failed'])
    print(update(parser.parse_args().action))
