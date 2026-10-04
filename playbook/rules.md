# AME Playbook — the rules

<!--
Format (read by src/bms/playbook.py; the whole file is also the cached instructions of every AI step):
- One "## " heading per topic. Topics are fixed below; a new topic needs the controller.
- Under a topic, each rule is a "### " heading with its short name, then plain sentences.
  The short name is the rule's id: a validator's or the QC pass's Finding.rule is exactly this name.
- Rule names are unique across the file. No rule outside a topic. No empty rule.
- A rule marked with an HTML comment "sample" right under its heading is a format example from Phase 0;
  workstream 1 replaces it with the real rule and removes the marker.
- Plain words only: no invented codes, no example from another job.
-->

## Evidence and citations

### Every line cites this job
<!-- sample -->
A device line is written only when this job's documents call for it, and it carries at least one citation: the
source id, the exact words and where they are. There is no standard line, no fallback line and no line taken from
another job.

## Ownership

## Counts and quantities

## Clarifications and assumptions

## Packaged units

### Packaged units
<!-- sample -->
A unit that comes with its manufacturer's own controls is a packaged unit. AME does not furnish the points the unit's
controls already have; AME connects to the unit through its manufacturer's interface and maps the available points.

## Shipped-loose devices

## Dampers under their fan

## Duct heaters

## VRF and split systems

## Integration lines

## UUKL

## Residential equipment

## Front end

## Exceptions and alternates

## Tech hours

## Shapes and wording
