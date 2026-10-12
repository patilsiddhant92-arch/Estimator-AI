"""Reviewer's test for G-004 Task 1 (uncommitted): a finding that names a flagged device at the end of a sentence
still folds that device's flag into one sub-point. Invented data only."""
from __future__ import annotations

import json
import re

from bms import review
from bms.model import Count, Device, Family, Finding, Job, Ref, System

REF = Ref("S1", "AHU row", "M-501, Invented.pdf page 6")


def _device(i: int, flag: str) -> Device:
    return Device(id=f"AHU.d{i}", slot="other_device", name=f"Point {i}", verb="Furnish and Install",
                  furnished_by="AME", installed_by="AME", wired_by="AME", quantity=Count(1, (REF,)), refs=(REF,),
                  flag=flag)


def test_an_id_at_the_end_of_a_sentence_still_folds_the_flagged_device(tmp_path):
    system = System(key="AHU", name="Air Handling Unit", shape="Air Handling Unit", control="field",
                    families=(Family("Air Handling Unit", ("AHU-1",), Count(1, (REF,))),),
                    devices=(_device(1, "none"), _device(2, "ownership")))
    finding = Finding("interlock", "AHU", "AHU.d1", "check", "AHU.d1 repeats the lines of AHU.d2.", "Remove one.")
    page = review.review_page(Job(name="Invented", systems=(system,)), (finding,), tmp_path).read_text("utf-8")
    ids = [json.loads(raw)["device_id"] for raw in re.findall(r'class="qdata">(.*?)</script>', page, re.S)]
    assert ids == ["AHU.d1"]
    assert "Who furnishes, installs or wires this line is not settled." in page
