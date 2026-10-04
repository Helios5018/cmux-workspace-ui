#!/usr/bin/env python3
"""Publish tmux session details and scoped close actions into the sidebar."""
import argparse
import hashlib
import json
import subprocess
import time
from tmux_actions import action_url, identity, read_state, PENDING, requires_confirmation, LAYOUT
from sentinel_config import TMUX, each_cmux_socket
from sidebar_metadata import publish as publish_metadata

FIELDS = ('session_name', '@note', '@project', '@lifecycle', '@port',
          'session_windows', 'session_attached', 'session_created', 'pid', 'socket_path')


def row_key(row):
    return hashlib.sha256(json.dumps(identity(row), sort_keys=True).encode()).hexdigest()[:24]


def snapshot(rows):
    pending = read_state(PENDING)
    return {
        'layout': read_state(LAYOUT),
        'pending': next((row_key(r) for r in rows if identity(r) == pending), None),
        'sessions': [{
            'key': row_key(r), 'name': r['session_name'], 'note': r['@note'],
            'project': r['@project'], 'port': r['@port'],
            'lifecycle': {'persistent': '常驻', 'temporary': '临时'}.get(r['@lifecycle'], r['@lifecycle'] or '未标注'),
            'protected': requires_confirmation(r), 'windows': r['session_windows'],
            'attached': r['session_attached'], 'close_url': action_url(r, 'close'),
            'confirm_url': action_url(r, 'confirm-close'),
        } for r in rows],
    }


def publish(rows):
    return publish_metadata(snapshot(rows))


def update():
    rows = sessions()
    return each_cmux_socket(lambda: publish(rows))


def query(*args):
    return subprocess.run([TMUX, *args], capture_output=True, text=True, timeout=5)


def sessions():
    result = query('list-sessions', '-F', '#{session_id}')
    if result.returncode:
        if 'no server running' in result.stderr or 'No such file' in result.stderr:
            return []
        raise RuntimeError('tmux list-sessions failed')
    rows = []
    for session_id in result.stdout.splitlines():
        row = {'id': session_id}
        for field in FIELDS:
            # One field per call preserves tabs/newlines inside user-authored notes.
            value = query('display-message', '-p', '-t', session_id, '#{' + field + '}')
            if value.returncode:
                break  # Session closed during the snapshot; retry next cycle.
            row[field] = value.stdout.rstrip('\n')
        else:
            rows.append(row)
    return sorted(rows, key=lambda r: r['session_name'].casefold())


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--renderer', choices=('js', 'swift'), default='js')
    args = parser.parse_args()
    while True:
        try:
            if args.renderer == 'swift':
                from tmux_swift import update as update_swift
                update_swift()
            else:
                update()
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            print('sidebar refresh failed: ' + type(error).__name__, flush=True)
            if args.once:
                raise SystemExit(1)
        if args.once:
            break
        time.sleep(5)
