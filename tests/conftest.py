import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _raise_no_network(*args, **kwargs):
    raise urllib.error.URLError(
        "Network disabled (NO_NETWORK=1) during offline tests."
    )


def pytest_configure():
    if os.getenv("NO_NETWORK") == "1":
        urllib.request.urlopen = _raise_no_network
