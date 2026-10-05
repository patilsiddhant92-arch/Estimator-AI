"""The review page and the estimator's decisions (workstream 7, design §4.7).

`review_page` writes one self-contained `Review.html`; the estimator answers the open questions in a browser, which
cannot write files, so the page downloads `decisions.json` and the estimator saves it into the out folder.
`load_decisions` reads it back and `apply_decisions` (pure) applies it to the Job. Each save holds only the answers
on the page it came from, so the run keeps every saved decision in `decisions history.json` (`merge_decisions`):
a new save adds a round, its answer on a line replaces an earlier round's answer on the same line, and reading the
same file again adds nothing. Starting over means deleting both files.
`unhonored_decisions` is the post-check: a saved decision that the final job does not still show.
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

from bms.counts import counted_from
from bms.model import PARTIES, VERBS, Count, Decision, Device, Finding, Job, ModelError, Ref, System

REVIEW_PAGE = "Review.html"
DECISIONS_FILE = "decisions.json"
DECISIONS_HISTORY = "decisions history.json"
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

    def add(**kw) -> None:
        nonlocal seq
        device_id = kw.get("device_id")
        key = (kw.get("system_key", ""), device_id) if device_id else None
        if key is not None and key in by_device:
            current = by_device[key]
            notes = tuple(note for note in kw.get("notes") or () if note not in current.notes)
            rank = kw.get("rank", current.rank)
            if kw.get("finding_rule") and current.finding_rule is not None:
                # a second finding on the line: the most severe leads the card (title and rule, the rule a saved
                # decision keeps); the other's description stays on the card as a note, once
                title = kw.get("title")
                if rank < current.rank:
                    title, current.title = current.title, title or current.title
                    current.finding_rule = kw["finding_rule"]
                if title and title != current.title and f"Finding: {title}" not in current.notes + notes:
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

    scopes: list[tuple[str, Sequence[Device], Sequence]] = [(s.key, s.devices, s.families) for s in job.systems]
    if job.front_end is not None:
        scopes.append(("", job.front_end.devices, ()))
    by_key = {key: devices for key, devices, _f in scopes}

    for finding in findings:
        device = (next((d for d in by_key.get(finding.system_key, ()) if d.id == finding.device_id), None)
                  if finding.device_id else None)
        add(system_key=finding.system_key,
            rank=RANK_MUST_FIX if finding.severity == "must_fix" else RANK_CHECK,
            title=finding.what, level="device" if device is not None else "system",
            device_id=device.id if device else None, finding_rule=finding.rule,
            notes=(f"What to do: {finding.fix}",) if finding.fix else (),
            device=device, count=device.quantity if device else None, refs=device.refs if device else ())

    for key, devices, families in scopes:
        for family in families:
            count = family.count
            if count.others or count.value is None:
                why = ("The sources give different counts; the highest prints." if count.others
                       else "No source gives a count; it prints as Qty (##).")
                add(system_key=key, rank=RANK_FLAGGED, title=f"How many {family.name} units?",
                    level="family", family_name=family.name, notes=(why,), count=count, refs=count.sources)
        for device in devices:
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
    return out


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
    parts.append("</div>")
    return "".join(parts)


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
    hint = {"device": "Type a number to set the count, ## for not known, or new words to rename the line.",
            "family": "Type a number to set the count, or ## for not known.",
            "system": "A note for the writer; it is recorded but does not edit the job."}[q.level]
    delete = f'<button type="button" data-act="delete">{del_label}</button>' if can_delete else ""
    selects = ""
    if q.level == "device" and q.device:
        d = q.device
        selects = ('<div class="fields">' + _select("verb", VERBS, d.verb)
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
          f'aria-label="{_e(hint)}"><div class="hint">{_e(hint)}</div>{selects}</div></div>')


_SCRIPT_CORE = r"""
function parseNumber(text) {
  var t = String(text || "").trim();
  if (/^\d+$/.test(t)) return {kind: "number", value: parseInt(t, 10)};
  if (/^(##|unknown|not known|qty \(##\))$/i.test(t)) return {kind: "number", value: null};
  return {kind: t ? "words" : "none", value: t};
}
function buildDecision(q, state) {
  if (!state || !state.action) return null;
  var d = {system_key: q.system_key, action: state.action, device_id: q.device_id || null,
           family_name: q.family_name || null, device: null, count: null, finding_rule: q.finding_rule || null,
           reason: "", was: (q.level === "device" && q.device) ? JSON.parse(JSON.stringify(q.device)) : null};
  if (state.action === "change") {
    var parsed = parseNumber(state.text);
    d.reason = String(state.text || "").trim();
    if (q.level === "device" && q.device) {
      var dev = JSON.parse(JSON.stringify(q.device));
      if (parsed.kind === "number") dev.quantity.value = parsed.value;
      else if (parsed.kind === "words") dev.name = parsed.value;
      var f = state.fields || {};
      ["verb", "furnished_by", "installed_by", "wired_by"].forEach(function (k) { if (f[k]) dev[k] = f[k]; });
      dev.flag = "none";
      d.device = dev;
    } else if (q.level === "family" && q.count) {
      var c = JSON.parse(JSON.stringify(q.count));
      if (parsed.kind === "number") c.value = parsed.value;
      d.count = c;
    }
  }
  return d;
}
"""

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
  }
});
document.addEventListener("change", function (ev) {
  var el = ev.target.closest(".q");
  if (el && states[el.id] && states[el.id].action === "change") states[el.id].fields = readFields(el);
});
document.getElementById("showall").addEventListener("click", function () {
  var on = document.body.classList.toggle("all");
  this.textContent = on ? "Show only the top questions" : "Show all questions";
});
document.getElementById("save").addEventListener("click", function () {
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
.q.extra{display:none}body.all .q.extra{display:block}.more{display:block}body.all .more{display:none}
.qtitle{font-weight:600}
.tag{display:inline-block;font-size:12px;border-radius:4px;padding:1px 6px;border:1px solid var(--line);color:var(--mute)}
.tag.r0{color:var(--bad);border-color:var(--bad)}.tag.r1{color:var(--warn);border-color:var(--warn)}
.rule,.where,.hint,.others,.empty{color:var(--mute);font-size:13px}.src{font-weight:600;margin-right:4px}
.note{margin:4px 0}.count{margin:6px 0}ul{margin:4px 0 4px 18px;padding:0}
.proof img{display:block;max-width:100%;max-height:260px;border:1px solid var(--line);margin:4px 0}
.buttons{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:6px}
button{font:inherit;padding:4px 12px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--ink);cursor:pointer}
button.on{background:var(--acc);color:#fff;border-color:var(--acc)}.q.answered{border-left:3px solid var(--ok);padding-left:8px}
.changebox{margin-top:6px}.changebox input[type=text]{width:100%;padding:5px}.fields{display:flex;gap:10px;flex-wrap:wrap;margin-top:6px}
.fields label{font-size:13px}.state{color:var(--ok);font-size:13px}#saved{color:var(--ok);margin-top:6px}
button.primary{background:var(--acc);color:#fff;border-color:var(--acc)}
@media (max-width:600px){main{padding:8px}.card{padding:10px}}
"""


def review_page(job: Job, findings: Sequence[Finding], out_dir: Path) -> Path:
    """Write `out_dir/Review.html` and return its path.

    One card per system (and one for the front end and the whole job when they have questions) with its open
    questions: the findings, flagged devices and counts with others, and assumptions, ranked must_fix first, then
    counts flagged, then assumptions, then checks. Only the top MAX_QUESTIONS for the job show at first; "Show all"
    reveals the rest. Each count shows every source and other count, and the proof image when a Ref points to a
    relative image path. Buttons Accept / Change / Delete per question; "Save decisions" downloads `decisions.json`
    (a list of `Decision.to_dict()`), which the estimator saves into `out_dir`. One self-contained file."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ranked = _ranked(_questions(job, findings))
    proofs = count_proofs(out_dir)
    visible = {q.qid for q in ranked[:MAX_QUESTIONS]}

    cards: list[tuple[str, str]] = [(s.key, f"{s.name} ({s.key})") for s in job.systems]
    if job.front_end is not None:
        cards.append(("", "Front end and whole job"))
    known = {key for key, _ in cards}
    for q in ranked:
        if q.system_key not in known:
            known.add(q.system_key)
            cards.append((q.system_key, "Whole job" if q.system_key == "" else q.system_key))

    body: list[str] = []
    for key, title in cards:
        mine = [q for q in ranked if q.system_key == key]
        hidden = sum(1 for q in mine if q.qid not in visible)
        inner = "".join(_question_html(q, q.qid not in visible, proofs) for q in mine)
        if not mine:
            inner = '<p class="empty">Nothing to ask here.</p>'
        elif hidden == len(mine):
            inner += f'<p class="empty more">{hidden} more question(s) under "Show all questions".</p>'
        body.append(f'<section class="card" data-system="{_e(key)}"><h2>{_e(title)}</h2>{inner}</section>')
    if job.questions:
        body.append('<section class="card"><h2>Open questions for the client</h2><ul>'
                    + "".join(f"<li>{_e(t)}</li>" for t in job.questions) + "</ul></section>")

    total = len(ranked)
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


def load_decisions(out_dir: Path) -> list[Decision]:
    """The decisions in `out_dir/decisions.json` (a JSON list of Decision dicts); [] when the file is missing.
    Raises `bms.model.ModelError` naming the entry when one is malformed."""
    path = Path(out_dir) / DECISIONS_FILE
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ModelError(f"{DECISIONS_FILE}: not valid JSON ({error})") from None
    if not isinstance(data, list):
        raise ModelError(f"{DECISIONS_FILE}: expected a list of decisions, got {type(data).__name__}")
    out: list[Decision] = []
    for n, entry in enumerate(data):
        try:
            out.append(Decision.from_dict(entry))
        except ModelError as error:
            raise ModelError(f"{DECISIONS_FILE}: decisions[{n}]: {error}") from None
    return out


@dataclass(frozen=True)
class SavedDecision:
    """One decision kept in the run's history: the save it came from (`round`, 1 for the first) and whether it took
    effect on some run (it matched a line and was applied). `saved` is the decision as decisions.json had it when
    the run rebased it onto an earlier change (`merge_decisions`); None when `decision` is that decision.
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
    line whatever id the page showed (`_same_line`). Pure."""
    history = list(history)
    saved = list(saved)
    if not saved:
        return history
    latest = max((h.round for h in history), default=0)
    if history and [h.as_saved for h in history if h.round == latest] == saved:
        return history
    carried = [h for h in history
               if not any(_same_line(h.as_saved, d, job) or _same_line(h.decision, d, job) for d in saved)]
    new: list[SavedDecision] = []
    for d in saved:
        base = _changed_into(carried, d)
        if base is None:
            new.append(SavedDecision(d, latest + 1, copies=_seen(job, d)))
            continue
        carried.remove(base)
        old = base.decision
        rebased = dataclasses.replace(d, device_id=old.device_id, was=old.was)
        new.append(SavedDecision(rebased, latest + 1, saved=d, copies=_seen(job, rebased)))
    return [*carried, *new]


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
            out.append(dataclasses.replace(decision.device, id=device.id) if decision.device is not None
                       else device)
        # delete: dropped
    return tuple(out)


def apply_decisions(job: Job, decisions: Sequence[Decision]) -> Job:
    """The job with the decisions applied, in order: accept clears the device's flag, or, for a family, the
    quantity flags of the devices counted from that family (shared sources, `counts.counted_from`) whose own count
    is known; delete removes the device (or the system, when no device or family is
    named); change replaces the device (same id) or the family's Count. A decision naming a system or device the
    job no longer has is skipped. Pure. System key "" names the front end's devices.

    A device delete whose id no longer holds its line is applied to a line with the same content only when as many
    copies of it are left as the estimator saw (`apply_seen`, with `copies_seen` of the history; when not known, see
    `_held_back`): else it is not applied, and `unhonored_decisions` gives it a "could not be applied" card."""
    return apply_seen(job, decisions, None)


def apply_seen(job: Job, decisions: Sequence[Decision], copies: dict[Decision, int] | None) -> Job:
    """`apply_decisions` with the number of copies of its line each delete saw (`copies_seen` of the history)."""
    copies = copies or {}
    for decision in decisions:
        job = _apply_one(job, decision, copies.get(decision))
    return job


def _apply_one(job: Job, d: Decision, seen: int | None = None) -> Job:
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
            devices = tuple(dataclasses.replace(dev, flag="none") if _accept_clears(dev, family) else dev
                            for dev in system.devices)
            return job.with_system(dataclasses.replace(system, devices=devices))
        if d.action != "change" or d.count is None:
            return job
        families = tuple(dataclasses.replace(f, count=d.count) if f.name == d.family_name else f
                         for f in system.families)
        return job.with_system(dataclasses.replace(system, families=families))
    if d.action == "delete":
        return dataclasses.replace(job, systems=tuple(s for s in job.systems if s.key != d.system_key))
    return job


def _accept_clears(device: Device, family: Family) -> bool:
    """Whether accepting a family's count clears this device's quantity flag: the device was counted from that
    family (shared sources, `counts.counted_from`, the rule the run flags by) and has a count of its own. A device
    whose own count is unknown keeps its flag: accepting the family does not say how many of it there are."""
    return device.flag == "quantity" and device.quantity.value is not None and counted_from(device, family)


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
    has that content when there is one, else on the system (no device). A decision without `was` that named
    nothing the earlier job had is skipped, as `apply_decisions` skips it. A delete `apply_decisions` holds back
    (`copies`: the number of copies of the line differs from what the estimator saw) could not be applied either."""
    copies = copies or {}
    expected = apply_seen(before, decisions, copies)
    return [finding for decision in decisions
            if (finding := _unhonored(before, decision, after, expected, copies.get(decision))) is not None]


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
               seen: int | None = None) -> Finding | None:
    if expected is None:
        expected = apply_seen(before, [decision], {decision: seen} if seen is not None else None)
    subject = decision.device_id or decision.family_name or decision.system_key or "the front end"
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
    if not _decision_holds(before, decision, after, expected):
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


def _decision_holds(before: Job, decision: Decision, after: Job, expected: Job) -> bool:
    if decision.device_id is not None:
        return _device_holds(before, decision, after, expected)
    if decision.family_name is not None:
        return _family_holds(before, decision, after, expected)
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
        new = decision.device
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


def _family_holds(before: Job, decision: Decision, after: Job, expected: Job) -> bool:
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
                    if _accept_clears(dev, family):
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
