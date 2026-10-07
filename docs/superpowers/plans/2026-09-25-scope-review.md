# Scope Review Implementation Plan (Spec overview, part 2)

> **For agentic workers:** Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** The Spec overview becomes the place where the tool highlights potential scope AME needs to carry, and anything that shouldn't go unreviewed. This part adds six sections and one fix.

**The user's words:** "Basically this is where we highlight potential scope that AME needs to carry. What else can we add here that should not be left without review?" They approved all seven items below.

**Reference job:** 26-0445, in `D:\Estimation Assistant\Learn\26-0445` (read-only).
- Its proposal is `3. Proposal\1. Base Proposal\Sid revision comment26-0445 2.docx`, the estimator's own revision.
- Its spec is Division 25 (`25 05 00` to `25 35 00`) inside `2026.06.26 OWNERCO XX-1 DC-1 IFC PManual 00000.0000.pdf`.
- Its controls drawings are `Marked_10_CONTROLS_COMBINED.pdf`. IC00-00 holds a responsibility matrix.

The estimator carried scope the standard exclusions would have left out. Examples:
- 72 chiller flow meters, although "All water flow meters" is a standard exclusion
- power-quality meter wiring
- gateways for chillers and drives
- rope leak sensors and hydrogen detection
- fiber cabling

They also noted "Owner Provided Server", "OWNERCO BMS / EPMS Switch by Owner", "IDF Cabinet by Others" and "Procure Licenses … SCADA Software (25 15 50 - 2)".

**Architecture:**
- Extend `src/estimator/catalogue/overview.py` and `SpecOverview`.
- Add one new reading list, `assets/reading_lists/scope_review.json`.
- AME's standard exclusions and clarifications are **read from the proposal template at run time**, so they never drift from what the proposal prints. Use `assets/templates/AME_nordomatic Proposal Template.docx`, the paragraphs after `CLARIFICATIONS` / `EXCLUSIONS` in `estimator.proposal.layout`. Read them the way `estimator.proposal.read` reads that template.
- The JSON maps each template line to the words that show the job wants that item from the controls contractor.

**Spec:** `docs/superpowers/specs/2026-09-24-estimator-ai-design.md` §8 and §9.1. Recall is deterministic and nothing is guessed: every row quotes the job word for word, with its place.

## Global Constraints

- `D:\AME Estimation` and `D:\Estimation Assistant` are read-only.
- No job PDFs in the repo.
- Every piece of text the user sees is plain English, with no short codes. Where a job uses its own abbreviation (DSI, CSI, PSI, SSI, MSI), the quote shows it. Our own text says it in words, for example "the job splits controls between several contractors".
- Run text through `clean_text` before matching.
- Don't touch the bid check (`qualify.py`, `manufacturers.json`).
- Patterns and words live in JSON, never in code. Never special-case a job.
- Don't push. End commit messages with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

---

## The status of a row

Each row is one of three things:
- **Found:** a sentence names it.
- **Ruled out:** the only sentences that name it also forbid it. The forbidding words are: not allowed, not permitted, shall not, prohibited, not acceptable, is not required, are not required, not be used, no … shall be. Keep the list in the JSON as `ruled_out_words`.
- **Not found**

Apply this to the existing Protocols, Network and Electrical topics as well (item 7).
- On 26-0445, "BACnet IP is not allowed anywhere in the building" must make BACnet/IP read **Ruled out**.
- A "Found" cell is green. "Ruled out" is amber (FFEB9C). "Not found" has no fill.

## Where to search

Keep the existing strengths and add one more:

6. **"General requirements (Division 1)"**: a page inside a spec section whose number starts with `01`. Only the conditions section (section F below) searches these pages.

A responsibility or controls-contractor word in the sentence makes a mechanical, electrical or Division 1 hit count. Examples: `(?:BMS|BAS|ATC|DDC|controls?|temperature\s+control|automation|integration)\s+(?:contractor|subcontractor|vendor|provider|integrator)`, `Division\s+25`, `Section\s+23\s*09`, `\bDSI\b|\bCSI\b|\bPSI\b|\bSSI\b|\bMSI\b`. Keep this list in the JSON as `controls_party_words`. A hit on a controls spec page or a controls drawing counts without one, because there the controls contractor is the one being addressed.

## The new sections (in this order on the tab, before the existing Protocols section)

### A. "AME normally excludes this — the job asks for it" (item 1)

**What it checks:** each line of the template's Clarifications and its Exceptions and Exclusions.
- **Clarifications:** a row when the job says something about the same subject. Quote it, so the estimator can see whether the job agrees with the clarification.
- **Exclusions:** a row when the job asks the controls contractor to furnish, provide or install the excluded item.

**The JSON.** `scope_review.json` has `"exclusions": [{"line_starts": "All water flow meters", "patterns": [...]}]`, with one entry per template line.
- `line_starts` matches the start of the template paragraph, ignoring case and trailing spaces.
- A template line with no entry is skipped, but a test lists all the lines so none is forgotten. The test fails if a template line has no entry. An entry can say `"patterns": []` with `"why_not_searched": "…"` for lines that can't be searched for, such as "valid for 30 days".
- A sentence counts for an exclusion only when it also has a furnish or provide verb: `furnish|provide|install|supply|include|responsible\s+for|shall\s+be\s+by`.

**Rows:** AME's line (verbatim) | Status | Where | How strong | What the job says.

**For 26-0445, at least these must be found, each with a quote:**
- "All water flow meters", or "The installation of … water flow meters"
- "All electric power meters"
- "EMT or RGS conduit (if specified) …", for the blue-conduit rule
- "All equipment manufacturer integration/communication devices …", for gateways
- "Any gas detection system or components", which catches the hydrogen and refrigerant detection

### B. "Who does what" (item 2)

- **Every sentence that assigns work to someone other than the controls contractor**, as found rows. The words are: by others, by owner, owner[- ]furnished, furnished by the owner, OFCI/OFOI (quoted only), provided by (the owner, others, mechanical contractor, electrical contractor, Division 26, unit manufacturer, equipment manufacturer), by the EC/MC/GC, furnished by … installed by. One row per unique sentence, up to 60. After that, add one row: "…and N more; see the Pages tab".
- **A responsibility matrix:** a row when a page carries "responsibility matrix", "division of responsibility", "responsibility schedule" or "scope matrix", naming the sheet.
- **A split between several controls contractors:** one row when the job names two or more of: DSI, CSI, PSI, SSI, MSI, "system integrator" and "master systems integrator". The row's text reads "The job splits controls between several contractors — say which part AME is pricing", and it quotes the first sentence that defines them.

For 26-0445, these must be found:
- the owner-provided server
- a switch by the owner
- the IC00-00 matrix
- the split between several contractors

### C. "Other systems to connect to" (item 3)

A list of systems in the JSON (`"integrations"`), each with patterns:
- UPS
- static transfer switch
- automatic transfer switch
- switchgear / switchboard
- generator
- transformer
- power meter / power quality meter
- PDU / remote power panel
- lighting controls
- fire alarm
- access control
- elevators
- leak detection
- hydrogen detection
- refrigerant detection
- gas detection
- chillers
- boilers
- computer room units (CRAH/CRAC)
- humidifiers
- variable frequency drives
- heat trace
- domestic water meter
- lift station
- reverse osmosis
- sump pumps
- glycol system
- fuel oil system
- water treatment
- kitchen hood
- snow melt
- solar / PV
- BTU / energy meters

**When a system counts:** its sentence also has an integration word: integrat, interface, monitor, map, points?, Modbus, BACnet, gateway, "connect(ed)? to the BMS", hardwired, "EtherNet/IP". Keep these words in the JSON.

**Rows:** System | Status | Protocol named in the same sentence (Modbus TCP, Modbus RTU, BACnet/IP, BACnet MS/TP, EtherNet/IP, hardwired, or "not stated") | Where | How strong | What the job says.

For 26-0445, at least UPS, generator, switchgear, chillers and leak detection must be found.

### D. "Services that cost hours" (item 4)

Topics:
- training, with the hours captured when the sentence says `(\d+)\s*(?:hours?|hrs?)` or `(\d+)\s*(?:sessions?|days?)`
- commissioning
- functional performance testing
- point-to-point checkout
- trend logging
- warranty, capturing `(\d+|one|two|three|five)\s*(?:\(\d+\)\s*)?(?:years?|months?)`
- service or maintenance agreement
- as-built drawings
- operation and maintenance manuals
- shop drawings and submittals
- coordination drawings / BIM / Revit
- spare parts / attic stock / extra materials
- software licences
- graphics (3-D)
- seasonal testing
- owner demonstration

**Rows:** Service | Status | Amount stated (hours, sessions or years, when captured; else blank) | Where | How strong | What the job says.

For 26-0445: training, commissioning and software licences must be found.

### E. "Special systems" (item 6)

Topics:
- smoke control (UUKL, firefighter's smoke control panel, smoke control system)
- laboratory / room pressurization / room pressure monitor
- isolation rooms
- cybersecurity
- UL 508A panels
- redundant controllers / redundancy / ring network
- SCADA
- hazardous (classified) locations / explosion-proof
- NEMA 4X enclosures
- seismic

Same columns as the Protocols table.

For 26-0445: cybersecurity, UL 508A, SCADA and redundancy must be found.

### F. "Project conditions that change the price" (item 5)

These search Division 1 pages too, plus every spec and drawing page in scope. Topics:
- normal working hours / off-hours / night / weekend work
- phasing
- occupied building
- union labor
- prevailing wage / Davis-Bacon
- security badging / background checks / escorts
- bonds
- allowances
- alternates
- unit prices
- liquidated damages
- tax exemption
- minority / women-owned business participation (MBE/WBE)

Same columns as the Protocols table.

### Not found

Section 6 ("Searched for but not found") also lists each topic in D, E and F that wasn't found. A and C don't need this: "not asked" is the normal case.

---

### Task 1: Reading list, template lines and the status rule

- Create `assets/reading_lists/scope_review.json` with the lists above. **You draft the patterns.** Keep them tight, because a false "Found" costs the estimator a look and a false "Not found" can cost AME money. Prefer an extra quoted row to a missed one.
- Read the template's Clarifications and Exclusions lines.
- Add the Found / Ruled out / Not found status to `Found`. Keep `places` and `quote`, and add `status: str` and `amount: str = ""`. Check the existing tests and update any that assume found means places isn't empty.
- **Tests (synthetic sentences):**
  - Each section has at least one found case and one near-miss case, for example "flow meters by others" is not an exclusion hit, because the verb says someone else provides it.
  - "BACnet IP is not allowed anywhere in the building." reads Ruled out.
  - Every template line has an entry.
- Commit: `feat: the Spec overview checks the job against AME's standard exclusions, and marks what the job rules out`

### Task 2: Who does what, other systems, services, special systems, conditions

- Add the B–F sections to `build_overview`, and write them on the tab in the order A, B, C, D, E, F, then the existing Protocols, Network, Electrical, Manufacturers and Not found sections.
- Renumber the headings 1 to 12, with the controls platform staying 1.
- **Tests:** synthetic sentences for each section, including the 26-0445 shapes quoted above; the tab layout; and the summary line. Add a second line to `summary_lines`: "Scope review: N standard exclusions the job asks for; M other systems to connect to; K who-does-what lines."
- Commit: `feat: the Spec overview shows who does what, other systems to connect, services, special systems and project conditions`

### Task 3: The Learn jobs

- Run `tools/learn_check.py` (exit 0, bid-check table unchanged). Add the columns "Exclusions asked for", "Systems to connect" and "Who-does-what lines" to its Spec overview table.
- Read the new sections of all ten tabs. Cut false hits in the JSON, with a test for each.
- **Check against the estimator's own proposals.** For each Learn job, open its proposal in `3. Proposal\1. Base Proposal\*.docx`. Prefer the estimator's revision file if there is one; skip `proposal template.docx` and `~$` files. Compare:
  - **the standard exclusion lines the estimator removed or changed**, and the scope lines they added (fiber, gateways, meters, leak detection and so on), against
  - **what section A and section C found.**
  In the report, list for each job what the tool caught, and what the estimator carried that the tool didn't flag. Where a miss could be caught by a tighter or wider pattern, fix it in the JSON with a test.
- Add `"scope_review_includes": [...]` expectations for 26-0445, using the must-find items above, and make `learn_check.misses` report a missing one, with a test.
- Commit: `feat: the Learn check shows each job's scope review; checked against the estimator's own proposals`
- **Report** to `.superpowers/sdd/2026-09-25-scope-review/report.md`. If your tools refuse to write it, return the full report in your final message instead. Include:
  - commits and test totals
  - the Learn table
  - the proposal comparison, job by job
  - false hits cut
  - what's still missed and why
