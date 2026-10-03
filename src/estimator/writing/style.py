"""AME's house style as data (assets/house_style.json): the verbs a scope line starts with, the
trailing forms, the integration trio and when it applies, the note rules, what may never be
written, and a short plain-English guide for the AI.

`check_line` and `check_note` say, in plain words, why something the AI wrote breaks the house
style (None when it is fine), so the judge can drop it and list it.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[3] / "assets"
STYLE_FILE = ASSETS / "house_style.json"
TEMPLATES_FILE = ASSETS / "system_templates.json"
_TRIO_LEAD = "furnish bms communication wiring to "
_TOP = "  top level  "           # the key under which the template forms keep the lines written at the top level


def _squash(text: str) -> str:
    return " ".join((text or "").split())


def _key(text: str) -> str:
    """A line as the Master Template's lines are looked up: spaces squashed, case and a trailing stop ignored."""
    return _squash(text).casefold().rstrip(".-– ")


@dataclass(frozen=True)
class HouseStyle:
    header: str
    verbs: tuple[str, ...]
    no_verb_starts: tuple[str, ...]
    trailing_forms: tuple[str, ...]
    trio: tuple[str, str, str]
    trio_depths: tuple[int, ...]
    trio_applies_when: tuple[str, ...]
    trio_rule: str
    note_start: str
    note_rule: str
    note_examples: tuple[str, ...]
    forbidden_words: tuple[str, ...]
    category_words: tuple[str, ...]
    forbidden_patterns: tuple[str, ...]
    max_line_length: int
    guide: tuple[str, ...]
    also_accepted: tuple = ()            # openings without a verb the check accepts, beyond what the AI is told
    template_forms: dict = field(default=None, hash=False, compare=False)   # the Master Template's own lines, by _key: the form it writes them in
    long_note: int = 90                  # a "comes with the unit" note longer than this takes the short house form
    by_unit_mfr: str = "*{item} BY UNIT MFR."
    by_unit_mfr_patterns: tuple = ()
    duplicate_share: float = 0.7
    boilerplate_words: frozenset = frozenset()
    line_order: tuple = ()               # the groups, in the house order
    order_checks: tuple = ()             # (group, "text" | "device", compiled patterns), in the order they are tried
    device_ends: str = r"\s*\("
    software_points: tuple = ()
    panel_kinds: tuple = ()              # compiled: a header or kind naming a panel or a controller
    panels_stated: object = None         # compiled: "two gas detection panels"
    spec_openings: tuple = ()            # compiled: "ATC Contractor to …"
    spec_verbs: dict = field(default=None, hash=False, compare=False)   # the specification's verb -> the house verb
    verb_forms: dict = field(default=None, hash=False, compare=False)   # a verb, casefolded -> the Master Template's form
    sow_positions: tuple = ()            # the GEM's SOW order: (position, verbs, text patterns, device patterns)
    internal_words: tuple = ()           # the GEM's reasoning words: a note naming one never prints
    internal_patterns: tuple = ()        # compiled, the same ("C1" … "C6", "QC-", "GEM")
    glyphs: object = None                # compiled: the GEM's flag glyphs and other emoji, taken out
    source_id_patterns: tuple = ()       # compiled: "(S170)", "[Q7]", "S480", taken out
    contractor: tuple = ()               # (compiled, replacement): "CC" is "AME"
    doubled_label: object = None         # compiled: "*Assumed: ASSUMED: …" is "*Assumed: …"
    parties: tuple = ()                  # compiled: a note giving an item to another party
    our_parties: tuple = ()              # compiled: the controls contractor's own names, never another party
    unit_notes: tuple = ()               # compiled: an integral-thermostat or manufacturer-switch note
    software_work: tuple = ()            # compiled: a note restating the controls contractor's software work
    unit_maker: object = None            # compiled: an exclusion saying the unit's manufacturer furnishes it
    unit_devices: tuple = ()             # (name, compiled patterns): a device the unit's manufacturer furnishes
    monitoring_kinds: tuple = ()         # compiled: a monitor-only system (plumbing pumps, water heaters …)
    monitoring_block: str = "Misc Monitoring Systems"
    monitoring_max_lines: int = 4
    own_controller: object = None        # compiled: a line furnishing the system's own controller
    devices: object = None               # compiled: a header naming a device (counted per drawing, never scheduled)
    covered_items: tuple = ()            # compiled: an exclusion item the standard exclusions already cover
    packaged_units: dict = field(default_factory=dict, hash=False, compare=False)   # the packaged-unit doctrine: raw pattern lists, by key

    # -- what the client must never see (the GEM's own words)
    def internal(self, text: str) -> str | None:
        """The GEM's reasoning word, glyph or source id the text names (the client must never see it), or None."""
        low = (text or "").casefold()
        for word in self.internal_words:
            if word.casefold() in low:
                return word
        for pattern in self.internal_patterns:
            m = pattern.search(text or "")
            if m:
                return m.group(0)
        if self.glyphs is not None and self.glyphs.search(text or ""):
            return "a flag glyph"
        for pattern in self.source_id_patterns:
            m = pattern.search(text or "")
            if m:
                return m.group(0).strip()
        for pattern, _ in self.contractor:
            m = pattern.search(text or "")
            if m:
                return m.group(0)
        return None

    def client_text(self, text: str) -> str:
        """The text as the client may read it: no flag glyph, no source id, "CC" written "AME", a label written once
        ("*Assumed: ASSUMED: …" is "*Assumed: …"), a bracket naming the GEM's reasoning taken out."""
        out = text or ""
        if self.glyphs is not None:
            out = self.glyphs.sub("", out)
        for pattern in self.source_id_patterns:
            out = pattern.sub("", out)
        for pattern, replacement in self.contractor:
            out = pattern.sub(replacement, out)
        out = re.sub(r"\(\s*[,;]?\s*\)", "", out)
        out = re.sub(r"\(([^()]*)\)", lambda m: "" if self._reasoning(m.group(1)) else m.group(0), out)
        out = _squash(re.sub(r"\s+([,.;:)])", r"\1", re.sub(r"\(\s+", "(", out)))
        if self.doubled_label is not None:
            out = self.doubled_label.sub(r"\1 ", out)
        return _squash(out).rstrip(" ,;–-")

    def _reasoning(self, text: str) -> bool:
        low = text.casefold()
        return (any(w.casefold() in low for w in self.internal_words)
                or any(p.search(text) for p in self.internal_patterns))

    # -- which notes the client sees
    def names_other_party(self, text: str) -> bool:
        """The note gives an item to the owner or another party (another trade, the unit's manufacturer, others);
        the controls contractor's own names never count."""
        for pattern in self.parties:
            for m in pattern.finditer(text or ""):
                if not any(o.search(m.group(0)) for o in self.our_parties):
                    return True
        return False

    def is_unit_note(self, text: str) -> bool:
        """An integral-thermostat or manufacturer-switch note."""
        return any(p.search(text or "") for p in self.unit_notes)

    def is_software_work(self, text: str) -> bool:
        """A note restating the controls contractor's software work ("**Program …", "**Set up …")."""
        return any(p.search(_squash(text)) for p in self.software_work)

    def unit_maker_devices(self, text: str) -> list[str]:
        """The devices the unit's manufacturer furnishes that an exclusion names, in the house's words, or []."""
        if self.unit_maker is None or not self.unit_maker.search(text or ""):
            return []
        return [name for name, patterns in self.unit_devices if any(p.search(text) for p in patterns)]

    def is_monitoring(self, text: str) -> bool:
        """A monitor-only system (plumbing pumps, water heaters, glycol, gas booster, heat tracing, a generator)."""
        return any(p.search(text or "") for p in self.monitoring_kinds)

    def is_device(self, text: str) -> bool:
        """The words name a device (a sensor, a damper, a panel …), counted per drawing and never scheduled."""
        return self.devices is not None and bool(self.devices.search(text or ""))

    def covered_exclusion(self, text: str) -> bool:
        """Every item of the exclusion's list is one the proposal's standard exclusions cover (power wiring,
        disconnects, piping, ductwork …)."""
        head = re.split(r"\s*\(|,?\s+by\s+|\s+—\s+|:\s", _squash(text), maxsplit=1)[0]
        items = [i.strip(" .") for i in re.split(r",|\band\b|;|/", head) if i.strip(" .")]
        return bool(items) and all(any(p.search(i) for p in self.covered_items) for i in items)

    def sow_position(self, text: str) -> int | None:
        """The GEM's SOW position (1 to 20) of a scope line, or None when no entry of the table fits it (an interlock,
        a monitoring line): it then stays next to the line above it."""
        squashed = _squash(text)
        verb = (self.verb(squashed) or "").casefold()
        device = None
        for position, verbs, texts, devices in self.sow_positions:
            if verbs and verb not in verbs:
                continue
            if not texts and not devices:
                return position
            if any(p.search(squashed) for p in texts):
                return position
            if devices:
                device = self._device(squashed) if device is None else device
                if any(p.search(device) for p in devices):
                    return position
        return None

    @property
    def openings(self) -> tuple[str, ...]:
        """Every opening a line may have without a verb."""
        return self.no_verb_starts + self.also_accepted

    # -- the Master Template's own lines
    def template_form(self, text: str) -> str:
        """The line in the form the Master Template writes it (its capitals), when it is one of its lines,
        or the first integration line naming any equipment; else the line with its verb in the form the Master
        Template writes most ("Install and wire …")."""
        forms = self.template_forms or {}
        key = _key(text)
        if key in forms:
            return self.verb_form(forms[key])
        squashed = _squash(text)
        low = squashed.casefold()
        if low.startswith(_TRIO_LEAD) and low.endswith("factory controls"):
            middle = squashed[len(_TRIO_LEAD):len(squashed) - len("factory controls")].strip()
            return _squash(self.trio[0].replace("{what}", middle))
        return self.verb_form(text)

    def verb_form(self, text: str) -> str:
        """The line with its opening verb in the form the Master Template writes most often."""
        verb = self.verb(text)
        form = (self.verb_forms or {}).get(verb.casefold()) if verb else None
        if not form or form == verb:
            return text
        stripped = text.strip()
        return form + stripped[len(verb):]

    def house_opening(self, text: str) -> str | None:
        """Specification wording at the start of a line ("ATC Contractor to provide a relay …") in the house
        verb form ("Furnish a relay …"); None when its verb has no house form. A line without such wording is
        given back as it is."""
        squashed = _squash(text)
        for pattern in self.spec_openings:
            m = pattern.match(squashed)
            if m is None:
                continue
            rest = squashed[m.end():]
            low = rest.casefold()
            for verb in sorted(self.spec_verbs or {}, key=len, reverse=True):
                if low.startswith(verb + " "):
                    tail = rest[len(verb):].strip()
                    return _squash(f"{self.spec_verbs[verb]} {tail}")
            return None
        return text

    def is_spec_wording(self, text: str) -> bool:
        return any(p.match(_squash(text).lstrip("*").strip()) for p in self.spec_openings)

    def is_panel(self, text: str) -> bool:
        """The words name a panel or a controller ("Gas Detection System", "Fire Pump Controller")."""
        return any(p.search(text or "") for p in self.panel_kinds)

    def panels_in(self, quote: str) -> int | None:
        """The number of panels a quote states ("2 gas detection panels"), or None."""
        m = self.panels_stated.search(quote or "") if self.panels_stated is not None else None
        if m is None:
            return None
        n = m.group("n").lower()
        words = "one two three four five six seven eight nine ten".split()
        return int(n) if n.isdigit() else words.index(n) + 1

    def is_template_line(self, text: str) -> bool:
        """The line is one the Master Template writes at the top level (under the header), word for word."""
        return _key(text) in (self.template_forms or {}).get(_TOP, ())

    # -- the house order of a system's lines
    def _device(self, text: str) -> str:
        """The device a line names: after its verb or its opening, before "for", "to", a bracket or a dash."""
        text = _squash(text)
        verb = self.verb(text)
        if verb:
            text = text[len(verb):]
        else:
            low = text.lower()
            start = next((s for s in sorted(self.openings, key=len, reverse=True)
                          if low.startswith(s.lower() + " ")), "")
            text = text[len(start):]
        return re.split(self.device_ends, text.strip(), maxsplit=1, flags=re.I)[0]

    def line_group(self, text: str) -> str | None:
        """The house-order group of a scope line (controller, sensors, points, valves and dampers,
        integration), or None when no group's words are in it."""
        device = None
        wiring = self.verb(text) is None      # an interlock, a tie-in, low-voltage wiring: only integration moves it
        for group, where, patterns in self.order_checks:
            if wiring and group != "integration":
                continue
            if where == "device":
                device = self._device(text) if device is None else device
                if any(p.search(device) for p in patterns):
                    return group
            elif any(p.search(_squash(text)) for p in patterns) or (group == "integration" and self.is_trio(text)):
                return group
        return None

    def line_rank(self, text: str) -> int | None:
        group = self.line_group(text)
        return None if group is None else self.line_order.index(group)

    def is_software_point(self, text: str) -> bool:
        return any(p.search(text or "") for p in self.software_points)

    # -- checking what the AI wrote
    def verb(self, text: str) -> str | None:
        """The house verb the line starts with, as written, or None."""
        low = _squash(text).lower()
        for verb in sorted(self.verbs, key=len, reverse=True):
            if low.startswith(verb.lower() + " "):
                return text.strip()[: len(verb)]
        return None

    def is_trio(self, text: str) -> bool:
        low = _squash(text).lower().rstrip(".")
        lead = self.trio[0].split("{what}")[0].strip().lower()
        return ((low.startswith(lead + " ") and low.endswith("controls"))
                or low in (self.trio[1].lower(), self.trio[2].lower()))

    def starts_without_verb(self, text: str) -> bool:
        low = _squash(text).lower()
        return any(low.startswith(start.lower() + " ") for start in self.openings)

    def forbidden(self, text: str) -> str | None:
        """What in the text the client must never see, or None."""
        low = text.lower()
        for word in self.forbidden_words:
            if word.lower() in low:
                return f"it names “{word}”"
        for word in self.category_words:
            if re.search(rf"\b{re.escape(word)}\b", text):
                return f"it names the category word {word}"
        for pattern in self.forbidden_patterns:
            if re.search(pattern, text, re.I):
                return "it names tech hours"
        return None

    def check_line(self, text: str, depth: int = 1) -> str | None:
        """Why the scope line breaks the house style, or None when it is fine. A line under
        another line (depth 2 or more) may be a plain noun phrase — the Master Template writes
        "Damper Actuator" under its parent line — so only a top-level line needs a house verb."""
        text = _squash(text)
        if not text:
            return "it is empty"
        if len(text) > self.max_line_length:
            return f"it is longer than {self.max_line_length} characters"
        bad = self.forbidden(text)
        if bad:
            return bad
        if depth < 2 and not (self.verb(text) or self.is_trio(text) or self.starts_without_verb(text)
                              or self.is_template_line(text)):
            return "it does not start with a house verb (" + ", ".join(self.verbs) + ")"
        return None

    def by_unit_mfr_item(self, note: str) -> str | None:
        """The item a note gives to the unit (“… are coming with the unit per equipment schedule”, “… furnished
        by the fan manufacturer”), or None when it says no such thing."""
        text = _squash(note).lstrip("*").strip()
        for pattern in self.by_unit_mfr_patterns:
            m = re.search(pattern, text, re.I)
            if m and m.start() > 0:
                item = text[:m.start()].strip(" ,.-–")
                if item.count("(") != item.count(")") or re.search(r"\b(?:is|are|shall|will|be|by)\b", item, re.I):
                    return None                  # a clause ("heaters are controlled by …"), not an item
                return item or None
        return None

    def short_note(self, note: str) -> str | None:
        """The house form "*<ITEM> BY UNIT MFR." of a long note giving a device to the unit, else None."""
        item = self.by_unit_mfr_item(note)
        return self.by_unit_mfr.format(item=item.upper()) if item else None

    def note_words(self, note: str) -> frozenset[str]:
        """A note's words, for finding a duplicate: the boilerplate ("coming with the unit per equipment
        schedule") left out, plurals as singulars."""
        words = re.findall(r"[a-z0-9]+", _squash(note).casefold())
        return frozenset(w[:-1] if len(w) > 3 and w.endswith("s") else w for w in words
                         if w not in self.boilerplate_words)

    def same_note(self, a: str, b: str) -> bool:
        """Two notes that say the same thing: most of the shorter one's words are in the other."""
        wa, wb = self.note_words(a), self.note_words(b)
        if not wa or not wb:
            return _key(a) == _key(b)
        return len(wa & wb) / min(len(wa), len(wb)) >= self.duplicate_share

    def check_note(self, text: str) -> str | None:
        text = _squash(text)
        if not text.startswith(self.note_start) or not text.lstrip("*").strip():
            return f"a note must start with “{self.note_start}”"
        if len(text) > self.max_line_length:
            return f"it is longer than {self.max_line_length} characters"
        return self.forbidden(text)

    # -- for the AI's prompt
    def prompt_text(self) -> str:
        trio = "\n".join(f"  {'  ' * (d - 1)}{line}" for line, d in zip(self.trio, self.trio_depths))
        parts = ["How AME writes a system (the house style):",
                 *[f"- {line}" for line in self.guide],
                 f"- The header is \"{self.header}\"; the writer fills in the count and the tags.",
                 "- A line starts with one of these verbs: " + "; ".join(self.verbs) + ".",
                 "- Without a verb, only the openings the Master Template writes (an interlock, a tie-in, "
                 "low-voltage wiring, mapping points, monitoring …), starting: " + "; ".join(self.openings) + ".",
                 "- A line may end with one of these forms: " + "; ".join(self.trailing_forms) + ".",
                 "- The integration trio, when " + "; or ".join(self.trio_applies_when) + ":",
                 trio,
                 f"  {self.trio_rule}",
                 f"- Notes: {self.note_rule}",
                 f"- A line is at most {self.max_line_length} characters.",
                 "- Never write prices, tech hours, confidence, category words ("
                 + ", ".join(self.category_words) + ") or \"rule:\"."]
        return "\n".join(parts)


def _template_forms(trio: tuple[str, ...]) -> dict[str, str]:
    """The Master Template's lines (assets/system_templates.json), by _key, in its own form. The integration
    trio's form comes first: it is how the template writes those lines everywhere."""
    forms: dict = {_key(line): line for line in trio if "{" not in line}
    top = set()
    try:
        raw = json.loads(TEMPLATES_FILE.read_text(encoding="utf-8"))
    except OSError:
        raw = {}
    for system in raw.get("systems", ()):
        for line in system.get("lines", ()):
            text = _squash(line.get("text", ""))
            if text and "{" not in text:
                forms.setdefault(_key(text), text)
                if int(line.get("depth", 1)) < 2:
                    top.add(_key(text))
    forms[_TOP] = frozenset(top)
    return forms


def _verb_forms(verbs: tuple[str, ...]) -> dict[str, str]:
    """Each house verb, casefolded, and the form the Master Template writes it in most often ("Install and wire",
    ten lines against two)."""
    try:
        raw = json.loads(TEMPLATES_FILE.read_text(encoding="utf-8"))
    except OSError:
        return {}
    counts: dict[str, dict[str, int]] = {}
    for system in raw.get("systems", ()):
        for line in system.get("lines", ()):
            text = _squash(line.get("text", ""))
            for verb in sorted(verbs, key=len, reverse=True):
                if text.casefold().startswith(verb.casefold() + " "):
                    form = text[:len(verb)]
                    counts.setdefault(verb.casefold(), {}).setdefault(form, 0)
                    counts[verb.casefold()][form] += 1
                    break
    return {verb: max(forms, key=lambda f: (forms[f], f)) for verb, forms in counts.items()}


def _order(raw: dict) -> tuple[tuple, tuple]:
    order = raw.get("line_order") or {}
    groups = order.get("groups", {})
    checks = []
    for name in order.get("checked_in_this_order", ()):
        for where, patterns in groups.get(name, {}).items():
            checks.append((name, where, tuple(re.compile(p, re.I) for p in patterns)))
    return tuple(order.get("order", ())), tuple(checks)


def _compiled(patterns) -> tuple:
    return tuple(re.compile(p, re.I) for p in patterns or ())


def _gem_words(raw: dict) -> dict:
    """The house style's checks on what the GEM writes: what the client never sees, which notes print, the devices
    the unit's manufacturer furnishes, the monitor-only systems and the exclusions already covered."""
    internal = raw.get("internal") or {}
    notes = raw.get("clarifications") or {}
    makers = raw.get("unit_maker_devices") or {}
    monitoring = raw.get("misc_monitoring") or {}
    return dict(
        internal_words=tuple(internal.get("words", ())),
        internal_patterns=_compiled(internal.get("patterns")),
        glyphs=re.compile(internal["glyphs"]) if internal.get("glyphs") else None,
        source_id_patterns=tuple(re.compile(p) for p in internal.get("source_ids", ())),
        contractor=tuple((re.compile(p), r) for p, r in internal.get("contractor", ())),
        doubled_label=re.compile(internal["doubled_labels"]) if internal.get("doubled_labels") else None,
        parties=_compiled(notes.get("parties")),
        our_parties=_compiled(notes.get("ours")),
        unit_notes=_compiled(notes.get("unit_notes")),
        software_work=_compiled(notes.get("software_work")),
        unit_maker=re.compile(makers["maker"], re.I) if makers.get("maker") else None,
        unit_devices=tuple((d["name"], _compiled(d.get("patterns"))) for d in makers.get("devices", ())),
        monitoring_kinds=_compiled(monitoring.get("kinds")),
        monitoring_block=monitoring.get("block", "Misc Monitoring Systems"),
        monitoring_max_lines=int(monitoring.get("max_lines", 4)),
        own_controller=re.compile(monitoring["own_controller"], re.I) if monitoring.get("own_controller") else None,
        devices=re.compile(monitoring["devices"], re.I) if monitoring.get("devices") else None,
        covered_items=_compiled((raw.get("review") or {}).get("covered_items")),
    )


@lru_cache(maxsize=2)
def _load(path: Path) -> HouseStyle:
    raw = json.loads(path.read_text(encoding="utf-8"))
    trio = raw["integration_trio"]
    notes = raw["notes"]
    line_order, order_checks = _order(raw)
    return HouseStyle(
        **_gem_words(raw),
        header=raw["header"],
        verbs=tuple(raw["verbs"]),
        no_verb_starts=tuple(raw["no_verb_starts"]["starts"]),
        also_accepted=tuple(raw["no_verb_starts"].get("also_accepted", ())),
        trailing_forms=tuple(raw["trailing_forms"]),
        trio=tuple(trio["lines"]),
        trio_depths=tuple(trio["depths"]),
        trio_applies_when=tuple(trio["applies_when"]),
        trio_rule=trio["rule"],
        note_start=raw["notes"]["start"],
        note_rule=raw["notes"]["rule"],
        note_examples=tuple(raw["notes"]["examples"]),
        forbidden_words=tuple(raw["forbidden"]["words"]),
        category_words=tuple(raw["forbidden"]["category_words"]),
        forbidden_patterns=tuple(raw["forbidden"]["patterns"]),
        max_line_length=int(raw["max_line_length"]),
        guide=tuple(raw["guide"]),
        template_forms=_template_forms(tuple(trio["lines"])),
        long_note=int(notes.get("long", 90)),
        by_unit_mfr=notes.get("by_unit_mfr", "*{item} BY UNIT MFR."),
        by_unit_mfr_patterns=tuple(notes.get("by_unit_mfr_patterns", ())),
        duplicate_share=float(notes.get("duplicate_share", 0.7)),
        boilerplate_words=frozenset(notes.get("boilerplate_words", ())),
        line_order=line_order,
        order_checks=order_checks,
        device_ends=(raw.get("line_order") or {}).get("device_ends", r"\s*\("),
        software_points=tuple(re.compile(p, re.I) for p in (raw.get("software_points") or {}).get("patterns", ())),
        panel_kinds=tuple(re.compile(p, re.I) for p in (raw.get("panels") or {}).get("kinds", ())),
        panels_stated=(re.compile(raw["panels"]["stated"], re.I) if (raw.get("panels") or {}).get("stated")
                       else None),
        spec_openings=tuple(re.compile(p, re.I) for p in (raw.get("spec_openings") or {}).get("patterns", ())),
        spec_verbs={k.casefold(): v for k, v in ((raw.get("spec_openings") or {}).get("verbs") or {}).items()},
        verb_forms=_verb_forms(tuple(raw["verbs"])),
        packaged_units=dict(raw.get("packaged_units") or {}),
        sow_positions=tuple((int(e["position"]), tuple(v.casefold() for v in e.get("verbs", ())),
                             tuple(re.compile(p, re.I) for p in e.get("text", ())),
                             tuple(re.compile(p, re.I) for p in e.get("device", ())))
                            for e in (raw.get("sow_positions") or {}).get("positions", ())),
    )


def load_house_style(path: Path | str = STYLE_FILE) -> HouseStyle:
    return _load(Path(path).resolve())
