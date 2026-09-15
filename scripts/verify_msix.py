"""Verify round-tripped Store identity, payload integrity and build evidence."""
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app_version import VERSION
root = Path('build/msix-inspect')
expected = json.loads(Path('packaging/store/identity.json').read_text())
ns = {'p': 'http://schemas.microsoft.com/appx/manifest/foundation/windows10'}
manifest = ET.parse(root/'AppxManifest.xml').getroot()
identity = manifest.find('p:Identity', ns)
assert identity.get('Name') == expected['name']
assert identity.get('Publisher') == expected['publisher']
assert identity.get('Version') == VERSION+'.0'
assert manifest.find('p:Properties/p:PublisherDisplayName', ns).text == expected['publisher_display_name']
assert (root/'verisade-store-channel').is_file()
for source in Path('build/msix-stage').rglob('*'):
    if source.is_file() and source.name != 'AppxManifest.xml':
        target = root/source.relative_to('build/msix-stage')
        assert target.is_file() and hashlib.sha256(source.read_bytes()).digest() == hashlib.sha256(target.read_bytes()).digest(), str(source)
configured = not Path('BUILD-NOT-CONFIGURED.txt').exists()
artifact = Path('Output/store/Verisade.msix')
digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
Path('Output/store/SHA256SUMS.txt').write_text(f'{digest}  Verisade.msix\n')
Path('Output/store/package-report.json').write_text(json.dumps({
    'identity': expected, 'version': VERSION+'.0', 'configured': configured,
    'sha256': digest, 'signed': False, 'purpose': 'partner_center_submission_candidate',
    'installed_windows_acceptance': 'pending', 'store_certification': 'pending',
    'checks': ['makeappx_validation', 'round_trip_identity', 'round_trip_payload_hashes']
}, indent=2)+'\n')
Path('Output/store/READ-ME.txt').write_text(
    'Partner Center MSIX submission candidate. Not a direct-install signed release.\n'
    'Microsoft signs accepted Store packages. Do not disable Windows protection to install this artifact.\n'
    + ('Real public backend configuration is included.\n' if configured else 'FIXTURE BUILD: do not submit to Store. Rebuild manually with repository public variables.\n')
    + 'Store review and installed-device login/capture/recovery tests remain pending.\n')
print('MSIX identity and payload verified; configured='+str(configured))
