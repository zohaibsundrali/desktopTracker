"""Describe a build without exposing project credentials or local machine data."""
import hashlib
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app_version import VERSION

installer = Path('Output/DeveloperTracker-Setup.exe')
digest = hashlib.sha256(installer.read_bytes()).hexdigest()
Path('Output/SHA256SUMS.txt').write_text(f'{digest}  {installer.name}\n', encoding='utf-8')
manifest = {'version': VERSION, 'commit': os.environ.get('GITHUB_SHA', 'local'),
            'platform': 'windows-x64', 'installer': installer.name, 'sha256': digest,
            'configured': not Path('BUILD-NOT-CONFIGURED.txt').exists(),
            'signed': os.environ.get('DESKTOP_SIGNING_VERIFIED') == 'true',
            'acceptance': 'manual_windows_test_required'}
Path('Output/release-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
if not manifest['signed']:
    Path('Output/UNSIGNED-TEST-BUILD.txt').write_text('Unsigned testing candidate. Not a signed production release.\n', encoding='utf-8')
