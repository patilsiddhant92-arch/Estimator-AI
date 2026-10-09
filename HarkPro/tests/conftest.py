"""HarkPro tests: synthetic fixtures only (AGENTS.md rule 1). The app's src/ is put on the path read-only."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for p in (HERE.parent, HERE.parents[1] / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
