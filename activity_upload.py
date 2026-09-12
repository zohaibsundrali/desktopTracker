"""Frozen-identity transport for aggregate receipts; no mutable SDK credentials."""
import httpx
import supabase_session


def upload_activity(project,public_key,context,kind,record,revision,allowed):
    if not allowed():
        return False
    try:
        with supabase_session._lock:
            if not context or supabase_session.tracking_context()!=context:
                return False
            access=supabase_session.access_token()
        if not access or not allowed():
            return False
        with httpx.Client(timeout=httpx.Timeout(10,connect=5),follow_redirects=False) as client:
            response=client.post(project.rstrip('/')+'/rest/v1/rpc/ingest_activity_aggregate',
                headers={'apikey':public_key,'Authorization':'Bearer '+access},
                json={'p_kind':kind,'p_record':record,'p_revision':revision})
        if response.status_code!=200 or not allowed() or supabase_session.tracking_context()!=context:
            return False
        body=response.json()
        return (body.get('kind')==kind and body.get('session_id')==record['session_id']
                and body.get('record_key')==record['app_name_raw' if kind=='app' else 'site']
                and type(body.get('revision')) is int and body['revision']==revision)
    except (httpx.HTTPError,ValueError,TypeError,AttributeError,KeyError):
        return False
