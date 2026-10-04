"""Held-out measurement (workstream 7, design §4.8): match the rendered lines to the estimator's final proposal.

    python tools/measure.py RENDERED_LINES.json FINAL_PROPOSAL.docx

Used on the held-out jobs only, to see whether a change helped; never to tune. Prints the share matched, missed
and extra. Runs on this machine only and writes nothing into the repo.
"""
from __future__ import annotations

import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from bms.render import RenderedLine  # noqa: E402


@dataclass(frozen=True)
class LineMatch:
    system: str                 # the system / block header as printed
    device: str                 # the device words
    verb: str | None
    quantity: int | None


@dataclass(frozen=True)
class MeasureResult:
    matched: tuple[tuple[LineMatch, LineMatch], ...]   # (rendered, final) pairs
    missed: tuple[LineMatch, ...]                      # in the final proposal, not rendered
    extra: tuple[LineMatch, ...]                       # rendered, not in the final proposal

    @property
    def share_matched(self) -> float:
        total = len(self.matched) + len(self.missed)
        return len(self.matched) / total if total else 1.0

    def summary(self) -> str:
        """One line: "matched a/b (p%), missed c, extra d"."""
        total = len(self.matched) + len(self.missed)
        return (f"matched {len(self.matched)}/{total} ({self.share_matched:.0%}), missed {len(self.missed)}, "
                f"extra {len(self.extra)}")


def measure(rendered_lines: Sequence[RenderedLine], final_proposal_path: Path) -> MeasureResult:
    """Match each device line of `rendered_lines` (`bms.render.RenderedLine`, kind "line") to a line of the final
    proposal (read with `estimator.proposal.read.read_proposal(path, template_path)` and the house proposal
    template) on system, device, verb and quantity; one final line matches at most one rendered line."""
    raise NotImplementedError("workstream 7: the measurement")


if __name__ == "__main__":
    raise SystemExit("workstream 7: the measurement command is not built yet")
