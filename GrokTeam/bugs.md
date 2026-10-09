# Bugs

Problems found in the app outputs, with evidence (file, sheet, line) and severity.

## B-01 (High): app does not connect devices to the unit that serves their room
Found on test job 26-0560 (2026-10-09). Applies to the original app (src/bms), not fixed there; proposed fix is GrokTeam patch 6c.
- What happened: 3 CO2 sensors were assigned to the VAV boxes because each sat in a room near a VAV tag. The correct owner was the AC/VRF indoor unit whose duct serves that room (confirmed by Siddhant and by duct trace).
- Why: the app links a device to the nearest tag. It never reads the schedules' "Area Served" / room column (only duct heaters have a served link, `_SERVES`/`Served` in src/bms/plan.py), and it does not combine plan symbols, schedule columns and duct routing. With no sequence of operation there was nothing else to go on.
- Rule (Siddhant): estimating means connecting the dots across inputs. A device belongs to the unit whose schedule says it serves the device's room; match on room number, name only as fallback; if two units claim the room, or none does, ask the estimator. Never fall back to the nearest tag.
- Related on the same job: VRF thermostat note on a detail sheet never linked to the VRF family; outside-air riser damper not traced to DOAS-1; VAV-2 duct CFM 420 vs schedule max 320 not flagged.
