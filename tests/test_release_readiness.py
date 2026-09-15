"""Distribution and diagnostics tests use synthetic keys, no network or capture."""
import base64
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from public_config import PublicConfigError, validate_public_config
from diagnostics import collect_report
from scripts.prepare_public_config import prepare


def jwt(role):
    encode = lambda value: base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip('=')
    return encode({'alg': 'HS256'}) + '.' + encode({'role': role}) + '.fakeSignature'


class ReleaseReadinessTests(unittest.TestCase):
    def setUp(self):
        self.safe = {'SUPABASE_URL': 'https://project.example.test/', 'SUPABASE_KEY': jwt('anon')}

    def test_accepts_public_keys_only(self):
        for key in (jwt('anon'),):
            result = validate_public_config({**self.safe, 'SUPABASE_KEY': key})
            self.assertEqual(result['SUPABASE_URL'], 'https://project.example.test')
            self.assertEqual(result['SUPABASE_KEY'], key)
        for key in (jwt('service_role'), jwt('authenticated'), 'sb_publishable_abcdefghijklmnop', 'sb_secret_private', '', '${SERVICE_ROLE_KEY}', 'not-a-key', jwt('anon') + '\nPRIVATE=value'):
            with self.subTest(key_kind=key[:8]):
                with self.assertRaises(PublicConfigError) as error:
                    validate_public_config({**self.safe, 'SUPABASE_KEY': key})
                if key:
                    self.assertNotIn(key, str(error.exception))

    def test_refuses_unsafe_origins(self):
        for url in ('http://example.test', 'https://u:p@example.test', 'https://example.test/path',
                    'https://example.test?token=secret', 'https://example.test#token',
                    'https://example.test:invalid', 'https://example.test\nEVIL=1'):
            with self.subTest(url=url), self.assertRaises(PublicConfigError):
                validate_public_config({**self.safe, 'SUPABASE_URL': url})

    def test_packaging_ignores_unrelated_secrets_and_removes_stale_output(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True):
            source, output = Path(tmp) / '.env', Path(tmp) / 'build/.env'
            source.write_text('\n'.join(f'{k}={v}' for k, v in self.safe.items()) + '\nSERVICE_ROLE_KEY=do-not-bundle\n')
            prepare(source, output)
            self.assertNotIn('do-not-bundle', output.read_text(encoding="utf-8"))
            source.write_text('SUPABASE_KEY=sb_secret_do-not-bundle\n')
            with self.assertRaises(PublicConfigError):
                prepare(source, output)
            self.assertFalse(output.exists())

    def test_packaging_disables_environment_interpolation(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'PRIVATE': jwt('anon')}, clear=True):
            source = Path(tmp) / '.env'
            source.write_text('SUPABASE_URL=https://example.test\nSUPABASE_KEY=${PRIVATE}\n')
            with self.assertRaises(PublicConfigError):
                prepare(source, Path(tmp) / 'build/.env')

    def test_diagnostics_never_return_raw_errors_credentials_or_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            def failing_import(name):
                raise RuntimeError('secret-token person@example.test C:/Users/Private')
            report = collect_report(self.safe, 'Windows', failing_import, tmp)
            self.assertFalse(report['ready_for_manual_test'])
            encoded = json.dumps(report)
            for secret in ('secret-token', 'person@example.test', 'Private', self.safe['SUPABASE_KEY'], self.safe['SUPABASE_URL'], tmp):
                self.assertNotIn(secret, encoded)
            self.assertIn('screen_and_input_capture', report['not_tested'])

    def test_setup_success_is_not_live_tracking_certification(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = collect_report(self.safe, 'Windows', lambda _: None, tmp)
            self.assertTrue(report['ready_for_manual_test'])
            self.assertEqual(report['scope'], 'offline_setup_only')
            self.assertIn('hosted_permissions', report['not_tested'])
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_unsupported_platform_and_unwritable_storage_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / 'file'
            file.write_text('occupied')
            report = collect_report(self.safe, 'Linux', lambda _: None, file)
            self.assertFalse(report['ready_for_manual_test'])
            failed = {check['name'] for check in report['checks'] if check['status'] == 'fail'}
            self.assertEqual(failed, {'supported_platform', 'writable_user_data'})


if __name__ == '__main__':
    unittest.main()
