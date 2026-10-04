"""The house check (design 2026-10-03 §2.3): the estimator's packaged-unit doctrine and the shared-item rule,
enforced on a written scope after the ledger check. On a packaged unit a device wired inside the unit is never a
line unless the sequence names the controls contractor for it, a 'Furnish <point>' line is covered by the
integration lines, a shipped-loose device is installed and wired, and a duct heater keeps only its interlock lines
unless the sequence gives the BMS the heater's control. Duct heaters are written in one place: a unit whose heaters
have their own block writes no duct heater line. In any block, an item another block owns is left to that block.
Every refusal and change is listed in plain words."""
from __future__ import annotations

import dataclasses
import re

_SPACES = re.compile(r"\s+")
_SENTENCE = re.compile(r"(?<=[.;!?])\s+|\n+")


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


_LEADING_ID = re.compile(r"^\s*\[[A-Z]{1,3}\d+\]\s*")


def heater_control_sentence(text: str, style) -> str:
    """The first sentence of `text` that gives the BMS the duct heater's control: it names the duct heater (the
    house style's duct heater words), assigns it to the BMS or the controls contractor ('heater_control_assign':
    the BMS shall provide or control it, field installed controls for it) and gives it to no one else
    ('heater_control_reject': by others, not by, by the heater or unit mfr, provided by anyone else). A leading
    source id is not part of the sentence. "" when none does."""
    heater, assign = _patterns(style, "duct_heater_words"), _patterns(style, "heater_control_assign")
    reject = _patterns(style, "heater_control_reject")
    for sentence in _SENTENCE.split(str(text or "")):
        sentence = _LEADING_ID.sub("", sentence)
        if _any(heater, sentence) and _any(assign, sentence) and not _any(reject, sentence):
            return _squash(sentence)
    return ""


def heater_item(assignment) -> str:
    """The sequence item that gives the BMS the heater's control, as the brief and the house check name it:
    '[S31] “The BMS will …”'; "" when there is none."""
    sentence, source = assignment or ("", "")
    if not sentence:
        return ""
    return f"[{source}] “{sentence}”" if source else f"“{sentence}”"


def house_check(scope, system, klass: str, owned_elsewhere: dict[str, str], style, heater_class: str = "",
                heater_home: tuple[str, str] = ("", ""), heater_assignment: tuple[str, str] = ("", "")):
    """`heater_class` is the class of the unit a duct heater serves (brief.served_class): a duct heater's own block
    keeps only its interlock lines when that unit is packaged, and its full scope when the unit is field or not
    known (then a note says so), or when `heater_assignment` (brief.heater_assignment: the sequence sentence giving
    the BMS the heater's control and its source id) is given: the explicit assignment wins and a note names it.
    `heater_home` (brief.heater_home: the heaters' tags and their block's header) names the block that writes this
    unit's duct heaters: here every duct heater line is refused. Without a heater block, duct heater lines inside a
    packaged unit's own block are interlock-only."""
    internal, loose, cc = _patterns(style, "internal"), _patterns(style, "shipped_loose"), _patterns(style, "cc_terms")
    point, exempt = _patterns(style, "point_line"), _patterns(style, "internal_exempt_quote")
    keep, heater = _patterns(style, "duct_heater_keep"), _patterns(style, "duct_heater_words")
    kept, refused, changed = [], list(scope.refused), list(getattr(scope, "changed", ()))
    key = getattr(system, "key", "")
    heater_block = _any(heater, f"{key} {getattr(system, 'kind', '')} {getattr(system, 'header', '')}")
    heater_rule = heater_class if heater_block else klass      # the served unit's class, or this unit's own
    home_tags, home_header = heater_home or ("", "")
    item = heater_item(heater_assignment)
    if heater_block and heater_rule == "packaged" and item:    # the sequence gives the BMS the heater's control
        heater_rule = "field"
        changed.append(f"duct heater kept in full: the sequence gives the BMS the heater's control ({item})")
    for line in scope.lines:
        text, quote = line.text, line.quote or ""
        if home_header and not heater_block and _any(heater, text):
            refused.append(f"“{text}”: the duct heaters serving this unit ({home_tags}) are written in the "
                           f"{home_header} block; left out here")
            continue
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
