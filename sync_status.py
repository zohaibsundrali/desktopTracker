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


def break_status_text(status):
    """Breaks exclude tracked time; no paid/unpaid classification is inferred."""
    import math
    if not isinstance(status, dict):
        return 'Break status unavailable', 'warning'
    count, seconds = status.get('count'), status.get('duration_seconds')
    if (type(count) is not int or count < 0 or type(seconds) not in (int, float)
            or not math.isfinite(seconds) or seconds < 0 or type(status.get('paused')) is not bool):
        return 'Break status unavailable', 'warning'
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    state = 'On break' if status['paused'] else 'Breaks'
    return f'{state}: {count} · {hours:02d}:{minutes:02d}:{seconds:02d} excluded from tracked time', 'muted'


def idle_reminder_text(status):
    import math
    if not isinstance(status, dict) or status.get('available') is not True:
        return 'Idle reminder unavailable; tracked time is unchanged.', False
    if status.get('enabled') is False:
        return 'Idle reminders are disabled by admin.', False
    threshold, seconds = status.get('threshold_seconds'), status.get('idle_seconds')
    if status.get('paused') is True:
        return 'Idle reminder paused with tracking.', False
    if (status.get('enabled') is not True or type(threshold) is not int or not 60 <= threshold <= 3600
            or type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0):
        return 'Idle detection unavailable; tracked time is unchanged.', False
    if status.get('pending') is True:
        return (f'No keyboard or mouse input detected for {int(seconds)}s. Continue tracking or Pause. '
                'No time has been deducted.'), True
    return f'Idle reminder enabled after {threshold}s without input. No automatic time deduction.', False


def activity_sync_text(status):
    if status is None:
        return 'App/site sync starts with tracking', 'muted'
    if not isinstance(status, dict):
        return 'App/site sync status unavailable', 'warning'
    pending = status.get('pending')
    if type(pending) is not int or pending < 0:
        return 'App/site sync status unavailable', 'warning'
    if status.get('error'):
        return f'App/site sync needs attention ({pending} queued). Check connection and local storage.', 'warning'
    if pending:
        return f'App/site sync: {pending} snapshots saved locally, awaiting confirmation', 'warning'
    if status.get('last_success_at'):
        return 'App/site sync: latest queued snapshots confirmed', 'success'
    return 'App/site sync: waiting for first saved snapshot', 'muted'
