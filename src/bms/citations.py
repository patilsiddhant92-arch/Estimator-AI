"""The one source-id pattern. S is a schedule line, Q a keynote, I a drawing, F a fact, C a count.

Render replaces these with the sheet or section, or drops them. Validate flags them in wording that
prints. Both import this module so a new prefix is added in one place.
"""
from __future__ import annotations

import re

ONE_ID_TEXT = r"\b[SQIFC]\d{1,4}[a-z]?\b"
WITH_NOTE = rf"{ONE_ID_TEXT}(?:\s+(?:note|paragraph)\s+\d+)?"
ONE_ID = re.compile(ONE_ID_TEXT)
SOURCE_ID = re.compile(WITH_NOTE)
ID_GROUP = re.compile(rf"{WITH_NOTE}(?:\s*(?:,|and|to|through|thru|-|–)\s*{WITH_NOTE})*")
