# Playbook edits draft (not applied)

Status: DRAFT for the lead. No file in the repo was edited. The patched copies that I used for checks are in the
scratchpad (see "Verification").

## Basis

- Playbook files: branch `rebuild` at 8ccd0b3. All line numbers are lines of these files on `rebuild`. The quoted
  files are byte for byte these blobs: rules.md 5fc504a, shapes.json 58c06e3, wording.json 300efeb, GEM v4 34da05c,
  ame_practice.txt 0a89304.
- Rulings R1 to R18: `HarkPro/doctrine/rulings.md` on `origin/main` (a54ea82). R19 to R22: the newer file on
  `origin/hark/harkpro` (f3485b6). The text of R1 to R18 is the same in both files. `conflicts.md` is the same in both.
- Master Template words and hours: `HarkPro/doctrine/lines.json` (same refs). They are used as wording and hours only.

## Decisions of 2026-10-10 that the drafts follow

1. Evidence only. A line prints only when the job's documents show that device. The Master Template gives wording,
   order and hours, never a reason for a line to exist. Not drafted: the lines.json "required" flags and conflicts
   C11 to C16. The current text stays (rules.md "No standard or fallback lines", "Front end lines cite the
   specification", "Template gives shape only"; the "Never content" sentence in shapes.json line 3).
2. The highest count prints. Every other count that differs prints in a "*" note with both numbers. This replaces R1.
3. R2 to R22 are accepted as decided, with three exceptions. R1 is replaced (decision 2). R11 is limited to wording
   and hours (decision 1). Every part marked PENDING stays out. Those parts are in "Pending sub-cases (not drafted)".

## How to read this draft

- Edit ids: RULES-n is `playbook/rules.md`. SHAPES-n is `playbook/shapes.json`. GEM-n is
  `assets/gem/BMS_DDC_GEM_v4.txt`. PRACTICE-n is `assets/gem/ame_practice.txt`. `playbook/wording.json` has no edit.
- A "replace" edit swaps one whole rule, or the quoted lines of JSON. "Current text" is the text on `rebuild`.
  "Proposed text" is the text after the edit. In a replaced rule, the lines before the first changed word keep their
  line breaks, so a diff shows only the change.
- A line range of a rule includes its heading line.
- An "add" edit gives a new rule and says where it goes.
- The proposed rules follow `playbook_lint`: no arrows, no emoji, no source ids, no repeated rule name. Every
  "(see ...)" names a rule that exists after the edits. No ruling number is in the proposed text.
- GEM-n and PRACTICE-n are second priority. The app reads `rules.md`, not the GEM. These edits keep the older
  writing sources from contradicting the rulings.

## Edit index

| Edit | File | Where | Rulings | What it does |
|---|---|---|---|---|
| RULES-1 | rules.md | lines 160-162 | D2 | Higher count prints |
| RULES-2 | rules.md | lines 77-84 | R2 | Who owns what by default |
| RULES-3 | rules.md | new rule after the rule "Explicit assignment always wins" | R2 | Controls given to the mechanical contractor |
| RULES-4 | rules.md | new rule after the new rule "Controls given to the mechanical contractor" (RULES-3) | R10 | Schedule notes address the manufacturer |
| RULES-5 | rules.md | lines 121-126 | R2, R4 | Other trades in brackets |
| RULES-6 | rules.md | new rule after the rule "Other trades in brackets" | R3 | Leak detectors |
| RULES-7 | rules.md | new rule after the new rule "Leak detectors" (RULES-6) | R4 | Condensate pump float switch |
| RULES-8 | rules.md | new rule after the new rule "Condensate pump float switch" (RULES-7) | R5 | Local alarm panel |
| RULES-9 | rules.md | lines 204-213 | R3, R12 | Client notes |
| RULES-10 | rules.md | lines 238-244 | R3, R4, R5 | Packaged units |
| RULES-11 | rules.md | lines 249-252 | R3, R4, R19, R20 | Nothing inside the unit is a line |
| RULES-12 | rules.md | lines 254-256 | R19 | Factory-installed devices |
| RULES-13 | rules.md | new rule after the rule "Factory-installed devices" | R19 | Unit control devices when AME provides the controls |
| RULES-14 | rules.md | lines 264-269 | R19 | Shipped-loose devices |
| RULES-15 | rules.md | new rule after the rule "Dampers under their fan" | R6 | Count every damper |
| RULES-16 | rules.md | new rule after the new rule "Count every damper" (RULES-15) | R20 | Damper actuators are Furnish and Install |
| RULES-17 | rules.md | new rule after the rule "Everything assigned is extracted" | R8 | Occupancy sensors are never dropped |
| RULES-18 | rules.md | new rule after the rule "Front end items by others" | R9 | Lighting control integration |
| RULES-19 | rules.md | lines 429-433 | R10, R2 | Named exceptions |
| RULES-20 | rules.md | new topic, before "VRF and split systems" | R11 | VAV lines |
| RULES-21 | rules.md | new rule after the new rule "VAV lines" (RULES-20) | R7 | Radiation valves tied to VAV zone thermostats |
| RULES-22 | rules.md | new rule after the rule "Minimum points on AME-run equipment" | R21 | Every block lists its end devices |
| RULES-23 | rules.md | lines 128-131 | R21 | Point lines only on AME controllers |
| RULES-24 | rules.md | lines 200-202 | R22 | Assumption wording has no source ids |
| SHAPES-1 | shapes.json | lines 1876-1877 | R4 | VRF System: slot condensate_float_switch, wording |
| SHAPES-2 | shapes.json | lines 1932-1933 | R4 | Split System: slot condensate_float_switch, wording |
| SHAPES-3 | shapes.json | lines 1990-1991 | R4 | Computer Room Air Conditioning Unit: slot condensate_float_switch, wording |
| SHAPES-4 | shapes.json | lines 2053, 2062-2063, 2073-2074 | R9 | Front End: new slot lighting_interface (3 places) |
| SHAPES-5 | shapes.json | lines 1764, 1770-1771, 1787-1788 | R9 | Misc Monitoring Systems: slot lighting_interface removed (3 places) |
| SHAPES-6 | shapes.json | line 75 | R11 | VAV / Fan VAV: slot power_loop, wording |
| SHAPES-7 | shapes.json | lines 583, 586-590, 610-613 | R2 | Exhaust Fan: new slot space_thermostat (3 places) |
| GEM-1 | BMS_DDC_GEM_v4.txt | line 105 | R2 | SCOPE OWNERSHIP, the Mechanical contractor line |
| GEM-2 | BMS_DDC_GEM_v4.txt | line 120 | R2 | DEVICE OWNERSHIP RESOLUTION, question 1 |
| GEM-3 | BMS_DDC_GEM_v4.txt | line 247 | R4 | OTHER TRADES IN BRACKETS |
| GEM-4 | BMS_DDC_GEM_v4.txt | line 294 | R3, R4, R5, R20 | PACKAGED UNITS, WHAT IS INSIDE THE UNIT IS NOT A LINE |
| PRACTICE-1 | ame_practice.txt | line 24 | R4 | OWNERSHIP ANSWERS, answer (3) |

## Count of edits

| File | Edits | Replace | Add | Note |
|---|---|---|---|---|
| playbook/rules.md | 24 | 11 | 13 | 13 new rules. One of them is in a new topic. |
| playbook/shapes.json | 7 | 7 | 0 | 13 separate text changes. Two edits add a slot. One removes a slot. |
| playbook/wording.json | 0 | 0 | 0 | See "wording.json: no edit". |
| assets/gem/BMS_DDC_GEM_v4.txt | 4 | 4 | 0 | Second priority. |
| assets/gem/ame_practice.txt | 1 | 1 | 0 | Second priority. |

## Points to confirm before applying

I made these readings where a ruling is not exact. Each one is also in the note of its ruling.

1. R4, tie-in: it prints when the documents have the BMS wire to the float switch, not for every condensate pump
   (RULES-7). Is that the intent? If yes, "VRF lines" and the practice paragraph "VRF SYSTEMS" ("when there are
   condensate pumps") need the same condition. I did not draft that edit.
2. R4, bracket: SHAPES-1 to SHAPES-3 print "(Furnished by Mfr.)" as fixed text. The Unit Mfr. bracket would need no
   shape edit but reads "(Furnished by Unit Mfr.)". Which one?
3. R7: one interlock line for all zones, or one line for each zone? The template spells "Associate". The shape prints
   "Associated".
4. R9: remove the old slot in Misc Monitoring (SHAPES-5), or keep it and rely on RULES-18?
5. R11: does the bracket "(Mentioned 24 V Wiring Control by BMS Contractor)" print (SHAPES-6, RULES-20)? Is a new topic
   "VAV boxes and radiation" allowed (RULES-20, RULES-21)?
6. R20: does it reach a damper inside a unit on factory controls (for example an economizer damper)?
7. R3: the general "**<ITEM> BY UNIT MFR." form stays (RULES-9). Only the leak example changed. Correct?
8. R21: "a note" is read as a client note. An exhaust fan with points and no controller line gets no tech hours today.
9. GEM-1 to GEM-4 and PRACTICE-1: apply them with the Playbook, or leave the GEM and the practice rules as they are?

## Rulings, one by one

### R1. Replaced by decision 2

R1 (the schedule count prints; other counts are flagged) is replaced as a whole. No text of R1 is drafted. Decision 2
is drafted next. The other parts of R1 are not carried over. They are listed in "Pending sub-cases (not drafted)".

### Decision 2 (replaces R1): the highest count prints, other counts print as a "*" note

Decides: The highest count prints, and every other count that differs prints in a "*" note with both numbers (this replaces R1).

Edits: RULES-1.

The Playbook already agrees in these places (no edit): "Never undershoot" (rules.md lines 164-166), "Line quantity"
(168-170), the quantity note in "Joining into the one clarification" (187-192), `wording.json` `quantity.others_note`
(it prints "*Qty. (N) per ...; M per ..."), GEM v4 line 594 and the practice paragraph "CONTRADICTED COUNTS" (both
already name both counts beside the printed one). The code agrees too (see "Code that must change").

#### RULES-1 (replace): rule "Higher count prints"
- File and lines: playbook/rules.md, lines 160-162.
- Rulings: D2.
- Change: Keeps the current sentences and adds the required "*" quantity note that holds both numbers.

Current text:
```text
### Higher count prints
When the documents give different counts, the highest count prints, flagged, and every other count is named with
where it is. The estimator decides on review.
```

Proposed text:
```text
### Higher count prints
When the documents give different counts, the highest count prints, flagged, and every other count is named with
where it is. The estimator decides on review. Every count that differs from the printed one prints in the block's
"*" quantity note, beside the printed count, with both numbers and where each one is: "*Qty. (6) per the schedule;
4 per plan placements." The note is written whenever two counts differ.
```

### R2. AME is the mechanical contractor's subcontractor: controls items given to the MC are AME's

Decides: A controls item that the documents give to the mechanical contractor is AME's scope, because AME is the mechanical contractor's subcontractor.

Edits: RULES-2, RULES-3, RULES-5, SHAPES-7, GEM-1, GEM-2. Also uses: RULES-19 (shown under R10).

- `wording.json` keeps the "Mechanical Contractor" owner bracket. The loader needs a bracket for every party
  (`bms.playbook.load_wording`, `PARTIES` in `bms.model`). RULES-5 says that a controls item has no such bracket.
- SHAPES-7 gives the exhaust fan shape a place for the space thermostat (the ruling's example, line exhaust_fan.09 in
  lines.json). Without it the AI must use `space_temperature` or `other_device`.
- Pending: whether AME also wires that thermostat to the fan or starter. See "Pending sub-cases".

#### RULES-2 (replace): rule "Who owns what by default"
- File and lines: playbook/rules.md, lines 77-84.
- Rulings: R2.
- Change: The mechanical contractor keeps valve bodies and piping only. A controls item given to the mechanical contractor is AME's.

Current text:
```text
### Who owns what by default
Work that belongs to another party is not AME's scope unless the documents give it to AME. Fire alarm contractor:
fan start/stop through the fire alarm, smoke and duct detectors, any command the fire alarm starts. Mechanical
contractor: valve bodies, piping, unit-mounted safeties not assigned to the controls contractor. Electrical
contractor: VFDs unless the controls contractor furnishes them, line-voltage wiring, conduit, disconnects. Unit
manufacturer: factory-mounted sensors, factory controls, isolation valves and internal safeties. Owner: anything
the specification calls owner-furnished. Sheet metal contractor: ductwork, and installing airflow measuring
stations.
```

Proposed text:
```text
### Who owns what by default
Work that belongs to another party is not AME's scope unless the documents give it to AME. Fire alarm contractor:
fan start/stop through the fire alarm, smoke and duct detectors, any command the fire alarm starts. Mechanical
contractor: valve bodies and piping. AME is the mechanical contractor's subcontractor for controls, so a controls
item or sensor that the documents give to the mechanical contractor is AME's (see Controls given to the mechanical
contractor). Electrical contractor: VFDs unless the controls contractor furnishes them, line-voltage wiring,
conduit, disconnects. Unit manufacturer: factory-mounted sensors, factory controls, isolation valves and internal
safeties. Owner: anything the specification calls owner-furnished. Sheet metal contractor: ductwork, and installing
airflow measuring stations.
```

#### RULES-3 (add): new rule "Controls given to the mechanical contractor"
- File: playbook/rules.md. It goes after the rule "Explicit assignment always wins" (it ends at rules.md line 109). Topic: Ownership.
- Rulings: R2.
- Change: New rule. It states that AME is the mechanical contractor's subcontractor for controls.

Current text: none. This is a new rule.

Proposed text:
```text
### Controls given to the mechanical contractor
AME is the mechanical contractor's subcontractor for controls. A controls item or sensor that the documents give to
the mechanical contractor ("by MC", "by HVAC contractor", "mechanical contractor shall provide ...") is AME's
scope. It is written with the normal AME verb. It is never a named exception and never "(Furnished by Mechanical
Contractor)". An exhaust fan space thermostat "by MC" is "Furnish and Install Space Thermostat". A leak detector
"by MC" is "Furnish and Install Leak Sensor". Work that is not controls stays with the mechanical contractor: valve
bodies and piping. AME still furnishes and wires the control valve and its actuator.
```

#### RULES-5 (replace): rule "Other trades in brackets"
- File and lines: playbook/rules.md, lines 121-126.
- Rulings: R2, R4.
- Change: Removes the mechanical contractor bracket for condensate pumps and float switches. Adds the "(Furnished by Mfr.)" bracket of the float switch. Says that a controls item given to the mechanical contractor has no bracket.

Current text:
```text
### Other trades in brackets
Name the furnishing party in brackets after the device: "(Furnished by Unit Mfr.)" for the unit manufacturer;
"(Relay Furnished by FA)" for fire alarm relays and signals; "(Furnished by Others)" for dampers and end switches by
the sheet metal contractor; "(Furnished by Mechanical Contractor)" for condensate pumps and float switches;
"(Furnished by Electrical Contractor)" and "(Furnished by Owner)" when those parties furnish. The bracket names
only the furnishing party; who installs is kept in the Evidence Package, not printed.
```

Proposed text:
```text
### Other trades in brackets
Name the furnishing party in brackets after the device: "(Furnished by Unit Mfr.)" for the unit manufacturer;
"(Relay Furnished by FA)" for fire alarm relays and signals; "(Furnished by Others)" for dampers and end switches by
the sheet metal contractor; "(Furnished by Mfr.)" for the condensate pump float switch (see Condensate pump float
switch); "(Furnished by Electrical Contractor)" and "(Furnished by Owner)" when those parties furnish. A controls
item that the documents give to the mechanical contractor is AME's and has no bracket (see Controls given to the
mechanical contractor). The bracket names only the furnishing party; who installs is kept in the Evidence Package,
not printed.
```

#### SHAPES-7 (change), shape "Exhaust Fan": new slot space_thermostat (3 places)
- File: playbook/shapes.json.
- Rulings: R2.
- Change: Adds a slot for the space thermostat after space_temperature, kind device, generic wording.

Text change 1 of 3, playbook/shapes.json, line 583.

Current text:
```json
      "line_order": ["interlock", "controller", "space_temperature", "duct_static", "start_stop_status", "vfd_control", "damper_actuator", "other_device", "other_point", "fire_alarm", "other_valve", "other_install_and_wire", "other_wire", "other_interlock", "other_wiring", "vfd_comm_wiring", "vfd_map_points", "vfd_rep_assist", "comm_wiring", "map_points", "rep_assist"],
```

Proposed text:
```json
      "line_order": ["interlock", "controller", "space_temperature", "space_thermostat", "duct_static", "start_stop_status", "vfd_control", "damper_actuator", "other_device", "other_point", "fire_alarm", "other_valve", "other_install_and_wire", "other_wire", "other_interlock", "other_wiring", "vfd_comm_wiring", "vfd_map_points", "vfd_rep_assist", "comm_wiring", "map_points", "rep_assist"],
```

Text change 2 of 3, playbook/shapes.json, lines 586-590.

Current text:
```json
        "controller": "device",
        "space_temperature": "device",
        "duct_static": "device",
        "start_stop_status": "point",
        "vfd_control": "point",
```

Proposed text:
```json
        "controller": "device",
        "space_temperature": "device",
        "space_thermostat": "device",
        "duct_static": "device",
        "start_stop_status": "point",
        "vfd_control": "point",
```

Text change 3 of 3, playbook/shapes.json, lines 610-613.

Current text:
```json
        "space_temperature": "{verb} {device}{owner}{qty}",
        "duct_static": "{verb} {device}{owner}{qty}",
        "start_stop_status": "{verb} {device}{owner}{qty}",
        "vfd_control": "{verb} {device}{owner}{qty}",
```

Proposed text:
```json
        "space_temperature": "{verb} {device}{owner}{qty}",
        "space_thermostat": "{verb} {device}{owner}{qty}",
        "duct_static": "{verb} {device}{owner}{qty}",
        "start_stop_status": "{verb} {device}{owner}{qty}",
        "vfd_control": "{verb} {device}{owner}{qty}",
```

#### GEM-1 (change): SCOPE OWNERSHIP, the Mechanical contractor line
- File: assets/gem/BMS_DDC_GEM_v4.txt.
- Rulings: R2.
- Change: Valve bodies and piping only. Controls items given to the MC are the controls contractor's.

assets/gem/BMS_DDC_GEM_v4.txt, line 105.

Current text:
```text
  Mechanical contractor (MC): valve bodies, piping, and unit-mounted safety devices not explicitly assigned to the BMS.
```

Proposed text:
```text
  Mechanical contractor (MC): valve bodies and piping. The controls contractor is the MC's subcontractor for controls, so a controls item the documents give to the MC is the controls contractor's scope.
```

#### GEM-2 (change): DEVICE OWNERSHIP RESOLUTION, question 1
- File: assets/gem/BMS_DDC_GEM_v4.txt.
- Rulings: R2.
- Change: A controls device given to the MC is furnished by the controls contractor.

assets/gem/BMS_DDC_GEM_v4.txt, line 120.

Current text:
```text
"Mechanical Contractor" or "MC": the mechanical contractor furnishes it.
```

Proposed text:
```text
"Mechanical Contractor" or "MC", for a controls device: the controls contractor furnishes it, because it is the MC's subcontractor for controls. Any other device: the mechanical contractor furnishes it.
```

### R3. Leak detectors: "Furnish and Install Leak Sensor"; leak detection built into the unit is a client note

Decides: A water or drip pan leak detector prints as "Furnish and Install Leak Sensor", and leak detection built into the unit stays a client note.

Edits: RULES-6, RULES-9, RULES-10, RULES-11, GEM-4.

- Interpretation: R3 rules on leak detection only. The general house form "**<ITEM> BY UNIT MFR." stays in RULES-9.
  Only its leak example is replaced. Conflict C8 says the form is not in the Master Template, but no ruling removes it.
- RULES-6 fixes the device name "Leak Sensor" (Master Template wording). For this device it wins over "Device names
  from the documents".
- The `leak_sensor` slot already exists in the Fan Coil Unit, Air Handling Unit, Unit Ventilators, Apartment Heat
  Pumps, VRF, Split and CRAC shapes. No shape edit.

#### RULES-6 (add): new rule "Leak detectors"
- File: playbook/rules.md. It goes after the rule "Other trades in brackets" (it ends at rules.md line 126). Topic: Ownership.
- Rulings: R3.
- Change: New rule. A water or drip pan leak detector is "Furnish and Install Leak Sensor". Leak detection built into the unit is a client note.

Current text: none. This is a new rule.

Proposed text:
```text
### Leak detectors
A water leak detector or drip pan detector at a unit is "Furnish and Install Leak Sensor": AME furnishes, installs
and wires it like any field sensor. This holds on a packaged unit too, and when the documents say only that it is
wired to a local alarm panel and name no furnishing party. It is the exception to the packaged unit default in
Three ownership questions. The device name is Leak Sensor, as the Master Template names it. Refrigerant leak
detection that is part of the unit is not a line. Its client note is "**Refrigeration Leak Detection system is
coming with the unit per equipment schedule". The wiring that AME does for refrigerant leak detection is a line
(see Refrigerant leak detection wiring).
```

#### RULES-9 (replace): rule "Client notes"
- File and lines: playbook/rules.md, lines 204-213.
- Rulings: R3, R12.
- Change: R3: the leak detection example is replaced by another example, and the Master Template note for leak detection built into the unit is added. R12 (decided part): a client note prints in red.

Current text:
```text
### Client notes
A client note is a statement to the client that the documents support, such as "**Start/Stop via Fire Alarm
System". It has no place of its own: it goes into the block's one clarification. When the block has nothing to
confirm, assume or count per drawings, the clarification is the "note" kind and the notes are joined with "; "
("**Start/Stop via Fire Alarm System; PC Workstation by Owner"). Otherwise they are joined after the other parts,
each led by "Note:" (see Joining into the one clarification). A client note never changes the price: work AME
prices is a line, never a note (see Miscellaneous responsibilities). A device the documents say the unit's
manufacturer furnishes, and that AME does not touch, may be noted in the house form "**<ITEM> BY UNIT MFR." (for
example "**LEAK DETECTION BY UNIT MFR."). Never an estimating hint (where to look, how to decide), never tech
hours, never prices.
```

Proposed text:
```text
### Client notes
A client note is a statement to the client that the documents support, such as "**Start/Stop via Fire Alarm
System". It has no place of its own: it goes into the block's one clarification. When the block has nothing to
confirm, assume or count per drawings, the clarification is the "note" kind and the notes are joined with "; "
("**Start/Stop via Fire Alarm System; PC Workstation by Owner"). Otherwise they are joined after the other parts,
each led by "Note:" (see Joining into the one clarification). A client note prints in red. A client note never
changes the price: work AME prices is a line, never a note (see Miscellaneous responsibilities). A device the
documents say the unit's manufacturer furnishes, and that AME does not touch, may be noted in the house form
"**<ITEM> BY UNIT MFR." (for example "**AIRFLOW MEASURING STATION BY UNIT MFR."). Refrigerant leak detection that
is part of the unit is the exception: its note is "**Refrigeration Leak Detection system is coming with the unit
per equipment schedule" (see Leak detectors). Never an estimating hint (where to look, how to decide), never tech
hours, never prices.
```

#### RULES-10 (replace): rule "Packaged units"
- File and lines: playbook/rules.md, lines 238-244.
- Rulings: R3, R4, R5.
- Change: Adds three field devices at the unit to AME's work on a packaged unit.

Current text:
```text
### Packaged units
A packaged unit comes with its factory controller, its end devices and its equipment wired inside at the factory.
The controller and every end device belong to the unit manufacturer unless the documents (sequence, schedule note,
plan note or detail) give one to the controls contractor. AME's work on it is limited to four things: the
shipped-loose devices; any device the documents explicitly give to the controls contractor, with the normal verb;
wiring to a factory-installed device only when the sequence gives that wiring to AME; and the three integration
lines, last.
```

Proposed text:
```text
### Packaged units
A packaged unit comes with its factory controller, its end devices and its equipment wired inside at the factory.
The controller and every end device belong to the unit manufacturer unless the documents (sequence, schedule note,
plan note or detail) give one to the controls contractor. AME's work on it is limited to four things: the
shipped-loose devices; any device the documents explicitly give to the controls contractor, with the normal verb;
wiring to a factory-installed device only when the sequence gives that wiring to AME; and the three integration
lines, last. Three field devices at the unit are also lines: the leak detector, the local alarm panel module and
the condensate pump float switch tie-in (see Leak detectors, Local alarm panel and Condensate pump float switch).
```

#### RULES-11 (replace): rule "Nothing inside the unit is a line"
- File and lines: playbook/rules.md, lines 249-252.
- Rulings: R3, R4, R19, R20.
- Change: Takes condensate devices and refrigerant leak detectors out of the list of what is inside the unit. Names what is outside the unit and is a line.

Current text:
```text
### Nothing inside the unit is a line
What the sequence describes inside the unit (valve control, fan control, DX staging, leak control, reheat, internal
sensors, actuators, safeties, filter switches, airflow stations, condensate devices, refrigerant leak detectors) is
wired at the factory and is not written. Do not write a line per monitored point or per internal device.
```

Proposed text:
```text
### Nothing inside the unit is a line
What the sequence describes inside the unit (valve control, fan control, DX staging, leak control, reheat, internal
sensors, actuators, safeties, filter switches, airflow stations) is wired at the factory and is not written. Do not
write a line per monitored point or per internal device. These are outside the unit and are lines: the leak
detector at the unit, the local alarm panel module and the condensate pump float switch tie-in (see Leak detectors,
Local alarm panel and Condensate pump float switch); a damper actuator that the documents show (see Damper
actuators are Furnish and Install); and the control devices of a unit when AME provides its controls (see Unit
control devices when AME provides the controls).
```

#### GEM-4 (change): PACKAGED UNITS, WHAT IS INSIDE THE UNIT IS NOT A LINE
- File: assets/gem/BMS_DDC_GEM_v4.txt.
- Rulings: R3, R4, R5, R20.
- Change: Takes condensate devices and refrigerant leak detectors out of the list. Adds the field devices that are lines.

assets/gem/BMS_DDC_GEM_v4.txt, line 294.

Current text:
```text
Not the controls contractor's scope: all internal sensors, actuators, safeties and valves, filter differential pressure switches, AFMS, condensate devices, refrigerant leak detectors, and any device described only as "provide", "furnish" or "install" with no party named.
```

Proposed text:
```text
Not the controls contractor's scope: all internal sensors, actuators, safeties and valves, filter differential pressure switches, AFMS, and any device described only as "provide", "furnish" or "install" with no party named.
Field devices at the unit are the exception, and they are written: the leak detector, the local alarm panel module, the condensate pump float switch tie-in, and a damper actuator that the documents show.
```

### R4. Condensate pump float switch: "Tie-in Condensate Pump Float Switch (Furnished by Mfr.)"

Decides: The condensate pump float switch prints as "Tie-in Condensate Pump Float Switch (Furnished by Mfr.)", never with the mechanical contractor in the bracket.

Edits: RULES-7, SHAPES-1, SHAPES-2, SHAPES-3, GEM-3, PRACTICE-1. Also uses: RULES-5 (shown under R2), RULES-10 (shown under R3), RULES-11 (shown under R3), GEM-4 (shown under R3).

- Interpretation: the tie-in prints when the documents have the BMS wire to the float switch (a detail, a sequence or a
  plan note). It does not print for every condensate pump. This follows the last bullet of R4, R10 and the estimator's
  note in `HarkPro/discussion.md` (the schedule note is the pump maker's; the detail says "wire to BMS"). If the
  estimator wants the line for every pump, change the second sentence of RULES-7.
- Tension, not drafted: "VRF lines" (rules.md lines 337-341) and the practice paragraph "VRF SYSTEMS" (ame_practice.txt
  line 14) say "the condensate pump float switch tie-in when there are condensate pumps". RULES-7 asks for the BMS wiring
  as well. If the estimator agrees with RULES-7, those two sentences should say the same.
- SHAPES-1 to SHAPES-3 print the line as fixed text because the Job model has no "Mfr." party. The Unit Mfr. bracket
  reads "(Furnished by Unit Mfr.)". If the estimator accepts that bracket, skip SHAPES-1 to SHAPES-3.
- A condensate pump in its own block has no shape. See "Pending sub-cases".

#### RULES-7 (add): new rule "Condensate pump float switch"
- File: playbook/rules.md. It goes after the new rule "Leak detectors" (RULES-6). Topic: Ownership.
- Rulings: R4.
- Change: New rule. The float switch tie-in has the bracket "(Furnished by Mfr.)".

Current text: none. This is a new rule.

Proposed text:
```text
### Condensate pump float switch
The float switch of a condensate pump comes with the pump. When the documents say that the BMS ties in to it (a
detail, a sequence or a plan note gives the wiring to the BMS), AME writes "Tie-in Condensate Pump Float Switch
(Furnished by Mfr.)". The bracket is "(Furnished by Mfr.)", never "(Furnished by Mechanical Contractor)". A pump
schedule note such as "provide float operated high water alarm" is the pump manufacturer's note (see Schedule notes
address the manufacturer). It does not give AME the tie-in by itself.
```

#### SHAPES-1 (change), shape "VRF System": slot condensate_float_switch, wording
- File: playbook/shapes.json.
- Rulings: R4.
- Change: The float switch line prints as fixed Master Template text. No {device} and no {owner}.

playbook/shapes.json, lines 1876-1877.

Current text:
```json
        "condensate_float_switch": "Tie-in {device}{owner}",
        "leak_detection_wiring": "{verb} {device}{owner}{qty}",
```

Proposed text:
```json
        "condensate_float_switch": "Tie-in Condensate Pump Float Switch (Furnished by Mfr.)",
        "leak_detection_wiring": "{verb} {device}{owner}{qty}",
```

#### SHAPES-2 (change), shape "Split System": slot condensate_float_switch, wording
- File: playbook/shapes.json.
- Rulings: R4.
- Change: Same change as SHAPES-1.

playbook/shapes.json, lines 1932-1933.

Current text:
```json
        "condensate_float_switch": "Tie-in {device}{owner}",
        "indoor_outdoor_interlock": "Low Voltage Interlock Wiring between Indoor and Outdoor Unit",
```

Proposed text:
```json
        "condensate_float_switch": "Tie-in Condensate Pump Float Switch (Furnished by Mfr.)",
        "indoor_outdoor_interlock": "Low Voltage Interlock Wiring between Indoor and Outdoor Unit",
```

#### SHAPES-3 (change), shape "Computer Room Air Conditioning Unit": slot condensate_float_switch, wording
- File: playbook/shapes.json.
- Rulings: R4.
- Change: Same change as SHAPES-1.

playbook/shapes.json, lines 1990-1991.

Current text:
```json
        "condensate_float_switch": "Tie-in {device}{owner}",
        "condenser_isolation_valve": "{verb} {device}{owner}{qty}",
```

Proposed text:
```json
        "condensate_float_switch": "Tie-in Condensate Pump Float Switch (Furnished by Mfr.)",
        "condenser_isolation_valve": "{verb} {device}{owner}{qty}",
```

#### GEM-3 (change): OTHER TRADES IN BRACKETS
- File: assets/gem/BMS_DDC_GEM_v4.txt.
- Rulings: R4.
- Change: The condensate bracket is "(Furnished by Mfr.)".

assets/gem/BMS_DDC_GEM_v4.txt, line 247.

Current text:
```text
  (Furnished by Mechanical Contractor) for condensate pumps and float switches.
```

Proposed text:
```text
  (Furnished by Mfr.) for the condensate pump float switch tie-in.
```

#### PRACTICE-1 (change): OWNERSHIP ANSWERS, answer (3)
- File: assets/gem/ame_practice.txt.
- Rulings: R4.
- Change: The condensate bracket is "(Furnished by Mfr.)".

assets/gem/ame_practice.txt, line 24 (the change is inside this line; only the changed words are quoted).

Current text:
```text
'(Furnished by Mechanical Contractor)' for condensate pumps and float switches.
```

Proposed text:
```text
'(Furnished by Mfr.)' for the condensate pump float switch tie-in.
```

### R5. Local alarm panel: "Furnish and Install Local RAM Module"

Decides: A local alarm panel for leak or condensate alarms prints as "Furnish and Install Local RAM Module".

Edits: RULES-8. Also uses: RULES-10 (shown under R3), GEM-4 (shown under R3).

- The `ram_module` slot already exists in the VRF, Split and CRAC shapes. No shape edit. In other shapes the line goes
  in `other_device`.

#### RULES-8 (add): new rule "Local alarm panel"
- File: playbook/rules.md. It goes after the new rule "Condensate pump float switch" (RULES-7). Topic: Ownership.
- Rulings: R5.
- Change: New rule. A local alarm panel gets "Furnish and Install Local RAM Module".

Current text: none. This is a new rule.

Proposed text:
```text
### Local alarm panel
When leak detectors or a condensate overflow report to a local alarm panel (a local audible or visual alarm) that
the documents show, AME writes "Furnish and Install Local RAM Module" in the block of the unit they serve. This is
also so on a packaged unit, with no party named (see Three ownership questions). The line is not written when the
documents show no local alarm panel.
```

### R6. Motorized dampers shown without tags: count every one, trace it, else its own block

Decides: Count every damper actuator on the plans, tagged or not, and trace each one to its fan or unit, or else put it in its own Motorized Dampers block.

Edits: RULES-15.

- The current rules already say "with the sheet references and the total count, flagged for the estimator" ("Untraced
  dampers in their own block", lines 289-291). Only "count every damper" is new. GEM v4 and the practice rules agree
  (conflict C31).

#### RULES-15 (add): new rule "Count every damper"
- File: playbook/rules.md. It goes after the rule "Dampers under their fan" (it ends at rules.md line 287). Topic: Dampers under their fan.
- Rulings: R6.
- Change: New rule. Count every damper actuator the plans show. Never assume one per unit.

Current text: none. This is a new rule.

Proposed text:
```text
### Count every damper
Count every damper actuator the plans show, tagged or not. Never assume one actuator per unit. Trace each damper's
duct to the fan or unit it serves and write the actuator in that block (see Dampers under their fan). A damper that
cannot be assigned goes in the Motorized Dampers block (see Untraced dampers in their own block).
```

### R7. Radiator or perimeter valve run from VAV zone thermostats: interlock wiring line

Decides: A radiation valve run from VAV zone thermostats gets an interlock wiring line for each zone, plus the hot water valve line when AME furnishes the valve.

Edits: RULES-21.

- Interpretation: "an interlock wiring line per zone" is written as the usual one line for all zones ("Line quantity",
  rules.md lines 168-170). If the estimator wants one line for each zone, say so.
- The Finned Tube Radiation shape (shapes.json lines 1007-1051) already has the slots `hot_water_valve` and
  `interlock`. It prints "Interlock with Associated {device} Operation". The ruling quotes the Master Template as
  "Associate". The shape keeps "Associated". No shape edit. Ask the estimator if the template spelling is wanted.
- Pending: where the line prints (the radiation block when it has tags, the VAV block when it has none). RULES-21 names no
  place, so the pending part stays out.

#### RULES-21 (add): new rule "Radiation valves tied to VAV zone thermostats"
- File: playbook/rules.md. It goes after the new rule "VAV lines" (RULES-20). Topic: VAV boxes and radiation.
- Rulings: R7.
- Change: New rule. An interlock wiring line for each zone, and the valve line when AME furnishes the valve. Where the line prints stays open (pending part of the ruling).

Current text: none. This is a new rule.

Proposed text:
```text
### Radiation valves tied to VAV zone thermostats
When the documents run radiator, finned tube or perimeter heat valves from each VAV zone thermostat, with separate
wiring, AME writes an interlock wiring line for each zone. The line names the associated VAV, FCU or system as its
device. When AME furnishes the valve, the valve line is "Furnish and Wire Hot Water Control Valve and Actuator". A
line is written only when the documents show the valve and its interlock.
```

### R8. Occupancy sensors are not dropped (decided part only)

Decides: An occupancy sensor in the controls documents is never dropped: it becomes an AME line or an ownership flag (which one by default is pending).

Edits: RULES-17.

- Only the first bullet of R8 is decided. The default (a line or a flag), the line wording and the flag wording are
  pending.

#### RULES-17 (add): new rule "Occupancy sensors are never dropped"
- File: playbook/rules.md. It goes after the rule "Everything assigned is extracted" (it ends at rules.md line 53). Topic: Evidence and citations.
- Rulings: R8.
- Change: New rule (decided part of the ruling only). Which of the two outcomes is the default stays open.

Current text: none. This is a new rule.

Proposed text:
```text
### Occupancy sensors are never dropped
Every occupancy sensor that the controls documents show ends as a line for AME or as an ownership flag in the
block's clarification. It is never left out.
```

### R9. Lighting integration given to the ATC vendor: one line, in the Front End block

Decides: A lighting integration that the documents give to the ATC or BMS vendor prints once, in the Front End block.

Edits: RULES-18, SHAPES-4, SHAPES-5.

- SHAPES-5 is optional. It removes the old slot in Misc Monitoring so that the line cannot print twice. Without it,
  RULES-18 alone says "once, in the front end block".
- The front end has no writer in `src/bms` today (see "Code that must change"). The line cannot print until one exists.

#### RULES-18 (add): new rule "Lighting control integration"
- File: playbook/rules.md. It goes after the rule "Front end items by others" (it ends at rules.md line 416). Topic: Front end.
- Rulings: R9.
- Change: New rule. The lighting integration line prints once, in the front end block.

Current text: none. This is a new rule.

Proposed text:
```text
### Lighting control integration
When the documents give the ATC or BMS contractor the integration of a lighting control system (for example for
occupied standby), AME writes this line once, in the front end block: "Interface Lighting Control System (By
Others) With Front End BMS Via Manufacturer Provided BMS Interface". It is not written again in a Misc Monitoring
block.
```

#### SHAPES-4 (change), shape "Front End": new slot lighting_interface (3 places)
- File: playbook/shapes.json.
- Rulings: R9.
- Change: Adds the slot after it_infrastructure, kind wiring, with the fixed Master Template text.

Text change 1 of 3, playbook/shapes.json, line 2053.

Current text:
```json
      "line_order": ["network_panel", "workstation", "server", "portable_terminal", "ups", "graphics", "training", "it_infrastructure", "other_device"],
```

Proposed text:
```json
      "line_order": ["network_panel", "workstation", "server", "portable_terminal", "ups", "graphics", "training", "it_infrastructure", "lighting_interface", "other_device"],
```

Text change 2 of 3, playbook/shapes.json, lines 2062-2063.

Current text:
```json
        "it_infrastructure": "device",
        "other_device": "device"
```

Proposed text:
```json
        "it_infrastructure": "device",
        "lighting_interface": "wiring",
        "other_device": "device"
```

Text change 3 of 3, playbook/shapes.json, lines 2073-2074.

Current text:
```json
        "it_infrastructure": "{verb} {device}{owner}{qty}",
        "other_device": "{verb} {device}{owner}{qty}"
```

Proposed text:
```json
        "it_infrastructure": "{verb} {device}{owner}{qty}",
        "lighting_interface": "Interface Lighting Control System (By Others) With Front End BMS Via Manufacturer Provided BMS Interface",
        "other_device": "{verb} {device}{owner}{qty}"
```

#### SHAPES-5 (change), shape "Misc Monitoring Systems": slot lighting_interface removed (3 places)
- File: playbook/shapes.json.
- Rulings: R9.
- Change: Takes the slot out so the line cannot print here and in the front end block. Option: keep the slot and rely on RULES-18.

Text change 1 of 3, playbook/shapes.json, line 1764.

Current text:
```json
      "line_order": ["map_or_connect", "monitored_item", "monitored_detail", "meter", "meter_comm_wiring", "lighting_interface", "other_device", "other_point", "fire_alarm", "other_valve", "other_install_and_wire", "other_wire", "other_interlock", "other_wiring"],
```

Proposed text:
```json
      "line_order": ["map_or_connect", "monitored_item", "monitored_detail", "meter", "meter_comm_wiring", "other_device", "other_point", "fire_alarm", "other_valve", "other_install_and_wire", "other_wire", "other_interlock", "other_wiring"],
```

Text change 2 of 3, playbook/shapes.json, lines 1770-1771.

Current text:
```json
        "meter_comm_wiring": "wiring",
        "lighting_interface": "wiring",
```

Proposed text:
```json
        "meter_comm_wiring": "wiring",
```

Text change 3 of 3, playbook/shapes.json, lines 1787-1788.

Current text:
```json
        "lighting_interface": "Interface Lighting Control System (By Others) With Front End BMS Via Manufacturer Provided BMS Interface",
        "other_device": "{verb} {device}{owner}{qty}",
```

Proposed text:
```json
        "other_device": "{verb} {device}{owner}{qty}",
```

### R10. Schedule notes are mostly addressed to the manufacturer

Decides: A note on an equipment schedule is the manufacturer's instruction unless it names the controls contractor or gives BMS wiring.

Edits: RULES-4, RULES-19.

- RULES-4 repeats one sentence of "Explicit assignment always wins" on purpose: a generic "provide" is not an
  assignment to AME.
- RULES-19 follows conflict C9: a BMS word in a schedule note counts only when the note names the controls contractor
  or gives BMS wiring.

#### RULES-4 (add): new rule "Schedule notes address the manufacturer"
- File: playbook/rules.md. It goes after the new rule "Controls given to the mechanical contractor" (RULES-3). Topic: Ownership.
- Rulings: R10.
- Change: New rule. A schedule note is the manufacturer's instruction unless it names the controls contractor or gives BMS wiring.

Current text: none. This is a new rule.

Proposed text:
```text
### Schedule notes address the manufacturer
A note on an equipment schedule is the unit or pump manufacturer's instruction, unless it names the controls
contractor (ATC, BMS or controls contractor) or gives BMS wiring ("wire to BMS", "by BMS contractor", "by ATC"). A
generic "provide ..." in a schedule note is not an assignment to AME. The note is still read: it tells which
devices come with the unit (shipped loose, integral, factory mounted), and that decides the Install and Wire,
Tie-in and client note lines. A schedule note that gives a controls item to the mechanical contractor makes it
AME's (see Controls given to the mechanical contractor).
```

#### RULES-19 (replace): rule "Named exceptions"
- File and lines: playbook/rules.md, lines 429-433.
- Rulings: R10, R2.
- Change: A BMS word in a schedule note counts only when the note names the controls contractor or gives BMS wiring. A thermostat given to the mechanical contractor is AME's, never an exception.

Current text:
```text
### Named exceptions
A unit the documents leave with no BMS work is a named exception in the estimator's form: "EXCEPTION TO ANY WORK
WITH Qty (n) <tags> - <reason>" (for example INTEGRAL THERMOSTAT, LINE-VOLTAGE THERMOSTAT, MANUFACTURER ON/OFF
SWITCH). One BMS word in its own sequence paragraphs or schedule notes (BMS, DDC, monitor, alarm, status, BACnet)
means it has BMS work and is priced instead.
```

Proposed text:
```text
### Named exceptions
A unit the documents leave with no BMS work is a named exception in the estimator's form: "EXCEPTION TO ANY WORK
WITH Qty (n) <tags> - <reason>" (for example INTEGRAL THERMOSTAT, LINE-VOLTAGE THERMOSTAT, MANUFACTURER ON/OFF
SWITCH). One BMS word in its own sequence paragraphs (BMS, DDC, monitor, alarm, status, BACnet) means it has BMS
work and is priced instead. The same word in a schedule note counts only when the note names the controls
contractor or gives BMS wiring (see Schedule notes address the manufacturer). A thermostat that the documents give
to the mechanical contractor is AME's, never an exception (see Controls given to the mechanical contractor).
```

### R11. VAV scope: Master Template words and hours (limited by decision 1)

Decides: VAV lines use the Master Template words and hours (3 hours cooling-only, 4 hours with a hot water reheat valve), and a line prints only when the documents show the device.

Edits: RULES-20, SHAPES-6.

- Decision 1 applied. Not drafted: "every VAV prints the controller line", "reheat means the discharge air sensor and a
  reheat line by default", and the 24V choice by default (lines.json "required" and "applies_when"). RULES-20 gives the
  words and says that a line is written only when the documents show the device.
- Hours: no edit. shapes.json line 93 already gives 3, or 4 with a hot water valve. rules.md lines 452-453 say the same.
- RULES-20 also states the exception of the VAV controller to "Furnish alone is for a hardwired signal" and to "A DDC
  controller ... Furnish and Install". The validator accepts "Furnish" here: the verb follows from AME furnishing it.
- SHAPES-6 prints the 24V text with the template's bracket "(Mentioned 24 V Wiring Control by BMS Contractor)". Ask
  the estimator if the bracket prints.
- Pending: hours for a VAV with electric reheat.

#### RULES-20 (add): new topic and rule "VAV lines"
- File: playbook/rules.md. It goes as a new topic "VAV boxes and radiation", before the topic "VRF and split systems" (its heading is at rules.md line 329). Topic: VAV boxes and radiation.
- Rulings: R11.
- Change: New topic with the rule VAV lines. A new topic needs the controller's yes (rules.md header comment). If there is no new topic, put VAV lines and RULES-21 in Shapes and wording.

Current text: none. This is a new rule.

Proposed text:
```text
## VAV boxes and radiation

### VAV lines
A VAV, fan powered box or terminal unit takes the Master Template's words for each line the documents call for.
When the documents give AME the controller and have the box maker mount it, the line is "Furnish DDC Controller to
the Factory for Installation": AME furnishes it and the factory installs it. This is the exception to Furnish alone
in Verb from the three answers and to the DDC controller verb in Verbs by device type. A "factory-mounted" or "open
protocol controller" note in the schedule is this controller, not the manufacturer's own controls. A VAV has one
space sensor, the one the sequence declares: "Space Temperature Sensor", "Space Temperature / Humidity Sensor",
"Space Temperature / Humidity / CO2 Sensor" or "Space Temperature / CO2 Sensor". "Furnish Fan Enable" is for a fan
powered box only. For reheat the words are "Furnish and Install Discharge Air Temperature Sensor" and one of
"Furnish and Wire Hot Water Control Valve and Actuator", "Furnish Electric Heat Enable (DO)" or "Furnish Electric
Heat SCR Control (AO)". For 24V power the words are one of "Run 24V Power Loop to VAVs (Mentioned 24 V Wiring
Control by BMS Contractor)", "Furnish and Install VAV Transformer" or "24V VAV Transformer is Coming with the
Unit", the one that matches who provides the power. A line is written only when the documents show the device. Tech
hours follow the shape: 3 per cooling-only VAV and 4 per VAV with a hot water valve.
```

#### SHAPES-6 (change), shape "VAV / Fan VAV": slot power_loop, wording
- File: playbook/shapes.json.
- Rulings: R11.
- Change: The 24V power loop line takes the full Master Template text of the ruling.

playbook/shapes.json, line 75.

Current text:
```json
        "power_loop": "Run 24V Power Loop to VAVs",
```

Proposed text:
```json
        "power_loop": "Run 24V Power Loop to VAVs (Mentioned 24 V Wiring Control by BMS Contractor)",
```

### R12. Client notes are red (decided part only)

Decides: A client note is written with two asterisks and prints in red (the orange and blue marks are pending).

Edits: RULES-9 (shown under R3).

- Only the decided part is drafted: one sentence in RULES-9. The colour is not a Playbook field. No code sets a colour
  today (see "Code that must change").

### R19. Unit-scheduled control devices are AME's when AME provides the controls

Decides: When AME provides the controls of a unit, the control devices on the unit schedule are AME's.

Edits: RULES-12, RULES-13, RULES-14. Also uses: RULES-11 (shown under R3).

- RULES-13 is the rule. RULES-12 and RULES-14 stop two older rules ("Factory-installed devices", "Shipped-loose
  devices") from contradicting it. RULES-11 adds a pointer to it.

#### RULES-12 (replace): rule "Factory-installed devices"
- File and lines: playbook/rules.md, lines 254-256.
- Rulings: R19.
- Change: The rule is for a device that the unit manufacturer furnishes and installs. A device that AME furnishes to the factory is AME's.

Current text:
```text
### Factory-installed devices
A device installed at the factory is never a line, blanket wiring clause or not. It becomes "Wire <device>
(Furnished by Unit Mfr.)" only when the sequence itself gives the wiring of that device to the controls contractor.
```

Proposed text:
```text
### Factory-installed devices
A device that the unit manufacturer furnishes and installs at the factory is never a line, blanket wiring clause or
not. It becomes "Wire <device> (Furnished by Unit Mfr.)" only when the sequence itself gives the wiring of that
device to the controls contractor. A device that AME furnishes to the factory for installation is AME's (see Unit
control devices when AME provides the controls).
```

#### RULES-13 (add): new rule "Unit control devices when AME provides the controls"
- File: playbook/rules.md. It goes after the rule "Factory-installed devices" (it ends at rules.md line 256). Topic: Packaged units.
- Rulings: R19.
- Change: New rule. The control devices on the unit schedule are AME's when AME provides the controls.

Current text: none. This is a new rule.

Proposed text:
```text
### Unit control devices when AME provides the controls
When AME provides the controls of a unit, including a controller that AME furnishes to the unit manufacturer for
installation at the factory, the control devices on the unit schedule are AME's: temperature and enthalpy sensors,
freezestat, drain pan level sensor and filter switch. They are "Furnish and Install", or "Furnish and Wire" when
the factory installs the device and AME wires it. Do not write "Install and Wire ... (Furnished by Unit Mfr.)" for
them unless the documents clearly give the device to the unit manufacturer. When unsure, keep the device as AME's
and flag the ownership.
```

#### RULES-14 (replace): rule "Shipped-loose devices"
- File and lines: playbook/rules.md, lines 264-269.
- Rulings: R19.
- Change: Says the rule is for a unit on the manufacturer's controls and points to the new rule.

Current text:
```text
### Shipped-loose devices
A device the unit manufacturer furnishes and ships loose (space sensor or thermostat, supply air temperature
sensor, supply static pressure sensor and the like) is written "Install and Wire <device> (Furnished by Unit Mfr.)"
on its own line, wired to the unit's own controller. Write out every manufacturer-furnished device the job names
that AME installs or wires. "Wire <device> (Furnished by Unit Mfr.)" is only for a device the manufacturer already
mounts. When unsure whether it is mounted, write Install and Wire.
```

Proposed text:
```text
### Shipped-loose devices
A device the unit manufacturer furnishes and ships loose (space sensor or thermostat, supply air temperature
sensor, supply static pressure sensor and the like) is written "Install and Wire <device> (Furnished by Unit Mfr.)"
on its own line, wired to the unit's own controller. Write out every manufacturer-furnished device the job names
that AME installs or wires. "Wire <device> (Furnished by Unit Mfr.)" is only for a device the manufacturer already
mounts. When unsure whether it is mounted, write Install and Wire. This is for a unit on the manufacturer's
controls. When AME provides the controls of the unit, see Unit control devices when AME provides the controls.
```

### R20. Damper actuators are Furnish and Install

Decides: A damper actuator that the documents show is Furnish and Install by AME, also when the equipment schedule lists it with the unit.

Edits: RULES-16. Also uses: RULES-11 (shown under R3), GEM-4 (shown under R3).

- Interpretation: R20 applies to any damper that the documents show. It does not say if it reaches a damper inside a
  unit on factory controls (for example an economizer damper). Ask the estimator.
- "Verbs by device type" (rules.md lines 99-104) already says that damper actuators are Furnish and Install. No edit
  there.

#### RULES-16 (add): new rule "Damper actuators are Furnish and Install"
- File: playbook/rules.md. It goes after the new rule "Count every damper" (RULES-15). Topic: Dampers under their fan.
- Rulings: R20.
- Change: New rule. A damper actuator the documents show is Furnish and Install, also when the equipment schedule lists it with the unit.

Current text: none. This is a new rule.

Proposed text:
```text
### Damper actuators are Furnish and Install
A damper that the plans, the control diagram or the sequence show gets "Furnish and Install ... Damper Actuator"
from AME, even when the equipment schedule lists the damper or its actuator with the unit. When the schedule says
that another party furnishes it, still write the line and add the "*Confirm ownership" clarification. A "Wire ...
Damper Actuator" line is rare: it is for an actuator that another party furnishes and installs and AME only wires.
```

### R21. Every system block lists all its end devices

Decides: A system block lists all its end devices when the sequence or diagram gives it points, and is never only "Interlock with ...".

Edits: RULES-22, RULES-23.

- RULES-23 makes a fan whose points land on the controller of another AME unit count as "run by an AME controller" in
  "Point lines only on AME controllers".
- The Exhaust Fan shape (shapes.json line 631) gives tech hours only when a controller line exists. An exhaust fan
  block with R21 points and no controller of its own gets no hours. The Master Template says "4 hour each fan if gets
  more points". No ruling covers this. Ask the estimator.
- Interpretation: "a note" in the ruling is read as a client note ("**" form) in the block's one clarification.

#### RULES-22 (add): new rule "Every block lists its end devices"
- File: playbook/rules.md. It goes after the rule "Minimum points on AME-run equipment" (it ends at rules.md line 140). Topic: Ownership.
- Rulings: R21.
- Change: New rule. A block is never only an interlock when the documents give the system points.

Current text: none. This is a new rule.

Proposed text:
```text
### Every block lists its end devices
A block is never only "Interlock with ...". When the sequence or the control diagram gives a system points, the
block lists all its end devices. For an exhaust fan these are, as the documents call for them: start/stop and
status, VFD control, VFD fault and the damper actuator. This holds when the points land on the controller of
another AME unit, such as the air handler: the lines stay in the fan's block, and a client note says where the
points land.
```

#### RULES-23 (replace): rule "Point lines only on AME controllers"
- File and lines: playbook/rules.md, lines 128-131.
- Rulings: R21.
- Change: A fan whose points land on the controller of another AME unit counts as run by an AME controller.

Current text:
```text
### Point lines only on AME controllers
"Furnish <point>" lines (start/stop and status, speed control, enable, setpoint, alarms, feedback) are written only
for a system AME's own DDC controller runs. On a packaged or factory-controlled unit the three integration lines
cover every monitored point.
```

Proposed text:
```text
### Point lines only on AME controllers
"Furnish <point>" lines (start/stop and status, speed control, enable, setpoint, alarms, feedback) are written only
for a system AME's own DDC controller runs. On a packaged or factory-controlled unit the three integration lines
cover every monitored point. A fan whose points land on the controller of another AME unit (an exhaust fan wired to
the air handler's controller) counts as run by an AME controller (see Every block lists its end devices).
```

### R22. The evidence prints the proof, not ids

Decides: The Evidence Package shows the sheet, page and exact quote on each scope line, not source ids or line ids.

Edits: RULES-24.

- Only the sentence in RULES-24 is Playbook text. The real change is in code (see "Code that must change").

#### RULES-24 (replace): rule "Assumption wording has no source ids"
- File and lines: playbook/rules.md, lines 200-202.
- Rulings: R22.
- Change: Source ids are for the model's citations only. The Evidence Package shows the sheet, page and quote.

Current text:
```text
### Assumption wording has no source ids
An assumption or a clarification names the sheet or section it rests on ("M-201", "the fan schedule"), never a
source id ("S12", "S40 note 1"): source ids are for the Evidence Package only.
```

Proposed text:
```text
### Assumption wording has no source ids
An assumption or a clarification names the sheet or section it rests on ("M-201", "the fan schedule"), never a
source id ("S12", "S40 note 1"): source ids are for the model's citations only. The Evidence Package shows, on
every scope line, where the documents say it, word for word: the sheet, the page and the quote, not an id.
```

### R13 to R18. Pending, nothing drafted

Every part of R13, R14, R15, R16, R17 and R18 is marked PENDING in `rulings.md`. They stay out. See "Pending
sub-cases (not drafted)".

## wording.json: no edit

No ruling needs a change in `playbook/wording.json`.

- Decision 2: `quantity.others_note` ("*Qty. {counts}.", line 45) already prints the printed count first and every
  other count with its place.
- R2 and R4: the "Mechanical Contractor" owner bracket (line 19) stays. `load_wording` needs one bracket for every
  party except AME. RULES-5 and RULES-7 stop the rules from using it for controls items and float switches. The
  bracket "(Furnished by Mfr.)" has no party in the Job model, so SHAPES-1 to SHAPES-3 print it as fixed text.
- R12: the client note form "**{text}" (line 35) stays. A colour is not a wording field.
- No new verb: the bare "Install" verb of conflict C20 has no ruling.

## Pending sub-cases (not drafted)

These parts are marked PENDING in the rulings, or no ruling covers them. No edit above holds them.

### Marked PENDING in the rulings

| Ruling | Pending part | What the ruling says to do until it is decided |
|---|---|---|
| R1 (replaced) | A system with no schedule at all (named only in a sequence, a plan note or a riser): print the highest count the documents support, flagged as a conflict, or follow the Quantity rules? | Nothing drafted. The current "Systems named only in the sequence" (rules.md lines 172-176) stays as it is. |
| R2 | Does AME also wire the exhaust fan space thermostat to the fan or starter, or only furnish and install it? | Print the "Furnish and Install Space Thermostat" line and raise the question. |
| R7 | Where the interlock line prints: in the radiation block (when it has tags) or in the VAV block (when it has none). It is the placement rule of the hark/fix-all patch, not confirmed. | RULES-21 names no place. |
| R8 | Which outcome is the default (an AME line or an ownership flag), the line wording ("Furnish and Install Occupancy Sensor", not from the Master Template) and the flag wording ("*Confirm ownership: occupancy sensors (AME vs electrical)"). | RULES-17 says only that the sensor is not dropped. |
| R11 | Tech hours for a VAV with electric reheat. The template gives hours only for cooling-only and hot water reheat. | No hours drafted. |
| R12 | One short client line per "*" item, with the reasoning kept in the Evidence Package. "*Confirm" in orange (ED7D31). "*Assumed" in blue (2F5597). In the Master Template, ED7D31 means "estimator hint, never print". | Nothing drafted. |
| R13 | Coverage gate: every controls fact ends as a line, an exception, a clarification or a dismissal with a reason. An unaccounted fact blocks the proposal. | Nothing drafted. |
| R14 | Keep or reword the opening sentence "A.M.E., Inc, is pleased to provide a quotation ...". | Nothing drafted. |
| R15 | The fallback exception reason "NO BMS WORK IN THE CONTRACT DOCUMENTS" (not Master Template wording). | Nothing drafted. |
| R16 | An "ALTERNATE #n" with no add or deduct (planned as an add, with a question). | Nothing drafted. |
| R17 | An empty "DEDUCT ALTERNATES: ALT #:" heading (proposed: drop the heading). | Nothing drafted. |
| R18 | Price book gaps: unpriced items and four value conflicts. | Nothing drafted. |

### R1 parts that decision 2 does not carry over

R1 is replaced as a whole. These parts of R1 are not drafted. Ask the estimator if any of them should stay.

- The equipment schedule decides which systems the job has.
- `Brain/Quantity rules.txt` governs every quantity (its categories CONFIRMED, DISCREPANCY, EXTRA, MISSING, ORPHANED,
  CONFLICT, and EXISTING, REMOVAL and REUSE).
- A duplicate tag row on a schedule is a DISCREPANCY. A type-only schedule takes its count from the plans. An indoor
  and outdoor pair is one system.

### Rejected by decision 1 (not drafted)

- The lines.json lines with `required: true`. Examples: the VAV controller line "by AME default (about 99%)", the
  front end 3-D graphics and training lines marked "Default", and the condensate pump float switch line "whenever
  pumps are in the job". The Master Template gives their wording only.
- Conflicts C11 to C16. The current text stays: rules.md "No standard or fallback lines" (lines 26-29), "Front end
  lines cite the specification" (407-410) and "Template gives shape only" (465-468); shapes.json line 3.

### No ruling covers these (not drafted)

- Conflict C18: whether device names come from the documents or from the template ("Space Temperature Sensor" or
  "zone sensor"). The current rule "Device names from the documents" stays.
- Conflict C20: the template's bare "Install" verb has no verb in the Job model.
- Conflict C21: "Furnish Humidifier Control Valve and Actuator" in the template, against "every valve is Furnish and
  Wire".
- Conflicts C32, C33 and C34: the source of 16 hours for a packaged unit, 4 hours per integration, and "40 hours each"
  for kitchen exhaust.
- Conflicts C35 and C36: the tag prefixes AC, ACCU and HP are in two shapes each.
- A condensate pump in its own block (prefix CP): no shape and no ruling. lines.json calls its own block an estimator
  decision.
- Bipolar ionization: only Master Template lines exist. shapes.json has an `ionization_alarm` slot on the Air Handling
  Unit and Packaged shapes only.
- The spelling "Associate" (Master Template) against "Associated" (shapes.json line 1033) in the radiation interlock.
- GEM v4 lines 396-403 ("the Master Template entry is the frame ... leave a template line out only when the documents
  exclude it") say the opposite of decision 1. The app does not read the GEM. The lead may want to align it.
- R20 for a damper inside a unit on factory controls (see the R20 note).
- Exhaust fan tech hours when the fan has points and no controller line (see the R21 note).

## Code that must change to follow these rules

I list `src/bms`, and the two `src/estimator` files that the colour change needs. I read the code. I did not run it on
a ledger. "Certain" means the text of the code contradicts the ruling. "Possible" means it depends on how the ledger
words a fact.

| # | File and lines (rebuild) | What the code does now | Ruling | What it must do | Sure? |
|---|---|---|---|---|---|
| 1 | src/bms/plan.py:536, 556-557, 576 | The docstring (536) says the mechanical contractor furnishes the float switch. Two questions to the estimator (556-557, 576) print "(Furnished by Mechanical Contractor)" as the bracket of the tie-in. | R4 | Say "(Furnished by Mfr.)". tests/bms/test_final_b.py:185 checks that the question holds "Mechanical Contractor". | Certain |
| 2 | src/bms/validate.py:219-223 | On a packaged unit, a device that AME furnishes gets a "check": "If the documents give this device to the controls contractor, keep it; otherwise delete it." | R3, R5, R19, R20 | Leave out the check for a leak sensor, a local RAM module and a damper actuator, and for a unit where AME provides the controls. R19 says: when unsure, keep the device as AME's and flag it. | Certain (severity is check) |
| 3 | src/bms/validate.py:212-218 | On a system with control "packaged": a "Furnish" point line is must_fix, and an AME-furnished controller is must_fix ("Delete the line"). | R11, R19, R21 | Allow the VAV controller line and a controller that AME furnishes to the unit factory (R11, R19). Allow the points of a fan whose points land on another AME controller (R21). | Possible (see 4) |
| 4 | src/bms/plan.py:63-65 and 961 | A provider fact with the words "manufacturer", "factory", "packaged" and similar makes the system "packaged" (`_control`). A fact such as "controller furnished by AME to the factory" has those words. | R11, R19 | Read "AME furnishes to the factory" as AME-provided controls (control "field"), not as packaged. | Possible |
| 5 | src/bms/plan.py:1393-1402; src/bms/render.py:735 | `_front_end` builds `FrontEnd(mode=...)` only. No code in src/bms writes front end devices (git grep: `front_end.devices` is read, never set). The renderer prints front end lines with no shape, so the Front End shape of shapes.json (SHAPES-4) does not reach a printed line. | R9 | A front end writer. The renderer must pass the Front End shape, so that the lighting line prints in its slot. | Certain |
| 6 | src/bms/evidence.py:27-30, 33-34, 49, 54-57 | The Scope lines tab has a "Device id" column. Each citation prints the source id first ("S12 / where / quote"). The Findings tab names the device by id. | R22 | Print the sheet, page and exact quote on each scope line. Drop the id columns and the source id from the citation text. (The old tabs are in src/estimator/evidence/workbook.py; not read.) | Certain |
| 7 | src/bms/review.py:203 | The review page prints the source id in a span before each quote. | R22 | R22 names "evidence sheets". The review page may need the same change. | Possible |
| 8 | src/bms/render.py:600-622 and 719-721; src/estimator/scope.py:19-23; src/estimator/proposal/write.py | A client note prints as plain text. `Run` has `text` and `bold` only. No code sets a colour on a note. | R12 (decided part) | Add a colour to `Run`. Set red on "**" notes in `_notes` and `_items`. Write it in the Word file. | Certain |

No code change is needed for decision 2. plan.py:20, validate.py:358-374 and render.py:271-273 and 399-457 already
print the highest count and name every other count. I found no code in src/bms that prints a template line by default
or that prefers the schedule count.

## Tests that change if the drafts are applied

I applied every edit to a scratch copy of `rebuild` (the repo is untouched). I ran the tests that load the Playbook with
the project's Python (`PYTHONPATH=src`, `-p no:cacheprovider`).

| Run | Files | Result |
|---|---|---|
| A. Before the edits | 20 test files: test_playbook*, test_rule_names, test_validate*, test_render*, test_contracts, test_final_b, test_gem_v4, test_gem_round, test_gem_round2, test_next_batch | 555 passed |
| B. After the edits | the same 20 files | 554 passed, 1 failed (see below) |
| C. After the edits and the test list fix below | 33 files: the 20 files of A and 13 more that load the repo Playbook (test_ai, test_plan, test_robustness, test_run, test_review, test_status, test_doctor, test_citations_reviews, test_final_fixes, test_review_final, test_review_final2_plan, test_count_cause_note, test_final_h_counts) | 1118 passed (555.43 s) |
| D. After the edits, the other tests/bms files (test_run_*, test_review_*, test_final_*, test_correct_*, test_citations_*, test_counts*, test_bms_evidence, test_measure, test_status_*) | the files not in C | 713 passed (938.00 s) |
| E. After the edits, 10 old-app files that use the GEM or the practice rules (test_whole_job, test_assemble, test_assemble_round4, test_assumption_reasons, test_brief, test_dossier, test_estimate, test_house_check, test_ledger_plan, test_ledger_run) | 10 files | 258 passed (140.11 s) |

The one failure of run B is `tests/bms/test_rule_names.py::test_every_slot_has_a_verb_or_a_parent_or_carries_its_own_verb`.
The test keeps a fixed list of the wordings that carry their own verb (`OWN_VERB_TEXT`, about line 201). The edits add
two fixed wordings, so four slots are not in the list: the VAV power loop (SHAPES-6) and the float switch line in the
VRF, Split and CRAC shapes (SHAPES-1 to SHAPES-3). Fix, in the list: replace "Run 24V Power Loop to VAVs" with "Run 24V
Power Loop to VAVs (Mentioned 24 V Wiring Control by BMS Contractor)", and add "Tie-in Condensate Pump Float Switch
(Furnished by Mfr.)". I made that change in the scratch copy only. The test file has CRLF line endings.

A note on `tests/bms/test_review_final.py`: it failed once because I rewrote the patched rules.md while it ran. The
run noticed the changed Playbook and asked a write step again. It passes when the files stay still. The final run C
did not change any file.

Tests that need an update when the code changes (not when the Playbook changes):

- `tests/bms/test_final_b.py:185` expects "Mechanical Contractor" in the planner's question (code row 1).
- `tests/bms/test_validate.py:150` quotes "(Furnished by Mechanical Contractor)" for condensate pumps in a docstring. No
  assertion depends on it.

Other files that follow the Playbook:

- `docs/superpowers/specs/2026-10-04-playbook-sources.md` maps every rule to its source. It needs a row for each of the
  13 new rules and the new topic, and a row for the changed Front End, Misc Monitoring, Exhaust Fan, VAV, VRF, Split and
  CRAC shapes.
- Effect on a run: `rules.md` is the system prompt of every AI step, and the answer cache is keyed on the prompt
  (`src/bms/ai.py`, module notes). After the edits, a job asks its AI steps again.
- I ran all 72 files of tests/bms and 16 old-app files that read the Playbook, the GEM or the practice file (runs A to E). The other old-app tests were not run, and tests/data was left out of the scratch copy. AGENTS.md makes the whole suite (about 1,900 tests) the gate before a merge. Run it on the real
  branch after the edits are applied.

## Verification

I ran these checks on a scratch copy of `rebuild` 8ccd0b3 in the scratchpad. The repo was not touched. The Playbook,
GEM and practice files were patched by script from the same data that this draft quotes, so the quoted text is the
applied text.

1. `python -m bms playbook-lint playbook`, before and after the edits: "The Playbook at playbook is clean." both times.
   `lint_playbook(root, referenced_rule_names())` gives no problem after the edits, so every rule name that the
   validators, the AI prompts and the Findings use is still in rules.md.
2. `load_playbook()` after the edits: 97 rules (84 before), 17 topics (16 before), 37 shapes. The JSON of shapes.json
   and wording.json parses.
3. Script checks on the new and changed rule text: every "(see ...)" names a rule that exists after the edits; no
   arrow, no emoji, no ruling or conflict number; no rules.md line is longer than 117 characters; the rule names are
   unique.
4. A render check with an invented job (no job data) and the patched Playbook (`tools/render_check.py`). These are the
   printed lines of the changed slots:

```text
Qty (2) VRF System IDU-1, 2
Furnish and Install Leak Sensor
Furnish and Install Local RAM Module (Qty. 1 Total)
Tie-in Condensate Pump Float Switch (Furnished by Mfr.)
Qty (2) VAV Boxes VAV-1, 2
Furnish DDC Controller to the Factory for Installation
Furnish and Install Space Temperature Sensor
Run 24V Power Loop to VAVs (Mentioned 24 V Wiring Control by BMS Contractor)
Qty (2) Exhaust Fans EF-1, 2
Furnish and Install Space Thermostat
Furnish Fan Start/Stop and Status
Qty (1) Front End
Interface Lighting Control System (By Others) With Front End BMS Via Manufacturer Provided BMS Interface
```

   The validator gives no must_fix on these lines. The "Furnish" verb on the VAV controller line passes the three-answer
   check. The three "check" findings of that run come from the counts of my invented job, not from the edits.
5. Tests: see the section "Tests that change if the drafts are applied".

Files in the scratchpad (folder `C:\Users\SIDDHA~1\AppData\Local\Temp\claude\D--Estimator-AI\f78f2256-5778-440f-8d52-039ebb5fad17\scratchpad`):

- `repo_patched\` is the scratch copy with every edit applied (playbook files, GEM, practice, and the one test list).
- `rules.diff`, `shapes.diff`, `gem.diff`, `practice.diff` are unified diffs against `rebuild` (rules.md: +139
  lines, -23 lines).
- `edits_applied.json` holds the exact texts and line numbers. `tools\` holds the scripts.
- To apply later: the three Playbook files, the GEM file and the practice file in `repo_patched\` can be copied as they
  are, if the files in the repo are still the blobs named in "Basis". If they changed, redo the edits from this draft.
