#!/usr/bin/env python3
"""Persistent tmux worker. Poll account usage without sending model requests."""
import datetime
import json
import os
import subprocess
import sys
import time

from sentinel_config import SOURCE as ROOT, USAGE_STATE as STATE, PROVIDERS, cmux_socket_paths, using_cmux_socket, poller
from sidebar_metadata import stamp


def stamp_shell(output, labels):
    # The shell poller reports only completely painted instances. Never make a
    # failed instance look fresh just because another instance was updated.
    allowed = cmux_socket_paths()
    paths = list(dict.fromkeys(line.removeprefix('sentinel-socket-updated:')
                              for line in output.splitlines()
                              if line.startswith('sentinel-socket-updated:')))
    success = False
    for path in paths:
        if path not in allowed:
            continue
        try:
            with using_cmux_socket(path):
                stamp(labels, int(time.time()))
            success = True
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            print('Usage freshness write failed: ' + type(exc).__name__, file=sys.stderr)
    return success


def stamp_codex(output):
    return stamp_shell(output, ('cx5h', 'cx7d'))


def cycle():
    status = {}
    for provider, command in (
        ('claude', [str(poller('claude')), '--update']),
        ('codex', [str(poller('codex')), '--update']),
        ('grok', [sys.executable, str(ROOT / 'grok_usage.py'), '--update']),
        ('opencode-go', [sys.executable, str(ROOT / 'opencode_go_usage.py'), '--update']),
    ):
        if provider not in PROVIDERS:
            continue
        try:
            result = subprocess.run(command, timeout=100, capture_output=True, text=True)
            status[provider] = 'ok' if result.returncode == 0 else 'error'
            if provider == 'codex' and result.returncode == 0:
                status[provider] = 'ok' if stamp_codex(result.stdout) else 'error'
            if provider == 'claude' and result.returncode == 0:
                status[provider] = 'ok' if stamp_shell(result.stdout, ('5h', '7d', 'm7d', 'spend')) else 'error'
        except (OSError, ValueError, subprocess.SubprocessError):
            status[provider] = 'error'
    STATE.mkdir(parents=True, exist_ok=True)
    report = {'checked_at': int(time.time()), 'providers': status}
    tmp = STATE / ('refresh.tmp.' + str(os.getpid()))
    tmp.write_text(json.dumps(report) + '\n')
    tmp.chmod(0o600)
    tmp.replace(STATE / 'refresh.json')
    print(datetime.datetime.now().astimezone().isoformat(timespec='seconds'), json.dumps(status), flush=True)
    return all(value == 'ok' for value in status.values())


def wait_until(deadline, step=15):
    # macOS time.sleep does not count system sleep, so one long sleep delays the
    # first refresh after wake by the remaining interval. Poll the wall clock.
    while (remaining := deadline - time.time()) > 0:
        time.sleep(min(remaining, step))


if __name__ == '__main__':
    while True:
        success = cycle()
        if '--once' in sys.argv:
            raise SystemExit(0 if success else 1)
        wait_until(time.time() + 300)
