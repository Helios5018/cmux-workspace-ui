"""Serialize read/modify/write of workspace descriptions across local workers."""
from contextlib import contextmanager
import fcntl
import json
import os
import subprocess

from sentinel_config import CMUX, STATE

DATA_MARKER = '\nsentinel-tmux:'


@contextmanager
def metadata_lock():
    STATE.mkdir(parents=True, exist_ok=True)
    with os.fdopen(os.open(STATE / 'sidebar-metadata.lock', os.O_CREAT | os.O_RDWR, 0o600), 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def matches(row, labels):
    title = row.get('title') or ''
    return any(title == label or title.startswith(label + ' ') for label in labels)


def update_descriptions(transform):
    """transform(rows) returns (row, new_description) pairs for each window."""
    changed = False
    with metadata_lock():
        windows = json.loads(subprocess.check_output(
            [CMUX, '--id-format', 'both', 'list-windows', '--json'], timeout=15))
        for window in windows:
            win = window.get('id') or window['ref']
            rows = json.loads(subprocess.check_output(
                [CMUX, 'rpc', 'extension.sidebar.snapshot', json.dumps({'window_id': win})],
                timeout=15))['workspaces']
            for row, description in transform(rows):
                if description == (row.get('description') or ''):
                    continue
                subprocess.run([CMUX, 'workspace-action', '--workspace', row.get('id') or row['ref'],
                                '--window', win, '--action', 'set-description',
                                '--description', description], check=True, capture_output=True, timeout=15)
                changed = True
    return changed


def stamp(labels, epoch):
    def transform(rows):
        for row in rows:
            if matches(row, labels):
                description = row.get('description') or ''
                head, marker, metadata = description.partition(DATA_MARKER)
                lines = [line for line in head.splitlines() if not line.startswith('sentinel-updated:')]
                head = '\n'.join(['sentinel-updated:' + str(epoch), *lines]).rstrip('\n')
                yield row, head + (marker + metadata if marker else '')
    return update_descriptions(transform)


def publish(payload):
    def transform(rows):
        if not rows:
            return
        # Reuse a meter when possible; tmux also works without any enabled provider.
        carrier = min(rows, key=lambda r: (
            0 if matches(r, ('cx7d',)) else 1 if matches(r, ('cx5h',)) else
            2 if matches(r, ('grokcredits',)) else 3,
            r.get('index', 0)))
        encoded = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
        for row in rows:
            description = row.get('description') or ''
            head = description.partition(DATA_MARKER)[0]
            if row is carrier:
                yield row, head + DATA_MARKER + encoded
            elif DATA_MARKER in description:
                yield row, head  # Remove an obsolete carrier when the preferred one returns.
    return update_descriptions(transform)
