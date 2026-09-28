"""Build the phrasing bank (assets/phrasing_bank.json) from the Learn jobs' issued proposals.

    .venv/Scripts/python.exe tools/build_phrasing_bank.py [--learn "D:\\Estimation Assistant\\Learn"]

One entry per block of each issued proposal: the job, the header, the header's tag prefixes and
its other words, the lines (text and depth) and the notes. Tech hours and prices are never kept.

The sources are read-only: each Learn job's proposal in "3. Proposal/1. Base Proposal" (the
estimator's revision file when there is one, else <job>.docx) and the sent 26-0246 proposal in
tests/data. The test jobs 26-0478 and 26-0193 are left out entirely: their folders are never
opened. Proposals on the AME template are read with estimator.proposal.read; ones written in the
older "(xN)" style are read by a simple fallback.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from estimator.catalogue.tags import Equipment, find_tags  # noqa: E402
from estimator.files import open_docx  # noqa: E402
from estimator.proposal.read import ProposalFormatError, read_blocks_fallback, read_scope  # noqa: E402
from estimator.text import squash  # noqa: E402

LEARN = Path(r"D:\Estimation Assistant\Learn")
SENT = ROOT / "tests" / "data" / "26-0246" / "sent-proposal.docx"
SENT_JOB = "26-0246"
BANK = ROOT / "assets" / "phrasing_bank.json"
PROPOSAL_FOLDER = Path("3. Proposal") / "1. Base Proposal"
EXCLUDED = ("26-0478", "26-0193")    # the answer key of a comparison that is running: never opened
READ_SCOPE, FALLBACK = "read_scope", "(xN) fallback"

_JOB = re.compile(r"^\d{2}-\d{4}")
_QTY = re.compile(r"^\*?\s*(?:\(x\s*\d+\)|Qty\s*\(\s*[\d#?]+\s*\))\s*", re.I)
_TRAILING_X = re.compile(r"\s*[-–]?\s*\(x\s*\d+\)\s*$", re.I)
_HOURS = re.compile(r"\d\s*-?\s*(?:hours?|hrs?)\b|tech\s*hour", re.I)
_TAGGISH = re.compile(r"^[A-Z]{1,6}(?:[-–.#]|\d)")    # EWH-1, CHLR-#-#, VAV-21-01, AHU1


def job_of(name: str) -> str | None:
    m = _JOB.match(name)
    return m.group(0) if m else None


def _skipped(name: str) -> bool:
    low = name.lower()
    return (not low.endswith(".docx") or low.startswith(("proposal template", "ame_nordomatic", "~$"))
            or "_elec" in low)


def choose_file(folder: Path, job: str) -> Path | None:
    """The estimator's revision file (named "+SP" or "revision") when there is one, else <job>.docx,
    else the only proposal in the folder."""
    files = sorted(p for p in folder.iterdir() if p.is_file() and not _skipped(p.name))
    revisions = [p for p in files if "+sp" in p.name.lower() or "revision" in p.name.lower()]
    if revisions:
        return revisions[-1]
    plain = [p for p in files if p.name.lower() == f"{job}.docx"]
    if plain:
        return plain[0]
    return files[0] if len(files) == 1 else None


# --- one block ----------------------------------------------------------------------------------

def _clean(text: str) -> str | None:
    """The line as written, or None when it carries hours or a price (never kept)."""
    text = squash(text)
    if not text or "$" in text or _HOURS.search(text):
        return None
    return text


def entry(job: str, header: str, lines, notes, equipment: Equipment) -> dict:
    """One bank entry. `lines` are (text, depth) pairs."""
    tags = find_tags(header, equipment)
    prefixes = list(dict.fromkeys(t.split("-", 1)[0] for t in tags))
    # Beyond find_tags: a tag with no number yet ("CHLR-#-#"), a tag-shaped code the equipment
    # list does not know ("HPWH-1") and a known prefix standing alone ("… Box – VAV").
    for token in re.split(r"[\s,|]+", header):
        token = token.strip("()*:;.")
        m = re.match(r"^([A-Z]{2,6})-(?=\S*[#\d])", token)
        code = m.group(1) if m else (token if token in equipment.prefixes else None)
        if code and code not in prefixes:
            prefixes.append(code)
    rest = re.sub(r"\(x\s*\d+\)", " ", _QTY.sub("", header), flags=re.I)
    kind_words = []
    for token in re.split(r"[\s,/&()|]+", rest):
        token = token.strip("-–:;.*")
        if not token or len(token) < 2 or re.search(r"[\d#]", token) or not re.search(r"[A-Za-z]", token):
            continue
        if _TAGGISH.match(token) and not token.isalpha():
            continue
        if token.lower() in ("qty", "thru", "and") or token in tags:
            continue
        kind_words.append(token)
    kept_lines = [{"text": t, "depth": d} for t, d in ((_clean(t), d) for t, d in lines) if t]
    kept_notes = [n for n in (_clean(n) for n in notes) if n]
    return {"job": job, "header": squash(header), "prefixes": prefixes, "kind_words": kind_words,
            "lines": kept_lines, "notes": kept_notes}


# --- reading a proposal ---------------------------------------------------------------------------

def _from_read_scope(document, job: str, equipment: Equipment) -> list[dict]:
    _, _, blocks, add, deduct = read_scope(document)
    every = list(blocks) + [b for alternate in (*add, *deduct) for b in alternate.blocks]
    found = []
    for block in every:
        lines = [(item.text, item.depth) for item in block.items if item.kind == "line"]
        notes = [item.text for item in block.items if item.kind == "note"]
        found.append(entry(job, block.header, lines, notes, equipment))
    return found


def _fallback(document, job: str, equipment: Equipment) -> list[dict]:
    """The "(xN)" style (estimator.proposal.read.read_blocks_fallback), each line's own "- (xN)" taken off."""
    return [entry(job, b["header"], [(_TRAILING_X.sub("", text), depth) for text, depth in b["lines"]], b["notes"],
                  equipment) for b in read_blocks_fallback(document)]


def read_blocks(path: Path, job: str, equipment: Equipment | None = None) -> tuple[list[dict], str]:
    """The proposal's blocks as bank entries, and which reader read them."""
    equipment = equipment or Equipment.load()
    document = open_docx(path)
    try:
        found = _from_read_scope(document, job, equipment)
        reader = READ_SCOPE
    except ProposalFormatError:
        found, reader = [], READ_SCOPE
    if not found:
        found, reader = _fallback(document, job, equipment), FALLBACK
    return [e for e in found if e["lines"] or e["notes"]], reader


# --- the whole bank -------------------------------------------------------------------------------

def build(learn: Path, sent: Path | None = SENT) -> dict:
    equipment = Equipment.load()
    blocks: list[dict] = []
    sources: list[dict] = []
    skipped: list[dict] = []
    if sent is not None:
        found, reader = read_blocks(sent, SENT_JOB, equipment)
        blocks += found
        sources.append({"job": SENT_JOB, "file": "tests/data/26-0246/sent-proposal.docx", "reader": reader,
                        "blocks": len(found)})
    for folder in sorted(p for p in Path(learn).iterdir() if p.is_dir()):
        job = job_of(folder.name)
        if job is None or job in EXCLUDED:
            continue                                     # never opened
        if sent is not None and job == SENT_JOB:
            continue                                     # the same file as the sent copy in tests/data
        proposals = folder / PROPOSAL_FOLDER
        path = choose_file(proposals, job) if proposals.is_dir() else None
        if path is None:
            skipped.append({"job": job, "why": "no issued proposal found"})
            continue
        try:
            found, reader = read_blocks(path, job, equipment)
        except Exception as error:                      # one bad file never stops the bank
            skipped.append({"job": job, "why": f"{path.name} could not be read: {error}"})
            continue
        if not found:
            skipped.append({"job": job, "why": f"{path.name}: no block could be read"})
            continue
        blocks += found
        sources.append({"job": job, "file": path.name, "reader": reader, "blocks": len(found)})
    return {
        "about": ("How systems were actually written in the Learn jobs' issued proposals: one entry per block. "
                  "Built by tools/build_phrasing_bank.py; no tech hours or prices. The test jobs 26-0478 and "
                  "26-0193 are left out."),
        "sources": sources,
        "skipped": skipped,
        "blocks": blocks,
    }


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--learn", type=Path, default=LEARN)
    parser.add_argument("--out", type=Path, default=BANK)
    args = parser.parse_args(argv)
    bank = build(args.learn)
    args.out.write_text(json.dumps(bank, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for source in bank["sources"]:
        print(f"{source['job']}: {source['blocks']} blocks from {source['file']} ({source['reader']})")
    for skip in bank["skipped"]:
        print(f"{skip['job']}: skipped — {skip['why']}")
    print(f"{len(bank['blocks'])} blocks from {len(bank['sources'])} jobs -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
