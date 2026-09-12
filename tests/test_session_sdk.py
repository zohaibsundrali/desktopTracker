"""Exercise the installed pinned SDK with local sessions; all network is forbidden."""
import base64
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import time
import unittest
from unittest.mock import patch

try:
    from supabase import create_client
    from gotrue.types import Session, User
except ImportError:
    create_client = None


@unittest.skipUnless(create_client, 'Install requirements.txt to run real SDK coverage')
class PinnedSdkSessionTests(unittest.TestCase):
    def test_header_only_tracker_never_inherits_refresh_and_logout_clears_real_headers(self):
        spec = importlib.util.spec_from_file_location('sdk_shared_session', Path(__file__).resolve().parents[1] / 'supabase_session.py')
        shared = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(shared)
        claims = {'sub': 'auth-a', 'session_id': 'session-a', 'exp': int(time.time()) + 3600,
                  'app_metadata': {'organization_id': 'org-a', 'app_user_id': 'staff-a'}}
        token = 'header.' + base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip('=') + '.signature'
        public = 'header.public.signature'
        with patch('httpx.Client.send', side_effect=AssertionError('Network forbidden')):
            source = create_client('https://offline.test', public)
            shared.register(source, auth_source=True)
            user = User(id='auth-a', app_metadata=claims['app_metadata'], user_metadata={},
                        aud='authenticated', created_at=datetime.now(timezone.utc))
            source.auth._save_session(Session(access_token=token, refresh_token='refresh-a',
                                              user=user, token_type='bearer', expires_at=claims['exp'], expires_in=3600))
            with patch.object(shared.threading, 'Timer'):
                shared.set_tokens(token, 'refresh-a')
                tracker = create_client('https://offline.test', public)
                shared.register(tracker)
                self.assertIsNone(tracker.auth.get_session())
                self.assertEqual(tracker.postgrest.session.headers['authorization'], 'Bearer ' + token)
                self.assertEqual(tracker.storage._client.headers['authorization'], 'Bearer ' + token)
                shared.clear()
                self.assertIsNone(source.auth.get_session())
                self.assertEqual(tracker.postgrest.session.headers['authorization'], 'Bearer ' + public)
                self.assertEqual(tracker.storage._client.headers['authorization'], 'Bearer ' + public)


if __name__ == '__main__':
    unittest.main()
