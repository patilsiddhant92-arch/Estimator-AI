# Conflicts between the old doctrine sources and lines.json / rulings.md

Built 2026-10-09 against branch `hark/harkpro-notes` (= `main`). Precedence: **rulings.md > lines.json > Brain/Quantity
rules.txt > everything else**. "Winner" names which side holds. Nothing in `src/`, `playbook/`, `Brain/`, `assets/` or
`tests/` was changed; each row is a proposed edit for the estimator to approve.

Line numbers
- `playbook/rules.md` numbers are for **main**. `HarkPro/discussion.md` cites three ranges against the **hark/fix-all patch**
  (which inserts 10 lines at 157 and 29 lines at 265). Mapping: main 78-84 = patched 78-84; main 121-126 = patched
  121-126; **main 429-433 = patched 466-472** (the named exceptions rule). On main, 466-472 is "Template gives shape only",
  which is itself a conflict (C11), so both are listed.
- GEM v3.2 is cited as the docx paragraph (`Brain/BMS_DDC_GEM_v3.2.docx ¶n`, python-docx body index) and the text copy
  (`assets/gem/BMS_DDC_GEM_v3.2.txt:n`).
- Master Template is `MT ¶n` (`Brain/Master Template.docx`, same indexing as `lines.json`).

## A. Ownership: the MC-controls ruling (R2) and the condensate / leak rulings (R3, R4)

| # | Old source | Old text | Contradicts | Winner |
|---|---|---|---|---|
| C1 | `playbook/rules.md:78-84` | "Mechanical contractor: valve bodies, piping, unit-mounted safeties not assigned to the controls contractor." | R2: any controls item or sensor the documents give to the MC is AME's. Unit-mounted safeties/controls "by MC" become AME lines. | **R2.** Keep valve bodies and piping as the MC's; delete "unit-mounted safeties not assigned to the controls contractor" from the MC list and add "controls items given to the MC are AME's (AME is the MC's sub)". |
| C2 | GEM v3.2 Q1: `BMS_DDC_GEM_v3.2.docx ¶191` / `assets/gem/BMS_DDC_GEM_v3.2.txt:143` | `"Mechanical Contractor" / "MC" → MC furnishes it.` | R2 | **R2.** Q1 must read: MC named for a controls device → AME furnishes it (normal verb). Same fix in GEM v4 `assets/gem/BMS_DDC_GEM_v4.txt:120`. |
| C3 | GEM v3.2 `docx ¶165-166` / `txt:124-125` | "Mechanical Contractor (MC) — valve bodies, piping, unit-mounted safety devices not explicitly assigned to BMS" | R2 | **R2** (as C1). Also GEM v4 `txt:105`. |
| C4 | `playbook/rules.md:121-126` | "(Furnished by Mechanical Contractor)" for condensate pumps and float switches | R4 + MT ¶678/692/705: `Tie-in Condensate Pump Float Switch (Furnished by Mfr.)` | **R4 / lines.json.** Bracket for the float switch is "(Furnished by Mfr.)". |
| C5 | `playbook/wording.json:19` | `"Mechanical Contractor": " (Furnished by Mechanical Contractor)"` owner bracket | R2 (a controls item by the MC has no MC bracket; it is AME's) and R4 | **R2/R4.** Keep the key only for non-controls items, or remove it; never use it for condensate float switches. |
| C6 | `assets/gem/BMS_DDC_GEM_v4.txt:247`; `assets/gem/ame_practice.txt:24` | "(Furnished by Mechanical Contractor) for condensate pumps and float switches." | R4 | **R4.** |
| C7 | GEM v3.2 `docx ¶402-404` / `txt:306-307`; `playbook/rules.md:249-252` | Factory-controls unit: "NOT CC SCOPE: ... condensate, refrigerant leak detectors ..." / "Nothing inside the unit is a line (... condensate devices, refrigerant leak detectors)" | R3 (drip-pan leak detector → `Furnish and Install Leak Sensor`), R4 (condensate float switch tie-in), R5 (local RAM). These are field devices outside the unit, not internal ones. | **R3/R4/R5.** Narrow the old text to devices **inside** the unit; integral refrigerant leak detection stays a client note (R3). |
| C8 | `playbook/rules.md:204-213` | House form "**<ITEM> BY UNIT MFR." e.g. "**LEAK DETECTION BY UNIT MFR." | R3 and MT ¶16: `**Refrigeration Leak Detection system is coming with the unit per equipment schedule` | **R3 / MT ¶16** for refrigerant leak detection. The "BY UNIT MFR." form is not in the Master Template. |
| C9 | `playbook/rules.md:429-433` (= patched **466-472**) | Named exceptions "INTEGRAL THERMOSTAT, LINE-VOLTAGE THERMOSTAT, MANUFACTURER ON/OFF SWITCH"; "One BMS word in its own sequence paragraphs or schedule notes (BMS, DDC, monitor, alarm, status, BACnet) means it has BMS work and is priced instead." | R2: a thermostat "by MC" is `Furnish and Install Space Thermostat`, never an exception. R10: schedule notes are mostly the OEM's; a word like "alarm" in a pump/unit schedule note does not by itself make it AME work (e.g. a float high-water alarm note → only the tie-in line, R4). | **R2 + R10.** Exceptions only for items with no controls work for anyone; the "one BMS word in schedule notes" test applies only when the note names the ATC/BMS contractor or gives BMS wiring. |
| C10 | GEM v3.2 `docx ¶196-198` / `txt:147-148`; `playbook/rules.md:86-90` | "No named party + packaged/factory controls unit → OEM scope. Do NOT write a scope line." | R2 when the named party is the MC; R3/R4/R5 for leak, condensate and local alarm devices, which print template lines without a named AME assignment. | **Rulings** for those device types; the default still holds for other devices. |

## B. "No standard lines" vs a line library (R11, lines.json `required`)

| # | Old source | Old text | Contradicts | Winner |
|---|---|---|---|---|
| C11 | `playbook/rules.md:465-469` (main) | "The Master Template (shapes.json) sets only the shape of a block ... It never says that a line exists." | lines.json is the line library; `required: true` lines print whenever the family is present and `applies_when` holds (R11 VAV lines; front-end graphics/training marked "Default" in MT ¶60/62). | **lines.json.** Lines still need the family to be in the job (R1) and their condition to hold; they no longer need their own document citation. |
| C12 | `playbook/rules.md:26-29` | "There is no 'AME standard' line and no fallback line. A line is never added because ... the Master Template lists it" | Same as C11; R11 | **lines.json / R11.** |
| C13 | `AGENTS.md:28-29` | "The job's own documents decide the scope. No standard lines, no fallback lines, no wording from other jobs." | Same as C11 | **lines.json / R11** for "no standard lines". "No wording from other jobs" still holds (lines.json carries no job data). |
| C14 | `playbook/shapes.json:3` | "Never content: no default lines, no device a block gets without this job's evidence." | Same as C11 | **lines.json.** shapes.json keeps the slot order and wording forms. |
| C15 | `Brain/ESTIMATOR_DOCTRINE.md:13` | "Never invent — No Brain lines without evidence" | Same as C11 | **lines.json / R11** (evidence = the family is scheduled; the line's condition is in `applies_when`). |
| C16 | `playbook/rules.md:407-410` | Each front end line (... 3-D graphics, training ...) "is written only when this job's specification calls for it" | MT ¶60 and ¶62 mark 3-D Graphics and Training "Default" (`front_end.07`, `.08`, `.16`, `.17` required). | **lines.json.** |
| C17 | `assets/system_templates.json:3, 94-95, 314` | "standard" lines added "as an ASSUMPTION with '*Assumed per AME standard - confirm'"; `standard_text` "24V Transformer by Unit Mfr." | lines.json prints template wording without an assumption flag when required; MT ¶158 wording is "24V VAV Transformer is Coming with the Unit". | **lines.json.** (Also: this file carries a sample tag and a sheet reference copied from the template; see the report.) |

## C. Wording and verbs

| # | Old source | Old text | Contradicts | Winner |
|---|---|---|---|---|
| C18 | GEM v3.2 `docx ¶617-619` / `txt:473-474`; `playbook/rules.md:66-69` | "Device names always come from the sequence and point list — never from this template." | Ruling brief / lines.json: keep the template's wording exact. | **lines.json** for the line form and every fixed line. The documents' noun fills a placeholder only where lines.json has one, and replaces a template device name only when the documents name a different device (e.g. "spill air damper"). **Ask the estimator** whether "Space Temperature Sensor" should become the documents' "zone sensor" etc. (ambiguity A3). |
| C19 | GEM v3.2 `docx ¶399, 659, 664` / `txt:304, 510, 514` | "◊ Controls Contractor requires mfr. rep to assist in integration, cost to be incurred by mech contractor" | MT ¶21: "AME requires mfr. Rep to assist in integration, cost to be incurred by mech contractor" | **lines.json (MT).** |
| C20 | `playbook/wording.json:11, 14` | "the Master Template's bare 'Install' has no Job model verb; it is not used" | MT ¶12 `Install ABC (Furnished by Unit Mfr.)`, MT ¶679 `Install Central Controller by Unit Mfr. Tie into BMS` (`vrf_system.07`, verb `install`). | **lines.json.** The Job model needs an `install` verb (or the line prints as fixed text). |
| C21 | GEM v3.2 `docx ¶320` / `txt:242`; `playbook/rules.md:103` | "All valves and actuators — always Furnish and Wire, no exceptions" | MT ¶320 `Furnish Humidifier Control Valve and Actuator` (verb Furnish). | **Unclear — ask (A5).** lines.json keeps the template's exact text; the estimator decides whether ¶320 is a typo. |
| C22 | GEM v3.2 `docx ¶306-317` / `txt:229-239` | "FURNISH — CC provides hardwired signal only, no physical device" | MT front end uses Furnish for hardware: `Furnish Network Level Control Panel`, `Furnish PC Workstation`, `Furnish BMS Server`, `Furnish UPS`. | **lines.json** (verb meaning in the front end = AME supplies it; install/wire not stated). |
| C23 | GEM v3.2 `docx ¶734-736` / `txt:567` | "Do NOT write a separate Furnish and Install Current Switch line when Status is already in the Start/Stop line." | MT ¶517 `Furnish and Install Fan CT` (DDC-ready UV, where there is no start/stop line). | No real clash (different case); lines.json keeps ¶517. |
| C24 | `playbook/shapes.json:802` | FSD end switch wording `{verb} Open / Close Status to BMS via FSD End Switch{owner}{qty}` | MT ¶103 ends "(End switch provided w damper by others)"; `{owner}` would print "(Furnished by Others)". | **lines.json (MT ¶103).** |
| C25 | `Brain/ESTIMATOR_DOCTRINE.md:37` | "Conflicts → `*C#` on proposal" | R1 (flag, not print) and the `*Confirm` / `**` forms (R12, wording.json) | **R1/R12.** `*C#` is retired. |
| C26 | `playbook/rules.md:180-192` | One clarification of each kind per block, items joined with "; " | R12 proposal: one short client line per `*` item — **PENDING estimator** | Old rule holds until R12 is decided. |

## D. Quantities (R1)

| # | Old source | Old text | Contradicts | Winner |
|---|---|---|---|---|
| C27 | `playbook/rules.md:160-166` (main) | "Higher count prints ... the highest count prints, flagged" / "Never print a count lower than one the documents give." | R1: the schedule count prints; other counts are flagged. | **R1** (the hark/fix-all patch already rewrites these lines, unmerged). |
| C28 | `assets/gem/BMS_DDC_GEM_v4.txt:594`; `assets/gem/ame_practice.txt` "CONTRADICTED COUNTS" (main) | "the higher count prints, flagged CONFIRM QUANTITY" | R1 | **R1** (patch fixes, unmerged). |
| C29 | `playbook/rules.md:172-176` | A system named only in the sequence prints in the base bid, "Qty (##)" | `Brain/Quantity rules.txt:59-63, 125` ORPHANED: "do not price until confirmed" | **Quantity rules** (they outrank rules.md) for a system in one place only; R1 sub-case is PENDING estimator. |

## E. Placement and tech hours

| # | Old source | Old text | Contradicts | Winner |
|---|---|---|---|---|
| C30 | `playbook/shapes.json:1787` (Misc Monitoring `lighting_interface` slot) and `:2053` (Front End `line_order` has no lighting slot); MT ¶581-582 places the line under Misc Monitoring Systems | lighting interface lives in Misc Monitoring | R9: a lighting integration named for the ATC vendor is a Front End line (`front_end.21`). | **R9.** shapes.json Front End needs a slot. |
| C31 | `assets/gem/BMS_DDC_GEM_v4.txt:184`; `assets/gem/ame_practice.txt:12` | "Damper actuators are not gathered into one motorized damper block at the end." / standalone block only for dampers no fan claims | R6 adds: count every untagged damper; an unassignable one gets its own block. | **R6** (compatible with `playbook/rules.md:283-295`, which already allows an untraced-damper block). |
| C32 | `playbook/rules.md:453`; `playbook/shapes.json:385` | Packaged ERU / RTU / AHU is 16 hours per unit | MT ¶253-262 gives no hours. | **Unknown source — ask (A7).** lines.json leaves hours null. |
| C33 | `playbook/rules.md:456-458` | Integration-only systems 4 hours per integration | Not in the MT (Equipment VFD, generator etc. have no hours). | Old rule stands as a house rule until the estimator says otherwise; lines.json records the gap. |
| C34 | `playbook/rules.md:452` | "Kitchen Exhaust Ventilation is 40 hours per kitchen exhaust fan" | MT ¶232 "40 hour each" (each of what is not stated). | **Ask (A8).** |
| C35 | `playbook/shapes.json:1900` (Split prefixes `AC`, `CU`, `ACCU`) and `:1842` (VRF prefixes `IDU`, `BS`, `BC`) | AC/ACCU always pick the split shape | MT ¶670-671 VRF headers use "Indoor Unit AC" and "Condensing Unit ACCU" too. | **lines.json** lists AC/ACCU under both; the family is picked by the system (VRF vs split), not the prefix. |
| C36 | `playbook/shapes.json:911-913` | `HP` prefix → Apartment Heat Pumps | Any heat pump tagged HP (WSHP, geothermal) would be read as an apartment heat pump. | Ask; lines.json lists HP only as an alias of apartment heat pumps and GHP under geothermal. |

## F. Missing from the old sources (no contradiction, but no home)

- Occupancy sensors (R8): no rule, shape or template line.
- Condensate pump as its own system (CP prefix): no shape (`HarkPro/bugs.md` "CP and BIPO named Equipment").
- Bipolar ionization: only MT ¶519 / ¶728; shapes has an `ionization_alarm` slot on AHU and packaged units only.
- EF space thermostat by MC (R2): the Exhaust Fan shape (`playbook/shapes.json:583`) has no thermostat slot.
