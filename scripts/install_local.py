#!/usr/bin/env python3
"""Deploy the JS/tmux profile. Service startup is always an explicit command."""
import argparse
import datetime
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
PATTERNS = ('VERSION', 'install.sh', 'bin/cmux-sentinel', 'bin/*.sh', 'hooks/*',
            'sidebars/*.swift', 'sidebars/*.js', 'src/*.py', 'scripts/*.py', 'LICENSE-CC-Switch')


def fingerprint(root=ROOT):
    digest = hashlib.sha256()
    for pattern in PATTERNS:
        for path in sorted(root.glob(pattern)):
            if path.is_file():
                digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def put(source, target, mode=0o644):
    data = source.read_bytes() if isinstance(source, Path) else source.encode()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.read_bytes() == data:
            target.chmod(mode)
            return
        backup = target.with_name(target.name + '.bak.' + datetime.datetime.now().strftime('%Y%m%d%H%M%S%f'))
        shutil.copy2(target, backup)
        for stale in sorted(target.parent.glob(target.name + '.bak.*'), reverse=True)[3:]:
            stale.unlink()
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as out:
        temporary = Path(out.name)
        out.write(data)
    try:
        temporary.chmod(mode)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def install(home, setup=True, actions=True):
    cfg = home / '.config/cmux-sentinel'
    local = cfg / 'local'
    for source in sorted((ROOT / 'src').glob('*.py')):
        put(source, local / source.name)
    put(ROOT / 'LICENSE-CC-Switch', local / 'LICENSE-CC-Switch')
    for name in ('cmux-sentinel', 'cmux-claude-usage.sh', 'cmux-codex-usage.sh', 'cmux-sentinel-setup.sh', 'cmux-sentinel-doctor.sh'):
        put(ROOT / 'bin' / name, home / 'bin' / name, 0o755)
    put(ROOT / 'sidebars/workspaces.js', home / '.config/cmux/sidebars/workspaces.js')
    # The repair command stays available at its established installed path.
    put(ROOT / 'scripts/install_tmux_actions.py', local / 'install_tmux_actions.py')
    env = home / '.config/cmux/usage-sentinels.env'
    if not env.exists():
        put('USAGE_PROVIDERS="codex grok"\nSENTINEL_REFRESH_TMUX="cmux-sentinel-refresh"\n', env, 0o600)
    if actions:
        subprocess.run([sys.executable, str(local / 'install_tmux_actions.py')], check=True)
    if setup:
        subprocess.run([str(home / 'bin/cmux-sentinel-setup.sh')], check=True)
    # Stamp only a completed install, with source identity and the whole local payload.
    result = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', '--short', 'HEAD'],
                            capture_output=True, text=True)
    top = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', '--show-toplevel'],
                         capture_output=True, text=True)
    commit = (result.stdout.strip() if result.returncode == 0 and top.returncode == 0
              and Path(top.stdout.strip()).resolve() == ROOT else 'unknown')
    put('version=' + (ROOT / 'VERSION').read_text().strip() + '\nprofile=local\n'
        + 'installed=' + datetime.datetime.now(datetime.timezone.utc).isoformat() + '\n'
        + 'commit=' + commit + '\npayload=' + fingerprint() + '\n', cfg / 'VERSION')


def main():
    parser = argparse.ArgumentParser(description='Install local JS/tmux profile; does not start workers or install LaunchAgents.')
    parser.add_argument('--no-setup', action='store_true', help='copy files without creating meter workspaces')
    parser.add_argument('--no-actions', action='store_true', help='skip macOS URL handler registration (staging/tests)')
    args = parser.parse_args()
    if not args.no_actions and sys.platform != 'darwin':
        parser.error('URL handler requires macOS; use --no-actions for staging')
    install(Path.home(), setup=not args.no_setup, actions=not args.no_actions)
    print('Installed local JS/tmux profile. Start/reuse workers manually: ~/bin/cmux-sentinel start')
    print('After updating running workers, restart them explicitly to load the new Python code.')


if __name__ == '__main__':
    main()
