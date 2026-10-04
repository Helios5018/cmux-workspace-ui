#!/usr/bin/env python3
"""Read-only checks for enabled usage providers and tmux workers (no network request)."""
import json
import subprocess
import time

from sentinel_config import USAGE_STATE as root, TMUX, SESSION, PROVIDERS
failures = []


def check(ok, message):
    print(('PASS ' if ok else 'FAIL ') + message)
    if not ok:
        failures.append(message)


worker = subprocess.run([TMUX, 'list-panes', '-s', '-t', SESSION,
                         '-F', '#{pane_dead}:#{pane_current_command}:#{pane_start_command}'],
                        capture_output=True, text=True)
for script in ('refresh.py', 'tmux_sidebar.py'):
    check(worker.returncode == 0 and any(line.lower().startswith('0:python') and script in line
                                        for line in worker.stdout.splitlines()),
          script + ' worker is alive')
for provider in PROVIDERS:
    try:
        age = int(time.time()) - int((root / (provider + '.last-success')).read_text())
        check(0 <= age < 900, provider + ' updated %ds ago' % age)
    except (ValueError, OSError):
        check(False, provider + ' freshness stamp missing')
try:
    result = json.loads((root / 'refresh.json').read_text())
    check(all(result['providers'].get(p) == 'ok' for p in PROVIDERS), 'last cycle succeeded for enabled providers')
    if 'grok' in PROVIDERS:
        grok = json.loads((root / 'grok.json').read_text())
        check(isinstance(grok['used_percent'], (int, float)) and 0 <= grok['used_percent'] <= 100,
              'Grok billed usage: %s%%' % grok['used_percent'])
except (ValueError, OSError, KeyError):
    check(False, 'usage snapshot missing or invalid')
raise SystemExit(bool(failures))
