"""The writer's scope (the app's Job.json, read as a plain dict): a compact view for the critic, the concepts it
already names, and the writer's revisions applied to a copy.

Job.json is never written in place: `apply_operations` returns a new dict, and the loop saves each round's scope in
its own out folder.
"""
from __future__ import annotations

import copy
import re

from .evidence import concepts

FE = "FE"


def _qty(count) -> int | None:
    if not isinstance(count, dict):
        return None
    values = [count.get("value")] + [o.get("value") for o in count.get("others") or [] if isinstance(o, dict)]
    numbers = [v for v in values if isinstance(v, int) and not isinstance(v, bool)]
    return max(numbers) if numbers else None


def printed(device: dict) -> str:
    """The house line, in the app's plain form: "<Verb> <Name> (Furnished by X)" / "(Qty. N Total)"."""
    verb, name = device.get("verb", ""), device.get("name", "")
    text = name if re.match(r"(furnish|install|wire|tie-in|interface|interlock|map|run|ame |24v|seamlessly|demo |extend|re-commission)", name, re.I) \
        else f"{verb} {name}".strip()
    furnisher = device.get("furnished_by", "")
    if verb in ("Install and Wire", "Wire") and furnisher and furnisher != "AME" and "furnished by" not in text.lower():
        text += f" (Furnished by {furnisher})"
    return text


def blocks(job: dict) -> list[dict]:
    """Every block, the front end last as key "FE"."""
    out = list(job.get("systems") or [])
    fe = job.get("front_end") or {}
    out.append({"key": FE, "name": "Front End", "shape": "Front End", "control": "integration",
                "families": [], "devices": list(fe.get("devices") or []),
                "clarifications": list(fe.get("clarifications") or []), "alternate": "base",
                "mode": fe.get("mode"), "existing_system_name": fe.get("existing_system_name")})
    return out


def devices(job: dict) -> list[tuple[str, dict]]:
    return [(b["key"], d) for b in blocks(job) for d in b.get("devices") or []]


def view(job: dict) -> dict:
    """What the critic reads: the scope without the planner's internals."""
    systems = []
    for b in blocks(job):
        systems.append({
            "key": b.get("key"), "name": b.get("name"), "shape": b.get("shape"), "control": b.get("control"),
            "alternate": b.get("alternate", "base"),
            **({"mode": b.get("mode"), "existing_system_name": b.get("existing_system_name")} if b["key"] == FE else {}),
            "families": [{"name": f.get("name"), "tags": list(f.get("tags") or []), "count": _qty(f.get("count"))}
                         for f in b.get("families") or []],
            "no_scope_reason": b.get("no_scope_reason"),
            "devices": [{"id": d.get("id"), "line": printed(d), "verb": d.get("verb"),
                         "furnished_by": d.get("furnished_by"), "installed_by": d.get("installed_by"),
                         "wired_by": d.get("wired_by"), "quantity": _qty(d.get("quantity")),
                         "flag": d.get("flag", "none"),
                         "assumption": d.get("assumption"),
                         "cites": [{"source_id": r.get("source_id"), "quote": r.get("quote"), "where": r.get("where")}
                                   for r in d.get("refs") or []]}
                        for d in b.get("devices") or []],
            "clarifications": [c.get("text") for c in b.get("clarifications") or []],
        })
    return {"name": job.get("name"), "systems": systems,
            "exceptions": [{"system_key": e.get("system_key"), "text": e.get("text")} for e in job.get("exceptions") or []],
            "questions": list(job.get("questions") or [])}


def scope_concepts(job: dict) -> set[str]:
    """The concepts the scope's printed lines, clarifications, exceptions and questions name."""
    texts = [printed(d) for _, d in devices(job)]
    for b in blocks(job):
        texts += [c.get("text", "") for c in b.get("clarifications") or []]
    texts += [e.get("text", "") for e in job.get("exceptions") or []]
    texts += [str(q) for q in job.get("questions") or []]
    found: set[str] = set()
    for t in texts:
        found |= set(concepts(t))
    return found


# ---- revisions ---------------------------------------------------------------------------------------------------

class OperationError(ValueError):
    pass


def _block(job: dict, key: str, name: str | None, create: bool) -> dict:
    if key == FE:
        fe = job.setdefault("front_end", {"mode": "new-system", "existing_system_name": None, "devices": [],
                                          "clarifications": [], "tech_hours": None})
        fe.setdefault("devices", [])
        return fe
    for s in job.setdefault("systems", []):
        if s.get("key") == key:
            return s
    if not create:
        raise OperationError(f"no block {key!r} in the scope")
    s = {"key": key, "name": name or key, "shape": "", "control": "field", "families": [], "sequence_refs": [],
         "devices": [], "clarifications": [], "tech_hours": None, "alternate": "base", "no_scope_reason": None,
         "serves": []}
    job["systems"].append(s)
    return s


def check_operation(job: dict, op: dict) -> str | None:
    """Why `op` cannot be applied to `job`, or None."""
    try:
        apply_operations(job, [op])
    except OperationError as e:
        return str(e)
    return None


def apply_operations(job: dict, operations: list[dict]) -> dict:
    """A copy of `job` with the writer's operations applied (add / change / delete a device)."""
    job = copy.deepcopy(job)
    ids = {d.get("id") for _, d in devices(job)}
    for op in operations:
        kind, key, device_id, device = op.get("op"), op.get("system_key") or "", op.get("device_id"), op.get("device")
        if kind == "add":
            if not isinstance(device, dict):
                raise OperationError("an add needs a device")
            if device.get("id") in ids:
                raise OperationError(f"device id {device.get('id')!r} is already in the scope")
            block = _block(job, key, op.get("system_name"), create=True)
            block.setdefault("devices", []).append(device)
            if key != FE:
                block["no_scope_reason"] = None
            ids.add(device.get("id"))
        elif kind in ("change", "delete"):
            found = False
            for b in ([job.get("front_end") or {}] + list(job.get("systems") or [])):
                devs = b.get("devices") or []
                for n, d in enumerate(devs):
                    if d.get("id") == device_id:
                        found = True
                        if kind == "delete":
                            devs.pop(n)
                            ids.discard(device_id)
                        else:
                            if not isinstance(device, dict):
                                raise OperationError("a change needs the new device")
                            devs[n] = {**device, "id": device_id}
                        break
                if found:
                    break
            if not found:
                raise OperationError(f"no device {device_id!r} in the scope")
        elif kind == "clarify":
            if not op.get("text"):
                raise OperationError("a clarify needs its text")
            block = _block(job, key, op.get("system_name"), create=False)
            block["clarifications"] = [{"kind": "confirm", "text": op["text"]}]   # one per block
        elif kind == "except":
            if not op.get("text"):
                raise OperationError("an except needs its text")
            refs = list((device or {}).get("refs") or [])
            job.setdefault("exceptions", []).append({"system_key": "" if key == FE else key, "text": op["text"],
                                                     "refs": refs})
        else:
            raise OperationError(f"unknown operation {kind!r}")
    return job
