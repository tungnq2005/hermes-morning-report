#!/usr/bin/env python3
"""CLI entrypoint for Morning Report update preview."""

from __future__ import annotations

import sys
from pathlib import Path

UPDATE_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = UPDATE_DIR.parent

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from update.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
