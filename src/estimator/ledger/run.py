"""The reading run (design 2026-09-29 §2): seed the ledger, then ask each pass in the estimator's order through the
judge, carrying the ledger between them. A pass with nothing to read is skipped and says so. A pass too long for one
request is cut at line ends and its parts asked and applied in turn. The run stops at the first pass with no
answer (in chat mode, the request is waiting), because every later pass reads this one's understanding."""
from __future__ import annotations

from pathlib import Path

from estimator.ledger.passes import LEDGER_PROMPT, PASSES, apply, documents, prompt, schema
from estimator.ledger.seed import seed


def read_job(judge, dossier, catalogue, save_to: Path | None = None, limit: int | None = None):
    from estimator.writing import whole_job as wj
    limit = limit or wj.SPLIT_LIMIT
    ledger = seed(dossier)
    images = list(getattr(dossier, "images", ()) or ())
    known_all = wj.known_ids(dossier.text, images)

    def save() -> None:
        if save_to is not None:
            ledger.save(save_to)

    for pass_ in PASSES:
        text = documents(pass_, dossier, catalogue)
        if not text.strip():
            ledger.understanding[pass_.name] = f"nothing to read: no {pass_.title} in this job"
            save()
            continue
        parts = wj._chunks(text, limit) if len(text) > limit else [text]
        pass_images = images if pass_.with_images else []
        refused: list[str] = []
        for n, part in enumerate(parts, start=1):
            name = f"the {pass_.title} pass" + (f" (part {n} of {len(parts)})" if len(parts) > 1 else "")
            extra = {"pass": pass_.name} | ({"part": f"{n} of {len(parts)}"} if len(parts) > 1 else {})
            got = judge.ask_pass(name, LEDGER_PROMPT, prompt(pass_, ledger, part, pass_images), schema(), pass_images, extra)
            if got is None:
                ledger.stopped_at = pass_.name
                ledger.complete = False
                ledger.refused[pass_.name] = refused
                save()
                return ledger
            known = wj.known_ids(part, pass_images) | frozenset(ledger.facts) | known_all
            refused += apply(pass_, ledger, got[0], known)
        ledger.refused[pass_.name] = refused
        save()
    ledger.complete = True
    ledger.stopped_at = ""
    save()
    return ledger
