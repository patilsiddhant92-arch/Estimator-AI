"""Reviewer's tests for hark/T-005c (2026-10-11). Every job, folder and name here is invented."""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from bms.render import short_points
from estimator.proposal.write import ame_bms

TODAY = dt.date(2026, 10, 11)


def _header(root: Path):
    from estimator.writing.front_end import job_header
    catalogue = SimpleNamespace(job=SimpleNamespace(name=root.name, root=root), pages=(), sheets=(), sections=(),
                                overview=SimpleNamespace(topics=(), who_does_what=(), services=()))
    return job_header(catalogue, SimpleNamespace(versions=()), TODAY)


# ruling 4 names AME's three as "Honeywell WEBS, Johnson FX (Facility Explorer) or Niagara Tridium": each of those
# spellings, as a reader may copy it from a spec, must print plain (no ***, no flag line)
@pytest.mark.parametrize("name", ["Honeywell WEBS", "Johnson FX", "Johnson FX (Facility Explorer)",
                                  "Niagara Tridium", "JOHNSON CONTROLS FACILITY EXPLORER"])
def test_the_rulings_own_spellings_of_ames_three_are_ame(name):
    assert ame_bms(name)


# F1 (the lead's four spellings of the Johnson line, and the nearest forms of them): each names AME's own platform
@pytest.mark.parametrize("name", ["Johnson FX", "Johnson Controls FX", "Facility Explorer", "FX80", "FX 80", "FX-80",
                                  "FX-PCG", "JCI FX"])
def test_every_spelling_of_the_johnson_fx_line_is_ame(name):
    assert ame_bms(name)


@pytest.mark.parametrize("name", ["Schneider Electric (with existing NAC-1)", "Johnson Controls Metasys",
                                  "Johnson Metasys", "Siemens Desigo CC", "Automated Logic WebCTRL", "Honeywell EBI"])
def test_other_makers_are_not_ame(name):
    assert not ame_bms(name)


# a bare "FX", or "FX" with a one-digit number or a year, is no platform name
@pytest.mark.parametrize("name", ["FX", "FX-1", "FX 1", "FX2026"])
def test_a_bare_fx_is_not_ame(name):
    assert not ame_bms(name)


# ruling 3: a project name with several commas, a takeoff subfolder and a folder below it
def test_a_project_name_with_commas_keeps_every_part_after_the_job_number():
    job = "26-7101, Invented Hall, 12 Nowhere St, Springfield, ZZ - Reno"
    header, flags = _header(Path("Jobs") / job / "2. Takeoffs" / "1. Base Takeoff" / "Specifications")
    assert header.quote_number == "26-7101"
    assert header.reference == "Invented Hall, 12 Nowhere St, Springfield, ZZ - Reno"
    assert not any("project name" in f for f in flags)


# ruling 3: "never the takeoff folder's name", also when the takeoff subfolder is itself called "Takeoff"
def test_a_takeoff_subfolder_named_takeoff_does_not_become_the_job_folder():
    job = "26-7102, Invented Library"
    header, _ = _header(Path("Jobs") / job / "2. Takeoffs" / "Takeoff")
    assert header.quote_number == "26-7102"
    assert header.reference == "Invented Library"


# ruling 5: short points never cut or change a word
def test_short_points_keep_every_word():
    text = ("* Clarification: The spec section 23 09 23 calls for the U.S. made controller. AME furnishes the panel "
            "per Spec. Section 23 09 23; the Electrical Contractor provides 120 V power to each panel. The Owner "
            "furnishes the network drop, e.g. at the 2nd floor IDF. Approx. 4 panels are shown on sheet M-701.")
    out = short_points(text)
    assert len(out) >= 2 and all(line.startswith("*") for line in out)       # T-008: one "*" line per point
    words = lambda s: [w.strip(".;") for w in re.split(r"\s+", s) if w.strip(".;*")]
    words2 = words
    assert [w.lstrip("*") for w in words(" ".join(out))] == [w.lstrip("*") for w in words(text)]
