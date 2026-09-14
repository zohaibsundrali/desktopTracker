"""Write an allowlisted .env for packaging; never copy a developer's .env."""
import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from public_config import PublicConfigError, validate_public_config


def prepare(source, destination):
    # dotenv_values does not alter the caller's environment. Disable interpolation
    # so a value such as ${SERVICE_ROLE_KEY} cannot enter the packaged file.
    from dotenv import dotenv_values
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Never let a failed validation leave a previous project's bundle available.
    destination.unlink(missing_ok=True)
    values = dict(dotenv_values(source, interpolate=False)) if Path(source).exists() else {}
    for name in ('SUPABASE_URL', 'SUPABASE_KEY', 'SCREENSHOTS_ENABLED'):
        if name in os.environ:
            values[name] = os.environ[name]
    safe = validate_public_config(values)
    destination.write_text(''.join(f'{name}={value}\n' for name, value in safe.items()), encoding='utf-8')
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', default=str(ROOT / '.env'))
    parser.add_argument('--output', default=str(ROOT / 'build/public-config/.env'))
    args = parser.parse_args()
    try:
        prepare(args.source, args.output)
        print('Public desktop configuration validated and prepared.')
    except (PublicConfigError, OSError) as exc:
        # Only controlled validation messages are suitable for a build log.
        print(str(exc) if isinstance(exc, PublicConfigError) else 'Could not prepare public desktop configuration.', file=sys.stderr)
        raise SystemExit(1)
