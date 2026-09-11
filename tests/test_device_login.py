"""Offline Auth/device contracts. No credentials, network, or tracker capture."""
import importlib.util
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]


class DeviceLoginTests(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.shared = MagicMock()
        modules = {
            'supabase': SimpleNamespace(create_client=lambda *_: self.client),
            'config': SimpleNamespace(config=SimpleNamespace(SUPABASE_URL='https://offline.test', SUPABASE_KEY='not-a-key')),
            'supabase_session': self.shared,
        }
        self.modules = patch.dict(sys.modules, modules)
        self.modules.start()
        spec = importlib.util.spec_from_file_location('device_test_auth_manager', ROOT / 'auth_manager.py')
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        self.manager = module.AuthManager()
        self.client.auth.sign_in_with_password.return_value = SimpleNamespace(
            user=SimpleNamespace(id='auth-id', email='staff@example.test'),
            session=SimpleNamespace(access_token='test-access', refresh_token='test-refresh'))
        self.profile_result = self.client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value
        self.profile_result.data = [{'id': 'profile-id', 'status': 'active', 'name': 'Staff'}]
        self.client.rpc.return_value.execute.return_value = SimpleNamespace(data='device-id')

    def tearDown(self):
        self.modules.stop()
        sys.modules.pop('device_test_auth_manager', None)

    def test_registered_login_uses_profile_identity(self):
        success, _, user = self.manager.login('staff@example.test', 'test-password')
        self.assertTrue(success)
        self.assertEqual(user.id, 'profile-id')
        self.assertEqual(self.client.rpc.call_args.args[0], 'enroll_tracker_device')
        self.assertEqual(self.manager._device_id, 'device-id')

    def test_missing_profile_stops_before_enrollment_and_clears_session(self):
        self.profile_result.data = []
        self.assertFalse(self.manager.login('staff@example.test', 'test-password')[0])
        self.client.rpc.assert_not_called()
        self.shared.clear.assert_called_once()

    def test_suspended_profile_stops_before_enrollment(self):
        self.profile_result.data[0]['status'] = 'suspended'
        self.assertFalse(self.manager.login('staff@example.test', 'test-password')[0])
        self.client.rpc.assert_not_called()

    def test_enrollment_error_does_not_start_tracking(self):
        self.client.rpc.return_value.execute.side_effect = RuntimeError('database unavailable')
        self.assertFalse(self.manager.login('staff@example.test', 'test-password')[0])
        self.assertIsNone(self.manager.current_user)
        self.shared.clear.assert_called_once()

    def test_unconfirmed_enrollment_fails_closed(self):
        self.client.rpc.return_value.execute.return_value.data = None
        self.assertFalse(self.manager.login('staff@example.test', 'test-password')[0])

    def test_logout_revokes_device_and_clears_even_if_network_fails(self):
        self.manager.login('staff@example.test', 'test-password')
        self.client.rpc.return_value.execute.side_effect = RuntimeError('offline')
        self.manager.logout()
        self.client.rpc.assert_called_with('revoke_tracker_device', {'p_id': 'device-id'})
        self.shared.clear.assert_called_once()
        self.assertIsNone(self.manager.current_user)
        self.assertIsNone(self.manager._device_id)


if __name__ == '__main__':
    unittest.main()
