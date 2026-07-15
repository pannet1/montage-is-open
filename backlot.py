#!/usr/bin/env python3
"""Wrapper to run OpenMontage's backlot module from the project root.

Usage:
    uv run python backlot.py open              # library — every project on disk
    uv run python backlot.py open <project>    # one project's live board
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "OpenMontage"))
from backlot.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
