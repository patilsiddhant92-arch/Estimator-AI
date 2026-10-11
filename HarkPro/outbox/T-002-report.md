# T-002 report

1. Task T-002, branch hark/T-002, base origin/rebuild at ce07960. Last commit: see branch tip (one commit).

## 2. What I changed

## 2a. How prices are read today (before this change)

- `assets/price_book/` held an older copy of the AME workbook (`AME Std Pricing Spreadsheet.xlsx`, sheets "Parts Pricing"
  and "BMS-DDC-Panels") and `aliases.json` (empty).
- `estimator/__main__.py` (`PRICE_BOOK`, `ALIASES`) and `bms/run.py` call `PriceBook.load(book, aliases)`
  (`src/estimator/price_sheet/price_book.py`): every row with a text name in column B and a number in column C
  ("Estimation Price") is an item; a column A note starting "Need" marks the price as needing review.
- A price sheet line finds its price by `price_key`: bullet, leading verb (Furnish / Furnish and Install / Furnish and
  Wire / Provide) and "(Qty. N Total)" taken off, lower case. It must equal an item's name, or an alias key
  (`aliases.json`: scope line -> exact item name). "Install and wire ..." lines are never priced (device by others).
- No match: `write_price_sheet` leaves the unit price empty, writes PRICE PENDING in column H and counts it on the
  Summary; a questioned price is written and flagged PRICE NEEDS REVIEW. `price_check` lists the 3 closest items to help
  an estimator add an alias. No fuzzy match ever prices a line.

## 2b. Approach and files

Approach: **the loader reads the revised workbook in its own layout, and the app's copy is Brain's file byte for byte**,
put there by `tools/update_price_book.py`. Why: the app reads the fixed path `assets/price_book/AME Std Pricing
Spreadsheet.xlsx` from `__main__.py`, which I may not edit, so it can't point at `Brain/` directly; and converting to the
old two-sheet format would make a second, different file (and lose the valve sheet's sizes). A byte copy keeps one
content: the estimator edits only Brain's workbook, runs the tool, and the suite fails
(`test_the_apps_copy_is_the_estimators_revised_workbook`) until the copy matches.

- `assets/price_book/AME Std Pricing Spreadsheet.xlsx`: now Brain's revised workbook (sha256 2768e1b3...).
- `assets/price_book/aliases.json`: 75 aliases from the Master Template's device names (list below); "about" says they
  wait for the estimator's review.
- `src/estimator/price_sheet/price_book.py`: reads sheets "Std Parts Pricing", "BMS-DDC-Panels", "Control Valves &
  Meters" (B = name, C = price; the valve sheet's side table H/I too). Not an item: a row without a name (a second part
  number) or without a price above 0 (blank, word, 0). Valve size rows read "<heading> <size>" ('Modulating Control
  Valves 1/2"'); a "High Performance" row reads "<item above> - High Performance". Rows under the book's own "Below is
  not completed" note (the three Plant Controllers) are priced but marked needs review. A missing sheet is refused in
  plain words. An alias whose key is itself a different book item is refused (it could never apply). New
  `PriceBook.unpriced(lines)`: the lines with no price.
- `tools/update_price_book.py` (new): checks the workbook with the aliases, then copies it; refuses (copy left as it
  was) when the workbook can't be read or an alias target is gone; prints priced items per sheet. `--check` only
  compares (exit 1 when out of date).
- `tests/test_assets.py`: the pinned hash is the new workbook's; "alias file starts empty" became "alias file maps names
  to names". `tests/test_price_book.py`: counts (114 = 53 + 19 + 42), no-guessing examples, the book's own doubts (Plant
  Controller), rows without a price (Enable/Disable) follow the revised workbook. `tests/test_write_price_sheet.py`:
  the PRICE NEEDS REVIEW test builds its own questioned item (the revised book no longer questions Filter DP Switch).
  These three files are outside the named list; they pin the old workbook, so they had to follow it.

Real workbook now: 114 priced items (Std Parts 53, Panels 19, Valves & Meters 42), 3 marked needs review.
Prices that changed for lines the old book priced by name: Outdoor Air Temperature Sensor 50 -> 100, BACnet Thermostat
(for Supplemental AC/FCUs) 360 -> 355, (for CUH/EUH/FTRs) 200 -> 255, DDC Controller ... 16UIO 1000 -> 1100.
Renamed: "Space Temperature Sensor" (TR100-T-G) is now "Thermostat for FPB/VAV/Terminal Units" (same part, 142, kept by
alias); "Duct Air Temperature/Humidity Sensor" became "Duct Humidity Sensor". Gone from the parts sheet: the seven
"... Control Valve and Actuator" budget lines (AHU CHW 500, AHU HW 400, ...); valves are now priced by size.

## 2c. Alias coverage

End devices = the Master Template's device lines for the Playbook's shapes (the house names a device slot prints, from
`assets/system_templates.json` and `assets/front_end.json`), leaving out points (enable, status, start/stop, VFD,
setpoint, alarm), wiring, interlocks, integration lines, monitored items, labour lines and install-and-wire / tie-in /
by-mfr lines (furnished by others, never priced by design). `wording.json` names no end device of its own (verbs,
owner brackets, the integration trio); the FA relay bracket is not a priced device. Shapes' slots themselves carry no
device name, so a job prices only when the document's name matches an item or an alias.

**159 end devices: 83 priced, 76 not.**

Aliases added (scope name -> book item): DDC Controller to the Factory for Installation -> VAV DDC Controller; Space
Temperature Sensor -> Thermostat for FPB/VAV/Terminal Units; Space Temperature / Humidity Sensor -> Thermostat with
Humidity ...; Space Temperature / Humidity / CO2 (Sensor) -> Thermostat with Humidity & CO2 ...; Space Temperature
Sensor (BMS Monitoring) / for BMS Monitoring -> Space Temp for Monitoring; Discharge Air Temperature / Discharge
Temperature Sensor -> Discharge Air Temperature Sensor; Outside Air Temperature (Sensor) -> Outdoor Air Temperature
Sensor; Outside Air Temperature / Humidity Sensor -> Outdoor Air Temp/Humidity Sensor; Building Static Pressure Sensor ->
Building Pressure Sensor; Supply Static Pressure Sensor -> Duct Static Pressure Sensor; Expansion Tank Pressure
Transmitters -> Expansion Tank Pressure Sensor; every water Differential Pressure Transmitter(s) line (11) -> Water
Differential Pressure Sensor; single and plural water / glycol Temperature Transmitter(s) and Basin Water Temperature
Sensor (10) -> Water Temperature Sensor (with well); Return Air CO2 Sensor -> Duct CO2 Sensor; Return Air / Discharge Air
Humidity Sensor -> Duct Humidity Sensor; Freezestat -> AHU Freezestat; Freeze stat -> UV Freezestat; (Spot) Leak Sensor
-> Spot Leak Sensor - Standard to use; Damper Actuator, Outside / Return / Exhaust Air Damper Actuator -> Standard Damper
Actuator; Horn and Strobe Sensor, Remote Horn / Strobe Sensor, Horn / Strobe -> Horn and Strobe; Breakglass Switch (/
Station) -> Break Glass Switch; Boiler Room CO Sensor -> CO Sensor; Boiler Room Natural Gas Sensor -> CH4 Sensor;
Sensaphone -> Autodialer (6 Point Alarm) + Panel; (Local) RAM Module -> RAM Device; Fan CT -> Status / CT; Flow Switch,
Chiller / Geothermal Heat Pump Flow Switches -> Water Flow Switch / Pressuretrol; Chilled Water / Hot Water / Chilled
Water Main Flow Meter -> Flow Meter; every "... BTU Meter - ..." line (7) -> BTU Meter; UPS for DDC Controller, UPS – For
workstation, server, network level control panel -> UPS; POT (Laptop or Tablet) -> Laptop; Network Switch(es) ->
Newtwork Switch (Standard).

Still no price (76):
- Valves, priced by size on "Control Valves & Meters", and a Master Template line carries no size (31): 3-Way Hot Water;
  Boiler Isolation; Chilled Glycol Flow Bypass; Chiller Isolation w/ (2) End Switches; Condenser Water Supply / Return
  Isolation; Cooling Coil; Cooling Coil Water; Cooling Tower Spray / Sump / Supply-Return Isolation (3); Differential
  Pressure Bypass; DP Bypass; Domestic Water Preheat; Free Cooling Flow Control (Duty/Standby); Geothermal Ground Loop
  Flow Bypass; Geothermal Heat Pump Isolation / Modulating (2); GHP Hot Water Supply; Heat Exchanger; Heat Exchanger
  Isolation / Modulating (2); Heating Coil; Hot Water; Hot Water Plant Bypass; Humidifier; HX Primary / Secondary / Steam
  (3); Minimum Flow Bypass; Snow Melt Heat Exchanger; Steam / Hot Water (by AME) - each "... Control Valve(s) and
  Actuator(s)".
- The book has more than one size or kind and the line doesn't say which (5): DDC Controller; DDC Controller or
  Communicating Thermostat; Network Level Control Panel (25 or 100 devices); Outside Air and Supply Air Flow Measuring
  Station (Large AHUs or Smaller Units).
- Supply / return pairs, one line for two sensors (7): Building Water, Chilled Water Coil, Condenser Water, Hot Water
  Coil (air), Hot Water, HX, System Water Supply / Return Temperature Sensor.
- A likely item, not added until confirmed (21): Coil Leaving Air / Return Air / Return Temperature Sensor (3, Discharge
  Air Temperature Sensor 25?); High Static Pressure Switch, Low Suction Pressure Switch (Hi / Low Pressure Switch 210?);
  High Limit Humidity Switch (Duct Humidistat 350?); Stairwell Pressure Sensor (Building Pressure Sensor 120?); DP Sensor
  for Supply / Exhaust Airflow Monitoring (Piezo Ring) (2, Duct Static Pressure Sensor 120?); Damper Actuator w/ End
  Switch, Damper Actuator (Exhaust Fan), Damper Actuator (Smoke Detector by Others), Outside Air/Return Air, Intake /
  Exhaust, Heat Wheel Face/Bypass Air Damper Actuator (6, Standard Damper Actuator 320?); Outside Air Humidity (Outdoor
  Air Temp/Humidity Sensor 150?); Outside Air CO2 (Outdoor Air Temp / Humidity / CO2 Sensor 350?); CO/NO2 Sensor (CO 300
  plus NO2 330?); Pull Station (Break Glass Switch 170?); Remote Refrigeration Sensor (Refrigerant Leak Sensor (for VRF)
  250?); Remote Space Temperature Sensor, VRF (Space Temp for Monitoring 76?).
- Flow meters other than the main chilled / hot water ones (5): Steam, Chilled Water System Makeup Water, Hot Water System
  Make-Up (transmitter), Domestic Hot Water, PFHX Flow Meter.
- Nothing in the book (7): Gas Detection Panel; Electrical Meter; Nest Thermostat (Alternate); Fan Relays (Enable/Disable
  has a part, no estimation price); IT Infrastructure "Panels" and "Fiber – Ethernet"; Stairwell/Elevator Pressurization
  (unclear device). 3-D Graphics and Training are labour, left out of the count.

31 + 5 + 7 + 21 + 5 + 7 = 76.

## 2d. What Sheet 1 ("Bid Overview") asks to look for

A per-bid checklist with a YES/NO (or NA) column E and a notes column:
- Header: Job #, MEP Engineer, Mech / GC, Estimator, Project Type, Floors, Labor Type (Union / OS).
- QC review of the take-off: (1) Quantity Take-Off, (2) Schedule Notes, (3) Mechanical details from the mechanical floor
  plans, (4) Network riser and workstation accessories, (5) Keynotes on the mechanical plans, (6) Notes from HubSpot /
  the client's request, (7) Plumbing / electrical drawings requested if needed.
- Important notes: New BMS, standalone or tie-in; additional warranty (1 year standard in base); service contract; tax
  exempt, prevailing wage, PLA, CCIP/OCIP, P&P bond, proposal validity; overtime requirements; any mechanical work.
- Spec and SOP review / exhibits / RFIs / design-build scope narrative: acceptable manufacturers; existing BMS vendor;
  BMS network by AME or the IT vendor; 120 VAC power wiring for BMS panels; power wiring for VAV boxes; FSD scope of work;
  work on smoke purge / fire alarm; BACnet IP or MS/TP controllers; control valve make; control valve type
  (high-performance, PICV, butterfly, globe, energy valve); AFMS; BTU / flow meters; gas monitoring; third-party systems.
Most items map to facts the reading step already finds (front-end mode, warranty, tax/PW, VAV power, FSD, valves,
meters); a check could list each item as found (with its source) or "not found" on the review page.

The workbook's "Base", "ALT #1" and "ALT #2" sheets are a bid workup (tech 110/h, PM 40 %, engineering 20 %, markup 40 %,
contractor markup 25 %, NY tax 8.875 %, street buffer 5 %). The app still writes the separate
`PriceWorkup_Template - 12-21-25.xlsx`; I did not change that.

## 3. Tests

New `tests/test_price_book_revised.py` (19, invented workbooks and names): priced by book name; priced by alias; a
device with no price is reported by `unpriced`; a row with no / 0 / word price is not an item; an alias to an unpriced
row is refused; the price sheet leaves an unpriced line empty and flagged PRICE PENDING (never 0); all three price sheets
read, bid sheets not; a second price without a name is not an item; valve size takes its heading; High Performance takes
the item above; the valve sheet's side table is read; rows under "Below is not completed" need review; a column A
"Need" note still marks; a workbook without a price sheet is refused; an alias that would hide a different item is
refused; the app's copy is Brain's workbook; every alias points at a priced item; the tool copies and `--check` reports
stale; the tool refuses a workbook that breaks an alias and leaves the copy. Updated: see section 2.

Full suite (`PYTHONPATH=src python -m pytest tests -q -p no:cacheprovider -n 2`): 7 failed, 4431 passed, 10 skipped
in 843.71s. All 7 are baseline: 4 of the 5 test_ai chat tests (the fifth passed this run), test_review_final3 resource
code, test_main open output folder, test_assets project python.

## 4. What I did not do, and why

- No Sheet 1 check (as asked). No sizing of valves, no choice between controller / panel / airflow-station sizes: those
  need a job fact (size, IO count, device count), and pricing them is a model or renderer change.
- Aliases are by name only, so one name can't have two prices by system (see questions 1-3).
- Not touched: playbook/, model.py, playbook.py, run.py, __main__.py, fixtures, contracts, specs, the workup template.
  `tests/conftest.py`'s comment on `small_job` still says Filter DP Switch is "marked Need review" (cosmetic, left).
- Prices from the valve sheet keep the workbook's own decimals (1390.425 = 1.25 x 1112.34).

## 5. Questions (for the estimator)

1. "Space Temperature Sensor" is aliased to Thermostat for FPB/VAV/Terminal Units (142, the old standard). The workbook
   says "Space Temp for Monitoring" (76) is for exhaust fans and misc systems, and the Master Template uses "Space
   Temperature Sensor" on exhaust fans, unit heaters, FCUs and UVs. Keep 142 for all, or should the exhaust fan line read
   "Space Temperature Sensor for BMS Monitoring" (76)?
2. Unit heaters' "BACnet Thermostat" matches the panels sheet item "BACnet Thermostat" (355), but the parts sheet has
   "BACnet Thermostat (for CUH/EUH/FTRs)" at 255. Which is right for CUH/EUH/UH? (An alias can't override an exact name.)
3. Damper actuators: plain "Damper Actuator" is aliased to Standard Damper Actuator (320). The workbook notes LF24-SR at
   270 "for smaller AC units & exhaust fans" (a price row with no name). Should exhaust-fan actuators be 270, and what
   do "w/ End Switch" and the other variants cost?
4. Leak Sensor is aliased to "Spot Leak Sensor - Standard to use" (112); FCU / apartment heat pump units may want "Leak
   Sensor for Residential/Hotel FCUs and WSHP Units" (60). Which for those?
5. Valves: the book prices by size. Should the app read the size from the valve schedule and pick "Modulating Control
   Valves <size>" / "HW/CHW Isolation Control Valves <size>", or keep valves PRICE PENDING for the estimator?
6. Supply / return temperature lines: price as 2 x Water Temperature Sensor (with well) per line?
7. Please confirm or reject the 21 "likely item" pairs in section 2c, and the aliases added (they are marked as waiting
   for your review in aliases.json).
8. "Flow Meter" (5000) and "BTU Meter" (6000) are marked Budget; sized meters are on the valve sheet. Keep the budget
   price for unsized lines?
9. Bray "14\" 2-Way Open/Close Valve" is 555.19 while 12" is 4359.81 and 16" is 7942.96: a typo in the workbook?
10. Should the app's price workup move to the workbook's own Base / ALT sheets (different markups from the
    PriceWorkup template)?
