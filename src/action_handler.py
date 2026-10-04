#!/usr/bin/env python3
"""URL entry point, separated from signing and metadata collection."""
from datetime import datetime, timezone
import subprocess
import sys
from urllib.parse import urlsplit
from sentinel_config import STATE
from tmux_actions import perform_action
from tmux_sidebar import update

LOG = STATE / 'url-action-errors.log'
LOG_LIMIT = 64 * 1024


def note_failure(message):
    """Actions run headless from the URL applet; an unrecorded failure cannot be debugged."""
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        if LOG.exists() and LOG.stat().st_size > LOG_LIMIT:
            LOG.unlink()
        with LOG.open('a') as out:
            out.write(f'{datetime.now(timezone.utc).isoformat(timespec="seconds")} {message}\n')
    except OSError:
        pass


def main():
    try:
        url = sys.argv[1]
        perform_action(url)
        if urlsplit(url).netloc not in ('notepad', 'console', 'terminal'):
            update()
    except (OSError, ValueError, KeyError, IndexError, RuntimeError, subprocess.SubprocessError) as error:
        note_failure(f'{type(error).__name__}: {error}')
        raise SystemExit('Unable to apply sidebar action')


if __name__ == '__main__':
    main()
