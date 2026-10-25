import ast
import threading
import time
import unittest
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace


def mouse_class():
    tree = ast.parse((Path(__file__).resolve().parents[1] / 'mouse_tracker.py').read_text(encoding='utf-8'))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'MouseTracker')
    decorator = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == '_serialize_input')
    future = ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0)
    namespace = dict(threading=threading, time=time, datetime=datetime,
        MouseEvent=lambda **values: SimpleNamespace(**values),
        supabase_session=SimpleNamespace(tracking_context=lambda: None))
    exec(compile(ast.fix_missing_locations(ast.Module(body=[future, decorator, cls], type_ignores=[])),
        'mouse_tracker.py', 'exec'), namespace)
    return namespace['MouseTracker']


class MouseEventCountTests(unittest.TestCase):
    def setUp(self):
        cls = mouse_class()
        self.mouse = cls.__new__(cls)
        self.mouse._input_lock = threading.RLock()
        self.mouse.is_tracking = True
        self.mouse.pause_ctrl = None
        self.mouse._tracking_context = ('auth', 'org', 'dev', 'developer', 'login')
        self.mouse.click_counts = {'left': 0, 'right': 0, 'middle': 0, 'other': 0}
        self.mouse.scroll_counts = {'up': 0, 'down': 0, 'left': 0, 'right': 0}
        self.mouse.time_buckets = defaultdict(lambda: {
            'move_events': 0, 'click_events': 0, 'scroll_events': 0,
            'total_events': 0, 'distance': 0.0, 'active_seconds': 0.0,
            'idle_seconds': 0.0, 'productivity_score': 0.0, 'avg_velocity': 0.0,
            'quadrant_distribution': defaultdict(int),
        })
        self.mouse.events = deque()
        self.mouse.save_summary_only = True
        self.mouse.screen_width = 1920
        self.mouse.screen_height = 1080
        self.mouse.session_id = 'session'

        self.mouse._capture_allowed.__globals__['supabase_session'].tracking_context = lambda: self.mouse._tracking_context

    def test_one_physical_click_is_counted_once_not_on_release(self):
        self.mouse.record_click('left', 100, 100, True)
        self.mouse.record_click('left', 100, 100, False)
        bucket = next(iter(self.mouse.time_buckets.values()))
        self.assertEqual(self.mouse.click_counts['left'], 1)
        self.assertEqual(bucket['click_events'], 1)
        self.assertEqual(bucket['total_events'], 1)

    def test_scroll_directions_and_totals_are_exact(self):
        for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            self.mouse.record_scroll(100, 100, dx, dy)
        bucket = next(iter(self.mouse.time_buckets.values()))
        self.assertEqual(self.mouse.scroll_counts, {'up': 1, 'down': 1, 'left': 1, 'right': 1})
        self.assertEqual(bucket['scroll_events'], 4)
        self.assertEqual(bucket['total_events'], 4)


if __name__ == '__main__':
    unittest.main()
