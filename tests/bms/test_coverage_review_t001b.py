"""Review of record for hark/T-001b (invented fixtures only).

The coverage gate counts a family or unit fact as cited only by a ref with its source and quote, or by one of its own
tags; never by the bare tag prefix. The first test must pass on the branch. The probes below it describe gaps the
review found: each is a strict xfail, so it turns into a failure (and the marker goes) once the gap is closed."""
import pytest
from estimator.ledger.facts import Ledger

from bms.coverage import coverage
from bms.model import Clarification, Count, Device, Family, Job, Ref, ScopeException, System

QUOTE_FAMILY = "ZQ (equipment): 4 schedule rows"
QUOTE_UNIT = "Tags: ZQ-1 thru 4"


def _ledger():
    ledger = Ledger({"S1": "M-1, Invented.pdf page 1", "S9": "M-9, Invented.pdf page 9"})
    ledger.add("family", "ZQ", "unit", "S1", QUOTE_FAMILY, "seed")          # F1
    ledger.add("unit", "ZQ", "ZQ-1 thru 4", "S1", QUOTE_UNIT, "seed")       # F2
    return ledger


def _line(name="Status point", refs=(Ref("S9", "unrelated words", "M-9, Invented.pdf page 9"),)):
    return Device("ZQ.d1", "slot", name, "Furnish", "AME", "AME", "AME", Count(4), tuple(refs))


def _job(*, family_tags=("ZY-7",), refs=(Ref("S9", "unrelated words", "M-9, Invented.pdf page 9"),), words=(),
         name="ZQ status point"):
    """A job that says the bare prefix "ZQ" everywhere it can, and cites what `refs` and `words` say."""
    system = System("ZQ", "ZQ Units", "shape", "field", (Family("ZQ", family_tags, Count(4)),),
                    devices=(_line(name, refs),),
                    clarifications=(Clarification("note", "ZQ units are by others " + " ".join(words)),))
    return Job("j", systems=(system,), questions=("Are the ZQ units ours?",),
               exceptions=(ScopeException("ZQ", "ZQ items are by others"),))


def _ids(found):
    return [f.what.split(":")[0] for f in found]


def test_a_prefix_a_family_names_cites_nothing_but_a_ref_or_an_own_tag_does():
    # 1. The bare prefix is in the family, the system, a line, a clarification, an exception and a question: no citation.
    found = coverage(_job(), _ledger())
    assert _ids(found) == ["F1", "F2"]
    assert all((f.rule, f.severity, f.system_key, f.device_id) == ("coverage", "check", "", None) for f in found)
    # 2. A line that cites a fact by its source and quote covers that fact and no other.
    family_ref = Ref("S1", QUOTE_FAMILY, "M-1, Invented.pdf page 1")
    unit_ref = Ref("S1", QUOTE_UNIT, "M-1, Invented.pdf page 1")
    assert _ids(coverage(_job(refs=(family_ref,)), _ledger())) == ["F2"]
    assert _ids(coverage(_job(refs=(unit_ref,)), _ledger())) == ["F1"]
    assert coverage(_job(refs=(family_ref, unit_ref)), _ledger()) == []
    # 3. One of the fact's own tags (a tag of its range, not the prefix) covers the unit fact and the family on its prefix.
    assert coverage(_job(words=("ZQ-3 is excluded",)), _ledger()) == []
    assert _ids(coverage(_job(words=("ZQ-9 is excluded",)), _ledger())) == ["F1", "F2"]      # not one of its tags
    assert _ids(coverage(_job(words=("ZQ-30 is excluded",)), _ledger())) == ["F1", "F2"]     # a longer tag is not it


# ---- probes: gaps the review found. Strict xfail: each must flip (and lose its marker) when the gap is closed -------

@pytest.mark.xfail(strict=True, reason="a ref whose quote is only the bare prefix still cites a fact of its source: "
                                       "_same() takes any substring, with no minimum")
def test_probe_a_ref_that_quotes_only_the_bare_prefix_cites_nothing():
    found = coverage(_job(refs=(Ref("S1", "ZQ", "M-1, Invented.pdf page 1"),)), _ledger())
    assert _ids(found) == ["F1", "F2"]


@pytest.mark.xfail(strict=True, reason="the job's text reads a range written 'thru' only; the fact's value reads "
                                       "'through', 'to', a dash and 'ZQ-1, 2, 3' too (plan_read.expand)")
def test_probe_a_range_the_job_words_with_through_covers_its_end_tag():
    ledger = Ledger({"S1": "M-1"})
    ledger.add("unit", "ZQ", "ZQ-4", "S1", "Tags: ZQ-4", "seed")
    assert coverage(_job(words=("ZQ-1 through 4 are excluded",)), ledger) == []


@pytest.mark.xfail(strict=True, reason="a unit fact's contradicting list is part of its tags (plan_read._added_tags "
                                       "joins both lists); `_own_tags` reads the value only")
def test_probe_a_tag_only_in_the_contradicting_list_of_a_unit_fact_cites_it():
    ledger = Ledger({"S1": "M-1", "S2": "M-2"})
    fact = ledger.add("unit", "ZQ", "ZQ-1", "S1", "Tags: ZQ-1", "seed")
    ledger.contradict(fact.id, "ZQ-2 thru 3", "S2", "plans: ZQ-2 thru 3", "plans")
    assert coverage(_job(words=("ZQ-3 is excluded",)), ledger) == []


@pytest.mark.xfail(strict=True, reason="a ref that carries the fact's own id (Ref.source_id allows 'F17') is not seen "
                                       "as a citation: _cited compares with fact.source_id only")
def test_probe_a_ref_that_carries_the_fact_id_cites_the_fact():
    ledger = _ledger()
    refs = (Ref("F1", QUOTE_FAMILY, "M-1, Invented.pdf page 1"), Ref("F2", QUOTE_UNIT, "M-1, Invented.pdf page 1"))
    assert coverage(_job(refs=refs), ledger) == []
