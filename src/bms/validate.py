"""The validators (workstream 3, design §4.3): one small function per Playbook rule, on fields, never on text."""
from __future__ import annotations

from bms.model import Finding, Job
from bms.playbook import Playbook


def validate(job: Job, playbook: Playbook) -> list[Finding]:
    """Every rule broken by the job, in system order then device order.

    Contract:
    - Each Finding names the Playbook rule it enforces (`Finding.rule` is a key of `playbook.rules`), the system
      (`system_key`, "" for the front end or the whole job), the device or None, the severity (`must_fix` or
      `check`) and `what` / `fix` in plain words.
    - Checks fields only (verb, parties, slot and its kind in the shape, refs, counts, flags, clarifications),
      never the wording of a sentence. Examples: a packaged system with a device whose verb is "Furnish" and whose
      slot kind is "point" is must_fix; a duct heater device outside the heater system is must_fix; a device whose
      slot is not in its system's shape is must_fix; a Count whose value is lower than one of its others is
      must_fix; more than one clarification in a block is must_fix; an assumption with no reason is must_fix.
    - Pure and total: never raises on a well-formed Job; an empty list means nothing to fix.
    """
    raise NotImplementedError("workstream 3: the validators")
