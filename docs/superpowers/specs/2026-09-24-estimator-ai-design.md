# Estimator AI — Design

**Date:** 2026-09-24
**Status:** Agreed in conversation; waiting for your sign-off
**Supersedes:** `D:\Estimation Assistant` (read-only reference from here on)
**Reference corpus:** `D:\AME Estimation` (read-only)

---

## Read this first — in plain words

**What the tool does.** You give it a job's mechanical drawings and specs. It gives you back
three files: the proposal, the price sheet, and a third file that shows where every number
came from and lists everything it wasn't sure about. You go through that list, make the
calls, and the proposal is ready to send.

**How it works.** It follows your method, in the order you work:

1. **Check the job can be bid.** It reads the spec for the controls manufacturer. Honeywell
   WEBs or Johnson Controls FX — it carries on. Anything else — it flags it for the US team
   and keeps going, but the proposal can't go out until they've decided.
2. **Read the whole job, sheet by sheet.** Schedules, plans, details, air riser, water
   riser, network riser and specs — each read for the things you look for on that kind of
   sheet. It locates every unit, and counts sensors, actuators and keynotes wherever the
   drawings show them.
3. **Write the scope one system at a time.** For each system it gathers everything about it
   into one place, reads the sequence of operation, checks it against the point list, and
   adds anything the drawings show that both of those missed.
4. **Fill in your templates.** Your own proposal template and your own price workup — so
   the output looks like yours because it is built on yours.

**Why you can trust it.** Every number in the proposal has to point back to a sheet, a spec
paragraph or a stated assumption, or the tool won't produce the document. When two
documents disagree, it doesn't quietly pick one — it shows you both and asks. When it
doesn't know, it says so, instead of writing "as required".

**How we'll know it's working.** There are 268 past jobs where we have both the drawings and
the proposal you actually sent. The tool will be run on those and its output compared line
by line with yours. That comparison is the scoreboard. Every improvement has to show up on
it, and nothing is allowed to make it worse.

**The order it gets built in** — five steps, each usable on its own:

1. **Make the documents come out right.** Before the tool reads a single drawing, prove it
   can produce a proposal and a price sheet exactly like yours. Tested on job 26-0246.
2. **Build the scoreboard** that compares the tool's output with your real proposals.
3. **Check the job can be bid, and catalogue every page.**
4. **Read the job the way you do**, sheet type by sheet type.
5. **Write each system**, and produce the list of doubtful items for you to decide.

The parts that can simply be checked come first. The parts that need judgement come last —
when the scoreboard already exists to tell us whether they are right.

**Still needed from you:**

- The tech-hours sheet you are putting together.
- Later, when the tool reaches writing scope: a check that the standard minimum list of
  sensors for each type of equipment — used only when nothing on the job says otherwise —
  matches how AME actually bids.

*Everything after this section is the detailed design, written for whoever builds the tool.*

---

## 1. What this is

A tool that reads an HVAC/BMS controls bid package — mechanical plans and specs at
minimum, plus addenda, RFIs and exhibits when present — and produces two deliverables
an AME estimator can issue after a short, structured review:

1. **Proposal** (`.docx`) — the client-facing scope of work
2. **Price Sheet** (`.xlsx`) — the same scope, priced

Plus a third artifact that is not optional, and is the reason the first two can be
trusted:

3. **Evidence Package** (`.xlsx`) — every quantity's provenance, every flag, every
   discrepancy, every assumption, every revision change

Before any of that, it checks whether the job can be bid at all.

It counts **equipment** and it counts **devices** — sensors, thermostats, damper
actuators, valves, controllers. Devices are not a secondary concern to be handed
elsewhere: without them there is no scope, and they are the part the schedules do not
give you.

### Core value

**A scope you can defend, line by line.** If a number in the proposal cannot be traced
to a sheet, a spec paragraph, or a named assumption, the tool has failed — regardless of
whether the number happens to be right.

### Success criterion

The estimator's job changes from *writing the scope* to *resolving a short list of
flagged decisions*. The measure is the length of that list and the rate at which its
defaults are accepted, tracked against the reference corpus (§7).

---

## 2. Why the previous build is being replaced

Measured, not assumed. On job **26-0352**, the previous tool's `Proposal_DRAFT.docx` was
compared against the proposal actually issued.

**It got the equipment counts right.** 12 VAV, 28 FTR, 2 FSD, 1 EF, 2 EWH — identical to
the human.

**It was still unsendable:**

| Issued | Tool emitted |
|---|---|
| Header table; `MEP Engineer: GOLDMAN COPELAND` | flat paragraphs; `MEP Engineer: —` |
| `M-001.00 thru M-605.00 Dated: 06/08/2026` | `Based on Plans and Specs: See takeoff package` |
| `Heading 1` / `PR1` / `PR2` / `PR3` outline | every paragraph `[Normal]` |
| `EWH-1, 2` · `VAV-21-01 thru 12` | `EWH EWH` · `VAV-21-01..12` |
| ~30 exclusions | 17 — dropped wall sensor guards, EMT/RGS conduit, computers, AFMS, water-flow meters, electric power meters, gas meters, housekeeping pads, boiler control panel, gas detection, core drilling, roof penetrations, bonds, project allowances |
| ADD/DEDUCT ALTERNATES + signature block | absent |
| Space Temp ×10, Temp/CO2 ×2, Occupancy ×21 | "Space Temperature Sensor **as required**" |

Plus `🟡` and `🔴` internal flag markers printed into a client document, and a trailing
"generated by Estimation Assistant" note.

That last table row is the whole diagnosis in miniature. The equipment was right; the
**devices** were guessed, and when guessing failed the tool wrote *"as required"* — a
line nobody can price.

**No price sheet at all.** `Learn/_Phase3/decision_model_v2.md` §16: *"Pricing math out
of scope."*

**The per-job patching is in the repository.** `tools/` holds `_build_0393_takeoff.py`
(555 lines), `_build_0401_takeoff.py` (546), `_build_0410_takeoff.py` (396),
`_rewrite_0393_proposal.py` (289), `_rewrite_0410_proposal.py` (266),
`_rewrite_0401_proposal.py` (149) — roughly 2,200 lines of single-job scripts, in a repo
whose own `WORKFLOW.md` forbids them. The last two recorded runs exited with code 2.

### What carries over

The domain work is good and is being ported, not rewritten:

- `decision_model_v2.md` — the 43 scope rules, the equipment package taxonomy, verb rules
- `Brain/Quantity rules.txt` — Rules 1–9, and the flag taxonomy in Rule 3
- `Brain/ESTIMATOR_DOCTRINE.md` — source priority, "job evidence wins", "never invent"
- `Brain/AME Std Pricing Spreadsheet.xlsx` — the price book (§6)
- `app/accuracy/*` — sequence, plan-device, manufacturer and controls-spec harvesters

### The actual diagnosis

The rules are not wrong. **Nothing enforces them.** They are prose in markdown that a
model may or may not follow, and the code path that renders documents never consults
them. No rule said "emoji are internal" because nobody thought one was needed — and
nothing would have enforced it.

And the previous build did not follow an estimator's method; it followed its own. The
work is turning an expert's method and the existing doctrine into data structures and
tests.

---

## 3. The method

This section is the spine of the tool. It is the working method of an AME estimator
with more than eight years and roughly 4,000 mechanical drawing sets reviewed, and the
tool follows it step for step.

That is deliberate. When the tool raises a flag, it should read the way the estimator
already thinks — *"found on water riser M-601, not in the sequence"* — rather than in the
tool's own terms. A review list written in the reviewer's own words is one that gets
cleared.

### Stage 1 — Qualify

Read the spec and decide whether the job can be bid. AME bids two Niagara N4 product
lines: **Honeywell WEBs** and **Johnson Controls FX**. If the spec names any other
manufacturer, it is highlighted to the US team, and **the final call is theirs**.

### Stage 2 — Understand the job

Read every sheet, sorted by type, until the job is known inside out:

- **Schedules** — what equipment is in the job. The notes below each schedule, checked
  for who provides the unit controller. Those notes are mostly written for the equipment
  manufacturer, with some exceptions — so they are not scope by default.
- **Plans** — every scheduled unit located, each in its own colour. Sensors, important
  keynotes and damper actuators marked. Anything else that adds value to controls scope
  highlighted.
- **Equipment details** — control valves, expansion tank flow and pressure sensors,
  damper actuators, fire/smoke damper integration, and anything else touching a
  scheduled unit. If it affects controls, it goes into scope.
- **Air riser** — how air moves through the building and into the spaces. Damper
  actuators. Stair-pressurisation pressure sensors and other sensors. **Equipment shown
  here that is not on the plans or the schedule — highlighted.**
- **Water riser** — how water moves in, through and out of the building. Above all,
  **the loop**: how the chillers, pumps and heat exchangers work together. Pipe sizes,
  control valve sizes, differential pressure sensors.
- **Network riser** — the backbone: fibre or Ethernet, and who provides it. Whether AME
  furnishes network switches, workstations, laptops or servers. How each piece of
  equipment is served. VFD integration. Miscellaneous integration callouts for plumbing
  and electrical systems.

### Stage 3 — Write each system

Only once the job is understood, scope is written — one system at a time. For a chilled
water system with pumps and heat exchangers:

1. Find where its equipment sits on the plans.
2. Read its part of the water riser.
3. Read every keynote that touches it.
4. Read its equipment details.
5. Gather all of it into one place.
6. **Read the sequence of operation** — the most important document. It gives the scope
   line by line: who furnishes and installs each temperature sensor, pressure sensor and
   valve; the chiller controls; the pump controls; every integration.
7. If there is a point list, cross-check the sequence against it.
8. Add anything on the equipment details or floor plans that is in neither the sequence
   nor the point list.

*"That is how one system gets designed."* Then the next system.

### What the method implies for the tool

- **Two passes, in order.** The tool reads by sheet type first, then writes by system.
  The ordering is the method's.
- **The sequence is the backbone, not one source among several.** It decides which
  scope lines exist. The point list checks it. The drawings complete it.
- **"Which lines" and "how many" are separate questions.** The sequence says a zone has a
  space sensor; the plan says how many zones there are.
- **The reading lists are data.** Each sheet type has a checklist of things to look for
  (§9.2). They are the estimator's experience made explicit, and they are extended every
  time the scoreboard finds something the tool missed — which is how experience gets
  captured in a form that improves instead of one that depends on who is at the desk.
- **Step 8 is where a tool can beat a tired person** rather than merely match one: it
  checks every detail, every riser and every plan against the sequence, for every
  system, every time.

---

## 4. Naming

The existing shorthand — `R36`, `FE`, `Package D`, `GEMS`, `G0`, `Primary 3`, `Stage0` —
is unmemorable, and unmemorable names are why doctrine gets ignored. Every identifier in
this build is a phrase you can say out loud.

**`GEM` is not a domain term.** `BMS_DDC_GEM_v3.2.docx` is titled *"Senior Estimator
System Prompt — Complete Instructions"*: it is a Gemini *Gem*, a tooling artifact whose
name leaked into the vocabulary. It becomes the **Estimator Playbook** — the authority
on verbs, ownership and phrasing.

| Was | Becomes |
|---|---|
| `R01`–`R43` | kebab-case slugs that *are* the name, e.g. `terminal-unit-ddc-ships-to-factory` (was R36), `valves-are-furnished-and-wired` (was R06), `sequence-beats-boilerplate-exclusion` (was R23) |
| Package A | **factory-integrated** — manufacturer's controls, we wire and map |
| Package B | **factory-plus-field** — as above, plus field dampers and sensors |
| Package C | **field-ddc-air-side** — our DDC, our sensors, start/stop, speed |
| Package D | **terminal-unit-factory-ddc** — controller shipped to the box factory |
| Package E | **unitary-heat-pump** |
| Package F | **hydronic-plant** |
| Package G | **existing-system-tie-in** |
| Package H | **data-centre-integration** |
| `FE`, `fe_mode` | **front end**, `front_end_mode`: `new-system` \| `extend-existing` |
| `GEMS` | **Estimator Playbook** |
| `G0`, `G_VISION` | named gates: `every-page-read`, `every-quantity-sourced`, `no-pending-in-client-doc` |
| `Stage0` | **intake** |
| `Primary 3` | name the three files |
| `C1–C6`, `QC-01–10` | folded into named checks |

Terms that appear in the client document stay exactly as they are — *Front End Web
Enabled BMS System*, *Scope of Work*, *ADD ALTERNATE*, *Qty*. Those are house vocabulary,
not jargon.

Every ported rule also carries a one-line plain-English statement. A rule you cannot
restate in a sentence is a rule nobody will apply.

---

## 5. Architecture

```
  mechanical plans + specs   (+ addenda, RFIs, exhibits when present)
         |
    1. QUALIFY
         spec -> BMS manufacturer requirement
         Honeywell WEBs / Johnson Controls FX  -> qualifies
         anything else                          -> US team decides
         |
    2. UNDERSTAND THE JOB                (every sheet, by type)
         register every page; classify every sheet
         schedules      -> equipment; who provides the unit controller
         plans          -> units located; sensors, keynotes, actuators marked
         details        -> valves, expansion tank sensors, actuators, FSD
         air riser      -> air path, actuators, sensors, unscheduled equipment
         water riser    -> the loop, valve sizes, differential pressure
         network riser  -> backbone, who furnishes IT, VFD + misc integration
         control diagrams, specs -> sequence, point list, front end
         supersession ladder; revision diff
         |
    3. WRITE EACH SYSTEM                 (one system at a time)
         gather the bundle across every sheet type
         sequence of operation  = which scope lines exist
         point list             = cross-check
         drawings               = add what both missed
         plan counts            = how many
         compare the answers -> the review list
         |
    4. FILL IN YOUR TEMPLATES
         scope lines --+--> Proposal .docx     (python-docx, AME template)
                       +--> Price Sheet .xlsx  (openpyxl, PriceWorkup template)
                       +--> Evidence Package   (flags, provenance, change log)
```

### The core type

```python
class Evidence:
    sheet: str                 # "M-002"
    sheet_type: SheetType      # SCHEDULE|PLAN|DETAIL|AIR_RISER|WATER_RISER|
                               # NETWORK_RISER|CONTROL_DIAGRAM|SPEC
    kind: EvidenceKind         # TEXT|TABLE_ROW|SYMBOL|KEYNOTE|SEQUENCE|POINT_LIST
    locator: str               # "Fan Coil Unit Schedule row 7" | "23 09 93 §3.4.B" | "Keynote 7"
    quote: str                 # the actual text found, or the symbol matched
    revision: str              # "base" | "Add.1" | "IFC"
    doc_date: date

class Derivation:
    method: RULE | PLAN_COUNT | MODEL | HUMAN   # PLAN_COUNT = symbols or keynotes
    rule: str | None           # "terminal-unit-ddc-ships-to-factory"
    note: str

class Quantity:
    value: int | None          # None = PENDING. Never a silent 1.
    category: Category         # CONFIRMED|DISCREPANCY|ADDED|EXTRA|MISSING|ORPHANED|
                               # CONFLICT|EXISTING|ASSUMPTION|PENDING
    confidence: float
    evidence: list[Evidence]   # non-empty, or the build fails
    derivations: list[Derivation]
    alternatives: list[Quantity]   # on disagreement the loser is kept, not discarded
```

`sheet_type` records *where* evidence was found; `kind` records *what form* it takes. A
keynote on an air riser is `AIR_RISER` + `KEYNOTE`.

### Six guarantees

Each is checked by an automatic test, not left to good intentions, and each closes a
failure seen in the old tool.

**One list, two documents.** The proposal and the price sheet are both produced from the
same list of scope lines. A line cannot appear in one and not the other. `Price Sheet 1`
already mirrors the scope row for row when an estimator fills it in by hand; the tool
makes that automatic.

**Every number has a source.** A quantity that cannot point to a sheet, a spec paragraph
or a stated assumption stops the tool. This is the old doctrine's "never invent", made
automatic.

**No guessing.** The tool is allowed to say "I don't know" — and a line it doesn't know
cannot go into the client document. This is what makes *"as required"* impossible: the
tool can say *pending*, so it never has to bluff.

**The template owns the boilerplate.** Exclusions, clarifications, the header table, the
ADD/DEDUCT sections and the signature block live in your Word template, exactly as you
wrote them. The tool fills in only what changes from job to job. The 13 exclusions went
missing because the old tool rebuilt that list itself; if the template owns it, nothing
can drop it.

**Nothing internal reaches the client.** Confidence scores, rule names and flag markers
live only in the review files. The client template has no place to put them, so they
cannot leak — not filtered out, simply impossible.

**Only approved wording.** Every scope line's wording is taken from the approved phrasing
bank (§10.4). If an item has no approved wording, the tool flags it rather than making
some up.

---

## 6. Input assets

| Asset | Role | Shape |
|---|---|---|
| `AME_nordomatic Proposal Template.docx` | **Document shell** | 87 paragraphs, 1 header table, `Heading 1`/`PR1`/`PR2`/`PR3`/`List Paragraph`, full exclusions + clarifications + ADD/DEDUCT + Base Price + signature |
| `Brain/2024_Template.docx` | **Phrasing bank** | 810 paragraphs, zero tables, 691 approved `PR2` scope lines |
| `Brain/AME Std Pricing Spreadsheet.xlsx` | **Price book** | material price and device selection per scope item |
| *(pending)* | **Labour book** | tech hours per equipment block — to be supplied |
| `PriceWorkup_Template - 12-21-25.xlsx` | **Price sheet shell** | `Price Sheet 1` mirrors the scope; `Summary` rolls up to margin and sell price |

### The price sheet shell

Measured on the filled 26-0246 workup:

- **Tech hours attach to blocks; unit prices attach to lines.** Of 288 scope rows, 47
  carry tech hours — the `Qty (N)` equipment headers and the front-end section — and 91
  carry a unit price — the device lines beneath them. The labour book is therefore keyed
  by equipment block, not by device, and the tool writes hours and prices to
  different rows.
- **It is formula-dense: 4,199 formulas** — 408 on each of the ten price sheets and 119 on
  the `Summary`. The fill must load with `data_only=False` and write only input cells;
  anything else ships a workbook with dead totals.
- **Header fields are not trustworthy in the ground truth.** The master template itself
  carries a leftover *"MCCC LA"* as the Job Name and as the location of Price Sheet 1, and a
  stale date — so every workup made from it starts out saying "MCCC LA" unless an estimator
  overwrites it. The scoreboard identifies workups by folder, never by their header; the
  tool fills the header in from the job itself.
- **The Summary's total adds the alternates in.** Its Total row sums every price sheet, so
  a job whose alternates sit on their own sheets (as 26-0246's do) shows a total that
  includes them. The base price is the base sheet's own sell price, never that Total.
- **The two documents already drift apart by hand.** In the proposal sent for 26-0246 the
  alternate blocks are numbered 45 and 46; in its workup they are 44 and 45, because the
  workup was built from an earlier draft with one fewer block. The one-list, two-documents
  guarantee exists to make that impossible.

### The document shell

Issued `26-0352.docx` is 875,713 bytes; the shell is 875,213. The estimator copies the
shell and types scope into it — which is what the template-owns-the-boilerplate
guarantee makes automatic.
`proposal template.docx` is a stale variant (2024 dates, 60-day validity, no tariff
clause). Not canonical.

**Filling the template.** The tool fills the team's template file directly — it finds
the headings it knows, writes the job's lines in between, and leaves everything else as the
team wrote it. There is no converted copy to keep in step: when the team updates their
template, refreshing the tool is copying the new file in. Two things in the template are
choices, not clutter, and the tool makes them:

- **Two front-end openings** separated by a literal `OR` line — new system vs. extension
  of an existing district-wide BMS. Selected from the spec and the network riser (§10.5),
  with a citation. Where both are silent it becomes a review question, never a default:
  the wrong front-end block is a five-figure error in either direction.
- **`IT Infrastructure – By AME or by Others?`** with `Network Switches / Panels / Fiber –
  Ethernet`. Answered from the network riser (§10.5); a review question when it is silent.

Genuinely removable: the duplicated exclusion (`"Any demolition work not mentioned."` and
`"Any demolition work not specifically mentioned"` are both present) and the stale
template date.

**The cover date is a live field.** The template's Date is a Word `DATE` field, so every
proposal made from it shows *today's* date whenever it is reopened or printed — an archived
proposal never shows the day it was issued. The tool writes the issue date as plain text.

**The template has no example of an equipment block.** It goes from the front-end block
straight to *ADD ALTERNATES*, so estimators paste block formatting in from older proposals.
That is why 26-0246 builds its scope lines from six different bullet lists in two fonts
(the house font, and Calibri pasted in from elsewhere). The template's own list 12 is the
right one for scope lines, and the tool always uses it.

### The price book

Two sheets, and it does more than price.

**`Parts Pricing`** — field devices with an estimation price and a design reference
(manufacturer, part number, AME cost). Air and water temperature sensors, space sensors
in four variants (temp / temp+humidity / temp+humidity+CO2 / temp+CO2), pressure sensors,
gas sensors, BACnet thermostats in two variants, switches, freezestats, leak sensors,
damper actuators in two sizes, enable/disable relays.

**`BMS-DDC-Panels`** — workstation, server, laptop, display, UPS, network switches,
network-level control panels bundled by device count, Niagara supervisors, VAV
controllers, terminal-unit controllers by point count, plant controllers by point count,
and enclosures by size.

Four things follow from its structure:

1. **It is also a device selection guide.** Rows carry notes such as *"Standard to use
   with All VAVs/FPB/Terminal Units"* and *"Suggesting not to use as standard
   selection"*. Those are selection rules and they feed §10.4.
2. **Its line names are close to scope line names.** *Space Temperature / CO2 Sensor*
   appears in both. The scope→price join is largely a name match, but must be
   **validated against the 61 filled workups** before it is trusted.
3. **Incomplete rows are flags, not zeros.** Several entries are marked *"Need review
   from Engg Team"* or *"Need Part # & pricing"*, and the plant-panel block is marked
   incomplete. A missing price surfaces as `PRICE-PENDING`, never as nothing.
4. **One book prices both product lines — confirmed.** The design-reference part numbers
   are Honeywell WEBs — `VAA-VA75MB24NMC`, `UN-RS0844MSB24NMC`, `N-ADV-112-H-C`,
   `WEB-S-100-N4` — but the estimation prices apply to Johnson Controls FX jobs too. The
   part numbers are a design reference, not a product-line lock.
5. **It is the generic price — confirmed.** A job can use a vendor quote for a line instead:
   26-0246's Space Temperature / CO2 Sensor was quoted at $380 against the book's generic
   $182. A quoted price applies to that job only and never changes the book. So every
   price has a source — a vendor quote for this job (named), the price book, or
   PRICE PENDING — and a difference between the book and a sent workup is not, by itself,
   an error in the book. Each job folder keeps its quotes in `7. Vendor-Sub Quotes`;
   reading them comes in a later build step.

---

## 7. The reference corpus

`D:\AME Estimation` — **read-only**, never written to, never built in.

| Measure | Count |
|---|---|
| Job folders (2025 + 2026) | 399 |
| With a human-issued proposal `.docx` | 286 |
| …of which also retain source PDFs | **268** |
| With a filled price workup | **61** |

Every job uses the same skeleton, which makes the corpus machine-readable:

```
<job>/
  1. Project Documents/{1. Base Documents, 2. A, 3. A, 2. IFC}/   inputs
  2. Takeoffs/
  3. Proposal/1. Base Proposal/<quote>.docx                        ground truth
  5. Price Workup/1. Base Documents/*.xlsx                         ground truth
  6. Electrical/  7. Vendor-Sub Quotes/  QC Checklist.docx
```

The revision folders encode supersession order in the filesystem, so it is read rather
than inferred.

**268 paired input→output examples** is the basis for the scoreboard (§12). The previous
build learned from 9.

**Roughly 10% of incoming packages are scanned image PDFs.** Vision is required, but not
on the critical path for nine jobs in ten.

**House style is `Qty (N)`.** 260 of 279 issued proposals use `Qty (4) Recessed Wall
Electric Cabinet Unit Heater CBH-A`; 9 use `(x12) VAV-21-01 thru 12`, all of them from
2026. The scoreboard treats the two notations as equivalent when scoring content.

---

## 8. Stage 1 — Qualify

Before any takeoff, find the BMS manufacturer requirement in the spec — typically
Division 23 09 xx, or 159xx in older specs (26-0246 uses 15970) — and classify it.

| The spec says | Finding |
|---|---|
| Honeywell WEBs, Johnson Controls FX, or Niagara N4 without naming a vendor | **Qualifies** |
| An approved-manufacturer list that includes either line | **Qualifies** |
| Another manufacturer as basis of design, *or approved equal* | **Open** — substitution may be possible |
| Another manufacturer, sole source | **Does not qualify** |
| Silent | **Open** |

The estimator's rule is simple — *any other manufacturer mentioned is highlighted to the
US team* — and the tool keeps it that way. The classification above does not replace
that rule; it tells the US team *how* the other manufacturer is named, which is what they
need to decide. The spec paragraph is quoted verbatim.

**The tool reports; it does not decide.** Final call is the US team's.

**Behaviour — confirmed: continue.** The full analysis runs regardless; the job's size and
shape inform the US team's decision. The qualification finding is the first page of the
Evidence Package, and any finding other than *qualifies* blocks issue until the US team
has decided.

Qualification ships first within its milestone (§14): it is small, and a job that does
not qualify is the most expensive one to take off.

---

## 9. Stage 2 — Understand the job

### 9.1 Recall is deterministic; judgement is not

Reasoning over a bundle of 10–30 pages about one system is reliable. Guaranteeing that
every relevant page was found across a 1,235-PDF package (26-0328) is not, and it fails
silently — nobody knows which page was missed.

So recall never depends on the model:

1. **Page register** — every page of every document, text layer plus vision where there
   is no text layer. A page that could not be read is a hard blocker.
2. **Sheet classification** — every sheet typed (§9.2).
3. **Tag occurrence index** — every occurrence of every equipment tag, located.
4. **Legend and keynote extraction** — the controls symbol legend (symbol → device type)
   and each sheet's keynote list (number → note text).

**Honest limit:** index recall is bounded by text extraction. If vision misses a tag on a
scanned sheet, the index misses it. The `every-page-read` gate stays hard.

### 9.2 Sheet classification and reading lists

Every sheet is typed, then read against the checklist for its type. The checklists are
the method of §3 made explicit. **They are data, not code**, versioned, and extended
whenever the scoreboard shows a miss.

| Sheet type | Read for |
|---|---|
| **Schedules** | equipment: tags, types, quantities. Notes below the schedule — mostly for the equipment manufacturer, so not scope by default; the exceptions stating who provides the unit controller are extracted |
| **Duct and pipe plans** | every scheduled unit located; sensors, keynotes and damper actuators marked; anything else adding controls scope highlighted; typical-floor designations |
| **Equipment details** | control valves; expansion tank flow and pressure sensors; damper actuators; fire/smoke damper integration; anything touching a scheduled unit |
| **Air riser** | air path through the building; damper actuators; stair-pressurisation and other sensors; **equipment not on the plans or the schedule** |
| **Water riser** | water path in, through and out; **the loop — chillers, pumps and heat exchangers and how they work together**; pipe and control valve sizes; differential pressure sensors |
| **Network riser** | backbone — fibre or Ethernet, and who provides it; who furnishes switches, workstations, laptops, servers; how each piece of equipment is served; VFD integration; miscellaneous plumbing and electrical integration callouts |
| **Control diagrams** | point-level detail per system |
| **Specs** | manufacturer requirement (§8); sequence of operation; point list; front-end requirements; warranty, training and service terms |

**How sheets are typed.** Title-block title and content, not the sheet number alone —
numbering conventions differ between engineering firms. A sheet can carry more than one
type (a plan sheet with a schedule on it). A sheet that cannot be typed is flagged.

### 9.3 Alias resolution

`AHU-1` / `AHU–1` (en dash) / `AHU 1` / `AHU#1` / `Air Handling Unit No. 1` are one
system. `AHU-1` must never match `AHU-10`. Whole-token matching against an alias table,
with the look-alikes that must *not* match as test cases.

### 9.4 Document authority ladder

| Tier | Documents | Behaviour |
|---|---|---|
| 1 | Mechanical drawings — plans, schedules, details, risers, control diagrams | Primary; establishes scope |
| 2 | Mechanical specs | Primary; establishes requirements and ownership |
| 3 | Addenda / bulletins | **Supersede** tiers 1–2 for the sheets they reissue, by date |
| 4 | RFIs, exhibits | **Additive** — novel scope is added and cited; restatement is ignored |

### 9.5 Supersession — latest date wins, scoped per sheet

**Rule: the latest-dated document wins.** Confirmed practice.

**Scope: per sheet, not per document.** An addendum that reissues M-201 and M-202 says
nothing about VAV-3 on M-301. Applied document-wide, "not mentioned = removed" would strip
most of a job's scope every time an addendum touches two sheets.

```
Addendum 1 (Jan 10) reissues M-201, M-202, spec 230900

  AHU-1 on M-201  -> reissued sheet governs.
                     CO2 absent from new M-201 = REMOVED   [Add.1, M-201 r2]
  VAV-3 on M-301  -> not reissued. Base stands. No change.
```

The reissued sheet list comes from the addendum's drawing list or transmittal,
cross-checked against title-block revision number and date. Spec sections supersede the
same way.

### 9.6 Revision diff

A reissued sheet is a **diff against its predecessor**, not a replacement. Estimator
practice is to compare old and new side by side, use revision clouds to find what
changed, and record *every* change — not only the one being looked for.

- **Text-layer diff** — tags added/removed, schedule rows changed, notes edited. Reliable,
  and it catches most controls-relevant change.
- **Revision clouds** — locate the change and make a clean citation. Vector clouds are
  findable geometrically; raster clouds on scanned sheets need vision; some engineers use
  triangles or deltas. A hint, never the sole authority — the text diff runs regardless.
- **Title block** — revision number and date; anchors ordering.

Whole sheet clouded → full re-review of that sheet, flagged as such.

**Deliverable:** the change log is a tab in the Evidence Package.

> Addendum 1 — 14 changes across M-201, M-202, 230900
> 3 affect controls scope · 9 informational · 2 need review
> each with sheet, what changed, old value, new value, action taken

**Will not be caught:** purely geometric change with no text signal — a duct rerouted, a
unit moved. A whole-sheet-clouded case always escalates to full review rather than
trusting the diff.

### 9.7 Equipment inventory

- Schedule is primary (`Quantity rules.txt` Rule 1)
- Plans locate and verify; risers and control diagrams cross-check (Rule 2)
- Every item lands in exactly one Rule 3 category; nothing is unclassified
- Rule 7 (duplicate tag), Rule 8 (typical/type-only schedule) and Rule 9 (paired systems)
  port verbatim, with their worked examples as test cases
- **Equipment on a riser but not on the plans or schedule is `EXTRA`** — highlighted, and
  not priced until confirmed (Rule 3)

**Typical-floor expansion.** A sheet marked *typical floors 3 thru 14* multiplies its
contents. The multiplier is **the count of actual floors in the building's floor list**,
not `last - first + 1` — a building that omits floor 13 breaks the arithmetic. It renders
as a cited line:

```
Typical plan M-301 -> floors 3-14. Floor list (A-001): 12 floors.
Multiplier = 12.  [CONFIRMED — A-001]
```

**Missing-tag inference.** An untagged unit adjacent to a tagged run can often be
identified from its neighbours. Permitted, never silent: category `ORPHANED` or
`DISCREPANCY`, with the inference stated.

### 9.8 Device marks — symbols and keynotes

Confirmed practice: devices are counted from the plans whenever they are drawn there, as
symbols or as keynotes. On design-bid-build the controls contractor designs the layout,
so the plans may show equipment but no devices. The tool detects which world a job is in
and says so:

> `No device symbols or device keynotes found on plan sheets (28 sheets searched,`
> `legend absent). Device quantities derived from sequence and point list — see flags.`

**Symbols.** Extract the controls legend, which gives symbol → device type.
Template-match each legend symbol across plan sheets at drawing scale, with the match
scored and the hit located. Every counted device carries a `SYMBOL` evidence record
naming the sheet and position, so a disputed count can be pointed at.

Symbol sets are not standardised between engineering firms, which is why the legend is
the entry point rather than a fixed symbol library. Scanned sheets degrade matching and
dense plans produce overlapping hits. Each is a flag, never a silent number.

**Keynotes.** Devices are often called out with a keynote rather than drawn — a number in
a hexagon or circle, placed at the location, pointing to the sheet's keynote list. Only 7
of 279 issued proposals cite a keynote explicitly, but that undercounts use: estimators
read a keynote and write the line without citing it. Where one is cited, it carries
something large:

| Job | Issued line |
|---|---|
| 26-0190 | Space Static Pressure Sensor – (Qty. 24 Total) – as per IC00-02 Keynote #14 |
| 26-0328 | Data Hall to Corridor Differential Pressure Sensor – Qty. 20 (Keynote 9) |
| 26-0267 | Qty (182) Existing FTR-# (Scope as per Demo Plan Key notes) |
| 25-0671 | Sump Box Leak Sensor; Wired by Others – as per key note #27 |
| 25-0749 | *All scope with Fire Alarm by Others. Key Note #23 on M-110.07 |
| 25-0726 | EF-5 – Scope as per Keynote #3 on M-404 |

A keynote carries more than a count: its text gives the device type, and often the
ownership, an exclusion, or a unit's entire scope. *Count* = placements of the callout
on the sheet. *Type* = the keynote's text.

Three traps, each flagged rather than guessed:

- **A bare number is everywhere.** A "7" appears in dimensions, grid lines, room numbers
  and sheet references. A placement counts only when the number sits inside a keynote
  shape — hexagon, circle or diamond, per the sheet's convention — and matches an entry
  in that sheet's keynote list. Without the enclosing-shape check, every "7" on the sheet
  becomes a sensor.
- **"TYP." multiplies.** A keynote placed once and marked *typical* applies to every
  similar location. The modifier is parsed and the multiplier made explicit, the same way
  typical-floor expansion is.
- **Numbering is per sheet.** Keynote 7 on M-101 and keynote 7 on M-102 are different
  notes. Every keynote reference is keyed by sheet, never by number alone.

---

## 10. Stage 3 — Write each system

### 10.1 The system bundle

For each system — a chilled water system with its pumps and heat exchangers, say — the
tool gathers, into one place:

- where its equipment sits on the plans
- its part of the riser
- every keynote that touches it
- its equipment details
- its sequence of operation
- its point list, if there is one

This is the step that most depends on recall and least on judgement, which is why it is a
query against the tag occurrence index (§9.1) rather than a search.

### 10.2 Which scope lines exist — the sequence is the backbone

The sequence of operation is the most important document for scope. It gives the items
line by line: what is controlled, who furnishes and installs each temperature sensor,
pressure sensor and valve, the chiller controls, the pump controls, every integration.

Three steps, in order:

1. **Sequence → scope lines.** The backbone.
2. **Point list → cross-check.** Every sequence item against the point list, and every
   point against the sequence. Disagreement is a flag (§11), with both documents quoted.
3. **Drawings → add what both missed.** Anything on the equipment details, plans or
   risers that neither the sequence nor the point list covers is **added to scope**, cited
   to the sheet it came from.

Step 3 must not be confused with Rule 3's `EXTRA`:

| Case | Category | Why |
|---|---|---|
| A whole unit on a riser, not in the schedule | `EXTRA` | whether the unit exists at all is in question — highlighted, not priced until confirmed |
| A scope item on the drawings, not in the sequence — a control valve on a detail | `ADDED` | the method completes a system's scope from its drawings — included, cited to its sheet |

### 10.3 How many — quantity per line

Which lines exist and how many of each are separate questions. The sequence says each
zone gets a space sensor; the plan says how many zones there are.

| Priority | Source | Confidence |
|---|---|---|
| 1 | **Counted on the plans** — symbols or keynotes (§9.8) | highest; a count, not a derivation |
| 2 | **Stated in the point list** | high |
| 3 | **Derived** — equipment count × per-unit rule, e.g. one controller per VAV box | medium |
| 4 | **Default** — standard package, or the ASHRAE Guideline 36 minimum | `ASSUMPTION`; always flagged |

#### The grouping question

Device count is not a function of unit count. From issued 26-0246:

| Block | Units | Thermostats |
|---|---|---|
| CBH-A | 4 | **1** |
| ECUH-## | 43 | **42** |
| Electric Baseboard | 8 | **5** |
| Electric Baseboard | 105 | **0** — interlocked with associated VAV |

Four heaters in one vestibule share one stat; 105 baseboards inside VAV zones need none.
This is why priority 1 is a count rather than a multiplication: **when the plan shows one
thermostat — as a symbol or a keynote — serving four heaters, the answer is one, and you
get it by counting rather than reasoning.**

Where nothing exists to count, it falls through the priorities and, at 4, becomes a review
question with an honest default:

```
ECUH-## — 43 units, M-101…M-104. No thermostat symbols or keynotes on these sheets.
Sequence and point list silent.  Default 1:1 -> 42  [ASSUMPTION].  Confirm grouping.
```

The failure to avoid is not getting 42 wrong; it is **silently emitting 43** when the
answer is 1. One is a ten-second decision, the other is a priced error nobody sees.

Over time the corpus supplies priors — *"cabinet heaters in a vestibule grouped to a
single stat in 38 of the last 40 jobs"* — and a prior with evidence beats an invented
rule. That is the mechanism by which the tool stops needing per-job patching.

### 10.4 Package, device, wording, price

| Question | Source |
|---|---|
| Which equipment package | job class + equipment type + evidence — the eight packages named in §4 |
| Which device is selected | price book selection notes — e.g. the space temperature sensor that is standard for all terminal units |
| What wording | the 691-line approved phrasing bank — only approved wording |
| What it costs | a vendor quote sourced for this job, if there is one; otherwise the price book's generic price — plus labour book hours |

`2024_Template.docx` yields the phrasing bank. Unmatched items raise *"no approved wording
for this scope item"* — which is also how the bank grows, deliberately, with review.

### 10.5 The network riser — front end, IT, and integrations

The network riser answers the two decision points left open in the proposal shell (§6):
which front-end block, and *IT Infrastructure – By AME or by Others?* — whether the
backbone is fibre or Ethernet, and who furnishes switches, workstations, laptops and
servers.

It is also where **VFD integration** and **miscellaneous plumbing and electrical
integrations** are called out — sometimes only there.

**Rule — confirmed: one source is enough.** If the network riser, or any other single
source, shows VFD integration, it is in scope even when the sequence is silent. This is
step 3 of §10.2 applied to the network riser: silence is not contradiction, so the line
is `ADDED` and cited to its source, not a `DISCREPANCY`. Only an explicit contrary
statement — *"VFD integration by others"* — raises a flag.

It deserves its own paragraph because VFD integration is a significant cost, which makes
the network riser the single most expensive sheet to skip.

---

## 11. Comparing answers, and the review list

Two kinds of disagreement feed one review list.

**Document against document** — your own cross-check. Sequence against point list;
schedule against plans against risers (Rule 2); keynotes against the sequence. Places
where the documents themselves disagree.

**Method against method** — the tool's own safety net. It works out every scope line
twice, two different ways: once by following written rules, and once by having the AI
read the documents the way a person would. Where the two answers differ, both go on the
review list with their sources. Where the plans give a count, that is a third answer to
compare against.

| What happened | Label | What the tool does |
|---|---|---|
| The documents and both methods agree | CONFIRMED | goes in the proposal |
| The documents or the methods disagree | DISCREPANCY | every answer and its source go on the review list; stays out of the proposal until you decide |
| On the drawings, but in neither the sequence nor the point list | ADDED | goes in the proposal, citing the sheet it came from |
| A whole unit that isn't in the schedule | EXTRA | highlighted; not priced until confirmed |
| Only the AI found it; the rules were silent | ASSUMPTION | goes in the proposal, with the assumption stated |
| Nothing establishes it | PENDING | cannot go in the proposal (no guessing) |
| No entry in the price book | PRICE PENDING | the line goes in; its price is flagged |
| The spec names another manufacturer | QUALIFICATION | goes to the US team; the proposal cannot be issued until they decide |

This is your Rule 2 taken one level further: cross-check every sheet that exists and
confirm nothing until they agree — applied not only between documents, but between the
two methods as well.

Confidence derives from **evidence agreement**, never from a model's self-assessment. A
model reporting `0.85` about its own output is not a number that belongs in a priced
document.

---

## 12. The scoreboard

Without this, every change is a guess and "don't patch it per job" cannot be measured.

The tool is run on past jobs where we have both the drawings and the proposal you actually
sent — up to all 268 of them — and its output is compared with yours, line by line.

| What is checked | How it is judged |
|---|---|
| Equipment blocks | Did it find every block you wrote, and invent none you didn't? A missing block is the worst failure there is |
| Block quantities | Does each `Qty (N)` header match yours? |
| Device lines | Did it find every sensor, actuator and valve line you wrote? This is where "Occupancy ×21" gets caught |
| Device quantities | Do the counts match? Scored separately for counts taken off the plans, counts from the point list, and counts worked out from the equipment — so each source is judged on its own |
| Lines you took from the drawings | Of your lines that cite a detail, a riser or a keynote, how many did the tool also find? This is the best available check on the "add what the drawings show" step |
| Sheet sorting | Does it sort sheets by type the same way a person does, on a sample checked by hand? |
| Wording | Is every line from the approved phrasing bank, and does it match what you wrote? |
| Price | Does each line's price match the filled workup, on the 61 jobs that have one? |
| Boilerplate | **Must be perfect, every time** — every exclusion and clarification present |
| Layout | **Must be perfect, every time** — right styles, the header table, and no internal markers |

**You are not always right either, and the scoreboard allows for that.** Every difference
is sorted into *better than what was sent*, *worse than what was sent*, or *no real
difference*, with a sample checked by a person. The bar for accepting a change is **no
change makes anything worse** — not simply "the score went up".

**Where misses go.** When the tool misses something because it didn't know to look for it,
the fix is to add that thing to the reading list for that type of sheet (§9.2) — never a
script written for one job. That is the rule that stops `tools/_build_0393_takeoff.py` from
being written again.

---

## 13. Stack

Versions verified on PyPI, 2026-09-24.

| Need | Choice | Version | Note |
|---|---|---|---|
| Domain model / validation | `pydantic` | 2.13.5 | MIT. Enforces §5 types at every boundary |
| PDF parse, text layer, render | `pymupdf` | 1.28.2 | **AGPL-3.0-or-commercial.** Internal use inside one legal entity is not conveying, so fine as an internal tool; distribution outside Nordomatic needs an Artifex licence |
| Symbol and keynote detection | `opencv-python-headless` | 4.x | Legend-driven template matching, and the enclosing-shape check that separates a keynote callout from a stray digit. `headless` avoids ~30 MB of unused Qt |
| Arrays | `numpy` | 2.x | — |
| Proposal render | `python-docx` | 1.2.0 | MIT. Fills the team's template in place (§6). `docxtpl` was considered and dropped: it would need a converted copy of the template kept in step with the team's, and the template has no equipment-block example for it to repeat anyway |
| Price sheet fill | `openpyxl` | 3.1.5 | MIT. **Load `data_only=False`** — `data_only=True` loses every formula on save, and the workup carries 4,199 of them (§6) |
| Equipment vocabulary | Brick Schema | `brickschema` 0.7.9 | BSD-3. Class backbone only |

### On Brick Schema

It supplies the **equipment class backbone** — the registry whose absence produced `EWH
EWH`, `FTR-PERIM`, `FSD-EXIST` and `VAV-21-01..12`. With it, an instance is
`{class: VAV, tags: [VAV-21-01 … VAV-21-12], display: "VAV-21-01 thru 12"}` and rendering
is a lookup rather than string concatenation.

It is **not** a scope vocabulary. Brick was built for live building metadata and has no
notion of *"Furnish BMS Communication Wiring to Factory Controls"* or *"24V Transformer by
Unit Mfr."* Those come from the phrasing bank and the price book. Do not force scope lines
into Brick points.

**Open:** depend on the package (rdflib + SHACL reasoning) or vendor the class hierarchy
as a static table. Leaning static — a naming registry does not need a reasoner.

**Alternative considered:** Project Haystack (`phable` 0.1.29, MIT). Tag-based rather than
class-based and arguably closer to integrator vocabulary, but its tooling targets live
Haystack servers. `hszinc` is dead (2023). Brick preferred.

**ASHRAE 223P** — the eventual successor merging Brick and Haystack thinking — is still a
public review draft, publication expected FY26, second review pending. Too immature to
build on.

**ASHRAE Guideline 36** is a standard, not a library. It supplies the minimum point list
per equipment class, which is what makes *"as required"* unnecessary: either something
establishes the point, or the Guideline 36 default applies and is flagged with a
citation.

**There is no HVAC controls estimating library.** The domain knowledge lives in the
method (§3), in `Brain/`, in the price book, in the 286 issued proposals, and in the
estimators. The stack's job is to give it somewhere solid to live.

---

## 14. Build order

Five build steps. Each one is usable on its own and ends in something that runs.

**Build step 1 — Make the documents come out right.** Before the tool reads a single
drawing, prove it can produce a proposal and a price sheet that look exactly like yours.
The tool fills in your Word template itself. The price workup is filled
with every formula left working. Material prices come from the price book. All of it is
tested on one real job, using the scope lines taken straight from the proposal you
actually sent for that job — so this step tests only the documents, not the reading.

*Why first:* it is the whole "presentable" half of what you asked for, it involves no
judgement, and from then on every later step's output can be checked by eye.

**Test job: 26-0246** — PS Q517, 1 Beach 39th St, Queens (SCA). It is written in the
house `Qty (N)` style, it has a filled price workup, and it has nearly every kind of block:
the expanded SCA front end, BACnet data cabinets, packaged AHUs with VFD and energy-wheel
integration, terminal units, split systems, a kitchen exhaust system, electric heat,
domestic hot water, a generator, metering, warranties quoted from the spec, and both ADD
and DEDUCT alternates. It sits in `Learn/` rather than among the 268 past jobs, so the job
this step is built on cannot also be one the scoreboard later marks.

26-0352 — the job the old tool was measured on — is one of the nine written in `(xN)`
style, so it cannot be the target for a tool that writes `Qty (N)`.

**Done when:**

- the proposal matches the one you issued for 26-0246 in layout, styles and boilerplate;
- the price sheet has exactly the proposal's lines, its formulas still calculate, and every
  line is either priced from the price book or flagged PRICE PENDING;
- where the price book's price differs from what was entered in 26-0246's own workup, the
  difference is **reported, not treated as a failure** — the book holds the generic price
  used on most jobs, and a job often uses a vendor quote sourced for it instead.

Tech hours come from the test job itself until the labour book arrives.

**Build step 2 — Build the scoreboard.** Run the tool against the 268 past jobs where we
have both the drawings and the proposal you actually sent, and score its output against
yours. It starts by scoring build step 1's output, so the scoring itself is proven before
anything depends on it.

*Why second:* it turns "don't patch it per job" from a hope into a number.

**Build step 3 — Check the job can be bid, and catalogue every page.** Every page read and
recorded; every sheet sorted by type; the spec sections indexed; the bid check; every
equipment tag located; and the different ways one tag gets written — `AHU-1`, `AHU 1`,
`AHU#1` — matched up. The bid check comes first within this step.

**Build step 4 — Read the job the way you do.** The reading list for each sheet type; the
equipment list; sensors, actuators and keynotes counted off the plans; latest-date-wins
for addenda; and comparing old and new versions of a sheet, with every change logged.

**Build step 5 — Write each system.** Gather everything about each system into one place;
the sequence of operation as the backbone; the cross-check against the point list; adding
whatever the drawings show that both missed; the quantities; choosing the equipment
package and devices; comparing the two methods' answers; and the review list.

*Why last:* it is the largest step and needs the most judgement, so it is the one that most
needs the scoreboard to exist before work on it starts.

The order is deliberate: **the parts that can simply be checked come first; the parts that
need judgement come last, when there is already a scoreboard to tell us whether they are
right.**

---

## 15. Out of scope for v1

- Electrical (`_ELEC`) proposals — modelled later; never modelled in the previous build
- Multi-building merge — one building, one proposal
- `.xlsm` macro workbooks — target the `.xlsx` price template unless the macros prove
  load-bearing
- Geometric-only drawing change with no text signal (§9.6) — escalates to human review

---

## 16. Open questions

### Needs you

1. **Labour book.** Tech hours per equipment block, still to be supplied. The price book
   covers material only. Blocks the hours column for real jobs — not build step 1, whose test job
   carries its own hours.
2. **Guideline 36 validation.** Minimum point lists need checking against AME practice
   before they become defaults — it is a design standard, not a bid standard. Needed by
   build step 5, not before.

3. **Vendor quotes.** When the tool starts reading them: does a quote always give a unit
   price per device, or sometimes one lump sum for a package? Needed by build step 5, not
   before.

### Answered

| Question | Answer | Where |
|---|---|---|
| VFD integration on the network riser | In scope if the riser or any one source shows it | §10.5 |
| Qualification behaviour | Continue the full analysis; the US team decides | §8 |
| Johnson Controls FX pricing | Same book as Honeywell WEBs | §6 |
| House style | `Qty (N)` — 260 of 279 issued proposals | §7 |
| Scanned-PDF share | Roughly 10% | §7 |
| Devices on plans | Counted when drawn, as symbols or keynotes | §9.8 |
| Book price vs. the price on a sent workup | The book is the generic price; a job can use a vendor quote instead | §6 |

### Measured or decided during the build

3. **Price book join.** Validated against the 61 filled workups, gaps listed.
4. **Plan-evidence coverage.** The share of jobs that draw devices on plans, measured by
   the scoreboard — it decides how much weight priority 1 of §10.3 carries.
5. **Brick dependency vs. vendored table** (§13).
6. **Job-class coverage.** The six classes in `decision_model_v2` came from 7 jobs;
   checked against the 268.
7. **The 113 folders without an issued proposal.** Some may be no-bid decisions, which
   would make them test cases for qualification. Unverified — some will simply be jobs
   still in progress.

---

## 17. Rules of engagement

- `D:\Estimation Assistant` and `D:\AME Estimation` are **read-only**. No writes, no
  builds, no test runs against either.
- Every quantity carries provenance, or the build fails.
- A miss is fixed by extending a reading list, never by a job-specific script.
- A hardening claim without a failing test does not count — recorded twice in the previous
  build's audit history.
- Nothing is pushed without a milestone.
