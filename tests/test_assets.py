"""The files copied in from the team's folders are exactly the ones measured while planning."""
import hashlib
import json
import sys

import pytest

from conftest import ALIASES, PRICE_BOOK, PROPOSAL_TEMPLATE, SENT_PROPOSAL, SENT_WORKUP, WORKUP_TEMPLATE

EXPECTED = {
    PROPOSAL_TEMPLATE: "cdc84d56e9b085bd8f8140651e51be9e4422c3f968a316c636df39d9cbd13085",
    WORKUP_TEMPLATE: "70925fb6ebe3a5f726146b7bc479f436d9a16d976a72d413550c433f7aef7ad7",
    PRICE_BOOK: "2768e1b39a3cd45136645e7600aad6985acf076aa0911b6b34a08227a98f2b6f",
    SENT_PROPOSAL: "3d2c48982eb94a0a697b9cb56bab03ccd80052f2734a1e9b6869851355566319",
    SENT_WORKUP: "8a516b27bd7448fc174c1eaf3d7c74d057fbe1bcd2cd77912093171cc41c60d7",
}


@pytest.mark.parametrize("path", list(EXPECTED), ids=lambda p: p.name)
def test_asset_is_the_measured_file(path):
    assert path.exists(), f"{path} is missing — copy it in (Task 1, Step 7)"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == EXPECTED[path]


def test_alias_file_maps_scope_names_to_price_book_names():
    aliases = json.loads(ALIASES.read_text(encoding="utf-8"))["aliases"]
    assert aliases and all(isinstance(k, str) and isinstance(v, str) for k, v in aliases.items())


def test_running_on_the_project_python():
    assert sys.version_info[:3] == (3, 13, 15), "run tests with .venv/Scripts/python.exe"
