import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import httpx
import tracking_work

PROJECT = '11111111-1111-4111-8111-111111111111'
OTHER = '22222222-2222-4222-8222-222222222222'
TASK = '33333333-3333-4333-8333-333333333333'
CONTEXT = ('auth', 'org', 'staff', 'developer', 'login')
OPTIONS = dict(organization_id='org', projects=[dict(id=PROJECT,name='Project')],
               tasks=[dict(id=TASK,title='Task',project_id=PROJECT)])

class WorkOptionsTests(unittest.TestCase):
    def setUp(self):
        self.context = CONTEXT
        session = SimpleNamespace(_lock=threading.RLock(), tracking_context=lambda:self.context,
                                  access_token=lambda:'frozen-token')
        p = patch.object(tracking_work, 'supabase_session', session)
        p.start()
        self.addCleanup(p.stop)

    def request(self, body=OPTIONS, status=200, change=False):
        def respond(request):
            self.assertEqual(request.url.path, '/rest/v1/rpc/get_tracking_work_options')
            self.assertEqual(request.headers['authorization'], 'Bearer frozen-token')
            if change:
                self.context = ('different-auth', *CONTEXT[1:])
            return httpx.Response(status, json=body)
        client = httpx.Client(transport=httpx.MockTransport(respond))
        with patch.object(tracking_work.httpx, 'Client', return_value=client):
            return tracking_work.get_tracking_work_options('https://offline.test','public',CONTEXT)

    def test_identity_bound_success_and_valid_selection(self):
        options = self.request()
        self.assertEqual(tracking_work.validate_selection(options,PROJECT,TASK),(PROJECT,TASK))
        self.assertEqual(tracking_work.validate_selection(options,PROJECT),(PROJECT,None))

    def test_rejects_cross_project_unassigned_and_malformed_selection(self):
        for project, task in [(OTHER,None),(PROJECT,OTHER),(None,TASK),('bad',None)]:
            with self.assertRaises(tracking_work.TrackingWorkError):
                tracking_work.validate_selection(OPTIONS,project,task)

    def test_wrong_org_invalid_response_and_inaccessible_endpoint_fail_closed(self):
        for body,status in [(dict(OPTIONS,organization_id='other'),200),(None,200),
                            (dict(OPTIONS,tasks=[dict(id=TASK,title='Task',project_id=OTHER)]),200),
                            (OPTIONS,403),(OPTIONS,503)]:
            with self.assertRaises(tracking_work.TrackingWorkError):
                self.request(body,status)

    def test_logout_during_request_never_returns_other_login_options(self):
        with self.assertRaises(tracking_work.TrackingWorkError):
            self.request(change=True)
