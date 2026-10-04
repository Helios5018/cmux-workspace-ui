import struct
import unittest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch
import grok_usage
from grok_usage import UsageError, parse_billing

NOW = 1789555000


def vint(n):
    out = bytearray()
    while n >= 128:
        out.append((n & 127) | 128)
        n >>= 7
    return bytes(out + bytes([n]))


def msg(field, data):
    return vint(field << 3 | 2) + vint(len(data)) + data


def integer(field, value):
    return vint(field << 3) + vint(value)


def percent(field, value):
    return vint(field << 3 | 5) + struct.pack('<f', value)


def frame(data, flag=0):
    return bytes([flag]) + len(data).to_bytes(4, 'big') + data


class BillingTests(unittest.TestCase):
    def test_live_shape_and_preferred_reset(self):
        inner = msg(2, percent(1, 99)) + percent(1, 21)
        inner += msg(5, integer(1, NOW + 86400)) + integer(9, NOW + 60)
        result = parse_billing(frame(msg(1, inner)), NOW)
        self.assertEqual(result['used_percent'], 21)
        self.assertEqual(result['resets_at'], NOW + 86400)

    def test_raw_proto(self):
        self.assertEqual(parse_billing(msg(1, percent(1, 37.5)), NOW)['used_percent'], 37.5)

    def test_missing_percent_not_fabricated(self):
        with self.assertRaises(UsageError):
            parse_billing(frame(msg(1, msg(5, integer(1, NOW + 86400)))), NOW)

    def test_confirmed_proto3_zero(self):
        inner = msg(5, integer(1, NOW + 86400)) + msg(8, integer(1, 1))
        self.assertEqual(parse_billing(frame(msg(1, inner)), NOW)['used_percent'], 0)

    def test_grpc_failure_overrides_plausible_data(self):
        for status in (16, 14, 9):
            payload = frame(msg(1, percent(1, 21)))
            payload += frame(('grpc-status: %d\r\n' % status).encode(), 128)
            with self.assertRaises(UsageError):
                parse_billing(payload, NOW)

    def test_malformed_and_nonfinite(self):
        for payload in (b'', b'<html>login</html>', b'\x00\x00\x01\x00\x00x',
                        frame(msg(1, percent(1, float('nan')))),
                        frame(msg(1, percent(1, 101)))):
            with self.assertRaises(UsageError):
                parse_billing(payload, NOW)


class CredentialTests(unittest.TestCase):
    def test_credentials_reappear_during_login(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(Path, 'home', return_value=Path(temp)):
            auth = Path(temp) / '.grok/auth.json'
            auth.parent.mkdir()
            def replace_credentials(_):
                auth.write_text(json.dumps({'https://auth.x.ai::test': {'key': 'test-credential'}}))
            with patch.object(grok_usage.time, 'sleep', side_effect=replace_credentials) as sleep:
                self.assertEqual(grok_usage.read_token(), 'test-credential')
                sleep.assert_called_once_with(2)

    def test_absent_credentials_report_missing_after_bounded_retry(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(Path, 'home', return_value=Path(temp)), \
                patch.object(grok_usage.time, 'sleep') as sleep:
            with self.assertRaisesRegex(UsageError, 'login missing'):
                grok_usage.read_token()
            self.assertEqual(sleep.call_count, 3)

    def test_empty_credentials_replaced_by_login(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(Path, 'home', return_value=Path(temp)):
            auth = Path(temp) / '.grok/auth.json'
            auth.parent.mkdir()
            auth.write_text('{}')
            def replace_credentials(_):
                auth.write_text(json.dumps({'https://auth.x.ai::test': {'key': 'test-credential'}}))
            with patch.object(grok_usage.time, 'sleep', side_effect=replace_credentials):
                self.assertEqual(grok_usage.read_token(), 'test-credential')


if __name__ == '__main__':
    unittest.main()
