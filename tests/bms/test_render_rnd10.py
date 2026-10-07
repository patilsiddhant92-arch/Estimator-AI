"""RND-10: title casing never turns an ordinary word into an acronym, on invented names and the repo Playbook."""
from __future__ import annotations

from pathlib import Path

import pytest

from bms.model import Count, Device, Family, Header, Job, Ref, System
from bms.playbook import load_playbook
from bms.render import render

ROOT = Path(__file__).resolve().parents[2]
REF = Ref(source_id="S1", quote="q", where="M-1, Drawings.pdf page 1")


@pytest.fixture(scope="module")
def pb():
    return load_playbook(ROOT / "playbook")


def device(name: str) -> Device:
    return Device(id="X.d1", slot="x", name=name, verb="Furnish and Install", furnished_by="AME", installed_by="AME",
                  wired_by="AME", quantity=Count(value=2), refs=(REF,))


def job(name: str) -> Job:
    s = System(key="EF", name="Exhaust Fans", shape="", control="field",
               families=(Family("Exhaust Fan", ("EF-1", "EF-2"), Count(value=2)),), devices=(device(name),))
    return Job(name="Invented", systems=(s,), header=Header("00-0000", "Invented", "Invented", ("A",), "2026-10-04"))


# ---- RND-10: ordinary words are never made acronyms ---------------------------------------------------------------

@pytest.mark.parametrize("name, printed", [
    ("Damper actuator with no end switch", "Damper Actuator with No End Switch"),
    ("No. 2 fuel oil pump", "No. 2 Fuel Oil Pump"),
    ("Co-located sensor", "Co-located Sensor"),
    ("connect it to the panel", "Connect it to the Panel"),
    ("vfd", "VFD"),
    ("CO sensor", "CO Sensor"),
    ("co sensor", "CO Sensor"),
    ("co2 detector", "CO2 Detector"),
    ("it closet cooling unit", "IT Closet Cooling Unit"),
    ("no sensor", "No Sensor"),
    ("FA relay", "FA Relay"),
    ("fa relay", "FA Relay"),
    ("fa panel interface", "FA Panel Interface"),
])
def test_ordinary_words_are_not_turned_into_acronyms(pb, name, printed):
    out = [l.text for l in render(job(name), pb).lines if l.system_key == "EF"]
    assert out[1] == f"Furnish and Install {printed}"
