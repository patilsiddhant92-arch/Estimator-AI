"""The planner (workstream 2): the job ledger to the Job skeleton (design §4.2, §5 row 2)."""
from __future__ import annotations

from estimator.catalogue.job import Catalogue
from estimator.ledger.facts import Ledger
from estimator.writing.dossier import Dossier

from bms.model import Job
from bms.playbook import Playbook


def plan_job(ledger: Ledger, catalogue: Catalogue, dossier: Dossier, playbook: Playbook) -> Job:
    """The Job skeleton from the completed ledger (`ledger.complete` is True).

    Contract:
    - One System per block the job calls for, each with `key` (unique), `name`, `shape` (a Playbook shape name via
      `playbook.shape_for(kind, prefixes)`, or "" when no shape applies), `control`, `families` (each with its tags
      and a Count whose `value` is the highest count any source gives, `sources` the refs giving it, `others` every
      different count with its ref; `value` None when no count is known), `sequence_refs` (the sequence passages,
      as Refs) and `alternate`.
    - `devices`, `clarifications` are empty and `tech_hours` None: `write_system` fills them.
    - Groups the practice rules keep together are one System: a VRF / split group with its indoor, condensing and
      branch-selector families; dampers linked to a fan are under that fan's system (not a system of their own);
      duct heaters in one place.
    - A system the documents name but AME does not do goes to `Job.exceptions`; open questions to `Job.questions`.
    - `Job.front_end` is set (mode from the ledger's front_end facts); `Job.header` stays None (the run sets it).
    - Every Ref's `source_id` is a ledger / dossier source id ("S41", "I2", "Q7", "F17"), its `quote` the exact
      words, its `where` the place (`ledger.sources[source_id]`, shortened by `estimator.ledger.facts.where_short`).
    - Pure: the same ledger, catalogue, dossier and Playbook give the same Job. No AI call.
    """
    raise NotImplementedError("workstream 2: the planner")
