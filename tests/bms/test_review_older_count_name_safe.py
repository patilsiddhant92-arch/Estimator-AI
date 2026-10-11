"""T-003 review of record (range 8ccd0b3..ce07960): an older page saved a count typed on a line as the line's new name
("2 units"); `review._read_count_name` reads it back as a count. It reads the same texts the count box reads
(`_typed_count`): a letter Python's case folding maps onto ASCII ("ſix units", "fıve ea") is words there, and a number
of more than 15 digits is words too. Before, such a name raised ValueError (its number word is in no list; Python's
int() refuses more than 4300 digits), and the whole run stopped while it read decisions.json. Invented data only: the
sample fixture."""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from bms import review
from bms.model import Decision, Job

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def job() -> Job:
    return Job.from_dict(json.loads((FIXTURES / "sample_job.json").read_text(encoding="utf-8")))


def _line(job: Job):
    return next(d for d in job.system("EF").devices if d.id == "EF.d1")


def _older_page_change(job: Job, text: str) -> Decision:
    line = _line(job)
    return Decision("EF", "change", device_id=line.id, reason=text, was=line,
                    device=dataclasses.replace(line, name=text, flag="none"))


@pytest.mark.parametrize("text", ["\u017fix units", "\u017feven ea", "f\u0131ve nos", "f\u0130ve units",
                                  "n\u0131ne pcs", "2 unit\u017f", "1" * 5000 + " units",
                                  "99999999999999999999 units"], ids=lambda text: ascii(text)[:40])
def test_a_name_the_count_box_reads_as_words_stays_a_rename_and_never_raises(job, text):
    assert review._read_count_name(_older_page_change(job, text)) == _older_page_change(job, text)
    result = review.apply_decisions(job, [_older_page_change(job, text)])
    assert _line(result).name == text                                    # a rename, as the words were saved


@pytest.mark.parametrize("text, value", [("6 units", 6), ("six units", 6), ("999999999999999 ea", 999999999999999),
                                         ("2\u00a0units", 2)])
def test_a_name_that_is_a_count_is_still_read_as_one(job, text, value):
    read = review._read_count_name(_older_page_change(job, text))
    assert read.device.name == _line(job).name and read.device.quantity.value == value
