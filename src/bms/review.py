"""The review page and the estimator's decisions (workstream 7, design §4.7).

`review_page` writes one self-contained `Review.html`; the estimator answers the open questions in a browser, which
cannot write files, so the page downloads `decisions.json` and the estimator saves it into the out folder.
`load_decisions` reads it back and `apply_decisions` (pure) applies it to the Job.
"""
from __future__ import annotations

import dataclasses
import html
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from bms.model import PARTIES, VERBS, Count, Decision, Device, Finding, Job, ModelError, Ref, System

REVIEW_PAGE = "Review.html"
DECISIONS_FILE = "decisions.json"
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

    def add(**kw) -> None:
        nonlocal seq
        seq += 1
        out.append(_Question(qid=f"q{seq}", order=seq, **kw))

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
    can_delete = q.level == "device" or (q.level == "system" and q.system_key != "")
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
           reason: ""};
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
save that file into the out folder, then run the estimate again.</div><div id="saved"></div></header>
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


def _apply_to_devices(devices: tuple[Device, ...], device_id: str, decision: Decision) -> tuple[Device, ...]:
    out: list[Device] = []
    for device in devices:
        if device.id != device_id:
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
    quantity flags on that system's devices; delete removes the device (or the system, when no device or family is
    named); change replaces the device (same id) or the family's Count. A decision naming a system or device the
    job no longer has is skipped. Pure. System key "" names the front end's devices."""
    for decision in decisions:
        job = _apply_one(job, decision)
    return job


def _apply_one(job: Job, d: Decision) -> Job:
    if d.system_key == "":
        front = job.front_end
        if front is None or d.device_id is None or not any(x.id == d.device_id for x in front.devices):
            return job
        return dataclasses.replace(
            job, front_end=dataclasses.replace(front, devices=_apply_to_devices(front.devices, d.device_id, d)))
    if not any(s.key == d.system_key for s in job.systems):
        return job
    system: System = job.system(d.system_key)
    if d.device_id is not None:
        if not any(x.id == d.device_id for x in system.devices):
            return job
        return job.with_system(dataclasses.replace(
            system, devices=_apply_to_devices(system.devices, d.device_id, d)))
    if d.family_name is not None:
        if not any(f.name == d.family_name for f in system.families):
            return job
        if d.action == "accept":
            devices = tuple(dataclasses.replace(dev, flag="none") if dev.flag == "quantity" else dev
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
