"""The house check (design 2026-10-03 §2.3): the estimator's packaged-unit doctrine and the shared-item rule,
enforced on a written scope after the ledger check. On a packaged unit a device wired inside the unit is never a
line unless the sequence names the controls contractor for it, a 'Furnish <point>' line is covered by the
integration lines, a shipped-loose device is installed and wired, and a duct heater keeps only its interlock lines.
In any block, an item another block owns is left to that block. Every refusal and change is listed in plain words."""
from __future__ import annotations

import dataclasses
import re

_SPACES = re.compile(r"\s+")


def _squash(text) -> str:
    return _SPACES.sub(" ", str(text or "")).strip()


def _patterns(style, key: str) -> list[re.Pattern]:
    raw = (getattr(style, "packaged_units", None) or {}).get(key, ())
    if isinstance(raw, str):
        raw = [raw]
    return [re.compile(p, re.I) for p in raw]


def _any(patterns, text: str) -> bool:
    return any(p.search(text) for p in patterns)


def _item_words(item: str) -> str:
    for head in ("damper actuator ", "duct heater interlock "):
        if item.startswith(head):
            return item[len(head):]
    return item


HEATER_UNKNOWN = "duct heater kept in full: the unit it serves is not known"


def house_check(scope, system, klass: str, owned_elsewhere: dict[str, str], style, heater_class: str = ""):
    """`heater_class` is the class of the unit a duct heater serves (brief.served_class): a duct heater's own block
    keeps only its interlock lines when that unit is packaged, and its full scope when the unit is field or not
    known (then a note says so). Duct heater lines inside a packaged unit's own block are interlock-only."""
    internal, loose, cc = _patterns(style, "internal"), _patterns(style, "shipped_loose"), _patterns(style, "cc_terms")
    point, exempt = _patterns(style, "point_line"), _patterns(style, "internal_exempt_quote")
    keep, heater = _patterns(style, "duct_heater_keep"), _patterns(style, "duct_heater_words")
    kept, refused, changed = [], list(scope.refused), list(getattr(scope, "changed", ()))
    key = getattr(system, "key", "")
    heater_block = _any(heater, f"{key} {getattr(system, 'kind', '')} {getattr(system, 'header', '')}")
    heater_rule = heater_class if heater_block else klass      # the served unit's class, or this unit's own
    for line in scope.lines:
        text, quote = line.text, line.quote or ""
        owner = next((o for item, o in owned_elsewhere.items()
                      if o != key and re.search(rf"(?<![A-Za-z0-9]){re.escape(_item_words(item))}(?![A-Za-z0-9])", text, re.I)), None)
        if owner:
            refused.append(f"“{text}” is written under {owner}; left out here")
            continue
        if _any(heater, text) and not _any(keep, text):
            if heater_rule == "packaged":
                refused.append(f"“{text}”: on a packaged unit AME wires the duct heater's interlock only (AME practice: "
                               "electric duct heaters); left out")
                continue
            if heater_block and not heater_class and HEATER_UNKNOWN not in changed:
                changed.append(HEATER_UNKNOWN)
        if klass == "packaged":
            hit = [p for p in internal if p.search(text)]
            if hit and not _any(exempt, quote) and not (_any(cc, quote) and any(p.search(quote) for p in hit)):
                refused.append(f"“{text}” is inside the unit and comes wired from the factory; the integration lines "
                               "cover it (AME practice: packaged units); left out")
                continue
            if _any(point, text) and not style.is_trio(text):
                refused.append(f"“{text}” is a monitored point on a packaged unit; the integration lines cover it "
                               "(AME practice); left out")
                continue
            if re.match(r"^\s*Wire\s+", text) and _any(loose, text) and re.search(r"Furnished by Unit Mfr|Shipped Loose", text, re.I):
                new = re.sub(r"^\s*Wire\s+", "Install and Wire ", text, count=1)
                changed.append(f"“{text}” → “{new}” (AME practice: shipped-loose devices are installed and wired)")
                line = dataclasses.replace(line, text=new)
        kept.append(line)
    return dataclasses.replace(scope, lines=tuple(kept), refused=tuple(refused), changed=tuple(changed))
