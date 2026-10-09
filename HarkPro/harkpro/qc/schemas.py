"""The answer schemas of the two QC steps, and a schema checker.

The checker understands the keywords these schemas use (type, enum, properties, required, additionalProperties
false, items, minItems, anyOf): the same subset as the app's `bms.model.schema_errors`, so `tools/run_job.py check`
accepts these requests too. Vocabularies (verbs, parties) are the app's (`bms.model`), copied so HarkPro runs
without the app on the path.
"""
from __future__ import annotations

VERBS = ["Furnish and Install", "Furnish", "Furnish and Wire", "Install and Wire", "Wire"]
PARTIES = ["AME", "Unit Mfr.", "FA", "Mechanical Contractor", "Electrical Contractor", "Others", "Owner"]
FLAGS = ["none", "quantity", "ownership", "assumed"]
THREAD_KINDS = ["missing_line", "missing_system", "front_end", "ownership", "quantity", "template_line", "alternate",
                "unsupported_line", "left_out", "other"]
SEVERITIES = ["must_fix", "check"]
ITEM_STATUS = ["covered", "dismissed", "raised"]
VERDICTS = ["resolved", "reopen", "escalate"]
ACTIONS = ["revise", "justify", "estimator_question"]
OPS = ["add", "change", "delete", "clarify", "except"]


def _s(**kw):
    return {"type": "string", **kw}


def _obj(props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def _nullable(schema: dict) -> dict:
    return {"anyOf": [schema, {"type": "null"}]}


CITATION = _obj({"evidence_id": _s(description="E001 ..."),
                 "quote": _s(description="Words copied exactly from that evidence item's text."),
                 "where": _s()})
REF = _obj({"source_id": _s(description="The source id as the scope uses it (S41, I2 ...); '' when the evidence "
                                        "item has none."),
            "quote": _s(), "where": _s()})
COUNT = _obj({"value": _nullable({"type": "integer"}), "sources": {"type": "array", "items": REF},
              "others": {"type": "array", "items": _obj({"value": {"type": "integer"}, "ref": REF})}})
DEVICE = _obj({
    "id": _s(), "slot": _s(), "name": _s(description="The device in the template line's words."),
    "verb": _s(enum=VERBS), "furnished_by": _s(enum=PARTIES), "installed_by": _s(enum=PARTIES),
    "wired_by": _s(enum=PARTIES), "quantity": COUNT,
    "refs": {"type": "array", "items": REF, "minItems": 1},
    "assumption": _nullable(_obj({"what": _s(), "why": _s()})),
    "flag": _s(enum=FLAGS)})
PROPOSED = _obj({"line_id": _s(description="The checklist line id, '' when the line is not a template line."),
                 "text": _s(), "verb": _s(enum=VERBS), "furnished_by": _s(enum=PARTIES),
                 "installed_by": _s(enum=PARTIES), "wired_by": _s(enum=PARTIES),
                 "quantity": _nullable({"type": "integer"})})
THREAD = _obj({
    "id": _s(), "kind": _s(enum=THREAD_KINDS), "severity": _s(enum=SEVERITIES), "system_key": _s(),
    "device_id": _nullable(_s()), "evidence_ids": {"type": "array", "items": _s(), "minItems": 1},
    "question": _s(), "critique": _s(), "proposed": _nullable(PROPOSED),
    "citations": {"type": "array", "items": CITATION, "minItems": 1}})

CRITIC = _obj({
    "items": {"type": "array", "items": _obj({
        "evidence_id": _s(), "status": _s(enum=ITEM_STATUS),
        "device_ids": {"type": "array", "items": _s()}, "thread_ids": {"type": "array", "items": _s()},
        "note": _s()})},
    "threads": {"type": "array", "items": THREAD},
    "verdicts": {"type": "array", "items": _obj({
        "thread_id": _s(), "verdict": _s(enum=VERDICTS), "reason": _s(),
        "citations": {"type": "array", "items": CITATION}})}})

RESPOND = _obj({"responses": {"type": "array", "items": _obj({
    "thread_id": _s(), "action": _s(enum=ACTIONS), "text": _s(),
    "operations": {"type": "array", "items": _obj({
        "op": _s(enum=OPS), "system_key": _s(), "system_name": _nullable(_s()), "device_id": _nullable(_s()),
        "device": _nullable(DEVICE),
        "text": _nullable(_s(description="clarify: the block's one clarification (replaces it); except: the "
                                         "exception text. null for device operations."))})},
    "citations": {"type": "array", "items": CITATION}})}})

_TYPES = {"string": str, "integer": int, "number": (int, float), "object": dict, "array": list,
          "boolean": bool, "null": type(None)}


def schema_errors(value, schema: dict, path: str = "$") -> list[str]:
    if "anyOf" in schema:
        if any(not schema_errors(value, option, path) for option in schema["anyOf"]):
            return []
        return [f"{path}: fits none of the allowed forms"]
    kind = schema.get("type")
    if kind is not None:
        ok = isinstance(value, _TYPES[kind]) and not (kind in ("integer", "number") and isinstance(value, bool))
        if not ok:
            return [f"{path}: expected {kind}, got {type(value).__name__}"]
    errors: list[str] = []
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} is not one of {schema['enum']}")
    if isinstance(value, dict):
        props = schema.get("properties", {})
        errors += [f"{path}: missing {n}" for n in schema.get("required", []) if n not in value]
        if schema.get("additionalProperties") is False:
            errors += [f"{path}: unexpected {n}" for n in value if n not in props]
        for name, sub in props.items():
            if name in value:
                errors += schema_errors(value[name], sub, f"{path}.{name}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{path}: needs at least {schema['minItems']} item(s)")
        for n, item in enumerate(value):
            errors += schema_errors(item, schema.get("items", {}), f"{path}[{n}]")
    return errors
