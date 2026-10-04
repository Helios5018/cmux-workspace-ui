#!/usr/bin/env python3
"""Read Go quota with Pi-owned credentials; never send model requests."""
import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request

from sentinel_config import CMUX, USAGE_STATE as STATE, each_cmux_socket, setting
from sidebar_metadata import stamp

ENDPOINT = 'https://opencode.ai/zen/go/v1/usage'
WINDOWS = {'rolling': 'go5h', 'weekly': 'go7d', 'monthly': 'go1m'}


class UsageError(Exception):
    def __init__(self, message, transient=False):
        super().__init__(message)
        self.transient = transient


def read_key():
    path = Path(setting('SENTINEL_OPENCODE_GO_AUTH_FILE', str(Path.home() / '.pi/agent/auth.json'))).expanduser()
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        raise UsageError('Pi Go login missing') from None
    except (OSError, ValueError):
        raise UsageError('cannot read Pi Go credentials') from None
    auth = data.get('opencode-go') if isinstance(data, dict) else None
    key = auth.get('key') if isinstance(auth, dict) else None
    if (not isinstance(auth, dict) or auth.get('type') not in ('api_key', 'api')
            or not isinstance(key, str) or not key or not key.isascii()
            or any(c.isspace() or ord(c) < 32 for c in key)):
        raise UsageError('Pi Go API key missing or invalid')
    return key


def parse_usage(data, now):
    try:
        usage = json.loads(data)['usage']
        windows = {}
        for name in WINDOWS:
            row = usage[name]
            percent, status = row['percent'], row['status']
            if (type(percent) not in (int, float) or not math.isfinite(percent)
                    or not 0 <= percent <= 100 or status not in ('ok', 'rate-limited')):
                raise ValueError()
            reset = datetime.fromisoformat(row['resetsAt'].replace('Z', '+00:00'))
            if reset.tzinfo is None:
                raise ValueError()
            windows[name] = {'used_percent': percent, 'resets_at': int(reset.timestamp()), 'status': status}
        return {'provider': 'opencode-go', 'queried_at': int(now), 'windows': windows}
    except (ValueError, KeyError, TypeError, AttributeError, OverflowError):
        raise UsageError('Go usage format changed') from None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise UsageError('unexpected Go API redirect')


def fetch_usage():
    request = urllib.request.Request(ENDPOINT, headers={
        'Authorization': 'Bearer ' + read_key(), 'Accept': 'application/json',
        'User-Agent': 'cmux-sentinel/0.2.3 (usage monitor)',
    })
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=20) as response:
            data = response.read(65537)
            if len(data) > 65536:
                raise UsageError('oversized Go usage response')
    except urllib.error.HTTPError as exc:
        # Only inspect a bounded body for error classification; never print it.
        try:
            body = json.loads(exc.read(65536))
        except (ValueError, OSError):
            body = {}
        if not isinstance(body, dict):
            body = {}
        if body.get('cloudflare_error') or str(body.get('error_code')) == '1010':
            raise UsageError('Go access blocked', transient=True) from None
        if exc.code == 401:
            raise UsageError('Go key rejected') from None
        error = body.get('error')
        if exc.code == 403 and isinstance(error, dict) and error.get('type') == 'EntitlementError':
            raise UsageError('Go subscription required') from None
        if exc.code == 429:
            raise UsageError('Go API throttled', transient=True) from None
        raise UsageError('Go API HTTP %d' % exc.code, transient=exc.code >= 500) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise UsageError('Go offline', transient=True) from None
    return parse_usage(data, time.time())


def cmux(*args):
    result = subprocess.run([CMUX, *args], capture_output=True, text=True, timeout=15)
    if result.returncode:
        raise UsageError('cmux command failed: ' + args[0])
    return result.stdout


def resolve():
    found = {label: [] for label in WINDOWS.values()}
    for window in json.loads(cmux('--id-format', 'both', 'list-windows', '--json')):
        win = window.get('id') or window['ref']
        rows = json.loads(cmux('--id-format', 'both', 'workspace', 'list', '--window', win, '--json'))['workspaces']
        for row in rows:
            title = row.get('title') or ''
            for label in found:
                if title == label or title.startswith(label + ' '):
                    found[label].append((row.get('id') or row['ref'], win))
    return found


def countdown(reset):
    minutes = max(0, int(reset - time.time()) // 60)
    if minutes >= 1440:
        return '%dd %dh' % (minutes // 1440, minutes % 1440 // 60)
    return '%dh %dm' % (minutes // 60, minutes % 60)


def atomic_state(name, value):
    STATE.mkdir(parents=True, exist_ok=True)
    path = STATE / (name + '.tmp.' + str(os.getpid()))
    try:
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w') as out:
            out.write(value)
        path.replace(STATE / name)
    finally:
        path.unlink(missing_ok=True)


def publish(snapshot=None, error=None):
    def write():
        targets = resolve()
        if not all(targets.values()):
            raise UsageError('Go meter workspace missing; run setup')
        for name, label in WINDOWS.items():
            row = snapshot['windows'][name] if snapshot else None
            if error:
                detail = ('%g%% · stale · ' % row['used_percent'] if row else '') + '⚠ ' + str(error)
            else:
                detail = '%g%% (%s)' % (row['used_percent'], countdown(row['resets_at']))
            for ref, win in targets[label]:
                target = ['--workspace', ref, '--window', win]
                cmux('rename-workspace', *target, label + ' |' + detail + '|')
                if row:
                    cmux('set-progress', str(row['used_percent'] / 100), '--label', detail, *target)
                else:
                    cmux('clear-progress', *target)
        if not error:
            stamp(tuple(WINDOWS.values()), snapshot['queried_at'])
            atomic_state('opencode-go.json', json.dumps(snapshot) + '\n')
            atomic_state('opencode-go.last-success', str(snapshot['queried_at']) + '\n')

    each_cmux_socket(write)


def cached_usage():
    try:
        data = json.loads((STATE / 'opencode-go.json').read_text())
        # Reuse the strict parser, so corrupt local data never becomes a quota.
        payload = {'usage': {name: {
            'percent': row['used_percent'], 'status': row['status'],
            'resetsAt': datetime.fromtimestamp(row['resets_at'], timezone.utc).isoformat(),
        } for name, row in data['windows'].items()}}
        return parse_usage(json.dumps(payload), data['queried_at'])
    except (UsageError, ValueError, OSError, TypeError, KeyError, AttributeError, OverflowError):
        return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--update', action='store_true')
    parser.add_argument('--print', action='store_true')
    args = parser.parse_args(argv)
    try:
        snapshot = fetch_usage()
        if args.update:
            publish(snapshot)
        print(json.dumps(snapshot))
        return 0
    except (UsageError, ValueError, OSError, subprocess.SubprocessError) as exc:
        error = str(exc) if isinstance(exc, UsageError) else 'Go local reader failed'
        if args.update:
            try:
                cached = cached_usage() if isinstance(exc, UsageError) and exc.transient else None
                publish(cached, error=error)
            except (UsageError, ValueError, OSError, subprocess.SubprocessError):
                pass
        print(json.dumps({'provider': 'opencode-go', 'error': error}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
