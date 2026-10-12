"""G-005 review of record, minor finding 3 (lead, 2026-10-12): the exclusions reader skips only the sub-bullets the
app wrote (style PR3 and one of the writer's own sentences). A line the estimator typed, in PR3 or PR2 style, red or
not, is a named exception and is read. Invented data only."""
from __future__ import annotations

import copy

import pytest
from docx.shared import RGBColor
from docx.text.paragraph import Paragraph

from estimator.__main__ import PROPOSAL_TEMPLATE
from estimator.proposal import layout
from estimator.proposal.read import read_named_exceptions
from estimator.proposal.write import _replace_text
from estimator.text import squash

from test_g005_generic_sections import OFF, OFF_NO_HOURS, WAGE, _proposal, scope  # noqa: F401 (scope is a fixture)

TYPED = "Any invented work the estimator leaves out after the review."
LOOKS_LIKE_IT = "The documents require off-hours work to be left out."     # the writer's words, not its sentence


def _typed_last_exclusion(document, text, style, red):
    """A line the estimator typed after the standard exclusions: a copy of the last point, in `style`."""
    paragraphs = document.paragraphs
    base = next(i for i, p in enumerate(paragraphs) if squash(p.text).startswith(layout.BASE_PRICE))
    last = next(p for p in reversed(paragraphs[:base]) if p.text.strip())
    clone = copy.deepcopy(last._p)
    last._p.addnext(clone)
    added = Paragraph(clone, last._parent)
    _replace_text(added, text)
    added.style = document.styles[style]
    if red:
        for run in added.runs:
            run.font.color.rgb = RGBColor(0xFF, 0x00, 0x00)
    return added


def _writers_sub_bullet(document):
    return next(p for p in document.paragraphs if squash(p.text).startswith("The documents require"))


@pytest.mark.parametrize("conditions", [(OFF,), (OFF_NO_HOURS,), (OFF, WAGE)])
def test_every_sentence_the_writer_adds_under_an_exclusion_is_skipped(scope, tmp_path, conditions):
    document = _proposal(scope, tmp_path, conditions)
    assert _writers_sub_bullet(document).style.name == "PR3"          # it is in the proposal
    assert read_named_exceptions(document, PROPOSAL_TEMPLATE) == ()


def test_a_proposal_written_before_the_sentence_had_its_full_stop_still_reads(scope, tmp_path):
    document = _proposal(scope, tmp_path, (OFF,))
    sub_bullet = _writers_sub_bullet(document)
    assert squash(sub_bullet.text).endswith(".")
    sub_bullet.runs[0].text = sub_bullet.runs[0].text.rstrip(".")
    assert not squash(sub_bullet.text).endswith(".")
    assert read_named_exceptions(document, PROPOSAL_TEMPLATE) == ()


@pytest.mark.parametrize("red", [True, False])
@pytest.mark.parametrize("style", ["PR3", "PR2"])
@pytest.mark.parametrize("text", [TYPED, LOOKS_LIKE_IT])
def test_a_line_the_estimator_typed_is_read_beside_the_sub_bullets_the_writer_added(scope, tmp_path, text, style, red):
    document = _proposal(scope, tmp_path, (OFF, WAGE))
    added = _typed_last_exclusion(document, text, style, red)
    assert added.style.name == style
    assert read_named_exceptions(document, PROPOSAL_TEMPLATE) == (text,)
