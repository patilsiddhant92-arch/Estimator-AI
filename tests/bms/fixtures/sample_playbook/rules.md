# Sample Playbook (test fixture: a minimal, invented rule book in the real format)

## Evidence and citations

### Every line cites this job
A device line carries at least one citation from this job.

## Counts and quantities

### The schedule count prints
The schedule's count prints when a schedule gives one; every other count is a flag named in the note. With no
schedule the highest count prints, flagged.

## Clarifications and assumptions

### One clarification per block
A block has at most one "*" clarification.

### Every assumption says why
An assumption says what is assumed and why.

## Packaged units

### Packaged units
A packaged unit's points are not furnished by AME; AME integrates through the manufacturer's interface.

### VAV boxes are field DDC
A VAV box is field DDC: a factory-installed controller is the DDC controller AME furnishes to the factory.

### VAV boxes on the manufacturer's controls
A VAV box takes the integration lines only when its controls are the manufacturer's own and the BMS integrates them.

### VAV zone radiation interlock
Radiation tied to a VAV zone is written in its own block when it has tags of its own, else in the VAV block.

## Shipped-loose devices

### Shipped-loose devices
A device shipped loose with a unit is furnished by the unit's manufacturer and installed and wired by AME.

## Dampers under their fan

### Dampers under their fan
A damper linked to a fan is a line of that fan's block.

## Duct heaters

### Duct heaters in one place
Every duct heater line is in the duct heater block.

## VRF and split systems

### VRF and split as one block
A VRF or split group is one block with its indoor, condensing and branch-selector families.

## Ownership

### Three ownership questions
Each line answers who furnishes it, who installs it and who wires it.

### Who owns what by default
With no document saying otherwise, AME furnishes, installs and wires its own devices.

### Every line carries its ownership
A line furnished by another party prints that party in its bracket.

### Unclear ownership is flagged
When the documents do not say who furnishes a device, the line carries a confirm note.

## Blocks and lines

### One system one block
One system prints as one block.

### Placing a device in a slot
A device goes in the slot of its shape that names what it is.

### Sub-lines under their parent
A sub-line prints one level in, under its parent line.

### Nothing inside the unit is a line
A part the unit manufacturer builds into the unit is not a line of its own.

### Start/stop covers the relay and status switch
A start/stop line covers its relay and its status switch; they are not lines of their own.

### Systems named only in the sequence
A system only the sequence of operations names is written from that sequence.

## Integration

### Integration trio
A unit with factory controls gets the three integration lines.

### Integration lines last
The integration lines print last in their block.

### Integration lines cover monitoring
The integration lines cover the points monitored through the unit's interface.

## Counts and assumptions in client words

### Never change a count silently
A count is never raised or lowered without its flag.

### Assumption wording has no source ids
An assumption's words name the document by its title, never by its source id.

### Everything assigned is extracted
Nothing on the list of assigned systems is dropped; a block with no lines says why.

### Words the client never sees
Client text carries no internal flag words, prices, source ids or reasoning words.

### Line form
A printed line is one short line of at most 160 characters.

### Front end mode
The front end is a new system or a tie-in to an existing one; an existing system the documents do not name prints
"[existing BMS name]" and is flagged.
