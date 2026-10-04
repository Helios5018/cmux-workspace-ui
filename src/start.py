#!/usr/bin/env python3
"""Start/reuse the persistent usage worker without opening a TCP port."""
from pathlib import Path
import os
import argparse
import shlex
import subprocess
import sys

from sentinel_config import SESSION, SOURCE as ROOT, CMUX_SOCKET, TMUX


def tmux(*args, **kwargs):
    return subprocess.run([TMUX, *args], **kwargs)


def worker_alive(lines, script):
    for line in lines:
        if not line.startswith('0 '):
            continue
        try:
            if any(Path(token).name == script for token in shlex.split(line[2:])):
                return True
        except ValueError:
            continue
    return False


def ensure_workers():
    if tmux('has-session', '-t', SESSION, capture_output=True).returncode:
        task_path = os.environ.get('PATH', '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin')
        tmux('new-session', '-d', '-s', SESSION, '-c', str(ROOT),
             '-e', 'PATH=' + task_path,
             '-e', 'CMUX_SOCKET_PATH=' + str(CMUX_SOCKET),
             shlex.join([sys.executable, str(ROOT / 'refresh.py')]), check=True)
    for key, value in {
        '@project': 'cmux-sentinel',
        '@lifecycle': 'persistent',
        '@port': '',
        '@note': '每 5 分钟刷新已启用的 Claude、Codex、Grok、OpenCode Go 用量，每 5 秒同步侧栏 tmux 名称和备注；停止后两者不再刷新',
    }.items():
        tmux('set-option', '-t', SESSION, key, value, check=True)
    panes = tmux('list-panes', '-s', '-t', SESSION, '-F', '#{pane_dead} #{pane_start_command}',
                 capture_output=True, text=True, check=True).stdout.splitlines()
    for script, window in (('refresh.py', 'usage'), ('tmux_sidebar.py', 'tmux-sidebar')):
        if not worker_alive(panes, script):
            tmux('new-window', '-d', '-t', SESSION, '-n', window, '-c', str(ROOT),
                 '-e', 'PATH=' + os.environ.get('PATH', '/usr/bin:/bin'),
                 '-e', 'CMUX_SOCKET_PATH=' + str(CMUX_SOCKET),
                 shlex.join([sys.executable, str(ROOT / script)]), check=True)
    print('Running: ' + SESSION + ' (no TCP port)')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Manually start/reuse usage and tmux sidebar refresh.')
    parser.parse_args(argv)
    ensure_workers()


if __name__ == '__main__':
    main()
