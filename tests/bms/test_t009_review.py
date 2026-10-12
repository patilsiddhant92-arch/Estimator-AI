"""Reviewer tests for T-009 task 2 (ruling 22). Invented fixtures only."""
from __future__ import annotations

import pytest
from docx import Document

from estimator.proposal import layout
from estimator.proposal.read import read_named_exceptions
from estimator.scope import Block, Item, Run
from estimator.text import squash
from bms.render import render
from test_t009_demolition import (_template, _with_demolition, _without_demolition, _write,  # noqa: F401
                                            job, playbook)


@pytest.mark.parametrize("with_block", [True, False])
def test_a_written_proposal_reads_back_its_named_exception_in_both_cases(job, playbook, tmp_path, with_block):
    base = _with_demolition(job) if with_block else _without_demolition(job)
    scope = render(base, playbook).scope.model_copy(update={"named_exceptions": ("Any invented exception.",)})
    assert read_named_exceptions(_write(scope, tmp_path), _template()) == ("Any invented exception.",)


def test_a_scope_line_with_the_dropped_text_outside_the_exclusions_is_kept(job, playbook, tmp_path):
    # no Demolition Scope block, so the specific exclusion is dropped; a scope line with the same words must stay
    scope = render(_without_demolition(job), playbook).scope
    block = Block(header="Invented Block", numbered=False,
                  items=(Item(kind="line", depth=1, runs=(Run(text=layout.DEMOLITION_SPECIFIC),)),))
    scope = scope.model_copy(update={"blocks": scope.blocks + (block,)})
    texts = [squash(p.text) for p in _write(scope, tmp_path).paragraphs]
    assert texts.count(squash(layout.DEMOLITION_SPECIFIC)) == 1


# --- task 1 (ruling 21), reviewer tests -----------------------------------------------------------------------------
import dataclasses as _dc

from test_t009_plan_count import SENSOR, SEQUENCE, VERIFY, _fcu_notes, _line, _printed, _sequence_writer, _step, \
    planned  # noqa: F401,E402
from bms.model import Count, Decision, Job as _Job  # noqa: E402
from bms.review import apply_decisions  # noqa: E402
from bms.run import _plan_counts  # noqa: E402
import takeoff_fixture as fx  # noqa: E402


def test_the_verify_line_and_the_printed_count_survive_the_job_file(planned):
    once = _step(_sequence_writer(planned))
    again = _Job.from_json(once.to_json())
    assert VERIFY in _fcu_notes(again)
    assert _printed(again).text.startswith("Qty (30)")


class _Reading:
    devices = fx.reading().devices


def _again(job, decisions=(), before=None):
    """The run's re-application after a count rewrite or a revise (`run._plan_counts`)."""
    return _plan_counts(job, _Reading(), fx.dossier(), None, decisions, before)


def _rewritten(job, quantity):
    systems = tuple(_dc.replace(s, devices=tuple(_dc.replace(d, quantity=quantity) if d.id == SENSOR else d
                                                 for d in s.devices)) for s in job.systems)
    return _dc.replace(job, systems=systems)


def test_a_later_rewrite_back_to_the_sequence_number_still_shows_the_plan_count(planned):
    # the revise (or the count rewrite of the decisions step) copies the family count back (55); the run applies the
    # step again, so the plan count 30 prints with its "*Verify" line, and the set-asides say what prints
    once = _step(_sequence_writer(planned))
    revised = _again(_rewritten(once, Count(55, (SEQUENCE,))))
    printed = " ".join([_printed(revised).text, *_fcu_notes(revised)])
    assert "30" in printed
    assert _printed(revised).text.startswith("Qty (30)") and VERIFY in _fcu_notes(revised)
    mine = [a for a in revised.set_aside if a.reason == "plan count prints" and a.family == SENSOR]
    assert mine and all("the plan count 30 of" in a.note and a.value == 55 for a in mine)
    assert revised.set_aside == once.set_aside            # the same, true set-asides: none doubled, none stale
    assert _again(revised) == revised                     # idempotent


def test_a_revise_that_removes_the_line_leaves_no_plan_count_set_aside(planned):
    once = _step(_sequence_writer(planned))
    systems = tuple(_dc.replace(s, devices=tuple(d for d in s.devices if d.id != SENSOR)) for s in once.systems)
    after = _again(_dc.replace(once, systems=systems))
    assert not [a for a in after.set_aside if a.reason == "plan count prints"]


def test_a_count_the_estimator_typed_is_not_reduced_again_after_the_revise(planned):
    once = _step(_sequence_writer(planned))
    typed_line = _dc.replace(_line(once), quantity=Count(33, (SEQUENCE,)))
    decision = Decision("FCU", "change", device_id=SENSOR, device=typed_line, was=_line(once))
    after = _again(apply_decisions(once, [decision]), [decision], once)
    assert _line(after).quantity.value == 33
    assert not any(n.startswith("*Verify") for n in _fcu_notes(after))
    assert not [a for a in after.set_aside if a.reason == "plan count prints" and a.family == SENSOR]
