"""Offline lifecycle coverage: no credentials, provider calls, or input capture."""
import base64
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
import threading
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]


def token(sub='auth-a', session='session-a', org='org-a', exp=5000):
    claims = {'sub': sub, 'session_id': session, 'exp': exp,
              'app_metadata': {'organization_id': org, 'app_user_id': 'staff-a'}}
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip('=')
    return 'header.' + payload + '.signature'


class SharedSessionTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('tested_shared_session', ROOT / 'supabase_session.py')
        self.shared = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.shared)
        self.timer_patch = patch.object(self.shared.threading, 'Timer')
        self.timer = self.timer_patch.start()
        self.time_patch = patch.object(self.shared.time, 'time', return_value=1000)
        self.time_patch.start()
        self.source = MagicMock(supabase_key='public-key')
        self.tracker = MagicMock(supabase_key='public-key')
        self.shared.register(self.source, auth_source=True)
        self.shared.register(self.tracker)

    def tearDown(self):
        self.shared.clear()
        self.timer_patch.stop()
        self.time_patch.stop()

    def login(self):
        self.shared.set_tokens(token(), 'refresh-a')
        return self.shared._generation

    def test_refresh_tokens_only_belong_to_auth_source(self):
        self.login()
        self.source.auth.set_session.assert_not_called()
        self.tracker.auth.set_session.assert_not_called()
        self.assertFalse(self.tracker.auth._persist_session)
        self.assertFalse(self.tracker.auth._auto_refresh_token)
        self.tracker.postgrest.auth.assert_called_with(token())
        self.timer.assert_called_with(3940, self.shared._refresh, args=(self.shared._generation,))
        self.assertTrue(self.timer.return_value.daemon)

    def test_refresh_rotates_all_headers_and_shared_tokens(self):
        generation = self.login()
        renewed = token(exp=9000)
        self.source.auth._refresh_access_token.return_value = SimpleNamespace(
            session=SimpleNamespace(access_token=renewed, refresh_token='refresh-b'))
        self.shared._refresh(generation)
        self.source.auth._refresh_access_token.assert_called_once_with('refresh-a')
        self.assertEqual(self.shared.access_token(), renewed)
        self.assertEqual(self.shared.refresh_token(), 'refresh-b')
        self.tracker.postgrest.auth.assert_called_with(renewed)
        self.tracker.storage._client.headers.update.assert_called_with({'Authorization': 'Bearer ' + renewed})

    def test_offline_logout_clears_headers_and_cancels_pending_refresh(self):
        generation = self.login()
        self.shared.clear()
        self.timer.return_value.cancel.assert_called()
        self.source.auth._remove_session.assert_called()
        self.tracker.postgrest.auth.assert_called_with('public-key')
        self.assertIsNone(self.shared.organization_id())
        self.shared._refresh(generation)
        self.source.auth._refresh_access_token.assert_not_called()

    def test_old_timer_cannot_refresh_new_login(self):
        generation = self.login()
        self.shared.set_tokens(token(sub='auth-b'), 'refresh-b')
        self.shared._refresh(generation)
        self.source.auth._refresh_access_token.assert_not_called()

    def test_transient_outage_retries_without_losing_session(self):
        generation = self.login()
        self.source.auth._refresh_access_token.side_effect = OSError('offline')
        self.shared._refresh(generation)
        self.assertEqual(self.shared.refresh_token(), 'refresh-a')
        self.timer.assert_called_with(30, self.shared._refresh, args=(generation,))

    def test_revoked_refresh_fails_closed(self):
        generation = self.login()
        error = RuntimeError('revoked')
        error.status = 400
        self.source.auth._refresh_access_token.side_effect = error
        self.shared._refresh(generation)
        self.assertIsNone(self.shared.access_token())
        self.tracker.postgrest.auth.assert_called_with('public-key')

    def test_changed_identity_or_session_stops_tracking(self):
        for renewed in [token(sub='different'), token(session='different'), token(org='different')]:
            generation = self.login()
            self.source.auth._refresh_access_token.return_value = SimpleNamespace(
                session=SimpleNamespace(access_token=renewed, refresh_token='refresh-b'))
            self.shared._refresh(generation)
            self.assertIsNone(self.shared.app_user_id())

    def test_late_registered_tracker_inherits_latest_access_without_refresh_session(self):
        self.login()
        late = MagicMock(supabase_key='public-key')
        self.shared.register(late)
        late.postgrest.auth.assert_called_with(token())
        late.auth.set_session.assert_not_called()
        self.shared.register(late)
        self.assertEqual(len(self.shared._live_clients()), 3)

    def test_device_denial_notifies_stop_hook_and_clears_access(self):
        class Listener:
            def __init__(self):
                self.stopped = threading.Event()
            def stop(self):
                self.stopped.set()
        listener = Listener()
        self.login()
        self.shared.on_session_lost(listener.stop)
        self.shared.start_device_monitor()
        self.source.rpc.return_value.execute.return_value = SimpleNamespace(data=False)
        self.shared._check_device(self.shared._generation)
        self.assertTrue(listener.stopped.wait(1))
        self.assertIsNone(self.shared.access_token())
        self.source.rpc.assert_called_once_with("auth_tracker_session", {})

    def test_device_timeout_does_not_claim_revocation(self):
        generation = self.login()
        self.shared.start_device_monitor()
        self.source.rpc.return_value.execute.side_effect = OSError("offline")
        self.shared._check_device(generation)
        self.assertEqual(self.shared.access_token(), token())
        self.timer.assert_called_with(30, self.shared._check_device, args=(generation,))

    def test_slow_refresh_does_not_block_clear_or_restore_old_identity(self):
        generation = self.login()
        entered, release = threading.Event(), threading.Event()
        def response(_):
            entered.set()
            release.wait(2)
            return SimpleNamespace(session=SimpleNamespace(access_token=token(exp=9000), refresh_token="rotated"))
        self.source.auth._refresh_access_token.side_effect = response
        worker = threading.Thread(target=self.shared._refresh, args=(generation,))
        worker.start()
        self.assertTrue(entered.wait(1))
        try:
            cleared = threading.Event()
            threading.Thread(target=lambda: (self.shared.clear(), cleared.set()), daemon=True).start()
            self.assertTrue(cleared.wait(0.5), "Logout waited on a provider request")
            self.shared.set_tokens(token(sub="auth-b"), "refresh-b")
        finally:
            release.set()
            worker.join(2)
        self.assertEqual(self.shared.refresh_token(), "refresh-b")
        self.source.auth._save_session.assert_not_called()

    def test_old_device_denial_cannot_clear_new_login(self):
        generation = self.login()
        self.shared.start_device_monitor()
        def late_response():
            self.shared.set_tokens(token(sub="auth-b"), "refresh-b")
            return SimpleNamespace(data=False)
        self.source.rpc.return_value.execute.side_effect = late_response
        self.shared._check_device(generation)
        self.assertEqual(self.shared.refresh_token(), "refresh-b")


if __name__ == '__main__':
    unittest.main()
