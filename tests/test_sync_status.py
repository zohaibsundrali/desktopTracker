import unittest
from sync_status import session_sync_text


class SyncStatusTests(unittest.TestCase):
    def test_pending_is_not_claimed_uploaded(self):
        text, tone = session_sync_text({'pending': 2, 'last_success_at': '2026-09-12T08:00:00Z'})
        self.assertIn('2 saved locally, waiting to upload', text)
        self.assertEqual(tone, 'warning')

    def test_no_history_does_not_claim_server_success(self):
        self.assertIn('waiting for first', session_sync_text({'pending': 0})[0])

    def test_error_never_displays_raw_provider_text(self):
        text, tone = session_sync_text({'pending': 2, 'error': 'PRIVATE_TOKEN_AND_EMAIL'})
        self.assertNotIn('PRIVATE', text)
        self.assertIn('needs attention', text)
        self.assertEqual(tone, 'warning')

    def test_legacy_records_are_not_hidden_by_empty_current_queue(self):
        text, tone = session_sync_text({'pending': 0, 'legacy_pending': True})
        self.assertIn('recovery review', text)
        self.assertEqual(tone, 'warning')

    def test_invalid_snapshots_fail_visibly(self):
        for value in [None, {}, {'pending': -1}, {'pending': True}, {'pending': '2'}]:
            self.assertEqual(session_sync_text(value), ('Session sync status unavailable', 'warning'))

    def test_success_and_malformed_timestamp(self):
        self.assertTrue(session_sync_text({'pending': 0, 'last_success_at': '2026-09-12T08:00:00Z'})[0].startswith('Last session sync:'))
        self.assertEqual(session_sync_text({'pending': 0, 'last_success_at': 'invalid'})[0], 'Session sync: no pending session summaries')


if __name__ == '__main__':
    unittest.main()
