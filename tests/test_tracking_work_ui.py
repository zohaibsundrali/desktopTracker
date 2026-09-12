"""Execute dashboard work-selection handlers without an OS display."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


class Widget:
    def __init__(self, value=''):
        self.value = value
        self.options = {}
    def configure(self, **kwargs):
        self.options.update(kwargs)
    def set(self, value):
        self.value = value
    def get(self):
        return self.value


class WorkUiTests(unittest.TestCase):
    def setUp(self):
        self.jobs, self.callbacks = [], []
        self.identity = ('subject', 'org', 'profile', 'developer', 'session')
        tree = ast.parse(Path(__file__).resolve().parents[1].joinpath('ui_dashboard.py').read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'DashboardWindow')
        names = {'_set_work_controls', '_clear_work_options', '_on_project_changed',
                 '_load_work_options', 'start_timer', '_reset_buttons_on_error', '_on_session_stopped'}
        cls.body = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in names]
        namespace = {'supabase_session': SimpleNamespace(tracking_context=lambda: self.identity),
                     'threading': SimpleNamespace(Thread=lambda target, **kw: SimpleNamespace(start=lambda: self.jobs.append(target))),
                     'Colors': SimpleNamespace(ACCENT_ORANGE='orange', ACCENT_GREEN='green', ACCENT_RED='red'),
                     'messagebox': Mock()}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[])), 'ui_dashboard.py', 'exec'), namespace)
        self.ui = namespace['DashboardWindow']()
        u = self.ui
        u._alive, u._work_locked, u._work_loading = True, False, False
        u.timer_running, u.timer_paused = False, False
        u._work_generation = 0
        u._work_identity = self.identity
        for name in ('project_select', 'task_select', 'work_retry_btn', 'work_status_label',
                     'start_btn', 'stop_btn', 'pause_btn', 'status_label'):
            setattr(u, name, Widget())
        u.app = SimpleNamespace(after=lambda delay, callback: self.callbacks.append(callback), update_idletasks=lambda: None)
        u._dash_root = SimpleNamespace(winfo_exists=lambda: True)
        u.timer = SimpleNamespace(get_tracking_work_options=Mock(return_value={
            'projects': [{'id': 'p1', 'name': 'Project'}, {'id': 'p2', 'name': 'Project'}],
            'tasks': [{'id': 't1', 'title': 'Task', 'project_id': 'p1'}]}), start=Mock(return_value=True))
        u.pause_timer = Mock()
        u.radial_timer = Mock()
        u._clear_work_options()

    def load(self):
        self.ui._load_work_options()
        self.jobs.pop(0)()
        self.callbacks.pop(0)()

    def test_duplicate_names_remain_distinct_and_project_change_resets_task(self):
        self.load()
        u = self.ui
        self.assertEqual(len(u._projects), 3)
        u._on_project_changed('Project · p1')
        u.task_select.set('Task · t1')
        u._on_project_changed('Project · p2')
        self.assertEqual(u.task_select.get(), 'No task')
        self.assertEqual(u.task_select.options['state'], 'disabled')

    def test_start_passes_ids_and_freezes_selectors(self):
        self.load()
        u = self.ui
        u.project_select.set('Project · p1')
        u._on_project_changed('Project · p1')
        u.task_select.set('Task · t1')
        u.start_timer()
        self.assertEqual(u.project_select.options['state'], 'disabled')
        self.jobs.pop(0)()
        u.timer.start.assert_called_once_with(project_id='p1', task_id='t1')
        u._reset_buttons_on_error('Pause failed')
        self.assertTrue(u._work_locked)
        self.assertEqual(u.task_select.options['state'], 'disabled')

    def test_start_failure_restores_selection_controls(self):
        self.load()
        self.ui.timer.start.return_value = False
        self.ui.start_timer()
        self.jobs.pop(0)()
        self.callbacks.pop(0)()
        self.assertFalse(self.ui._work_locked)
        self.assertEqual(self.ui.project_select.options['state'], 'normal')

    def test_stale_account_result_never_populates(self):
        self.ui._load_work_options()
        self.jobs.pop(0)()
        self.identity = ('different',)
        self.callbacks.pop(0)()
        self.assertEqual(self.ui._projects, {'General tracking': None})

    def test_newer_request_wins(self):
        self.ui._load_work_options()
        self.jobs.pop(0)()
        self.ui._load_work_options()
        self.callbacks.pop(0)()
        self.assertTrue(self.ui._work_loading)
        self.assertEqual(len(self.ui._projects), 1)

    def test_failure_offers_general_tracking_and_retry(self):
        self.ui.timer.get_tracking_work_options.side_effect = RuntimeError('secret provider text')
        self.load()
        self.assertIn('Retry', self.ui.work_status_label.options['text'])
        self.assertNotIn('secret', self.ui.work_status_label.options['text'])
        self.ui.start_timer()
        self.jobs.pop(0)()
        self.ui.timer.start.assert_called_once_with(project_id=None, task_id=None)

    def test_loading_completion_does_not_change_running_session(self):
        self.ui._load_work_options()
        self.jobs.pop(0)()
        self.ui.start_timer()
        self.callbacks.pop(0)()
        self.assertEqual(self.ui._projects, {'General tracking': None})
        self.assertTrue(self.ui._work_locked)

    def test_stop_unlocks_controls(self):
        self.ui._set_work_controls(True)
        self.ui._on_session_stopped(None, '00:01:00')
        self.assertFalse(self.ui._work_locked)

    def test_logged_out_callback_ignored(self):
        self.ui._load_work_options()
        self.jobs.pop(0)()
        self.ui._alive = False
        self.callbacks.pop(0)()
        self.assertEqual(len(self.ui._projects), 1)
