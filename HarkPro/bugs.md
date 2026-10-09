# Bugs and status

Status as of 2026-10-09. "Fixed*" = fixed in the uncommitted patch, awaiting review.

## Reading layer (READ)
| ID | Bug | Status |
|---|---|---|
| READ-1 | Title-block slack drops centered titles, so many sheets get no type and no AI reading pass | Fixed* |
| READ-2 | Ductwork, zoning and controls plans of the same floor summed, so VAV counts double (Job 3 ~2x, Job 2a 25 vs 15) | Fixed* (same-floor dedupe) |
| READ-3 | Air-outlet type schedule (B1-B4) read as ~1,763 boilers on Job 3 | Fixed* |
| READ-4/5 | Schedules skipped when the header is "UNIT", "PUMP NO." or blank, or when one good table blocks the fallback (AC, ACCU, EF = 0 on Job 2b) | Fixed* |

## Plan and counts (PLAN)
| ID | Bug | Status |
|---|---|---|
| PLAN-1 | Typical floors ignored in the plan-text count | Fixed* |
| PLAN-2 | Vision count = number of distinct tag names, not placements | Fixed* |
| PLAN-3 | "VAV-1 thru 5" against a schedule of 3 prints 3 | Fixed* (discrepancy flagged) |
| PLAN-4/5 | "(TYP. OF 4 PLACES)", "CUH-A(4)" and "4x CUH-A" read as 1 or 0 | Fixed* |

## Core model, validators, renderer (CORE)
| ID | Bug | Status |
|---|---|---|
| CORE-1 | Unnamed existing BMS crashes the render | Fixed* (prints "[existing BMS name]" + clarification) |
| CORE-2 | (see audit) | Fixed* |
| CORE-3 | Validator contradicts ruling D1 (one clarification per kind) | Fixed* |
| CORE-4 | False must_fix on D3 rep-assist lines | Fixed* |

## Run, review, evidence (RUN / EVID)
| ID | Bug | Status |
|---|---|---|
| RUN-1 | Deletes/changes from the revise are not re-applied; deleted lines come back | Fixed* |
| RUN-2 | Re-copying an old decisions.json rolls back newer answers | Fixed* |
| RUN-4 | (see audit) | Fixed* |
| RUN-10, EVID-01, EXCEL-01, LABOR-01 | Evidence Package: duplicate citations, filter breakage, tech hours missing | Fixed in commit 7e27873 (branch hark/evidence-ui, not pushed) |
| RUN-11 | Revise answers can't change family, count or alternate; app reverts to the planner (VAV 30 printed instead of 15) | Fixed* |
| MAX_QUESTIONS | Must-fix questions hidden by the question cap | Fixed* |

## Scope (found on the Job 2a AI run)
| Bug | Status |
|---|---|
| VAVs with a factory-mounted controller classed as packaged/integration instead of field DDC | Fixed* (Master Template lines: DDC controller furnished to factory, space temp / CO2 sensor, 24V transformer, reheat/DAT/valve when applicable, 3 h cooling-only / 4 h HW reheat) |
| Diffuser/grille type codes promoted to controls systems | Fixed* |
| AC schedule missed | Fixed* |
| Front end drops spec lines (MER DDC panel, graphics, lighting integration); QC findings on the front end never revised | Fixed* (round 2) |
| "(ADD ALTERNATE)" in a schedule title not read | Fixed* (round 2) |
| Equipment with no BMS scope never prints the Master Template EXCEPTION line | Fixed* (round 2) |
| Proposal opening always says "existing District Wide BMS system" | Fixed* (round 2) |

## Still open
| Item | Notes |
|---|---|
| PRICE PENDING lines | 10 on Job 2a (AC, CP alarm, VAV DDC controller, BIPO). Price book gaps DOC-11..14 |
| CP and BIPO named "Equipment" | Prefixes missing from the equipment catalogue |
| Vision cache reuse | Next run must freshly inspect every tile |
| Pre-existing test failures | 11-12 fail on clean 7e27873 too: 5 test_ai chat, python pin, Windows file locking, Windows resource code, flaky normal-exit, flaky revert-audit |
| Two real tags left in docstrings in the patch | Redacted in this copy; to clean in source |

## Pipeline (queued, fix after mockup review)
| Item | Plan |
|---|---|
| Proposal clarifications too long | One short client-facing line per "*" item; full reasoning stays in the Evidence Package |
| Colour-coded markers | `**` client note = red EE0000 (house, per Master Template); `*Confirm` = orange ED7D31; `*Assumed` = blue 2F5597. Mockup sent 2026-10-09, awaiting review |
| Empty "DEDUCT ALTERNATES: ALT #:" | Drop when there are no deducts |
| Controls by mechanical = AME scope | EF thermostat "by MC" → "Furnish and Install Space Thermostat" (wiring scope TBD) |

## Pipeline: scope misses on Job 2a (found in review 2026-10-09; the facts WERE in the ledger, so they were dropped between ledger and scope)
| Miss | Fix |
|---|---|
| Local alarm panel for leak detectors / condensate overflow | "Furnish and Install Local RAM Module" (Master Template) |
| Motorized dampers shown on plans with no tags | Count every damper actuator; trace ducts to assign to equipment; if not assignable, print as its own block, never assume 1 per unit |
| Radiator control valve interlock with each VAV zone thermostat (wired separately) | Interlock wiring line per zone |
| Occupancy sensors (19 on the controls plan; thermostat with integral occupancy by HVAC contractor) | AME line, or flag AME vs electrical ownership |
| Lutron Vive integration for occupied standby | Front-end line (round-2 front-end writer; verify on rerun) |
| Rule clashes (rules.md 78-84, 122-124, 466-472; GEM v3.2 Q1) | Rewrite to the MC-controls ruling |
| Systemic | Coverage gate: every controls-relevant ledger fact must end as a line, an exception, a clarification, or a dismissal with a reason |

## Job 4 (found 2026-10-09; app not changed, so these were worked around in the output)
| Bug | Notes |
|---|---|
| A seed count that a pass contradicted still prints | The writer and planner keep the seed values (AHU, ERV, FCU) |
| One source id carries different text in the write evidence and the quote index | Correct quotes are rejected |
| The control schematic and details are left out of the write evidence | AHU devices were missed |
| EF schedule notes are not read | The damper with actuator and end switch is missed |
| A system is named after its sequence heading | "Sequence Of Operation - ..." |
| The planner's own plan-image citation is rejected | Same as the known plan-image bug |
| Plan counts double-count units drawn on both the duct and the piping sheets | |
| "(E) RH COIL" is read as a humidity sensor | |
| The front end repeats the "Seamlessly Tie in" line | |
| A standalone FCU is flagged as packaged | False "integration lines missing" must-fix findings |
| The playbook defaults unit-schedule devices to the unit manufacturer | Conflicts with R19 |
| "Wire Damper Actuator" is used when the schedule lists the damper with the unit | Conflicts with R20 |
| A block can print as interlock only | Conflicts with R21 |
| The Evidence Package shows source and line ids, not quotes | Conflicts with R22. HarkPro's evidence is fixed; the app's is not |
