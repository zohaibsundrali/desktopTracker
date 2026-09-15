"""Generate installer version from the application's single version constant."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app_version import VERSION
import re
if not re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', VERSION):
    raise SystemExit('Invalid app release version')
Path('build').mkdir(exist_ok=True)
Path('build/version.iss').write_text(f'#define MyAppVersion "{VERSION}"\n', encoding='utf-8')
