# Playbook sources (workstream 1, 2026-10-04)

Where every rule in `playbook/rules.md`, every shape in `playbook/shapes.json` and every form in
`playbook/wording.json` came from, and what was dropped and why. Sources:

- **GEM** — `assets/gem/BMS_DDC_GEM_v4.txt` (the approved method), cited by its section heading.
- **Practice** — `assets/gem/ame_practice.txt` (the estimator's dated rules; they govern where more specific),
  cited by the paragraph's heading.
- **House style** — `assets/house_style.json`, cited by key.
- **Template** — `assets/system_templates.json` (the Master Template as data), cited by system entry or key. Only
  shape was taken.
- **Front end** — `assets/front_end.json`, cited by key.
- **Design** — `docs/superpowers/specs/2026-10-04-rebuild-design.md` §2 (the estimator's ground rules).

Not used: `assets/phrasing_bank.json` and any past-job example (brief). No job text is in the Playbook.

## 1. Rules

| Topic | Rule | Source |
|---|---|---|
| Evidence and citations | Every line cites this job | Design §2.1; GEM Reference line format (the snippet becomes the citation) |
| | No standard or fallback lines | Design §2.2; replaces Template `standard_lines_about` (dropped, see §4) |
| | Nothing from other jobs | Design §2.2 |
| | Read the whole sequence first | GEM Step 0 Project quick scan (the eight fields) |
| | Contractor name in the documents | GEM Contractor name rule; Self-QC 01 |
| | Everything assigned is extracted | GEM Pre-scope work extraction (categories A and B); Self-QC 03 and 10 |
| | Sequence first, point list second | GEM Input handling, priority rule |
| | Every point-list point is checked | GEM Point list integration rule |
| | Device names from the documents | GEM Additional rules: device naming; Damper actuator rule (do not rename); SOW format (Title Case); GEM SOW order ("use the sequence's noun") |
| Ownership | Every line carries its ownership | Design §2.4; Practice Packaged units (last sentence) |
| | Who owns what by default | GEM Scope ownership, primary rule |
| | Three ownership questions | GEM Device ownership resolution, questions 1 to 3 |
| | Verb from the three answers | GEM Verb assignment; Verb rules (Furnish and Wire: no dash) |
| | Verbs by device type | GEM Verb rules (Furnish and Install / Furnish and Wire lists); Self-QC 05, 06; Additional rules: filter DP switches |
| | Explicit assignment always wins | GEM Explicit assignment always wins; Packaged units item 2; Practice Factory controls |
| | Mixed ownership device by device | GEM Mixed ownership |
| | Blanket wiring clause | GEM Blanket wiring clause, with the estimator's exception (2026-10-03) |
| | Other trades in brackets | GEM Other trades in brackets; Practice Ownership answers (3) |
| | Point lines only on AME controllers | Practice Ownership answers (2); GEM Verb rules (Furnish, the estimator's rule) |
| | Minimum points on AME-run equipment | GEM Mandatory minimum points; Feedback signals; VFD fault naming rule; Self-QC 04 (see §4: citation added, VFD control only with a VFD) |
| | Start/stop covers the relay and status switch | GEM Additional rules: start/stop and status |
| | Fire alarm interface | GEM Fire alarm and life safety interface, steps 1 to 3; Self-QC 08 |
| | Unclear ownership is flagged | GEM Contradiction and assumption scan, conflicts 1 to 4; Flags (confirm ownership) |
| Counts and quantities | Higher count prints | Practice Contradicted counts; GEM Quantity detailing; Design §2.5 |
| | Never undershoot | Design §2.5; GEM Quantity detailing ("never invent a number"); Contradiction scan, conflict 6 |
| | Line quantity | GEM Additional rules: consolidating identical lines; Quantity detailing; House style `trailing_forms` |
| | Systems named only in the sequence | Practice Systems named only in the sequence; GEM same section |
| Clarifications and assumptions | One clarification per block | Practice Flags in the draft; GEM One clarification per block; Design §2.6 |
| | Every assumption says why | Practice Assumptions give their reason; GEM Flags (assumed); Contradiction scan, conflict 5 |
| | Client notes | House style `notes` (rule, examples, `by_unit_mfr`); Template `schedule_overrides` notes ("**LEAK DETECTION BY UNIT MFR.") |
| | Miscellaneous responsibilities | GEM Miscellaneous responsibilities; House style `sow_positions` position 20 (printed as "**" notes) |
| | Words the client never sees | House style `forbidden` (words, category words, hours pattern) and `internal` (source ids, GEM words, "CC" written AME) |
| | Questions for the estimator | Practice Systems named only in the sequence ("never held back as a question only"); Design §4.7 |
| Packaged units | Packaged units | Practice Packaged units, what AME does; Practice Factory controls; GEM Packaged units, "four things" |
| | No AME controller on a packaged unit | GEM Packaged units, quick scan declaration; Self-QC 02 |
| | Nothing inside the unit is a line | Practice Packaged units; GEM Packaged units, "what is inside the unit is not a line" |
| | Factory-installed devices | Practice Ownership answers (1); GEM Packaged units item 3; Blanket wiring clause exception |
| | Template is the ideal case | Practice Packaged units (last sentences); GEM Packaged units item 4 |
| Shipped-loose devices | Shipped-loose devices | Practice Shipped-loose devices; Practice Factory controls; GEM Packaged units item 1; GEM Verb rules (Install and Wire) |
| | Shipped-loose devices not named | GEM Packaged units item 1 (no submittal in hand); Template Packaged entry ("mfr. provided sensors shipped loose"); citation added (§4) |
| | Thermostat furnished by the unit manufacturer | Template `schedule_overrides` "thermostat by the unit manufacturer"; Practice VRF systems |
| Dampers under their fan | Dampers under their fan | Practice Damper actuators (2026-10-03) and Damper actuators, where they go; GEM Where damper actuators go |
| | Untraced dampers in their own block | Practice Damper actuators, where they go; GEM same |
| | Unclaimed dampers in their own block | Practice Damper actuators (2026-10-03); GEM same |
| | Fire and smoke dampers keep their own block | Practice Damper actuators (2026-10-03); GEM same; Template Fire / Smoke Dampers |
| | One line per damper type | GEM Damper actuator rule, distinct types; Self-QC 07 |
| Duct heaters | Duct heaters in one place | Practice Electric duct heaters, one clear write-up (2026-10-04) |
| | Heater on a packaged unit | Practice Electric duct heaters (2026-10-03); GEM Electric duct heaters |
| | Heater on an AME controller | Practice Electric duct heaters; GEM Electric duct heaters |
| | Heater assignment wins | Practice Electric duct heaters (the estimator, 2026-10-04); House style `packaged_units` heater assignment and rejection patterns, in words |
| VRF and split systems | VRF and split as one block | Practice One system, one block (2026-10-04) |
| | VRF lines | Practice VRF systems; Template VRF System entry (order) |
| | VRF wiring belongs to the manufacturer | Practice VRF systems |
| | Split system interlock wiring | Practice Split systems and VRF; Template Split System entry |
| | Refrigerant leak detection wiring | Practice Split systems and VRF |
| | BMS space sensor on AC units | Practice BMS space temperature sensor on AC units (2026-10-04) |
| Integration lines | Integration trio | GEM Integration lines; House style `integration_trio` (text, depths, `applies_when`); Template `integration_trio`, `factory_controls` |
| | Integration lines cover monitoring | Practice Packaged units (3); GEM Packaged units item 4 |
| | Integration lines last | GEM Integration lines (never split, last, VFD group first); SOW order 19; Self-QC 09 |
| UUKL | UUKL listed smoke control | Practice Smoke control (UL-864 UUKL); GEM same section |
| Residential equipment | Residential equipment stays in scope | Practice Residential equipment in the hundreds |
| | Factory thermostat units with no BMS work | Practice Residential equipment; Template `not_priced` (reasons) |
| | Electric unit heater with factory thermostat | Practice Residential equipment |
| Front end | Front end mode | Front end `headings`, `existing_systems` (`unnamed`) |
| | Front end lines cite the specification | Front end `variants` (lines and wording), with Design §2.2 (see §4) |
| | Front end items by others | Front end `conditions` (`*_by_owner`, `network_by_others`, `not_ownership`), `client_notes` |
| | Auto dialer with a network panel | Template HVAC Alarm Panel `becomes_exception_when` (the estimator, 2026-09-25) |
| | Warranty lines | Front end `warranty` |
| Exceptions and alternates | Named exceptions | Template `not_priced` (`exception` form, reasons, `bms_words`); Practice Residential equipment |
| | Never invent an alternate | Practice Residential equipment ("never invent an alternate") |
| | Exclusions | GEM Verb assignment (last case); Assumptions and clarifications format (exclusions); Fire alarm interface step 2 |
| Tech hours | Tech hours follow the shape | Template `tech_hours` per entry; House style `software_points`; Template `not_hardware_points_containing` |
| | Tech hours the shape cannot express | Template Gas Detection, Kitchen Exhaust Ventilation, VAV, Global Points, Packaged entries (`of` and two-part rules) |
| | Integration-only systems | Practice Systems named only in the sequence (4 hours per integration) |
| | Tech hours never print | House style `forbidden`, `notes` rule |
| Shapes and wording | Template gives shape only | Design §2.3; Practice Packaged units ("the ideal case") |
| | Placing a device in a slot | This Playbook's format (shapes.json `conventions`); GEM SOW order (places an added line) |
| | Standard order | GEM SOW order, the standard order 1 to 20 |
| | Line form | GEM SOW format; Additional rules: sensor naming, filter DP switches; House style `guide`, `trailing_forms`, `no_verb_starts`, `max_line_length` |
| | Untemplated systems | House style `about`, `header`; memory rule "write any system" (compose from evidence in house style) |
| | One system one block | Memory rule "the GEM is the method" (one system, one sequence section, never collapse); Practice One system, one block |

## 2. Shapes

Every Master Template entry is a shape, with its header form, family names, line order (its lines in template
order, each turned into a slot), wording forms and tech-hour rule. Every shape also gets the "other" slots (before
the integration lines, in the GEM's standard order) and both integration trios, so a line beyond the template has a
place; a slot never makes a line by itself. Changes from the template, all shape-only:

| Shape | Source | Changes |
|---|---|---|
| VAV / Fan VAV | Template VAV / Fan VAV | Kind word "vav" added (template has none). The three power choices are two slots (power loop, transformer); "24V Transformer by Unit Mfr." is a client note when the documents say so. |
| Existing Fan Coil Unit (relocated) | Template same | Kind words lower case; moved before Fan Coil Unit (more specific). |
| Fan Coil Unit | Template same | Kind word added. |
| Air Handling Unit | Template same | Kind word added. Ionization tie-in kept before the integration lines. |
| Packaged ERU / RTU / AHU | Template same | Kind words for its own prefixes added (rooftop unit, energy recovery unit or ventilator, dedicated outdoor air). Ionization tie-in moved before the trio (GEM: integration last). `standard_lines` dropped. |
| Toilet Exhaust Fan, Dryer Exhaust Fan, Kitchen Exhaust Ventilation, Post-Fire Smoke Purge Fans | Template same | Moved before Exhaust Fan so their kind words win. Kitchen: MAU removed from prefixes (it picks Packaged first), kept as a family. Purge: controller slot added for the UUKL line (Practice UUKL). |
| Exhaust Fan | Template same | Standard damper and start/stop lines become plain slots. |
| Stair / Elevator Vent | Template same | Kind words "stair vent", "elevator vent" (the template's label has a slash and could never match); smoke detector interlock slot. |
| Stair Pressurization Fans | Template same | — |
| Gas Detection | Template same | EF and SF removed from prefixes (they would pick Exhaust Fan for the whole group); kept as families. Sensors and horn/strobes are their own lines (no depth in the format). |
| Fire / Smoke Dampers | Template same; Practice damper rule | No "other" slots and no integration slots: the block holds only its interlock wiring and end-switch status. |
| Motorized Dampers | Practice Damper actuators, where they go; House style `packaged_units.damper_prefixes` (MD) | New: the untraced or unclaimed dampers' block. No tech hours (no source). |
| Duct Heater | Practice Electric duct heaters; GEM same | New: the template data has no heater entry although the practice rule cites one. Slots from the practice's full scope (discharge air temperature, SCR control, status/alarm, enable) and interlock-only scope (enable/interlock, auxiliary contact), plus a controller slot. No tech hours (no source). |
| Apartment Heat Pumps | Template same | The Nest line is an "alternate thermostat" slot. |
| HVAC Alarm Panel w/ Auto Dialer | Template same | The alarm list is a slot of its own; the exception line goes to the exceptions. |
| Finned Tube Radiation, EUH / CUH / UH, Air Curtain, Unit Ventilators | Template same | Unit heater: the three control choices are one controller slot; usable kind words. Unit ventilator: both variants merged into one order; terminal-strip devices are their own slot. |
| Geothermal System | Template same | Moved before Heat Exchanger and Chilled Water; prefixes cut to GHP, GWP, HGP (the others pick other plants first); kept as families. Temperature transmitters, meters, DP transmitters and valves grouped into shared slots (one line per distinct device still). Template order of its two trios kept. |
| Heat Exchanger, Chilled Water, Hot Water, Condenser Water Systems | Template same | Family names added from the hints where the template gives none (Chiller, Pump, Cooling Tower, Condenser Water Pump). Hot Water and Condenser Water get the missing comm-wiring slot (GEM: the trio is never split). Chilled Water keeps the template's trio order. |
| Refrigeration Monitoring System, Fuel Oil Pump System | Template same | Fuel oil gets the missing rep slot. |
| Integrated Equipment | Practice Systems named only in the sequence | New: one block per generator, plumbing pump, water heater, heat tracing, glycol feed or gas booster system, 4 hours fixed. |
| Misc Monitoring Systems | Template same | Header gets the house "Qty ({n}) {name} {tags}" form (the format needs a count). Each monitored item's details go in brackets on its line (no depth in the format). 2 hours per line. |
| Global Points | Template same | — |
| VRF System | Template same; Practice VRF systems | Prefixes IDU, BS, BC (ODU left to Split, as the template's split families have it; BC from the VRF family names). Leak-detection wiring slot (Practice Split systems and VRF). Central controller line keeps its house text (the bare "Install" verb is not a Job model verb). |
| Split System | Template same; Practice | Interlock line in the practice's words ("Low Voltage Interlock Wiring between Indoor and Outdoor Unit"); leak-detection wiring slot. |
| Computer Room Air Conditioning Unit | Template same | BMS space sensor is a slot only (Practice BMS space sensor on AC units). |
| Equipment VFD | Template same; Practice | 4 hours per unit (Practice: "VFD ... integrations", template had none). |
| Front End | Front end `variants` | New shape for the front end's devices (network panel, workstation, server, portable terminal, UPS, graphics, training, IT infrastructure). The heading is printed from the mode, not from this shape. No tech hours (no source). |

## 3. Wording

| Form | Source |
|---|---|
| Verbs | GEM Verb rules (the five ownership verbs). |
| Owner brackets | GEM Other trades in brackets; Practice Ownership answers (3). Electrical Contractor and Owner follow the same form. |
| Integration trio | Template `integration_trio`, House style `integration_trio` (word for word, depths 1, 1, 2). |
| Clarifications | confirm "*Confirm {text}" and assumed "*Assumed: {text}" are the forms the old app printed (House style `internal.doubled_labels`); per_drawings "*Quantity per {text} drawings" is the Practice's "*Quantity per plumbing drawings"; note "**{text}" is the House style client note. |
| Header | Template and House style header "Qty ({n}) ..."; "##" for an unknown count (Design §2.5); tags joined ", " as the template writes them. |
| Quantity | GEM Quantity detailing "(Qty. N Total)"; unknown "(Qty. ##)" (Design §2.5); the others note names every other count (Practice Contradicted counts). |

## 4. Dropped or changed, and why

For the estimator's review. Items marked **decide** change what used to print.

1. **Template content flags.** `default`, `standard`, `standard_lines`, `standard_text`, `standard_if`,
   `standard_needs`, `standard_field_ddc`, and the note "*Assumed per AME standard - confirm": dropped. Ground rule
   2 (no standard line, no fallback line).
2. **Template selection logic.** `conditions`, `when`, `unless`, `choice`, `of`, `quantity` ("per_unit",
   "counted", "one"): dropped. Which lines a block has is decided by this job's documents, not by the template.
3. **Template hints and client notes.** Estimator hints ("look for GPM in the schedule", typical quantities, job
   numbers) are dropped (ground rule 3 and the memory rule "estimator hints never"); the tech-hour hints became the
   tech-hour rules; "*Fans Are Controlled via Fire Alarm System" is content and prints only when the documents say so.
4. **GEM "the Master Template entry is the frame"** ("write its lines ... leave a template line out only when the
   documents exclude it"): replaced by "Template gives shape only" (ground rule 3).
5. **decide — Minimum points.** The GEM wrote fan and pump start/stop and VFD control "always" on field DDC, with
   the reference "(Mandatory minimum point ... not explicitly called in sequence)". Now they need the citation that
   puts the equipment under AME's controller, and VFD control needs a VFD the documents show.
6. **decide — Front end standard lines.** `front_end.json` printed Network Level Control Panel, PC Workstation,
   3-D Graphics and Training always ("keep"), the workstation unless given to the owner, and filled to six lines.
   Now each front end line needs the specification's citation (ground rule 2).
7. **decide — Shipped-loose generic line.** "Install and Wire Mfr. Provided Shipped Loose End Devices" now needs a
   document saying devices ship loose; it is no longer written for every packaged unit without a submittal.
8. **GEM unknown-quantity forms** "(Qty. per Mechanical Schedule) / (Qty. per Drawing) / (Qty. per Engineer)":
   replaced by "Qty (##)" / "(Qty. ##)" and the block's "*Quantity per <trade> drawings" or "*Confirm quantity"
   (ground rule 5).
9. **GEM chat output.** The printed Quick Scan, system explanation, reference lines under each scope line, the
   "— CONTRADICTIONS AND ASSUMPTIONS —" section, the flag words in a flag field and the Self-QC printout: not
   proposal text. Their work is kept (the reading steps, Ref quotes, Device.flag, one "*" per block, the validators
   and QC), their print form is dropped.
10. **House style regular expressions** (`line_order` and `sow_positions` patterns, `spec_openings`, `internal`,
    `clarifications` filters, `unit_maker_devices`, `misc_monitoring`, `review`, `packaged_units`, `panels`): the
    text-pattern layer the rebuild replaces (design §1). Their meaning is kept in rules (standard order, words the
    client never sees, client notes, packaged units, heater assignment, named exceptions). The stacked Misc
    Monitoring header is dropped (one header per block).
11. **The bare verb "Install"** (template and house style verb lists): not a Job model verb; lines that used it keep
    their house text in a fixed wording (VRF central controller).
12. **Template prefixes that pick the wrong shape**: Gas Detection EF and SF, Kitchen MAU, Geothermal CHWP, HWP, ET,
    PFHX, AS, VRF ODU. Kept as family names. `shape_for` picks the first shape sharing any prefix.
13. **Sub-lines one level in** (Gas Detection sensors, HVAC alarm list, unit ventilator terminal-strip devices, Misc
    Monitoring details): the shape format has no depth except the integration trio's; these print as their own
    lines, Misc Monitoring details in brackets. Needs a format change if the estimator wants them indented.
14. **Two-part tech hours** (Gas Detection panel plus fan, Kitchen per KEF only): the format has one basis per
    shape; the full rule is in "Tech hours the shape cannot express".
15. **No source for hours**: Duct Heater, Motorized Dampers, Front End, Existing Fan Coil Unit, Post-Fire Smoke
    Purge Fans, Exhaust Fan without a controller: left empty for the estimator.
16. **GEM fire alarm "(Module Furnished by FA)"**: the format has one bracket per party; FA prints "(Relay
    Furnished by FA)". A run-status module line names the module in the device's words.
