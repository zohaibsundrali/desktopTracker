"""Exercise real tracker transports against an explicitly disposable QA tenant.

No desktop capture is started. All samples are synthetic. This verifies delivery,
receipts, replay, authorized reads and cleanup; Windows capture needs its own test.
Credentials are read from files/environment, never command-line arguments or reports.
"""
import argparse
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import uuid
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import dotenv_values
import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', required=True, type=Path)
    parser.add_argument('--backend-env-file', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--base-url', help='Optional running website to verify its keyboard API')
    parser.add_argument('--allow-qa-writes', action='store_true')
    parser.add_argument('--verify-role-access', action='store_true', help='Verify HR, manager, team lead and unrelated staff with temporary QA reporting links')
    parser.add_argument('--pause-before-cleanup', action='store_true', help='Keep synthetic samples for an interactive browser check; Enter always resumes cleanup')
    args = parser.parse_args()
    if not args.allow_qa_writes:
        parser.error('--allow-qa-writes is required; only disposable QA tenants are accepted')
    if not args.env_file.is_file() or not args.backend_env_file.is_file():
        parser.error('Both explicit environment files must exist')
    env = {**dotenv_values(args.backend_env_file), **dotenv_values(args.env_file), **os.environ}
    required = ('NEXT_PUBLIC_SUPABASE_URL', 'NEXT_PUBLIC_SUPABASE_ANON_KEY', 'SUPABASE_SERVICE_ROLE_KEY',
                'E2E_DEVELOPER_EMAIL', 'E2E_DEVELOPER_PASSWORD', 'E2E_OWNER_EMAIL', 'E2E_OWNER_PASSWORD',
                'E2E_ORG_B_OWNER_EMAIL', 'E2E_ORG_B_OWNER_PASSWORD')
    if any(not env.get(name) for name in required):
        parser.error('Missing required backend or QA owner/developer/other-organization credentials')
    url = env['NEXT_PUBLIC_SUPABASE_URL'].rstrip('/')
    key = env['NEXT_PUBLIC_SUPABASE_ANON_KEY']
    service = env['SUPABASE_SERVICE_ROLE_KEY']
    os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'] = url, key
    from auth_manager import AuthManager
    import supabase_session
    from session_outbox import SessionOutbox
    from input_upload import InputSync, upload_input
    from activity_upload import upload_activity
    from screenshot_upload import upload_capture

    results, tokens = [], []
    session_id = 'qa-roundtrip-' + str(uuid.uuid4())
    report = {'run': session_id, 'scope': 'Synthetic data through real Python transports and hosted Supabase',
              'windows_capture_tested': False, 'started_at': datetime.now(timezone.utc).isoformat(), 'results': results}
    auth, context, device, storage_path, capture_id = None, None, None, None, None
    reporting_restore = []
    role_viewers = {}
    client = httpx.Client(timeout=30, follow_redirects=False)
    admin_headers = {'apikey': key, 'Authorization': 'Bearer ' + service}

    def save():
        report['passed'] = sum(r['status'] == 'PASS' for r in results)
        report['failed'] = sum(r['status'] == 'FAIL' for r in results)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + '\n')
    save()

    def request(method, path, token=None, **kwargs):
        headers = dict(admin_headers if token is None else {'apikey': key, 'Authorization': 'Bearer ' + token})
        headers.update(kwargs.pop('headers', {}))
        response = client.request(method, url + path, headers=headers, **kwargs)
        if response.is_error:
            try:
                code = response.json().get('code', response.status_code)
            except (ValueError, AttributeError):
                code = response.status_code
            raise RuntimeError(f'{method} {path.split("?")[0]}: HTTP {response.status_code}, code {code}')
        return response.json() if response.content else None

    def check(name, fn):
        try:
            fn()
            results.append({'name': name, 'status': 'PASS'})
        except Exception as error:
            # The transport SDK can include credentials in reprs; emit only a
            # controlled assertion or our bounded HTTP/code error.
            detail = str(error) if isinstance(error, (AssertionError, RuntimeError)) else type(error).__name__ + ': ' + str(getattr(error, 'code', '')) + ' ' + str(getattr(error, 'message', ''))
            results.append({'name': name, 'status': 'FAIL', 'detail': detail[:250]})
        print(results[-1]['status'], name, flush=True)
        save()

    def require(value, message):
        if not value:
            raise AssertionError(message)

    def login(role):
        result = request('POST', '/auth/v1/token?grant_type=password', key,
                         json={'email': env[f'E2E_{role}_EMAIL'], 'password': env[f'E2E_{role}_PASSWORD']})
        tokens.append(result['access_token'])
        return result['access_token'], result['user']

    def rows(table, token, field='session_id', value=None):
        return request('GET', '/rest/v1/' + table, token,
                       params={'select': '*', field: 'eq.' + (value or session_id)})

    try:
        # Establish that these are test identities before enrolling any device.
        profile = request('GET', '/rest/v1/developers', params={
            'select': 'id,organization_id,auth_user_id', 'email': 'eq.' + env['E2E_DEVELOPER_EMAIL']})
        require(len(profile) == 1, 'Expected exactly one QA developer profile')
        org = profile[0]['organization_id']
        organization = request('GET', '/rest/v1/organizations', params={'select': 'name', 'id': 'eq.' + org})
        require(len(organization) == 1 and re.fullmatch(r'(QA Test Org [AB]|Verisade QA [a-z0-9-]+ [AB])', organization[0]['name']),
                'Refusing to write outside a named disposable QA organization')
        owner_token, owner = login('OWNER')
        require(owner['app_metadata'].get('organization_id') == org, 'QA owner must belong to the same organization')
        other_token, other = login('ORG_B_OWNER')
        require(other['app_metadata'].get('organization_id') != org, 'Isolation control needs a different organization')
        auth = AuthManager()
        with patch('platform.node', return_value=session_id):
            ok, _, user = auth.login(env['E2E_DEVELOPER_EMAIL'], env['E2E_DEVELOPER_PASSWORD'])
        require(ok, 'Real desktop login/device enrollment failed')
        context = supabase_session.tracking_context()
        device = auth._device_id
        report['device_id'] = device
        report['organization_id'] = org
        save()
        require(context and context[1] == org and context[2] == profile[0]['id'], 'Desktop identity mismatch')
        token = supabase_session.access_token()
        # Log only bounded provider error codes/messages; never request headers,
        # successful Auth bodies, tokens, credentials or screenshot bytes.
        network_errors = []
        report['transport_errors'] = network_errors
        real_http_client = httpx.Client
        def capture_failure(response):
            if response.is_error:
                response.read()
                try:
                    body = response.json()
                    network_errors.append({'path': response.request.url.path,
                        'status': response.status_code, 'code': body.get('code'),
                        'message': str(body.get('message', body.get('error', '')))[:200]})
                except (ValueError, AttributeError):
                    pass
        def diagnostic_client(*a, **kw):
            kw['event_hooks'] = {'response': [capture_failure]}
            return real_http_client(*a, **kw)
        httpx.Client = diagnostic_client
        results.append({'name': 'Real desktop login and device enrollment', 'status': 'PASS'})
        print('PASS Real desktop login and device enrollment', flush=True)

        if args.verify_role_access:
            for role in ('HR', 'MANAGER', 'TEAM_LEAD', 'EMPLOYEE', 'FINANCE', 'CLIENT'):
                viewer, identity = login(role)
                require(identity['app_metadata'].get('organization_id') == org, 'Role test identity is outside QA organization')
                role_viewers[role] = viewer
            identities = {}
            for role in ('DEVELOPER', 'MANAGER', 'TEAM_LEAD', 'EMPLOYEE'):
                found = request('GET', '/rest/v1/memberships', params={'select': 'id,user_id,user_type,reports_to,role',
                    'organization_id': 'eq.' + org, 'email': 'eq.' + env[f'E2E_{role}_EMAIL'], 'status': 'eq.active'})
                require(len(found) == 1, 'QA reporting identity is ambiguous: ' + role)
                identities[role] = found[0]
            for child, parent in (('TEAM_LEAD', 'MANAGER'), ('DEVELOPER', 'TEAM_LEAD')):
                member = identities[child]
                reporting_restore.append((member['id'], member['reports_to']))
                request('PATCH', '/rest/v1/memberships', params={'id': 'eq.' + member['id'], 'organization_id': 'eq.' + org},
                    json={'reports_to': identities[parent]['user_id']})
            report['developer_id'] = user.id
            report['unrelated_developer_id'] = identities['EMPLOYEE']['user_id']
            save()

        now = datetime.now(timezone.utc)
        start, end = (now - timedelta(seconds=60)).isoformat(), now.isoformat()
        row = dict(session_id=session_id, organization_id=org, user_id=user.id, user_email=user.email,
                   start_time=start, end_time=end, total_duration=60, active_duration=45, idle_duration=15,
                   break_duration=0, break_periods=[], productivity_score=75, mouse_events=10,
                   keyboard_events=12, screenshots_taken=0, status='completed', project_id=None, task_id=None,
                   app_usage_summary='{}')
        allowed = lambda: supabase_session.tracking_context() == context
        with tempfile.TemporaryDirectory(prefix='tracker-roundtrip-') as directory:
            outbox = SessionOutbox(directory, url, context[:4])

            def upload_session(payload):
                response = supabase_session.session_upsert_request(auth.supabase, context, payload).execute()
                return any(item.get('session_id') == session_id and item.get('user_id') == user.id for item in response.data)

            def session_test():
                outbox.put(row)
                require(outbox.replay(lambda _: False) == 0 and outbox.count() == 1, 'Failed send must retain durable session')
                require(outbox.replay(upload_session) == 1 and outbox.count() == 0, 'Session must drain only after a matching receipt')
                outbox.put(row)
                require(outbox.replay(upload_session) == 1, 'Session replay failed')
                for viewer in (token, owner_token):
                    found = rows('productivity_sessions', viewer)
                    require(len(found) == 1 and found[0]['total_duration'] == 60 and found[0]['active_duration'] == 45,
                            'Session fetch lost data or duplicated replay')
            check('Durable session send, retry, exact owner/staff readback', session_test)

            keyboard = dict(organization_id=org, developer_id=user.id, session_id=session_id,
                            user_email=user.email, total_time_minutes=1, active_time_minutes=.75,
                            idle_time_minutes=.25, keyboard_activity_percentage=75, total_keys=12,
                            unique_keys=8, words_per_minute=2.4, activity_score=75, per_minute_summary=[], tracked_at=end)
            mouse = dict(organization_id=org, developer_id=user.id, session_id=session_id,
                         developer_name='QA tracker roundtrip', timestamp=end, activity_status='active',
                         active_percentage=75, idle_percentage=25, total_events=10, move_events=6, click_events=3, scroll_events=1)
            for kind, payload, table, count_key, expected in (
                    ('keyboard', keyboard, 'keyboard_stats', 'total_keys', 12),
                    ('mouse', mouse, 'mouse_activities', 'total_events', 10)):
                def input_test(kind=kind, payload=payload, table=table, count_key=count_key, expected=expected):
                    enabled = [False]
                    sync = InputSync(directory, url, key, context, allowed=lambda: enabled[0] and allowed(), kind=kind)
                    capture = sync.capture(kind, payload)
                    require(sync.replay() == 0 and sync.snapshot()['pending'] == 1, 'Offline capture must stay queued')
                    enabled[0] = True
                    require(sync.replay() == 1 and sync.snapshot()['pending'] == 0, 'Capture upload did not acknowledge')
                    require(upload_input(url, key, context, allowed, kind, capture, payload), 'Idempotent retry failed')
                    for viewer in (token, owner_token):
                        found = rows(table, viewer)
                        require(len(found) == 1 and found[0][count_key] == expected, 'Input readback/count or replay mismatch')
                check(f'{kind} durable send, reconnect, duplicate prevention and readback', input_test)

            common = dict(organization_id=org, user_email=user.email, user_login=user.email,
                          session_id=session_id, duration_seconds=30, duration_minutes=.5)
            for kind, table, payload in (
                    ('app', 'app_usage', dict(common, app_name='QA tracker roundtrip', app_name_raw='qa-roundtrip.exe',
                                             window_title='Synthetic test', start_time=start, end_time=end)),
                    ('browser', 'browser_usage', dict(common, site='example.invalid', first_seen=start, last_seen=end))):
                def activity_test(kind=kind, table=table, payload=payload):
                    for _ in range(2):
                        require(upload_activity(url, key, context, kind, payload, 1, allowed), 'Activity receipt missing')
                    updated = dict(payload, duration_seconds=45, duration_minutes=.75)
                    require(upload_activity(url, key, context, kind, updated, 2, allowed), 'Activity revision not acknowledged')
                    for viewer in (token, owner_token):
                        found = rows(table, viewer)
                        require(len(found) == 1 and found[0]['duration_seconds'] == 45, 'Activity totals or replay mismatch')
                check(f'{kind} aggregate upload, revision, duplicate prevention and readback', activity_test)

            capture_id = str(uuid.uuid4())
            storage_path = f'{org}/{user.id}/capture_{capture_id}.png'
            report['screenshot_capture_id'] = capture_id
            report['storage_path'] = storage_path
            save()
            # Fixed, synthetic 1x1 PNG; never reads the user's display.
            image = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')
            metadata = dict(organization_id=org, developer_id=user.id, developer_email=user.email,
                            storage_path=storage_path, filename=f'capture_{capture_id}.png',
                            public_url=None, mime_type='image/png', width=1, height=1, size_kb=len(image)/1024,
                            timestamp=end, app_active='QA tracker roundtrip', is_annotated=False, annotation_text=None)
            def screenshot_test():
                for _ in range(2):
                    require(upload_capture(url, key, context, allowed, capture_id, metadata, image,
                                           hashlib.sha256(image).hexdigest(), False, lambda: None), 'Screenshot receipt missing')
                found = rows('screenshots', owner_token, 'capture_id', capture_id)
                require(len(found) == 1 and found[0]['storage_path'] == storage_path, 'Screenshot metadata/readback mismatch')
                response = client.get(url + '/storage/v1/object/authenticated/monitoring/' + storage_path,
                                      headers={'apikey': key, 'Authorization': 'Bearer ' + owner_token})
                require(response.status_code == 200 and response.content == image, 'Stored screenshot bytes differ')
            check('Synthetic screenshot upload, duplicate recovery and exact bytes fetched', screenshot_test)

            def isolation_test():
                for table in ('productivity_sessions', 'keyboard_stats', 'mouse_activities', 'app_usage', 'browser_usage'):
                    require(not rows(table, other_token), 'Cross-organization read exposed test data: ' + table)
                    require(not rows(table, key), 'Anonymous read exposed test data: ' + table)
            check('Other organization and anonymous users cannot fetch the samples', isolation_test)

            if args.base_url:
                def web_test():
                    response = client.get(args.base_url.rstrip('/') + '/api/keyboard-stats',
                        headers={'Authorization': 'Bearer ' + owner_token}, params={
                            'developerId': user.id, 'start': start, 'end': (now + timedelta(seconds=1)).isoformat()})
                    require(response.status_code == 200, 'Website keyboard API returned HTTP ' + str(response.status_code))
                    matching = [r for r in response.json().get('data', []) if r['session_id'] == session_id]
                    require(len(matching) == 1 and matching[0]['total_keys'] == 12, 'Website API did not return uploaded keyboard metrics')
                check('Website API fetches the tracker keyboard sample', web_test)

            if args.verify_role_access:
                def role_access_test(role, viewer, expected):
                    for table in ('productivity_sessions', 'keyboard_stats', 'mouse_activities', 'app_usage', 'browser_usage'):
                        found = rows(table, viewer)
                        require(len(found) == (1 if expected else 0), role + ' has incorrect scope for ' + table)
                    found = rows('screenshots', viewer, 'capture_id', capture_id)
                    require(len(found) == (1 if expected else 0), role + ' has incorrect screenshot metadata access')
                    response = client.get(url + '/storage/v1/object/authenticated/monitoring/' + storage_path,
                        headers={'apikey': key, 'Authorization': 'Bearer ' + viewer})
                    require((response.status_code == 200 and response.content == image) if expected else response.status_code != 200,
                        role + ' has incorrect screenshot object access')
                    roster = request('POST', '/rest/v1/rpc/monitoring_roster', viewer, json={'p_organization_id': org})
                    require(any(item['id'] == user.id for item in roster) == expected, role + ' has incorrect tracking selector scope')
                    if role in ('MANAGER', 'TEAM_LEAD'):
                        require(not any(item['id'] == identities['EMPLOYEE']['user_id'] for item in roster), 'Unrelated staff leaked into team selector')
                    page = client.post(url + '/rest/v1/rpc/monitoring_screenshot_page',
                        headers={'apikey': key, 'Authorization': 'Bearer ' + viewer}, json={
                            'p_organization_id': org, 'p_developer_id': user.id,
                            'p_start': start, 'p_end': (now + timedelta(seconds=1)).isoformat()})
                    require(page.is_success if expected else page.status_code == 403, role + ' has incorrect screenshot page access')
                    if expected:
                        require(any(item['storage_path'] == storage_path for item in page.json()['rows']), role + ' screenshot missing from page')
                    presence = client.post(url + '/rest/v1/rpc/monitoring_tracker_presence',
                        headers={'apikey': key, 'Authorization': 'Bearer ' + viewer}, json={'p_organization_id': org, 'p_developer_id': user.id})
                    require(presence.is_success if expected else presence.status_code == 403, role + ' has incorrect presence access')
                for role, viewer, expected in [('SELF', token, True), ('OWNER', owner_token, True)] + [
                        (role, viewer, role in ('HR', 'MANAGER', 'TEAM_LEAD')) for role, viewer in role_viewers.items()]:
                    check(role + ' real database, private screenshot, roster and presence access',
                        lambda role=role, viewer=viewer, expected=expected: role_access_test(role, viewer, expected))
            if args.pause_before_cleanup:
                save()
                print('Samples ready for browser verification. Press Enter to revoke the QA device and clean up.', flush=True)
                input()

            def revocation_test():
                request('PATCH', '/rest/v1/tracker_devices', params={'id': 'eq.' + device, 'organization_id': 'eq.' + org},
                        json={'revoked_at': datetime.now(timezone.utc).isoformat()})
                require(not upload_input(url, key, context, allowed, 'keyboard', str(uuid.uuid4()), keyboard),
                        'Revoked device still uploaded input')
            check('Revoked tracker device cannot send more captures', revocation_test)
    except Exception as error:
        detail = str(error) if isinstance(error, (AssertionError, RuntimeError)) else type(error).__name__
        results.append({'name': 'Preflight/setup', 'status': 'FAIL', 'detail': detail[:250]})
        print('FAIL Preflight/setup:', detail[:250], flush=True)
    finally:
        if auth:
            auth.logout()
        if context:
            if storage_path:
                check('Clean up this run’s synthetic image', lambda: request('DELETE', '/storage/v1/object/monitoring', json={'prefixes': [storage_path]}))
            if capture_id:
                check('Clean up this run’s screenshot metadata', lambda: request('DELETE', '/rest/v1/screenshots', params={'capture_id': 'eq.' + capture_id, 'organization_id': 'eq.' + context[1]}))
            for table in ('keyboard_stats', 'mouse_activities', 'app_usage', 'browser_usage', 'productivity_sessions'):
                def cleanup(table=table):
                    request('DELETE', '/rest/v1/' + table, params={'session_id': 'eq.' + session_id, 'organization_id': 'eq.' + context[1]})
                    require(not rows(table, None), 'QA cleanup left records in ' + table)
                check('Clean up this run’s ' + table, cleanup)
            if device:
                check('Clean up this run’s enrolled device', lambda: request('DELETE', '/rest/v1/tracker_devices', params={'id': 'eq.' + device, 'organization_id': 'eq.' + context[1]}))
        if context:
            for member_id, previous_parent in reversed(reporting_restore):
                def restore(member_id=member_id, previous_parent=previous_parent):
                    request('PATCH', '/rest/v1/memberships', params={'id': 'eq.' + member_id, 'organization_id': 'eq.' + context[1]},
                        json={'reports_to': previous_parent})
                    found = request('GET', '/rest/v1/memberships', params={'select': 'reports_to', 'id': 'eq.' + member_id,
                        'organization_id': 'eq.' + context[1]})
                    require(len(found) == 1 and found[0]['reports_to'] == previous_parent, 'Reporting link restoration failed')
                check('Restore temporary QA reporting link', restore)
        for token in tokens:
            try:
                request('POST', '/auth/v1/logout?scope=local', token)
            except Exception:
                results.append({'name': 'QA login session cleanup', 'status': 'FAIL'})
        client.close()
        if 'real_http_client' in locals():
            httpx.Client = real_http_client
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        save()
        print(json.dumps({'passed': report['passed'], 'failed': report['failed']}))
    return 1 if report['failed'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
