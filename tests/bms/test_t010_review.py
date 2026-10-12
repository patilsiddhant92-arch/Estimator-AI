"""Reviewer-of-record tests for T-010 (2026-10-12): one per task. Invented fixtures only: no job text."""
from __future__ import annotations

import re

import test_t010_contradictions as con
import test_t010_ownership as own
from bms import ai
from bms.model import Count, Family, OtherCount
from bms.render import render


# ---- task 1 (ruling 23) ------------------------------------------------------------------------------------------

def test_factory_installed_alone_does_not_move_the_furnishing_and_a_provided_by_maker_sequence_does():
    """A sequence passage that gives only the mounting to the factory leaves "Furnish and Wire" AME's; one that says
    the unit maker provides the device moves it to "Wire ... (Furnished by Unit Mfr.)" and refuses "Furnish and
    Wire" with the rule's name and first sentence. Called as `_check_system` calls it (no kept ids)."""
    def problems(quote, verb, furnished):
        d = own._device("Freezestat", "freezestat", verb, [], furnished=furnished, installed="Unit Mfr.")
        d["refs"] = [{"source_id": "S1", "quote": quote, "where": "Seq of Ops, Invented.pdf page 1"}]
        return ai._freezestat_filter_problems(own._unit(), None, [d], set(), frozenset({"S1"}), own.PLAYBOOK.rules)

    mounted = "THE LOW LIMIT FREEZESTAT IS FACTORY INSTALLED AND WIRED BY THE CONTROLS CONTRACTOR"
    assert problems(mounted, "Furnish and Wire", "AME") == []
    assert problems(mounted, "Wire", "Unit Mfr.") != []
    provided = "THE LOW LIMIT FREEZESTAT IS PROVIDED BY THE INVENTED UNIT MANUFACTURER"
    (problem,) = problems(provided, "Furnish and Wire", "AME")
    assert f'"{own.AME_RULE}"' in problem and own._first_sentence(own.AME_RULE) in problem
    assert problems(provided, "Wire", "Unit Mfr.") == []


# ---- task 2 (ruling 25) ------------------------------------------------------------------------------------------

def test_a_count_and_an_owner_contest_in_one_block_print_two_red_lines_last_short_and_without_ids():
    """One block with a contested family count and a contested owner: exactly two red lines, after every black
    note, each at most 160 characters, no source id, every number of the bracket kept, and both in draft.lines."""
    from bms.playbook import load_playbook
    pb = load_playbook(con.ROOT / "playbook")
    count = Count(value=55, sources=(con.P901,), others=(OtherCount(1, con.ROWS), OtherCount(7, con.P902)))
    s = con.system(families=(Family("Fan Coil Unit", ("FC-1",), count),),
                   devices=(con.device(), con.owner_device()))
    draft = render(con.job(s), pb)
    (block,) = [b for b in draft.scope.blocks if b.items]
    items = con.notes(block)
    reds = [t for t, red in items if red]
    assert len(reds) == 2, reds
    assert [red for _, red in items][-2:] == [True, True]
    assert all(len(t) <= 160 and t.startswith("*") and not re.search(r"\[S\d+\]|\bS\d\b", t) for t in reds)
    (counts,) = [t for t in reds if "counts differ" in t]
    assert con.numbers(counts) == [55, 7, 1]
    (owner,) = [t for t in reds if "Freezestat" in t]
    assert "AME" in owner and "Unit Mfr." in owner
    assert not [t for t, red in items if not red and t.startswith("*Assumed") and "Freezestat" in t]
    traced = con.traced_notes(draft)
    assert all(t in traced for t in reds)
