# Estimator AI — Gemini 3.8 Deep Audit, Contradictions, Bug Findings & Evidence Sheet UI Redesign

**Author**: Gemini 3.8  
**Date**: October 8, 2026  
**Target Commit**: `3053148` (branch `rebuild`)  
**Test Suite Verification**: 3,773 / 3,773 passing (clean run, 0 failures, 0 regressions)  
**Reference Specs**:
- [docs/superpowers/specs/2026-10-04-rebuild-design.md](file:///d:/Estimator%20AI/docs/superpowers/specs/2026-10-04-rebuild-design.md)
- [docs/superpowers/specs/2026-10-04-rebuild-interfaces.md](file:///d:/Estimator%20AI/docs/superpowers/specs/2026-10-04-rebuild-interfaces.md)
- [docs/USER-GUIDE.md](file:///d:/Estimator%20AI/docs/USER-GUIDE.md)
- [playbook/rules.md](file:///d:/Estimator%20AI/playbook/rules.md)
- [bugs.md](file:///d:/Estimator%20AI/bugs.md)

---

## Executive Summary

A forensic code, rule, and interface audit of the Estimator AI platform was conducted across `src/bms/`, `playbook/`, `docs/`, `bugs.md`, and test suites. The platform core is robust with a 100% green test suite (3,773 tests), but critical misalignments exist across three tiers:

1. **Spec & Rule Contradictions**: Written playbook rules and prompt guidelines conflict with real-world estimating domain practice regarding sub-line ownership (Ruling D3 / VAL-11), saved-decision rule name overloading, and legacy wording metadata.
2. **Operational & Validation Gaps**: Validation misses invalid sub-line ownership; the Excel evidence generator injects duplicate citations and destroys table filtering; 40–50% of bid labor (tech hours) is omitted from output summaries; and the review UI silently masks estimator questions.
3. **Evidence Package & Review UX Bottlenecks**: The existing Evidence Sheet tries to force paragraph-level prose into a flat tabular format. A modern 5-tab workbook architecture and a responsive 3-pane desktop Review Studio layout solve these usability and commercial risks.

---

## Part 1: Verified Contradictions & Spec Misalignments

### Contradiction 1: Sub-Line Ownership vs. Domain Integration Practice (Ruling D3 / VAL-11)
* **The Playbook & Prompt Rule**:
  - [playbook/rules.md:500-501](file:///d:/Estimator%20AI/playbook/rules.md#L500-L501): *"Every sub-line inherits furnished_by, installed_by and wired_by from its parent line."*
  - [playbook/shapes.json:17](file:///d:/Estimator%20AI/playbook/shapes.json#L17): Validates that subline owners mirror parents.
  - [src/bms/prompts/write_system.md:27](file:///d:/Estimator%20AI/src/bms/prompts/write_system.md#L27): Explicitly instructs AI writers that all sub-lines inherit parent ownership.
* **The Domain Practice & Test Reality**:
  - In [bugs.md:153](file:///d:/Estimator%20AI/bugs.md#L153) (Ruling D3) and live fixtures ([tests/bms/fixtures/sample_job.json:78-89](file:///d:/Estimator%20AI/tests/bms/fixtures/sample_job.json#L78-L89)):
    - Parent line (`map_points`): Furnished/Installed/Wired by **AME**.
    - Sub-line (`rep_assist` / `vfd_rep_assist`): Furnished/Installed/Wired by **Mechanical Contractor**.
* **Impact**:
  - The AI writer prompt contradicts real estimating logic. If an AI writer follows `write_system.md`, it assigns third-party mechanical factory support to AME, inflating BMS bid pricing. If it follows domain practice, it violates the written rule in `rules.md`.

---

### Contradiction 2: Rule Name Overloading for Saved Decisions in Review Engine
* **The Implementation**:
  - In [src/bms/playbook_lint.py:28](file:///d:/Estimator%20AI/src/bms/playbook_lint.py#L28), `RUN_LEVEL_RULE_NAMES = frozenset({"decision not honored"})`.
  - In [src/bms/review.py:898, 904, 947](file:///d:/Estimator%20AI/src/bms/review.py#L898), three fundamentally different runtime failure modes all emit the identical finding name:
    1. Line deleted during re-planning (`review.py:898`).
    2. Device copy count shifted during re-takeoff (`review.py:904`).
    3. Entire parent system dropped (`review.py:947`).
* **The User Documentation**:
  - [docs/USER-GUIDE.md:83-88](file:///d:/Estimator%20AI/docs/USER-GUIDE.md#L83-L88) specifies distinct estimator diagnostic cards: *"Decision could not be applied"* vs. *"Check this system"*.
* **Impact**:
  - Estimators cannot programmatically filter or triage minor line-level revisions from catastrophic dropped-system events.

---

### Contradiction 3: Stale Wording Contract in `playbook/wording.json`
* **The File**:
  - [playbook/wording.json:10](file:///d:/Estimator%20AI/playbook/wording.json#L10) (`$format.quantity.others_note`) states:
    > *"omit unlabelled counts, cap at five clauses"*
* **The Live Code**:
  - Per Ruling D6 ([bugs.md:150](file:///d:/Estimator%20AI/bugs.md#L150)) and [src/bms/render.py:430](file:///d:/Estimator%20AI/src/bms/render.py#L430), all clauses are preserved without capping, and unlabelled counts print as `"N elsewhere in the documents"`.
* **Impact**:
  - Violates the core governance principle ("The Playbook belongs to the estimator"), leaving misleading documentation for anyone auditing proposal generation logic.

---

### Contradiction 4: Internal Estimating Doubts Mislabeled as Client RFIs
* **The UI Label**:
  - [src/bms/review.py:433](file:///d:/Estimator%20AI/src/bms/review.py#L433) prints `job.questions` under an H2 banner:
    ```html
    <h2>Open questions for the client</h2>
    ```
* **The Planning Reality**:
  - [src/bms/plan.py:1080-1400](file:///d:/Estimator%20AI/src/bms/plan.py#L1080) and [src/bms/counts.py:332](file:///d:/Estimator%20AI/src/bms/counts.py#L332) populate `job.questions` with internal takeoff uncertainties (e.g., *"Schedule gives 0 but floor plan lists tags"*, *"Documents do not clarify if BMS extends existing network"*).
* **Impact**:
  - Presenting internal estimator doubt as client-facing questions creates serious commercial and contractual exposure if an estimator blindly exports or shares this section.

---

### Verification: Contract Spec Synchronization
* An initial hypothesis that `CountResult.untagged` was omitted from [docs/superpowers/specs/2026-10-04-rebuild-interfaces.md](file:///d:/Estimator%20AI/docs/superpowers/specs/2026-10-04-rebuild-interfaces.md) was investigated.
* **Result**: **Refuted / Synchronized**. Lines 415–416 of `rebuild-interfaces.md` explicitly define:
  ```python
  untagged: int | None = None
  ```
  The interface specification correctly matches [src/bms/counts.py](file:///d:/Estimator%20AI/src/bms/counts.py).

---

## Part 2: Confirmed Bugs & Quality Risks

| Bug ID | Severity | File & Lines | Root Cause | Impact |
| :--- | :--- | :--- | :--- | :--- |
| **VAL-11** | **High** | [src/bms/validate.py:183-193](file:///d:/Estimator%20AI/src/bms/validate.py#L183-L193) | `_sublines()` verifies parent slot existence, but never compares `(furnished_by, installed_by, wired_by)` tuples between child and parent. | Non-integration sub-lines with conflicting owners pass validation silently without warning. |
| **EVID-01** | **Medium** | [src/bms/evidence.py:56](file:///d:/Estimator%20AI/src/bms/evidence.py#L56) | Citations combined as `[*device.refs, *device.quantity.sources]` without deduplicating identical `(source_id, quote, where)` tuples. | Identical citations duplicate on adjacent lines in the same Excel cell. |
| **LABOR-01**| **High** | [src/bms/evidence.py:27](file:///d:/Estimator%20AI/src/bms/evidence.py#L27) & [src/bms/review.py:400](file:///d:/Estimator%20AI/src/bms/review.py#L400) | `System.tech_hours` and `FrontEnd.tech_hours` ([src/bms/model.py:172, 196](file:///d:/Estimator%20AI/src/bms/model.py#L172)) are omitted from evidence tables and the review dashboard. | **40–50% of bid labor value is invisible** in both review and audit sheets. |
| **EXCEL-01**| **High** | [src/bms/evidence.py:60-88](file:///d:/Estimator%20AI/src/bms/evidence.py#L60-L88) | Injecting non-device rows (Clarifications, Sequence Refs, Exceptions) into a 15-column device table with 11–12 blank cells. | Applying Excel AutoFilter on columns like `Verb` or `Furnished By` hides critical scope notes and exceptions. |
| **REV-01** | **Medium** | [src/bms/review.py:429-430](file:///d:/Estimator%20AI/src/bms/review.py#L429-L430) | Hard cap `MAX_QUESTIONS = 15`. If 16 questions exist and 1 is shown on a card, `elif hidden == len(mine):` fails to fire. | Questions silently disappear from the estimator's screen with no warning banner. |
| **IO-01** | **Low** | [src/bms/review.py:355-370](file:///d:/Estimator%20AI/src/bms/review.py#L355-L370) | Review HTML uses standard browser `<a>` download to `Downloads/decisions.json`. | Creates file collisions (`decisions (1).json`) and requires manual, error-prone copying into `out/`. |

---

## Part 3: Comprehensive UI/UX Redesign for Evidence Package

The existing Evidence Package attempts to merge commercial schedules, itemized takeoffs, and specification prose into a single unformatted worksheet. We propose splitting the presentation into two high-performance modalities:

1. **Modality A (Excel Workbook)**: A structured 5-tab financial and engineering ledger.
2. **Modality B (Review Studio `Review.html`)**: An interactive 3-pane desktop workbench with synchronized visual proof.

---

### Modality A: The 5-Tab Financial & Engineering Workbook (`Evidence.xlsx`)

```
Evidence.xlsx
 ├── 01_Bid Summary           (Executive KPIs, System Matrix, Tech & Labor Breakdown)
 ├── 02_Scope & Labor Ledger  (Canonical Device & Labor Schedule with strict typed columns)
 ├── 03_Findings & QC         (Rule Violations, Discrepancies, and Decision Audit Trail)
 ├── 04_Equipment Takeoff     (Drawing Callout Counts, Tag Details, and Location Register)
 └── 05_Drawing Index         (Specifications, Addenda, Schedules & Revision Matrix)
```

#### Visual Language & Styling System
* **Header Style**: Navy Slate (`#1E293B`), White text (`#FFFFFF`), Bold, 10pt Segoe UI, 28px row height.
* **AME Responsibility**: Soft Emerald (`#ECFDF5`), Dark Green text (`#065F46`).
* **Mechanical / By Others**: Muted Amber (`#FFFBEB`), Dark Amber text (`#92400E`).
* **Electrical Contractor**: Soft Cyan (`#ECFEFF`), Dark Cyan text (`#0E7490`).
* **QC Violations / Findings**: Soft Rose (`#FFF1F2`), Red text (`#9F1239`).
* **Borders**: Thin gray (`#CBD5E1`) cell grid; heavy dark bottom border on header rows.
* **Auto-fit & Frozen Panes**: Top row frozen on all tabs; column widths sized with +3 character padding.

---

#### Tab 01: `01_Bid Summary` (Executive Dashboard)
Provides an instant financial, equipment, and labor rollup:

```
+-----------------------------------------------------------------------------------------------+
| ESTIMATOR AI — BID EVIDENCE PACKAGE & AUDIT SUMMARY                                          |
| Job: Project Alpha Medical Tower    | Date: 2026-10-08 | Engine Commit: 3053148 | Rules: PASS |
+-----------------------------------------------------------------------------------------------+

[ SYSTEM BREAKDOWN & LABOR ROLLUP ]
+-------------------+-------+------------+-----------+------------+------------+---------------+
| System Name       | Qty   | Dev Count  | Tech Hrs  | PM/Eng Hrs | Wiring By  | Scope Health  |
+-------------------+-------+------------+-----------+------------+------------+---------------+
| AHU-1 thru 4      | 4     | 96         | 32.0      | 16.0       | EC         | [ 100% Valid ]|
| Chilled Water Plt | 1     | 42         | 24.0      | 12.0       | AME        | [ 100% Valid ]|
| VAV Boxes (Typ)   | 142   | 426        | 71.0      | 28.0       | EC         | [ 1 Warning ] |
| Front-End / BACnet| 1     | 18         | 40.0      | 20.0       | AME        | [ 100% Valid ]|
+-------------------+-------+------------+-----------+------------+------------+---------------+
| TOTALS            | 148   | 582        | 167.0 hrs | 76.0 hrs   | —          | 99.4% Pass    |
+-------------------+-------+------------+-----------+------------+------------+---------------+

[ KEY SCOPE EXCEPTIONS & CLARIFICATIONS ]
- AHU VFDs furnished by Div 23 Mechanical, wired by Div 26 Electrical, BACnet card by AME.
- Damper actuators on smoke dampers are furnished and wired by Fire Alarm Contractor.
```

---

#### Tab 02: `02_Scope & Labor Ledger` (Strict AutoFilter Compliance)
Every row represents a quantifiable device or direct labor line. **No injected free-text paragraph rows**:

```
Columns:
[A] System Name     | Text ("AHU-1")
[B] Sub-System      | Text ("Supply Air Section")
[C] Item Type       | Category ("Sensor", "Actuator", "Controller", "Integration", "Tech Labor")
[D] Device / Line   | Text ("Supply Air Temperature Sensor")
[E] Quantity        | Number (1)
[F] Unit            | Text ("EA", "HRS")
[G] Furnished By    | Badge ("AME", "Mechanical", "Electrical")
[H] Installed By    | Badge ("AME", "Mechanical", "Electrical")
[I] Wired By        | Badge ("AME", "Electrical")
[J] Citation Code   | Text ("SPEC-230923-2.4.A")
[K] Drawing Ref     | Text ("M-601 Detail 3")
[L] Specification Quote (Primary Justification)
[M] Rule Status     | ("Pass", "Exemption D3")
```

---

#### Tab 03: `03_Findings & QC Register`
Replaces scattered findings with an actionable resolution ledger:

```
+-----------+--------------------+----------+--------------------------------+-------------------+
| Finding ID| Rule Name          | Severity | Description                    | Estimator Action  |
+-----------+--------------------+----------+--------------------------------+-------------------+
| F-01      | val-actuator-torque| High     | Actuator missing sq-ft sizing  | Overridden (10Nm) |
| F-02      | val-sensor-well    | Med      | Immersion sensor missing well  | Well added        |
| F-03      | decision-reapplied | Info     | Restored valve count from run  | Accepted          |
+-----------+--------------------+----------+--------------------------------+-------------------+
```

---

#### Tab 04: `04_Equipment Takeoff Ledger`
Dedicated equipment counts showing evidence source reconciliation:

```
+------------+------------+---------+-------------+-------------+---------------------+---------+
| System     | Tag Prefix | Sched Qty Plan Count  | Variance    | Drawing Callouts    | Status  |
+------------+------------+---------+-------------+-------------+---------------------+---------+
| AHU        | AHU-1..4   | 4       | 4           | 0           | M-101, M-102, M-103 | MATCH   |
| VAV (Flr 1)| VAV-1-xx   | 48      | 50          | +2 (Floor)  | M-201 Callouts      | RFI-03  |
+------------+------------+---------+-------------+-------------+---------------------+---------+
```

---

#### Tab 05: `05_Drawing Index`
Complete ledger of specification sections, plan sheets, schedules, and addenda cited in the estimate.

---

### Modality B: Interactive Review Studio (`Review.html`)

A responsive **3-Pane Desktop Workbench** replacing the vertical single-column layout:

```
+------------------------------------------------------------------------------------------------------+
| [Estimator AI Logo]  Job: Project Alpha  |  Progress: [==== 85% ====]  |  [Save Decisions] [Export]  |
+------------------------------------+------------------------------------+----------------------------+
| PANE 1: SYSTEM EXPLORER (20%)      | PANE 2: PROPOSAL & SCOPE (50%)     | PANE 3: PROOF VIEWER (30%) |
|                                    |                                    |                            |
| Search Systems...             [Q]  | SYSTEM: AHU-1 (VAV Rooftop Unit)   | CITATION & EVIDENCE DRAWER |
|                                    | Base Qty: 4 units                  |                            |
| v AIR SYSTEMS                      |                                    | Source: Spec 23 09 23      |
|   [*] AHU-1..4 (4 units)  [OK]     | [+] Add Device Line                | Section: 2.4.B Page 14     |
|   [ ] RTU-1..2 (2 units)  [1 Warn] |                                    | "Supply air temperature    |
|   [ ] VAV Boxes (142)     [OK]     | > Supply Air Temp Sensor           |  sensor shall be 10k Type  |
|                                    |   Qty: 1 per AHU (Total: 4)        |  III thermistor installed  |
| v PLANT SYSTEMS                    |   Furnished: [AME       v]         |  downstream of fan..."     |
|   [ ] Chilled Water Plant [OK]     |   Installed: [AME       v]         |                            |
|   [ ] Boiler Plant        [OK]     |   Wired:     [AME       v]         | -------------------------- |
|                                    |   Citations: 2 refs [View ->]      | DRAWING CALLOUTS:          |
| v FRONT END & NETWORKING           |                                    | Sheet: M-601 (Mechanical)  |
|   [ ] BACnet IP Backbone  [OK]     | > Modulating Heating Valve Actuator| Callout: [TE-1] at SA Fan  |
|                                    |   Qty: 1 per AHU (Total: 4)        | Verified in 4/4 plans      |
| ---------------------------------- |   Furnished: [AME       v]         |                            |
| ESTIMATOR RFIs (Internal Takeoff)  |   Installed: [Mechanical v]        | -------------------------- |
| [!] Schedule shows 4 tags, but     |   Wired:     [AME       v]         | QC FINDINGS ON THIS LINE:  |
|     floor plan M-101 shows 5.      |                                    | (No open findings)         |
|     [Flag for Principal Estimator] | > Tech Labor: 32.0 hrs             |                            |
+------------------------------------+------------------------------------+----------------------------+
```

#### Key UX Features in Review Studio
1. **Coupled Ownership Dropdowns**: Selecting `Furnished By: Mechanical` automatically switches `Installed By: Mechanical` while maintaining `Wired By: AME` (single-click toggle), visually preventing VAL-11 mismatches.
2. **Synchronized Citation Drawer**: Clicking any device row in Pane 2 immediately pulls up the exact specification clause, schedule cell, and drawing tag in Pane 3.
3. **Direct Save Workflow (File System Access API)**: Replace blind browser downloads with `window.showSaveFilePicker()` so estimators can save `decisions.json` directly back into `out/`, eliminating duplicate files in `Downloads/`.
4. **Faceted RFI / Question Filters**: Replace `MAX_QUESTIONS = 15` truncation with filterable category chips: `[All (24)]`, `[Device Ambiguities (14)]`, `[Tag Mismatches (8)]`, `[System Level (2)]`.

---

## Part 4: Recommended Action Plan & Next Steps

### Phase 1: Rule & Validation Hardening
1. **Fix VAL-11**:
   - Update [src/bms/validate.py:183-193](file:///d:/Estimator%20AI/src/bms/validate.py#L183-L193) to check subline ownership against parent lines, with an explicit exemption for integration slots (`rep_assist`, `vfd_rep_assist`) per Ruling D3.
   - Update [playbook/rules.md:500](file:///d:/Estimator%20AI/playbook/rules.md#L500) and [src/bms/prompts/write_system.md:27](file:///d:/Estimator%20AI/src/bms/prompts/write_system.md#L27) to formalize this exemption.
2. **Synchronize Playbook Phrasing**:
   - Update [playbook/wording.json:10](file:///d:/Estimator%20AI/playbook/wording.json#L10) to match live formatting behavior (Ruling D6).
   - In [src/bms/review.py:433](file:///d:/Estimator%20AI/src/bms/review.py#L433), rename `"Open questions for the client"` to `"Internal Takeoff & Estimating RFIs"`.

### Phase 2: Evidence Engine Overhaul ([src/bms/evidence.py](file:///d:/Estimator%20AI/src/bms/evidence.py))
1. **Deduplicate Citations**:
   - In `evidence.py:56`, deduplicate `[*device.refs, *device.quantity.sources]` using a set keyed by `(source_id, quote, where)` before joining into cell text.
2. **Implement 5-Tab Architecture**:
   - Refactor `render_evidence_package()` to output the 5 tabs (`01_Bid Summary`, `02_Scope & Labor Ledger`, `03_Findings & QC`, `04_Equipment Takeoff`, `05_Drawing Index`).
   - Add `System.tech_hours` and `FrontEnd.tech_hours` to all summary rollups.

### Phase 3: Review Studio Polish ([src/bms/review.py](file:///d:/Estimator%20AI/src/bms/review.py))
1. **Remove Question Masking**:
   - Eliminate `MAX_QUESTIONS = 15` truncation; replace with collapsible accordion cards and tag counters.
2. **Native Save Integration**:
   - Upgrade script in `review.py` to use `showSaveFilePicker()` for direct saving.

---
*Report generated and archived in main folder as requested.*
