"""Shared paths and settings for source checkouts and installed workers."""
import contextlib
import os
from pathlib import Path
import shlex
import shutil
import sys

SOURCE = Path(__file__).resolve().parent
CONFIG = Path.home() / '.config/cmux-sentinel'
STATE = Path(os.environ.get('CMUX_SENTINEL_STATE_DIR',
                            str(Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state'))) / 'cmux-sentinel')))
USAGE_STATE = STATE / 'usage'
SIDEBAR_DIR = Path.home() / '.config/cmux/sidebars'
ENV_FILE = Path.home() / '.config/cmux/usage-sentinels.env'
CMUX = os.environ.get('SENTINEL_CMUX_BIN') or shutil.which('cmux') or 'cmux'
TMUX = os.environ.get('SENTINEL_TMUX_BIN') or shutil.which('tmux') or 'tmux'
CMUX_SOCKET = os.environ.get('CMUX_SOCKET_PATH', str(Path.home() / '.local/state/cmux/cmux.sock'))


def setting(name, default):
    if name in os.environ:
        return os.environ[name]
    try:
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip().removeprefix('export ')
            if line.startswith(name + '='):
                values = shlex.split(line.split('=', 1)[1], comments=True)
                return ' '.join(values)
    except (OSError, ValueError):
        pass
    return default


SESSION = setting('SENTINEL_REFRESH_TMUX', 'cmux-sentinel-refresh')
PROVIDERS = setting('USAGE_PROVIDERS', 'codex grok').split()


def poller(name):
    checkout = SOURCE.parent / 'bin' / ('cmux-' + name + '-usage.sh')
    return checkout if checkout.exists() else Path.home() / 'bin' / checkout.name


def cmux_socket_paths():
    """Explicit targets only; preserve order and remove duplicates."""
    primary = os.environ.get('CMUX_SOCKET_PATH', str(Path.home() / '.local/state/cmux/cmux.sock'))
    extras = setting('CMUX_EXTRA_SOCKETS', '').split()
    return list(dict.fromkeys(path for path in [primary, *extras] if path))


@contextlib.contextmanager
def using_cmux_socket(path):
    previous = os.environ.get('CMUX_SOCKET_PATH')
    os.environ['CMUX_SOCKET_PATH'] = path
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop('CMUX_SOCKET_PATH', None)
        else:
            os.environ['CMUX_SOCKET_PATH'] = previous


def each_cmux_socket(action):
    """Attempt every target independently; fail only if no target succeeds.

    Callbacks must stamp freshness only after a successful write. A false/None
    result still means success (for example, unchanged tmux metadata).
    """
    results, errors = [], []
    for path in cmux_socket_paths():
        try:
            with using_cmux_socket(path):
                results.append(action())
        except Exception as exc:
            errors.append(exc)
            # Exception messages can contain provider responses or signed URLs.
            print('cmux-sentinel: write failed at %s (%s)' % (path, type(exc).__name__), file=sys.stderr)
    if not results:
        if errors:
            raise errors[-1]
        raise OSError('No cmux socket configured')
    return any(results)
