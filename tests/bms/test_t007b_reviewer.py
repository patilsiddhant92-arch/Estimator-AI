"""Reviewer of record, T-007b (2026-10-12): two dropped placement numbers of one family, each split by sheet.
Invented fixture only (tests/bms/fixtures/takeoff via takeoff_fixture)."""
from __future__ import annotations

import test_takeoff as tt
from bms import takeoff
from bms.model import Ref


def _entries():
    attic = Ref(source_id="S5", quote="plan placements 21", where="M-401")
    levels = Ref(source_id="S6", quote="plan placements 8", where="M-201")
    return [(21, (attic,)), (8, (levels,))]


BREAKDOWN = {21: "M-401 5; M-402 5; M-403 3; M-404 3; MD-401 5", 8: "M-201 3; MD-201 5"}


def test_two_dropped_numbers_with_different_reasons_record_two_set_asides():
    register = tt._register()
    again = takeoff.recount(tt.fx.catalogue(), register)
    kept, aside = takeoff.admit("AHU", _entries()[:1], register, again, BREAKDOWN)
    assert sorted((a.reason, a.value) for a in aside) == [("demolition sheet", 5), ("part plan of one area", 16)]
    assert max(n for n, _ in kept) == 5


def test_each_dropped_number_keeps_all_its_parts_when_a_part_repeats_value_and_reason():
    """21 (attic) and 8 (Level 1) both drop a "demolition sheet" 5, on different sheets (MD-401, MD-201). Each dropped
    number's parts must add up to it, so MD-201's 5 must be recorded too."""
    register = tt._register()
    again = takeoff.recount(tt.fx.catalogue(), register)
    kept, aside = takeoff.admit("AHU", _entries(), register, again, BREAKDOWN)
    by_source = {}
    for a in aside:
        by_source.setdefault(a.ref.source_id, []).append(a.value)
    assert sum(by_source.get("S5", [])) == 21
    assert sum(by_source.get("S6", [])) == 8, [(a.ref.source_id, a.reason, a.value, a.note) for a in aside]
    assert any("MD-201" in a.note for a in aside)
