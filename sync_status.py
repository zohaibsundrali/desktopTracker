"""Pure presentation of session-summary sync health; contains no credentials."""
from datetime import datetime


def session_sync_text(status):
    """Return user-facing text and semantic tone from a cached tracker snapshot."""
    if not isinstance(status, dict):
        return 'Session sync status unavailable', 'warning'
    if status.get('error'):
        return 'Session sync needs attention. Check connection and local storage.', 'warning'
    pending = status.get('pending')
    if isinstance(pending, bool) or not isinstance(pending, int) or pending < 0:
        return 'Session sync status unavailable', 'warning'
    if pending:
        text = f'Session sync: {pending} saved locally, waiting to upload'
        tone = 'warning'
    elif status.get('last_success_at'):
        try:
            stamp = datetime.fromisoformat(status['last_success_at'].replace('Z', '+00:00'))
            text = f'Last session sync: {stamp.astimezone().strftime("%H:%M:%S")}'
        except (TypeError, ValueError, AttributeError):
            text = 'Session sync: no pending session summaries'
        tone = 'success'
    else:
        text, tone = 'Session sync: waiting for first saved session', 'muted'
    if status.get('legacy_pending'):
        text += '. Older local records need recovery review.'
        tone = 'warning'
    return text, tone


def screenshot_sync_text(status):
    """Screenshot ACKs are distinct from captured images and session summaries."""
    if status is None:
        return 'Screenshot sync starts with tracking', 'muted'
    if not isinstance(status, dict):
        return 'Screenshot sync status unavailable', 'warning'
    pending = status.get('pending')
    if status.get('error'):
        suffix = f' ({pending} queued)' if isinstance(pending, int) and not isinstance(pending, bool) and pending > 0 else ''
        return f'Screenshot sync needs attention{suffix}. Check connection and local storage.', 'warning'
    if isinstance(pending, bool) or not isinstance(pending, int) or pending < 0:
        return 'Screenshot sync status unavailable', 'warning'
    if pending:
        return f'Screenshot sync: {pending} saved locally, awaiting confirmation', 'warning'
    if status.get('last_success_at'):
        try:
            stamp = datetime.fromisoformat(status['last_success_at'].replace('Z', '+00:00'))
            return f'Last screenshot sync: {stamp.astimezone().strftime("%H:%M:%S")}', 'success'
        except (TypeError, ValueError, AttributeError):
            return 'Screenshot sync: no pending captures', 'muted'
    return 'Screenshot sync: waiting for first saved capture', 'muted'


def screenshot_policy_text(status):
    if not isinstance(status, dict):
        return 'Screenshot policy is checked when tracking starts. Pause stops all tracking.', 'muted'
    policy = status.get('policy')
    if not isinstance(policy, dict) or policy.get('available') is not True:
        return 'Screenshot policy unavailable: capture and upload held. Pause stops all tracking.', 'warning'
    if policy.get('enabled') is False:
        return 'Screenshots disabled by admin. Saved captures remain queued.', 'muted'
    seconds = policy.get('interval_seconds')
    if policy.get('enabled') is not True or type(seconds) is not int or not 60 <= seconds <= 3600:
        return 'Screenshot policy unavailable: capture and upload held.', 'warning'
    state = 'Paused' if status.get('paused') else 'Tracking stopped' if not status.get('running') else 'Enabled by admin'
    return f'Screenshots: {state}; interval {seconds}s. Pause stops all tracking.', 'muted'
