# Playbook proposal: rulings 1 to 19 of 2026-10-11

The text passes the loader and `playbook-lint` on a copy of `playbook/` (97 rules become 108). Code lines are for
`lead/wave2` b6ea499; "Code: new" means no hit in `src/bms` or the older reading code.

## 1. Demolition plans
Merged into ruling 17.

## 2. Part plans
Add to "Counts and quantities":
```
### One unit on two part plans counts once
One unit can show on two part plans that share an area. Count it once. The other labels are duplicates of the same
unit. A short "*" line gives both numbers.
```
The exception to "Never undershoot" is in ruling 17. Code: partly. Ruling L1 merges sheets of other trades, or of one
title with repeated tags (`src/estimator/reading/inventory.py:384-405`).

## 3. Proposal header
Add to "Shapes and wording":
```
### Proposal header
"Quote #" is the job number and "Reference" is the project name, both from the name of the job folder, never the
takeoff folder. Never print a bracket placeholder such as "[project name]". When the job folder gives no project name,
print "***" in red and ask the estimator.
```
Code: exists (T-005c). `src/estimator/writing/front_end.py:376-405` reads the job folder; with no name it prints "***"
in red.

## 4. Existing BMS name; no front end
Partly there: "Front end mode" prints "[existing BMS name]" and flags it; keep it. Add to "Front end":
```
### Existing BMS the house works with
AME works only with Honeywell WEBS, Johnson FX and Niagara Tridium. Those names print plain. Any other name prints in
red as "***<name>***" wherever it appears: in the front end heading and in the opening sentence. The front end then
gets one flag line: "***AME works only with Honeywell WEBS, Johnson FX (Facility Explorer) or Niagara Tridium front
ends". The fill-in "[existing BMS name]" prints the same way, with no flag line.

### No front end called for
When the documents call for no front end, the front end of the proposal says "No front end information found".
```
Code: exists (T-005c). `src/bms/render.py:49-52`, `:863-875`; `src/estimator/proposal/write.py:56-66`, `:257`.

## 5. Short points
Covered by ruling 14.

## 6. Stated facts, no "Assumed"
Add to "Clarifications and assumptions":
```
### A stated fact is not an assumption
When a schedule or the sequence states a fact, write it as stated and cite it. Never print "Assumed" for it.
```
Code: new.

## 7. FUTURE items and red flags
Add to "Clarifications and assumptions":
```
### Red flags for the estimator
An item the documents mark FUTURE prints as its normal line, then "(FUTURE AS PER <source>)" in red font, naming the
sheet or section. An item the estimator must notice, such as an integral drain pan level sensor that the factory
furnishes, is highlighted red in the scope. Red marks what the estimator must see.
```
Code: partly. Printing exists (`src/bms/model.py:152-158`, `src/bms/render.py:833`); the writer prompts do not set the
mark.

## 8. Valves under their unit
Add to "Shapes and wording":
```
### Valves under their unit
A control valve and its actuator are written in the block of the unit they serve (an air handler, a fan coil), never
in a separate valve system. The plans, risers and sequence show which unit. When none can be traced, ask the
estimator.
```
In "One system one block" replace `rule and the dampers rules say` with `rule, the dampers rules and the valves rule
say`. Code: new.

## 9. Pumps by service
Covered by ruling 18.

## 10. Loose devices on unit schedules
Mostly there. In "Shipped-loose devices", after "Write out every manufacturer-furnished device ..." add:
> A unit schedule (an ERV, an RTU or any other unit) can list end devices shipped loose, in a column or a note. Read it, and write each one as a line.

Code: partly. `src/bms/validate.py:251-262` checks verb and parties only; `src/bms/coverage.py:15` reports an uncited
device fact.

## 11. Review page: each question once
Change "Questions for the estimator": add at the end:
> A question is asked once. A question that holds for a whole family is asked once for the family, never per unit or per line.

Code: new. `src/bms/review.py:99-136` merges findings of one device only.

## 12. Off-hours work and prevailing wage
Add to "Exceptions and alternates":
```
### Off-hours work and prevailing wage
When the documents name off-hours work (for example 6 PM to 6 AM) or prevailing wage, add each to the proposal and to
the price sheet, highlighted red. Never exclude either one silently. The standard exclusion "All off-hours or overtime
labor" does not stand against it.
```
The last sentence is mine: the proposal template fixes the exclusion "All off-hours or overtime labor." Code: new.

## 13. Master Template format and GEM order
Already there: "Template gives shape only" and "Standard order". Rulings 14, 15 and 16 answer the handover's details.
"'**' lines are estimator hints" needs no change: "Client notes" stays; the template's "**tech hour" lines are
guidance.

## Rulings 14 to 19 (2026-10-11 afternoon)
### 14. Short "*" lines, red for the estimator
Change "One clarification per block": replace its last sentence (on the quantity note) with:
> Each "*" line is one short line, never a paragraph. Several "*" lines in one block are fine when each is a different item. A "*" line that the estimator must see prints in red.

Code: partly. `src/bms/render.py:65-90` splits a "*" line over 150 characters into points; `src/bms/validate.py:405-410`
refuses a second clarification.

### 15. Quantities print in the line
Add to "Counts and quantities":
```
### Quantities print in the line
A quantity prints in the line it counts: "Qty (n) <device>" in a header or a count line, "(Qty. N Total)" after the
device on a scope line. There is no separate quantity note. When two counts differ, the line prints the highest and
names each other count with where it is, in brackets, for example "(4 per plan placements)".
```
Delete "Last comes the quantity note ... still prints)." in "Joining into the one clarification". In "Higher count
prints" replace the last two sentences with:
> Every count that differs from the printed one prints in the same line (see Quantities print in the line).

Code: the opposite. `src/bms/render.py:531` and `:721-723` print the separate note; `wording.json` requires it
(`src/bms/playbook.py:476`). One test pins the old "Higher count prints" sentence: `tests/bms/test_playbook_edits_1010.py:145-147`.

### 16. Tech hours: guidance only
Change "Tech hours never print": add at the end:
> The Master Template's tech-hour lines ("**tech hour: ...") are guidance for the estimate, not lines of the proposal.

Code: exists. Tech hours reach only the price sheet and the Evidence Package (`src/estimator/price_sheet/rows.py:68`,
`src/estimator/evidence/workbook.py:590`).

### 17. Demolition Scope
Add to "Counts and quantities":
```
### Demolition Scope
A demolition plan shows the previous job's units: removed, remaining or relocated. Their count never goes into the
new-work blocks. It prints in one block headed "Demolition Scope", the last block of the scope, in lines such as "Qty
(n) AHU demo", "Qty (n) FCU Existing to Remain" and "Qty (n) VAV Relocation". Named work on such a unit, such as
refurbishing it or relocating its sensors or thermostat, is a line of this block.
```
Change "Never undershoot": add at the end:
> The only exceptions, here and in Higher count prints, are the units on demolition sheets, whose count moves to Demolition Scope with its number, and a duplicate label of one unit on two part plans, which a short "*" line names with both numbers.

Code: new. `src/estimator/reading/inventory.py:690` counts demolition sheets; the block needs a later shape `order`
(`src/bms/render.py:779`).

### 18. Pumps by plant or by service
Add to "Shapes and wording":
```
### Pumps by plant or by service
When the plant (chillers, boilers or the like) is in the job's scope and the pumps serve it, the pumps are part of the
plant block. When the job shows remote pumps, each service is its own block: chilled water pumps in one, hot water
pumps in another. The documents decide. The block header makes clear which case it is.
```
`shapes.json`, as a conditional with nothing removed: keep the pump families and slots in the plant shapes (the plant
case). Add "Chilled Water Pumps" and "Hot Water Pumps" shapes, pump slots only, for remote pumps. CHWP and HWP already
pick the plant shapes (`src/bms/playbook.py:117-135`).

Code: new. `src/bms/plan.py:538-585` plans condensate pumps only.

### 19. Front end house lines
Change "Front end lines cite the specification": replace its first sentence with:
> The house front end lines are the standard lines that the Master Template's front end section defines, with the reason for each. Write each one as that section says and cite that section. Every other front end line (PC workstation, BMS server, portable operator terminal, UPS, IT infrastructure) is written only when this job's specification calls for it, with its citation.

Add at the end of "No standard or fallback lines" and of "Template gives shape only":
> The front end house lines are the one exception.

Code: partly. `src/bms/prompts/write_front_end.md:12` writes a line only when the documents call for it;
`src/bms/plan.py:1469` holds no standard line.

## Open points
1. GEM item 20 puts Miscellaneous Responsibilities after the integration lines; "Standard order" puts them before.
   Which one?
2. Does red text come out at sign-off?
3. My readings: (15) "Qty (n) <device>" is the header and count-line form, a scope line keeps "(Qty. N Total)", other
   counts go in brackets; (17) "last" is the last block of the scope.
