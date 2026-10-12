"""G-004 Task 1: one review question per family, with a sub-point for each old question. Invented data only."""
from __future__ import annotations

import json
import re

from bms import review
from bms.model import Count, Decision, Device, Family, Finding, FrontEnd, Job, OtherCount, Ref, System

REF = Ref("S1", "AHU row", "M-501, Invented.pdf page 6")
OTHER = Ref("S2", "AHU rows 3", "M-601, Invented.pdf page 7")
FLAG_OWNERSHIP = "Who furnishes, installs or wires this line is not settled."


def _settled(n: int = 1) -> Count:
    return Count(n, (REF,))


def _disputed() -> Count:
    return Count(5, (REF,), (OtherCount(3, OTHER),))


def _device(i: int, flag: str = "ownership", count: Count | None = None, system: str = "AHU") -> Device:
    return Device(id=f"{system}.d{i}", slot="other_device", name=f"Point {i}", verb="Furnish and Install",
                  furnished_by="AME", installed_by="AME", wired_by="AME", quantity=count or _settled(),
                  refs=(REF,), flag=flag)


def _job(*devices: Device, families=None, name: str = "Air Handling Unit", key: str = "AHU",
         front_end: FrontEnd | None = None) -> Job:
    families = families if families is not None else (Family("Air Handling Unit", ("AHU-1",), _settled()),)
    system = System(key=key, name=name, shape="Air Handling Unit", control="field", families=families,
                    devices=devices)
    return Job(name="Invented", systems=(system,), front_end=front_end)


def _page(job: Job, findings=(), tmp_path=None) -> str:
    return review.review_page(job, findings, tmp_path).read_text(encoding="utf-8")


def _headings(page: str) -> list[str]:
    return re.findall(r"<h3>(.*?)</h3>", page)


def _groups(page: str) -> list[str]:
    return re.findall(r'<section class="group(?: extra)?">(.*?)</section>', page, re.S)


def _qdata(fragment: str) -> list[dict]:
    return [json.loads(raw) for raw in re.findall(r'class="qdata">(.*?)</script>', fragment, re.S)]


def test_one_family_with_seven_flagged_devices_is_one_group(tmp_path):
    devices = tuple(_device(i) for i in range(1, 8))
    page = _page(_job(*devices), tmp_path=tmp_path)
    assert page.count('<section class="card"') == 1
    assert _headings(page) == ["Air Handling Unit: 7 points to check"]
    assert "q1" not in _headings(page)[0]
    (group,) = _groups(page)
    data = _qdata(group)
    assert [row["device_id"] for row in data] == [f"AHU.d{i}" for i in range(1, 8)]
    assert group.count('data-act="accept"') == 7
    assert group.count('data-act="change"') == 7
    assert "1 of 1 question(s) shown" in page


def test_accept_on_one_sub_point_changes_only_that_device(tmp_path):
    job = _job(_device(1), _device(2), _device(3))
    page = _page(job, tmp_path=tmp_path)
    assert _headings(page) == ["Air Handling Unit: 3 points to check"]
    assert len(_qdata(page)) == 3
    after = review.apply_decisions(job, [Decision("AHU", "accept", device_id="AHU.d2")])
    flags = {device.id: device.flag for device in after.system("AHU").devices}
    assert flags == {"AHU.d1": "ownership", "AHU.d2": "none", "AHU.d3": "ownership"}


def test_a_finding_that_names_a_flagged_device_keeps_one_sub_point(tmp_path):
    named = Finding("interlock", "AHU", "AHU.d1", "check", "The interlock for AHU.d2 is open.", "Cite AHU.d2.")
    kept = Finding("quote", "AHU", "AHU.d23", "check", "The note names AHU.d23 only.", "Keep the note.")
    job = _job(_device(1, flag="none"), _device(2), _device(20), _device(23, flag="none"))
    page = _page(job, (named, kept), tmp_path)
    data = _qdata(page)
    assert [row["device_id"] for row in data] == ["AHU.d20", "AHU.d1", "AHU.d23"]
    a = next(block for block in _groups(page) for row in _qdata(block) if row["device_id"] == "AHU.d1")
    assert FLAG_OWNERSHIP in a
    assert "AHU.d2" not in [row["device_id"] for row in data]
    own = Finding("interlock", "AHU", "AHU.d2", "must_fix", "AHU.d2 has no citation.", "Cite it.")
    other = Finding("interlock", "AHU", "AHU.d1", "check", "See also AHU.d2.", "Check AHU.d2.")
    both = _page(_job(_device(1, flag="none"), _device(2)), (own, other), tmp_path)
    assert {row["device_id"] for row in _qdata(both)} == {"AHU.d1", "AHU.d2"}


def test_two_families_put_other_questions_in_the_system_group(tmp_path):
    families = (Family("Air Handling Unit", ("AHU-1",), _disputed()),
                Family("Energy Recovery Unit", ("ERV-1",), _disputed()))
    finding = Finding("shape", "AHU", None, "check", "The block has no tech hours.", "Set the hours.")
    page = _page(_job(_device(1), families=families, name="Air Side"), (finding,), tmp_path)
    groups = {heading: block for heading, block in zip(_headings(page), _groups(page))}
    assert "Air Handling Unit: 1 point to check" in groups
    assert "Energy Recovery Unit: 1 point to check" in groups
    assert "Air Side: 2 points to check" in groups
    assert "How many Air Handling Unit units?" in groups["Air Handling Unit: 1 point to check"]
    assert "How many Energy Recovery Unit units?" in groups["Energy Recovery Unit: 1 point to check"]
    system = groups["Air Side: 2 points to check"]
    assert "Point 1 (Furnish and Install)" in system
    assert "The block has no tech hours." in system
    assert "How many" not in system


def test_a_group_counts_as_one_question_toward_the_cap(tmp_path):
    page = _page(_job(*(_device(i) for i in range(1, 17))), tmp_path=tmp_path)
    assert "1 of 1 question(s) shown" in page
    assert page.count('class="q extra"') == 0
    assert len(_qdata(page)) == 16


def test_show_all_hides_whole_groups(tmp_path):
    systems = []
    for n in range(16):
        key = f"S{n}"
        device = _device(1, system=key)
        systems.append(System(key=key, name=f"System {n}", shape="Air Handling Unit", control="field",
                              families=(Family(f"Family {n}", (f"T-{n}",), _settled()),), devices=(device,)))
    job = Job(name="Invented", systems=tuple(systems))
    page = _page(job, tmp_path=tmp_path)
    assert "15 of 16 question(s) shown" in page
    assert page.count('<section class="group extra">') == 1
    assert page.count('<section class="group">') == review.MAX_QUESTIONS
    assert 'class="q extra"' not in page
    hidden = re.search(r'<section class="group extra">(.*?)</section>', page, re.S).group(1)
    assert 'class="q"' in hidden and 'class="q extra"' not in hidden
    assert ".group.extra{display:none}" in page
    assert "body.all .group.extra{display:block}" in page
    assert '1 more question(s) under "Show all questions".' in page


def test_a_system_with_no_family_uses_the_system_name(tmp_path):
    device = _device(1, system="CB")
    system = System(key="CB", name="Coil Bank", shape="Coil Bank", control="none", families=(), devices=(device,))
    page = _page(Job(name="Invented", systems=(system,)), tmp_path=tmp_path)
    assert _headings(page) == ["Coil Bank: 1 point to check"]


def test_front_end_questions_use_one_group_named_front_end(tmp_path):
    device = _device(1, system="FE")
    job = Job(name="Invented", front_end=FrontEnd(mode="new-system", devices=(device,)))
    page = _page(job, tmp_path=tmp_path)
    assert _headings(page) == ["Front end: 1 point to check"]
    assert _qdata(page)[0]["device_id"] == "FE.d1"
