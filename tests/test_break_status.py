import unittest
from sync_status import break_status_text

class BreakStatusTests(unittest.TestCase):
    def test_live_break_and_completed_break_are_distinguished(self):
        self.assertEqual(break_status_text({'count':2,'duration_seconds':3661.9,'paused':True}),
                         ('On break: 2 · 01:01:01 excluded from tracked time','muted'))
        self.assertTrue(break_status_text({'count':2,'duration_seconds':60,'paused':False})[0].startswith('Breaks:'))

    def test_unavailable_or_invalid_data_is_not_zero_breaks(self):
        for state in (None, {}, {'count':True,'duration_seconds':1,'paused':False},
                      {'count':1,'duration_seconds':float('nan'),'paused':False},
                      {'count':1,'duration_seconds':-1,'paused':False}):
            self.assertEqual(break_status_text(state),('Break status unavailable','warning'))
