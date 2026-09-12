import unittest
from sync_status import idle_reminder_text

class IdleStatusTests(unittest.TestCase):
    def test_pending_does_not_claim_a_time_deduction(self):
        text, pending = idle_reminder_text(dict(available=True,enabled=True,threshold_seconds=60,idle_seconds=80,pending=True,paused=False))
        self.assertTrue(pending)
        self.assertIn('No time has been deducted',text)

    def test_unavailable_disabled_paused_or_missing_input_never_offer_idle_actions(self):
        base=dict(available=True,enabled=True,threshold_seconds=60,idle_seconds=80,pending=True,paused=False)
        for change in ({'available':False},{'enabled':False},{'paused':True},{'idle_seconds':None},{'idle_seconds':float('nan')}):
            self.assertFalse(idle_reminder_text(dict(base,**change))[1])
