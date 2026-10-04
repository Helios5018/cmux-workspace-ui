import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import grok_usage
import opencode_go_usage as go
import refresh
import sentinel_config as config
import tmux_sidebar


class SocketTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {'CMUX_SOCKET_PATH': '/test/official.sock',
                                     'CMUX_EXTRA_SOCKETS': '/test/local.sock'})
        env.start()
        self.addCleanup(env.stop)
        stderr = contextlib.redirect_stderr(io.StringIO())
        stderr.__enter__()
        self.addCleanup(stderr.__exit__, None, None, None)

    def test_failed_primary_does_not_block_local_and_environment_is_restored(self):
        attempted = []

        def write():
            attempted.append(os.environ['CMUX_SOCKET_PATH'])
            if attempted[-1] == '/test/official.sock':
                raise OSError('closed')
            return False  # Unchanged metadata still means success.

        self.assertFalse(config.each_cmux_socket(write))
        self.assertEqual(attempted, ['/test/official.sock', '/test/local.sock'])
        self.assertEqual(os.environ['CMUX_SOCKET_PATH'], '/test/official.sock')

    def test_failed_extra_does_not_fail_successful_primary(self):
        def write():
            if os.environ['CMUX_SOCKET_PATH'] == '/test/local.sock':
                raise OSError('closed')
            return True

        self.assertTrue(config.each_cmux_socket(write))

    def test_all_targets_failing_is_not_success(self):
        def write():
            raise OSError('closed')

        with self.assertRaises(OSError):
            config.each_cmux_socket(write)
        self.assertEqual(os.environ['CMUX_SOCKET_PATH'], '/test/official.sock')

    def test_deduplication_and_reopened_instance_retried(self):
        os.environ['CMUX_EXTRA_SOCKETS'] = '/test/official.sock /test/local.sock /test/local.sock'
        self.assertEqual(config.cmux_socket_paths(), ['/test/official.sock', '/test/local.sock'])
        calls = []
        for cycle in range(2):
            def write():
                path = os.environ['CMUX_SOCKET_PATH']
                if cycle == 0 and path == '/test/official.sock':
                    raise OSError('closed')
                calls.append((cycle, path))
            config.each_cmux_socket(write)
        self.assertEqual(calls, [(0, '/test/local.sock'), (1, '/test/official.sock'),
                                (1, '/test/local.sock')])

    def test_unset_environment_restored_even_after_exception(self):
        os.environ.pop('CMUX_SOCKET_PATH')
        with self.assertRaises(OSError), config.using_cmux_socket('/test/local.sock'):
            raise OSError('closed')
        self.assertNotIn('CMUX_SOCKET_PATH', os.environ)

    def test_providers_stamp_only_successfully_written_instances(self):
        snapshots = [
            (grok_usage, {'used_percent': 2, 'resets_at': 2000000000, 'queried_at': 1900000000}),
            (go, {'queried_at': 1900000000, 'windows': {
                name: {'used_percent': 12, 'resets_at': 2000000000} for name in go.WINDOWS}}),
        ]
        for module, snapshot in snapshots:
            with self.subTest(provider=module.__name__), tempfile.TemporaryDirectory() as temp:
                def resolve():
                    if os.environ['CMUX_SOCKET_PATH'] == '/test/official.sock':
                        raise OSError('closed')
                    return ([('meter', 'window')] if module is grok_usage else
                            {label: [(label, 'window')] for label in go.WINDOWS.values()})

                stamped = []
                with patch.object(module, 'STATE', Path(temp)), patch.object(module, 'resolve', resolve), \
                        patch.object(module, 'cmux'), patch.object(module, 'stamp',
                        side_effect=lambda *args: stamped.append(os.environ['CMUX_SOCKET_PATH'])):
                    module.publish(snapshot)
                self.assertEqual(stamped, ['/test/local.sock'])
                self.assertTrue(list(Path(temp).glob('*.last-success')))

    def test_tmux_snapshot_collected_once_despite_primary_failure(self):
        calls = []

        def publish(rows):
            calls.append(os.environ['CMUX_SOCKET_PATH'])
            if calls[-1] == '/test/official.sock':
                raise OSError('closed')
            return True

        with patch.object(tmux_sidebar, 'sessions', return_value=[]) as collect, \
                patch.object(tmux_sidebar, 'publish', side_effect=publish):
            self.assertTrue(tmux_sidebar.update())
        collect.assert_called_once()
        self.assertEqual(calls, ['/test/official.sock', '/test/local.sock'])

    def test_codex_only_stamps_reported_configured_successes(self):
        stamped = []
        with patch.object(refresh, 'stamp', side_effect=lambda *args: stamped.append(os.environ['CMUX_SOCKET_PATH'])):
            self.assertTrue(refresh.stamp_codex('updated: cx7d=16%\n'
                                              'sentinel-socket-updated:/test/local.sock\n'
                                              'sentinel-socket-updated:/test/unconfigured.sock\n'))
            self.assertFalse(refresh.stamp_codex('provider disabled'))
        self.assertEqual(stamped, ['/test/local.sock'])

    def test_codex_stamp_failure_does_not_block_other_instance(self):
        attempted = []

        def stamp(*args):
            attempted.append(os.environ['CMUX_SOCKET_PATH'])
            if attempted[-1] == '/test/official.sock':
                raise subprocess.CalledProcessError(1, 'cmux')

        with patch.object(refresh, 'stamp', side_effect=stamp):
            self.assertTrue(refresh.stamp_codex('sentinel-socket-updated:/test/official.sock\n'
                                              'sentinel-socket-updated:/test/local.sock\n'))
        self.assertEqual(attempted, ['/test/official.sock', '/test/local.sock'])

    def test_claude_cycle_requires_explicit_success_before_stamping(self):
        for output, expected in [('provider unavailable', False),
                                 ('sentinel-socket-updated:/test/local.sock\n', True)]:
            with self.subTest(output=output), tempfile.TemporaryDirectory() as temp, \
                    patch.object(refresh, 'STATE', Path(temp)), \
                    patch.object(refresh, 'PROVIDERS', ['claude']), \
                    patch.object(refresh.subprocess, 'run', return_value=
                                 subprocess.CompletedProcess([], 0, output, '')) as run, \
                    patch.object(refresh, 'stamp') as stamp, \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(refresh.cycle(), expected)
                self.assertEqual(Path(run.call_args.args[0][0]).name, 'cmux-claude-usage.sh')
                self.assertEqual(stamp.call_count, int(expected))
                if expected:
                    self.assertEqual(stamp.call_args.args[0], ('5h', '7d', 'm7d', 'spend'))
                self.assertEqual(json.loads((Path(temp) / 'refresh.json').read_text())['providers'],
                                 {'claude': 'ok' if expected else 'error'})


class RefreshWaitTests(unittest.TestCase):
    def test_wall_clock_jump_after_system_sleep_ends_wait(self):
        clock = [1000.0]
        naps = []

        def nap(seconds):
            naps.append(seconds)
            clock[0] += 600  # The machine slept through the rest of the interval.

        with patch.object(refresh.time, 'time', lambda: clock[0]), patch.object(refresh.time, 'sleep', nap):
            refresh.wait_until(1300)
        self.assertEqual(naps, [15])
