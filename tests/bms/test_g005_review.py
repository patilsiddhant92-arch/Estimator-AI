"""Review of record for G-005 (lead reviewer, 2026-10-12). Invented data only."""
from __future__ import annotations

from docx import Document

from bms.model import Count, OtherCount
from bms.render import render
from estimator.price_sheet.price_book import price_key
from estimator.text import squash

from test_g005_quantity_form import REF, SHEET_401, SHEET_601, _by_name, _device, _job, _lines, _playbook
from test_g005_generic_sections import OFF, WAGE, _proposal, _region, scope, template_doc  # noqa: F401 (fixtures)


# Task 1 (ruling 24): a line whose count differs from the block AND carries a note prints the end words first,
# then the other counts, and the price key of that full line is the device alone (the sheet finds its price).
def test_a_different_count_with_a_note_prints_total_then_counts_and_keeps_its_price_key():
    count = Count(4, (SHEET_601,), (OtherCount(2, SHEET_401),))
    device = _device("Space Temperature Sensor", 4, "UH.d1", count=count)
    line = _by_name(_lines(_job(device, count=6)), "Space Temperature Sensor")
    assert line.text.startswith("Furnish and Install Space Temperature Sensor (Qty. 4 Total) (")
    assert "4 per M-601" in line.text and "2 per M-401" in line.text
    assert line.quantity == 4 and not line.runs[0].red
    assert price_key(line.text) == price_key("Furnish and Install Space Temperature Sensor")


# Task 2 (ruling 26): the off-hours sub-bullet is a copy of the template's own PR3 paragraph (no numbering of its
# own, so the style numbers it "a." under its PR2 point), it sits between its parent and the next exclusion, and the
# exclusions keep the template's number of PR2 points.
def test_the_off_hours_sub_bullet_is_a_template_pr3_between_its_parent_and_the_next_point(scope, template_doc,
                                                                                           tmp_path):
    document = _proposal(scope, tmp_path, (OFF, WAGE))
    paragraphs = [p for p in document.paragraphs if p.text.strip()]
    texts = [squash(p.text) for p in paragraphs]
    parent = texts.index("All off-hours or overtime labor.")
    sub = paragraphs[parent + 1]
    assert sub.style.name == "PR3" and texts[parent + 1].startswith("The documents require work between")
    assert paragraphs[parent + 2].style.name == "PR2"
    assert texts[parent + 2] == "All temporary heating or cooling."
    assert sub._p.pPr is None or sub._p.pPr.numPr is None
    sent_pr2 = [squash(p.text) for p in _region(document) if p.style.name == "PR2" and not p.text.strip().startswith("Any demolition work not")]
    template_pr2 = [squash(p.text) for p in _region(template_doc) if p.style.name == "PR2" and not p.text.strip().startswith("Any demolition work not")]
    assert sent_pr2 == template_pr2
