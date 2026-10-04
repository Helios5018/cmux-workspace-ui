#!/usr/bin/env python3
"""Local profile commands, shared by checkout and installed entry points."""
import os
import subprocess
import sys
from sentinel_config import SOURCE, PROVIDERS, poller


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    command = args.pop(0)
    scripts = {'start': 'start.py', 'doctor': 'doctor.py', 'paint': 'refresh.py', 'refresh': 'refresh.py'}
    if command in scripts:
        if command in ('paint', 'refresh'):
            args = ['--once', *args]
        os.execv(sys.executable, [sys.executable, str(SOURCE / scripts[command]), *args])
    if command == 'setup':
        helper = poller('codex').with_name('cmux-sentinel-setup.sh')
        os.execv(str(helper), [str(helper), *args])
    if command == 'usage':
        failed = False
        for provider in PROVIDERS:
            if provider == 'grok':
                cmd = [sys.executable, str(SOURCE / 'grok_usage.py')]
            elif provider == 'opencode-go':
                cmd = [sys.executable, str(SOURCE / 'opencode_go_usage.py')]
            elif provider in ('claude', 'codex'):
                cmd = [str(poller(provider))]
            else:
                continue
            failed |= subprocess.run([*cmd, *(args or ['--print'])]).returncode != 0
        return int(failed)
    raise SystemExit('Unknown local command: ' + command)


if __name__ == '__main__':
    raise SystemExit(main())
