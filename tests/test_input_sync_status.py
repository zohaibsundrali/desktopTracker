import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from sync_status import input_sync_text
from test_sync_status_ui import dashboard_class

class InputSyncStatusTests(unittest.TestCase):
    def test_each_source_needs_its_own_confirmation(self):
        text, tone = input_sync_text({'keyboard': {'pending': 0, 'last_success_at':'now'}, 'mouse': {'pending': 2}})
        self.assertIn('Keyboard sync: latest queued batches confirmed', text)
        self.assertIn('Mouse sync: 2 batches saved locally', text)
        self.assertEqual(tone, 'warning')
    def test_private_errors_are_not_rendered(self):
        text, tone = input_sync_text({'keyboard': {'pending': 1, 'error':'private-token'}, 'mouse': None})
        self.assertNotIn('private-token', text)
        self.assertEqual(tone, 'warning')
    def test_missing_state_never_claims_confirmed(self):
        for state in (None, {}, {'keyboard': {'pending': True}}, {'mouse': {'pending': -1}}):
            self.assertNotEqual(input_sync_text(state)[1], 'success')
    def test_ui_cached_poll_is_throttled(self):
        clock=SimpleNamespace(monotonic=Mock(return_value=10))
        view=dashboard_class(clock)()
        view.timer=SimpleNamespace(get_input_sync_status=Mock(return_value={'keyboard':{'pending':1}}))
        view.input_sync_label=Mock()
        view._refresh_input_sync(); view._refresh_input_sync()
        view.timer.get_input_sync_status.assert_called_once()
        self.assertIn('awaiting confirmation',view.input_sync_label.configure.call_args.kwargs['text'])
    def test_timer_retains_stopped_sources_without_network(self):
        tree=ast.parse(Path('timer_tracker.py').read_text(encoding="utf-8"))
        method=next(n for c in tree.body if isinstance(c,ast.ClassDef) for n in c.body if isinstance(n,ast.FunctionDef) and n.name=='get_input_sync_status')
        ns={};exec(compile(ast.fix_missing_locations(ast.Module(body=[method],type_ignores=[])), 'timer_tracker.py','exec'),ns)
        timer=SimpleNamespace(_last_input_sync_status={'keyboard':None,'mouse':None},keyboard_tracker=SimpleNamespace(get_sync_status=lambda:{'pending':3}),mouse_tracker=None)
        first=ns['get_input_sync_status'](timer)
        timer.keyboard_tracker=None
        first['keyboard']['pending']=999
        self.assertEqual(ns['get_input_sync_status'](timer)['keyboard']['pending'],3)
