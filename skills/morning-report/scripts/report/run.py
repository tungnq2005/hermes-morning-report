#!/usr/bin/env python3
"""CLI entrypoint for Morning Report run phases."""

from __future__ import annotations

import sys
from pathlib import Path

REPORT_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = REPORT_DIR.parent

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from report.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
