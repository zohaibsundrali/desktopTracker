import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import httpx
import screenshot_policy
from sync_status import screenshot_policy_text

CONTEXT = ('auth', 'org', 'dev', 'developer', 'login')

class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.context = CONTEXT
        self.session = SimpleNamespace(_lock=threading.RLock(), tracking_context=lambda:self.context,
                                       access_token=lambda:'token')
        self.patch = patch.object(screenshot_policy, 'supabase_session', self.session)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.policy = screenshot_policy.ScreenshotPolicy('https://offline.test', 'public', CONTEXT)

    def refresh(self, body=None, code=200, handler=None):
        def respond(request):
            self.assertEqual(request.url.path, '/rest/v1/rpc/get_screenshot_policy')
            self.assertEqual(request.headers['authorization'], 'Bearer token')
            if handler:
                return handler(request)
            return httpx.Response(code, json=body)
        client = httpx.Client(transport=httpx.MockTransport(respond))
        with patch.object(screenshot_policy.httpx, 'Client', return_value=client):
            return self.policy.refresh()

    def test_valid_disabled_and_interval_boundaries(self):
        for enabled in (False, True):
            for interval in (60, 3600):
                self.assertEqual(self.refresh(dict(organization_id='org',enabled=enabled,interval_seconds=interval)), enabled)
                self.assertEqual(self.policy.snapshot(),dict(available=True,enabled=enabled,interval_seconds=interval))

    def test_failed_refresh_revokes_previous_enabled_state(self):
        self.assertTrue(self.refresh(dict(organization_id='org',enabled=True,interval_seconds=60)))
        self.assertFalse(self.refresh({},503))
        self.assertFalse(self.policy.snapshot()['available'])
        self.assertFalse(self.policy.snapshot()['enabled'])

    def test_malformed_wrong_org_and_out_of_range_fail_closed(self):
        for body in [None, [], {},dict(organization_id='wrong',enabled=True,interval_seconds=60),
                     dict(organization_id='org',enabled=1,interval_seconds=60),
                     *[dict(organization_id='org',enabled=True,interval_seconds=i) for i in (True,59,3601,'60',60.0)]]:
            self.assertFalse(self.refresh(body))
            self.assertFalse(self.policy.snapshot()['available'])

    def test_login_change_during_request_and_offline_fail_closed(self):
        def changed(request):
            self.context = ('other', *CONTEXT[1:])
            return httpx.Response(200,json=dict(organization_id='org',enabled=True,interval_seconds=60))
        self.assertFalse(self.refresh(handler=changed))
        self.context = CONTEXT
        def offline(request):
            raise httpx.ConnectError('offline')
        self.assertFalse(self.refresh(handler=offline))

    def test_policy_ui_explains_employee_pause_without_override(self):
        self.assertIn('unavailable', screenshot_policy_text({'policy':{'available':False}})[0])
        self.assertIn('disabled by admin', screenshot_policy_text({'policy':{'available':True,'enabled':False}})[0])
        text,_=screenshot_policy_text({'policy':{'available':True,'enabled':True,'interval_seconds':120},'paused':True,'running':True})
        self.assertIn('Paused',text)
        self.assertIn('120s',text)
        self.assertIn('all tracking',text)
