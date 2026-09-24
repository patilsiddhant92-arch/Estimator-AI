"""Shared test fixtures: where the real templates, price book and test job live."""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
PROPOSAL_TEMPLATE = ASSETS / "templates" / "AME_nordomatic Proposal Template.docx"
WORKUP_TEMPLATE = ASSETS / "templates" / "PriceWorkup_Template - 12-21-25.xlsx"
PRICE_BOOK = ASSETS / "price_book" / "AME Std Pricing Spreadsheet.xlsx"
ALIASES = ASSETS / "price_book" / "aliases.json"
TEST_JOB_DIR = ROOT / "tests" / "data" / "26-0246"
SENT_PROPOSAL = TEST_JOB_DIR / "sent-proposal.docx"
SENT_WORKUP = TEST_JOB_DIR / "sent-workup.xlsx"
TEST_JOB_FILE = TEST_JOB_DIR / "job.json"


@pytest.fixture
def proposal_template() -> Path:
    return PROPOSAL_TEMPLATE


@pytest.fixture
def workup_template() -> Path:
    return WORKUP_TEMPLATE


@pytest.fixture
def price_book_path() -> Path:
    return PRICE_BOOK


@pytest.fixture
def aliases_path() -> Path:
    return ALIASES


@pytest.fixture
def sent_proposal() -> Path:
    return SENT_PROPOSAL


@pytest.fixture
def sent_workup() -> Path:
    return SENT_WORKUP
