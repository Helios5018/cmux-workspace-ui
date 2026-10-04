import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch, MagicMock
import urllib.error

import opencode_go_usage as go
import refresh

NOW = 2000000000


def payload():
    return {'usage': {name: {'percent': value, 'status': 'rate-limited' if value == 100 else 'ok',
                            'resetsAt': '2033-05-18T04:33:20Z'}
                      for name, value in zip(go.WINDOWS, (0, 12.5, 100))}}


class GoUsageTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {'CMUX_EXTRA_SOCKETS': ''})
        env.start()
        self.addCleanup(env.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_real_contract_preserves_zero_and_all_windows(self):
        snapshot = go.parse_usage(json.dumps(payload()), NOW)
        self.assertEqual([r['used_percent'] for r in snapshot['windows'].values()], [0, 12.5, 100])
        self.assertEqual(snapshot['windows']['monthly']['status'], 'rate-limited')
        self.assertEqual(snapshot['windows']['rolling']['resets_at'], NOW + 3600)

    def test_malformed_quota_never_becomes_zero(self):
        for value in (None, True, '0', -1, 101, float('nan'), float('inf')):
            data = payload()
            data['usage']['rolling']['percent'] = value
            with self.subTest(value=value), self.assertRaises(go.UsageError):
                go.parse_usage(json.dumps(data), NOW)
        for key, value in (('status', 'unknown'), ('resetsAt', 'tomorrow'),
                           ('resetsAt', '2033-05-18T04:33:20')):
            data = payload()
            data['usage']['weekly'][key] = value
            with self.assertRaises(go.UsageError):
                go.parse_usage(json.dumps(data), NOW)
        data = payload()
        del data['usage']['monthly']
        for invalid in (json.dumps(data), '<html>error</html>', 'null', '[]'):
            with self.assertRaises(go.UsageError):
                go.parse_usage(invalid, NOW)

    def test_pi_credentials_are_read_without_modification(self):
        path = self.root / 'auth.json'
        path.write_text(json.dumps({'opencode-go': {'type': 'api_key', 'key': 'fixture-go-key'}}))
        original = path.read_bytes()
        with patch.object(go, 'setting', return_value=str(path)):
            self.assertEqual(go.read_key(), 'fixture-go-key')
            self.assertEqual(path.read_bytes(), original)
            for content in ('{}', '[]', '{bad json', json.dumps({'opencode-go': {'type': 'oauth', 'key': 'wrong'}})):
                path.write_text(content)
                with self.assertRaises(go.UsageError):
                    go.read_key()

    def test_get_request_contract_and_redirect_block(self):
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value.read.return_value = json.dumps(payload()).encode()
        with patch.object(go, 'read_key', return_value='fixture-go-key'), \
                patch.object(go.urllib.request, 'build_opener', return_value=opener) as factory:
            snapshot = go.fetch_usage()
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, go.ENDPOINT)
        self.assertEqual(request.get_method(), 'GET')
        self.assertIsNone(request.data)
        self.assertEqual(request.get_header('Authorization'), 'Bearer fixture-go-key')
        self.assertTrue(request.get_header('User-agent').startswith('cmux-sentinel/'))
        self.assertEqual(snapshot['windows']['weekly']['used_percent'], 12.5)
        self.assertIsInstance(factory.call_args.args[0], go.NoRedirect)
        with self.assertRaises(go.UsageError):
            go.NoRedirect().redirect_request(request, None, 302, '', {}, 'https://example.invalid')

    def test_http_failures_are_sanitized_and_distinguished(self):
        for status, body, message, transient in (
            (401, {'error': {'message': 'private-account'}}, 'Go key rejected', False),
            (403, {'error': {'type': 'EntitlementError'}}, 'Go subscription required', False),
            (403, {'cloudflare_error': True}, 'Go access blocked', True),
            (429, {}, 'Go API throttled', True),
            (503, {}, 'Go API HTTP 503', True),
        ):
            opener = MagicMock()
            opener.open.side_effect = urllib.error.HTTPError(go.ENDPOINT, status, 'private', {},
                                                            io.BytesIO(json.dumps(body).encode()))
            with self.subTest(status=status, body=body), patch.object(go, 'read_key', return_value='fixture'), \
                    patch.object(go.urllib.request, 'build_opener', return_value=opener):
                with self.assertRaises(go.UsageError) as caught:
                    go.fetch_usage()
                self.assertEqual(str(caught.exception), message)
                self.assertEqual(caught.exception.transient, transient)

    def test_publish_and_stale_error_keep_metadata_freshness_honest(self):
        snapshot = go.parse_usage(json.dumps(payload()), NOW)
        targets = {label: [(label + '-id', 'window-id')] for label in go.WINDOWS.values()}
        with patch.object(go, 'STATE', self.root), patch.object(go, 'resolve', return_value=targets), \
                patch.object(go, 'cmux') as cmux, patch.object(go, 'stamp') as stamp:
            go.publish(snapshot)
            stamp.assert_called_once_with(tuple(go.WINDOWS.values()), NOW)
            self.assertEqual((self.root / 'opencode-go.json').stat().st_mode & 0o777, 0o600)
            self.assertEqual(go.cached_usage(), snapshot)
            stamp.reset_mock()
            cmux.reset_mock()
            go.publish(go.cached_usage(), error='Go offline')
            stamp.assert_not_called()
            self.assertEqual((self.root / 'opencode-go.last-success').read_text(), str(NOW) + '\n')
            renames = [call.args[-1] for call in cmux.call_args_list if call.args[0] == 'rename-workspace']
            self.assertIn('go7d |12.5% · stale · ⚠ Go offline|', renames)
            cmux.reset_mock()
            go.publish(error='Go key rejected')
            self.assertEqual(sum(call.args[0] == 'clear-progress' for call in cmux.call_args_list), 3)
            (self.root / 'opencode-go.json').write_text('{}')
            self.assertIsNone(go.cached_usage())

    def test_missing_meter_cannot_stamp_a_complete_success(self):
        with patch.object(go, 'resolve', return_value={'go5h': [], 'go7d': [], 'go1m': []}), \
                patch.object(go, 'stamp') as stamp:
            with self.assertRaises(go.UsageError):
                go.publish(go.parse_usage(json.dumps(payload()), NOW))
            stamp.assert_not_called()

    def test_refresh_runs_only_enabled_go_and_reports_failure(self):
        with patch.object(refresh, 'PROVIDERS', ['opencode-go']), patch.object(refresh, 'STATE', self.root), \
                patch.object(refresh.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1)) as run, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(refresh.cycle())
        self.assertEqual(run.call_count, 1)
        self.assertEqual(Path(run.call_args.args[0][1]).name, 'opencode_go_usage.py')
        self.assertEqual(json.loads((self.root / 'refresh.json').read_text())['providers'], {'opencode-go': 'error'})


if __name__ == '__main__':
    unittest.main()
