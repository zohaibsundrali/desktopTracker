import unittest
from unittest.mock import patch
from types import SimpleNamespace
import idle_reminder as module


class IdleReminderTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.context = ('auth', 'org', 'profile', 'developer', 'login')
        self.r = module.IdleReminder('https://test.invalid','public',self.context,lambda:self.now)
        self.r._policy = dict(enabled=True,threshold_seconds=60)

    def test_either_input_prevents_reminder_and_dismissal_is_once_per_episode(self):
        self.now=90
        self.r.update(90,1)
        self.assertFalse(self.r.status()['pending'])
        self.r.update(90,90)
        self.assertTrue(self.r.status()['pending'])
        self.r.dismiss()
        self.now=200
        self.r.update(200,200)
        self.assertFalse(self.r.status()['pending'])
        self.now=201
        self.r.update(0,201)
        self.now=262
        self.r.update(61,262)
        self.assertTrue(self.r.status()['pending'])

    def test_both_sensors_required_and_unknown_gap_is_not_counted(self):
        self.now=120
        for invalid in [None,float('nan'),float('inf'),-1,True,'120']:
            self.r.update(invalid,120)
            self.assertFalse(self.r.status()['available'])
        self.now=121
        self.r.update(121,121)
        self.assertFalse(self.r.status()['pending'])
        self.assertEqual(self.r.status()['idle_seconds'],1)

    def test_pause_authloss_and_disabled_policy_never_remind(self):
        self.now=120
        self.r.update(120,120,paused=True)
        self.assertTrue(self.r.status()['paused'])
        self.assertFalse(self.r.status()['pending'])
        self.r.update(120,120,authorized=False)
        self.assertIsNone(self.r._policy)
        self.r._policy=dict(enabled=False,threshold_seconds=60)
        self.now=300
        self.r.update(300,300)
        self.assertTrue(self.r.status()['available'])
        self.assertFalse(self.r.status()['pending'])
        self.r.update(None, None)
        self.assertTrue(self.r.status()['available'])
        self.assertFalse(self.r.status()['enabled'])
        self.assertIsNone(self.r.status()['idle_seconds'])

    def test_policy_is_validated_and_bound_to_identity(self):
        import threading
        session=SimpleNamespace(_lock=threading.RLock(),tracking_context=lambda:self.context,access_token=lambda:'secret')
        body=dict(organization_id='org',enabled=True,threshold_seconds=60)
        with patch.object(module,'supabase_session',session),patch.object(module.httpx,'Client') as client:
            response=client.return_value.__enter__.return_value.post.return_value
            response.status_code=200
            response.json.return_value=body
            self.assertTrue(self.r.refresh())
            for bad in [dict(body,organization_id='other'),dict(body,threshold_seconds=True),dict(body,threshold_seconds=59),dict(body,enabled='true')]:
                response.json.return_value=bad
                self.assertFalse(self.r.refresh())
                self.assertFalse(self.r.status()['available'])
            response.json.return_value=body
            def switched():
                session.tracking_context=lambda:('other',*self.context[1:])
                return body
            response.json.side_effect=switched
            self.assertFalse(self.r.refresh())

    def test_status_is_a_copy_and_reset_starts_new_interval(self):
        self.now=70
        self.r.update(70,70)
        state=self.r.status()
        state['pending']=False
        self.assertTrue(self.r.status()['pending'])
        self.r.reset()
        self.r.update(70,70)
        self.assertEqual(self.r.status()['idle_seconds'],0)


class IdleSensorTests(unittest.TestCase):
    @staticmethod
    def getter(filename, classname):
        import ast
        from pathlib import Path
        tree=ast.parse((Path(__file__).resolve().parents[1]/filename).read_text())
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==classname)
        fn=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='get_idle_seconds')
        code=compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),filename,'exec')
        namespace={'time':SimpleNamespace(monotonic=lambda:100.0)}
        exec(code,namespace)
        return namespace['get_idle_seconds']

    def test_mouse_requires_live_listener_and_fresh_successful_poll(self):
        getter=self.getter('mouse_tracker.py','MouseTracker')
        mouse=SimpleNamespace(is_tracking=True,listener=SimpleNamespace(is_alive=lambda:True),
            _idle_poll_at=99.9,_idle_last_activity=30.0,pause_ctrl=None)
        self.assertEqual(getter(mouse),70)
        mouse._idle_poll_at=90
        self.assertIsNone(getter(mouse))
        mouse._idle_poll_at=99.9
        mouse.listener.is_alive=lambda:False
        self.assertIsNone(getter(mouse))
        mouse.listener.is_alive=lambda:True
        mouse.is_tracking=False
        self.assertIsNone(getter(mouse))

    def test_keyboard_returns_unknown_for_paused_stopped_or_dead_listener(self):
        import threading
        getter=self.getter('keyboard_tracker.py','KeyboardTracker')
        core=SimpleNamespace(_lock=threading.Lock(),is_tracking=True,
            _listener=SimpleNamespace(is_alive=lambda:True),pause_ctrl=None,last_activity=40.0)
        keyboard=SimpleNamespace(_tracking=core)
        self.assertEqual(getter(keyboard),60)
        core.pause_ctrl=SimpleNamespace(is_paused=True,is_stopped=False)
        self.assertIsNone(getter(keyboard))
        core.pause_ctrl=None
        core._listener.is_alive=lambda:False
        self.assertIsNone(getter(keyboard))
        core._listener.is_alive=lambda:True
        core.is_tracking=False
        self.assertIsNone(getter(keyboard))


class IdleCoordinatorTests(unittest.TestCase):
    def setUp(self):
        import test_tracking_attribution as attribution
        attribution.TrackingAttributionTests.setUp(self)
        self.assertTrue(self.tracker.start())

    def test_status_and_dismiss_suppress_changed_identity(self):
        reminder=self.tracker._idle_reminder
        reminder._state=dict(available=True,enabled=True,threshold_seconds=60,idle_seconds=70,pending=True,paused=False)
        self.assertTrue(self.tracker.get_idle_reminder_status()['pending'])
        self.shared.tracking_context=lambda:None
        self.assertFalse(self.tracker.get_idle_reminder_status()['available'])
        self.tracker.dismiss_idle_reminder()
        self.assertTrue(reminder.status()['pending'])

    def test_pause_clears_pending_without_changing_tracked_seconds(self):
        reminder=self.tracker._idle_reminder
        reminder._state=dict(available=True,enabled=True,threshold_seconds=60,idle_seconds=70,pending=True,paused=False)
        previous=self.tracker.get_current_elapsed()
        self.tracker.dismiss_idle_reminder()
        self.assertGreaterEqual(self.tracker.get_current_elapsed(),previous)
        self.assertTrue(self.tracker.instant_timer.is_running)
        self.assertTrue(self.tracker.pause())
        self.assertFalse(self.tracker.get_idle_reminder_status()['pending'])
        self.assertTrue(self.tracker.get_idle_reminder_status()['paused'])
