"""The Store payload cannot switch itself to the classic EXE update channel."""
from pathlib import Path
import sys


def is_store_distribution():
    return bool(getattr(sys, 'frozen', False) and
                (Path(sys.executable).parent / 'verisade-store-channel').is_file())
