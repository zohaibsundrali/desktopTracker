"""Remote logout requests use only captured identity and never make real HTTP calls."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

class DeviceLogoutTests(unittest.TestCase):
    def setUp(self):
        self.httpx = MagicMock()
        spec = importlib.util.spec_from_file_location('tested_logout', Path(__file__).resolve().parents[1] / 'device_logout.py')
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'httpx': self.httpx}):
            spec.loader.exec_module(self.module)
        self.client = self.httpx.Client.return_value.__enter__.return_value

    def test_exact_device_and_local_auth_session_use_captured_credentials(self):
        self.module.cleanup_session('https://offline.test/', 'public', 'old-token', 'old-device')
        first, second = self.client.stream.call_args_list
        self.assertEqual(first.args, ('POST', 'https://offline.test/rest/v1/rpc/revoke_tracker_device'))
        self.assertEqual(first.kwargs['json'], {'p_id': 'old-device'})
        self.assertEqual(second.kwargs['params'], {'scope': 'local'})
        self.assertEqual(second.kwargs['headers']['Authorization'], 'Bearer old-token')
        self.httpx.Timeout.assert_called_once_with(5.0, connect=3.0)
        self.assertFalse(self.httpx.Client.call_args.kwargs['follow_redirects'])
        self.assertFalse(self.httpx.Client.call_args.kwargs['trust_env'])

    def test_device_failure_does_not_skip_auth_cleanup_or_retry_indefinitely(self):
        self.client.stream.side_effect = [OSError('offline'), MagicMock()]
        self.module.cleanup_session('https://offline.test', 'public', 'old-token', 'old-device')
        self.assertEqual(self.client.stream.call_count, 2)
        self.assertEqual(self.client.stream.call_args.kwargs['params'], {'scope': 'local'})

    def test_missing_access_does_not_attempt_anonymous_revocation(self):
        self.module.cleanup_session('https://offline.test', 'public', None, 'old-device')
        self.httpx.Client.assert_not_called()

if __name__ == '__main__':
    unittest.main()
