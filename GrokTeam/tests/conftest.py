"""GrokTeam tests import the app read-only: the tree's own src/ goes first on sys.path.

Run from the repo root:  python -m pytest GrokTeam/tests -q
Every fixture here is invented (no real job, project name, address or sheet).
"""
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
