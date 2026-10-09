"""The evidence log the critic walks: every fact of the app's Ledger.json and every row of the Evidence Package.

`load_evidence(ledger, package)` gives one `Item` per distinct piece of evidence, numbered E001.. in a stable order
(ledger facts first, then the package sheets in `PACKAGE_SHEETS` order). Rows that say a thing was *not* found are
skipped; identical texts are merged (their places are joined). The package is optional: without it (or without
openpyxl) the ledger alone is the log.

`concepts(text)` is a word scan for controls concepts. It is a hint for the critic (`scope_has` / `scope_lacks`),
never a verdict, and it is not job-specific: the vocabulary is generic controls nouns.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

# Package sheets read as evidence, in order. Scope-side sheets (Scope lines, Citations, Counts, System notes) and the
# ledger copy (Job ledger) are not evidence: they are the writer's output or a duplicate.
PACKAGE_SHEETS = ("Notes", "Schedules", "Devices on plans", "Equipment", "Equipment tags", "Spec overview", "Flags",
                  "Findings", "Sequence and points", "Bid check", "Citations")
# Sheets whose rows mix document text with the writer's own columns: only these columns are evidence. The Citations
# sheet is the writer's, but its quotes are document text (schedule notes the ledger keeps only as source ids).
PACKAGE_COLUMNS = {"Citations": ("Source id", "Sheet / section", "Document page", "Quote")}
_NOT_FOUND = re.compile(r"^\s*not found\s*$|\bnot found in\b|^nothing found|^no .* found\b", re.I)


@dataclass
class Item:
    id: str
    kind: str
    subject: str
    text: str
    where: str
    source_id: str = ""
    origin: str = ""
    concepts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ---- the concept scan ----------------------------------------------------------------------------------------

CONCEPTS: list[tuple[str, str]] = [
    ("lighting_integration", r"lutron|\bvive\b|lighting control"),
    ("integration", r"integrat\w*|\binterface\b|bacnet|modbus|tie[- ]in"),
    ("local_alarm", r"local alarm|alarm panel|audio/visual|audible|visual alarm|\bram\b|remote alarm"),
    ("leak", r"\bleak (?:detect\w*|sensor\w*)|water leak|drip pan"),
    ("float_switch", r"float|high water|overflow"),
    ("condensate_pump", r"condensate pump"),
    ("radiator_valve", r"radiator|perimeter (?:steam|heat|radiation)|finned tube|baseboard|convector"),
    ("interlock", r"interlock\w*"),
    ("occupancy", r"occupan\w* sensor|\bocc\b|occupied standby|vacancy sensor"),
    ("co2", r"\bco2\b|co₂|carbon dioxide|demand control\w* ventilation|\bdcv\b"),
    ("humidity", r"humidity|humidistat"),
    ("thermostat", r"thermostat\w*|space temp\w*|zone sensor|temperature sensor|\bstat\b"),
    ("damper_actuator", r"(?:motori[sz]ed|control|outside air|motor operated) dampers?|damper actuator\w*|actuators?"),
    ("pressure_sensor", r"(?:static|duct|differential) pressure (?:sensor|switch|transmitter)\w*|\bsp\b"),
    ("airflow_switch", r"air ?flow (?:switch|station|monitor\w*)|\bafs\b"),
    ("smoke_detector", r"smoke detector\w*|duct detector"),
    ("control_valve", r"control valves?|valve actuators?"),
    ("control_panel", r"control panel|\blcp\b|local panel"),
    ("controller", r"\bddc\b|controllers?|controller card"),
    ("transformer", r"transformer\w*|24 ?v"),
    ("status", r"\bstatus\b|current switch|current sensor"),
    ("graphics", r"graphic\w*|workstation|front end|\bbms\b"),
    ("sequence", r"sequence\w*|\bpoints?\b|economizer|setpoint"),
    ("vfd", r"\bvfd\b|variable (?:frequency|speed) drive|variable speed"),
    ("controls_party", r"\batc\b|temperature control|controls? (?:contractor|vendor)|bms (?:contractor|vendor)|"
                       r"automatic control"),
    ("other_party", r"by others|by (?:the )?(?:mc|ec|gc|owner)\b|mechanical contractor|electrical contractor|"
                    r"hvac contractor|by (?:unit )?mfr|by (?:the )?manufacturer|furnished by"),
]
_COMPILED = [(k, re.compile(p, re.I)) for k, p in CONCEPTS]
# the concepts that say who, not what: never "lacking" from a scope line
PARTY_CONCEPTS = {"controls_party", "other_party"}


def concepts(text: str) -> list[str]:
    text = str(text or "")
    return [k for k, rx in _COMPILED if rx.search(text)]


def is_controls(item: Item) -> bool:
    return bool(set(item.concepts) - {"sequence"}) or bool(item.concepts and item.kind in ("note", "provider"))


# ---- reading ---------------------------------------------------------------------------------------------------

def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


def ledger_items(ledger: dict) -> list[dict]:
    sources = ledger.get("sources") or {}
    out = []
    for fact in ledger.get("facts") or []:
        if not isinstance(fact, dict):
            continue
        sid = str(fact.get("source_id") or "")
        where = sources.get(sid, "")
        where = where.get("where", "") if isinstance(where, dict) else str(where)
        value = fact.get("value")
        quote = _norm(fact.get("quote"))
        text = f"{fact.get('subject', '')}: {value}. Quote: {quote}" if quote else f"{fact.get('subject', '')}: {value}"
        out.append({"kind": str(fact.get("kind") or "fact"), "subject": str(fact.get("subject") or ""),
                    "text": _norm(text), "where": where, "source_id": sid,
                    "origin": f"ledger {fact.get('id', '')}".strip()})
    return out


def _tables(rows: list[tuple]) -> list[tuple[list[str], list[list[str]]]]:
    """Split a sheet into tables: a header row (3+ cells) starts one; a blank row or a one-cell title row ends it."""
    tables: list[tuple[list[str], list[list[str]]]] = []
    header: list[str] | None = None
    body: list[list[str]] = []
    for raw in rows:
        cells = ["" if c is None else _norm(c) for c in raw]
        filled = [c for c in cells if c]
        if len(filled) <= 1:
            if header is not None and body:
                tables.append((header, body))
            header, body = None, []
            continue
        if header is None:
            header = cells
            continue
        body.append(cells)
    if header is not None and body:
        tables.append((header, body))
    return tables


def package_items(path: str | Path, sheets=PACKAGE_SHEETS) -> list[dict]:
    try:
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception:
        return []
    out = []
    for name in sheets:
        if name not in wb.sheetnames:
            continue
        rows = list(wb[name].iter_rows(values_only=True))
        for header, body in _tables(rows):
            for cells in body:
                pairs = [(h or f"col{i + 1}", c) for i, (h, c) in enumerate(zip(header, cells)) if c]
                if name in PACKAGE_COLUMNS:
                    pairs = [(h, c) for h, c in pairs if h in PACKAGE_COLUMNS[name]]
                if not pairs or any(_NOT_FOUND.search(c) for _, c in pairs):
                    continue
                text = " | ".join(f"{h}: {c}" for h, c in pairs)
                where_bits = [c for h, c in pairs if re.search(r"sheet|where|page|document", h, re.I)]
                sid = next((c for h, c in pairs if h.lower() == "source id"), "")
                out.append({"kind": f"package:{name}", "subject": pairs[0][1][:60], "text": text,
                            "where": "; ".join(where_bits)[:200], "source_id": sid,
                            "origin": f"Evidence Package / {name}",
                            "scan": " ".join(c for _, c in pairs)})
    return out


def load_evidence(ledger: dict, package: str | Path | None = None) -> list[Item]:
    raw = ledger_items(ledger) + (package_items(package) if package else [])
    seen: dict[str, dict] = {}
    order: list[dict] = []
    for r in raw:
        k = _key(r["text"])
        if k in seen:
            if r["where"] and r["where"] not in seen[k]["where"]:
                seen[k]["where"] = f"{seen[k]['where']}; {r['where']}".strip("; ")
            continue
        seen[k] = r
        order.append(r)
    return [Item(f"E{n:03d}", r["kind"], r["subject"], r["text"], r["where"], r["source_id"], r["origin"],
                 concepts(r.get("scan", r["text"]))) for n, r in enumerate(order, 1)]
