"""Run-to-run REGRESSION diff of two proposals (the old run against the new one).

There are no golden answer keys (every job is different, and old proposals can carry misses too), so this does not
score against "the right answer": it shows what changed between two runs of the same job, so a fix that silently
drops or changes scope is seen.

Inputs: a Word proposal or the app's Job.json, for each side (they may differ: v1 docx vs v2 Job.json). Both are
reduced to SCOPE BLOCKS: the front end, then each "Qty (n) <name> <tags>" heading (stacked headings join) with the
lines under it; "*" / "**" lines are the block's notes. Blocks are matched by tags, else name words; lines inside a
matched block by fuzzy device text (verb, quantity and "(Furnished by ...)" taken off).

Output: blocks added / removed / changed (heading qty, alternate), and per block the lines added, removed and
changed (verb, qty, wording), plus notes added and removed. JSON and markdown.
"""
from __future__ import annotations

import difflib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import appio

VERBS = ("Furnish and Install", "Furnish and Wire", "Install and Wire", "Furnish", "Install", "Wire")
_VERB_RE = re.compile(r"^(" + "|".join(re.escape(v) for v in VERBS) + r")\b\s*", re.I)
_HEAD = re.compile(r"^\s*Qty\s*\(\s*([\d#?]+)\s*\)\s*(.*)$", re.I)
_LINE_QTY = re.compile(r"\(\s*Qty\.?\s*(\d+|##)\s*(?:Total)?\s*\)", re.I)
_FURNISHED = re.compile(r"\(\s*Furnished\s+by\s+([^)]*)\)", re.I)
_STOP = frozenset("the a an of for to with at in on and each new per via by from all as is are be unit units qty "
                  "total".split())
LINE_MATCH = 0.5
BLOCK_MATCH = 0.3


@dataclass
class SLine:
    text: str
    verb: str
    device: str                 # normalised device words
    quantity: int | None
    furnished_by: str = ""
    own_qty: bool = False       # the line states its own quantity (else it is the block's)


@dataclass
class SBlock:
    key: str                    # "FE" for the front end, else the heading
    header: str
    quantity: int | None
    tags: frozenset
    words: frozenset
    alternate: str = "base"
    lines: list[SLine] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)       # "*" and "**" lines


# ---- normalising ------------------------------------------------------------------------------------------


def _singular(w: str) -> str:
    if len(w) > 3 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def device_words(text: str) -> str:
    text = _LINE_QTY.sub(" ", text)
    text = _FURNISHED.sub(" ", text)
    text = _VERB_RE.sub("", text.strip())
    text = re.sub(r"[^A-Za-z0-9/ ]", " ", text).replace("/", " ")
    return " ".join(_singular(w) for w in text.casefold().split() if w not in _STOP)


def parse_line(text: str, block_qty: int | None) -> SLine:
    text = " ".join(text.split())
    m = _VERB_RE.match(text)
    verb = m.group(1).title().replace(" And ", " and ") if m else ""
    q = _LINE_QTY.search(text)
    qty = int(q.group(1)) if q and q.group(1).isdigit() else block_qty
    f = _FURNISHED.search(text)
    return SLine(text, verb, device_words(text), qty, f.group(1).strip() if f else "", bool(q))


def _header_words(header: str, tags: frozenset) -> frozenset:
    words = set()
    for tok in re.split(r"[\s,/&()|:;]+", header):
        tok = tok.strip("-–.*")
        if not tok or re.search(r"\d", tok) or appio.norm_tag(tok) in tags or tok.lower() in ("qty", "thru"):
            continue
        w = _singular(tok.casefold())
        if len(w) >= 2 and w not in _STOP:
            words.add(w)
    return frozenset(words)


def _new_block(headers: list[str], alternate: str) -> SBlock:
    header = " / ".join(headers)
    qty, rest = 0, []
    found = False
    for h in headers:
        m = _HEAD.match(h)
        if m:
            rest.append(m.group(2))
            if m.group(1).isdigit():
                qty += int(m.group(1))
                found = True
        else:
            rest.append(h)
    tags = frozenset(t for r in rest for t in appio.tags_in(r))
    return SBlock(header, header, qty if found else None, tags, _header_words(" ".join(rest), tags), alternate)


# ---- reading a proposal -------------------------------------------------------------------------------------


def read_docx(path) -> list[SBlock]:
    import docx  # python-docx
    document = docx.Document(str(path))
    paragraphs = [" ".join(p.text.split()) for p in document.paragraphs]
    start = next((i for i, t in enumerate(paragraphs) if t.upper().startswith("SCOPE OF WORK")), None)
    if start is None:
        raise ValueError(f"{Path(path).name}: no 'SCOPE OF WORK' heading")
    end = next((i for i, t in enumerate(paragraphs) if i > start and t.lower().startswith(
        "clarifications and inclusions")), len(paragraphs))
    blocks: list[SBlock] = [SBlock("FE", "Front end", None, frozenset(), frozenset({"front", "end"}))]
    alternate, pending = "base", []
    for text in paragraphs[start + 1:end]:
        if not text or text.startswith("[MOCKUP"):
            continue
        upper = text.upper()
        if upper.startswith("ADD ALTERNATE"):
            alternate = "add"
            continue
        if upper.startswith("DEDUCT ALTERNATE"):
            alternate = "deduct"
            continue
        if re.match(r"^ALT\s*#", upper):
            continue
        if _HEAD.match(text):
            pending.append(text)
            continue
        if pending:
            blocks.append(_new_block(pending, alternate))
            pending = []
        block = blocks[-1]
        if text.startswith("*"):
            block.notes.append(text)
        else:
            block.lines.append(parse_line(text, block.quantity))
    if pending:
        blocks.append(_new_block(pending, alternate))
    return blocks


def read_job(job: dict, printed: dict[str, str] | None = None,
             notes: dict[str, list[str]] | None = None) -> list[SBlock]:
    """Blocks from the app's Job.json, worded as the app prints them (lines and notes) when its renderer is
    importable; else the plain wording and the raw clarifications."""
    if printed is None:
        printed, notes = appio.printed_texts(job), appio.printed_notes(job)
    fe = job.get("front_end") or {}
    blocks = [SBlock("FE", "Front end", None, frozenset(), frozenset({"front", "end"}))]
    by_key: dict[str, SBlock] = {}
    for system in job.get("systems") or []:
        if not system.get("devices"):
            continue
        heads = [f"Qty ({appio._qty(f.get('count')) if appio._qty(f.get('count')) is not None else '##'}) "
                 f"{f.get('name', '')} {', '.join(f.get('tags') or [])}".strip()
                 for f in system.get("families") or [] if f.get("tags") or len(system.get("families") or []) == 1]
        block = _new_block(heads or [system.get("name", system.get("key", ""))], system.get("alternate", "base"))
        block.notes = (notes or {}).get(system.get("key", "")) if notes is not None else \
            [f"*{c.get('kind', '')}: {c.get('text', '')}" for c in system.get("clarifications") or []]
        block.notes = list(block.notes or [])
        by_key[system.get("key", "")] = block
        blocks.append(block)
    blocks[0].notes = list((notes or {}).get("FE") or []) if notes is not None else \
        [f"*{c.get('kind', '')}: {c.get('text', '')}" for c in fe.get("clarifications") or []]
    if fe.get("mode") == "extend-existing":   # the template's opening line (not a Job device)
        blocks[0].lines.append(parse_line("Seamlessly Tie in to the Existing [existing BMS name] BMS", None))
    for line in appio.job_lines(job, printed):
        block = blocks[0] if line.system_key == "FE" else by_key.get(line.system_key)
        if block is None:
            continue
        parsed = parse_line(line.text, block.quantity)
        if line.quantity is not None:
            parsed.own_qty = parsed.own_qty or line.quantity != block.quantity
            parsed.quantity = line.quantity
        block.lines.append(parsed)
    return blocks


def read_any(path) -> list[SBlock]:
    path = Path(path)
    if path.suffix.lower() == ".json":
        return read_job(appio.load_json(path))
    return read_docx(path)


# ---- matching -----------------------------------------------------------------------------------------------


def _jaccard(a, b) -> float:
    a, b = set(a), set(b)
    return len(a & b) / len(a | b) if a and b else 0.0


def block_similarity(a: SBlock, b: SBlock) -> float:
    if a.key == "FE" or b.key == "FE":
        return 1.0 if a.key == b.key == "FE" else 0.0
    if a.tags and b.tags:
        tag = _jaccard(a.tags, b.tags)
        if tag:
            return 0.5 + 0.5 * tag
    stems = lambda blk: {re.sub(r"\d+$", "", t) for t in blk.tags}
    return 0.6 * _jaccard(a.words, b.words) + 0.4 * _jaccard(stems(a), stems(b))


def line_similarity(a: SLine, b: SLine) -> float:
    if not a.device or not b.device:
        return 0.0
    seq = difflib.SequenceMatcher(None, a.device, b.device).ratio()
    return 0.6 * seq + 0.4 * _jaccard(a.device.split(), b.device.split())


def _greedy(left, right, sim, threshold):
    pairs = sorted(((sim(a, b), i, j) for i, a in enumerate(left) for j, b in enumerate(right)), reverse=True)
    used_l, used_r, out = set(), set(), []
    for s, i, j in pairs:
        if s < threshold or i in used_l or j in used_r:
            continue
        used_l.add(i)
        used_r.add(j)
        out.append((i, j, s))
    return out



@dataclass
class LineChange:
    change: str                 # added | removed | changed
    old: str = ""
    new: str = ""
    what: list[str] = field(default_factory=list)      # verb / qty / wording, for a changed line


@dataclass
class BlockDiff:
    change: str                 # added | removed | changed | same
    old: str
    new: str
    old_qty: int | None = None
    new_qty: int | None = None
    what: list[str] = field(default_factory=list)
    lines: list[LineChange] = field(default_factory=list)
    notes_added: list[str] = field(default_factory=list)
    notes_removed: list[str] = field(default_factory=list)


@dataclass
class DiffResult:
    old_file: str
    new_file: str
    blocks: list[BlockDiff]

    @property
    def totals(self) -> dict:
        lines = [l for b in self.blocks for l in b.lines]
        return {"blocks_added": sum(b.change == "added" for b in self.blocks),
                "blocks_removed": sum(b.change == "removed" for b in self.blocks),
                "blocks_changed": sum(b.change == "changed" for b in self.blocks),
                "lines_added": sum(l.change == "added" for l in lines),
                "lines_removed": sum(l.change == "removed" for l in lines),
                "lines_changed": sum(l.change == "changed" for l in lines),
                "notes_changed": sum(len(b.notes_added) + len(b.notes_removed) for b in self.blocks)}

    @property
    def unchanged(self) -> bool:
        return not any(self.totals.values())

    def to_dict(self) -> dict:
        return {"old_file": self.old_file, "new_file": self.new_file, "unchanged": self.unchanged,
                "totals": self.totals, "blocks": [asdict(b) for b in self.blocks]}


def _norm(text: str) -> str:
    return " ".join(text.split()).casefold()


def _line_changes(old: SBlock, new: SBlock) -> list[LineChange]:
    out = []
    pairs = _greedy(old.lines, new.lines, line_similarity, LINE_MATCH)
    for i, j, _ in sorted(pairs):
        a, b = old.lines[i], new.lines[j]
        what = []
        if a.verb.casefold() != b.verb.casefold():
            what.append(f"verb {a.verb or '—'} -> {b.verb or '—'}")
        if a.quantity != b.quantity and (a.own_qty or b.own_qty):   # a heading change is reported on the block
            what.append(f"qty {a.quantity} -> {b.quantity}")
        if not what and _norm(a.text) != _norm(b.text):
            what.append("wording")
        if what:
            out.append(LineChange("changed", a.text, b.text, what))
    seen_old, seen_new = {i for i, _, _ in pairs}, {j for _, j, _ in pairs}
    out += [LineChange("removed", l.text) for i, l in enumerate(old.lines) if i not in seen_old]
    out += [LineChange("added", "", l.text) for j, l in enumerate(new.lines) if j not in seen_new]
    return out


def diff_blocks(old: list[SBlock], new: list[SBlock], old_file: str = "", new_file: str = "") -> DiffResult:
    out: list[BlockDiff] = []
    pairs = _greedy(old, new, block_similarity, BLOCK_MATCH)
    for i, j, _ in sorted(pairs):
        a, b = old[i], new[j]
        d = BlockDiff("same", a.header, b.header, a.quantity, b.quantity, lines=_line_changes(a, b))
        if a.quantity != b.quantity:
            d.what.append(f"heading qty {a.quantity} -> {b.quantity}")
        if a.alternate != b.alternate:
            d.what.append(f"alternate {a.alternate} -> {b.alternate}")
        if a.tags != b.tags:
            d.what.append("tags " + ", ".join(sorted(a.tags ^ b.tags)))
        old_notes, new_notes = {_norm(n): n for n in a.notes}, {_norm(n): n for n in b.notes}
        d.notes_removed = [n for k, n in old_notes.items() if k not in new_notes]
        d.notes_added = [n for k, n in new_notes.items() if k not in old_notes]
        if d.what or d.lines or d.notes_added or d.notes_removed:
            d.change = "changed"
        out.append(d)
    used_old, used_new = {i for i, _, _ in pairs}, {j for _, j, _ in pairs}
    for i, a in enumerate(old):
        if i not in used_old and (a.lines or a.key != "FE"):
            out.append(BlockDiff("removed", a.header, "", a.quantity, None,
                                 lines=[LineChange("removed", l.text) for l in a.lines], notes_removed=list(a.notes)))
    for j, b in enumerate(new):
        if j not in used_new and (b.lines or b.key != "FE"):
            out.append(BlockDiff("added", "", b.header, None, b.quantity,
                                 lines=[LineChange("added", "", l.text) for l in b.lines], notes_added=list(b.notes)))
    return DiffResult(old_file, new_file, out)


def diff_files(old, new) -> DiffResult:
    return diff_blocks(read_any(old), read_any(new), Path(old).name, Path(new).name)


def markdown(result: DiffResult) -> str:
    t = result.totals
    out = [f"# Regression diff: {result.old_file} -> {result.new_file}", "",
           "**No change in scope.**" if result.unchanged else
           f"Blocks: {t['blocks_added']} added, {t['blocks_removed']} removed, {t['blocks_changed']} changed. "
           f"Lines: {t['lines_added']} added, {t['lines_removed']} removed, {t['lines_changed']} changed. "
           f"Notes changed: {t['notes_changed']}.", ""]
    for b in result.blocks:
        if b.change == "same":
            continue
        out += [f"## {b.change.upper()}: {b.new or b.old}" + (f" ({'; '.join(b.what)})" if b.what else ""), ""]
        for l in b.lines:
            if l.change == "added":
                out.append(f"- **+** {l.new}")
            elif l.change == "removed":
                out.append(f"- **−** {l.old}")
            else:
                out.append(f"- **~** {l.old} → {l.new} ({', '.join(l.what)})")
        out += [f"- note **+** {n}" for n in b.notes_added] + [f"- note **−** {n}" for n in b.notes_removed]
        out.append("")
    return "\n".join(out) + "\n"


def run(old, new, out_dir, name: str = "") -> DiffResult:
    result = diff_files(old, new)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stem = name or f"{Path(old).stem} vs {Path(new).stem}"
    (out / f"{stem} diff.json").write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False),
                                           encoding="utf-8")
    (out / f"{stem} diff.md").write_text(markdown(result), encoding="utf-8")
    return result
