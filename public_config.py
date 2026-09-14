"""Validate distributable configuration without printing credential values.

This is a packaging check, not JWT verification or an authorization boundary.
The pinned Supabase 1.x SDK requires a legacy anon-role key. Modern
publishable keys require an SDK migration before they can be distributed.
"""
import base64
import json
import re
from urllib.parse import urlsplit


class PublicConfigError(ValueError):
    pass


def validate_public_config(values):
    url = str(values.get('SUPABASE_URL') or '').strip()
    key = str(values.get('SUPABASE_KEY') or '').strip()
    try:
        parsed = urlsplit(url)
        valid_url = (parsed.scheme == 'https' and bool(parsed.hostname)
                     and parsed.username is None and parsed.password is None
                     and not parsed.query and not parsed.fragment
                     and parsed.path in ('', '/') and parsed.port in (None, 443)
                     and not any(c.isspace() for c in url))
    except ValueError:
        valid_url = False
    if not valid_url:
        raise PublicConfigError('SUPABASE_URL must be an HTTPS project origin without a path or credentials.')
    if key.startswith('sb_publishable_'):
        raise PublicConfigError('This desktop SDK requires the legacy anon key. Modern publishable keys are not supported by the pinned SDK.')
    publishable = False
    anon = False
    if not publishable:
        parts = key.split('.')
        try:
            if len(parts) == 3 and all(re.fullmatch(r'[A-Za-z0-9_-]+', part) for part in parts):
                payload = json.loads(base64.urlsafe_b64decode(parts[1] + '=' * (-len(parts[1]) % 4)))
                anon = isinstance(payload, dict) and payload.get('role') == 'anon'
        except (ValueError, UnicodeError, TypeError):
            pass
    if not publishable and not anon:
        raise PublicConfigError('SUPABASE_KEY must be a legacy anon key; private and user-session keys cannot be packaged.')
    enabled = str(values.get('SCREENSHOTS_ENABLED', 'true')).strip().lower()
    if enabled not in ('true', 'false'):
        raise PublicConfigError('SCREENSHOTS_ENABLED must be true or false.')
    return {'SUPABASE_URL': url.rstrip('/'), 'SUPABASE_KEY': key, 'SCREENSHOTS_ENABLED': enabled}
