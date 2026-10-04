import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import install_local
import install_tmux_actions

ROOT = Path(__file__).resolve().parent.parent


class LocalInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.env = dict(os.environ, HOME=str(self.home), PYTHONDONTWRITEBYTECODE='1',
                        CMUX_SENTINEL_PROFILE='local')

    def deploy(self):
        return subprocess.run(['bash', str(ROOT / 'install.sh'), '--no-setup', '--no-actions'],
                              env=self.env, text=True, capture_output=True, check=True)

    def test_complete_isolated_install_preserves_config_and_is_idempotent(self):
        env_file = self.home / '.config/cmux/usage-sentinels.env'
        env_file.parent.mkdir(parents=True)
        env_file.write_text('USAGE_PROVIDERS="grok"\n')
        self.deploy()
        local = self.home / '.config/cmux-sentinel/local'
        for source in (ROOT / 'src').glob('*.py'):
            self.assertEqual((local / source.name).read_bytes(), source.read_bytes())
        self.assertTrue((local / 'LICENSE-CC-Switch').exists())
        self.assertEqual((self.home / 'bin/cmux-claude-usage.sh').read_bytes(),
                         (ROOT / 'bin/cmux-claude-usage.sh').read_bytes())
        self.assertTrue((self.home / '.config/cmux/sidebars/workspaces.js').exists())
        self.assertFalse((self.home / 'Library/LaunchAgents').exists())
        self.assertEqual(env_file.read_text(), 'USAGE_PROVIDERS="grok"\n')
        self.deploy()
        self.assertFalse(list(local.glob('*.bak.*')))
        (local / 'start.py').write_text('old code')
        self.deploy()
        self.assertEqual(next(local.glob('start.py.bak.*')).read_text(), 'old code')
        result = subprocess.run([str(self.home / 'bin/cmux-sentinel'), 'update'], env=self.env,
                                text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('merge upstream', result.stderr)
        result = subprocess.run([str(self.home / 'bin/cmux-sentinel'), 'start', '--help'], env=self.env,
                                text=True, capture_output=True, check=True)
        self.assertIn('Manually start', result.stdout)

    def test_full_install_registers_handler_and_setup_without_starting_workers(self):
        def run(command, **kwargs):
            return subprocess.CompletedProcess(command, 0, 'test-commit\n', '')
        with patch.object(install_local.subprocess, 'run', side_effect=run) as commands:
            install_local.install(self.home)
        calls = [call.args[0] for call in commands.call_args_list]
        self.assertTrue(any(str(cmd[-1]).endswith('install_tmux_actions.py') for cmd in calls))
        self.assertTrue(any(str(cmd[0]).endswith('cmux-sentinel-setup.sh') for cmd in calls))
        self.assertFalse(any('start.py' in str(cmd) or 'launchctl' in str(cmd) for cmd in calls))

    def test_fingerprint_matches_shell_and_includes_js_and_python(self):
        entry = (ROOT / 'bin/cmux-sentinel').read_text()
        installer = (ROOT / 'install.sh').read_text()
        routine = entry[entry.index('payload_hash()'):entry.index('\n}', entry.index('payload_hash()')) + 2]
        self.assertIn(routine, installer)
        shell = subprocess.check_output(['bash', '-c', routine + '\npayload_hash "$1"', 'test', str(ROOT)], text=True)
        self.assertEqual(shell.strip(), install_local.fingerprint())
        tree = self.home / 'tree'
        tree.mkdir()
        for name in ('VERSION', 'sidebars/workspaces.js', 'src/start.py'):
            target = tree / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, target)
        before = install_local.fingerprint(tree)
        (tree / 'sidebars/workspaces.js').write_text('// modified UI')
        after = install_local.fingerprint(tree)
        self.assertNotEqual(before, after)
        (tree / 'src/start.py').write_text('# modified worker')
        self.assertNotEqual(after, install_local.fingerprint(tree))

    def test_url_handler_applet_carries_its_own_path_and_binaries(self):
        # cmux runs under launchd's minimal PATH (/usr/bin:/bin:/usr/sbin:/sbin), and the
        # applet inherits that environment, so resolving tmux/cmux at action time finds
        # nothing and every close click dies silently. The registered applet must carry
        # absolute binaries and an explicit PATH instead.
        def fake_resolve(*candidates):
            for candidate in filter(None, candidates):
                text = str(candidate)
                for name, path in (('tmux', '/fake/homebrew/bin/tmux'),
                                   ('cmux', '/fake/app/cmux'),
                                   ('python3', '/fake/bin/python3')):
                    if text.endswith(name):
                        return path
            return None
        with patch.object(install_tmux_actions, 'resolve', side_effect=fake_resolve):
            command = install_tmux_actions.applet_command(Path('/tmp/handler-root'))
        self.assertTrue(command.startswith('/usr/bin/env PATH='))
        self.assertIn('/fake/homebrew/bin', command)
        self.assertIn('SENTINEL_TMUX_BIN=/fake/homebrew/bin/tmux', command)
        self.assertIn('SENTINEL_CMUX_BIN=/fake/app/cmux', command)
        self.assertIn('/usr/bin:/bin:/usr/sbin:/sbin', command)
        self.assertIn('/tmp/handler-root/action_handler.py', command)
        staged = self.home / 'staged-bin'
        staged.mkdir()
        shim = staged / 'tmux'
        shim.write_text('#!/bin/sh\n')
        with patch.object(install_tmux_actions, 'TEMP', staged.resolve()):
            # A shim under TMPDIR is session-scoped; baking it would break the applet later.
            self.assertIsNone(install_tmux_actions.resolve(shim))
            self.assertEqual(install_tmux_actions.resolve(shim, '/bin/sh'), '/bin/sh')
