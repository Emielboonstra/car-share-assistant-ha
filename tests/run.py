"""Load HA's HTTP compatibility aliases before pytest's third-party plugins."""

import sys

import homeassistant  # noqa: F401
import pytest

if __name__ == "__main__":
    raise SystemExit(pytest.main(sys.argv[1:]))
