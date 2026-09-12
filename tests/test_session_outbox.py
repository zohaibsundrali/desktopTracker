"""Real disk/process regressions, with upload callbacks only; no hosted requests."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from session_outbox import SessionOutbox

IDENTITY = ('auth-a', 'org-a', 'staff-a', 'developer')


def row(session='one', status='periodic', duration=10):
    return dict(session_id=session, user_id='staff-a', organization_id='org-a',
                status=status, total_duration=duration)


class SessionOutboxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.queue = SessionOutbox(self.temp.name, 'https://project.test', IDENTITY)

    def test_network_failure_survives_reopen_without_new_id(self):
        self.queue.put(row())
        self.assertEqual(self.queue.replay(lambda _: False), 0)
        restarted = SessionOutbox(self.temp.name, 'https://project.test', IDENTITY)
        uploaded = []
        restarted.replay(lambda item: uploaded.append(item) or True)
        self.assertEqual(uploaded, [row()])
        self.assertEqual(restarted.count(), 0)

    def test_process_crash_during_upload_retains_payload_and_releases_lock(self):
        self.queue.put(row())
        script = '''from session_outbox import SessionOutbox
import os,sys
q=SessionOutbox(sys.argv[1], 'https://project.test', ('auth-a','org-a','staff-a','developer'))
q.replay(lambda row: os._exit(17))
'''
        result = subprocess.run([sys.executable, '-c', script, self.temp.name], cwd=Path(__file__).resolve().parents[1])
        self.assertEqual(result.returncode, 17)
        self.assertEqual(self.queue.count(), 1)
        self.assertEqual(self.queue.replay(lambda _: True), 1)

    def test_crash_after_server_success_before_ack_replays_same_id(self):
        self.queue.put(row())
        remote = {}
        def upload(item):
            remote[item['session_id']] = item
            return True
        with patch.object(self.queue, 'acknowledge', side_effect=RuntimeError('crash')):
            with self.assertRaises(RuntimeError):
                self.queue.replay(upload)
        self.queue.replay(upload)
        self.assertEqual(len(remote), 1)
        self.assertEqual(self.queue.count(), 0)

    def test_newer_final_payload_survives_ack_of_inflight_periodic(self):
        self.queue.put(row())
        def upload(_):
            self.queue.put(row(status='completed', duration=20))
            return True
        self.queue.replay(upload)
        self.assertEqual(json.loads(self.queue.snapshot()[0][1])['status'], 'completed')
        sent = []
        self.queue.replay(lambda item: sent.append(item) or True)
        self.assertEqual(sent[0]['total_duration'], 20)

    def test_late_periodic_never_resurrects_completed_session_after_ack(self):
        self.queue.put(row(status='completed'))
        self.queue.replay(lambda _: True)
        restarted = SessionOutbox(self.temp.name, 'https://project.test', IDENTITY)
        restarted.put(row(duration=2))
        self.assertEqual(restarted.count(), 0)

    def test_only_one_drain_sends_across_instances_while_producers_keep_writing(self):
        self.queue.put(row())
        second = SessionOutbox(self.temp.name, 'https://project.test', IDENTITY)
        entered, release = threading.Event(), threading.Event()
        uploaded = []
        def upload(item):
            entered.set()
            release.wait(3)
            uploaded.append(item)
            return True
        thread = threading.Thread(target=lambda: self.queue.replay(upload))
        thread.start()
        try:
            self.assertTrue(entered.wait(2))
            second.put(row(status='completed', duration=20))
            self.assertEqual(second.replay(lambda _: self.fail('Concurrent upload')), 0)
        finally:
            release.set()
            thread.join(3)
        second.replay(lambda item: uploaded.append(item) or True)
        self.assertEqual([item['status'] for item in uploaded], ['periodic', 'completed'])

    def test_scope_includes_project_auth_organization_profile_and_type(self):
        self.queue.put(row())
        variants = [('other-auth', *IDENTITY[1:]), (IDENTITY[0], 'other-org', *IDENTITY[2:]),
                    (*IDENTITY[:2], 'other-profile', IDENTITY[3]), (*IDENTITY[:3], 'admin')]
        for identity in variants:
            other = SessionOutbox(self.temp.name, 'https://project.test', identity)
            self.assertEqual(other.count(), 0)
            self.assertEqual(other.replay(lambda _: self.fail('Cross-account replay')), 0)
        other = SessionOutbox(self.temp.name, 'https://other-project.test', IDENTITY)
        self.assertEqual(other.count(), 0)
        self.assertEqual(self.queue.count(), 1)

    def test_mismatched_and_unbound_payloads_refused(self):
        for bad in [dict(row(), organization_id=None), dict(row(), user_id='someone-else'), dict(row(), session_id='')]:
            with self.assertRaises(ValueError):
                self.queue.put(bad)
        self.assertEqual(self.queue.count(), 0)

    def test_malformed_legacy_file_is_never_read_or_truncated(self):
        legacy = Path(self.temp.name) / '.pending_sessions.jsonl'
        content = b'{broken\n{"user_id":"other-user"}\n'
        legacy.write_bytes(content)
        self.queue.replay(lambda _: True)
        self.assertEqual(legacy.read_bytes(), content)

    def test_corrupt_payload_not_silently_deleted(self):
        self.queue.put(row())
        with self.queue.connect() as connection:
            connection.execute("update pending set payload='broken'")
        self.queue.put(row(session='healthy'))
        uploaded = []
        self.assertEqual(self.queue.replay(lambda item: uploaded.append(item) or True), 1)
        self.assertEqual(uploaded[0]['session_id'], 'healthy')
        self.assertTrue(self.queue.last_replay_error)
        self.assertEqual(self.queue.count(), 1)
        self.assertEqual(self.queue.snapshot(), [])
        self.queue.replay(lambda _: self.fail('Corrupt row retried'))
        self.assertTrue(self.queue.last_replay_error)

    def test_sqlite_rollback_preserves_previous_payload(self):
        self.queue.put(row())
        with self.assertRaises(RuntimeError):
            with self.queue.connect() as connection:
                connection.execute('delete from pending')
                raise RuntimeError('interrupted transaction')
        self.assertEqual(self.queue.count(), 1)


if __name__ == '__main__':
    unittest.main()
