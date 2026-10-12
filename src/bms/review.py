"""The review page and the estimator's decisions (workstream 7, design §4.7).

`review_page` writes one self-contained `Review.html`; the estimator answers the open questions in a browser, which
cannot write files, so the page downloads `decisions.json` and the estimator saves it into the out folder.
`load_decisions` reads it back and `apply_decisions` (pure) applies it to the Job. Each save holds only the answers
on the page it came from, so the run keeps every saved decision in `decisions history.json` (`merge_decisions`):
a new save adds a round, its answer on a line replaces an earlier round's answer on the same line, and reading the
same file again adds nothing. Starting over means deleting both files.
`unhonored_decisions` is the post-check: a saved decision that the final job does not still show.
The coverage gate's findings (facts nothing in the job cites) are no questions: the page lists them apart, in the
group NOT_CITED_GROUP, with no button.
"""
from __future__ import annotations

import dataclasses
import hashlib
import html
import json
import os
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from bms.counts import counted_from, disputed_families
from bms.coverage import RULE as COVERAGE_RULE
from bms.model import PARTIES, VERBS, Count, Decision, Device, Family, Finding, Job, ModelError, Ref, System

REVIEW_PAGE = "Review.html"
DECISIONS_FILE = "decisions.json"
DECISIONS_HISTORY = "decisions history.json"
NOT_CITED_GROUP = "Not cited in the job"      # the heading of the group of the coverage gate's findings
MAX_QUESTIONS = 15
PROOFS_FOLDER, PROOFS_MANIFEST = "count-proofs", "proofs.json"     # as bms.counts publishes them into the out folder

RANK_MUST_FIX, RANK_FLAGGED, RANK_ASSUMPTION, RANK_CHECK = 0, 1, 2, 3
_RANK_LABELS = {RANK_MUST_FIX: "Must fix", RANK_FLAGGED: "Count flagged", RANK_ASSUMPTION: "Assumption",
                RANK_CHECK: "Check"}
_FLAG_WORDS = {
    "quantity": "The sources disagree on the count, or the count is not known.",
    "ownership": "Who furnishes, installs or wires this line is not settled.",
    "assumed": "This line rests on an assumption.",
}
_IMAGE_EXT = re.compile(r"[^\s,;()\"']+\.(?:png|jpe?g|gif|webp|bmp)", re.IGNORECASE)


# ---- the questions ----------------------------------------------------------------------------------------------


@dataclass
class _Question:
    qid: str
    system_key: str
    rank: int
    title: str
    level: str                          # "device" | "family" | "system"
    device_id: str | None = None
    family_name: str | None = None
    finding_rule: str | None = None
    notes: tuple[str, ...] = ()         # plain-words lines under the title
    count: Count | None = None          # the count shown with its others
    refs: tuple[Ref, ...] = ()
    device: Device | None = None
    order: int = 0


def proof_image(ref: Ref) -> str | None:
    """The relative image path a Ref points to, or None. The path is whatever image file name the Ref's `where`
    carries; an absolute path, a web address or one that climbs out of the out folder is never used."""
    for found in _IMAGE_EXT.findall(ref.where or ""):
        path = found.replace("\\", "/")
        if path.startswith("/") or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", path) or ".." in path.split("/"):
            continue
        return path
    return None


def count_proofs(out_dir: Path) -> dict[str, list[str]]:
    """The plan count check's proof images published into the out folder (`bms.counts.publish_proofs`):
    the count's source id ("C3") -> the images' paths relative to the out folder. {} when there are none."""
    try:
        data = json.loads((Path(out_dir) / PROOFS_FOLDER / PROOFS_MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: dict[str, list[str]] = {}
    for entry in data if isinstance(data, list) else []:
        proof = entry.get("proof") if isinstance(entry, dict) else None
        if not isinstance(proof, str) or proof_image(Ref("", "", proof)) != proof:
            continue                                    # only a relative image path inside the out folder
        for sid in entry.get("source_ids") or []:
            if isinstance(sid, str) and proof not in out.setdefault(sid, []):
                out[sid].append(proof)
    return out


def _questions(job: Job, findings: Sequence[Finding]) -> list[_Question]:
    out: list[_Question] = []
    seq = 0
    by_device: dict[tuple[str, str], _Question] = {}
    by_title: dict[tuple[str, str, str, str], _Question] = {}

    def add(**kw) -> None:
        nonlocal seq
        device_id = kw.get("device_id")
        key = (kw.get("system_key", ""), device_id) if device_id else None
        same = None if device_id else (kw.get("system_key", ""), kw.get("level", ""), kw.get("family_name") or "",
                                       squash_title(kw.get("title", "")))
        if same is not None and same in by_title:
            # T-005b (ruling 11): a card with no line of its own that asks what another card of the same block
            # already asks (two passes giving one finding, one family named twice) is one card: its notes join it
            current = by_title[same]
            current.notes = tuple(dict.fromkeys(current.notes + tuple(kw.get("notes") or ())))
            current.rank = min(current.rank, kw.get("rank", current.rank))
            if current.finding_rule is None and kw.get("finding_rule"):
                current.finding_rule = kw["finding_rule"]
            current.refs = tuple(dict.fromkeys(current.refs + tuple(kw.get("refs") or ())))
            return
        if key is not None and key in by_device:
            current = by_device[key]
            notes = tuple(note for note in kw.get("notes") or () if note not in current.notes)
            rank = kw.get("rank", current.rank)
            if kw.get("finding_rule") and current.finding_rule is not None:
                # a second finding on the line: the most severe leads the card (title and rule, the rule a saved
                # decision keeps); the other's description stays on the card as a note, once
                title = kw.get("title")
                if rank < current.rank:
                    # the new lead's own notes ("What to do") come first; the old lead's title goes just above the
                    # notes it brought, so each fix stays next to its own finding (REVIEW-019b F2)
                    old_title, current.title = current.title, title or current.title
                    current.finding_rule = kw["finding_rule"]
                    lead = tuple(kw.get("notes") or ())
                    old = tuple(n for n in current.notes if n not in lead and n != f"Finding: {current.title}")
                    head = (f"Finding: {old_title}",) if old_title and old_title != current.title else ()
                    current.notes = tuple(dict.fromkeys(lead + head + old))
                    notes = ()
                elif title and title != current.title and f"Finding: {title}" not in current.notes + notes:
                    notes = (f"Finding: {title}",) + notes
            current.notes = current.notes + notes
            current.rank = min(current.rank, rank)
            if current.finding_rule is None and kw.get("finding_rule"):
                current.finding_rule = kw["finding_rule"]
            if current.device is None and kw.get("device") is not None:
                current.device = kw["device"]
            return
        seq += 1
        question = _Question(qid=f"q{seq}", order=seq, **kw)
        out.append(question)
        if key is not None:
            by_device[key] = question
        if same is not None:
            by_title[same] = question

    scopes: list[tuple[str, Sequence[Device], Sequence]] = [(s.key, s.devices, s.families) for s in job.systems]
    if job.front_end is not None:
        scopes.append(("", job.front_end.devices, ()))
    by_key = {key: devices for key, devices, _f in scopes}

    for finding in findings:
        if finding.rule == COVERAGE_RULE:
            continue                    # the coverage gate's findings have a group of their own (`_not_cited_html`)
        device = (next((d for d in by_key.get(finding.system_key, ()) if d.id == finding.device_id), None)
                  if finding.device_id else None)
        add(system_key=finding.system_key,
            rank=RANK_MUST_FIX if finding.severity == "must_fix" else RANK_CHECK,
            title=finding.what, level="device" if device is not None else "system",
            device_id=device.id if device else None, finding_rule=finding.rule,
            notes=(f"What to do: {finding.fix}",) if finding.fix else (),
            device=device, count=device.quantity if device else None, refs=device.refs if device else ())

    for key, devices, families in scopes:
        family_cards: dict[str, _Question] = {}
        for family in families:
            count = family.count
            if count.others or count.value is None or _adds_up(count):
                why = []
                if count.others:
                    why.append("The sources give different counts; the highest prints.")
                elif count.value is None:
                    why.append("No source gives a count; it prints as Qty (##).")
                if _adds_up(count):          # ruling L1: the sheets of one floor and area count once; both numbers
                    why.append("The sheets of one floor and area are counted once, not added up: "
                               f"{count.highest()} prints, {count.added_up.value} if every sheet is added up.")
                add(system_key=key, rank=RANK_FLAGGED, title=f"How many {family.name} units?",
                    level="family", family_name=family.name, notes=tuple(why), count=count, refs=count.sources)
                family_cards.setdefault(family.name, by_title[(key, "family", family.name,
                                                               squash_title(f"How many {family.name} units?"))])
        folded: dict[str, list[str]] = {}
        for device in devices:
            home = _repeats_family_count(device, families, family_cards) if (key, device.id) not in by_device \
                else None
            if home is not None:
                # T-005b (ruling 11): the line's only question is the family's count, asked once on the family card;
                # the family's Accept or Change settles the line too (`_accept_clears`)
                folded.setdefault(home, []).append(_device_title(device))
                continue
            counted = bool(device.quantity.others)
            if device.flag != "none" or counted:
                notes = []
                if device.flag != "none":
                    notes.append(_FLAG_WORDS[device.flag])
                if counted:
                    notes.append("The sources give different counts; the highest prints.")
                if device.assumption:
                    notes.append(f"Assumed: {device.assumption.what} Why: {device.assumption.why}")
                add(system_key=key, rank=RANK_FLAGGED, title=_device_title(device), level="device",
                    device_id=device.id, notes=tuple(notes), count=device.quantity, refs=device.refs, device=device)
            elif device.assumption:
                add(system_key=key, rank=RANK_ASSUMPTION, title=_device_title(device), level="device",
                    device_id=device.id,
                    notes=(f"Assumed: {device.assumption.what}", f"Why: {device.assumption.why}"),
                    count=device.quantity, refs=device.refs, device=device)
        for name, titles in folded.items():
            card = family_cards[name]
            card.notes = card.notes + (
                f"The lines counted from it print the same count, so they are not asked again; your answer here "
                f"settles them too: {'; '.join(titles)}.",)
    return out


def squash_title(text: object) -> str:
    """A card's title as two cards compare it: spaces squashed, any case."""
    return re.sub(r"\s+", " ", str(text or "")).strip().casefold()


def _repeats_family_count(device: Device, families: Sequence[Family], cards: dict[str, _Question]) -> str | None:
    """The name of the family whose count card already asks this line's only question, else None (T-005b, ruling 11).
    The line is flagged for its count only (flag "quantity", no assumption), was counted from exactly one disputed
    family that has a card (`counts.counted_from`, the rule the family's Accept clears it by), and its count is that
    family's: the same number prints, and its other counts are among the family's."""
    if device.flag != "quantity" or device.assumption is not None or device.quantity.value is None:
        return None
    homes = [f for f in families if f.count.others and counted_from(device, f)]
    if len(homes) != 1 or homes[0].name not in cards:
        return None
    family = homes[0]
    if device.quantity.highest() != family.count.highest():
        return None
    theirs = {o.value for o in family.count.others} | {family.count.value}
    return family.name if all(o.value in theirs for o in device.quantity.others) else None


def _adds_up(count: Count) -> bool:
    """Ruling L1: the count has a sum of the sheets of one floor and area (`Count.added_up`) above the number that
    prints. The sum is no count that prints; the card and the page name both numbers."""
    up, top = count.added_up, count.highest()
    return up is not None and top is not None and up.value > top


def _device_title(device: Device) -> str:
    return f"{device.name} ({device.verb})"


def _ranked(questions: list[_Question]) -> list[_Question]:
    return sorted(questions, key=lambda q: (q.rank, q.order))


# ---- HTML -------------------------------------------------------------------------------------------------------


def _e(text: object) -> str:
    return html.escape("" if text is None else str(text), quote=True)


def _json_safe(value: object) -> str:
    return (json.dumps(value, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("&", "\\u0026").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def _ref_html(ref: Ref, label: str = "", proofs: dict[str, list[str]] | None = None) -> str:
    images = [image] if (image := proof_image(ref)) else []
    images += [p for p in (proofs or {}).get(str(ref.source_id).strip(), []) if p not in images]
    pic = "".join(f'<a class="proof" href="{_e(image)}" target="_blank"><img src="{_e(image)}" alt="proof for '
                  f'{_e(ref.source_id)}" loading="lazy" onerror="this.parentNode.style.display=\'none\'"></a>'
                  for image in images)
    return (f'<li>{_e(label)}<span class="src">{_e(ref.source_id)}</span> "{_e(ref.quote)}" '
            f'<span class="where">{_e(ref.where)}</span>{pic}</li>')


def _count_html(count: Count, proofs: dict[str, list[str]] | None = None) -> str:
    shown = "Qty (##), not known" if count.value is None else str(count.value)
    parts = [f'<div class="count"><b>Printed count: {_e(shown)}</b>'
             + (" (the highest any source gives)" if count.others else "")]
    if count.sources:
        parts.append("<ul>" + "".join(_ref_html(r, "", proofs) for r in count.sources) + "</ul>")
    if count.others:
        parts.append('<div class="others">The other counts:</div><ul>'
                     + "".join(_ref_html(o.ref, f"{o.value}: ", proofs) for o in count.others) + "</ul>")
    if _adds_up(count):
        parts.append('<div class="others">If every sheet of the same floor and area is added up:</div><ul>'
                     + _ref_html(count.added_up.ref, f"{count.added_up.value}: ", proofs) + "</ul>")
    parts.append("</div>")
    return "".join(parts)


def _not_cited_html(findings: Sequence[Finding]) -> str:
    """The group of the coverage gate's findings: each fact the reading found that nothing in the job cites, as the gate
    worded it (`Finding.what`: its id, kind and name, the place it was read at, its quote) with what to do. A list, not
    questions: it has no button and saves no decision, and it changes nothing in the proposal."""
    items = "".join(
        f'<li>{_e(f.what)} <span class="rule">Rule: {_e(f.rule)}</span>'
        + (f'<p class="note">What to do: {_e(f.fix)}</p>' if f.fix else "") + "</li>" for f in findings)
    return (f'<section class="card" id="not-cited" data-group="not-cited"><h2>{_e(NOT_CITED_GROUP)}</h2>'
            '<p class="empty">The reading found each of these in the job\'s documents. Nothing in the job cites it: no '
            'line, note, exception or question. This list changes nothing in the proposal.</p>'
            f'<ul class="uncited">{items}</ul></section>')


def _select(name: str, options: Sequence[str], current: str) -> str:
    opts = "".join(f'<option{" selected" if o == current else ""}>{_e(o)}</option>' for o in options)
    return f'<label>{name} <select data-field="{name}">{opts}</select></label>'


def _question_html(q: _Question, extra: bool, proofs: dict[str, list[str]] | None = None) -> str:
    can_delete = q.level == "device" or (q.level == "system" and q.system_key != ""
                                         and q.finding_rule != "decision not honored")
    data = {"id": q.qid, "system_key": q.system_key, "level": q.level, "device_id": q.device_id,
            "family_name": q.family_name, "finding_rule": q.finding_rule,
            "device": q.device.to_dict() if q.device else None,
            "count": q.count.to_dict() if q.count is not None and q.level != "system" else None}
    if q.level == "device" and q.device:
        data["count"] = q.device.quantity.to_dict()
    del_label = "Delete this system" if q.level == "system" else "Delete"
    hint = {"device": "Type the new count here: a whole number, alone or with one unit word (5 or 5 units), or ## for "
                      "not known. To rename the line, type the new name in the name box.",
            "family": "Type the new count: a whole number, alone or with one unit word (5 or 5 units), or ## for not "
                      "known.",
            "system": "A note for the writer; it is recorded but does not edit the job."}[q.level]
    delete = f'<button type="button" data-act="delete">{del_label}</button>' if can_delete else ""
    selects = ""
    if q.level == "device" and q.device:
        d = q.device
        selects = (f'<label class="namebox">Line name <input type="text" class="newname" data-field="name" '
                   f'value="{_e(d.name)}" aria-label="Line name"></label>'
                   '<div class="fields">' + _select("verb", VERBS, d.verb)
                   + _select("furnished_by", PARTIES, d.furnished_by)
                   + _select("installed_by", PARTIES, d.installed_by) + _select("wired_by", PARTIES, d.wired_by)
                   + "</div>")
    shown_refs = ""
    if q.refs and q.count is None:
        shown_refs = ("<details><summary>Where the job says so</summary><ul>" + "".join(_ref_html(r, "", proofs) for r in q.refs)
                      + "</ul></details>")
    return (
        f'<div class="q{" extra" if extra else ""}" id="{q.qid}" data-rank="{q.rank}">'
        f'<script type="application/json" class="qdata">{_json_safe(data)}</script>'
        f'<div class="qhead"><span class="tag r{q.rank}">{_RANK_LABELS[q.rank]}</span> '
        f'<span class="qtitle">{_e(q.title)}</span>'
        + (f' <span class="rule">Rule: {_e(q.finding_rule)}</span>' if q.finding_rule else "") + "</div>"
        + "".join(f'<p class="note">{_e(n)}</p>' for n in q.notes)
        + (_count_html(q.count, proofs) if q.count is not None else "") + shown_refs
        + '<div class="buttons"><button type="button" data-act="accept">Accept</button>'
          '<button type="button" data-act="change">Change</button>' + delete
        + '<span class="state"></span></div>'
        + f'<div class="changebox" hidden><input type="text" class="newtext" placeholder="{_e(hint)}" '
          f'aria-label="{_e(hint)}"><div class="hint">{_e(hint)}</div><p class="msg" aria-live="polite"></p>'
          f'{selects}</div></div>')


# ---- a count typed in Change -------------------------------------------------------------------------------------
# What the estimator types in the count box of Change. It is a whole number, in digits or in words, alone or with one
# unit word and a dot, nothing else ("2", "5 units", "2 ea.", "two"). Other words after the number ("4 pipe FCU",
# "2 stage", "12 total") may say what the number is of, so the number alone is not the count: the text is words. A
# number joined to more is no count either ("24V", "2nd", "2.5", "1,000", "10-12", "3/4", "2-way valve"). "##"
# ("unknown", "not known", "Qty (##)") says the count is not known. The page (`parseNumber` in `_SCRIPT_CORE`) and
# `_typed_count` read the same two patterns, so both sides read one text alike. Anything else holds no count: the
# page says so (`decisionProblem`), and the decision keeps the words.
NUMBER_WORDS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven",
                "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty")
UNIT_WORDS = ("unit", "units", "no", "nos", "ea", "each", "pc", "pcs", "piece", "pieces", "item", "items", "qty")
UNKNOWN_COUNT_PATTERN = r"^(?:##|unknown|not known|qty \(##\))$"
# the spaces as the page's JavaScript knows them (its \s and its trim()): written out, because Python's \s and strip()
# know others (U+001C to U+001F, U+0085) and not U+FEFF, so one text read two ways. T-003.
_JS_SPACE_CLASS = r"[\t\n\v\f\r \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]"
JS_SPACES = ("\t\n\v\f\r \u00a0\u1680" + "".join(chr(c) for c in range(0x2000, 0x200B))
             + "\u2028\u2029\u202f\u205f\u3000\ufeff")
# the whole text: the number (group 1), then at most one unit word, then at most one dot. At most 15 digits: the page's
# parseInt holds no more exactly (2**53), and Python's int() refuses more than 4300. T-003.
LEADING_COUNT_PATTERN = (r"^" + _JS_SPACE_CLASS + r"*([0-9]{1,15}|" + "|".join(NUMBER_WORDS) + r")"
                         r"(?:" + _JS_SPACE_CLASS + r"+(?:" + "|".join(UNIT_WORDS) + r"))?\.?"
                         + _JS_SPACE_CLASS + r"*$")
# ASCII case folding only: the page's RegExp "i" (no "u") never folds a letter above U+007F onto an ASCII one, but
# Python's re.IGNORECASE folds four ("ſ", "ı", "İ", the Kelvin sign), so "ſix" was a count here and words on the page
# (and its number word was in no list: a ValueError). T-003.
_UNKNOWN_COUNT = re.compile(UNKNOWN_COUNT_PATTERN, re.IGNORECASE | re.ASCII)
_LEADING_COUNT = re.compile(LEADING_COUNT_PATTERN, re.IGNORECASE | re.ASCII)


def _typed_count(text: str) -> tuple[str, int | None]:
    """What a count typed in Change says: ("number", n) for a whole number alone or with one unit word,
    ("number", None) for "not known", ("words", None) for any other text (a number with other words after it is
    no count), ("none", None) for no text. The page reads it the same way (`parseNumber`)."""
    said = (text or "").strip(JS_SPACES)      # the page's trim()
    if not said:
        return ("none", None)
    if _UNKNOWN_COUNT.match(said):
        return ("number", None)
    found = _LEADING_COUNT.match(said)
    if found is None:
        return ("words", None)
    word = found.group(1).lower()
    return ("number", int(word) if word.isdigit() else NUMBER_WORDS.index(word))


# The page's decision code: pure functions of a question and the estimator's answer on it, so a test runs them in
# node. A count typed with words ("2 units") sets the quantity and keeps the line's name; a new name has its own box
# on a line's card. Text with no count in it changes nothing and says so (`explainChange`, `decisionProblem`).
_SCRIPT_CORE_SOURCE = r"""
var NUMBER_WORDS = __NUMBER_WORDS__;
var UNKNOWN_COUNT = new RegExp(__UNKNOWN_COUNT__, "i");
var LEADING_COUNT = new RegExp(__LEADING_COUNT__, "i");
function parseNumber(text) {
  var t = String(text || "").trim();
  if (!t) return {kind: "none", value: ""};
  if (UNKNOWN_COUNT.test(t)) return {kind: "number", value: null};
  var found = LEADING_COUNT.exec(t);
  if (!found) return {kind: "words", value: t};
  var word = found[1].toLowerCase();
  return {kind: "number", value: /^[0-9]+$/.test(word) ? parseInt(word, 10) : NUMBER_WORDS.indexOf(word)};
}
function buildDecision(q, state) {
  if (!state || !state.action) return null;
  var d = {system_key: q.system_key, action: state.action, device_id: q.device_id || null,
           family_name: q.family_name || null, device: null, count: null, finding_rule: q.finding_rule || null,
           reason: "", was: (q.level === "device" && q.device) ? JSON.parse(JSON.stringify(q.device)) : null};
  if (state.action === "change") {
    var parsed = parseNumber(state.text);
    var f = state.fields || {};
    var name = String(f.name || "").trim();
    d.reason = String(state.text || "").trim();
    if (q.level === "device" && q.device) {
      var dev = JSON.parse(JSON.stringify(q.device));
      if (!d.reason && name && name !== dev.name) d.reason = "renamed to " + name;
      // A count typed with words ("2 units") sets the quantity and keeps the name; the name box renames the line.
      if (parsed.kind === "number") {
        dev.quantity.value = parsed.value;
        dev.quantity.others = [];
        if (dev.quantity.added_up) dev.quantity.added_up = null;      // a typed count settles the sum as well
      }
      if (name) dev.name = name;
      ["verb", "furnished_by", "installed_by", "wired_by"].forEach(function (k) { if (f[k]) dev[k] = f[k]; });
      if (parsed.kind !== "words") dev.flag = "none";      // words with no count settle nothing
      d.device = dev;
    } else if (q.level === "family" && q.count) {
      // A typed count settles the dispute (no other counts left); words with no count change nothing, and the
      // page says so (decisionProblem).
      if (parsed.kind === "number") {
        var c = JSON.parse(JSON.stringify(q.count));
        c.value = parsed.value;
        c.others = [];
        if (c.added_up) c.added_up = null;      // ... and the sum of the sheets of one floor and area
        d.count = c;
      }
    }
  }
  return d;
}
var COUNT_HELP = "a whole number, alone or with one unit word, for example 5 or 5 units, or ## for not known";
function explainChange(q, state) {
  // {ok, text}: what the answer will do, or why it cannot. Only a Change on a line or a count has a problem; a
  // note on the system is free text.
  if (!state || state.action !== "change" || q.level === "system") return {ok: true, text: ""};
  var said = String(state.text || "").trim(), parsed = parseNumber(said);
  var name = String((state.fields || {}).name || "").trim();
  var renamed = q.level === "device" && q.device && name && name !== q.device.name;
  if (parsed.kind === "words") {
    return {ok: false, text: "I cannot read a count from \"" + said + "\". Type " + COUNT_HELP + "." +
            (q.level === "device" ? " To rename the line, use the name box." : "")};
  }
  if (parsed.kind === "none") {
    if (renamed) return {ok: true, text: "The line will be renamed to " + name + ". The count stays."};
    if (q.level === "device") return {ok: true, text: ""};
    return {ok: false, text: "Type the new count: " + COUNT_HELP + "."};
  }
  var counted = parsed.value === null ? "The count will print as Qty (##), not known." :
                "The count will be " + parsed.value + ".";
  return {ok: true, text: counted + (renamed ? " The line will be renamed to " + name + "." : "")};
}
function decisionProblem(q, state) {
  var said = explainChange(q, state);
  return said.ok ? "" : said.text;
}
"""
_SCRIPT_CORE = (_SCRIPT_CORE_SOURCE.replace("__NUMBER_WORDS__", json.dumps(list(NUMBER_WORDS)))
                .replace("__UNKNOWN_COUNT__", json.dumps(UNKNOWN_COUNT_PATTERN))
                .replace("__LEADING_COUNT__", json.dumps(LEADING_COUNT_PATTERN)))

_SCRIPT_PAGE = r"""
var questions = {}, states = {};
document.querySelectorAll(".q").forEach(function (el) {
  var q = JSON.parse(el.querySelector(".qdata").textContent);
  questions[q.id] = q;
});
function refresh(id) {
  var el = document.getElementById(id), s = states[id] || {};
  el.querySelectorAll(".buttons button").forEach(function (b) {
    b.classList.toggle("on", b.getAttribute("data-act") === s.action);
  });
  el.querySelector(".changebox").hidden = s.action !== "change";
  el.querySelector(".state").textContent = s.action ? "Your answer: " + s.action : "";
  el.classList.toggle("answered", !!s.action);
  var n = Object.keys(states).filter(function (k) { return states[k] && states[k].action; }).length;
  document.getElementById("answered").textContent = n;
  explain(id);
}
function explain(id) {
  // what a Change will do, or why it cannot be read, in plain words under the box (decisionProblem)
  var el = document.getElementById(id), said = explainChange(questions[id], states[id] || {});
  var box = el.querySelector(".msg");
  box.textContent = said.text;
  box.classList.toggle("bad", !said.ok);
}
function readFields(el) {
  var f = {};
  el.querySelectorAll("[data-field]").forEach(function (s) { f[s.getAttribute("data-field")] = s.value; });
  return f;
}
document.addEventListener("click", function (ev) {
  var b = ev.target.closest("button[data-act]");
  if (!b) return;
  var el = b.closest(".q"), id = el.id, act = b.getAttribute("data-act");
  if (act === "delete" && questions[id].level === "system" &&
      !window.confirm("Delete this whole system from the proposal?")) return;
  if (states[id] && states[id].action === act) { states[id] = {}; }
  else {
    states[id] = {action: act};
    if (act === "change") {
      states[id].text = el.querySelector(".newtext").value;
      states[id].fields = readFields(el);
    }
  }
  refresh(id);
});
document.addEventListener("input", function (ev) {
  var el = ev.target.closest(".q");
  if (el && states[el.id] && states[el.id].action === "change") {
    states[el.id].text = el.querySelector(".newtext").value;
    states[el.id].fields = readFields(el);
    explain(el.id);
  }
});
document.addEventListener("change", function (ev) {
  var el = ev.target.closest(".q");
  if (el && states[el.id] && states[el.id].action === "change") {
    states[el.id].fields = readFields(el);
    explain(el.id);
  }
});
document.getElementById("showall").addEventListener("click", function () {
  var on = document.body.classList.toggle("all");
  this.textContent = on ? "Show only the top questions" : "Show all questions";
});
document.getElementById("save").addEventListener("click", function () {
  // Nothing is saved while an answer cannot be read: it stays on the page, with its message, until it is fixed.
  var unread = Object.keys(questions).filter(function (id) { return decisionProblem(questions[id], states[id]); });
  if (unread.length) {
    var saved = document.getElementById("saved");
    saved.classList.add("bad");
    saved.textContent = "Not saved: " + unread.length + " answer(s) have a Change I cannot read. Fix the red " +
      "message on each one, or press Change again to take that answer back, then save again.";
    var first = document.getElementById(unread[0]);
    if (first.offsetParent === null) {
      document.body.classList.add("all");
      document.getElementById("showall").textContent = "Show only the top questions";
    }
    first.scrollIntoView();
    return;
  }
  var out = [];
  Object.keys(questions).forEach(function (id) {
    var d = buildDecision(questions[id], states[id]);
    if (d) out.push(d);
  });
  var blob = new Blob([JSON.stringify(out, null, 2)], {type: "application/json"});
  var a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "decisions.json";
  document.body.appendChild(a);
  a.click();
  setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 500);
  document.getElementById("saved").classList.remove("bad");
  document.getElementById("saved").textContent = out.length + " decision(s) downloaded as decisions.json. " +
    "Save that file into the out folder next to this page, then run the estimate again.";
});
"""

_CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#1d2430;--mute:#5b6678;--line:#d9dee7;--acc:#1f5fbf;--bad:#b3261e;--warn:#9a5b00;--ok:#1b6b3a}
@media (prefers-color-scheme:dark){:root{--bg:#14171c;--card:#1d2229;--ink:#e7eaf0;--mute:#9aa5b8;--line:#323a47;--acc:#7aa8ff;--bad:#ff8a80;--warn:#ffc266;--ok:#7fd39b}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,Segoe UI,sans-serif}
header.top{position:sticky;top:0;background:var(--card);border-bottom:1px solid var(--line);padding:12px 16px;z-index:5}
h1{font-size:18px;margin:0 0 4px}main{max-width:900px;margin:0 auto;padding:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;margin:0 0 16px;padding:12px 16px}
.card h2{font-size:16px;margin:0 0 8px}.q{border-top:1px solid var(--line);padding:10px 0}
.q.extra{display:none}body.all .q.extra{display:block}.group.extra{display:none}body.all .group.extra{display:block}.more{display:block}body.all .more{display:none}
.group h3{font-size:15px;margin:10px 0 0}
.qtitle{font-weight:600}
.tag{display:inline-block;font-size:12px;border-radius:4px;padding:1px 6px;border:1px solid var(--line);color:var(--mute)}
.tag.r0{color:var(--bad);border-color:var(--bad)}.tag.r1{color:var(--warn);border-color:var(--warn)}
.rule,.where,.hint,.others,.empty{color:var(--mute);font-size:13px}.src{font-weight:600;margin-right:4px}
.note{margin:4px 0}.count{margin:6px 0}ul{margin:4px 0 4px 18px;padding:0}.uncited li{margin:0 0 10px}
.proof img{display:block;max-width:100%;max-height:260px;border:1px solid var(--line);margin:4px 0}
.buttons{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:6px}
button{font:inherit;padding:4px 12px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--ink);cursor:pointer}
button.on{background:var(--acc);color:#fff;border-color:var(--acc)}.q.answered{border-left:3px solid var(--ok);padding-left:8px}
.changebox{margin-top:6px}.changebox input[type=text]{width:100%;padding:5px}.fields{display:flex;gap:10px;flex-wrap:wrap;margin-top:6px}
.fields label{font-size:13px}.state{color:var(--ok);font-size:13px}#saved{color:var(--ok);margin-top:6px}#saved.bad{color:var(--bad);font-weight:600}
.msg{margin:4px 0;font-size:13px;color:var(--mute)}.msg.bad{color:var(--bad);font-weight:600}
.namebox{display:block;margin-top:6px;font-size:13px}
button.primary{background:var(--acc);color:#fff;border-color:var(--acc)}
@media (max-width:600px){main{padding:8px}.card{padding:10px}}
"""


def _names_device(text: str, device_id: str) -> bool:
    """True when `device_id` is a whole id in `text`. `AHU.d2` does not match inside `AHU.d23` or `AHU.d2.1`.
    A period that ends the sentence still matches."""
    return re.search(rf"(?<![\w.]){re.escape(device_id)}(?![\w])(?!\.\w)", text) is not None


def _fold_named_flags(questions: list[_Question]) -> list[_Question]:
    """A finding on device A that names device B of the same system, as a whole id in the title or the notes, carries
    B's flag words on A's sub-point. B's flag-only question is not its own sub-point. A question that has its own
    finding stays, and a flag whose id is only named inside a longer id stays."""
    by_id = {(q.system_key, q.device_id): q for q in questions if q.device_id}
    drop: set[int] = set()
    for question in questions:
        if question.finding_rule is None or not question.device_id:
            continue
        blob = "\n".join((question.title, *question.notes))
        for (key, device_id), other in by_id.items():
            if key != question.system_key or device_id == question.device_id:
                continue
            if other.finding_rule is not None or other.device is None or other.device.flag == "none":
                continue
            if not _names_device(blob, device_id):
                continue
            words = _FLAG_WORDS[other.device.flag]
            if words not in question.notes:
                question.notes = question.notes + (words,)
            drop.add(id(other))
    return [question for question in questions if id(question) not in drop]


@dataclass
class _Group:
    system_key: str
    name: str
    questions: list[_Question]
    rank: int
    order: int


def _review_groups(job: Job, questions: list[_Question]) -> list[_Group]:
    """One group per family. A device or system question joins that family when the system has exactly one. With more
    than one family, or with none, those questions join one group named for the system. The front end's group is
    "Front end". Rank is the lowest rank of the sub-points."""
    names = {system.key: system.name for system in job.systems}
    families = {system.key: tuple(family.name for family in system.families) for system in job.systems}
    if job.front_end is not None:
        families.setdefault("", ())
    buckets: dict[tuple[str, str], list[_Question]] = {}
    for question in questions:
        fams = families.get(question.system_key, ())
        if question.level == "family" and question.family_name:
            label = question.family_name
        elif len(fams) == 1:
            label = fams[0]
        elif question.system_key == "" and job.front_end is not None:
            label = "Front end"
        elif question.system_key == "":
            label = "Whole job"
        else:
            label = names.get(question.system_key, question.system_key)
        buckets.setdefault((question.system_key, label), []).append(question)
    groups: list[_Group] = []
    for (key, label), items in buckets.items():
        ordered = sorted(items, key=lambda q: (q.rank, q.order))
        groups.append(_Group(key, label, ordered, min(q.rank for q in ordered), min(q.order for q in ordered)))
    groups.sort(key=lambda group: (group.rank, group.order))
    return groups


def _group_html(group: _Group, extra: bool, proofs: dict[str, list[str]] | None) -> str:
    n = len(group.questions)
    point = "point" if n == 1 else "points"
    inner = "".join(_question_html(question, False, proofs) for question in group.questions)
    kind = "group extra" if extra else "group"
    return f'<section class="{kind}"><h3>{_e(f"{group.name}: {n} {point} to check")}</h3>{inner}</section>'


def review_page(job: Job, findings: Sequence[Finding], out_dir: Path) -> Path:
    """Write `out_dir/Review.html` and return its path.

    One card per system (and one for the front end and the whole job when they have questions). Inside a card, the
    questions are grouped by family. A group counts as one question toward MAX_QUESTIONS. "Show all" reveals a hidden
    group. Each old question stays one sub-point, with its own Accept, Change and Delete. Findings, flagged devices,
    counts with others, and assumptions rank must_fix first, then counts flagged, then assumptions, then checks. Each
    count shows every source and other count, and the proof image when a Ref points to a relative image path.
    "Save decisions" downloads `decisions.json` (a list of `Decision.to_dict()`), which the estimator saves into
    `out_dir`. One self-contained file.

    The coverage gate's findings (rule `bms.coverage.RULE`: a fact the reading found that nothing in the job cites)
    are no questions. They are listed in one group of their own, NOT_CITED_GROUP, after the cards: each as the gate
    worded it, with no button and no decision. They do not count among the questions and take no place among the top
    ones. With none, the page has no such group."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    questions = _fold_named_flags(_questions(job, findings))
    grouped = _review_groups(job, questions)
    uncited = [f for f in findings if f.rule == COVERAGE_RULE]
    proofs = count_proofs(out_dir)
    visible = {id(group) for group in grouped[:MAX_QUESTIONS]}

    cards: list[tuple[str, str]] = [(s.key, f"{s.name} ({s.key})") for s in job.systems]
    if job.front_end is not None:
        cards.append(("", "Front end and whole job"))
    known = {key for key, _ in cards}
    for question in questions:
        if question.system_key not in known:
            known.add(question.system_key)
            cards.append((question.system_key, "Whole job" if question.system_key == "" else question.system_key))

    body: list[str] = []
    for key, title in cards:
        mine = [group for group in grouped if group.system_key == key]
        if not mine:
            inner = '<p class="empty">Nothing to ask here.</p>'
        else:
            hidden = sum(1 for group in mine if id(group) not in visible)
            inner = "".join(_group_html(group, id(group) not in visible, proofs) for group in mine)
            if hidden:
                inner += f'<p class="empty more">{hidden} more question(s) under "Show all questions".</p>'
        body.append(f'<section class="card" data-system="{_e(key)}"><h2>{_e(title)}</h2>{inner}</section>')
    if uncited:
        body.append(_not_cited_html(uncited))
    if job.questions:
        body.append('<section class="card"><h2>Open questions for the client</h2><ul>'
                    + "".join(f"<li>{_e(t)}</li>" for t in job.questions) + "</ul></section>")

    total = len(grouped)
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Review {_e(job.name)}</title><style>{_CSS}</style></head><body>
<header class="top"><h1>Review: {_e(job.name)}</h1>
<div>{min(total, MAX_QUESTIONS)} of {total} question(s) shown, most important first.
<button type="button" id="showall">Show all questions</button>
Answered: <span id="answered">0</span>
<button type="button" id="save" class="primary">Save decisions</button></div>
<div class="hint">Your browser cannot write into the out folder. "Save decisions" downloads decisions.json;
save that file into the out folder, then run the estimate again. Decisions saved earlier are kept; a new answer on
the same line replaces the earlier one.</div><div id="saved"></div></header>
<main>{"".join(body)}</main>
<script>{_SCRIPT_CORE}{_SCRIPT_PAGE}</script></body></html>
"""
    path = out_dir / REVIEW_PAGE
    path.write_text(page, encoding="utf-8")
    return path


# ---- the decisions ----------------------------------------------------------------------------------------------


def _changes_nothing(decision: Decision) -> str | None:
    """A plain reason when the decision could change nothing (so it is a mistake, not an answer), else None. A
    change of a device carries the new `device`; a change of a family carries a `count`, or words with a count in
    them (`reason`, read as the page reads a count typed in Change, `_typed_count`: an older page saved "5 units" as
    words only, and `_apply_one` applies it); a family cannot be deleted and belongs to a system. Words with no
    count in them change nothing: the page no longer saves them (it says so, `decisionProblem`), so one here came from
    an older page or a hand edit, and the run stops in words rather than lose it."""
    if decision.family_name is not None:
        if decision.system_key == "":
            return f"the family {decision.family_name!r} belongs to a system, but system_key is empty"
        if decision.action == "delete":
            return f"a family count cannot be deleted ({decision.family_name!r}); change its count instead"
        if decision.action == "change" and decision.count is None:
            said = decision.reason.strip()
            if not said:
                return (f"a change of the {decision.family_name!r} count has no count and no words, so it changes "
                        "nothing")
            if _typed_count(said)[0] == "words":
                return (f"a change of the {decision.family_name!r} count says {said!r}, but no whole number can be "
                        "read from it, so it changes nothing. Change that count on the review page again: type a "
                        "whole number, alone or with one unit word (for example 5 or 5 units, or ## for not known), "
                        "and save decisions.json again")
    elif decision.device_id is not None and decision.action == "change" and decision.device is None:
        return f"a change of device {decision.device_id!r} has no device, so it changes nothing"
    return None


def load_decisions(out_dir: Path) -> list[Decision]:
    """The decisions in `out_dir/decisions.json` (a JSON list of Decision dicts); [] when the file is missing.
    Raises `bms.model.ModelError` naming the entry when one is malformed or could change nothing."""
    path = Path(out_dir) / DECISIONS_FILE
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ModelError(f"{DECISIONS_FILE}: not valid JSON ({error})") from None
    except OSError:
        raise ModelError(f"could not read {DECISIONS_FILE}: close it if it is open and run again") from None
    if not isinstance(data, list):
        raise ModelError(f"{DECISIONS_FILE}: expected a list of decisions, got {type(data).__name__}")
    out: list[Decision] = []
    for n, entry in enumerate(data):
        try:
            decision = Decision.from_dict(entry)
        except ModelError as error:
            raise ModelError(f"{DECISIONS_FILE}: decisions[{n}]: {error}") from None
        if (problem := _changes_nothing(decision)) is not None:
            raise ModelError(f"{DECISIONS_FILE}: decisions[{n}]: {problem}")
        out.append(decision)
    return out


@dataclass(frozen=True)
class SavedDecision:
    """One decision kept in the run's history: the save it came from (`round`, 1 for the first) and whether it took
    effect on some run (it matched a line and was applied). `saved` is the decision as decisions.json had it when
    the run rebased it onto an earlier change, gave a words-only family change its count, or read a line renamed to a
    count's words as that count (`merge_decisions`); None when `decision` is that decision.
    `settled` is a digest of the decision's system in the final job of the last run that reached the end
    (`system_digest`); None before such a run. A different digest now: the system was asked again since.
    `copies` is, for a device delete, how many lines with the deleted content the written job had when the
    decision first came in (what the estimator saw); None when not known."""
    decision: Decision
    round: int
    took_effect: bool = False
    saved: Decision | None = None
    settled: str | None = None
    copies: int | None = None

    @property
    def as_saved(self) -> Decision:
        return self.saved if self.saved is not None else self.decision

    def to_dict(self) -> dict:
        data = {"decision": self.decision.to_dict(), "round": self.round, "took_effect": self.took_effect}
        if self.saved is not None:
            data["saved"] = self.saved.to_dict()
        if self.settled is not None:
            data["settled"] = self.settled
        if self.copies is not None:
            data["copies"] = self.copies
        return data


def system_digest(job: Job, key: str) -> str:
    """A digest of system `key` of `job` (the front end for ""); "" when the job has no such system."""
    if key == "":
        part = None if job.front_end is None else job.front_end.to_dict()
    else:
        part = next((s.to_dict() for s in job.systems if s.key == key), None)
    if part is None:
        return ""
    return hashlib.sha256(json.dumps(part, sort_keys=True).encode()).hexdigest()


def load_history(out_dir: Path) -> list[SavedDecision]:
    """The decisions kept from earlier saves (`out_dir/decisions history.json`); [] when there is none. Raises
    `bms.model.ModelError` naming the file when it is malformed (it is never dropped in silence)."""
    path = Path(out_dir) / DECISIONS_HISTORY
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(data, list):
            raise ModelError(f"expected a list, got {type(data).__name__}")
        return [SavedDecision(Decision.from_dict(entry["decision"]), int(entry["round"]),
                              bool(entry.get("took_effect", False)),
                              Decision.from_dict(entry["saved"]) if entry.get("saved") is not None else None,
                              _settled(entry.get("settled")), _copies(entry.get("copies")))
                for entry in data]
    except OSError:
        raise ModelError(f"could not read {DECISIONS_HISTORY}: close it if it is open and run again") from None
    except (json.JSONDecodeError, UnicodeDecodeError, ModelError, KeyError, TypeError, ValueError) as error:
        raise ModelError(f"{DECISIONS_HISTORY}: cannot be read ({error}). This file keeps the decisions of every "
                         f"earlier save; {DECISIONS_FILE} is fine. Put back a good copy of {DECISIONS_HISTORY} if "
                         f"you have one. Otherwise delete only {DECISIONS_HISTORY}: the next run starts again from "
                         f"the decisions in {DECISIONS_FILE}, and the decisions of earlier saves are not applied "
                         "(answer them again on the review page).") from None


def _copies(value: object) -> int | None:
    if value is None or (isinstance(value, int) and not isinstance(value, bool) and value > 0):
        return value
    raise ModelError(f"copies: expected a whole number above 0, got {value!r}")


def copies_seen(history: Sequence[SavedDecision]) -> dict[Decision, int]:
    """For `apply_decisions` and `unhonored_decisions`: how many copies of its line each delete saw."""
    return {entry.decision: entry.copies for entry in history if entry.copies is not None}


def _settled(value: object) -> str | None:
    if value is None or isinstance(value, str):
        return value
    raise ModelError(f"settled: expected text, got {type(value).__name__}")


def save_history(out_dir: Path, entries: Sequence[SavedDecision]) -> Path:
    """Written whole or not at all: to a temporary file in the same folder first, then swapped into place. When the
    file cannot be written or swapped (on Windows, another program has it open), the temporary file is removed and
    `bms.model.ModelError` names the file in plain words; the old history stays as it was."""
    path = Path(out_dir) / DECISIONS_HISTORY
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps([e.to_dict() for e in entries], indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as error:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise ModelError(f"{DECISIONS_HISTORY} could not be saved in {path.parent} ({error.strerror or error}). "
                         "Another program may have it open: close that program (a viewer, an editor, a sync "
                         "client) and run again. The history is as the last run left it.") from None
    return path


def _same_line(a: Decision, b: Decision, job: Job | None = None) -> bool:
    """True when two decisions are about the same thing: a line, a family's count, or the whole system. Two device
    decisions with the line as the page showed it (`was`) are about the same line when that content is equal and
    so is the id, or when only one line of `job`'s system has that content (the writer numbers lines again, so the
    id may differ). Twin lines (the same content twice) are told apart by id. Without `was`, by id."""
    if a.system_key != b.system_key:
        return False
    if a.device_id is not None or b.device_id is not None:
        if a.device_id is None or b.device_id is None:
            return False
        if a.was is not None and b.was is not None:
            if not _same_device((a.was,), b.was):
                return False
            if a.device_id == b.device_id:
                return True
            return job is not None and _how_many(_devices(job, a.system_key), a.was) == 1
        return a.was is None and b.was is None and a.device_id == b.device_id
    if a.family_name is not None or b.family_name is not None:
        return a.family_name == b.family_name
    return True


def merge_decisions(history: Sequence[SavedDecision], saved: Sequence[Decision], *,
                    job: Job | None = None) -> list[SavedDecision]:
    """The history with this decisions.json added. The page saves only its own answers, so earlier saves are kept:
    a decision from an earlier round stays unless the new save decides the same line (the new answer wins). Every
    decision in one save is kept, in order (a change then a delete of one line are both kept). Reading the same
    file again adds nothing; no file leaves the history as it is.

    A new delete or change of a line an earlier save changed (the page showed the changed line) is rebased onto the
    line the writer wrote: change X to Y, then delete Y, is kept as delete X; change X to Y, then Y to Z, as change X
    to Z. So every kept decision names a line of the written job; a newer answer on the line a rebased decision now
    names replaces it too. `job` is the written job: a line whose content only one of its lines has is the same
    line whatever id the page showed (`_same_line`). A family change saved as words only (an older page) whose words
    hold a whole number ("5 units") is kept with that count (`_with_typed_count`). So is a line change an older page
    saved as a rename to a whole number and a unit word ("2 units"): it is kept as that count on the line, which keeps
    its own name (`_read_count_name`). Pure."""
    history = [_with_typed_count(entry, job) for entry in history]
    saved = list(saved)
    if not saved:
        return history
    latest = max((h.round for h in history), default=0)
    if history and [h.as_saved for h in history if h.round == latest] == saved:
        return history
    carried = [h for h in history if not any(_replaces(d, h, job) for d in saved)]
    new: list[SavedDecision] = []
    for d in saved:
        base = _changed_into(carried, d)
        if base is None:
            new.append(_with_typed_count(SavedDecision(d, latest + 1, copies=_seen(job, d)), job))
            continue
        carried.remove(base)
        old = base.decision
        rebased = dataclasses.replace(_read_count_name(d), device_id=old.device_id, was=old.was)
        new.append(SavedDecision(rebased, latest + 1, saved=d, copies=_seen(job, rebased)))
    return [*carried, *new]


def _with_typed_count(entry: SavedDecision, job: Job | None) -> SavedDecision:
    """`entry`, when its decision is a count an older page saved as words: a family change that carries words and no
    count (an older page saved "5 units" so) gets the count its words say, set on the family's own count, as
    `_new_count` and the page build a typed count; a line change renamed to a count's words ("2 units") gets the
    line's own name back and that count (`_read_count_name`). The decision as saved stays on record (`saved`).
    Every reader of a decision's count (the run's count rewrite too) then sees it. A family change is unchanged when
    the words hold no number, when `job` is not given or has not that family, or when the decision already has a
    count."""
    d = entry.decision
    if d.device_id is not None:
        read = _read_count_name(d)
        if read == d:
            return entry
        return dataclasses.replace(entry, decision=read, saved=d if entry.saved is None else entry.saved)
    if job is None or d.family_name is None or d.action != "change" or d.count is not None:
        return entry
    family = _family(job, d.system_key, d.family_name)
    if family is None or (count := _new_count(d, family)) is None:
        return entry
    return dataclasses.replace(entry, decision=dataclasses.replace(d, count=count),
                               saved=d if entry.saved is None else entry.saved)


# The page before the typed-count fix took any words typed in Change on a line's card as the line's new name: "2 units"
# renamed the line to "2 units". The same words went in `reason`, and the quantity stayed as the card showed it. A
# decisions.json saved so is read as the count it meant, and the line keeps its own name, when the new name is a whole
# number and one unit word and nothing else. Other words stay a rename ("2 pipe FCU"). So does a name the current page
# saved: its `reason` is the count box text or "renamed to ...", never the name itself. (`UNIT_WORDS` is above, with
# the typed count it belongs to.)
# (It reads as the count box does, `_LEADING_COUNT`: ASCII case folding, the page's spaces, at most 15 digits. Before,
# a saved name "ſix units" or one of thousands of digits raised ValueError and stopped the run. T-003.)
_COUNT_NAME = re.compile(r"^" + _JS_SPACE_CLASS + r"*([0-9]{1,15}|" + "|".join(NUMBER_WORDS) + r")" + _JS_SPACE_CLASS
                         + r"+(?:" + "|".join(UNIT_WORDS) + r")\.?" + _JS_SPACE_CLASS + r"*$", re.IGNORECASE | re.ASCII)


def _read_count_name(d: Decision, line: Device | None = None) -> Decision:
    """`d` as the count an older page saved as a rename (see above): the line with its own name and the number the
    words say as its count, with no other counts, as the page builds a typed count. The line's own name is the saved
    line's (`was`), else the name of `line`, the line `d` is applied to. `d` itself for every other decision."""
    if d.action != "change" or d.device is None or d.device_id is None:
        return d
    found = _COUNT_NAME.match(d.device.name)
    if found is None or d.reason.strip() != d.device.name.strip():
        return d
    own = d.was if d.was is not None else line
    if own is None or own.name == d.device.name:
        return d
    word = found.group(1).lower()
    count = dataclasses.replace(d.device.quantity, value=int(word) if word.isdigit() else NUMBER_WORDS.index(word),
                                others=(), added_up=None)
    return dataclasses.replace(d, device=dataclasses.replace(d.device, name=own.name, quantity=count))


def _replaces(d: Decision, h: SavedDecision, job: Job | None) -> bool:
    """True when the new decision `d` takes the place of the earlier `h` (`_same_line`). A family Accept never takes
    the place of a family count change: the page shows the family card again after the changed count is written
    (its other counts are still there), and accepting it says the count is right as it is now, the changed one."""
    if (d.action == "accept" and d.device_id is None and d.family_name is not None
            and h.decision.action == "change" and h.decision.device_id is None):
        return False
    return _same_line(h.as_saved, d, job) or _same_line(h.decision, d, job)


def _seen(job: Job | None, d: Decision) -> int | None:
    """How many lines of `job` have the content a device delete names; None when not known (no job, not a device
    delete, or no line has it: the page showed a line the written job does not have)."""
    if job is None or d.action != "delete" or d.device_id is None or d.was is None:
        return None
    return _how_many(_devices(job, d.system_key), d.was) or None


def _changed_into(history: Sequence[SavedDecision], d: Decision) -> SavedDecision | None:
    """The earlier change whose new line is the line `d` deletes or changes, if there is one."""
    if d.action not in ("delete", "change") or d.device_id is None or d.was is None:
        return None
    return next((h for h in history if h.decision.system_key == d.system_key and h.decision.action == "change"
                 and h.decision.device is not None and h.decision.device_id is not None
                 and _same_device((h.decision.device,), d.was)), None)


def _held_back(devices: tuple[Device, ...] | None, decision: Decision, seen: int | None) -> bool:
    """True for a device delete that must not be applied by content: no line has both its id and its content, some
    lines have the content, and their number is not the number the estimator saw (`seen`). When that number is
    not known (a direct call, a history from before it was kept, a line the page showed only after the revise), it
    is held back when one copy is left and no line has its id at all (the system lost a line: likely the twin);
    a line under another id that is there is taken as renumbered. Deleting one of two twins must never take the
    only copy once a later write writes the line once."""
    if decision.action != "delete" or decision.device_id is None or decision.was is None or devices is None:
        return False
    if any(dev.id == decision.device_id and _same_device((dev,), decision.was) for dev in devices):
        return False
    now = _how_many(devices, decision.was)
    if now == 0:
        return False
    if seen is not None:
        return now != seen
    return now < 2 and not any(dev.id == decision.device_id for dev in devices)


def held_back(job: Job, decision: Decision, copies: dict[Decision, int] | None = None) -> bool:
    """True when `apply_decisions` leaves the device delete `decision` unapplied on `job` (`_held_back`)."""
    return _held_back(_devices(job, decision.system_key), decision, (copies or {}).get(decision))


def _apply_to_devices(devices: tuple[Device, ...], device_id: str, decision: Decision,
                      seen: int | None = None) -> tuple[Device, ...]:
    if _held_back(devices, decision, seen):
        return devices
    target_id: str | None = device_id
    if decision.was is not None:
        exact = next((dev for dev in devices if dev.id == device_id and _same_device((dev,), decision.was)), None)
        if exact is not None:
            target_id = exact.id
        else:
            by_content = next((dev for dev in devices if _same_device((dev,), decision.was)), None)
            target_id = by_content.id if by_content is not None else None
    if target_id is None:
        return devices
    out: list[Device] = []
    for device in devices:
        if device.id != target_id:
            out.append(device)
        elif decision.action == "accept":
            out.append(dataclasses.replace(device, flag="none"))
        elif decision.action == "change":
            made = _read_count_name(decision, device).device
            out.append(dataclasses.replace(made, id=device.id) if made is not None else device)
        # delete: dropped
    return tuple(out)


def apply_decisions(job: Job, decisions: Sequence[Decision]) -> Job:
    """The job with the decisions applied, in order: accept clears the device's flag, or, for a family, the
    quantity flags of the devices counted from that family (shared sources, `counts.counted_from`) whose own count
    is known; delete removes the device (or the system, when no device or family is
    named); change replaces the device (same id) or the family's Count (a family change that carries words and no
    count sets the number the words start with: "5 units" is 5; words with no number change nothing). A line change
    an older page saved as a rename to a whole number and a unit word ("2 units", "3 nos", "4 ea") sets that count
    and keeps the line's name (`_read_count_name`). A decision naming a system or device the job no longer has is
    skipped. Pure. System key "" names the front end's devices.

    A device delete whose id no longer holds its line is applied to a line with the same content only when as many
    copies of it are left as the estimator saw (`apply_seen`, with `copies_seen` of the history; when not known, see
    `_held_back`): else it is not applied, and `unhonored_decisions` gives it a "could not be applied" card."""
    return apply_seen(job, decisions, None)


def apply_seen(job: Job, decisions: Sequence[Decision], copies: dict[Decision, int] | None) -> Job:
    """`apply_decisions` with the number of copies of its line each delete saw (`copies_seen` of the history)."""
    copies = copies or {}
    accepted = _accepted_families(decisions)
    for decision in decisions:
        job = _apply_one(job, decision, copies.get(decision), accepted)
    return job


def _accepted_families(decisions: Sequence[Decision]) -> dict[str, frozenset[str]]:
    """The family names each system's family Accepts in `decisions` name, by system key."""
    found: dict[str, set[str]] = {}
    for d in decisions:
        if d.action == "accept" and d.device_id is None and d.family_name is not None:
            found.setdefault(d.system_key, set()).add(d.family_name)
    return {key: frozenset(names) for key, names in found.items()}


def keep_deleted(decided: Job, system: System, deletes: Sequence[Decision]) -> System:
    """`system`, written again (the count rewrite), with the lines the device deletes in `deletes` took out of
    `decided` (the job the decisions were applied to) taken out again. By the saved line (`was`) only, never by id:
    the writer numbers lines again. While `system` has more lines with a deleted line's content than `decided`'s
    system has, the last of them is dropped, so a twin the estimator kept is never taken. Pure."""
    before = _devices(decided, system.key) or ()
    devices = list(system.devices)
    lines = dict.fromkeys(d.was for d in deletes if d.system_key == system.key and d.action == "delete"
                          and d.device_id is not None and d.was is not None)
    for was in lines:
        allowed = _how_many(before, was)
        while _how_many(tuple(devices), was) > allowed:
            del devices[max(n for n, dev in enumerate(devices) if _same_device((dev,), was))]
    return system if len(devices) == len(system.devices) else dataclasses.replace(system, devices=tuple(devices))


def _apply_one(job: Job, d: Decision, seen: int | None = None,
               accepted: dict[str, frozenset[str]] | None = None) -> Job:
    if d.system_key == "":
        front = job.front_end
        if front is None or d.device_id is None:
            return job
        if d.was is None and not any(x.id == d.device_id for x in front.devices):
            return job
        return dataclasses.replace(
            job, front_end=dataclasses.replace(front, devices=_apply_to_devices(front.devices, d.device_id, d,
                                                                               seen)))
    if not any(s.key == d.system_key for s in job.systems):
        return job
    system: System = job.system(d.system_key)
    if d.device_id is not None:
        if d.was is None and not any(x.id == d.device_id for x in system.devices):
            return job
        return job.with_system(dataclasses.replace(
            system, devices=_apply_to_devices(system.devices, d.device_id, d, seen)))
    if d.family_name is not None:
        if not any(f.name == d.family_name for f in system.families):
            return job
        if d.action == "accept":
            family = next(f for f in system.families if f.name == d.family_name)
            names = (accepted or {}).get(d.system_key, frozenset()) | {d.family_name}
            devices = tuple(dataclasses.replace(dev, flag="none") if _accept_clears(dev, family, system, names)
                            else dev for dev in system.devices)
            return job.with_system(dataclasses.replace(system, devices=devices))
        if d.action != "change":
            return job
        families = tuple(_with_new_count(f, d) for f in system.families)
        if families == system.families:
            return job
        return job.with_system(dataclasses.replace(system, families=families))
    if d.action == "delete":
        return dataclasses.replace(job, systems=tuple(s for s in job.systems if s.key != d.system_key))
    return job


def _new_count(d: Decision, family: Family) -> Count | None:
    """The count a family change gives `family`: the decision's own `count`; else, for a change that carries words
    only (an older page, a hand edit), the whole number the words say (`_typed_count`), set on the family's own
    count: its sources stay, the other counts and the sum of the sheets of one floor and area (`Count.added_up`) go, as
    the page builds a typed count (a typed count settles the dispute). None when the decision holds no count (words
    with no number in them): nothing is applied."""
    if d.count is not None:
        return d.count
    kind, value = _typed_count(d.reason)
    return dataclasses.replace(family.count, value=value, others=(), added_up=None) if kind == "number" else None


def _with_new_count(family: Family, d: Decision) -> Family:
    """`family` with the count a family change gives it, when the change is about it (by name) and holds a count."""
    count = _new_count(d, family) if family.name == d.family_name else None
    return family if count is None else dataclasses.replace(family, count=count)


def _accept_clears(device: Device, family: Family, system: System | None = None,
                   accepted: frozenset[str] = frozenset()) -> bool:
    """Whether accepting a family's count clears this device's quantity flag: the device was counted from that
    family (shared sources, `counts.counted_from`, the rule the run flags by) and has a count of its own. A device
    whose own count is unknown keeps its flag: accepting the family does not say how many of it there are.
    With its `system`, a device also counted from another disputed family of it (`counts.disputed_families`) keeps
    its flag until that family is accepted as well (its name in `accepted`): one family's Accept does not settle
    the other family's count (the estimator's ruling, REVIEW-019b F3)."""
    if not (device.flag == "quantity" and device.quantity.value is not None and counted_from(device, family)):
        return False
    if system is None:
        return True
    return all(other.name in accepted for other in disputed_families(system)
               if other.name != family.name and counted_from(device, other))


def unhonored_decisions(before: Job, decisions: Sequence[Decision], after: Job, *,
                        copies: dict[Decision, int] | None = None) -> list[Finding]:
    """A must_fix for each saved decision the final job does not still show.

    `before` is the job the decisions were applied to, `after` the job after the last write. The job the decisions
    ask for is built once, `apply_decisions(before, decisions)`, so two decisions on one line (a change, then a
    delete of it or of its system) are checked together. The writer numbers devices again (`d1`, `d2`, ...), so a
    line is recognized by its content, not by the id it wore, and by how many lines have that content: deleting one
    of two identical lines is honored while the final job has no more of them than the decisions left. A change is
    honored while its new line is in the final job and the old line is not back. An accept sticks unless family
    counts changed or the line has been re-flagged. A "not honored" card sits on the line that came back.
    A device decision that carries the line as the page showed it (`was`) but matches no line of `before` could not
    be applied: it is a must_fix "decision could not be applied" (same rule name), on the line in `after` that still
    has that content when there is one, else on the system (no device). Such a decision, or a family decision,
    whose system (or family) `before` does not have at all is not applied: a check (severity "check") saying so,
    unless it is a delete or a system delete among `decisions` took that system out. A decision without `was` that named nothing the earlier job had is skipped, as
    `apply_decisions` skips it. A delete `apply_decisions` holds back
    (`copies`: the number of copies of the line differs from what the estimator saw) could not be applied either.
    A family change that carries words and no count, whose words hold no whole number ("only the roof units"), is
    applied by nothing: a check (severity "check") says so and how to answer it again (`_holds_no_count`)."""
    copies = copies or {}
    expected = apply_seen(before, decisions, copies)
    accepted = _accepted_families(decisions)
    deleted = frozenset(d.system_key for d in decisions
                        if d.action == "delete" and d.device_id is None and d.family_name is None)
    return [finding for decision in decisions
            if (finding := _unhonored(before, decision, after, expected, copies.get(decision), accepted,
                                      deleted)) is not None]


def _matches_nothing(job: Job, decision: Decision) -> bool:
    """True for a device decision whose `was` snapshot matches no line of `job`'s system (or front end), so
    `apply_decisions` cannot apply it to `job`. False when the system is not on the job at all."""
    if decision.device_id is None or decision.was is None:
        return False
    devices = _devices(job, decision.system_key)
    return devices is not None and not _same_device(devices, decision.was)


_GONE_DELETE = ("The line you deleted is not in this run's job as you saw it. It may have been removed or re-worded. "
                "Check this system.")
_GONE_OTHER = ("The line you decided on is not in this run's job, so your decision was not applied. "
               "Find the line on this page and decide again.")
_TWIN_DELETE = ("When you deleted this line, the job had a different number of copies of it than this run has, so "
                "the delete was not applied (it could take the only copy). Check how many copies this system needs "
                "and delete again if one is too many.")


def _unhonored(before: Job, decision: Decision, after: Job, expected: Job | None = None,
               seen: int | None = None, accepted: dict[str, frozenset[str]] | None = None,
               deleted: frozenset[str] = frozenset()) -> Finding | None:
    if accepted is None:
        accepted = _accepted_families([decision])
    if expected is None:
        expected = apply_seen(before, [decision], {decision: seen} if seen is not None else None)
    subject = decision.device_id or decision.family_name or decision.system_key or "the front end"
    if _lost_its_system(before, decision, deleted):
        return _lost_card(before, decision, subject)
    if _held_back(_devices(before, decision.system_key), decision, seen):
        still = next((dev for dev in _devices(after, decision.system_key) or () if _same_device((dev,), decision.was)),
                     None)
        return Finding("decision not honored", decision.system_key, still.id if still else None,
                       "must_fix", f"decision could not be applied: {decision.action} {subject}", _TWIN_DELETE)
    if _matches_nothing(before, decision):
        still = next((dev for dev in _devices(after, decision.system_key) or () if _same_device((dev,), decision.was)),
                     None)
        fix = _GONE_DELETE if decision.action == "delete" and still is None else _GONE_OTHER
        return Finding("decision not honored", decision.system_key, still.id if still else None,
                       "must_fix", f"decision could not be applied: {decision.action} {subject}", fix)
    if _holds_no_count(decision):
        return _no_count_card(decision, subject)
    if not _decision_holds(before, decision, after, expected, accepted.get(decision.system_key, frozenset())):
        device_id = decision.device_id
        target = _target(before, decision)
        if target is not None:
            later = [dev for dev in _devices(after, decision.system_key) or () if _same_device((dev,), target)]
            kept = {dev.id for dev in _devices(expected, decision.system_key) or () if _same_device((dev,), target)}
            back = [dev for dev in later if dev.id not in kept] or later
            if back:
                device_id = back[-1].id
        return Finding("decision not honored", decision.system_key, device_id, "must_fix",
                       f"decision not honored: {decision.action} {subject}",
                       "The estimator's decision stands. The last write undid it.")
    return None


def _holds_no_count(decision: Decision) -> bool:
    """True for a family change that carries words and no count, and whose words hold none (`_typed_count`): from an
    older page or a hand edit, it was kept in the history and nothing applies it (`_new_count`)."""
    return (decision.family_name is not None and decision.action == "change" and decision.count is None
            and _typed_count(decision.reason)[0] == "words")


def _no_count_card(decision: Decision, subject: str) -> Finding:
    """The check (severity "check", as `_lost_card`: the estimator is never left with a card they cannot clear) for a
    saved family change whose words hold no count (`_holds_no_count`). About the count (no line): a new answer on
    that count replaces it."""
    return Finding("decision not honored", decision.system_key, None, "check",
                   f"this saved decision (change {subject}) says {decision.reason.strip()!r}, which holds no whole "
                   "number; it is not applied",
                   "Change that count again on its card: type a whole number, alone or with one unit word, for example "
                   "5 or 5 units, or ## for not known. Then save again.")


def _lost_its_system(before: Job, decision: Decision, deleted: frozenset[str]) -> bool:
    """True for a line decision (it carries the line as the page showed it, `was`) or a family decision whose
    system (or family) `before` does not have, when no system delete among the decisions (`deleted`, by key) took
    that system out: `apply_decisions` skips it, so it is not applied and must not pass in silence (RUN-5). Never
    for a delete: with its system (or family) gone, a delete has nothing left to do."""
    if decision.system_key in deleted or decision.action == "delete":
        return False
    if decision.device_id is not None and decision.was is not None:
        return _devices(before, decision.system_key) is None
    if decision.device_id is None and decision.family_name is not None and decision.system_key != "":
        return _family(before, decision.system_key, decision.family_name) is None
    return False


def _lost_card(before: Job, decision: Decision, subject: str) -> Finding:
    """The check (severity "check", not must_fix, so the estimator is never left with a card they cannot clear) for
    a saved decision whose system, or family, this run no longer has (`_lost_its_system`). About the system (no
    line): the decision is not applied."""
    key = decision.system_key
    if decision.device_id is None and any(s.key == key for s in before.systems):
        where = f"the {decision.family_name} count of the {key} system, which this run no longer has"
        fix = ("It is not applied. If the count was merged into another family or renamed, set the count again on "
               "its new card.")
    else:
        where = f"the {key} system, which this run no longer has"
        fix = "It is not applied. If the system was merged or renamed, make the change again on its new block."
    return Finding("decision not honored", key, None, "check",
                   f"this saved decision ({decision.action} {subject}) is for {where}; it is not applied", fix)


def _decision_holds(before: Job, decision: Decision, after: Job, expected: Job,
                    accepted: frozenset[str] = frozenset()) -> bool:
    if decision.device_id is not None:
        return _device_holds(before, decision, after, expected)
    if decision.family_name is not None:
        return _family_holds(before, decision, after, expected, accepted)
    if decision.system_key == "" or not any(s.key == decision.system_key for s in before.systems):
        return True
    gone = decision.action == "delete"
    present = any(s.key == decision.system_key for s in after.systems)
    return present != gone


def _target(before: Job, decision: Decision) -> Device | None:
    """The line of `before` the device decision is about: by its saved content when it has one, else by id."""
    earlier = _devices(before, decision.system_key)
    if earlier is None or decision.device_id is None:
        return None
    if decision.was is not None:
        return (next((d for d in earlier if d.id == decision.device_id and _same_device((d,), decision.was)), None)
                or next((d for d in earlier if _same_device((d,), decision.was)), None))
    return next((device for device in earlier if device.id == decision.device_id), None)


def _how_many(devices: tuple[Device, ...] | None, line: Device, unflagged: bool = False) -> int:
    """How many lines are `line` (the id and the flag may differ); with `unflagged`, only those with no flag."""
    return sum(1 for dev in devices or () if _same_device((dev,), line) and (not unflagged or dev.flag == "none"))


def _device_holds(before: Job, decision: Decision, after: Job, expected: Job) -> bool:
    target = _target(before, decision)
    if target is None:
        return True
    want = _devices(expected, decision.system_key)
    if want is None:
        return True                                 # the same file deleted the system; that decision reports itself
    later = _devices(after, decision.system_key)
    if decision.action == "delete":
        return _how_many(later, target) <= _how_many(want, target)
    if decision.action == "change" and decision.device is not None:
        new = _read_count_name(decision, target).device
        return (_how_many(later, new) >= _how_many(want, new)
                and (_same_device((target,), new) or _how_many(later, target) <= _how_many(want, target)))
    if _how_many(later, target) < _how_many(want, target):
        return False
    if decision.action == "accept":
        counts_changed = _count_changed_between(before, after, decision.system_key,
                                                accept_families(before, decision))
        if not counts_changed and _how_many(later, target, unflagged=True) < _how_many(want, target, unflagged=True):
            return False
    return True


def _family_holds(before: Job, decision: Decision, after: Job, expected: Job,
                  accepted: frozenset[str] = frozenset()) -> bool:
    earlier = _family(before, decision.system_key, decision.family_name)
    if earlier is None:
        return True
    if not any(s.key == decision.system_key for s in expected.systems):
        return True                                 # the same file deleted the system; that decision reports itself
    want = _family(expected, decision.system_key, decision.family_name)
    got = _family(after, decision.system_key, decision.family_name)
    if want is None or got is None or got.count != want.count:
        return False
    if decision.action == "accept":
        system = after.system(decision.system_key) if any(s.key == decision.system_key for s in after.systems) else None
        if system is not None:
            family = next((f for f in system.families if f.name == decision.family_name), None)
            if family is not None and family.count.others:
                for dev in system.devices:
                    if _accept_clears(dev, family, system, accepted | {family.name}):
                        return False
    return True


def accept_family(job: Job | None, decision: Decision) -> str | None:
    """The family an accept (or any decision) is about: the family it names, else the family whose count the
    line's quantity cites (the line as saved, else the line of `job` with its id). None when that is not known;
    then a count change of any family of the system counts as a change of its family."""
    if decision.family_name is not None:
        return decision.family_name
    if job is None or decision.device_id is None:
        return None
    line = decision.was or next((d for d in _devices(job, decision.system_key) or ()
                                 if d.id == decision.device_id), None)
    family = _family_of_device(job, decision.system_key, line)
    return family.name if family is not None else None


def accept_families(job: Job | None, decision: Decision) -> frozenset[str] | None:
    """Every family an accept (or any decision) is about: the family it names, else every family whose count the
    line's quantity cites (a line may cite two). None when no family is known; then a count change of any family
    of the system counts. A count change of any of these families overrules the accept."""
    if decision.family_name is not None:
        return frozenset((decision.family_name,))
    if job is None or decision.device_id is None or decision.system_key == "":
        return None
    line = decision.was or next((d for d in _devices(job, decision.system_key) or ()
                                 if d.id == decision.device_id), None)
    if line is None:
        return None
    system = next((s for s in job.systems if s.key == decision.system_key), None)
    if system is None:
        return None
    names = frozenset(family.name for family in system.families if counted_from(line, family))
    return names or None


def _count_changed_between(before: Job, after: Job, key: str, family: str | frozenset[str] | None) -> bool:
    """True when the count of family `family` (or of any family in a set of names) of system `key` (any family of
    it, for None) differs between the two jobs."""
    if isinstance(family, str):
        family = frozenset((family,))
    if key == "":
        return False
    old = next((s for s in before.systems if s.key == key), None)
    new = next((s for s in after.systems if s.key == key), None)
    if old is None or new is None:
        return False
    counts = {f.name: f.count for f in new.families}
    return any(counts.get(f.name, f.count) != f.count for f in old.families
               if family is None or f.name in family)


def _family_of_device(job: Job, key: str, device: Device | None) -> Family | None:
    if device is None or key == "":
        return None
    for system in job.systems:
        if system.key == key:
            for family in system.families:
                if counted_from(device, family):
                    return family
    return None


def _devices(job: Job, key: str) -> tuple[Device, ...] | None:
    if key == "":
        return None if job.front_end is None else job.front_end.devices
    for system in job.systems:
        if system.key == key:
            return system.devices
    return None


def _family(job: Job, key: str, name: str | None):
    if not name or key == "":
        return None
    for system in job.systems:
        if system.key == key:
            for family in system.families:
                if family.name == name:
                    return family
            return None
    return None


def _same_device(devices: tuple[Device, ...], device: Device) -> bool:
    """True when some device is the same line. The id and the flag may differ."""
    probe = dataclasses.replace(device, id="", flag="none")
    return any(dataclasses.replace(other, id="", flag="none") == probe for other in devices)
