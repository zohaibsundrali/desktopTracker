"""Employee-visible local session details and privacy-safe support exports."""
import json
from pathlib import Path
import os
import tempfile
from app_version import VERSION
from sync_status import (session_sync_text, screenshot_sync_text, screenshot_policy_text,
                         activity_sync_text, input_sync_text, break_status_text)


def atomic_json(destination, value):
    target = Path(destination)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=target.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def tracking_details(timer):
    """Snapshot only; no capture, network calls or credential reads."""
    lines = [f'DevTrack {VERSION}', '',
             'Tracking records time, input activity counts, app/site usage and organization-authorized screenshots.',
             'Pause stops new capture. Queued records remain bound to the original account.',
             'Input activity indicates interaction, not work quality or performance.', '']
    def add(getter, formatter):
        try:
            result = formatter(getattr(timer, getter)())
            lines.append(result[0] if isinstance(result, tuple) else result)
        except Exception:
            lines.append('Status unavailable; check the dashboard or save setup diagnostics.')
    add('get_sync_status', session_sync_text)
    add('get_screenshot_sync_status', screenshot_sync_text)
    add('get_activity_sync_status', activity_sync_text)
    add('get_break_status', break_status_text)
    add('get_input_sync_status', input_sync_text)
    return '\n\n'.join(str(line) for line in lines)
