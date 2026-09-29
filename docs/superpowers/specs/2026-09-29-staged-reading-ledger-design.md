# Reading in stages, with a job ledger that locks — Design

**Date:** 2026-09-29
**Status:** Agreed in conversation; waiting for sign-off on this written spec
**Builds on:** `2026-09-24-estimator-ai-design.md` §3 (the method) and §10 (writing each system)
**Replaces:** the single "plan the job" pass in `src/estimator/writing/whole_job.py`

---

## In plain words

Today the AI reads the whole job in one sitting: every document is gathered into one dossier,
the AI lists the systems in one pass, then writes each system. Nothing is ever settled while it
reads. When a fact is not in front of it at that moment, it fills the gap from what it already
knows: the templates, the GEM and old jobs. That is where the borrowing from old jobs comes from,
and why it struggles to understand a job as a whole.

An estimator reads in an order, and each stage settles a few facts that the later stages build on
but do not overturn. Schedules fix what equipment exists. Plans fix where it is and which devices
go with it. Details and risers fix how the plant fits together. The network riser fixes who
provides what. The sequence says what each system does. The spec fixes the front end.

This change makes the AI read the same way. It reads the job in seven passes, in that order, and
carries a **job ledger** between them: a list of facts, each with its source, the pass that
settled it, and its state. A settled fact never changes. A later pass that disagrees adds a
contradiction beside it, with its own source. Writing then works from the ledger, not from the
whole dossier, and every scope line has to attach to a unit the ledger holds.

When two documents disagree about a count, **the higher count is printed**, so the price never
undershoots. The block carries a "*" note naming both counts and where each came from, and the
review list repeats it.

---

## 1. The job ledger

One file per job, `out/<job>/ledger.json`, and a "Job ledger" tab in the Evidence Package.

### 1.1 A fact

```
Fact
  id            "F17"                     short id, cited by later passes and by scope lines
  kind          one of: family, unit, count, location, device, provider, link, group,
                sequence_match, front_end, note
  subject       the tag, family or system it is about ("VAV", "RTU-1", "chilled water plant")
  value         the fact itself: a number, a name, a tag list, a floor, "AME" / "unit mfr" / "owner"
  source_id     the dossier source id ("[S41]") or image id ("[I2]")
  quote         the words or numbers stating it, copied exactly
  pass          schedules | plans | details | risers | network | sequence | spec | seed
  state         settled | added | contradicted
  contradictions  list of (value, source_id, quote, pass) — empty unless state is contradicted
```

Rules:

- A fact with state `settled` never changes `value`. A pass that finds a different value appends
  a contradiction and sets state to `contradicted`; the original value and source stay.
- `added` marks a fact a later pass introduced that the earlier, authoritative pass did not
  hold: equipment seen on the plans but not scheduled, equipment on a riser but on neither, a
  system the sequence names that no drawing shows. `added` facts always print with a flag.
- `seed` is the pass for facts the code found before the AI read anything (§1.3).
- Every fact has a `source_id` and a `quote`. A fact the AI offers without either is refused
  and listed, as unquoted lines are refused today.

### 1.2 The understanding

Beside the facts, the ledger holds one plain-words paragraph per pass, `understanding[pass]`:
what the job is, as far as that pass can tell. Each pass reads the earlier paragraphs first.
They are printed in order at the top of the Evidence Package under "How the job was read".

### 1.3 Seeding from the readers

Before the first AI pass, code writes the ledger's seed from what the readers already extract:

| Reader | Seed facts |
|---|---|
| `reading/schedules.py` | one `family` per tag prefix, one `count` per schedule QUANTITY column, provider notes as `provider` |
| `catalogue/tags.py`, `reading/inventory.py` | `unit` per distinct tag, `location` per plan placement |
| `reading/devices.py` | `device` counts per sheet, with the sheet's units |
| `reading/sequences.py` | one `sequence_match` candidate per lettered or numbered heading, value = the heading text |
| `catalogue/overview.py` (Spec overview) | `provider` and `front_end` candidates from the controls spec |
| `writing/systems.py` groupings | `group` candidates from `assets/system_groups.json` |

Seed facts are `settled` when the reader is certain (a schedule row's own QUANTITY cell), else
`added` for the pass that owns them to confirm. The AI starts every pass from evidence, not a
blank page.

### 1.4 Printing a contradicted count

The printed quantity is the highest value among the fact and its contradictions. The block
header uses it. Under the system's lines the block prints one "*" note in the house form:

```
*Qty. per M-201 thru M-206 (14 shown); Mechanical Schedule lists 12 — confirm.
```

The review list carries the same row, ranked with the count discrepancies at the top.

---

## 2. The seven reading passes

Each pass is one AI question. Its request holds:

1. the understanding paragraphs from earlier passes;
2. the ledger so far (facts as a compact table, ids kept);
3. only this pass's documents from the dossier, with their source ids;
4. the pass's own instructions: what it may settle, what it may only add, and the answer shape.

Its answer holds: `facts` to add (each with kind, subject, value, source_id, quote),
`contradictions` (fact id, value, source_id, quote), `confirmations` (seed fact ids it agrees
with, so they become settled), and `understanding`. An answer that tries to change a settled
fact's value is read as a contradiction, and the answer's log says so.

| Pass | Documents | Settles | May only add |
|---|---|---|---|
| 1 Schedules | schedule sheets and their notes, schedule pictures | families, tags, counts, who provides the unit controller | — |
| 2 Plans | plan sheets: their text, keynotes, device counts, placements | per family: floors and zones, devices, keynotes that matter | equipment not on the schedule ("seen on plans, not scheduled") |
| 3 Details | detail and control-diagram sheets | per settled unit: valves, actuators, FSD integration, tank sensors | — |
| 4 Risers | air riser, water riser | links (which unit serves which), the plant loop, riser sensors, groups | equipment on neither schedule nor plans |
| 5 Network | network riser, network notes | providers: backbone, switches, server, workstation; integration callouts | — |
| 6 Sequence | sequence of operation, points list | sequence_match per section to a settled system | a system the sequence names that no drawing shows, only when the section states a count |
| 7 Spec | the controls spec, the Spec overview's findings | manufacturer, front-end mode, warranty, training, services | — |

**Splitting.** A pass whose documents exceed the request limit is split by sheet (plans) or by
section (sequence); the ledger is carried between splits and the split answers are merged by
fact id. **Skipping.** A pass with no documents is skipped, and `understanding[pass]` says
"nothing to read: no <kind> sheets in this job".

**Chat mode.** Each pass is a request in the requests folder, answered in chat and cached,
exactly as the judge's questions are today. A job is seven pass requests plus one write request
per system.

---

## 3. Writing from the ledger

The plan pass (`Judge.plan_job`, `PLAN_PROMPT`) goes away. The systems are the ledger's:

- one system per `group` fact (a plant or multi-family group), else per family;
- each system's header, tags and quantity come from its facts; a contradicted count prints as
  §1.4;
- the order is the house order from `assets/system_groups.json`, as today.

`Judge.write_system` keeps the GEM. What changes is its evidence: the system's ledger entry
(its units, counts, locations, devices, links, providers, contradictions, each with its fact id
and quote) plus its sequence section and points-list rows. Not the whole dossier.

Two rules join the write prompt and the answer check:

1. **Every scope line attaches to a fact.** A line names the fact id(s) it rests on. A line
   whose fact ids the ledger does not hold is refused and listed.
2. **Every count in a line is a ledger count.** A quantity in a line must equal a `count` or
   `device` fact's value (or the printed higher value of a contradicted one). Otherwise refused.

Past-proposal blocks (`assemble.system_examples`) are shown only for a system with no Master
Template entry, only as wording examples, placed after the evidence and labelled "wording only:
the facts come from the ledger above".

**Assembly.** The checks in `assemble.py` read the ledger instead of recounting the dossier. A
written quantity that is not a ledger value is a defect that is listed and the line dropped, not a
discrepancy to reconcile. Everything else in assembly (GEM order, flags, exclusions, tech hours,
the review list ranking) is unchanged.

---

## 4. Where it lands in the code

**New** `src/estimator/ledger/`:

- `facts.py` — `Fact`, `Ledger` (facts, understanding, `settle`, `add`, `contradict`,
  `printed_count`), load and save.
- `seed.py` — the seed from the readers (§1.3).
- `passes.py` — the seven pass definitions: which dossier sections each takes, its prompt, its
  answer schema, and the check that turns an answer into ledger changes.
- `run.py` — the runner: seed, then each pass through the judge's cache and chat/API hand-off,
  splitting and skipping as §2.

**Changed:**

- `writing/whole_job.py` — `plan_job` and `PLAN_PROMPT` removed; `write_prompt` takes a ledger
  entry; the two new line checks.
- `writing/judge.py` — asks pass questions the way it asks the others (cache, chat, API).
- `writing/assemble.py` — systems and counts from the ledger; the "*" contradiction note.
- `evidence/workbook.py` — the "Job ledger" tab and "How the job was read".
- `__main__.py` — `estimate` runs the ledger passes before writing.

**Untouched:** the readers, the catalogue, the dossier and its source ids, the GEM and practice
files, the templates, the proposal and price sheet writers, the scoreboard.

---

## 5. Testing

Unit tests, on small hand-made ledgers and dossiers, no job data:

- a settled fact's value cannot be changed; an attempt becomes a contradiction with both sources;
- a pass may only add the kinds its row in §2 allows; anything else is refused and listed;
- the seed produces settled counts from a schedule QUANTITY column and added candidates
  otherwise;
- a contradicted count prints the higher value, its "*" note names both, and the review list
  has the row at the top;
- a scope line with a fact id the ledger lacks, or a count the ledger lacks, is refused;
- a pass with no documents is skipped and says so;
- a long plans pass is split by sheet and merged by fact id.

Then the usual quick gate: the Learn jobs in chat mode, reading the seven understanding
paragraphs against how the estimator would describe those jobs, and the scoreboard not going
backwards. No per-job tuning.

---

## 6. Out of scope

- Pricing changes. The price sheet reads the same scope as today.
- Changing the GEM's wording rules or the house style.
- Physical-flow reasoning beyond what the risers pass records as links and groups.
- The API hand-off. Chat mode first, as agreed; the passes go through the same hand-off as the
  existing questions when the API is switched on.
