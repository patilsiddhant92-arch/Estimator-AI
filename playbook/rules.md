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
written; if the gap matters, ask the estimator a question.

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
contractor: valve bodies, piping, unit-mounted safeties not assigned to the controls contractor. Electrical
contractor: VFDs unless the controls contractor furnishes them, line-voltage wiring, conduit, disconnects. Unit
manufacturer: factory-mounted sensors, factory controls, isolation valves and internal safeties. Owner: anything
the specification calls owner-furnished. Sheet metal contractor: ductwork, and installing airflow measuring
stations.

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
the sheet metal contractor; "(Furnished by Mechanical Contractor)" for condensate pumps and float switches;
"(Furnished by Electrical Contractor)" and "(Furnished by Owner)" when those parties furnish. The bracket names
only the furnishing party; who installs is kept in the Evidence Package, not printed.

### Point lines only on AME controllers
"Furnish <point>" lines (start/stop and status, speed control, enable, setpoint, alarms, feedback) are written only
for a system AME's own DDC controller runs. On a packaged or factory-controlled unit the three integration lines
cover every monitored point.

### Minimum points on AME-run equipment
On equipment AME's own controller runs, write these points with the documents' citation that puts the equipment
under AME's control. Fans and pumps: Start/Stop and Status; VFD Control when the equipment has a VFD. Boilers:
Enable, Status, Alarm/Fault; Setpoint only when the sequence calls for a BMS reset. Chillers: Enable, Status,
Alarm/Fault. Cooling towers: Fan Enable, Fan Status and Fan VFD Control; the Fan VFD Fault, like any VFD fault, is
written only when the documents call it, in their exact term (Fault, Malfunction or Safety Stop). VFD speed
feedback, position feedback and open/closed status from end switches only when the documents call them. These
are never listed for equipment on factory controls unless the documents give them to AME.

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
where it is. The estimator decides on review.

### Never undershoot
Never print a count lower than one the documents give. Never invent a number. An unknown count prints "Qty (##)"
in a header and "(Qty. ##)" on a line, flagged to confirm.

### Line quantity
A line's quantity prints only when it differs from the block's count, as "(Qty. N Total)". Identical lines for
several units are one line with the total ("Furnish Chiller Enable (Qty. 6 Total)"), never one line per tag.

### Systems named only in the sequence
A system the sequence names but no drawing shows (an emergency generator, plumbing pumps, domestic water heaters,
heat tracing, glycol feed, a gas booster) is printed in the base bid with its integration lines, "Qty (##)", and
the clarification "*Quantity per plumbing drawings" (or the drawings of the trade that shows it). It is never held
back as a question only.

## Clarifications and assumptions

### One clarification per block
A block has at most one "*" clarification, naming the lines it covers: the quantities to confirm, the ownership to
confirm and the assumptions made. Do not put a bracket on every line; the per-line detail stays in the Evidence
Package. When a block needs several, they are joined in that one clarification. Its forms: "*Confirm quantity:
...", "*Confirm ownership: ...", "*Assumed: ...", "*Quantity per <trade> drawings", and "**<note>" for client notes.

### Joining into the one clarification
The block's one clarification has one kind. When only one kind of item is needed, it takes that kind's form. When
several are needed, the kind is "confirm" if anything is to be confirmed or counted per drawings, else "assumed",
else "note". The parts are joined with "; " in the order: to confirm, assumed, per drawings, client notes. After
the first part each keeps its own leading words ("Assumed: ...", "quantity per plumbing drawings", "Note: ...").
Example: "*Confirm quantity: 4 per schedule; Assumed: relay by AME, as the sequence asks for a stop; Note: Start/Stop
via Fire Alarm System". The front end block follows the same rule.

### Every assumption says why
Every assumption says what was assumed and why, in a few plain words naming the document or the missing
information: "*Assumed: duct static pressure sensor shipped loose by the unit manufacturer, as the schedule shows no
factory sensor". A bare "*Assumed: unit type" is never printed. An assumption is an item AME prices on judgment, so
it always carries its reason.

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
proposal. A question never replaces a line the documents call for; a missing count prints "Qty (##)" and asks.

## Packaged units

### Packaged units
A packaged unit comes with its factory controller, its end devices and its equipment wired inside at the factory.
The controller and every end device belong to the unit manufacturer unless the documents (sequence, schedule note,
plan note or detail) give one to the controls contractor. AME's work on it is limited to four things: the
shipped-loose devices; any device the documents explicitly give to the controls contractor, with the normal verb;
wiring to a factory-installed device only when the sequence gives that wiring to AME; and the three integration
lines, last.

### No AME controller on a packaged unit
Never write "Furnish and Install DDC Controller" for a unit on factory controls.

### Nothing inside the unit is a line
What the sequence describes inside the unit (valve control, fan control, DX staging, leak control, reheat, internal
sensors, actuators, safeties, filter switches, airflow stations, condensate devices, refrigerant leak detectors) is
wired at the factory and is not written. Do not write a line per monitored point or per internal device.

### Factory-installed devices
A device installed at the factory is never a line, blanket wiring clause or not. It becomes "Wire <device>
(Furnished by Unit Mfr.)" only when the sequence itself gives the wiring of that device to the controls contractor.

### Template is the ideal case
The Master Template shows how the system looks in the ideal case. When the sequence says something explicit, it
is taken into account. AME's task is the right ownership on each line, not restating the sequence.

## Shipped-loose devices

### Shipped-loose devices
A device the unit manufacturer furnishes and ships loose (space sensor or thermostat, supply air temperature
sensor, supply static pressure sensor and the like) is written "Install and Wire <device> (Furnished by Unit Mfr.)"
on its own line, wired to the unit's own controller. Write out every manufacturer-furnished device the job names
that AME installs or wires. "Wire <device> (Furnished by Unit Mfr.)" is only for a device the manufacturer already
mounts. When unsure whether it is mounted, write Install and Wire.

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
Each front end line (network level control panel, PC workstation, BMS server, portable operator terminal, UPS,
3-D graphics, training, IT infrastructure) is written only when this job's specification calls for it, with its
citation. Graphics on a tie-in are "to match existing".

### Front end items by others
When the documents give the workstation, server or network switches to the owner or others in the same sentence,
the line is not written and the front end's one clarification carries the client note ("**PC Workstation by
Owner", joined as in Joining into the one clarification). A sentence about the owner's network connection or the
room's location is not the owner furnishing the item.

### Auto dialer with a network panel
When AME furnishes a network level control panel, the BMS can send alarms by email and text, so an auto dialer
(Sensaphone or similar) the documents call for becomes the exception "EXCEPTION TO AUTO DIALER (BMS CAN SEND OUT
ALARMS VIA EMAIL AND SMS TEXT)".

### Warranty lines
Warranty scope is written only when the specification states the warranty and its length; an extended maintenance
contract only when it states the extra years.

## Exceptions and alternates

### Named exceptions
A unit the documents leave with no BMS work is a named exception in the estimator's form: "EXCEPTION TO ANY WORK
WITH Qty (n) <tags> - <reason>" (for example INTEGRAL THERMOSTAT, LINE-VOLTAGE THERMOSTAT, MANUFACTURER ON/OFF
SWITCH). One BMS word in its own sequence paragraphs or schedule notes (BMS, DDC, monitor, alarm, status, BACnet)
means it has BMS work and is priced instead.

### Never invent an alternate
A system is an add or deduct alternate only when the documents say so. Otherwise it is base bid.

### Exclusions
Work another party furnishes, installs and wires goes to the exclusions, one plain line each, only items relevant
to this job.

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
per unit.

### Integration-only systems
A system with no Master Template hours that AME only integrates (a generator, heat tracing, water heaters, a VFD or
panel integration) is 4 hours per integration.

### Tech hours never print
Tech hours go to the price sheet only, never into a line or a note.

## Shapes and wording

### Template gives shape only
The Master Template (shapes.json) sets only the shape of a block: the header form, the order of lines and the
wording form of a line. It never says that a line exists. A slot is a place a line prints when, and only when, this
job's documents put a device there.

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
Each line starts with its verb, or with an interlock, tie-in or wiring phrase when it has no verb. No bullets, no
category or verb-group headers, no dash after the verb. Details go after the device in brackets: the owner, the
quantity "(Qty. N Total)", "(as per sequence)", "(Location: ...)". A combined sensor the documents name as one
("temperature and humidity sensor") is one line; named separately, two lines. A filter switch is one line per filter
stage in the documents' name. A line is at most 160 characters.

### Untemplated systems
A system with no shape is still written, from its evidence, in the house form "<verb> <device><owner><quantity>",
in the standard order, under a header "Qty (n) <name> <tags>". Every rule in this book applies to it.

### One system one block
Each system the documents describe is its own block, from its own sequence section; systems are never collapsed
into one block, except as the VRF and split rule and the dampers rules say.
