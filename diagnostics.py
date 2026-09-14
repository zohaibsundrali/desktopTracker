"""Offline setup report. No login, network, event hooks or screen capture."""
import importlib
import json
import os
from pathlib import Path
import platform
import tempfile

from public_config import PublicConfigError, validate_public_config

CORE_MODULES = ('customtkinter', 'supabase', 'psutil', 'PIL', 'dotenv', 'sqlite3')
WINDOWS_MODULES = ('win32gui', 'win32process', 'pynput.keyboard._win32', 'pynput.mouse._win32', 'uiautomation')


def collect_report(values=None, system=None, importer=None, data_directory=None):
    values = os.environ if values is None else values
    system = platform.system() if system is None else system
    importer = importlib.import_module if importer is None else importer
    checks = []

    def add(name, passed, detail):
        checks.append({'name': name, 'status': 'pass' if passed else 'fail', 'detail': detail})

    add('supported_platform', system == 'Windows', 'Full capture is supported on Windows 10/11.')
    try:
        validate_public_config(values)
        add('public_configuration', True, 'Public configuration is present; no credentials are included in this report.')
    except PublicConfigError as exc:
        add('public_configuration', False, str(exc))
    for module in CORE_MODULES + (WINDOWS_MODULES if system == 'Windows' else ()):
        try:
            importer(module)
            add('dependency:' + module, True, 'Import succeeded.')
        except Exception:
            # Third-party exception messages can include usernames, paths or tokens.
            add('dependency:' + module, False, 'Import failed. Reinstall the current desktop build.')
    try:
        if data_directory is None:
            from config import user_data_dir
            data_directory = user_data_dir()
        directory = Path(data_directory)
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=directory) as stream:
            stream.write(b'desktop-diagnostics')
            stream.flush()
        add('writable_user_data', True, 'Per-user data storage is writable.')
    except Exception:
        add('writable_user_data', False, 'Per-user data storage is unavailable. Check permissions and disk space.')
    return {'schema_version': 1, 'scope': 'offline_setup_only',
            'ready_for_manual_test': all(check['status'] == 'pass' for check in checks),
            'checks': checks,
            'not_tested': ['sign_in_and_device_enrollment', 'screen_and_input_capture',
                           'offline_recovery', 'hosted_permissions', 'live_dashboard_totals']}


def write_report(destination):
    report = collect_report()
    Path(destination).write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return 0 if report['ready_for_manual_test'] else 1
