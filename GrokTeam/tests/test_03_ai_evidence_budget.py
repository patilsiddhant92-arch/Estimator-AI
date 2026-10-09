"""Bug 3 (ai_evidence.py NOTES_LIMIT / SPEC_LIMIT, 12,000 characters): the notes and spec blocks take entries in
dossier order until the budget is spent, so a short note that names the system's own tag but comes late in the
dossier is dropped behind pages of passages that only use the general phrase ("exhaust fan"). The fix ranks
entries: a passage the planner cited or one naming one of the system's tags is always kept whole; the budget
applies to the phrase-only (and integration-word) passages. Invented dossier only."""
from bms import ai_evidence
from bms.model import Count, Family, Ref, System

FILLER = "general exhaust fan requirements for the invented building " * 7       # ~420 characters, phrase only
# a key passage longer than what the budget has left once the filler has used it (the cut skips whatever no longer
# fits, so a short one would slip through by luck)
DETAIL = " Sequence detail for the invented interlock, alarms and status." * 8
NOTE = "EF-7 shall be interlocked with its motorized damper MD-7." + DETAIL
SPEC = "Provide BACnet integration of EF-7 fan status and alarm." + DETAIL


def _dossier(n_filler=40):
    lines = ["== 7. NOTES ==", "--- M-001, Invented.pdf page 1 ---"]
    lines += [f"[N{i}] {FILLER}" for i in range(1, n_filler + 1)]
    lines += [f"[N900] {NOTE}"]
    lines += ["== 8. CONTROLS SPECIFICATION ==", "--- 23 09 00, Invented Specs.pdf page 2 ---"]
    lines += [f"[P{i}] {FILLER} integrate over BACnet." for i in range(1, n_filler + 1)]
    lines += [f"[P900] {SPEC}"]
    return "\n".join(lines) + "\n"


def _system(control="packaged", cited=()):
    refs = tuple(Ref(sid, "invented quote", "M-001, Invented.pdf page 1") for sid in cited)
    return System("EF", "Exhaust Fans", "Exhaust Fan", control,
                  (Family("Exhaust Fan", ("EF-7",), Count(1, refs)),))


def _evidence(system, text=None):
    return ai_evidence.evidence(system, text or _dossier(), {}, {}, ())


def _ids(evidence):
    return ai_evidence.cited_ids(evidence)


def test_a_late_note_naming_the_system_s_tag_is_kept():
    assert "N900" in _ids(_evidence(_system()))


def test_a_late_spec_passage_naming_the_system_s_tag_is_kept():
    assert "P900" in _ids(_evidence(_system()))


def test_kept_entries_are_whole():
    ev = _evidence(_system())
    assert f"[N900] {NOTE}" in ev
    assert f"[P900] {SPEC}" in ev


# ---- negative cases: these pass before and after the patch -----------------------------------------------------

def test_phrase_only_notes_are_still_held_to_the_budget():
    ev = _evidence(_system())
    given = [sid for sid in _ids(ev) if sid.startswith("N") and sid != "N900"]
    assert 0 < len(given) < 40
    assert sum(len(f"[{sid}] {FILLER}") for sid in given) <= ai_evidence.NOTES_LIMIT
    assert "cut at" in ev


def test_a_cited_late_note_is_given():
    assert "N40" in _ids(_evidence(_system(cited=("N40",))))


def test_a_small_dossier_gives_everything_and_says_no_cut():
    ev = _evidence(_system(), _dossier(n_filler=3))
    assert {"N1", "N2", "N3", "N900", "P1", "P2", "P3", "P900"} <= _ids(ev)
    assert "cut at" not in ev
