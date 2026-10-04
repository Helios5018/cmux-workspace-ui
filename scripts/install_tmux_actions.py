#!/usr/bin/env python3
"""Register a background macOS URL handler for the sidebar close buttons."""
from pathlib import Path
import os
import plistlib
import shlex
import shutil
import subprocess
import tempfile
import sys

# The applet inherits the environment of whoever opened the URL, and cmux itself
# runs under launchd with the minimal PATH (/usr/bin:/bin:/usr/sbin:/sbin). tmux
# and cmux are NOT discoverable there, so a handler that resolves them at action
# time dies with an unreadable OSError and the click does nothing. Resolve both
# now, at install time, and hand the applet an explicit PATH plus the
# SENTINEL_*_BIN overrides sentinel_config already honours.
SYSTEM_PATH = ('/usr/bin', '/bin', '/usr/sbin', '/sbin')
FALLBACK_DIRS = ('/opt/homebrew/bin', '/usr/local/bin')
CMUX_APP_BIN = '/Applications/cmux.app/Contents/Resources/bin/cmux'
TEMP = Path(tempfile.gettempdir()).resolve()


def resolve(*candidates):
    """First stable absolute path that exists; cmux's per-session CLI shims live in
    TMPDIR and must never be baked into the applet. Symlinked commands keep their
    stable prefix (/opt/homebrew/bin/tmux) instead of a version-pinned Cellar path."""
    for candidate in filter(None, candidates):
        path = Path(candidate)
        if path.is_file() and TEMP not in path.resolve().parents:
            return str(path)
    return None


def handler_environment():
    """PATH and command overrides the applet must carry into action_handler.py."""
    tmux = resolve(shutil.which('tmux'), *(Path(directory) / 'tmux' for directory in FALLBACK_DIRS))
    cmux = resolve(CMUX_APP_BIN, shutil.which('cmux'))
    python = resolve('/usr/bin/python3') or sys.executable or '/usr/bin/python3'
    for name, value in (('tmux', tmux), ('cmux', cmux)):
        if not value:
            print(f'install_tmux_actions: warning: {name} not found — sidebar actions stay broken '
                  f'until it is installed or SENTINEL_{name.upper()}_BIN is set', file=sys.stderr)
    directories = [str(Path(item).parent) for item in (python, tmux, cmux) if item]
    environment = ['PATH=' + os.pathsep.join(dict.fromkeys([*directories, *SYSTEM_PATH]))]
    for variable, value in (('SENTINEL_TMUX_BIN', tmux), ('SENTINEL_CMUX_BIN', cmux)):
        if value:
            environment.append(f'{variable}={value}')
    return environment, python


def applet_command(root):
    """The shell command the registered applet runs for one action URL."""
    environment, python = handler_environment()
    return shlex.join(['/usr/bin/env', *environment, python, str(root / 'action_handler.py')])


def main():
    root = Path.home() / '.config/cmux-sentinel/local'
    app = Path.home() / '.local/share/cmux-sentinel/Cmux Sentinel Actions.app'
    app.parent.mkdir(parents=True, exist_ok=True)
    command = applet_command(root) + ' '
    literal = '"' + command.replace('\\', '\\\\').replace('"', '\\"') + '"'
    source = f'''on open location actionURL
    do shell script {literal} & quoted form of actionURL
end open location
'''
    with tempfile.TemporaryDirectory(prefix='cmux-tmux-actions-') as temp:
        script = Path(temp) / 'handler.applescript'
        script.write_text(source)
        subprocess.run(['/usr/bin/osacompile', '-o', str(app), str(script)], check=True)
    info = app / 'Contents/Info.plist'
    data = plistlib.loads(info.read_bytes())
    data.update(CFBundleIdentifier='local.cmux-sentinel.actions', LSUIElement=True,
                CFBundleURLTypes=[{'CFBundleURLName': 'cmux-sentinel',
                                   'CFBundleURLSchemes': ['cmux-sentinel']}])
    info.write_bytes(plistlib.dumps(data))
    subprocess.run(['/usr/bin/codesign', '--force', '--sign', '-', str(app)], check=True)
    subprocess.run(['/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister',
                    '-f', str(app)], check=True)
    print('Registered local tmux close handler (no TCP port)')


if __name__ == '__main__':
    main()
