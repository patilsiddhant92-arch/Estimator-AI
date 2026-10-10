# Estimator rulings

These are the estimator's (Siddhant's) decisions. **They win over everything**: `lines.json`, `Brain/Quantity rules.txt`,
the GEM, `playbook/`, `Brain/ESTIMATOR_DOCTRINE.md`, `assets/` and `AGENTS.md`. When a ruling and another source disagree,
the ruling holds and the clash is listed in `conflicts.md`.

How to read this file
- One ruling per `### Rn` heading, numbered without gaps. A new ruling takes the next number; a changed ruling is edited
  in place with the new date and a line saying what it replaced.
- **Decided** = ruled by the estimator, with the date and where it was recorded.
- **PENDING estimator** = proposed (by Hark or by a reviewer) but not decided. Do not code a PENDING ruling as settled;
  a scope writer that meets the case asks the question instead.
- Line ids (`vav.01`, ...) point into `lines.json` for wording, order and hours only. `lines.json` never decides that a
  line exists: a line prints only when the job's documents show that device (estimator ruling 2026-10-10).
- No job names, tags, sheet numbers or job text here (AGENTS.md rule 1). Test jobs are Job 1, Job 2a/2b and Job 3.

---

### R1. The schedule says which systems are in the job; the Quantity rules govern quantities
**SUPERSEDED 2026-10-10** by the estimator rulings of 2026-10-10: "the highest count prints; every other differing count prints in a * note with both numbers and sources". Do not apply the count part of R1
(schedule count prints, others only flagged) or its PENDING no-schedule sub-case; kept below as history only.

**Decided 2026-10-09** (`HarkPro/discussion.md:4-5`).
- The equipment schedule decides which systems the job has.
- `Brain/Quantity rules.txt` governs every quantity.
- The schedule count prints. Plan, riser, sheet-text or vision counts that differ are **flagged** as discrepancies
  (the Quantity rules' categories: CONFIRMED, DISCREPANCY, EXTRA, MISSING, ORPHANED, CONFLICT, EXISTING/REMOVAL/REUSE),
  never printed and never used to raise or lower the count.
- Applies as written in the Quantity rules: a duplicate tag row on a schedule is a DISCREPANCY (Rule 7); a type-only
  schedule takes its count from the plans (Rule 8); an indoor/outdoor pair is one system (Rule 9).
- Sub-case **PENDING estimator**: a system with **no schedule at all** (named only in a sequence, a plan note or a
  riser). The hark/fix-all patch prints "the highest count the documents support, flagged as a CONFLICT"; the Quantity
  rules only cover "no schedule total" (Rule 8: plan count) and orphaned items (Rule 3: do not price until confirmed).
  The estimator has not said which applies.

### R2. AME is the mechanical contractor's sub: controls items given to the MC are AME's
**Decided 2026-10-09** (`HarkPro/discussion.md:10`, `HarkPro/bugs.md` "Controls by mechanical = AME scope").
- Any controls item or sensor the documents give to the mechanical contractor ("by MC", "by HVAC contractor",
  "mechanical contractor shall provide ...") is AME's scope, written with the normal AME verb. It is never an
  exception and never "(Furnished by Mechanical Contractor)".
- Examples: an exhaust-fan space thermostat "by MC" → `Furnish and Install Space Thermostat` (`exhaust_fan.09`);
  a leak detector by the MC → `Furnish and Install Leak Sensor` (`leak_detection.01`).
- Not covered: MC work that is not controls (valve bodies and piping stay the MC's; AME still furnishes and wires
  control valves, per the template's `Furnish and Wire ... Control Valve and Actuator`).
- Sub-case **PENDING estimator** (`discussion.md:13`, open item 0): for the EF thermostat, does AME also wire it to
  the fan or starter, or furnish and install it only? Until decided, print the Furnish and Install line and raise the
  question.

### R3. Leak detectors → "Furnish and Install Leak Sensor"; integral refrigerant leak detection → client note
**Decided 2026-10-09** (`HarkPro/discussion.md:24`).
- A drip-pan / water leak detector at a unit prints the Master Template line `Furnish and Install Leak Sensor`
  (`leak_detection.01`, and the same line inside the AC/VRF/split/CRAC/FCU/UV blocks), even when the documents only
  say it is wired to a local alarm panel and name no furnishing party.
- Refrigerant leak detection that is integral to the unit stays a client note:
  `**Refrigeration Leak Detection system is coming with the unit per equipment schedule` (Master Template ¶16).

### R4. Condensate pump → "Tie-in Condensate Pump Float Switch (Furnished by Mfr.)"
**Decided 2026-10-09** (`HarkPro/discussion.md:25`).
- Print the Master Template line `Tie-in Condensate Pump Float Switch (Furnished by Mfr.)` (`condensate_pump.01`;
  also `vrf_system.06`, `split_system.05`, `crac.06`). The bracket is "(Furnished by Mfr.)", never "(Furnished by
  Mechanical Contractor)".
- A pump schedule note such as "provide float operated high water alarm ..." is the pump manufacturer's note
  (see R10); a detail saying "wire to BMS" is what puts the tie-in in AME's scope.

### R5. A local alarm panel → "Furnish and Install Local RAM Module"
**Decided 2026-10-09** (Job 2a review, `HarkPro/bugs.md` "Pipeline: scope misses").
- When leak detectors or a condensate overflow report to a local alarm panel (local audible/visual alarm), print the
  Master Template line `Furnish and Install Local RAM Module` (`leak_detection.02`, `condensate_pump.02`,
  `vrf_system.04`, `split_system.04`, `crac.05`).

### R6. Motorized dampers shown without tags: count every one, trace, else own block
**Decided 2026-10-09** (Job 2a review, `HarkPro/bugs.md`).
- Count every damper actuator shown on the plans, tagged or not. Never assume one per unit.
- Trace each damper's duct to the fan or unit it serves and print `Furnish and Install Damper Actuator` (or the
  block's damper wording) under that fan's or unit's block.
- A damper that cannot be assigned prints in its own Motorized Dampers block (`motorized_dampers.01`) with the sheet
  references and the total count, flagged for the estimator.

### R7. Radiator / perimeter valve interlocked with VAV zone thermostats → interlock wiring line
**Decided 2026-10-09** (Job 2a review, `HarkPro/bugs.md`).
- When the documents run radiator / finned-tube / perimeter heat control valves from each VAV zone thermostat (wired
  separately), print an interlock wiring line per zone, in the template's words
  `Interlock with Associate VAV / FCU/ System Operation` (`finned_tube_radiation.02`), with the valve line
  `Furnish and Wire Hot Water Control Valve and Actuator` when AME furnishes the valve (`finned_tube_radiation.01`).
- Where it prints (the radiation's own block vs the VAV block when the radiation has no tags): the hark/fix-all patch
  puts it in the radiation block when the radiation is scheduled with tags, else in the VAV block. That placement rule
  is Hark's, **PENDING estimator** confirmation.

### R8. Occupancy sensors → an AME line, or an AME-vs-electrical flag
**Decided 2026-10-09 that they must not be dropped** (Job 2a review, `HarkPro/bugs.md`: occupancy sensors on the
controls plan; a thermostat with integral occupancy "by HVAC contractor").
- Every occupancy sensor the controls documents show ends as either an AME line or an ownership flag.
- **PENDING estimator**: which one by default, and the line wording. The Master Template has no occupancy-sensor line;
  `lines.json` carries a proposed `Furnish and Install Occupancy Sensor` (`occupancy_sensors.01`, marked
  `template_exact: false`) and the flag `*Confirm ownership: occupancy sensors (AME vs electrical)`
  (`occupancy_sensors.02`). By R2, sensors given to the HVAC/mechanical contractor are AME's.

### R9. A lighting integration named for the ATC vendor → a front-end line
**Decided 2026-10-09** (Job 2a review, `HarkPro/bugs.md` "Lutron Vive integration for occupied standby").
- When the documents give the ATC / BMS vendor the integration of a lighting control system (e.g. Lutron, for
  occupied standby), print it in the **Front End** block in the Master Template's words:
  `Interface Lighting Control System (By Others) With Front End BMS Via Manufacturer Provided BMS Interface`
  (`front_end.21`; template ¶581-582).
- Print it once. The template keeps the same line under Misc Monitoring Systems (`misc_monitoring` family); with R9 it
  goes in the Front End block, not in both.

### R10. Schedule notes are mostly addressed to the manufacturer / OEM
**Decided 2026-10-09** (stated with the condensate-pump ruling, `HarkPro/discussion.md:23-25, 31`).
- A note on an equipment schedule is the unit or pump manufacturer's instruction unless it names the ATC / controls /
  BMS contractor, or gives BMS wiring ("wire to BMS", "by BMS contractor", "by ATC"). A generic "provide ..." in a
  schedule note is not an assignment to AME (consistent with `playbook/rules.md:105-109`).
- What the note describes is still read: it tells which devices come with the unit (shipped loose, integral, factory
  mounted), which decides the Install and Wire / Tie-in / client-note lines.
- R2 still applies: a schedule note that gives a controls item to the mechanical contractor makes it AME's.

### R11. VAV scope follows the Master Template
**Decided 2026-10-09** (`HarkPro/discussion.md:6`, `HarkPro/bugs.md` VAV row; also `Brain/ESTIMATOR_DOCTRINE.md:50-53`).
- Every VAV / fan powered box / terminal unit: `Furnish DDC Controller to the Factory for Installation` (`vav.01`).
  A "factory-mounted" or "open protocol controller" note is this controller, not the manufacturer's own controls.
- One space sensor, the one the sequence declares: T, T/H, T/H/CO2 or T/CO2 (`vav.02`-`vav.05`).
- `Furnish Fan Enable` only for fan powered boxes (`vav.06`).
- Reheat: `Furnish and Install Discharge Air Temperature Sensor` (`vav.07`) plus the reheat line: hot water valve,
  electric heat enable (DO) or electric SCR (AO) (`vav.08`-`vav.10`).
- 24V: one of `Run 24V Power Loop to VAVs (Mentioned 24 V Wiring Control by BMS Contractor)`,
  `Furnish and Install VAV Transformer`, or `24V VAV Transformer is Coming with the Unit` (`vav.11`-`vav.13`), chosen
  per the template's 24V feedback (¶737-740).
- Tech hours: **3 h** each cooling-only VAV, **4 h** each hot water reheat VAV.
- **PENDING estimator**: hours for an electric-reheat VAV (the template gives only cooling-only and hot water reheat).

### R12. Proposal clarifications are short client lines, colour-coded
**Partly decided.**
- Decided (Master Template ¶14-16, house form): a client note is `**<note>`, printed red **EE0000**.
- **PENDING estimator** (`HarkPro/discussion.md:20` open item 7; `HarkPro/bugs.md` "Colour-coded markers", mockup
  sent 2026-10-09, awaiting review):
  - one short client-facing line per `*` item instead of a long paragraph, the reasoning kept in the Evidence Package;
  - `*Confirm` printed orange **ED7D31**;
  - `*Assumed` printed blue **2F5597**.
  - Note for the decision: in the Master Template orange ED7D31 means "estimator hint, never print" (¶41) and blue
    4472C4 marks alternatives; printing client lines in orange may confuse the two.

### R13. Coverage gate: every controls fact ends somewhere
**PENDING estimator** (Hark proposal, `HarkPro/critique.md` and `HarkPro/bugs.md` "Systemic").
- Every controls-relevant fact read from the documents must end as a line, an exception, a clarification, or a
  dismissal with a reason; an unaccounted fact blocks the proposal.

### R14. New-system opening sentence
**PENDING estimator** (`HarkPro/discussion.md:14`, open item 1). Keep the template's
"A.M.E., Inc, is pleased to provide a quotation on the above project to provide Automated Temperature Controls system."
(`front_end.01`) as written, or reword it.

### R15. Exception reason when the documents give no BMS work
**PENDING estimator** (`HarkPro/discussion.md:15`, open item 2). The fallback reason "NO BMS WORK IN THE CONTRACT
DOCUMENTS" is Hark's wording, not the template's. The exception form itself, "EXCEPTION TO ANY WORK WITH Qty (n)
<tags> - <reason>", comes from `playbook/rules.md:429-431`, not from the Master Template (whose only exception line is
the auto dialer one, ¶125). Note R2: an item "by MC" is never an exception.

### R16. "ALTERNATE #n" with no add or deduct
**PENDING estimator** (`HarkPro/discussion.md:16`, open item 3). Currently planned as an add, with a question raised.

### R17. Empty "DEDUCT ALTERNATES: ALT #:"
**PENDING estimator** (`HarkPro/discussion.md:21`, open item 8; `HarkPro/bugs.md` pipeline). Proposed: drop the
heading when there are no deducts.

### R18. Price book gaps
**PENDING estimator** (`HarkPro/discussion.md:17`, open item 4; DOC-11..14): unpriced items; OAT $50 vs $100;
16 UIO controller $1,000 vs $1,100; markup 15% vs 5%; tax NJ vs NY.

### R19. Unit-scheduled control devices are AME's
**DECIDED by the estimator, 2026-10-09 (Job 4).** When AME provides the controls (including a controller furnished
to the unit manufacturer for factory install), the control devices on the unit schedule (temperature and enthalpy
sensors, freezestat, drain pan level sensor, filter switch) are AME's: Furnish and Install, or furnish to the factory
for installation and wire. Do not print "Install and Wire ... (Furnished by Unit Mfr.)" unless the documents clearly
give the device to the unit manufacturer. When unsure, keep AME's and flag it.

### R20. Damper actuators are Furnish and Install
**DECIDED by the estimator, 2026-10-09 (Job 4).** A damper shown on the plans, control diagram or sequence gets
"Furnish and Install ... Damper Actuator" by AME, even when the equipment schedule lists the damper or actuator with
the unit. Add the *Confirm flag when the schedule says otherwise. "Wire Damper Actuator" is rare.

### R21. Every system block lists all its end devices
**DECIDED by the estimator, 2026-10-09 (Job 4).** A block is never just "Interlock with ..." when the sequence or
control diagram gives it points. Example: exhaust fans list start/stop and status, VFD control, VFD fault and the
damper actuator in the EF block, even when the points land on the AHU controller (that goes in a note).

### R22. The evidence prints the proof, not ids
**DECIDED by the estimator, 2026-10-09.** Evidence sheets show, on every scope line, where the documents say it,
word for word (sheet, page, quote). The estimator never has to follow source ids or line ids.
