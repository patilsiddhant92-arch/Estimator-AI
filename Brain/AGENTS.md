# AGENTS.md — Reverse-Engineering Discipline for Estimation Assistant

**Workspace root:** `D:\Estimation Assistant_Grok`  
**Production handoff (any coding agent):** `AI_HANDOFF/` — **read first for production jobs**  
**Companion system prompt:** `GROK_INSTRUCTIONS.md` v4.0  
**Last updated:** 2026-07-10  
**Learning status:** Phases 1–4 COMPLETE; multi-job learning COMPLETE; doctrine v2.0  
**Packaged skill:** `Skills/hvac-controls-scope-builder/` (v2.0)  
**Decision model:** `Learn/_Phase3/decision_model_v2.md` (R01–R43)  
**Doctrine:** `Brain/ESTIMATOR_DOCTRINE.md` (Brain = guide, not bible)  
**Synthesis:** `Learn/_All_Jobs/CONNECTING_THE_DOTS.md`

## Production vs Learning

| Mode | Read |
|------|------|
| **Production jobs** (`Jobs/`) | `AI_HANDOFF/WORKFLOW.md` + `GROK_INSTRUCTIONS.md` |
| **Learning** (`Learn/`) | This file (below) |

**Production golden rule:** takeoff first (per building) → AME SOW → Primary 3. Never merge buildings. Never invent scope.

This file governs **Learning mode**: how to turn paired Takeoffs + Proposal samples into a validated decision model and, eventually, a packaged skill.

---

## 1. Role

You reverse-engineer how a senior BMS/DDC controls estimator turns construction documents into proposal language.

You do **not** invent scope. You prove every proposal clause against input evidence, then cluster those decisions into reusable rules.

Brain sources (must be studied in Phase 1 before pairing):

| File | Purpose |
|------|---------|
| `Brain/BMS_DDC_GEM_v3.2.docx` | Senior estimator logic (Quick Scan, ownership, SOW, C1–C6, QC) |
| `Brain/Quantity rules.txt` | Schedule-first quantity verification categories |
| `Brain/2024_Template.docx` | Client-facing proposal structure and phrasing |
| `GROK_INSTRUCTIONS.md` | Production pipeline v4.0 + CLI |
| `AI_HANDOFF/` | Full pack for other coding agents |

---

## 2. Repository Layout (Learning vs Production)

```
Estimation Assistant_Grok/
├── AI_HANDOFF/                   ← production agent handoff
├── GROK_INSTRUCTIONS.md
├── Brain/
│   ├── AGENTS.md                 ← this file
│   ├── BMS_DDC_GEM_v3.2.docx
│   ├── Quantity rules.txt
│   └── 2024_Template.docx
├── Learn/                        ← paired samples (Learning mode)
│   └── JobName/
│       ├── 2. Takeoffs/          ← logical Takeoffs (folder name may include "2. ")
│       │   └── 1. Base Takeoff/
│       ├── 3. Proposal/          ← ground-truth output
│       │   └── 1. Base Proposal/
│       └── 5. Price Workup/      ← optional pricing ground truth
├── Jobs/                         ← production only (Stage 0–2)
└── Skills/                       ← Phase 4 packaged skills
```

**Learn folder aliasing:** treat `2. Takeoffs` as Takeoffs and `3. Proposal` as Proposal. Prefer `1. Base Takeoff` / `1. Base Proposal` as the primary pair; later revision folders (`2. A`, `3. A`) are secondary.

**Never mix modes without stating it.** Learning uses `Learn/`. Production uses `Jobs/`.

---

## 3. Four-Phase Learning Process (Mandatory Order)

### Phase 1 — Study Brain

1. Read all Brain files + `GROK_INSTRUCTIONS.md`.
2. Run structured brainstorming: **≥3 competing hypotheses per major pattern**, each with a stress test, before converging.
3. Write study notes (default path: `Learn/_Phase1_Brain_Study.md`).
4. **Stop.** Do not open Learn job Takeoffs for pairing until Phase 1 is reviewed.

### Phase 2 — Pair Takeoffs with Proposals

For every proposal clause (or coherent clause group):

```
input_evidence: "exact quote or table cell from file X page Y"
decision: "what rule or judgment bridges input to output"
output_clause: "exact or near-exact proposal language"
```

Rules:

- Brainstorm competing interpretations for ambiguous clauses.
- Prefer marked/base takeoffs and base proposal versions.
- Log quantity conflicts using `Quantity rules.txt` categories.
- Do not silently average or invent quantities.

### Phase 3 — Build and Validate the Decision Model

1. Cluster evidence logs into candidate rules.
2. Cross-check rules against `Quantity rules.txt` and GEM ownership/flag logic.
3. Produce a **numbered execution plan** and **pause**.
4. Wait for explicit user approval: `Plan approved` or `PLAN APPROVED` or `PROCEED`.
5. Validate on at least one **held-out** Learn job (not used to build the rules).
6. Document failures; revise rules; re-validate.

### Phase 4 — Productize

Only after held-out validation succeeds:

- Package logic into a reusable local skill under `Skills/` (e.g. `hvac-controls-scope-builder`).
- Skill must respect Stage 0 → Stage 1 → Stage 2 order from `GROK_INSTRUCTIONS.md`.

**Never skip or reorder phases.**

---

## 4. Hard Rules (Non-Negotiable)

1. **Never feed raw multi-file Takeoffs into GEM SOW generation.** Stage 0 normalization first (production).
2. **Never invent quantities, ownership, or scope.** Flag instead.
3. **Schedule is primary** for equipment quantities (`Quantity rules.txt` Rule 1). Supporting sheets verify; they do not silently override.
4. **Every Phase 2 clause needs evidence.** No evidence → no rule.
5. **Flags are early and explicit:** 🔴 🟡 🟠 🟢 with source quotes.
6. **Phase 3 plans require user approval before execution.**
7. **C1–C6 and evidence-based QC belong before final SOW presentation** (production Stage 2).
8. **RESET** (any case): hard session reset per GEM / GROK_INSTRUCTIONS; do not carry prior job state.

---

## 5. Evidence Log Format (Canonical)

Use this exact field order in Trace logs:

```
---
job: 26-0334
clause_id: P-017
section: "DDC Controllers" | "Points" | "Wiring" | "Exclusions" | ...
input_evidence: "exact quote or table cell from file X page Y"
input_source: "Marked_Mech.pdf p.12 / Equipment Schedule row AHU-1"
decision: "..."
quantity_category: CONFIRMED | DISCREPANCY | EXTRA | MISSING | ORPHANED | CONFLICT | EXISTING | REMOVAL | REUSE | N/A
ownership_verb: Furnish | Furnish and Install | Furnish and Wire | Install and Wire | Wire | N/A | Unclear
flag: none | 🔴 | 🟡 | 🟠 | 🟢
output_clause: "..."
notes: "optional"
---
```

Store Phase 2 logs under:

`Learn/<JobName>/Trace_Logs/phase2_evidence.md`  
(create `Trace_Logs/` as needed)

---

## 6. Decision Patterns to Extract (Minimum Set)

When pairing, actively hunt for rules about:

1. Field-installed DDC vs Factory/OEM vs Mixed unit typing  
2. Controller furnish/install vs factory controls  
3. Ownership verbs on end devices and signals  
4. Blanket wiring clauses  
5. FA interface / smoke / UUKL language  
6. Existing BMS / EPMS / DCIM tie-in  
7. Fan/VFD minimum points (GEM v3.2: Start/Stop+Status + VFD Control unconditional; VFD Fault not unconditional)  
8. Quantity CONFIRMED vs DISCREPANCY/EXTRA/MISSING handling in proposal  
9. Exclusions, alternates, clarifications, allowances  
10. Opening paragraphs / tie-in scenarios matching `2024_Template.docx`  

---

## 7. User Commands (Learning-Relevant)

| Command | Action |
|---------|--------|
| `BRAINSTORM: [topic]` | ≥3 hypotheses + stress tests |
| `PLAN` | Numbered plan; pause for approval |
| `PLAN APPROVED` / `PROCEED` | Continue after plan gate |
| `RESET` | Hard session reset |
| Production commands (`RUN STAGE 0`, etc.) | See `GROK_INSTRUCTIONS.md` — Jobs/ only |

---

## 8. Success Criteria

Learning succeeds when:

- Phase 1 study is complete and reviewed.
- Phase 2 evidence logs cover the major proposal sections of ≥1 full job.
- Phase 3 rules reproduce held-out proposal language without silent invention.
- Phase 4 skill enforces Stage 0–2 and quantity/flag discipline.

Production success criteria remain in `GROK_INSTRUCTIONS.md` §8.

---

**END OF AGENTS.md**
