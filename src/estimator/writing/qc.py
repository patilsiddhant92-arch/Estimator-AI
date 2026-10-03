"""The proposal QC pass (design 2026-10-03 §1): once every system is written, the whole draft goes to the AI as a
senior estimator would read it, block by block, against the Master Template, the practice rules and the job
ledger. It compares; it never rewrites. Its findings become review rows (must-fix at tier 1, check at tier 4)
and the "Proposal QC" tab; a finding naming a system or a line the draft does not have is dropped and listed."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from estimator.writing.assemble import TIER_DISAGREE, TIER_FIRST
from estimator.writing.write import ReviewItem

_SPACES = re.compile(r"\s+")

FINDING_KINDS = ("ownership", "not-ame-scope", "missing", "duplicate", "count", "wording", "placement")
MUST_FIX, CHECK = "must-fix", "check"
SEVERITIES = (MUST_FIX, CHECK)

QC_PROMPT = (
    "You are a senior AME controls estimator reviewing a draft proposal another estimator wrote from this job's "
    "documents. You do not rewrite it. For each block you compare its lines with how AME writes that kind of system "
    "(the Master Template entry), with the estimator's practice rules, and with the job ledger's facts, and you list "
    "what is wrong in plain words, one finding per line or block, with the line as it should read when a fix is a "
    "line. Kinds of finding: ownership (wrong furnish/install/wire verb), not-ame-scope (inside a packaged unit, a "
    "monitored point restated, a device another party owns), missing (a template line usually present and not "
    "excluded, or an explicit sequence assignment no line covers), duplicate (the same device in two blocks), count, "
    "wording (not the house form), placement (belongs under another system). Severity must-fix when the proposal "
    "would be wrong or unpriceable as written, check otherwise. Then one paragraph per block in the estimator's "
    "voice, and one for the job. Never invent a device the documents do not name; never change a count."
)


def _squash(text) -> str:
    return _SPACES.sub(" ", str(text or "").replace("\xa0", " ")).strip()


@dataclass(frozen=True)
class QcBlock:
    """One written block as the QC pass sees it: its lines as the draft prints them ("(Qty. N Total)" where the
    line has a quantity), the Master Template's lines for its kind of system, its tech-hour rule, its ledger entry
    and its sequence section id."""
    key: str
    header: str
    quantity: int | None
    klass: str                      # packaged or field, as the writer declared it
    lines: tuple[str, ...]
    template_lines: tuple[str, ...]
    hours_rule: str
    ledger_entry: str
    sequence_section: str


@dataclass(frozen=True)
class QcFinding:
    system: str
    line: str           # the block's own line text, "" for a block-level finding
    kind: str
    say: str
    fix: str
    severity: str
    quote: str


@dataclass(frozen=True)
class QcReport:
    findings: tuple[QcFinding, ...]
    block_notes: dict[str, str]     # system key -> the estimator's paragraph on that block
    job_note: str
    model: str
    dropped: tuple[str, ...] = field(default_factory=tuple)   # findings and notes that could not be used, in words


def _block_text(block: QcBlock) -> str:
    count = f"count {block.quantity}" if block.quantity is not None else "no count"
    out = [f"System {block.key}: {block.header} — {count} — {block.klass or 'class not given'}",
           "Its lines as the draft prints them:"]
    out += [f"  {n}. {line}" for n, line in enumerate(block.lines, 1)] or ["  (no lines)"]
    out.append("How AME writes this kind of system:")
    out += [f"  - {line}" for line in block.template_lines] or ["  (no Master Template entry)"]
    out.append(f"Tech hours: {block.hours_rule or 'no rule given'}")
    out.append(f"Ledger entry: {block.ledger_entry or 'none'}")
    out.append(f"Sequence section: {block.sequence_section or 'none'}")
    return "\n".join(out)


def qc_prompt(brief: str, blocks, practice_text: str, style_guide: str, others=()) -> str:
    """The QC request: the job brief, the practice rules, the house style guide, then each block. `others` are the
    headers of the blocks in other parts of a split draft, so a duplicate across parts can still be seen."""
    parts = [brief.strip()] if brief and brief.strip() else []
    if practice_text and practice_text.strip():
        parts.append("The estimator's practice rules:\n" + practice_text.strip())
    if style_guide and style_guide.strip():
        parts.append("The house style guide:\n" + style_guide.strip())
    if others:
        parts.append("The draft's other blocks (sent in another part; check for duplicates against them):\n"
                     + "\n".join(f"  - {h}" for h in others))
    parts.append("The draft, block by block:")
    parts += [_block_text(b) for b in blocks]
    parts.append("For each finding give the block's system key exactly as written above and, when it is about a "
                 "line, the line exactly as written above (\"\" for a block-level finding).")
    return "\n\n".join(parts)


def qc_schema() -> dict:
    text = {"type": "string"}
    finding = {"type": "object", "additionalProperties": False,
               "properties": {"system": text, "line": text, "kind": {"type": "string", "enum": list(FINDING_KINDS)},
                              "say": text, "fix": text, "severity": {"type": "string", "enum": list(SEVERITIES)},
                              "quote": text},
               "required": ["system", "line", "kind", "say", "fix", "severity", "quote"]}
    note = {"type": "object", "additionalProperties": False, "properties": {"system": text, "note": text},
            "required": ["system", "note"]}
    return {"type": "object", "additionalProperties": False,
            "properties": {"findings": {"type": "array", "items": finding},
                           "block_notes": {"type": "array", "items": note}, "job_note": text},
            "required": ["findings", "block_notes", "job_note"]}


def _find_block(blocks: dict[str, QcBlock], key: str) -> QcBlock | None:
    if key in blocks:
        return blocks[key]
    folded = key.casefold()
    return next((b for k, b in blocks.items() if k.casefold() == folded), None)


def parse_qc(answer, model: str, blocks) -> QcReport:
    """The QC answer as a report. A finding naming a system the draft does not have, or a line that is not one of
    that block's lines, is dropped and listed; so is one with nothing said or of an unknown kind."""
    by_key = {b.key: b for b in blocks}
    answer = answer if isinstance(answer, dict) else {}
    findings, dropped = [], []
    for raw in answer.get("findings") or ():
        if not isinstance(raw, dict):
            dropped.append("a finding that is not in the asked form")
            continue
        key, line, say = _squash(raw.get("system")), _squash(raw.get("line")), _squash(raw.get("say"))
        about = f"{key}: {line}" if line else key or "(no system)"
        block = _find_block(by_key, key)
        if block is None:
            dropped.append(f"{about} — the draft has no system {key or '(none named)'}: {say}")
            continue
        if line:
            match = next((own for own in block.lines if _squash(own).casefold() == line.casefold()), None)
            if match is None:
                dropped.append(f"{about} — not a line of this block: {say}")
                continue
            line = match
        if not say:
            dropped.append(f"{about} — nothing said")
            continue
        kind = _squash(raw.get("kind")).lower()
        if kind not in FINDING_KINDS:
            dropped.append(f"{about} — unknown kind of finding {kind!r}: {say}")
            continue
        severity = _squash(raw.get("severity")).lower()
        findings.append(QcFinding(block.key, line, kind, say, _squash(raw.get("fix")),
                                  severity if severity in SEVERITIES else CHECK, _squash(raw.get("quote"))))
    notes = {}
    for raw in answer.get("block_notes") or ():
        if not isinstance(raw, dict):
            continue
        key, note = _squash(raw.get("system")), _squash(raw.get("note"))
        block = _find_block(by_key, key)
        if block is None:
            if note:
                dropped.append(f"{key or '(no system)'} — a note on a system the draft does not have: {note}")
            continue
        if note:
            notes[block.key] = f"{notes[block.key]} {note}" if block.key in notes else note
    return QcReport(tuple(findings), notes, _squash(answer.get("job_note")), model, tuple(dropped))


def qc_review_rows(report: QcReport) -> list[ReviewItem]:
    """Each finding as a review row, worded as the QC pass said it, with the suggested line in the action."""
    rows = []
    for f in report.findings:
        if f.line:
            action = f"Change to: {f.fix}" if f.fix else "Remove the line"
        else:
            action = f"Add it: {f.fix}" if f.fix else "Add it"
        rows.append(ReviewItem(f.system, "QC", f.say, f.quote, action,
                               tier=TIER_FIRST if f.severity == MUST_FIX else TIER_DISAGREE, kind="qc"))
    return rows


def split_blocks(blocks, limit: int) -> list[list[QcBlock]]:
    """The blocks in parts whose QC request (blocks only; the caller leaves room for the brief and the rules)
    stays under `limit` characters. A block is never cut in two: one larger than the limit goes alone."""
    parts: list[list[QcBlock]] = []
    current: list[QcBlock] = []
    for block in blocks:
        if current and len(qc_prompt("", current + [block], "", "")) > limit:
            parts.append(current)
            current = []
        current.append(block)
    if current:
        parts.append(current)
    return parts
