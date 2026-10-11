"""The review page lists the coverage gate's findings (a fact the ledger read that nothing in the job cites) in a group
of its own, "Not cited in the job", with each fact's place and quote. They are no questions: no card, no button, no
decision, and they never use the room of the top questions. Invented data only."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from estimator.ledger.facts import Ledger

from bms import review
from bms.coverage import coverage
from bms.model import Finding, Job
from bms.status import _findings

FIXTURES = Path(__file__).resolve().parent / "fixtures"
GROUP = "Not cited in the job"


@pytest.fixture
def job() -> Job:
    return Job.from_dict(json.loads((FIXTURES / "sample_job.json").read_text(encoding="utf-8")))


def _page(job, findings, tmp_path) -> str:
    return review.review_page(job, findings, tmp_path).read_text(encoding="utf-8")


def _uncited(job: Job, *subjects: str) -> list[Finding]:
    """What the real gate says about invented facts the sample job never names."""
    ledger = Ledger({"S1": "M-1, Plans.pdf page 2 (x)", "S2": "Spec 23 09 00"})
    for n, subject in enumerate(subjects, start=1):
        ledger.add("family", subject, f"{subject} thing", "S1" if n % 2 else "S2", f"{subject}-1 is shown here", "seed")
    return coverage(job, ledger)


def _group(text: str) -> str:
    """The group's own section of the page."""
    return re.search(r'<section class="card" id="not-cited"[^>]*>.*?</section>', text, re.S).group(0)


def _cards(text: str) -> int:
    return text.count('<section class="card"')


def _question_count(text: str) -> int:
    return len(re.findall(r'<div class="q[ "]', text))


def test_the_group_shows_each_facts_place_and_quote(job, tmp_path):
    found = _uncited(job, "ZZA", "ZZB")
    assert len(found) == 2
    group = _group(_page(job, found, tmp_path))
    assert f"<h2>{GROUP}</h2>" in group
    assert group.count("<li") == 2
    assert "M-1, Plans.pdf page 2" in group and "Spec 23 09 00" in group          # the places
    assert "ZZA-1 is shown here" in group and "ZZB-1 is shown here" in group      # the quotes
    assert all(f.what in group and f.fix in group for f in found)                 # each finding as the gate wrote it


def test_no_uncited_fact_gives_no_group(job, tmp_path):
    text = _page(job, [], tmp_path)
    assert GROUP not in text and "not-cited" not in text


def test_an_uncited_fact_is_no_question(job, tmp_path):
    """The same question cards and the same count in the header with and without the findings; one more section."""
    found = _uncited(job, "ZZA", "ZZB", "ZZC")
    plain, with_group = _page(job, [], tmp_path), _page(job, found, tmp_path)
    assert _question_count(with_group) == _question_count(plain) > 0
    header = re.compile(r"\d+ of \d+ question\(s\) shown")
    assert header.search(with_group).group(0) == header.search(plain).group(0)
    assert _cards(with_group) == _cards(plain) + 1
    assert 'class="q' not in _group(with_group) and "<button" not in _group(with_group)


def test_the_findings_do_not_use_the_room_of_the_top_questions(job, tmp_path):
    many = _uncited(job, *(f"ZZ{n}" for n in range(30)))
    assert len(many) == 30
    plain, text = _page(job, [], tmp_path), _page(job, many, tmp_path)
    assert (text.count('class="q"'), text.count('class="q extra"')) == (plain.count('class="q"'),
                                                                        plain.count('class="q extra"'))
    assert _group(text).count("<li") == 30


def test_the_group_names_its_rule_for_status(job, tmp_path):
    (tmp_path / "Review.html").write_text(_page(job, _uncited(job, "ZZA", "ZZB"), tmp_path), encoding="utf-8")
    assert "2 for coverage" in _findings(tmp_path / "Review.html", current=True)


def test_other_findings_are_still_questions_beside_the_group(job, tmp_path):
    other = Finding("Every line cites this job", "EF", "EF.d1", "must_fix", "no citation here", "Cite it")
    text = _page(job, [other, *_uncited(job, "ZZA")], tmp_path)
    assert "no citation here" in text.replace(_group(text), "") and "no citation here" not in _group(text)
    assert "ZZA-1 is shown here" in _group(text)


def test_the_group_text_is_escaped(job, tmp_path):
    ledger = Ledger({"S1": "M-1, Plans <b>x</b> page 2"})
    ledger.add("family", "ZZA", "thing", "S1", "<script>alert(1)</script> & ZZA-1", "seed")
    group = _group(_page(job, coverage(job, ledger), tmp_path))
    assert "<script>alert(1)</script>" not in group and "&lt;script&gt;alert(1)&lt;/script&gt; &amp; ZZA-1" in group
    assert "<b>x</b>" not in group


def test_the_page_still_saves_its_decisions_with_the_group_on_it(job, tmp_path):
    """The page's script reads only the question cards; the group has none, so it cannot break the save."""
    text = _page(job, _uncited(job, "ZZA"), tmp_path)
    assert 'querySelectorAll(".q")' in text
    assert all(json.loads(found) for found in re.findall(r'class="qdata">(.*?)</script>', text, re.S))
