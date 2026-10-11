"""T-005c regression tests from an invented copy of the 26-0544 proposal defects (NOTES 2026-10-11 rule 4), read from
tests/bms/fixtures/t005c_proposal.json:

- the cover header was read from the takeoff folder's own name: it now comes from the job folder that holds
  "2. Takeoffs" (Quote # before the first comma, Reference after it);
- an existing Schneider BMS printed plain: a name that is not one of AME's three prints red between *** with one red
  flag line.
Invented fixtures only."""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from bms.model import FrontEnd
from bms.render import AME_ONLY_FLAG
from estimator.proposal.write import ame_bms
from test_t005c_proposal import (_device, _front_items, _header, _paragraph, _red_text, _write, job,  # noqa: F401
                                 playbook)

FIXTURE = json.loads((Path(__file__).resolve().parent / "fixtures" / "t005c_proposal.json").read_text("utf-8"))


def _root(parts):
    return Path(*(p.replace("{job}", FIXTURE["job_folder"]) for p in parts))


# ---- the header from the job folder, never the takeoff folder -----------------------------------------------------

@pytest.mark.parametrize("parts", FIXTURE["takeoff_roots"])
def test_fixture_header_comes_from_the_job_folder_not_the_takeoff_folder(parts):
    header, flags = _header(_root(parts))
    expected = FIXTURE["expected_header"]
    assert (header.quote_number, header.reference) == (expected["quote_number"], expected["reference"])
    for text in FIXTURE["never_printed"]:
        assert text not in header.quote_number + header.reference
    assert not any("job number" in f or "project name" in f for f in flags)   # no header question


def test_fixture_header_with_no_job_folder_prints_red_placeholders_and_asks():
    header, flags = _header(_root(FIXTURE["no_job_folder_root"]))
    assert (header.quote_number, header.reference) == ("***", "***")
    assert any("job number" in f and "project name" in f for f in flags)


# ---- Schneider printed plain -------------------------------------------------------------------------------------

@pytest.mark.parametrize("name", FIXTURE["non_ame_bms"])
def test_fixture_a_schneider_bms_is_not_ames_and_gets_one_red_flag(job, playbook, name):  # noqa: F811
    assert not ame_bms(name)
    front = FrontEnd(mode="extend-existing", existing_system_name=name, devices=(_device(),))
    flags = [i for i in _front_items(job, playbook, front) if i.text == AME_ONLY_FLAG]
    assert len(flags) == 1 and flags[0].runs[0].red


@pytest.mark.parametrize("name", FIXTURE["ame_bms"])
def test_fixture_ames_own_bms_names_get_no_flag(job, playbook, name):  # noqa: F811
    assert ame_bms(name)
    front = FrontEnd(mode="extend-existing", existing_system_name=name, devices=(_device(),))
    assert not any(i.text == AME_ONLY_FLAG for i in _front_items(job, playbook, front))


def test_fixture_schneider_prints_red_between_stars_in_the_heading(job, playbook, tmp_path):  # noqa: F811
    name = FIXTURE["non_ame_bms"][0]
    front = FrontEnd(mode="extend-existing", existing_system_name=name, devices=(_device(),))
    heading = _paragraph(_write(replace(job, front_end=front), playbook, tmp_path), "Seamlessly Tie in")
    assert _red_text(heading).strip() == f"***{name}***"
