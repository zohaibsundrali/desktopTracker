"""Stage the frozen desktop application for Partner Center, without credentials or signing."""
import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from xml.sax.saxutils import quoteattr, escape
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app_version import VERSION

ROOT = Path(__file__).resolve().parents[1]

def package_version(version):
    if not re.fullmatch(r'[1-9]\d*\.\d+\.\d+', version):
        raise ValueError('Expected a positive major and three numeric version components')
    if any(int(p) > 65535 for p in version.split('.')):
        raise ValueError('MSIX version components must fit unsigned 16-bit integers')
    return version + '.0'

def manifest(identity, version):
    name = identity['name']
    if not re.fullmatch(r'[A-Za-z0-9.-]{3,50}', name):
        raise ValueError('Invalid package identity name')
    if not identity['publisher'].startswith('CN='):
        raise ValueError('Expected the exact Partner Center publisher distinguished name')
    return f'''<?xml version="1.0" encoding="utf-8"?>
<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
 xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
 xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
 IgnorableNamespaces="uap rescap">
 <Identity Name={quoteattr(name)} Publisher={quoteattr(identity['publisher'])} Version={quoteattr(package_version(version))} ProcessorArchitecture="x64" />
 <Properties>
  <DisplayName>{escape(identity['display_name'])}</DisplayName>
  <PublisherDisplayName>{escape(identity['publisher_display_name'])}</PublisherDisplayName>
  <Description>Work time tracking with visible capture controls.</Description>
  <Logo>Assets\\StoreLogo.png</Logo>
 </Properties>
 <Dependencies><TargetDeviceFamily Name="Windows.Desktop" MinVersion="10.0.19041.0" MaxVersionTested="10.0.20348.0" /></Dependencies>
 <Resources><Resource Language="en-us" /></Resources>
 <Applications>
  <Application Id="Verisade" Executable="DeveloperTracker.exe" EntryPoint="Windows.FullTrustApplication">
   <uap:VisualElements DisplayName={quoteattr(identity['display_name'])} Description="Work time tracking with visible capture controls."
    BackgroundColor="#4338CA" Square150x150Logo="Assets\\Square150x150Logo.png" Square44x44Logo="Assets\\Square44x44Logo.png" />
  </Application>
 </Applications>
 <Capabilities><rescap:Capability Name="runFullTrust" /></Capabilities>
</Package>
'''

def stage(source, destination, identity):
    if not (source / 'DeveloperTracker.exe').is_file():
        raise ValueError('Build the frozen Windows application first')
    if destination.exists():
        raise ValueError('Use a fresh staging directory')
    shutil.copytree(source, destination)
    (destination / 'AppxManifest.xml').write_text(manifest(identity, VERSION), encoding='utf-8')
    # This marker accompanies only the Store payload, never the classic installer.
    (destination / 'verisade-store-channel').write_text('Microsoft Store manages updates.\n', encoding='utf-8')
    from PIL import Image, ImageDraw
    assets = destination / 'Assets'
    assets.mkdir()
    # Simple source-defined V monogram; replace with approved brand assets before listing.
    for name, size in [('StoreLogo', 50), ('Square150x150Logo', 150), ('Square44x44Logo', 44)]:
        image = Image.new('RGB', (size*4, size*4), '#4338CA')
        points = [(0.20,0.23),(0.38,0.23),(0.5,0.60),(0.62,0.23),(0.80,0.23),(0.59,0.78),(0.41,0.78)]
        ImageDraw.Draw(image).polygon([(int(x*size*4),int(y*size*4)) for x,y in points], fill='white')
        image.resize((size,size), Image.Resampling.LANCZOS).save(assets / (name+'.png'))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, default=ROOT/'dist/DeveloperTracker')
    parser.add_argument('--destination', type=Path, default=ROOT/'build/msix-stage')
    args = parser.parse_args()
    stage(args.source, args.destination, json.loads((ROOT/'packaging/store/identity.json').read_text()))
