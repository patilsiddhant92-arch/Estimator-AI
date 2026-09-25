"""One job, read the way the estimator reads it (build step 4): the equipment from the schedules,
the devices on the plans, the notes that add controls scope, which issue of each sheet governs,
and where the sequence of operation and points list sit."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from estimator.reading.devices import DeviceCount, LegendEntry, TypicalSheet, count_devices, read_legend, typical_sheets
from estimator.reading.inventory import FamilyTotal, InventoryItem, build_inventory
from estimator.reading.keynotes import Note, read_notes
from estimator.reading.pages import PageOpener
from estimator.reading.revisions import SheetVersion, Supersession, governing_pages, sheet_versions, supersede
from estimator.reading.schedules import Schedule, read_schedules
from estimator.reading.sequences import POINTS, SEQUENCE, Backbone, find_backbone

# The categories that need the estimator's eye before pricing; CONFIRMED doesn't.
NEEDS_A_LOOK = ("DISCREPANCY", "MISSING", "EXTRA", "ORPHANED", "PENDING", "TYPE ONLY", "EXISTING")


@dataclass(frozen=True)
class JobReading:
    schedules: tuple[Schedule, ...]
    inventory: tuple[InventoryItem, ...]
    totals: tuple[FamilyTotal, ...]
    devices: tuple[DeviceCount, ...]
    legend: tuple[LegendEntry, ...]
    typicals: tuple[TypicalSheet, ...]
    notes: tuple[Note, ...]
    versions: tuple[SheetVersion, ...]
    supersessions: tuple[Supersession, ...]
    backbone: tuple[Backbone, ...]
    flags: tuple[str, ...]


def read_job(catalogue, page_opener=None, cache_dir: Path | None = None) -> JobReading:
    """Every reading of the job. With no page opener, the job's own PDFs are opened (each once),
    and with a cache folder what was read from each page is kept there for the next run.

    Which issue of each sheet governs is decided first, and the schedules, devices and notes are
    read from the governing page of each sheet number only (a typical sheet from its first page),
    so a sheet in both the base set and an addendum, or in a marked-up copy, is counted once. A
    page that can't be read is skipped and flagged; it never stops the run."""
    versions = sheet_versions(catalogue)
    supersessions, revision_flags = supersede(catalogue, versions)
    typicals = typical_sheets(catalogue)
    pages = governing_pages(catalogue, supersessions, [t.sheet for t in typicals])
    page_flags: list[str] = []
    opener = page_opener or PageOpener(catalogue, cache_dir)
    try:
        schedules = read_schedules(catalogue, opener, pages, page_flags)
        items, totals, inventory_flags = build_inventory(catalogue, schedules)
        legend = read_legend(catalogue, opener, flags=page_flags)
        devices, device_flags = count_devices(catalogue, opener, legend, typicals, pages=pages)
    finally:
        if page_opener is None:
            opener.close()
    notes = read_notes(catalogue, pages)
    backbone, backbone_flags = find_backbone(catalogue)
    flags = page_flags + [f"Equipment: {line[0].upper()}{line[1:]}" for line in inventory_flags]
    flags += device_flags + revision_flags + backbone_flags
    return JobReading(tuple(schedules), tuple(items), tuple(totals), tuple(devices), tuple(legend), tuple(typicals),
                      tuple(notes), tuple(versions), tuple(supersessions), tuple(backbone), tuple(flags))


def _plural(n: int, word: str, many: str | None = None) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {many or word + 's'}"


def families(reading: JobReading) -> list[tuple[str, int]]:
    return [(t.prefix, t.scheduled) for t in reading.totals if t.scheduled]


def needing_a_look(reading: JobReading) -> list[tuple[str, int]]:
    count = Counter(item.category for item in reading.inventory)
    return [(category, count[category]) for category in NEEDS_A_LOOK if count[category]]


def device_labels(reading: JobReading) -> list[tuple[str, int]]:
    count: Counter = Counter()
    for device in reading.devices:
        count[device.label] += device.total
    return count.most_common()


def backbone_summary(reading: JobReading) -> str:
    parts = []
    for what, word in ((SEQUENCE, "sequence of operation"), (POINTS, "points list")):
        found = [b for b in reading.backbone if b.what == what and not b.duplicate_of]
        parts.append(f"{word}: {'; '.join(b.where for b in found[:2]) + (' …' if len(found) > 2 else '')}"
                     if found else f"{word}: none found")
    return "; ".join(parts)


def reading_lines(reading: JobReading) -> list[str]:
    fam = families(reading)
    units = sum(n for _, n in fam)
    look = needing_a_look(reading)
    labels = device_labels(reading)
    controls_notes = sum(1 for n in reading.notes if n.controls)
    tables = sum(1 for v in reading.versions if v.issues)
    lines = [
        f"Equipment: {_plural(units, 'unit')} on the schedules"
        + (f" ({', '.join(f'{p} {n}' for p, n in fam)})" if fam else "")
        + f", from {_plural(len(reading.schedules), 'schedule')}; "
        + (f"to look at: {', '.join(f'{c} {n}' for c, n in look)}." if look else "nothing to look at."),
        f"Devices on the plans: "
        + (", ".join(f"{label} {n}" for label, n in labels[:8]) + (" …" if len(labels) > 8 else "")
           if labels else "no device labels found")
        + f"; the legend explains {_plural(len(reading.legend), 'code')}; "
        + f"{_plural(len(reading.typicals), 'typical floor plan')}.",
        f"Notes: {_plural(controls_notes, 'note')} that add controls scope, of {len(reading.notes)} read.",
        f"Revisions: {_plural(tables, 'sheet')} with a readable revision table; "
        f"{_plural(len(reading.supersessions), 'sheet')} replaced by a later issue.",
        f"Sequence and points list — {backbone_summary(reading)}.",
    ]
    if reading.flags:
        lines.append(f"{_plural(len(reading.flags), 'reading flag')} — see the Flags tab.")
    return lines
