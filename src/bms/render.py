"""The renderer (workstream 4, design §4.4): the Job model to the house wording, as the inputs the OLD app's
writers take:

- `estimator.proposal.write.write_proposal(job: estimator.scope.Job, template_path: Path, out_path: Path) -> Path`
- `estimator.price_sheet.write.write_price_sheet(job: estimator.scope.Job, template_path: Path,
  book: estimator.price_sheet.price_book.PriceBook, out_path: Path) -> Path`
  (and `estimator.price_sheet.write.check_fit(job: estimator.scope.Job)` before writing).

Both take one `estimator.scope.Job` (pydantic, frozen): `header: Header`, `front_end: FrontEnd`,
`blocks: tuple[Block]` (`header: str`, `items: tuple[Item]`, `tech_hours`, `joined`, `numbered`), `add_alternates` /
`deduct_alternates: tuple[Alternate]`, `named_exceptions: tuple[str]`; an `Item` is `kind` ("line" | "note"),
`depth` 1-5, `runs: tuple[Run(text, bold)]`, `quantity` (priced when set), `tech_hours`.
"""
from __future__ import annotations

from dataclasses import dataclass

from estimator.scope import Job as ScopeJob

from bms.model import Job
from bms.playbook import Playbook


@dataclass(frozen=True)
class RenderedLine:
    """One printed line, traced back to the model (for the measurement tool and the review page)."""
    system_key: str            # "" for the front end
    device_id: str | None      # None for a header, a clarification or an integration-trio line with no device
    kind: str                  # "header" | "line" | "note"
    text: str                  # exactly as printed
    verb: str | None           # the device's verb, None when not a device line
    quantity: int | None       # the printed quantity, None when unknown or not a quantity line


@dataclass(frozen=True)
class ProposalDraft:
    """What `render` gives: `scope` is what `write_proposal` and `write_price_sheet` take, as is; `lines` is every
    printed line in print order, traced to its system and device."""
    scope: ScopeJob
    lines: tuple[RenderedLine, ...]


def render(job: Job, playbook: Playbook) -> ProposalDraft:
    """The Job in the house wording.

    Contract:
    - Pure: the same Job and Playbook give the same draft. All wording comes from `playbook.wording` and the
      system's shape (`playbook.shapes[system.shape]`): header form, line order (devices sorted by the slot's
      position in `line_order`, then their order in `System.devices`), the slot's wording form; owner brackets
      from `wording.owner_brackets[device.furnished_by]` (none for AME); "Qty (##)" forms when `Count.value` is
      None; the integration trio for an integration system; the block's one "*" clarification in its kind's form,
      as a `note` Item; a Count with `others` gets the others note.
    - `job.header` must be set (the run sets it): it becomes `scope.header` (`date` parsed from ISO).
    - Base systems become `scope.blocks`; `alternate` "add" / "deduct" systems go into `scope.add_alternates` /
      `scope.deduct_alternates`; `job.exceptions` become `scope.named_exceptions`; `job.front_end` the FrontEnd.
    - A system with no shape is rendered in the generic form "{verb} {device}{owner}{qty}" in device order.
    - Never adds a line that is not a field of the Job (nothing internal reaches the client document).
    """
    raise NotImplementedError("workstream 4: the renderer")
