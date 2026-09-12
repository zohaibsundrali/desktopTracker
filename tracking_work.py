"""Fetch selectable work under a frozen login; never trust a saved UI selection."""
import uuid
import httpx
import supabase_session


class TrackingWorkError(ValueError):
    """A user-safe failure that prevents attributed tracking from starting."""


def _id(value):
    if not isinstance(value, str):
        raise TrackingWorkError('Project or task selection is invalid. Reload and try again.')
    try:
        return str(uuid.UUID(value))
    except ValueError:
        raise TrackingWorkError('Project or task selection is invalid. Reload and try again.') from None


def get_tracking_work_options(project, public_key, context):
    try:
        with supabase_session._lock:
            if not context or supabase_session.tracking_context() != context:
                raise TrackingWorkError('Your login changed. Sign in again.')
            access = supabase_session.access_token()
        if not access:
            raise TrackingWorkError('Sign in to load your projects and tasks.')
        with httpx.Client(timeout=httpx.Timeout(10, connect=5), follow_redirects=False) as client:
            response = client.post(project.rstrip('/') + '/rest/v1/rpc/get_tracking_work_options',
                headers={'apikey': public_key, 'Authorization': 'Bearer ' + access}, json={})
        if supabase_session.tracking_context() != context:
            raise TrackingWorkError('Your login changed. Reload projects and try again.')
        if response.status_code != 200:
            raise TrackingWorkError('Projects and tasks are unavailable. Check your connection and access, then reload.')
        body = response.json()
        if (not isinstance(body, dict) or body.get('organization_id') != context[1]
                or not isinstance(body.get('projects'), list) or not isinstance(body.get('tasks'), list)):
            raise TrackingWorkError('Project options could not be verified. Reload and try again.')
        projects, tasks, seen = [], [], set()
        for item in body['projects']:
            identifier = _id(item['id'])
            if identifier in seen or not isinstance(item['name'], str):
                raise ValueError('Invalid projects')
            seen.add(identifier)
            projects.append({'id': identifier, 'name': item['name']})
        task_ids = set()
        for item in body['tasks']:
            identifier, project_id = _id(item['id']), _id(item['project_id'])
            if identifier in task_ids or project_id not in seen or not isinstance(item['title'], str):
                raise ValueError('Invalid tasks')
            task_ids.add(identifier)
            tasks.append({'id': identifier, 'title': item['title'], 'project_id': project_id})
        return {'organization_id': context[1], 'projects': projects, 'tasks': tasks}
    except TrackingWorkError:
        raise
    except (httpx.HTTPError, ValueError, AttributeError, TypeError, KeyError):
        raise TrackingWorkError('Projects and tasks could not be loaded. Check your connection and reload.') from None


def validate_selection(options, project_id=None, task_id=None):
    if project_id is None:
        if task_id is not None:
            raise TrackingWorkError('Select a project before selecting a task.')
        return None, None
    project_id = _id(project_id)
    task_id = _id(task_id) if task_id is not None else None
    if not any(item['id'] == project_id for item in options['projects']):
        raise TrackingWorkError('This project is no longer available to you. Reload projects.')
    if task_id is not None and not any(item['id'] == task_id and item['project_id'] == project_id
                                       for item in options['tasks']):
        raise TrackingWorkError('This task is no longer available under the selected project. Reload tasks.')
    return project_id, task_id
