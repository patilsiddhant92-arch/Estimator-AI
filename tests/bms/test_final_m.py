"""FINAL-M (the concerns of FINAL-L): four more disguises of an issued id, and one detection copy rule for the tags.

- (1) A zero-width run right after an id ("S141", U+200B, "per") is a token boundary in the detection copy, as one
  before it already is; inside an id it still glues, and so does one before a single suffix letter ("S141", U+200B,
  "A" reads "S141A", as ASCII "S141A" does).
- (2) A tag is read on the same detection copy as the scanner reads text (look-alikes, digits, zero-width runs),
  except that a soft hyphen in a tag is a separator, never glue ("S", U+00AD, "1" protects nothing, as before). The
  invariant: every token the scanner reads in a tag's own text is a token the tag reader produced, and (no range,
  no soft hyphen) the other way round.
- (3) A decimal digit of another script ("S", Arabic-Indic 1 4 1) reads as its ASCII digit.
- (4) The Latin, Cherokee and Lisu look-alikes of the id letters I, S, C, F, M and Q that NFKC leaves alone (small
  capitals, the Latin iota and the dental click as I or 1) read as ASCII.

Every probe goes through the real intake (`ai._check_system`), the validator and the renderer on one job (the
reviewer's `_verdicts`, the render column read by the eye). Tests named `test_guard_...` pin behaviour unchanged from
rebuild 1c45bed (they pass there); every other test fails there. Invented fixture only."""
from __future__ import annotations

import random
import re
import time
import unicodedata
from dataclasses import replace

import pytest

from bms import ai
from bms.citations import SourceIds, job_ids, job_sheets, job_tags, tag_tokens
from bms.render import render
from bms.validate import RULE, validate

from test_review_final3 import SAMPLE, ZERO_WIDTH, _job
from test_review_final6_ids import ACCEPTED, REFUSED, SOURCE, _job_with, _verdicts

ZW = "\u200b"
# the test's own reading of a look-alike (an oracle written apart from the detector's tables)
LOOK = {"\u0405": "S", "\u0455": "s", "\u03f9": "C", "\u0421": "C", "\u0406": "I", "\u039f": "0",
        "\ua731": "S", "\u1d04": "C", "\ua730": "F", "\u1d0d": "M", "\ua7af": "Q", "\u026a": "I", "\ua7ae": "I",
        "\u13da": "S", "\u13df": "C", "\u13b7": "M", "\ua4e2": "S", "\ua4da": "C", "\ua4dd": "F", "\ua4df": "M",
        "\u01c0": "1", "\u0196": "1", "\u0131": "1"}


def _seen(text: str) -> str:
    """What the eye reads: look-alikes as ASCII, zero-width characters out, NFKC, any digit as its ASCII digit."""
    text = unicodedata.normalize("NFKC", "".join(LOOK.get(c, c) for c in text if c not in ZERO_WIDTH))
    return "".join(str(unicodedata.digit(c)) if not c.isascii() and unicodedata.digit(c, None) is not None else c
                   for c in text)


def _ef_printed(job) -> str:
    return " | ".join(l.text for l in render(job, SAMPLE).lines if l.system_key == "EF")


def _shown(job, token: str) -> bool:
    """`token` reads in EF's printed lines to the eye, glued to a word or not."""
    return re.search(rf"{re.escape(token)}(?![0-9])", _seen(_ef_printed(job)), re.IGNORECASE) is not None


def _disguised(kind, probe, token, source=SOURCE):
    intake, validator, _ = _verdicts(kind, probe, token, source)
    return intake, validator, "prints" if _shown(_job_with(kind, probe, source), token) else "cut"


# ---- the probe table: 38 disguised forms of an issued id --------------------------------------------------------

PROBES = [
    # (1) a zero-width run right after the id
    ("text", "Valves per S141\u200bper.", "S141"),
    ("text", "Valves per S141\u2060now.", "S141"),
    ("text", "Valves per S141\ufeffnow.", "S141"),
    ("text", "Valves per S141\u00adnow.", "S141"),                     # a soft hyphen
    ("text", "Valves per S141\u200c\u200dnow.", "S141"),               # a run of two
    ("text", "Valves per\u200bS141\u200bper.", "S141"),                # both sides
    ("text", "Valves per C101\u200bper sheet.", "C101"),
    ("text", "Valves per Q2\u200bvalves.", "Q2"),
    # (3) decimal digits of other scripts
    ("text", "Valves per S\u0661\u0664\u0661.", "S141"),               # Arabic-Indic
    ("text", "Valves per S\u0967\u096a\u0967.", "S141"),               # Devanagari
    ("text", "Valves per C\u06f1\u06f0\u06f1.", "C101"),               # extended Arabic-Indic
    ("text", "Valves per F\uff11\u0660\u0661.", "F101"),               # full-width and Arabic-Indic mixed
    ("text", "Valves per S\u09e7\u09ea\u09e7.", "S141"),               # Bengali
    ("text", "Valves per S\u2776\u2463\u2776.", "S141"),               # dingbat circled one, circled four
    # (4) Latin, Cherokee and Lisu look-alikes of the id letters
    ("text", "Valves per \ua731141.", "S141"),                         # small capital S
    ("text", "Valves per \u1d04101.", "C101"),                         # small capital C
    ("text", "Valves per \ua730101.", "F101"),                         # small capital F
    ("text", "Valves per \ua7af2.", "Q2"),                             # small capital Q
    ("text", "Valves per \u026a1.", "I1"),                             # small capital I
    ("text", "Valves per \ua7ae1.", "I1"),                             # capital small capital I
    ("text", "Valves per \u13da141.", "S141"),                         # Cherokee DU
    ("text", "Valves per \u13df101.", "C101"),                         # Cherokee TLI
    ("text", "Valves per \ua4e2141.", "S141"),                         # Lisu SA
    ("text", "Valves per \ua4dd101.", "F101"),                         # Lisu TSA
    ("text", "Valves per S14\u01c0.", "S141"),                         # dental click for a one
    ("text", "Valves per S14\u0196.", "S141"),                         # Latin iota for a one
    # all at once
    ("text", "Valves per \ua731\u0661\u0664\u0661\u200bper.", "S141"),
    # a device name
    ("name", "Valve per S141\u200bper", "S141"),
    ("name", "Valve per S\u0661\u0664\u0661", "S141"),
    ("name", "Valve per \ua731141", "S141"),
    # a typed where (its place is the quantity note)
    ("where", "Valve schedule, S141\u200bper", "S141"),
    ("where", "Valve schedule, S\u0661\u0664\u0661", "S141"),
    ("where", "\ua731141, Structural.pdf page 3", "S141"),
    ("where", "S141\u200bper, Structural.pdf page 3", "S141"),
    ("where", "S\u0661\u0664\u0661, Structural.pdf page 3", "S141"),
    ("where", "Structural.pdf page 3, \u13df101", "C101"),
    # a device ref's own where
    ("refwhere", "Valve schedule, S141\u200bper", "S141"),
    ("refwhere", "\u1d04101, Structural.pdf page 3", "C101"),
]


@pytest.mark.parametrize("kind, probe, token", PROBES, ids=[f"{p[0]}-{n}" for n, p in enumerate(PROBES)])
def test_a_disguised_issued_id_is_refused_must_fix_and_cut(kind, probe, token):
    job = _job_with(kind, probe)
    assert token.upper() in {i.upper() for i in job_ids(job)}
    assert _disguised(kind, probe, token) == REFUSED


@pytest.mark.parametrize("where", [p[1] for p in PROBES if p[0] == "where" and not p[1].startswith("Valve schedule")])
def test_a_disguised_id_never_shows_in_the_quantity_note(where):
    job = _job_with("where", where)
    note = " ".join(l.text for l in render(job, SAMPLE).lines if l.system_key == "EF" and "Qty. " in l.text)
    assert not re.search(r"[SQIFC]\d", _seen(note), re.IGNORECASE), note


def test_guard_the_probe_table_holds_at_least_thirty_forms():
    assert len(PROBES) >= 30 and len({p[:2] for p in PROBES}) == len(PROBES)


@pytest.mark.parametrize("where, sheet", [
    ("\u0405\u0662\u0660\u0661, Structural.pdf page 3", "S201"),       # a disguised source sheet
    ("\ua731\u0662\u0660\u0662, Structural.pdf page 3", "S202"),
    ("Sheet \u1d0d-101, Drawings.pdf page 2", "M-101"),                 # a small capital M in a plain sheet
])
def test_a_disguised_sheet_in_a_where_prints_as_its_ascii_sheet(where, sheet):
    assert _verdicts("where", where, sheet) == ACCEPTED
    note = " ".join(l.text for l in render(_job_with("where", where), SAMPLE).lines
                    if l.system_key == "EF" and "Qty. " in l.text)
    assert sheet in note and note.isascii(), note


# ---- the renderer cuts the original characters ---------------------------------------------------------------

def test_the_renderer_cuts_the_original_characters_of_the_new_disguises():
    ids = SourceIds.of(["S141", "C101"])
    found = ids.scan("per S141" + ZW + "per")
    assert [(f.token, f.start, f.end, f.kind) for f in found] == [("S141", 4, 8, "issued")]
    found = ids.scan("per S\u0661\u0664\u0661 now")
    assert [(f.token, f.start, f.end, f.kind) for f in found] == [("S141", 4, 8, "issued")]
    found = ids.scan("per\u200b\ua731141\u2060per")
    assert [(f.token, f.start, f.end, f.kind) for f in found] == [("S141", 4, 8, "issued")]
    assert ids.without_issued("Valves per S\u0661\u0664\u0661 now.") == "Valves per now."
    assert ids.without_issued("Valves per \u13df101 now.") == "Valves per now."
    cut = ids.without_issued("Valves per S141" + ZW + "per now.")
    assert "S141" not in cut and cut.startswith("Valves per ") and cut.endswith("per now.")


# ---- what stays as it was --------------------------------------------------------------------------------------

@pytest.mark.parametrize("text, token", [
    ("Valves per S" + ZW + "141.", "S141"),      # zero-width inside the id: glued, read whole
    ("Valves per S14" + ZW + "1.", "S141"),
    ("Valves per S141" + ZW + "5.", "S1415"),    # a digit after the run: one number
    ("Valves per S141" + ZW + "A.", "S141A"),    # a single suffix letter glues, as ASCII "S141A" reads
])
def test_guard_a_zero_width_between_digits_or_before_a_suffix_still_glues(text, token):
    assert [f.token.upper() for f in SourceIds.of().scan(text)] == [token]


@pytest.mark.parametrize("text", [
    "Valves per S141" + ZW + "A.",             # a single suffix letter glues: "S141A", as in ASCII
    "Valves per S141" + ZW + "a now.",
    "Valves at 20" + ZW + "psi.",
    "Room \u0661\u0660\u0661 has a sensor.",   # digits of another script with no id letter
    "\u0915\u092e\u0930\u093e \u0967\u0966\u0967.",
    "Fan \u0262-1 serves the lab.",            # a small capital G is no id letter
    "Valves at 20 \u00b5A.",
])
def test_guard_honest_text_names_no_issued_id(text):
    assert SourceIds.of(["S141", "C101", "S1"]).refusal(text) == ""


@pytest.mark.parametrize("kind, probe, token", [
    ("text", "Valves per sheet S201.", "S201"),
    ("text", "Fan EF-1 serves the lab.", "EF-1"),
    ("where", "S201, Structural.pdf page 3", "S201"),
    ("name", "Valve sheets M-101 and S201", "S201"),
])
def test_guard_honest_ascii_forms_are_unchanged(kind, probe, token):
    assert _verdicts(kind, probe, token) == ACCEPTED


@pytest.mark.parametrize("probe", ["Valves per \u02e2141.", "Valves per \u01311.", "Valves per \uff33141."])
def test_guard_forms_nfkc_or_the_case_fold_already_read_stay_refused(probe):
    token = "I1" if "\u0131" in probe else "S141"
    assert _verdicts("text", probe, token) == REFUSED


# ---- (2) tags read on the same detection copy ------------------------------------------------------------------

@pytest.mark.parametrize("tag, protected", [
    ("FCU-\u0405141", {"S141"}),                  # Cyrillic DZE
    ("AHU-\ua731141", {"S141"}),                  # small capital S
    ("FCU-S\u0661\u0664", {"S14"}),               # Arabic-Indic digits
    ("EF-S2\u041e1", {"S201"}),                   # Cyrillic O for a zero
    ("Fan \u13df101", {"C101"}),                  # Cherokee C
    ("S" + ZW + "1", {"S1"}),                     # the scanner reads S1 here, so the tag protects S1
])
def test_a_tag_is_read_on_the_scanners_detection_copy(tag, protected):
    assert tag_tokens([tag]) == frozenset(protected)
    assert SourceIds.of(sorted(protected), tags=[tag]).refusal(tag) == ""


@pytest.mark.parametrize("tag, protected", [
    ("S\u00ad1", set()),                          # a soft hyphen in a tag is a separator (detect2 ruling)
    ("F\u00ad1 thru 4", set()),
    ("AHU\u00adS1", {"S1"}),
    ("S-" + ZW + "1", set()),
    ("S1\u00ad4", {"S1"}),                        # as rebuild reads it: no range S1 to S4
    ("AHU" + ZW + "S12" + ZW + "now", {"S12"}),
    ("AHU-S1", {"S1"}),
    ("F1-F4", {"F1", "F2", "F3", "F4"}),
])
def test_guard_the_tag_readers_hyphen_handling_is_kept(tag, protected):
    assert tag_tokens([tag]) == frozenset(protected)


_PIECES = ["S", "F", "C", "q", "1", "4", "0", "-", "_", " ", "AHU", "per", ZW, "\u2060", "\u00ad",
           "\u0405", "\ua731", "\u1d04", "\u041e", "\u0406", "\u0661", "\u0664", "\u01c0", "\uff13", "/", "."]


# a tag stands in text as a word: a separator (or the text's edge) on each side
_LEFT = ["", " ", ", ", "per ", "(", "Fan ", "sheet ", "S4 and "]
_RIGHT = ["", " ", ", ", ")", ".", " per", "; S4", " and \u0405141"]


def _scanner_tokens(text: str) -> set[str]:
    return {f.token.upper() for f in SourceIds.of().scan(text)}


def _soft_hyphen_glue(tag: str) -> bool:
    """A soft hyphen between a letter or digit and a digit (zero-width characters not counted): the one place the
    tag reader keeps its hyphen reading ("S", U+00AD, "1" is "S-1") where the scanner reads glue ("S1")."""
    seen = [c for c in tag if c not in ZERO_WIDTH or c == "\u00ad"]
    for n, c in enumerate(seen):
        if c == "\u00ad":
            before = next((b for b in reversed(seen[:n]) if b != "\u00ad"), "")
            after = next((a for a in seen[n + 1:] if a != "\u00ad"), "")
            if before.isalnum() and after and unicodedata.digit(unicodedata.normalize("NFKC", after)[0], None)                     is not None:
                return True
    return False


def test_every_token_the_scanner_reads_in_a_tag_is_one_the_tag_reader_produced():
    rng = random.Random(20261007)
    for _ in range(4_000):
        tag = "".join(rng.choice(_PIECES) for _ in range(rng.randint(1, 9)))
        protected = tag_tokens([tag])
        read = _scanner_tokens(tag)
        if not _soft_hyphen_glue(tag):
            # the scanner reads the written tag as all protected
            assert read <= protected, (ascii(tag), read, protected)
            assert SourceIds.of(sorted(read), tags=[tag]).refusal(tag) == "", ascii(tag)
            if "-" not in tag:
                # no range: the tag reader protects exactly what the scanner reads
                assert protected == read, (ascii(tag), read, protected)
        # in any text where the tag stands as a word: a token the scanner reads wholly inside the tag is protected
        left, right = rng.choice(_LEFT), rng.choice(_RIGHT)
        text = left + tag + right
        start, end = len(left), len(left) + len(tag)
        inside = {f.token.upper() for f in SourceIds.of().scan(text) if start <= f.start and f.end <= end}
        if not _soft_hyphen_glue(tag):
            assert inside <= protected, (ascii(text), inside, protected)
        assert {f.token.upper() for f in SourceIds.of(tags=[tag]).scan(text)
                if start <= f.start and f.end <= end} <= inside - protected, ascii(text)


def test_guard_a_tag_glued_by_a_soft_hyphen_still_protects_nothing():
    """The open asymmetry: the tag "S", U+00AD, "1" protects nothing (the tag reader's hyphen reading), while the
    scanner reads the same text as S1; with S1 issued, that text is refused (the safe side)."""
    tag = "S\u00ad1"
    assert tag_tokens([tag]) == frozenset()
    assert SourceIds.of(["S1"], tags=[tag]).refusal("Serves " + tag + ".")


def test_a_tag_written_with_a_look_alike_is_protected_through_intake_validate_and_render():
    for text in ("Serves FCU-S141.", "Serves FCU-\u0405141."):
        job = _with_note(replace(_job(tag="FCU-\u0405141"), source_sheets=SOURCE), text)
        system = job.system("EF")
        written, _ = ai._check_system(system.to_dict(), system, None, frozenset(job_ids(job)), (), (), [],
                                      job_tags(job), job_ids(job), tuple(job_sheets(job)), tuple(job.source_sheets))
        severities = [f.severity for f in validate(job, SAMPLE) if f.rule == RULE["ids"] and f.system_key == "EF"]
        assert written is not None, text
        assert "must_fix" not in severities, text
        assert "FCU-S141" in _seen(_ef_printed(job)), text


def _with_note(job, text):
    from test_review_final3 import _with_note as put
    return put(job, text)


# ---- linear time ---------------------------------------------------------------------------------------------

def test_the_detection_copy_stays_linear_on_the_new_forms():
    ids = SourceIds.of(["S141"])
    piece = "per S141" + ZW + "per S\u0661\u0664\u0661 \ua731141 "

    def best(text):
        times = []
        for _ in range(3):
            start = time.perf_counter()
            ids.scan(text)
            tag_tokens([text])
            times.append(time.perf_counter() - start)
        return min(times)

    one, many = best(piece * 500), best(piece * 10_000)     # 20 times the text: linear is about 20 times the time
    assert len(ids.scan(piece * 3)) == 9
    assert many < max(one, 0.005) * 60
