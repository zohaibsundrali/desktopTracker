"""Explicit stable-release checks and bounded, signed installer downloads.

No Supabase credentials are used. Unsigned test builds can check releases, but
cannot download executable updates until a trusted publisher is configured.
"""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from urllib.parse import urlsplit

import httpx
from app_version import VERSION, REPOSITORY, TRUSTED_SIGNERS

API = f'https://api.github.com/repos/{REPOSITORY}/releases/latest'
MAX_INSTALLER = 300 * 1024 * 1024


class UpdateError(RuntimeError):
    pass


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r'(0|[1-9]\d{0,4})\.(0|[1-9]\d{0,4})\.(0|[1-9]\d{0,4})', value, flags=re.ASCII):
        raise UpdateError('The release version is invalid.')
    return tuple(map(int, value.split('.')))


@dataclass(frozen=True)
class Release:
    version: str
    page: str
    installer: str
    checksum: str
    size: int


def parse_release(data, current=VERSION):
    if not isinstance(data, dict) or data.get('draft') is not False or data.get('prerelease') is not False:
        raise UpdateError('A stable desktop release is not available.')
    tag = data.get('tag_name', '')
    if not isinstance(tag, str) or not tag.startswith('v'):
        raise UpdateError('The release version is invalid.')
    version = tag[1:]
    remote, local = version_tuple(version), version_tuple(current)
    if remote <= local:
        return None
    page = f'https://github.com/{REPOSITORY}/releases/tag/{tag}'
    if data.get('html_url') != page:
        raise UpdateError('The release does not belong to this application.')
    assets = data.get('assets')
    if not isinstance(assets, list):
        raise UpdateError('The release files are unavailable.')
    urls, size = {}, None
    for name in ('DeveloperTracker-Setup.exe', 'SHA256SUMS.txt'):
        matches = [a for a in assets if isinstance(a, dict) and a.get('name') == name]
        if len(matches) != 1:
            raise UpdateError('The release files are incomplete or ambiguous.')
        asset = matches[0]
        expected = f'https://github.com/{REPOSITORY}/releases/download/{tag}/{name}'
        limit = MAX_INSTALLER if name.endswith('.exe') else 16384
        if (asset.get('browser_download_url') != expected or type(asset.get('size')) is not int
                or not 0 < asset['size'] <= limit):
            raise UpdateError('The release download is invalid.')
        urls[name] = expected
        if name.endswith('.exe'):
            size = asset['size']
    return Release(version, page, urls['DeveloperTracker-Setup.exe'], urls['SHA256SUMS.txt'], size)


def _allowed_url(url):
    try:
        p = urlsplit(url)
        return (p.scheme == 'https' and p.hostname in {'api.github.com', 'github.com',
                'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}
                and p.username is None and p.password is None and p.port in (None, 443)
                and not p.fragment and not any(c.isspace() for c in url))
    except (ValueError, TypeError):
        return False


def _read(url, limit, sink=None):
    """Follow only GitHub's release hosts; enforce size and wall-clock limits."""
    start, total, chunks = time.monotonic(), 0, []
    try:
        with httpx.Client(timeout=httpx.Timeout(15, connect=5), follow_redirects=False,
                          headers={'User-Agent': 'DevTrack-Desktop/' + VERSION}) as client:
            for _ in range(5):
                if not _allowed_url(url):
                    raise UpdateError('The update host is not allowed.')
                with client.stream('GET', url) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        url = response.headers.get('location', '')
                        continue
                    if response.status_code == 404:
                        raise UpdateError('No published desktop release is available yet.')
                    if response.status_code != 200:
                        raise UpdateError('Updates are unavailable. Try again later.')
                    for chunk in response.iter_bytes():
                        total += len(chunk)
                        if total > limit or time.monotonic() - start > 180:
                            raise UpdateError('The update download exceeded its limits.')
                        if sink is None:
                            chunks.append(chunk)
                        else:
                            sink.write(chunk)
                    return b''.join(chunks) if sink is None else total
            raise UpdateError('The update download redirected too many times.')
    except httpx.HTTPError:
        raise UpdateError('Could not reach the update service. Check your connection.') from None


def check_for_update():
    from store_distribution import is_store_distribution
    if is_store_distribution():
        raise UpdateError("Microsoft Store manages this installation. Check for updates in Microsoft Store.")
    try:
        return parse_release(json.loads(_read(API, 512 * 1024)))
    except (ValueError, TypeError, UnicodeError):
        raise UpdateError('The update service returned an invalid response.') from None


def checksum_value(content):
    try:
        entries = [line.split() for line in content.decode('utf-8-sig').splitlines() if line.strip()]
    except UnicodeError:
        raise UpdateError('The installer checksum is invalid.') from None
    matches = [parts[0].lower() for parts in entries if len(parts) == 2
               and parts[1] == 'DeveloperTracker-Setup.exe' and re.fullmatch(r'[a-fA-F0-9]{64}', parts[0])]
    if len(matches) != 1:
        raise UpdateError('The installer checksum is missing or ambiguous.')
    return matches[0]


def verify_signature(path, signers=TRUSTED_SIGNERS):
    if os.name != 'nt' or not signers or any(not re.fullmatch(r'[A-Fa-f0-9]{40}', s) for s in signers):
        raise UpdateError('Verified installer updates require Windows and a configured signing publisher.')
    # File paths are passed as environment data, never interpolated as script code.
    script = "$ErrorActionPreference='Stop'; $s=Get-AuthenticodeSignature -LiteralPath $env:DEVTRACK_UPDATE_FILE; @{status=$s.Status.ToString(); thumbprint=$s.SignerCertificate.Thumbprint} | ConvertTo-Json -Compress"
    env = os.environ.copy()
    env['DEVTRACK_UPDATE_FILE'] = str(Path(path).resolve())
    powershell = str(Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe')
    try:
        result = subprocess.run([powershell, '-NoProfile', '-NonInteractive', '-Command', script],
                                env=env, capture_output=True, text=True, timeout=30,
                                creationflags=0x08000000, check=True)
        signature = json.loads(result.stdout)
        valid = signature.get('status') == 'Valid' and signature.get('thumbprint', '').upper() in {s.upper() for s in signers}
    except (OSError, subprocess.SubprocessError, ValueError, AttributeError):
        valid = False
    if not valid:
        raise UpdateError('The installer publisher could not be verified. The download was rejected.')


def download_update(release, directory, reader=_read, verifier=verify_signature):
    from store_distribution import is_store_distribution
    if is_store_distribution():
        raise UpdateError("Update this installation through Microsoft Store.")
    # This gate is deliberately not bypassed for unsigned test candidates.
    if not TRUSTED_SIGNERS:
        raise UpdateError('Signing is not configured for this test build. Obtain the test installer from your administrator.')
    if not isinstance(release, Release) or version_tuple(release.version) <= version_tuple(VERSION):
        raise UpdateError('Preview a newer stable release before downloading.')
    tag = 'v' + release.version
    prefix = f'https://github.com/{REPOSITORY}/releases/download/{tag}/'
    if release.installer != prefix + 'DeveloperTracker-Setup.exe' or release.checksum != prefix + 'SHA256SUMS.txt' or type(release.size) is not int or not 0 < release.size <= MAX_INSTALLER:
        raise UpdateError('The release download is invalid.')
    target_dir = Path(directory) / 'updates'
    target_dir.mkdir(parents=True, exist_ok=True)
    expected = checksum_value(reader(release.checksum, 16384))
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target_dir, suffix='.exe', delete=False) as stream:
            temporary = Path(stream.name)
            count = reader(release.installer, release.size, stream)
            stream.flush()
            os.fsync(stream.fileno())
        if count != release.size:
            raise UpdateError('The installer download is incomplete.')
        digest = hashlib.sha256()
        with temporary.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        if digest.hexdigest() != expected:
            raise UpdateError('The installer checksum did not match.')
        verifier(temporary)
        target = target_dir / f'DeveloperTracker-{release.version}-Setup.exe'
        os.replace(temporary, target)
        return target
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
