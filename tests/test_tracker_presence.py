"""Presence is ephemeral, identity-bound telemetry, never offline activity replay."""
import threading
import unittest
from unittest.mock import MagicMock, patch
from tracker_presence import PresenceTransport, PresenceWorker


CTX = ('auth', 'org', 'staff', 'developer', 'jwt-session')


class TransportTests(unittest.TestCase):
    def test_http_request_owns_jwt_and_bounded_timeout(self):
        client = MagicMock()
        response = client.__enter__.return_value.post.return_value
        response.status_code = 200
        response.json.return_value = {'ok': True}
        with patch('tracker_presence.httpx.Client', return_value=client) as constructor:
            result = PresenceTransport('https://project.test/', 'public')('frozen-token', 'rpc_name', {'p_state':'idle'})
        self.assertEqual(result, {'ok': True})
        request = client.__enter__.return_value.post.call_args
        self.assertEqual(request.args[0], 'https://project.test/rest/v1/rpc/rpc_name')
        self.assertEqual(request.kwargs['headers']['Authorization'], 'Bearer frozen-token')
        self.assertFalse(constructor.call_args.kwargs['follow_redirects'])
        self.assertFalse(constructor.call_args.kwargs['trust_env'])
        self.assertEqual(constructor.call_args.kwargs['timeout'].connect, 5)
        self.assertEqual(constructor.call_args.kwargs['timeout'].read, 10)

    def test_http_failure_does_not_include_response_or_secrets(self):
        client = MagicMock()
        client.__enter__.return_value.post.return_value.status_code = 403
        with patch('tracker_presence.httpx.Client', return_value=client):
            with self.assertRaisesRegex(OSError, '^Presence unavailable$'):
                PresenceTransport('https://project.test', 'public')('secret', 'rpc', {})


EPOCH = '11111111-1111-4111-8111-111111111111'

def ack(sequence=0, state='idle'):
    return {'epoch': EPOCH, 'sequence': sequence, 'state': state, 'received_at':'2026-09-12T12:00:00+00:00'}


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.identity, self.token = CTX, 'token-a'
        self.calls = []
        def transport(token, rpc, payload):
            self.calls.append((token, rpc, dict(payload)))
            if rpc == 'get_tracker_presence_epoch':
                return {'epoch': None}
            return ack(payload.get('p_sequence', 0), payload['p_state'])
        self.transport = transport
        self.worker = PresenceWorker(lambda: (self.identity, self.token), lambda *args:self.transport(*args))

    def test_state_changes_and_paused_keepalive_use_increasing_sequence(self):
        self.worker.set_state(CTX, 'tracking')
        self.worker.tick()
        self.worker.set_state(CTX, 'paused')
        self.worker.tick()
        self.worker.tick()
        self.worker.set_state(CTX, 'idle')
        self.worker.tick()
        heartbeats = [p for _,rpc,p in self.calls if rpc == 'heartbeat_tracker_presence']
        self.assertEqual([p['p_state'] for p in heartbeats], ['tracking','paused','paused','idle'])
        self.assertEqual([p['p_sequence'] for p in heartbeats], [1,2,3,4])
        self.assertEqual(self.worker.interval, 30)

    def test_offline_failure_drops_old_state_instead_of_replaying(self):
        self.worker.tick()
        original = self.transport
        def offline(token, rpc, payload):
            original(token,rpc,payload)
            raise OSError('offline')
        self.transport = offline
        self.worker.set_state(CTX, 'tracking')
        self.worker.tick()
        self.transport = original
        self.worker.set_state(CTX, 'paused')
        self.worker.tick()
        self.assertEqual(self.calls[-1][2]['p_state'], 'paused')
        self.assertEqual(self.calls[-1][2]['p_sequence'], 3)

    def test_refresh_preserves_epoch_but_freezes_each_request_token(self):
        self.worker.tick()
        self.token = 'rotated'
        self.worker.tick()
        self.assertEqual(self.calls[-1][0], 'rotated')
        self.assertEqual(self.calls[-1][2]['p_sequence'], 2)
        self.assertEqual(sum(rpc == 'start_tracker_presence_stream' for _,rpc,_ in self.calls), 1)

    def test_identity_switch_clears_state_and_claims_new_stream(self):
        self.worker.set_state(CTX, 'tracking')
        self.worker.tick()
        first_nonce = self.calls[1][2]['p_stream_id']
        self.identity, self.token = ('other',) + CTX[1:], 'token-b'
        self.worker.tick()
        self.assertEqual(self.calls[-1][2]['p_state'], 'idle')
        self.assertEqual(self.calls[-1][2]['p_sequence'], 1)
        self.assertNotEqual(first_nonce, self.calls[-2][2]['p_stream_id'])

    def test_ambiguous_initialization_reuses_cas_and_nonce_with_current_state(self):
        original = self.transport
        def offline(token, rpc, payload):
            result = original(token,rpc,payload)
            if rpc == 'start_tracker_presence_stream':
                raise OSError('ambiguous')
            return result
        self.transport = offline
        self.worker.tick()
        initial = self.calls[-1][2]
        self.transport = original
        self.worker.set_state(CTX, 'paused')
        self.worker.tick()
        retry = self.calls[-2][2]
        self.assertEqual(initial['p_stream_id'], retry['p_stream_id'])
        self.assertEqual(initial['p_expected_epoch'], retry['p_expected_epoch'])
        self.assertEqual(retry['p_state'], 'paused')
        self.assertEqual(sum(rpc == 'get_tracker_presence_epoch' for _,rpc,_ in self.calls), 1)

    def test_stale_stream_never_reacquires_or_sends_again(self):
        from tracker_presence import PresenceError
        self.worker.tick()
        self.transport = MagicMock(side_effect=PresenceError('PRESENCE_STREAM_STALE'))
        self.worker.tick()
        self.worker.tick()
        self.assertEqual(self.transport.call_count, 1)

    def test_server_ack_sequence_after_ambiguous_init_is_preserved(self):
        original = self.transport
        def recovered(token,rpc,payload):
            result = original(token,rpc,payload)
            return ack(7,'tracking') if rpc == 'start_tracker_presence_stream' else result
        self.transport = recovered
        self.worker.tick()
        self.assertEqual(self.calls[-1][2]['p_sequence'], 8)

    def test_logout_during_response_does_not_send_followup(self):
        original = self.transport
        def logout(token,rpc,payload):
            result = original(token,rpc,payload)
            self.identity = None
            return result
        self.transport = logout
        self.worker.tick()
        self.assertEqual(len(self.calls), 1)

    def test_concurrent_ticks_are_serial_and_stop_does_not_wait_for_network(self):
        entered, release = threading.Event(), threading.Event()
        original = self.transport
        def delayed(token,rpc,payload):
            entered.set()
            release.wait(2)
            return original(token,rpc,payload)
        self.transport = delayed
        thread = threading.Thread(target=self.worker.tick)
        thread.start()
        self.assertTrue(entered.wait(1))
        self.worker.tick()
        self.worker.stop()
        release.set()
        thread.join(2)
        self.assertEqual(len(self.calls), 1)
        self.worker.tick()
        self.assertEqual(len(self.calls), 1)

    def test_worker_wakes_on_state_change_while_paused(self):
        reached = threading.Event()
        original = self.transport
        def observed(token,rpc,payload):
            result = original(token,rpc,payload)
            if rpc == 'heartbeat_tracker_presence' and payload['p_state'] == 'paused':
                reached.set()
            return result
        self.transport = observed
        self.worker.start()
        self.worker.set_state(CTX, 'paused')
        self.assertTrue(reached.wait(1))
        self.worker.stop()
        self.worker._thread.join(1)

    def test_missing_migration_recovers_without_blocking_local_state(self):
        original = self.transport
        self.transport = MagicMock(side_effect=OSError('missing migration'))
        self.worker.tick()
        self.worker.set_state(CTX, 'paused')
        self.transport = original
        self.worker.tick()
        self.assertEqual(self.calls[-1][2]['p_state'], 'paused')
        self.assertEqual(self.calls[-1][2]['p_sequence'], 1)

    def test_state_updates_do_not_wait_for_an_inflight_request(self):
        entered, release, updated = threading.Event(), threading.Event(), threading.Event()
        original = self.transport
        def delayed(token,rpc,payload):
            entered.set()
            release.wait(2)
            return original(token,rpc,payload)
        self.transport = delayed
        thread = threading.Thread(target=self.worker.tick)
        thread.start()
        self.assertTrue(entered.wait(1))
        updater = threading.Thread(target=lambda:(self.worker.set_state(CTX,'paused'),updated.set()))
        updater.start()
        try:
            self.assertTrue(updated.wait(0.5))
        finally:
            release.set()
            updater.join(2)
            thread.join(2)
        self.assertEqual(self.calls[-1][2]['p_state'], 'paused')
