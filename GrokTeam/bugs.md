# Bugs

Problems found in the app outputs, with evidence (file, sheet, line) and severity.

## B-01 (High): app does not connect devices to the unit that serves their room
Found on test job 26-0560 (2026-10-09). Applies to the original app (src/bms), not fixed there; proposed fix is GrokTeam patch 6c.
- What happened: 3 CO2 sensors were assigned to the VAV boxes because each sat in a room near a VAV tag. The correct owner was the AC/VRF indoor unit whose duct serves that room (confirmed by Siddhant and by duct trace).
- Why: the app links a device to the nearest tag. It never reads the schedules' "Area Served" / room column (only duct heaters have a served link, `_SERVES`/`Served` in src/bms/plan.py), and it does not combine plan symbols, schedule columns and duct routing. With no sequence of operation there was nothing else to go on.
- Rule (Siddhant): estimating means connecting the dots across inputs. A device belongs to the unit whose schedule says it serves the device's room; match on room number, name only as fallback; if two units claim the room, or none does, ask the estimator. Never fall back to the nearest tag.
- Related on the same job: VRF thermostat note on a detail sheet never linked to the VRF family; outside-air riser damper not traced to DOAS-1; VAV-2 duct CFM 420 vs schedule max 320 not flagged.

## From Estimator QA (2026-10-09)
Found while scoring a test run against a hand-built answer key. That run's AI steps were answered by an assistant in chat mode, so it is not a clean stock baseline. Every tag, room and quote below is invented. None of these repeats bugs 1-6 (GrokTeam patches) or B-01.

### B-02 (High): equipment schedules on a schedule sheet are never extracted; only the title-block revision table is found
- **Symptom:** every family reports "schedule rows 0". The schedules pass lists one "Schedule (no title found)" per sheet, holding only the MARK | DATE | DESCRIPTION revision rows. The schedules pass request carries no images. As a result:
  - maker and model never reach the headers;
  - schedule notes that give devices to the unit maker ("DISCHARGE SENSOR FURNISHED BY UNIT MFR, MOUNTED IN DUCT") are lost, so those devices print as AME Furnish and Install;
  - counts have no schedule anchor.
- **Likely cause:** the table finder stops at the first ruled table on the sheet (the revision block), or drops wide multi-header equipment tables. With text-only evidence, nothing falls back to the page image when a sheet titled as a schedule yields no tagged rows.
- **Suggested failing test:** an invented schedule sheet with a 4-row revision block and an "AIR UNIT SCHEDULE" table (tags XU-1..XU-3, columns TAG | CFM | MANUFACTURER | NOTES; note 5 "SUPPLY SENSOR BY UNIT MFR").
  - Expect three XU rows extracted, manufacturer captured, and note 5 linked to XU.
  - Expect that when a sheet whose title block says "SCHEDULES" yields 0 tagged rows, the schedules pass attaches that page image.

### B-03 (Medium): a system with no shape is named after a sequence heading, merging two families
- **Symptom:** the block header reads "Qty (8) Sequence Of Operation - Cold Loop Pump QP-1 thru 8", although QP-odd are cold-loop and QP-even are warm-loop pumps from two separate sequences. The shape is empty, so no tech-hour rule applies.
- **Likely cause:** when no schedule title names the family, the system name falls back to the first matched sequence heading text. Families whose tags share a prefix are joined into one system without keeping the second heading.
- **Suggested failing test:**
  - Inputs: invented sequences "3.05 SEQUENCE OF OPERATION - COLD LOOP PUMPS, QP-1,3,5,7" and "3.06 SEQUENCE OF OPERATION - WARM LOOP PUMPS, QP-2,4,6,8", with no schedule.
  - Expect the system name to be the family name ("Pump"), never "Sequence Of Operation…".
  - Expect the header to list both services, and the system to get the pump shape (or a planner question).

### B-04 (Medium): front-end tie-in text doubles words and keeps the template placeholder name
- **Symptom:**
  - The scope line prints "Seamlessly Tie in to the Existing Existing Campus Zephyr BMS BMS".
  - The opening sentence still says "an extension of the existing <template placeholder> BMS system" instead of the found system name.
- **Likely cause:** the found `existing_name` already includes "Existing" and "BMS", and the renderer wraps it as "Existing {name} BMS" without normalising. The opening paragraph is not templated from the front-end fact at all.
- **Suggested failing test:**
  - With `existing_name = "Existing Campus Zephyr BMS"`, the scope line equals "Seamlessly Tie in to the Existing Campus Zephyr BMS". No word may repeat back-to-back.
  - The opening contains "Campus Zephyr" and does not contain the template placeholder.

### B-05 (Medium): a per-fan tech-hour rule is applied once per block
- **Symptom:** a block of 6 field-DDC exhaust fans (XF-1..XF-6), each with a controller, gets 4 tech hours in total instead of 4 per fan.
- **Likely cause:** the exhaust-fan shape rule is written as "4 hours when the block has a device in each of: controller". It is a block-level condition, not multiplied by the fan count, while the template rule is per fan.
- **Suggested failing test:** with 6 XF fans, a controller line and a start/stop line, tech_hours == 24. A block of 1 fan gives 4.

### B-06 (Medium): one physical device prints in two blocks
- **Symptom:** a fan's motorized damper actuator prints under the parent air unit's block ("Furnish and Install Exhaust Damper Actuator", qty = units) and again under the fan's own block ("…Exhaust Air Damper Actuator w/ End Switches", qty = fans). It is priced twice.
- **Likely cause:** the parent unit's control diagram includes the child fan's points. The unit writer turns them into lines without checking whether the fan family has its own block. There is no cross-block dedupe by device and served tag.
- **Suggested failing test:**
  - Inputs: an invented diagram for XU-1 listing "XF-1 DAMPER ACTUATOR" and "XF-1 START/STOP", plus a separate XF family block.
  - Expect the damper and fan start/stop lines in the XF block only. The XU block carries no XF device, or a validator raises a duplicate-device finding.

### B-07 (Medium): points marked FUTURE on a control diagram become scope without a question
- **Symptom:** "Furnish and Wire Outside Airflow Measuring Station" prints with the unit count. The control diagram marks that point "[FUTURE]", and no plan or schedule shows it.
- **Likely cause:** the details pass records "[FUTURE]" only in free text. The writer gives the sequence sentence ("shall be provided with an airflow station") priority, and no rule turns a FUTURE / ALTERNATE / BY OWNER marker into a question or an alternate.
- **Suggested failing test:**
  - Inputs: invented diagram text "[FUTURE] OA AIRFLOW (FM)" and a sequence sentence requiring the station.
  - Expect no printed line and one planner question ("diagram marks the airflow station FUTURE; include it?"), or an add-alternate line.

### B-08 (Medium): header quantity exceeds the tags it names, and the provenance note contradicts itself
- **Symptom:**
  - A header prints "Qty (10) Exhaust Fans XF-1 thru 5", a quantity larger than its own non-type tag range, and no validator finding is raised.
  - The client proposal prints "*Qty. (21) per SHEET-A; 6 elsewhere in the documents; 6 per SHEET-A", which gives two counts for the same sheet.
- **Likely cause:** the validator does not compare `Count.value` to the distinct unit tags in the printed range. The provenance note is assembled from several count refs without a consistency check.
- **Suggested failing test:**
  - A block with tags XF-1..XF-5 (non-type) and Qty 10 gets a must_fix "header quantity exceeds the distinct tags named".
  - The provenance note renderer refuses, or merges, two different values for the same sheet.

### B-09 — WITHDRAWN (2026-10-09): the app's "Qualifies" was right: the spec lists a pre-qualified product the bidder carries
*Withdrawn after the estimator's bid ruling. A spec that lists a carried product among its pre-qualified field controllers qualifies the bidder on product. An installer-credentials clause is a bid action item, not a no-bid. The original entry is kept below for history; do not implement it.*

~~B-09 (High): the bid check says "Qualifies" when the spec restricts who may install~~
- **Symptom:** the bid check reports "Qualifies — the spec names <product line>" because a product is listed. Meanwhile, the controls section names a single approved installer "or approved equal", requires credentials submitted before bid by non-prequalified installers, and requires the installer to be an authorized dealer of the incumbent system. None of this surfaces.
- **Likely cause:** the bid check only matches product and platform names. It does not look for "approved integrator / installer", "prequalif", "authorized distributor / branch" or "submit credentials prior to bid" clauses.
- **Suggested failing test:**
  - Inputs: invented spec text "Approved integrators: Zephyr Controls: the controls contractor is Acme Installers LLC, or approved equal. Installers not prequalified shall submit credentials ten days prior to bid", plus a product list that includes the house platform.
  - Expect a verdict of "Qualifies — with conditions" (or "Check"), with a question citing the clause.

### B-10 (Medium): a job-wide work-hours restriction is not checked against the house clarifications
- **Symptom:** the plans say all work is to be done between 10PM and 5AM and on weekends. The proposal still prints the house inclusion "All labor will be performed during normal business working hours", plus the exclusion "All off-hours or overtime labor", with no question or flag.
- **Likely cause:** general and phasing notes about work hours are not extracted as a job-condition fact. Nothing compares job conditions to the house clarifications.
- **Suggested failing test:**
  - Inputs: an invented plan general note "ALL WORK IN OCCUPIED AREAS SHALL BE PERFORMED BETWEEN 10PM AND 5AM".
  - Expect a job-condition fact and one planner question ("documents require off-hours work; house text says normal hours; carry a premium?"). House text stays unchanged ([PROV 7]).

### B-11 (Low): HarkPro coverage mislinks printed lines
- **Symptoms:**
  - (i) Printed lines in off-library wording ("Furnish and Wire Heating Coil Valve") or inside a block with no shape ("Furnish Pump Start/Stop and Status") are not linked to their facts, giving false must_fix findings.
  - (ii) An AME "Furnish and Wire Hot Water Coil Control Valve" line is flagged under R2 as "printed as the mechanical contractor's".
- **Likely cause:**
  - (i) Linking needs a lines.json id or the block's shape concept map.
  - (ii) R2 reads "mechanical contractor" from the block's clarification text (MC installs the valve) instead of the line's own verb and owner.
- **Suggested failing test:**
  - (i) An invented ledger fact "QP pump start/stop and status" with a printed line "Furnish Pump Start/Stop and Status" in a shape-less QP block counts as accounted.
  - (ii) A line "Furnish and Wire Warm Coil Control Valve" with a note "valve installed by mechanical contractor" raises no R2 finding.

### KL-01 (Known limit, Builder): dashed-only status cannot be read from the sheet text
- **What:** Plans often draw an item that is not new work with dashed lines. The sheet text (`PageRecord.text`) carries words only, with no line style. So the plan text cannot show that an item is drawn dashed.
- **Effect:** Patch 04's demolition filter has an "unknown / drawn dashed" state (`counts.UNKNOWN`). A dashed-only item that no schedule lists is still counted and raises a question, never dropped silently. But nothing sets that state from a real drawing yet. Only test fixtures set it (`_Sheet.marks[tag] = UNKNOWN`). On a real job a dashed-only item counts as new work, with no question.
- **Possible next step (not built):** read the line style from the PDF's vector paths near the tag (dash pattern), or ask the sheet-picture pass to report dashed symbols beside `untagged_symbols`.
- **Test to add once a source exists:** an invented plan with a tag drawn only in a dashed outline and on no schedule. The tag stays counted and raises one question naming the tag and sheet ("EF-9 appears only drawn dashed, on sheet X-901 ...").
