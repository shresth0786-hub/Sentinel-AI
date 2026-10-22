"""
Sentinel AI — one-file launcher (Setup and command shortcut).

This is a thin shortcut that runs the real launcher in ``backend/execute.py``.
The implementation is kept in one place; this file only forwards to it.

    python execute.py                 # auto: Docker stack if available, else local
    python execute.py --mode docker   # full stack: app + PostgreSQL + Redis
    python execute.py --mode local    # backend + Vite dashboard
    python execute.py --stop          # stop the Docker stack
"""

from __future__ import annotations

import runpy
from pathlib import Path

_TARGET = Path(__file__).resolve().parent.parent / "backend" / "execute.py"

if __name__ == "__main__":
    runpy.run_path(str(_TARGET), run_name="__main__")
