import contextlib
import io
import unittest
from unittest import mock

import start


class ManualStartTests(unittest.TestCase):
    def test_manual_start(self):
        with mock.patch.object(start, 'ensure_workers') as ensure:
            start.main([])
            ensure.assert_called_once()

    def test_retired_flags_cannot_start_workers(self):
        for flag in ('--install-autostart', '--if-cmux'):
            with self.subTest(flag=flag), mock.patch.object(start, 'ensure_workers') as ensure:
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                    start.main([flag])
                self.assertEqual(error.exception.code, 2)
                ensure.assert_not_called()




class WorkerRecoveryTests(unittest.TestCase):
    def test_existing_session_recovers_missing_usage_worker(self):
        import subprocess
        def tmux(*args, **kwargs):
            output = '0 python3 ' + str(start.ROOT / 'tmux_sidebar.py') if args[0] == 'list-panes' else ''
            return subprocess.CompletedProcess(args, 0, output, '')
        with mock.patch.object(start, 'tmux', side_effect=tmux) as commands, contextlib.redirect_stdout(io.StringIO()):
            start.ensure_workers()
        windows = [call.args for call in commands.call_args_list if call.args[0] == 'new-window']
        self.assertEqual(len(windows), 1)
        self.assertIn(str(start.ROOT / 'refresh.py'), windows[0][-1])
        self.assertFalse(any(call.args[0] == 'new-session' for call in commands.call_args_list))

    def test_existing_healthy_workers_are_reused(self):
        import subprocess
        def tmux(*args, **kwargs):
            output = '\n'.join('0 python3 ' + str(start.ROOT / file) for file in ('refresh.py', 'tmux_sidebar.py'))
            return subprocess.CompletedProcess(args, 0, output, '')
        with mock.patch.object(start, 'tmux', side_effect=tmux) as commands, contextlib.redirect_stdout(io.StringIO()):
            start.ensure_workers()
        self.assertFalse(any(call.args[0] in ('new-session', 'new-window') for call in commands.call_args_list))

    def test_source_checkout_recognizes_installed_workers(self):
        self.assertTrue(start.worker_alive(['0 python3 /tmp/installed/local/refresh.py'], 'refresh.py'))
        self.assertFalse(start.worker_alive(['1 python3 /tmp/installed/local/refresh.py'], 'refresh.py'))


if __name__ == '__main__':
    unittest.main()
