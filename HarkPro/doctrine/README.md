# HarkPro doctrine: one source for the estimating flow

Four files replace the eight overlapping doctrine sources (Master Template, GEM v3.2/v4, `playbook/rules.md`,
`shapes.json`, `wording.json`, `ESTIMATOR_DOCTRINE.md`, `ame_practice.txt`, AGENTS).

| File | What it is |
|---|---|
| `rulings.md` | The estimator's dated, numbered decisions (R1..). **Win over everything.** PENDING items are questions, not rules. |
| `lines.json` | The Master Template as data: 39 families, 438 lines in the template's exact wording, with when each applies, ownership, tech hours and price-book items. |
| `conflicts.md` | Every place an old source contradicts the two files above, with file:line and the winner. |
| `check_doctrine.py` | Validator. Run it after every edit. |

Built 2026-10-09 on `hark/harkpro-notes`. Nothing outside `HarkPro/` was changed; the old sources still drive the app
until the estimator approves the edits listed in `conflicts.md`.

## Precedence

1. **`rulings.md`** (decided rulings only)
2. **`lines.json`** (which lines exist, their exact words, when they apply)
3. **`Brain/Quantity rules.txt`** (every count; R1 makes it the quantity authority)
4. Everything else: `playbook/rules.md`, `shapes.json` (slot order, header forms), `wording.json` (brackets, qty forms),
   GEM v3.2/v4, `ame_practice.txt`, `ESTIMATOR_DOCTRINE.md`, AGENTS files. Use them only where 1-3 are silent.

The job's documents still decide **which** systems are in the job (R1: the schedule) and which conditions hold; the
doctrine decides **how** each system is written.

## How a scope writer uses it

1. **Systems.** Take the systems from the equipment schedule (R1). Match each to a family by `aliases` (tag prefixes and
   names) and, where an alias is shared (AC/ACCU in VRF and split; EF in exhaust fans and gas detection), by what the
   documents say the system is.
2. **Counts.** Apply `Brain/Quantity rules.txt`. The schedule count prints; every other count is a flag (R1).
3. **Variant.** If the family has `variants` (front end new/existing, exhaust fan interlocked/field DDC, UV field
   DDC/DDC ready, unit heater electric/DDC/water, VRF central controller/BMS interface ...), pick the one the documents
   describe. Lines without a `variant` apply to every variant.
4. **Lines.** Walk the family's `lines` in order:
   - `required: true` → print it whenever `applies_when` holds (house default; no separate citation needed).
   - `required: false` → print it only when this job's documents call for it, citing them.
   - `alt_group` → print at most one line of the group (the template's OR); choose by `applies_when`.
   - `depth: 2` + `parent` → prints one level in, under its parent; never without the parent.
   - Fill placeholders (`{n}`, `{qty}`, `{tags}`, `{size}`, `{sheet}`, `{location}`, `{existing_bms}` ...) from the job.
     Everything else in `text` is printed exactly as written.
   - `template_exact: false` → wording comes from a ruling, not the template; check the ruling is not PENDING.
5. **Ownership.** `owner_furnish / owner_install / owner_wire` give the default. R2 overrides it: anything the
   documents give to the mechanical contractor that is a control or sensor is AME's.
6. **Cross-system facts.** Before closing a block, check the job's whole fact list for: leak detectors (R3), condensate
   pumps (R4), local alarm panels (R5), untagged dampers (R6), radiator/perimeter valves tied to VAV zones (R7),
   occupancy sensors (R8), lighting integration (R9). These live on other sheets than the system's own schedule.
7. **Schedule notes** are the manufacturer's unless they name the ATC/BMS contractor or give BMS wiring (R10).
8. **Client notes / clarifications.** `**` client notes (red EE0000) from `client_notes` and `format.client_note_forms`.
   The short-line and colour rules for `*Confirm` / `*Assumed` are PENDING (R12).
9. **Hours and price.** `tech_hours` (never printed) and `price_items` / `price_item` (names exactly as in
   `assets/price_book/AME Std Pricing Spreadsheet.xlsx`; `aliases.json` is still empty). `null` hours = not in the
   template; leave for the estimator.
10. **Never print** orange (ED7D31 / E36C0A) template text: those are `estimator_hints`.

## Job data

The Master Template's samples carry job data (tag lists, valve sizes, sheet numbers, floors, firm and client names, job
numbers). Per AGENTS.md rule 1 these are replaced by placeholders; each affected line lists what in `redacted`. Lines
with a header or label around them in the template carry `trimmed`.

## Running the validator

```
.venv/bin/python HarkPro/doctrine/check_doctrine.py \
    --docx "Brain/Master Template.docx" \
    --price-book "assets/price_book/AME Std Pricing Spreadsheet.xlsx"
```

Checks: schema and enums; every line has a source; no duplicate family or line ids; parents/variants resolve; every
exact-wording line matches its template paragraph (needs python-docx); every price item exists in the price book
(needs openpyxl); `rulings.md` numbered without gaps, each dated or PENDING. Last run 2026-10-09: OK (319 lines
matched word for word, 63 price items found, 18 rulings), one warning (the warranty sentence is over 160 characters).

## Ambiguities in the template the estimator must decide

Numbered A1.. (`conflicts.md` refers to them).

- **A1. Red means two things.** EE0000 is the `**` client-note colour (¶14-16), but EE0000 also marks two job-specific
  *lines* (UPS for DDC controller ¶362/394/637; one tag ¶402), and FF0000 marks sample words to replace (¶74, ¶78) and
  either/or markers (¶516/526, ¶681, ¶707 "Condenser Interlock Wiring"). Which red is "print as client note"?
- **A2. One single-`*` blue note.** ¶249 "*Fans Are Controlled via Fire Alarm System" is blue 4472C4 with one `*`; every
  other client note is red `**`. Client note or confirm item?
- **A3. Template noun vs document noun.** Keep "Space Temperature Sensor" when the documents say "zone sensor" /
  "thermostat"? (GEM says device names always come from the documents.)
- **A4. Placeholders in the template.** `ABC`, `##`, `#`, `###`, `****`, `*****` are all used; lines.json maps them to
  `{device}`, `{n}`, `{size}`, `{medium}`, `{unit}`. Confirm `###` in the HX block means the water medium (hot/chilled/
  condenser).
- **A5. Humidifier valve verb.** ¶320 "Furnish Humidifier Control Valve and Actuator": every other valve is Furnish
  and Wire.
- **A6. Cut-off or questioning lines.** ¶489 "Furnish and Install BACnet Thermostat (when sequence / point list" ends
  mid-sentence; ¶63 "IT Infrastructure – By AME or by Others?" is a question, not a line; ¶113 "Nest Thermostat
  ( Alternate) check schedule for notes)" mixes a line and a hint. Exact print wording?
- **A7. Hours not in the template**: front end, existing FCU relocation, interlocked exhaust fans, smoke purge fans,
  packaged ERU/RTU/AHU (the app uses 16 h, source unknown), equipment VFD (app uses 4 h), electric-reheat VAV,
  condensate pumps, motorized dampers, occupancy sensors.
- **A8. "Per what" hours.** Kitchen "40 hour each" (each fan? each system?); EF "4 hour each fan if gets more points"
  (and if not?); Misc Monitoring "2 hour per triangle bullet multiplied by qty" (which level is a triangle bullet?).
- **A9. Condenser Water block** prints Map Available Points and the rep line (¶463-464) without the comm-wiring line,
  and the Hot Water block likewise (¶624-625). Intentional, or print the full trio?
- **A10. Highlights.** Bright-green highlighted headers and yellow-highlighted boiler lines (breakglass, CO sensor,
  horn/strobe ¶613/616/617): meaning not stated.
- **A11. Lighting interface placement.** The template puts it under Misc Monitoring (¶581); R9 says Front End. Confirm
  it moves for every lighting integration, or only when named for the ATC vendor.
- **A12. Job-specific feedback** (¶713-750): the hotel guest-room thermostat entry has no quote source ("Get quote
  from" blank); the balancing entry has no print wording; one entry is tied to a single engineer's jobs. Which become
  lines or client notes?
- **A13. Condensate pump block.** Print the tie-in inside the served unit's block, or as its own block when pumps are
  scheduled on their own (Job 2a had them scheduled)?
- **A14. Electric FTR.** ¶174-175 has only the interlock line (no device). Confirm.
