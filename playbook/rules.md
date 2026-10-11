# AME Playbook — the rules

<!--
Format (read by src/bms/playbook.py; the whole file is also the cached instructions of every AI step):
- One "## " heading per topic. Topics are fixed below; a new topic needs the controller.
- Under a topic, each rule is a "### " heading with its short name, then plain sentences.
  The short name is the rule's id: a validator's or the QC pass's Finding.rule is exactly this name.
- Rule names are unique across the file. No rule outside a topic. No empty rule.
- Plain words only: no invented codes, no example from another job.
Sources: docs/superpowers/specs/2026-10-04-playbook-sources.md maps every rule to the GEM (v4), the estimator's
practice rules (ame_practice.txt), the house style, the Master Template and the front end it came from.
-->

How to read this book. AME is the controls contractor whose scope is being written. A job is written as blocks: one
block per system, a header ("Qty (n) name tags"), then its lines. Each line is a device, a point, an interlock, a
wiring item or an integration line, and each one rests on this job's documents. Where a rule here and a shape in
shapes.json seem to differ, the rule wins: a shape only says how a line looks and where it goes.

## Evidence and citations

### Every line cites this job
A device line is written only when this job's documents call for it. It carries at least one citation: the source
id, the exact words, and where they are (sheet, specification section, page). A line with no citation is not
written.

### No standard or fallback lines
There is no "AME standard" line and no fallback line. A line is never added because systems of this kind usually
have it, because the Master Template lists it, or to fill a gap. If the documents are silent, the line is not
written; if the gap matters, ask the estimator a question. The front end house lines are the one exception.

### Nothing from other jobs
Wording, devices, counts and examples come only from this job. Never reuse a line, a note or a quantity from
another job, even a similar one.

### Read the whole sequence first
Before writing any line, read the entire sequence of operation and the point list. Note for the job: every system
and equipment type; for each unit, whether it is field DDC (AME's controller), packaged (factory or OEM controls) or
mixed; whether a submittal is in hand; any blanket wiring clause, quoted; any fire alarm interface, with its relay
and module types; whether a point list is given; and the term the documents use for the controls contractor. Do not
start writing until this is done.

### Contractor name in the documents
Each specification has its own word for the controls contractor ("BMS Contractor", "ATC Contractor", "This
Section", "Controls Contractor" and others). Find the party the documents give the controls work to; whatever it is
called, that is AME. Use that term to decide ownership throughout. If several terms are used, all count. If the
term is unclear, flag the ownership before writing. Never reject an assignment because the term is unfamiliar.

### Everything assigned is extracted
List every item the documents give the controls contractor, in two groups. Devices and hardwired signals (every
sensor, actuator, switch, valve, relay, meter, detector, transmitter and hardwired signal) become lines. Other
responsibilities (panel work, demolition, wiring runs not tied to a device, coordination, testing) become lines
too (see Miscellaneous responsibilities). Nothing on the list is dropped. Every device on the list
has its line, and every line is on the list.

### Occupancy sensors are never dropped
Every occupancy sensor that the controls documents show ends as a line for AME or as an ownership flag in the
block's clarification. It is never left out.

### Sequence first, point list second
The sequence is the main source; the point list confirms it. Read the sequence first, then check the point list
for anything more. A point only the point list calls is written with the note "(As per Point List — not called in
sequence)". A point in both, or only in the sequence, takes no such note. Never absorb a point-list item silently.

### Every point-list point is checked
Check every point on the point list. A hardware device needs a line with the right verb. A hardwired signal
(start/stop, status, speed control, enable, feedback) needs a Furnish line in the point list's exact name, but only
on a system AME's own controller runs; on a packaged unit the integration lines cover it. A software or calculated
point gets no line.

### Device names from the documents
Name each device with the exact noun the documents use. Do not paraphrase, simplify or substitute. CO2 is always
CO2. A "spill air damper" is a Spill Air Damper Actuator, never an Exhaust Air Damper Actuator. When the documents
name a slot's device differently from the shape, use the documents' noun. Device names are in Title Case.

## Ownership

### Every line carries its ownership
Every line says who furnishes, who installs and who wires the device, and its verb follows from those three
answers. Getting this right is AME's responsibility on every line; restating the sequence is not.

### Who owns what by default
Work that belongs to another party is not AME's scope unless the documents give it to AME. Fire alarm contractor:
fan start/stop through the fire alarm, smoke and duct detectors, any command the fire alarm starts. Mechanical
contractor: valve bodies and piping. AME is the mechanical contractor's subcontractor for controls, so a controls
item or sensor that the documents give to the mechanical contractor is AME's (see Controls given to the mechanical
contractor). Electrical contractor: VFDs unless the controls contractor furnishes them, line-voltage wiring,
conduit, disconnects. Unit manufacturer: factory-mounted sensors, factory controls, isolation valves and internal
safeties. Owner: anything the specification calls owner-furnished. Sheet metal contractor: ductwork, and installing
airflow measuring stations.

### Three ownership questions
Ask three questions of every device, with no exception. Who furnishes it: the party the documents name; with no
party named, AME on a field DDC unit, the unit manufacturer on a packaged unit (then no line). Who installs it: the
party named; with none named, AME on a field DDC unit, the unit manufacturer on a packaged unit or when it is
factory-mounted. Who wires it: the party named; with none named and the device under DDC control, AME.

### Verb from the three answers
AME furnishes, installs and wires: Furnish and Install. AME furnishes and wires, another trade installs or pipes:
Furnish and Wire. Another party furnishes, AME installs and wires: Install and Wire, with the furnishing party in
brackets. Another party furnishes and installs, AME only wires: Wire, with the party in brackets. Another party
furnishes, installs and wires: not AME's scope; it goes to the exclusions only. Furnish alone is for a hardwired
signal with no physical device. No dash between the verb and the device.

### Verbs by device type
Field sensors and transmitters (temperature, humidity, CO2, pressure, static and differential pressure, current
switches, leak detectors, freezestats, limit and pressure switches), damper actuators, and interposing relays the
documents give to AME are Furnish and Install. A DDC controller, enclosure and transformer are Furnish and Install
on a field DDC unit only. Every valve and its actuator is Furnish and Wire, without exception. Filter differential
pressure switches are Furnish and Wire. An airflow measuring station AME furnishes is Furnish and Wire.

### Explicit assignment always wins
When the documents name the controls contractor for a device or a task, that overrides every default here,
including the packaged-unit defaults. A generic "provide", "furnish" or "install" with no party named is not an
assignment to AME.

### Controls given to the mechanical contractor
AME is the mechanical contractor's subcontractor for controls. A controls item or sensor that the documents give to
the mechanical contractor ("by MC", "by HVAC contractor", "mechanical contractor shall provide ...") is AME's
scope. It is written with the normal AME verb. It is never a named exception and never "(Furnished by Mechanical
Contractor)". An exhaust fan space thermostat "by MC" is "Furnish and Install Space Thermostat". A leak detector
"by MC" is "Furnish and Install Leak Sensor". Work that is not controls stays with the mechanical contractor: valve
bodies and piping. AME still furnishes and wires the control valve and its actuator.

### Schedule notes address the manufacturer
A note on an equipment schedule is the unit or pump manufacturer's instruction, unless it names the controls
contractor (ATC, BMS or controls contractor) or gives BMS wiring ("wire to BMS", "by BMS contractor", "by ATC"). A
generic "provide ..." in a schedule note is not an assignment to AME. The note is still read: it tells which
devices come with the unit (shipped loose, integral, factory mounted), and that decides the Install and Wire,
Tie-in and client note lines. A schedule note that gives a controls item to the mechanical contractor makes it
AME's (see Controls given to the mechanical contractor).

### Mixed ownership device by device
Decide each device on its own. A field DDC unit may have a device the unit manufacturer furnishes; a packaged unit
may have a device the documents give to AME.

### Blanket wiring clause
A clause such as "all control wiring by this contractor" makes AME wire every device in that sequence block,
including devices other parties furnish and install: write a Wire line for each such device, not absorbed into the
integration lines. Exception: a device installed at the factory inside a packaged unit is never a line, clause or
not (see Factory-installed devices).

### Other trades in brackets
Name the furnishing party in brackets after the device: "(Furnished by Unit Mfr.)" for the unit manufacturer;
"(Relay Furnished by FA)" for fire alarm relays and signals; "(Furnished by Others)" for dampers and end switches by
the sheet metal contractor; "(Furnished by Mfr.)" for the condensate pump float switch (see Condensate pump float
switch); "(Furnished by Electrical Contractor)" and "(Furnished by Owner)" when those parties furnish. A controls
item that the documents give to the mechanical contractor is AME's and has no bracket (see Controls given to the
mechanical contractor). The bracket names only the furnishing party; who installs is kept in the Evidence Package,
not printed.

### Leak detectors
A water leak detector or drip pan detector at a unit is "Furnish and Install Leak Sensor": AME furnishes, installs
and wires it like any field sensor. This holds on a packaged unit too, and when the documents say only that it is
wired to a local alarm panel and name no furnishing party. It is the exception to the packaged unit default in
Three ownership questions. The device name is Leak Sensor, as the Master Template names it. Refrigerant leak
detection that is part of the unit is not a line. Its client note is "**Refrigeration Leak Detection system is
coming with the unit per equipment schedule". The wiring that AME does for refrigerant leak detection is a line
(see Refrigerant leak detection wiring).

### Condensate pump float switch
The float switch of a condensate pump comes with the pump. When the documents say that the BMS ties in to it (a
detail, a sequence or a plan note gives the wiring to the BMS), AME writes "Tie-in Condensate Pump Float Switch
(Furnished by Mfr.)". The bracket is "(Furnished by Mfr.)", never "(Furnished by Mechanical Contractor)". A pump
schedule note such as "provide float operated high water alarm" is the pump manufacturer's note (see Schedule notes
address the manufacturer). It does not give AME the tie-in by itself.

### Local alarm panel
When leak detectors or a condensate overflow report to a local alarm panel (a local audible or visual alarm) that
the documents show, AME writes "Furnish and Install Local RAM Module" in the block of the unit they serve. This is
also so on a packaged unit, with no party named (see Three ownership questions). The line is not written when the
documents show no local alarm panel.

### Point lines only on AME controllers
"Furnish <point>" lines (start/stop and status, speed control, enable, setpoint, alarms, feedback) are written only
for a system AME's own DDC controller runs. On a packaged or factory-controlled unit the three integration lines
cover every monitored point. A fan whose points land on the controller of another AME unit (an exhaust fan wired to
the air handler's controller) counts as run by an AME controller (see Every block lists its end devices).

### Minimum points on AME-run equipment
On equipment AME's own controller runs, write these points with the documents' citation that puts the equipment
under AME's control. Fans and pumps: Start/Stop and Status; VFD Control when the equipment has a VFD. Boilers:
Enable, Status, Alarm/Fault; Setpoint only when the sequence calls for a BMS reset. Chillers: Enable, Status,
Alarm/Fault. Cooling towers: Fan Enable, Fan Status and Fan VFD Control; the Fan VFD Fault, like any VFD fault, is
written only when the documents call it, in their exact term (Fault, Malfunction or Safety Stop). VFD speed
feedback, position feedback and open/closed status from end switches only when the documents call them. These
are never listed for equipment on factory controls unless the documents give them to AME.

### Every block lists its end devices
A block is never only "Interlock with ...". When the sequence or the control diagram gives a system points, the
block lists all its end devices. For an exhaust fan these are, as the documents call for them: start/stop and
status, VFD control, VFD fault and the damper actuator. This holds when the points land on the controller of
another AME unit, such as the air handler: the lines stay in the fan's block, and a client note says where the
points land.

### Start/stop covers the relay and status switch
"Furnish <fan> Start/Stop and Status" includes the relay and the current switch. Do not add a separate current
switch line for the same status.

### Fire alarm interface
Find every hardwired fire alarm interface in the documents: stop and start relays and run status modules per fan
or equipment, damper override and open/close relays per damper or group, and any other relay or module named. When
the documents give AME the wiring, write one Wire line per distinct relay or module type, "(Relay Furnished by
FA)"; never one line for several types. When the fire alarm contractor wires it, it goes to the exclusions only.
When unclear, flag the ownership.

### Unclear ownership is flagged
Flag the ownership to confirm when: the same device is given to two parties in different places; AME furnishes a
device in one place and another trade installs or wires it elsewhere; a device is in AME's scope and also in an
exclusion; or a device with real cost has no named party and no default fits. Quote both places.

## Counts and quantities

### Higher count prints
When the documents give different counts, the highest count prints, flagged, and every other count is named with
where it is. The estimator decides on review. Every count that differs from the printed one prints in the same line
(see Quantities print in the line).

### Never undershoot
Never print a count lower than one the documents give. Never invent a number. An unknown count prints "Qty (##)", in
a header and in front of a line, flagged to confirm. The only exceptions, here and in Higher count prints, are the
units on demolition sheets, whose count moves to Demolition Scope with its number, and a duplicate label of one unit
on two part plans, which a short "*" line names with both numbers.

### Line quantity
A line's quantity prints only when it differs from the block's count, in front of the line, as
"Qty (N) <device line>". When it equals the block's count, the line has no quantity in front. Identical lines for
several units are one line with the total ("Qty (6) Furnish Chiller Enable"), never one line per tag.

### Systems named only in the sequence
A system the sequence names but no drawing shows (an emergency generator, plumbing pumps, domestic water heaters,
heat tracing, glycol feed, a gas booster) is printed in the base bid with its integration lines, "Qty (##)", and
the clarification "*Quantity per plumbing drawings" (or the drawings of the trade that shows it). It is never held
back as a question only.

### Demolition Scope
A demolition plan shows the previous job's units: removed, remaining or relocated. Their count never goes into the
new-work blocks. It prints in one block headed "Demolition Scope", the last block of the scope, in lines such as "Qty
(n) AHU demo", "Qty (n) FCU Existing to Remain" and "Qty (n) VAV Relocation". Named work on such a unit, such as
refurbishing it or relocating its sensors or thermostat, is a line of this block.

### One unit on two part plans counts once
One unit can show on two part plans that share an area. Count it once. The other labels are duplicates of the same
unit. A short "*" line gives both numbers.

### Quantities print in the line
A quantity prints in the line it counts. The block heading keeps "Qty (n) <system>". A device line inside a block
starts with its count, "Qty (N) <device line>", when the device count differs from the block count (for example
"Qty (33) Furnish and Install Space Temperature Sensor"). It is never a bracket "(Qty. N Total)" at the end of the
line. There is no separate quantity note. When two counts differ, the line prints the highest and names each other
count with where it is, in brackets, for example "(4 per plan placements)".

## Clarifications and assumptions

### One clarification per block
A block has at most one "*" clarification of each kind, naming the lines it covers: the quantities to confirm, the
ownership to confirm and the assumptions made. Do not put a bracket on every line; the per-line detail stays in the
Evidence Package. When a block needs several items of one kind, they are joined in that kind's one line. Its forms:
"*Confirm quantity: ...", "*Confirm ownership: ...", "*Assumed: ...", "*Quantity per <trade> drawings", and
"**<note>" for client notes. Each "*" line is one short line, never a paragraph. Several "*" lines in one block are
fine when each is a different item. A "*" line that the estimator must see prints in red.

### Joining into the one clarification
Each kind prints as one line, in a fixed order after the block's lines: to confirm, assumed, per drawings, client
notes. The items of one kind are joined with "; " in that kind's form. Example: "*Confirm quantity: 4 per schedule",
then "*Assumed: relay by AME, as the sequence asks for a stop", then "**Start/Stop via Fire Alarm System". The front
end block follows the same rule.

### Every assumption says why
Every assumption says what was assumed and why, in a few plain words naming the document or the missing
information: "*Assumed: duct static pressure sensor shipped loose by the unit manufacturer, as the schedule shows no
factory sensor". A bare "*Assumed: unit type" is never printed. An assumption is an item AME prices on judgment, so
it always carries its reason.

### Assumption wording has no source ids
An assumption or a clarification names the sheet or section it rests on ("M-201", "the fan schedule"), never a
source id ("S12", "S40 note 1"): source ids are for the model's citations only. The Evidence Package shows, on
every scope line, where the documents say it, word for word: the sheet, the page and the quote, not an id.

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

### Miscellaneous responsibilities
Controls work that is not a device (panel and enclosure work; demolition of tubing, wiring, transducers and
sensors; wiring and conduit not tied to a device; coordination and testing given to the controls contractor) is
never dropped: it is priced scope, so it is always a line of its own, with its citation and its three ownership
answers. Work a house verb can carry takes that verb: panel and enclosure work in the device slot ("Furnish and
Install Control Panel Enclosure"), wiring and conduit in the wiring slot ("Wire <run> per <section>"). Work no house
verb carries (demolition, coordination, testing, other work not tied to a device) is one plain statement per
responsibility in the block's other_wiring slot, which prints with no verb in front, the way the Existing Fan Coil
Unit shape prints its demolition and re-commissioning lines ("Demolition of Existing Pneumatic Tubing and
Sensors"). It is never folded into the block's one clarification. Leave them out when there are none.

### Words the client never sees
Nothing printed (header, line or note) carries: prices or dollar signs, tech hours, confidence, rule names, source
ids, "GEM", "QC", the flag words in capitals (CONFIRMED, ADDED, ASSUMPTION, PENDING, DISCREPANCY, EXTRA, MISSING,
ORPHANED, CONFLICT, EXISTING), or the reasoning words "mandatory minimum", "field DDC default", "Quick Scan". The
controls contractor is written AME.

### Questions for the estimator
What the documents cannot settle and that changes the price is a question for the estimator, kept off the
proposal. A question never replaces a line the documents call for; a missing count prints "Qty (##)" and asks. A
question is asked once. A question that holds for a whole family is asked once for the family, never per unit or per
line.

### A stated fact is not an assumption
When a schedule or the sequence states a fact, write it as stated and cite it. Never print "Assumed" for it.

### Red flags for the estimator
An item the documents mark FUTURE prints as its normal line, then "(FUTURE AS PER <source>)" in red font, naming the
sheet or section. An item the estimator must notice, such as an integral drain pan level sensor that the factory
furnishes, is highlighted red in the scope. Red marks what the estimator must see.

## Packaged units

### Packaged units
A packaged unit comes with its factory controller, its end devices and its equipment wired inside at the factory.
The controller and every end device belong to the unit manufacturer unless the documents (sequence, schedule note,
plan note or detail) give one to the controls contractor. AME's work on it is limited to four things: the
shipped-loose devices; any device the documents explicitly give to the controls contractor, with the normal verb;
wiring to a factory-installed device only when the sequence gives that wiring to AME; and the three integration
lines, last. Three field devices at the unit are also lines: the leak detector, the local alarm panel module and
the condensate pump float switch tie-in (see Leak detectors, Local alarm panel and Condensate pump float switch).

### No AME controller on a packaged unit
Never write "Furnish and Install DDC Controller" for a unit on factory controls.

### Nothing inside the unit is a line
What the sequence describes inside the unit (valve control, fan control, DX staging, leak control, reheat, internal
sensors, actuators, safeties, filter switches, airflow stations) is wired at the factory and is not written. Do not
write a line per monitored point or per internal device. These are outside the unit and are lines: the leak
detector at the unit, the local alarm panel module and the condensate pump float switch tie-in (see Leak detectors,
Local alarm panel and Condensate pump float switch); a remote duct damper actuator that a riser or a plan shows (see
Damper actuators are Furnish and Install); and the control devices of a unit when AME provides its controls (see
Unit control devices when AME provides the controls).

### Factory-installed devices
A device that the unit manufacturer furnishes and installs at the factory is never a line, blanket wiring clause or
not. It becomes "Wire <device> (Furnished by Unit Mfr.)" only when the sequence itself gives the wiring of that
device to the controls contractor. A device that AME furnishes to the factory for installation is AME's (see Unit
control devices when AME provides the controls).

### Unit control devices when AME provides the controls
When AME provides the controls of a unit, including a controller that AME furnishes to the unit manufacturer for
installation at the factory, the control devices on the unit schedule are AME's: temperature and enthalpy sensors,
freezestat, drain pan level sensor and filter switch. They are "Furnish and Install", or "Furnish and Wire" when
the factory installs the device and AME wires it. Do not write "Install and Wire ... (Furnished by Unit Mfr.)" for
them unless the documents clearly give the device to the unit manufacturer. When unsure, keep the device as AME's
and flag the ownership.

### Template is the ideal case
The Master Template shows how the system looks in the ideal case. When the sequence says something explicit, it
is taken into account. AME's task is the right ownership on each line, not restating the sequence.

## Shipped-loose devices

### Shipped-loose devices
A device the unit manufacturer furnishes and ships loose (space sensor or thermostat, supply air temperature
sensor, supply static pressure sensor and the like) is written "Install and Wire <device> (Furnished by Unit Mfr.)"
on its own line, wired to the unit's own controller. Write out every manufacturer-furnished device the job names
that AME installs or wires. A unit schedule (an ERV, an RTU or any other unit) can list end devices shipped loose, in
a column or a note. Read it, and write each one as a line. "Wire <device> (Furnished by Unit Mfr.)" is only for a
device the manufacturer already mounts. When unsure whether it is mounted, write Install and Wire. This is for a unit
on the manufacturer's controls. When AME provides the controls of the unit, see Unit control devices when AME
provides the controls.

### Shipped-loose devices not named
When the documents say the unit ships devices loose but do not name them and no submittal is in hand, write one
line, "Install and Wire Mfr. Provided Shipped Loose End Devices (Furnished by Unit Mfr.)", citing that statement,
with the quantity per the mechanical schedule flagged to confirm. Never write it when the documents say nothing
about loose devices.

### Thermostat furnished by the unit manufacturer
A thermostat the unit manufacturer furnishes is "Install and Wire <thermostat> (Furnished by Unit Mfr.)", in the
documents' words (space thermostat, programmable thermostat).

## Dampers under their fan

### Dampers under their fan
A damper actuator is written in the block of the fan or unit it serves (the exhaust fan's damper, the make-up air
fan's damper, the unit's outside air damper), never gathered into one motorized damper block at the end. The link
is on the plans and risers: when the duct can be traced on the plan or through the riser floors, the actuator goes
under that fan's or unit's block.

### Count every damper
Count every damper actuator the plans show, tagged or not. Never assume one actuator per unit. Trace each damper's
duct to the fan or unit it serves and write the actuator in that block (see Dampers under their fan). A damper that
cannot be assigned goes in the Motorized Dampers block (see Untraced dampers in their own block).

### Damper actuators are Furnish and Install
A damper that the plans, the risers, the control diagram or the sequence show gets "Furnish and Install ... Damper
Actuator" from AME, even when the equipment schedule lists the damper or its actuator with the unit. On a unit with
factory controls, a remote duct damper that a riser or a plan shows is AME's scope. A damper that only a schedule
shows is factory: the unit manufacturer furnishes it, and AME writes no line for it. When the schedule says that
another party furnishes a damper that a riser or a plan shows, still write the line and add the "*Confirm
ownership" clarification. A "Wire ... Damper Actuator" line is rare: it is for an actuator that another party
furnishes and installs and AME only wires.

### Untraced dampers in their own block
When a damper's fan cannot be traced, the dampers form one Motorized Dampers block of their own, with the sheet
references and the total count, flagged for the estimator.

### Unclaimed dampers in their own block
Dampers no fan or unit claims (stair-top vent dampers interlocked with a smoke detector, generator room dampers)
have their own block.

### Fire and smoke dampers keep their own block
Fire/smoke dampers have their own block, holding only the interlock wiring and the end-switch status, as the
Fire / Smoke Dampers shape writes them.

### One line per damper type
When a unit has several damper types, write one line per distinct type (minimum outdoor air, variable outdoor air,
return air, spill air, supply fan discharge and so on); never collapse them into one generic damper line. Add "w/
End Switches" when the documents speak of proving the damper open or closed; the switches are part of the actuator
line. Do not rename dampers.

## Duct heaters

### Duct heaters in one place
Duct heaters are written in one place: either their own block, or under the unit each heater serves, never partly
in the unit's block and again in a heater block. Each heater's scope (interlock only, or full scope) cites the
sequence or schedule item that decides it.

### Heater on a packaged unit
When the duct heater serves a unit with packaged or factory controls (an ERV, a packaged rooftop unit, a factory
make-up air fan), AME's scope is the interlock only: wire the heater's enable/interlock and auxiliary contact to the
unit's controls. The heater's own SCR control, airflow switch and cut-outs come with the heater.

### Heater on an AME controller
When AME's DDC controller controls the heater (a field DDC fan or unit), write the full heater scope: discharge air
temperature sensor, SCR control signal, status/alarm and enable.

### Heater assignment wins
When the sequence explicitly gives the BMS the heater's control (for example "the BMS will provide field installed
controls for the electric duct heater"), write the full heater scope even on a packaged unit. A sentence giving
only an enable, signal, interlock, status or alarm, or naming another party as providing the controls, is not such
an assignment.

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
Unit", the one that matches who provides the power. The power loop line is written when the mechanical drawings or
the specifications mention the 24 V wiring for the VAVs. A line is written only when the documents show the device.
Tech hours follow the shape: 3 per cooling-only VAV and 4 per VAV with a hot water valve.

### Radiation valves tied to VAV zone thermostats
When the documents run radiator, finned tube or perimeter heat valves from each VAV zone thermostat, with separate
wiring, AME writes an interlock wiring line for each zone. The line names the associated VAV, FCU or system as its
device. When AME furnishes the valve, the valve line is "Furnish and Wire Hot Water Control Valve and Actuator". A
line is written only when the documents show the valve and its interlock.

## VRF and split systems

### VRF and split as one block
A VRF system is one block: its indoor units, outdoor (condensing) units and branch selectors or branch circuit
controllers are written together, never as separate indoor, outdoor and branch blocks. A split system's indoor unit
and its outdoor unit are one block. The integration lines and "VRF Communication Wiring" are written once for the
system, in that block, never repeated in another block.

### VRF lines
Per indoor unit: "Install and Wire Programmable Thermostat (Furnished by Unit Mfr.)". The remote space sensor, leak
sensor or local RAM module only when the documents call for them. "VRF Communication Wiring" once. The condensate
pump float switch tie-in when there are condensate pumps. Then the central controller or BMS communication wiring,
Map Available Points and the manufacturer's representative line, once for the system.

### VRF wiring belongs to the manufacturer
Do not turn each item of a sequence's "BMS contractor shall wire..." list into its own Wire line. The interlock
wiring between indoor units, branch controllers and condensers is the manufacturer's VRF communication wiring,
unless the documents say otherwise.

### Split system interlock wiring
Write "Low Voltage Interlock Wiring between Indoor and Outdoor Unit" when the documents show the units
field-connected.

### Refrigerant leak detection wiring
When the documents show refrigerant leak detection with shut-off valves or an alarm chime on a VRF or split system,
write the wiring lines for them unless another party is named.

### BMS space sensor on AC units
The unit's own thermostat is "Install and Wire Programmable Thermostat (Furnished by Unit Mfr.)". A separate BMS
space temperature sensor on an indoor AC unit is written only when the documents call for one, citing the document
that does.

## Integration lines

### Integration trio
On a unit with the manufacturer's own controls, a manufacturer's gateway or BMS interface (BACnet, Modbus,
LonWorks), or where the documents say to map the unit's points, write three lines together, in this order:
"Furnish BMS Communication Wiring to <equipment> Factory Controls" (the equipment left out for plain factory
controls); "Map Available Points Via Mfr. Provided BMS Interface"; and, one level in, "AME requires mfr. Rep to
assist in integration, cost to be incurred by mech contractor". They take the place of a DDC controller line.

### Integration lines cover monitoring
The three integration lines cover every "monitor ... at the BMS" sentence for that equipment. Do not write a line
per monitored point.

### Integration lines last
The integration group is never split and always comes last in the block, after every device line and every fire
alarm Wire line. When both apply, the VFD group ("Furnish BMS Communication Wiring to <equipment> VFD Controls", map,
rep) comes before the factory controls group, except where a shape orders a plant's groups itself.

## UUKL

### UUKL listed smoke control
When the specification requires UL-864 UUKL listed control equipment for the smoke control sequences, write the
UUKL-listed controls in the scope: the stair or purge fan's controller line says "UL-864 UUKL Listed". Do not take
an exception.

## Residential equipment

### Residential equipment stays in scope
Apartment heat pumps, per-dwelling fans and the like, even in the hundreds, stay in the normal base scope when the
BMS has work on them. They go to an add or deduct alternate only when the documents clearly say so.

### Factory thermostat units with no BMS work
A unit that runs on factory controls with the maker's own thermostat (integral, line-voltage, or a manufacturer's
on/off switch), and that the sequence gives the BMS no work on, is a named exception, not a block.

### Electric unit heater with factory thermostat
An electric unit heater with a factory thermostat is one line, "Install and Wire Space Thermostat (Furnished by
Unit Mfr.)", with the plan count, when the documents give AME that work.

## Front end

### Front end mode
The front end is either a new web-enabled BMS ("Front End Web Enabled BMS System") or a tie-in to an existing one
("Seamlessly Tie in to the Existing <system> BMS"). The documents decide which. The existing system's name comes
from the documents; when they do not name it, print "[existing BMS name]" and flag it.

### Front end lines cite the specification
The house front end lines are the standard lines that the Master Template's front end section defines, with the
reason for each. Write each one as that section says and cite that section. Every other front end line (PC
workstation, BMS server, portable operator terminal, UPS, IT infrastructure) is written only when this job's
specification calls for it, with its citation. Graphics on a tie-in are "to match existing".

### Front end items by others
When the documents give the workstation, server or network switches to the owner or others in the same sentence,
the line is not written and the front end's one clarification carries the client note ("**PC Workstation by
Owner", joined as in Joining into the one clarification). A sentence about the owner's network connection or the
room's location is not the owner furnishing the item.

### Lighting control integration
When the documents give the ATC or BMS contractor the integration of a lighting control system (for example for
occupied standby), AME writes this line once, in the front end block: "Interface Lighting Control System (By
Others) With Front End BMS Via Manufacturer Provided BMS Interface". It is not written again in a Misc Monitoring
block.

### Auto dialer with a network panel
When AME furnishes a network level control panel, the BMS can send alarms by email and text, so an auto dialer
(Sensaphone or similar) the documents call for becomes the exception "EXCEPTION TO AUTO DIALER (BMS CAN SEND OUT
ALARMS VIA EMAIL AND SMS TEXT)".

### Warranty lines
Warranty scope is written only when the specification states the warranty and its length; an extended maintenance
contract only when it states the extra years.

### Existing BMS the house works with
AME works only with Honeywell WEBS, Johnson FX and Niagara Tridium. Those names print plain. Any other name prints in
red as "***<name>***" wherever it appears: in the front end heading and in the opening sentence. The front end then
gets one flag line: "***AME works only with Honeywell WEBS, Johnson FX (Facility Explorer) or Niagara Tridium front
ends". The fill-in "[existing BMS name]" prints the same way, with no flag line.

### No front end called for
When the documents call for no front end, the front end of the proposal says "No front end information found".

## Exceptions and alternates

### Named exceptions
A unit the documents leave with no BMS work is a named exception in the estimator's form: "EXCEPTION TO ANY WORK
WITH Qty (n) <tags> - <reason>" (for example INTEGRAL THERMOSTAT, LINE-VOLTAGE THERMOSTAT, MANUFACTURER ON/OFF
SWITCH). One BMS word in its own sequence paragraphs (BMS, DDC, monitor, alarm, status, BACnet) means it has BMS
work and is priced instead. The same word in a schedule note counts only when the note names the controls
contractor or gives BMS wiring (see Schedule notes address the manufacturer). A thermostat that the documents give
to the mechanical contractor is AME's, never an exception (see Controls given to the mechanical contractor).

### Never invent an alternate
A system is an add or deduct alternate only when the documents say so. Otherwise it is base bid.

### Exclusions
Work another party furnishes, installs and wires goes to the exclusions, one plain line each, only items relevant
to this job.

### Off-hours work and prevailing wage
When the documents name off-hours work (for example 6 PM to 6 AM) or prevailing wage, add each to the proposal and to
the price sheet, highlighted red. Never exclude either one silently. The standard exclusion "All off-hours or overtime
labor" does not stand against it.

## Tech hours

### Tech hours follow the shape
Each block's tech hours follow its shape's rule (per unit, per hardware point, per indoor unit, per panel, per fan,
fixed, or per line). A hardware point is a Furnish, Furnish and Install, Furnish and Wire or Install and Wire line
naming a physical input or output; a software point (an alarm at the BMS, a setpoint, a schedule, a trend) is not.
Where a shape gives no hours, leave the hours empty for the estimator.

### Tech hours the shape cannot express
Some template rules have two parts: Gas Detection is 8 hours per gas panel plus 4 hours per fan it controls;
Kitchen Exhaust Ventilation is 40 hours per kitchen exhaust fan; a reheat VAV with a hot water valve is 4 hours, a
cooling-only VAV 3; Global Points are 4 hours, plus 4 for a weather station; a Packaged ERU / RTU / AHU is 16 hours
per unit; an exhaust fan with points is 4 hours per fan, with or without an AME controller of its own.

### Integration-only systems
A system with no Master Template hours that AME only integrates (a generator, heat tracing, water heaters, a VFD or
panel integration) is 4 hours per integration.

### Tech hours never print
Tech hours go to the price sheet only, never into a line or a note. The Master Template's tech-hour lines ("**tech
hour: ...") are guidance for the estimate, not lines of the proposal.

## Shapes and wording

### Template gives shape only
The Master Template (shapes.json) sets only the shape of a block: the header form, the order of lines and the
wording form of a line. It never says that a line exists. A slot is a place a line prints when, and only when, this
job's documents put a device there. The front end house lines are the one exception.

### Placing a device in a slot
Put each device in the slot of its block's shape that matches it. Several devices may share a slot: one line per
distinct damper type, valve or sensor. A device no slot fits goes in the matching "other" slot, in the standard
order: other_device (controllers, sensors, switches, detectors, relays, actuators), other_point (hardwired Furnish
signals), fire_alarm (fire alarm Wire lines), other_valve (Furnish and Wire valves and devices),
other_install_and_wire, other_wire, other_interlock, other_wiring. Integration lines go only in the integration
slots.

### Standard order
Lines print in their shape's slot order. Without a shape the order is: DDC controller; field sensors and
transmitters; safety and pressure switches; leak detectors; standalone current switches; interposing relays; damper
actuators; fan and pump signals (start/stop and status, VFD control, VFD fault in the documents' term, VFD speed
feedback, safety stop); primary equipment signals (boiler, chiller, cooling tower); position feedback and open/closed
status; other hardwired outputs; power wiring; fire alarm Wire lines; Furnish and Wire filter switches, airflow
stations, valves; Install and Wire; other Wire; wiring runs and plain work statements (demolition, coordination,
testing); the integration lines last; then the block's one clarification.

### Line form
Each line starts with its verb, or with an interlock, tie-in or wiring phrase when it has no verb. A line whose count
differs from the block's count starts with "Qty (N)" before that (see Line quantity). No bullets, no category or
verb-group headers, no dash after the verb. Details go after the device in brackets: the owner, "(as per sequence)",
"(Location: ...)". A combined sensor the documents name as one ("temperature and humidity sensor") is one line; named
separately, two lines. A filter switch is one line per filter stage in the documents' name. A line is at most 160
characters.

### Sub-lines under their parent
Some lines print one level in, directly under a parent line, as the Master Template prints them: gas detection
sensors and horn / strobes under the gas detection panel, the alarms under "Monitor the following Alarms", unit
ventilator devices tied in through the terminal strip under the tie-in line, a monitored item's details under the
item, a meter's communication wiring under the meter, and the rep-assist line under its Map Available Points line.
The shape names these slots ("under" in shapes.json). A sub-line has no verb: it is listed as a device of its own,
with its slot set, its citation and its quantity, right after its parent device, and it carries the parent line's
ownership (the same furnished, installed and wired by). A sub-line needs its parent line in the same block.

### Untemplated systems
A system with no shape is still written, from its evidence, in the house form "<quantity><verb> <device><owner>" (the
quantity first, see Line quantity), in the standard order, under a header "Qty (n) <name> <tags>". Every rule in this
book applies to it.

### One system one block
Each system the documents describe is its own block, from its own sequence section; systems are never collapsed
into one block, except as the VRF and split rule, the dampers rules and the valves rule say.

### Proposal header
"Quote #" is the job number and "Reference" is the project name, both from the name of the job folder, never the
takeoff folder. Never print a bracket placeholder such as "[project name]". When the job folder gives no project name,
print "***" in red and ask the estimator.

### Valves under their unit
A control valve and its actuator are written in the block of the unit they serve (an air handler, a fan coil), never
in a separate valve system. The plans, risers and sequence show which unit. When none can be traced, ask the
estimator.

### Pumps by plant or by service
When the plant (chillers, boilers or the like) is in the job's scope and the pumps serve it, the pumps are part of the
plant block. When the job shows remote pumps, each service is its own block: chilled water pumps in one, hot water
pumps in another. The documents decide. The block header makes clear which case it is.
