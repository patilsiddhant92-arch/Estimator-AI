"""Every failing input of the three reviews of the regex rewriter (Colab/audit-cleanup-review*.md), under the new
policy: detect and refuse, never rewrite. A client text that prints an issued id anywhere, or an unissued id-shaped
token in a citation, is refused at intake with the token named; any other text is accepted as written (only its
label comes off). The renderer rewrites no sentence: its safety net takes out an issued id token and nothing else,
and the validator reports it as must_fix first. All data is invented.

Each case runs the real intake (`ai._check_system`) and the detector itself (`citations.SourceIds`)."""
from __future__ import annotations

import json
import re
import time
from dataclasses import replace
from pathlib import Path

import pytest

from bms import ai, citations
from bms.model import (Assumption, Clarification, Count, Device, Family, Job, OtherCount, Ref, ScopeException,
                       System)
from bms.playbook import load_playbook
from bms.render import RenderError, render
from bms.validate import RULE, validate

FIX = Path(__file__).resolve().parent / "fixtures"
ROOT = Path(__file__).resolve().parents[2]
CITED = Ref("Q88", "q", "M-201, Invented.pdf page 9")          # the device's own ref (issued, used in no text)
TAGS = ("EF-1", "EF-2")
WORDS = "name the document in words; cite it as a Ref, never print an id"


def _answer(field: str, kind: str, text: str) -> dict:
    device = Device("EF.d1", "controller", "DDC Controller", "Furnish and Install", "AME", "AME", "AME", Count(2),
                    (CITED,))
    clarifications = ()
    if field == "name":
        device = replace(device, name=text)
    elif field == "what":
        device = replace(device, assumption=Assumption(text, "the invented schedule shows it"))
    elif field == "why":
        device = replace(device, assumption=Assumption("one invented valve", text))
    elif field == "clarification":
        clarifications = (Clarification(kind, text),)
    devices = () if field == "no_scope_reason" else (device,)
    answer = System("EF", "Exhaust Fans", "Exhaust Fan", "field", (Family("Exhaust Fan", TAGS, Count(2)),),
                    devices=devices, clarifications=clarifications).to_dict()
    if field == "no_scope_reason":
        answer.update(no_scope_reason=text, tech_hours=None)
    return answer


def _intake(field: str, kind: str, text: str, issued=(), tags=TAGS):
    """The real intake on one text: (the System it gives or None, the problems that refuse it)."""
    skeleton = System("EF", "Exhaust Fans", "Exhaust Fan", "field", (Family("Exhaust Fan", tags, Count(2)),),
                      sequence_refs=tuple(Ref(i, "q", "M-101, Invented.pdf page 2") for i in issued))
    known = frozenset({*issued, CITED.source_id})
    return ai._check_system(_answer(field, kind, text), skeleton, None, known, (), (), [], tags)


def _stored(system: System, field: str) -> str:
    if field == "name":
        return system.devices[0].name
    if field == "what":
        return system.devices[0].assumption.what
    if field == "why":
        return system.devices[0].assumption.why
    if field == "no_scope_reason":
        return system.no_scope_reason
    return system.clarifications[0].text if system.clarifications else ""


def _detector(issued=(), tags=TAGS):
    return citations.SourceIds.of([*issued, CITED.source_id], tags)


S141 = ("S141",)

# (review finding, field, kind, text, issued ids, tags, the tokens the reason names)
REFUSED = [
    # review 1
    ("r1 C1", "clarification", "confirm", "Confirm valves per S141 and S999.", S141, TAGS, ("S141", "S999")),
    ("r1 C1", "clarification", "note", "Valves per S141 to S145.", S141, TAGS, ("S141", "S145")),
    ("r1 C1", "clarification", "note", "[S141, S999]", S141, TAGS, ("S141", "S999")),
    ("r1 C1", "clarification", "note", "S141-S999", S141, TAGS, ("S141", "S999")),
    ("r1 C1", "what", "", "two valves per S999", S141, TAGS, ("S999",)),
    ("r1 C1", "why", "", "S141 shows two", S141, TAGS, ("S141",)),
    ("r1 C1", "clarification", "note", "Valves per S141 and S999.", ("S141", "F1", "I3"), TAGS, ("S141", "S999")),
    ("r1 C1", "no_scope_reason", "", "No BMS scope per S141 and S999; the fans are on their own controls.", S141,
     TAGS, ("S141", "S999")),
    ("r1 I1", "clarification", "note", "Fans F1-F4 run per S141.", ("S141", "F1"), ("F1-F4",), ("S141",)),
    ("r1 I1", "clarification", "note", "Fans F1 thru F4 per I3.", ("I3", "F1"), ("F1-F4",), ("I3",)),
    ("r1 I2", "clarification", "note", "Fan C2 serves the lab", ("C2",), TAGS, ("C2",)),
    ("r1 I3", "clarification", "note", "Valves per s141.", S141, TAGS, ("s141",)),
    ("r1 I3", "clarification", "note", "Per S141A.", S141, TAGS, ("S141A",)),
    ("r1 I4", "name", "", "Control Valve per S141", S141, TAGS, ("S141",)),
    # review 2
    ("r2 I-1", "clarification", "note", "two valves[S141].", S141, TAGS, ("S141",)),
    ("r2 I-1", "clarification", "note", "[S141]valves", S141, TAGS, ("S141",)),
    ("r2 I-1", "clarification", "note", "valves [S141]x", S141, TAGS, ("S141",)),
    ("r2 I-2", "clarification", "note", "Valves per S141.", S141, TAGS, ("S141",)),
    ("r2 I-3", "clarification", "note", "per S141 and F5-F8", S141, ("F5-F8",), ("S141",)),
    ("r2 I-3", "clarification", "note", "Fans F5 to F8, S141", S141, ("F5-F8",), ("S141",)),
    ("r2 I-3", "clarification", "note", "Fans (F5-F8, S141)", S141, ("F5-F8",), ("S141",)),
    ("r2 I-3", "clarification", "note", "Fans F5-F8, F1", ("F1",), ("F5-F8",), ("F1",)),
    ("r2 I-4", "clarification", "note", "Two valves (see S999).", S141, TAGS, ("S999",)),
    ("r2 I-4", "clarification", "note", "Two valves (per S999).", S141, TAGS, ("S999",)),
    ("r2 I-4", "name", "", "Valve (see S999)", S141, TAGS, ("S999",)),
    ("r2 I-4", "clarification", "note", "Two valves [see S999]", S141, TAGS, ("S999",)),
    ("r2 I-4", "clarification", "note", "Two valves (per S7).", ("S7",), TAGS, ("S7",)),
    ("r2 I-5", "clarification", "note", "Fans stay on, valves per S141.", S141, TAGS, ("S141",)),
    ("r2 I-5", "clarification", "note", "Fans stay on, valves per S999.", S141, TAGS, ("S999",)),
    ("r2 I-5", "clarification", "note", "Valves per S141; the fans are left on.", S141, TAGS, ("S141",)),
    ("r2 I-5", "clarification", "note", "Fans per S999 stay on.", S141, TAGS, ("S999",)),
    ("r2 m-3", "clarification", "note", "per S141/S999", S141, TAGS, ("S141", "S999")),
    ("r2 m-3", "clarification", "note", "per S141 / S999", S141, TAGS, ("S141", "S999")),
    ("r2 m-3", "clarification", "note", "S141‐S999", S141, TAGS, ("S141", "S999")),
    ("r2 m-3", "clarification", "note", "S141—S999", S141, TAGS, ("S141", "S999")),
    ("r2 m-4", "name", "", "F1", ("F1",), TAGS, ("F1",)),
    ("r2 m-5", "clarification", "note", "see S998 S999", ("S998",), TAGS, ("S998",)),
    # review 3
    ("r3 C1", "clarification", "note", "see sheet S141", S141, TAGS, ("S141",)),
    ("r3 C1", "clarification", "note", "sheet S141.", S141, TAGS, ("S141",)),
    ("r3 C1", "clarification", "note", "dwg S141", S141, TAGS, ("S141",)),
    ("r3 C1", "clarification", "note", "sheets S962a, F10", ("S962a",), TAGS, ("S962a",)),
    ("r3 C1", "clarification", "note", "Fans per sheet I3.", ("I3",), TAGS, ("I3",)),
    ("r3 C1", "clarification", "note", "sheets C101 and I3", ("I3",), TAGS, ("I3",)),
    ("r3 C2", "clarification", "note", "S​141 runs", S141, TAGS, ("S141",)),
    ("r3 C2", "clarification", "note", "Fan Ｓ１４１ runs", S141, TAGS, ("S141",)),
    ("r3 I1", "clarification", "note", "Fans per S141.", S141, TAGS, ("S141",)),
    ("r3 I1", "clarification", "note", "(S141; I3).", ("S141", "I3"), TAGS, ("S141", "I3")),
    ("r3 I1", "clarification", "note", "Fans (per S141, see Q4A) run", ("S141", "Q4A"), TAGS, ("S141", "Q4A")),
    ("r3 I1", "clarification", "note", "Fans refer to S141 and I3.", ("S141", "I3"), TAGS, ("S141", "I3")),
    ("r3 I2", "clarification", "note", "Damper [S999; M-101] closes.", S141, TAGS, ("S999",)),
    ("r3 I2", "clarification", "note", "Damper (see I3; sheet M-101) closes.", ("I3",), TAGS, ("I3",)),
    ("r3 I2", "clarification", "note", "(I3, see sheet M-101)", ("I3",), TAGS, ("I3",)),
    ("r3 I3", "clarification", "note", "duct-S141 runs", S141, TAGS, ("S141",)),
    ("r3 I3", "clarification", "note", "panel/I3 is wired", ("I3",), TAGS, ("I3",)),
    ("r3 I3", "clarification", "note", "EF-1-S141.", S141, TAGS, ("S141",)),
    ("r3 I3", "clarification", "note", "fans – S141", S141, TAGS, ("S141",)),
    ("r3 I3", "clarification", "note", "S141 – I3 – fans", ("S141", "I3"), TAGS, ("S141", "I3")),
    ("r3 I3", "clarification", "note", "P-14 or AHU-5/I512 4 per F9032 %", S141, TAGS, ("F9032",)),
    ("r3 I4", "clarification", "note", "RTU-2-I3, C2 runs", ("I3",), TAGS, ("I3", "C2")),     # joined by "," to I3
    ("r3 I4", "clarification", "note", "fan-S141, C2 runs", S141, TAGS, ("S141", "C2")),
    ("r3 I4", "clarification", "note", "(relay RTU9 RTU9-I740a,I29)", S141, TAGS, ("I740a", "I29")),
    ("r3 I5", "clarification", "note", "Fans (pump (I3) runs C7777) stop.", ("I3",), TAGS, ("I3", "C7777")),
    ("r3 I5", "clarification", "note", "(Straße-Q240 is wired to (per Q1199) F2856/FCU-7)", S141, TAGS,
     ("Q240", "Q1199", "F2856")),
    ("r3 I6", "clarification", "note", "Note: see I3.", ("I3",), TAGS, ("I3",)),
    ("r3 I6", "clarification", "note", "Note: [I3]", ("I3",), TAGS, ("I3",)),
    ("r3 I6", "clarification", "confirm", "Confirm: per I3, ownership of the panel", ("I3",), TAGS, ("I3",)),
    ("r3 I6", "clarification", "per_drawings", "Quantity per I3 drawings", ("I3",), TAGS, ("I3",)),
    ("r3 I6", "clarification", "assumed", "Assumed: per I3, two valves", ("I3",), TAGS, ("I3",)),
    ("r3 M2", "clarification", "note", "S141/EF-1", S141, TAGS, ("S141",)),
    ("r3 M2", "clarification", "note", "S141-EF-1 fan", S141, TAGS, ("S141",)),
    ("r3 M3", "clarification", "note", "I3 and see Q4A and", ("I3", "Q4A"), TAGS, ("I3", "Q4A")),
    ("r3 M3", "clarification", "note", "because of I3.", ("I3",), TAGS, ("I3",)),
]


@pytest.mark.parametrize("finding, field, kind, text, issued, tags, named", REFUSED,
                         ids=[f"{c[0]}: {c[3]!a}" for c in REFUSED])
def test_a_review_input_is_refused_at_intake_naming_its_ids(finding, field, kind, text, issued, tags, named):
    written, problems = _intake(field, kind, text, issued, tags)
    assert written is None, (finding, _stored(written, field))
    reason = " ".join(problems)
    assert WORDS in reason, problems
    said = [t for p in problems for m in re.finditer(r"source ids? (.+?): name the document", p)
            for t in m.group(1).split(", ")]
    assert said == list(named), problems                     # every token named, in text order; never a tag
    assert citations.SourceIds.of([*issued, CITED.source_id], tags).refusal(citations.label_off(kind or "note", text))


# (review finding, field, kind, text, issued ids, tags, what the intake stores)
ACCEPTED = [
    ("r1 I1", "clarification", "confirm", "Confirm: confirm F1", ("F1",), ("F1-F4",), "F1"),
    ("r1 I2", "clarification", "note", "Fan C2 serves the lab", ("C2",), ("EF-1", "C2"), "Fan C2 serves the lab"),
    ("r1 I2", "clarification", "note", "Fan C2 serves the lab", S141, TAGS, "Fan C2 serves the lab"),
    ("r1 M1", "clarification", "confirm", "**Confirm**: ownership of valves", S141, TAGS, "ownership of valves"),
    ("r1 M1", "clarification", "confirm", "Confirm - ownership of valves", S141, TAGS, "ownership of valves"),
    ("r1 M1", "what", "", "Assumed - two valves", S141, TAGS, "two valves"),
    ("r1 M1", "what", "", "Assumption-based count", S141, TAGS, "Assumption-based count"),
    ("r2 I-2", "clarification", "note", "Valves per sheet C101.", S141, TAGS, "Valves per sheet C101."),
    ("r2 m-1", "what", "", "Assumed: -20 F outdoor design", S141, TAGS, "-20 F outdoor design"),
    ("r2 m-1", "clarification", "note", "Note: -1 spare", S141, TAGS, "-1 spare"),
    ("r2 m-2", "what", "", "Assumed—two valves", S141, TAGS, "two valves"),
    ("r2 m-2", "clarification", "confirm", "Confirm—ownership of valves", S141, TAGS, "ownership of valves"),
    ("r3 C1", "clarification", "note", "sheet C101 shows the fans", S141, TAGS, "sheet C101 shows the fans"),
    ("r3 C2", "clarification", "note", "3 per S141ft", S141, TAGS, "3 per S141ft"),       # no whole token: policy
]


@pytest.mark.parametrize("finding, field, kind, text, issued, tags, stored", ACCEPTED,
                         ids=[f"{c[0]}: {c[3]!a}" for c in ACCEPTED])
def test_a_review_input_is_accepted_as_written_apart_from_its_label(finding, field, kind, text, issued, tags,
                                                                     stored):
    written, problems = _intake(field, kind, text, issued, tags)
    assert problems == [] and _stored(written, field) == stored
    assert _detector(issued, tags).refusal(stored) == ""


# ---- the renderer: no sentence rewriting; the validator reports first --------------------------------------------

@pytest.fixture(scope="module")
def job() -> Job:
    return Job.from_dict(json.loads((FIX / "sample_job.json").read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def pb():
    return load_playbook(ROOT / "playbook")


M101 = Ref("S141", "q", "M-101, Invented.pdf page 2")


def _system(clarifications=(), devices=None, tags=TAGS, count=None, no_scope_reason=None) -> System:
    device = Device("EF.d1", "controller", "DDC Controller", "Furnish and Install", "AME", "AME", "AME", Count(2),
                    (M101,))
    return System("EF", "Exhaust Fans", "Exhaust Fan", "field", (Family("Exhaust Fan", tags, count or Count(2)),),
                  devices=tuple(devices) if devices is not None else (device,),
                  clarifications=tuple(clarifications), no_scope_reason=no_scope_reason)


def _ids(job: Job) -> list:
    return [(f.system_key, f.device_id, f.severity, f.what) for f in validate(job, load_playbook(ROOT / "playbook"))
            if f.rule == RULE["ids"]]


@pytest.mark.parametrize("kind, text, printed", [
    ("note", "Note: see S141.", "**see"),                                            # r3 I6: label first, once
    ("confirm", "Confirm: Confirm: per S141, ownership of the panel", "*Confirm per , ownership of the panel"),
    ("assumed", "Assumed: per S141, two valves", "*Assumed: per , two valves"),
    ("note", "two valves[S141].", "**two valves[ ]"),                                 # r2 I-1: token only
    ("note", "Valves per S141 and S999.", "**Valves per and S999"),                  # r1 C1: S999 as written
])
def test_a_stale_text_loses_the_issued_token_only_and_never_prints_a_label_twice(job, pb, kind, text, printed):
    lines = [l.text for l in render(replace(job, systems=(_system((Clarification(kind, text),)),)), pb).lines
             if l.system_key == "EF"]
    assert lines[-1] == printed


def test_a_per_drawings_text_of_only_an_id_prints_no_line(job, pb):
    """r3 I6: "Quantity per I3 drawings" never prints "*Quantity per Quantity drawings"."""
    j = replace(job, systems=(_system((Clarification("per_drawings", "Quantity per S141 drawings"),)),))
    lines = [l.text for l in render(j, pb).lines if l.system_key == "EF"]
    assert not any("Quantity" in line or "S141" in line for line in lines), lines
    assert [s for _, _, s, w in _ids(j) if "S141" in w] == ["must_fix"]


def test_the_validator_reports_every_review_text_before_render(job):
    """r1 I4, r2 I-4, r2 m-4, r3 M3: issued ids in names, exceptions and texts are must_fix; an unissued token is a
    check."""
    j = replace(job, systems=(_system(devices=(Device("EF.d1", "controller", "Control Valve per S141",
                                                      "Furnish and Install", "AME", "AME", "AME", Count(2),
                                                      (M101,)),)),),
                exceptions=(ScopeException("EF", "Fire alarm by others per S141", ()),
                            ScopeException("EF", "Fire alarm (see S999)", ()),
                            ScopeException("EF", "because of S141.", ())))
    found = _ids(j)
    assert ("EF", "EF.d1", "must_fix", "an id is in the client text of the name of Control Valve per S141 (S141)") \
        in found
    assert ("EF", None, "must_fix", "an id is in the client text of the named exception (S141)") in found
    assert sum(1 for _, _, s, w in found if s == "must_fix" and "named exception (S141)" in w) == 2
    assert any(s == "check" and "S999" in w for _, _, s, w in found), found


def test_an_exception_of_only_an_issued_id_is_must_fix_and_never_prints_empty(job, pb):
    """r2 m-4."""
    j = replace(job, systems=(_system(),), exceptions=(ScopeException("EF", "S141", ()),))
    assert [s for _, _, s, w in _ids(j) if "S141" in w] == ["must_fix"]
    with pytest.raises(RenderError, match="no words left"):
        render(j, pb)


# ---- places, built by code for the count note (kept: lossless and deterministic) -----------------------------------

@pytest.mark.parametrize("where, place", [
    ("C101, Controls.pdf page 2", "C101"),          # r2 I-2: the ledger's own sheet form
    ("Sheet C501, Controls.pdf page 4", "C501"),    # r2 I-2: after the word sheet
    ("schedule S9", ""),                            # r1 M2: not a sheet the ledger knows
    ("S141, Invented.pdf page 3", ""),              # an issued id is never a place
])
def test_a_count_note_place_is_a_sheet_never_an_id(job, pb, where, place):
    assert citations.SourceIds.of(["S141"], ()).place(where) == place
    count = Count(5, (Ref("S5", "q", where),), (OtherCount(3, M101),))
    lines = [l.text for l in render(replace(job, systems=(_system(count=count),)), pb).lines if l.system_key == "EF"]
    assert lines[-1] == (f"*Qty. (5) per {place}; 3 per M-101." if place else "*Qty. (5); 3 per M-101."), lines
    assert not any(token in " ".join(lines) for token in ("S9", "S141"))


# ---- intake to render, the production path ------------------------------------------------------------------------

def test_a_clean_answer_passes_intake_and_render_unchanged(job, pb):
    text = "Fans EF-1 and EF-2 run with the kitchen hood; see sheet C101 and the mechanical schedule."
    written, problems = _intake("clarification", "note", text, S141)
    assert problems == [] and written.clarifications[0].text == text
    j = replace(job, systems=(replace(written, devices=_system().devices),))
    assert [l.text for l in render(j, pb).lines if l.system_key == "EF"][-1] == "**" + text.rstrip(".")
    assert _ids(j) == []
    assert _detector(S141).scan(text) == [citations.Found("C101", text.index("C101"), text.index("C101") + 4,
                                                          "sheet")]


def test_a_stray_id_is_refused_at_intake_and_a_stale_one_is_must_fix_then_taken_out_at_render(job, pb):
    written, problems = _intake("clarification", "note", "Valves per S141.", S141)
    assert written is None and "prints the source id S141" in " ".join(problems)
    stale = replace(job, systems=(_system((Clarification("note", "Valves per S141."),)),))    # a cached answer
    assert _ids(stale) == [("EF", None, "must_fix", "an id is in the client text of the note clarification (S141)")]
    assert [l.text for l in render(stale, pb).lines if l.system_key == "EF"][-1] == "**Valves per"


def test_the_review_long_texts_are_detected_in_linear_time():
    """r1 M3, r3 M1."""
    ids = _detector(("S141", "I3"))
    for text in ("Valves per S141. " * 8000, "per S141 " + "and the " * 3000 + ".", "S141" + " " * 40_000 + "x",
                 "(I3) " * 16000, "([" * 8000 + "I3" + "])" * 8000):
        start = time.perf_counter()
        assert ids.refusal(text) and "S141" not in ids.without_issued(text).replace("I3", "")
        assert time.perf_counter() - start < 1.0
