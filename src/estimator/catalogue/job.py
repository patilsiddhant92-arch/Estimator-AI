"""One job, catalogued: every stage of build step 3, and the flags an estimator should look at."""
from __future__ import annotations

from dataclasses import dataclass

from estimator.catalogue.documents import JobFolder
from estimator.catalogue.qualify import BidCheck
from estimator.catalogue.register import PageRecord
from estimator.catalogue.sheet_types import Sheet
from estimator.catalogue.spec_sections import SpecSection
from estimator.catalogue.tags import TagEntry


@dataclass(frozen=True)
class Catalogue:
    job: JobFolder
    pages: tuple[PageRecord, ...]
    sheets: tuple[Sheet, ...]
    sections: tuple[SpecSection, ...]
    bid: BidCheck
    tags: tuple[TagEntry, ...]
    flags: tuple[str, ...]
