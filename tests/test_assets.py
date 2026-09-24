"""The files copied in from the team's folders are exactly the ones measured while planning."""
import hashlib
import json
import sys

import pytest

from conftest import ALIASES, PRICE_BOOK, PROPOSAL_TEMPLATE, SENT_PROPOSAL, SENT_WORKUP, WORKUP_TEMPLATE

EXPECTED = {
    PROPOSAL_TEMPLATE: "cdc84d56e9b085bd8f8140651e51be9e4422c3f968a316c636df39d9cbd13085",
    WORKUP_TEMPLATE: "70925fb6ebe3a5f726146b7bc479f436d9a16d976a72d413550c433f7aef7ad7",
    PRICE_BOOK: "7485d8bf608551a018dea497b00ca4d39fca2fafc92fb98bdb34d71257c4231a",
    SENT_PROPOSAL: "3d2c48982eb94a0a697b9cb56bab03ccd80052f2734a1e9b6869851355566319",
    SENT_WORKUP: "8a516b27bd7448fc174c1eaf3d7c74d057fbe1bcd2cd77912093171cc41c60d7",
}


@pytest.mark.parametrize("path", list(EXPECTED), ids=lambda p: p.name)
def test_asset_is_the_measured_file(path):
    assert path.exists(), f"{path} is missing — copy it in (Task 1, Step 7)"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == EXPECTED[path]


def test_alias_file_starts_empty():
    assert json.loads(ALIASES.read_text(encoding="utf-8"))["aliases"] == {}


def test_running_on_the_project_python():
    assert sys.version_info[:3] == (3, 13, 15), "run tests with .venv/Scripts/python.exe"
