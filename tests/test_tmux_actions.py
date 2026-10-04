from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import tmux_actions as actions


class ActionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        for name, file in (('KEY', 'key'), ('EXPANDED', 'expanded'), ('PENDING', 'pending'), ('LAYOUT', 'layout')):
            setting = patch.object(actions, name, Path(temp.name) / file)
            setting.start()
            self.addCleanup(setting.stop)
        self.row = {'id': '$7', 'session_created': '100', 'pid': '300', 'socket_path': '/tmp/test-tmux',
                    '@lifecycle': 'persistent', '@note': 'keep this service'}

    def run_tmux(self, cmd, **kwargs):
        field = cmd[-1]
        if field.startswith('#{session_id}'):
            output = '\t'.join(self.row[k] for k in actions.IDENTITY_FIELDS)
        elif field == '#{@lifecycle}':
            output = self.row['@lifecycle']
        elif field == '#{@note}':
            output = self.row['@note']
        else:
            output = ''
        return subprocess.CompletedProcess(cmd, 0, output + '\n', '')

    def test_signature_binds_action_and_tampering_never_runs_tmux(self):
        url = actions.action_url(self.row, 'toggle').replace('://toggle/', '://close/')
        with patch.object(actions.subprocess, 'run') as command, self.assertRaises(ValueError):
            actions.perform_action(url)
        command.assert_not_called()

    def test_new_persistent_annotation_blocks_old_direct_close(self):
        url = actions.action_url(self.row, 'close')
        with patch.object(actions.subprocess, 'run', side_effect=self.run_tmux) as command:
            actions.perform_action(url)
        self.assertFalse(any('kill-session' in call.args[0] for call in command.call_args_list))
        self.assertEqual(actions.read_state(actions.PENDING), actions.identity(self.row))

    def test_changed_confirmation_requires_another_confirmation(self):
        url = actions.action_url(self.row, 'confirm-close')
        self.row['@note'] = 'updated note'
        with patch.object(actions.subprocess, 'run', side_effect=self.run_tmux) as command:
            actions.perform_action(url)
        self.assertFalse(any('kill-session' in call.args[0] for call in command.call_args_list))

    def test_confirmed_identity_closes_only_exact_session(self):
        url = actions.action_url(self.row, 'confirm-close')
        with patch.object(actions.subprocess, 'run', side_effect=self.run_tmux) as command:
            actions.perform_action(url)
        kills = [call.args[0] for call in command.call_args_list if 'kill-session' in call.args[0]]
        self.assertEqual(kills, [[actions.TMUX, '-S', '/tmp/test-tmux', 'kill-session', '-t', '$7']])

    def test_replaced_session_is_noop(self):
        url = actions.action_url(self.row, 'confirm-close')
        self.row['session_created'] = '200'
        with patch.object(actions.subprocess, 'run', side_effect=self.run_tmux) as command:
            self.assertFalse(actions.perform_action(url))
        self.assertEqual(command.call_count, 1)
