# Discussion

Questions for Siddhant and his rulings.

## 2026-10-09
- Siddhant: work in our own GrokTeam/ folder on grok/work from main; never touch Claude's main app or HarkPro/. Record important discussions here for other AIs.
- Team created: Grok Bot (lead), Estimator QA, Builder, Reviewer; group chat "Estimator AI - Grok Team".
- HarkPro reviewed read-only: see harkpro-review-2026-10-09.md.
- Test job 26-0560 provided by Siddhant; run on Grok Bot's computer only, job data and outputs kept out of the repo.
- Ruling (13:29 IST): The Master Template shows how a system looks in ideal conditions. The job is always written from the information it holds. Use the template as a checklist: write template devices the documents support; a template device the documents do not support becomes a question for the estimator, not a printed line. HarkPro C11-C16 (template lines print by default) not adopted.
- Standing rulings (14:43 IST): VRF communication wiring is AME's by default on VRF systems. The VRF central controller is OEM/vendor scope, not AME; the VRF remote controller is the Master Template's programmable thermostat, furnished by OEM, installed and wired by AME. Damper "w/ End Switch" prints only when the documents call for it. Refrigerant leak detector is AME-furnished when the documents say "provide" with no party. Air curtain: door switch interlock.
- Ruling (14:50 IST): Every VAV gets "Furnish DDC Controller to the Factory for Installation" (R11 confirmed), unless the documents give VAV controls to someone else.
- Principle (14:50 IST): Estimating means connecting the dots across inputs. Link sensors and devices to the unit that serves their room (schedule area-served column, plan symbols, duct routing), never to the nearest tag.
- Builder (14:55 IST), rulings adopted in GrokTeam tests and proposed patches, at the lead's direction. FINAL means Siddhant ruled. PROVISIONAL means the lead adopted it and Siddhant has not ruled yet:
  - R1 FINAL (Siddhant Q4 / R11, 14:50 IST): every VAV gets "Furnish DDC Controller to the Factory for Installation", qty = VAV count, even when no document names one, unless a document gives the VAV controls to the box maker or someone else. This is the second documented exception to "no standard or fallback lines" (the first is Q1, VRF communication wiring). Both live in one table, `bms.rulings.DOCUMENTED_DEFAULTS` (patch 07). The earlier provisional R1 ("ask a question") is withdrawn.
  - R2 PROVISIONAL: when no BMS or front end is shown, print standalone scope plus ONE question: "No BMS or front end is shown in the documents; confirm standalone controls."
  - R3 PROVISIONAL: the schedule count wins. A unit tag shown on several plans counts its schedule qty: once if the schedule lists it once, 2 if the schedule says QTY 2. This contradicts main test CNT-5 on purpose. NOTE: Siddhant had asked to hold the CNT-5 change; R3 is provisional until he rules.
  - R4 PROVISIONAL: equipment with no template family raises "No template family fits ...; is it in AME's scope?" (refrigerant leak detectors excepted, per Q11).
  - R5 PROVISIONAL: a stand-alone condensate pump raises a question only when a document shows an alarm or interlock for it. NOTE: Siddhant had asked to hold the condensate-pump change; R5 is provisional until he rules.
  - R6 PROVISIONAL: a damper actuator with no named furnisher prints "Wire Damper Actuator (Furnished by Others)", not a question (Motorized Dampers blocks only).
  - Standing Q1, Q2, Q7, Q11 (14:43 IST above) are applied by `bms.rulings` after the writer (patch 07).
  - 6c finding: no schedule area-served / room / serves link exists in src today. Proposed: a ledger kind "area_served" and room-number-keyed matching (strict xfail tests only, no patch).
