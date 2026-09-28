"""Shared test fixtures: where the real templates, price book and test job live."""
import datetime as dt
from pathlib import Path

import docx
import pytest

from estimator.price_sheet.price_book import PriceBook
from estimator.proposal.read import read_proposal, read_scope
from estimator.scope import Alternate, Block, FrontEnd, Header, Item, Job, Run

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


def _line(text: str, *, quantity: int | None = None, depth: int = 1, bold: bool = False) -> Item:
    return Item(kind="line", depth=depth, runs=(Run(text=text, bold=bold),), quantity=quantity)


def _note(text: str) -> Item:
    return Item(kind="note", runs=(Run(text=text, bold=True),))


_HEADER = Header(
    date=dt.date(2026, 6, 8),
    quote_number="26-9999",
    reference="Test Building, 1 Main St",
    mep_engineer="Test MEP",
    based_on=("M-001 thru M-100 Dated: 01/02/2026", "Specs 23 09 00"),
)


@pytest.fixture
def small_job() -> Job:
    """A small job that uses every kind of line, both sections, a priced, a pending and a questioned price."""
    return Job(
        header=_HEADER,
        scope_heading_suffix="PREVAILING WAGE",
        front_end=FrontEnd(mode="new-system", tech_hours=40.0, items=(
            _line("Furnish Network Level Control Panel", quantity=1, bold=True),   # no price book match
            _line("Furnish BMS Server", quantity=1, bold=True),                    # price book: 2500
            _note("*CONNECTION TO OWNER WAN BY OTHERS"),
        )),
        blocks=(
            Block(header="Qty (2) Exhaust Fan EF-1, 2", tech_hours=8.0, items=(
                _line("Furnish and Install DDC Controller", quantity=2),           # no price book match
                _line("Mfr. to Provide Relay", depth=2),
                _note("*DAMPERS BY OTHERS"),
            )),
            Block(header="Qty (1) Air Handling Unit AHU-1", tech_hours=12.0, items=(
                _line("Furnish and Install Space Temperature Sensor", quantity=3), # price book: 142
                _line("Furnish and Wire Filter DP Switch", quantity=1),            # price book: 50, marked "Need review"
                Item(kind="line", runs=(Run(text="Furnish and Install "), Run(text="(Duct Mounted)", bold=True),
                                        Run(text=" Static Pressure Sensor"))),
            )),
        ),
        add_alternates=(Alternate(label="ALT 1: Controls for EF-3", blocks=(
            Block(header="Qty (1) Exhaust Fan EF-3", tech_hours=4.0, items=(
                _line("Furnish and Install DDC Controller", quantity=1),
            )),
        )),),
        named_exceptions=("EXCEPTION TO ANY WORK WITH EXHAUST FAN EF-4",),
    )


@pytest.fixture
def bare_job() -> Job:
    """Only the cover page and the front-end choice — no scope lines at all."""
    return Job(header=_HEADER, scope_heading_suffix="PREVAILING WAGE", front_end=FrontEnd(mode="new-system"))


@pytest.fixture
def without_prices():
    """Clear every tech_hours and quantity: what a proposal alone can tell you."""
    def clear(job: Job) -> Job:
        data = job.model_dump()

        def walk(node):
            if isinstance(node, dict):
                node.pop("tech_hours", None)
                node.pop("quantity", None)
                for value in node.values():
                    walk(value)
            elif isinstance(node, (list, tuple)):
                for value in node:
                    walk(value)

        walk(data)
        return Job.model_validate(data)

    return clear


@pytest.fixture(scope="session")
def template_document():
    return docx.Document(str(PROPOSAL_TEMPLATE))


@pytest.fixture(scope="session")
def sent_document():
    return docx.Document(str(SENT_PROPOSAL))


@pytest.fixture(scope="session")
def sent_scope(sent_document):
    return read_scope(sent_document)


@pytest.fixture(scope="session")
def sent_job():
    return read_proposal(SENT_PROPOSAL, PROPOSAL_TEMPLATE)


@pytest.fixture(scope="session")
def price_book():
    return PriceBook.load(PRICE_BOOK, ALIASES)


@pytest.fixture(scope="session")
def test_job():
    return Job.model_validate_json(TEST_JOB_FILE.read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _corrections_stay_in_tmp(tmp_path_factory, monkeypatch):
    """No test reads or writes the real out/corrections folder or the proposed rules in assets/gem."""
    import estimator.__main__ as cli
    import estimator.writing.whole_job as wj
    folder = tmp_path_factory.mktemp("corrections")
    monkeypatch.setattr(cli, "CORRECTIONS", folder / "out" / "corrections")
    monkeypatch.setattr(wj, "PROPOSED_PRACTICE_FILE", folder / "ame_practice_proposed.txt")
