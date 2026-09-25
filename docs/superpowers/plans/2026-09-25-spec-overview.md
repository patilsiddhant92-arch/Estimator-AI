# Spec Overview Tab Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Add a "Spec overview" tab to the Evidence Package. On one page it shows the estimator what the job says about:
- the controls platform
- protocols
- the network and front end
- electrical and conduit
- every manufacturer named, with who AME asks for a price
- what was searched for and not found

**Why:** The user liked the "Specs Overview" sheet the old tool (Grok) made, for example `D:\Estimation Assistant\Jobs\26-0363, Radical Media 6th Floor\04_Deliverable\26-0363_Specs_Overview.xlsx` (read-only). They want the same here, and will add to it as the app nears final.

**How it differs from Grok's version (binding):**
- **Nothing is guessed.** Grok wrote rows like "likely BACnet … CONFIRM" and "Belimo typical if not specified". Here each row either quotes the job word for word with where it was found, or says "Not found — ask the engineer". This follows design §9.1: recall is deterministic, and judgement comes later from the AI step.
- **Everything is data.** Topics, manufacturers and the AME vendor list are JSON files in `assets/reading_lists/`. The user adds to them, never to code.
- **Sources are short.** Show the first place found, then "(+N other)". The words go in their own column.

**Architecture:** A new module, `src/estimator/catalogue/overview.py`, reads the pages, sheets and sections the catalogue already has. It returns a `SpecOverview`, which `catalogue_job` stores on `Catalogue.overview`. `workbook.py` writes it as the second tab.

**Tech stack:** Python 3.13 (`.venv/Scripts/python.exe`), openpyxl, pytest. No new packages.

**Spec:** `docs/superpowers/specs/2026-09-24-estimator-ai-design.md` (§8 Evidence Package, §9.1 recall versus judgement).

## Global Constraints

- `D:\AME Estimation` and `D:\Estimation Assistant` are read-only: never write, build or run there.
- No job PDFs in the repo. Tests build `PageRecord` / `Sheet` / `SpecSection` objects directly, or use `tests/pdfs.py`.
- Every piece of text a user sees is plain English, with no short codes.
- Run text through `clean_text` (`estimator.catalogue.pdf`) before matching, as the rest of the catalogue does.
- Don't change the bid check (`qualify.py`, `manufacturers.json`). The user said not to spend time on it now.
- Don't push.

---

## Where to search (the "scope")

Each page gets a **strength**, which is also the order places are listed in. Where a page could have more than one, the first match wins.

1. **"Controls spec"**: a page inside a controls spec section (`SpecSection.controls`, from `first_page` to `last_page` of the same document).
2. **"Controls drawing"**: a drawing sheet whose `discipline == "Controls"`.
3. **"Mechanical drawing"**: a drawing sheet whose `discipline == "Mechanical"`.
4. **"Mechanical spec"**: a page inside a spec section whose number starts with `23`, `25` or `15`, and which is not a controls section.
5. **"Electrical drawing"**: a drawing sheet whose `discipline == "Electrical"`. It is searched only for topics marked `"electrical": true`, and only in a sentence that also has a controls word.

All other pages are not searched. That covers other spec divisions, architectural sheets and the rest.

The controls words are: `\bBMS\b`, `\bBAS\b`, `\bATC\b`, `\bDDC\b`, `building\s+(?:automation|management)`, `temperature\s+control(?!ler)`, `controls?\s+contractor`, `thermostats?`, `\bsensors?\b`, `control\s+(?:panel|wiring|device)s?`. Match them ignoring case.

**Sentence:** the text between sentence ends. A sentence ends at ". ", "; ", a line break followed by a list marker (`A.`, `1.`, `a.`, `(1)`) or a blank line. The quote is that sentence, whitespace squashed, cut to 300 characters around the match with "…" at the cut ends.

## The data files

### `assets/reading_lists/spec_overview.json` (create, content verbatim)

```json
{
  "about": "What the Spec overview tab looks for. Each topic is found or not found, never guessed. Add topics here, never in code. Patterns are matched ignoring case. electrical: true also searches electrical drawings, but only in a sentence with a controls word.",
  "topics": [
    {"section": "Protocols", "item": "BACnet/IP", "patterns": ["\\bBACnet\\s*/\\s*IP\\b", "\\bBACnet\\s+IP\\b", "\\bB/IP\\b"]},
    {"section": "Protocols", "item": "BACnet MS/TP", "patterns": ["\\bMS\\s*/\\s*TP\\b"]},
    {"section": "Protocols", "item": "BACnet (any mention)", "patterns": ["\\bBACnet\\b"]},
    {"section": "Protocols", "item": "Modbus", "patterns": ["\\bModbus\\b"]},
    {"section": "Protocols", "item": "LonWorks", "patterns": ["\\bLon\\s*Works\\b", "\\bLonTalk\\b"]},
    {"section": "Protocols", "item": "Open protocol stated", "patterns": ["\\bopen\\s+(?:protocol|system|architecture|standard)s?\\b", "\\bnon[- ]proprietary\\b", "\\binteroperab"]},
    {"section": "Protocols", "item": "Proprietary system stated", "patterns": ["(?<!non-)(?<!non )\\bproprietary\\b"]},
    {"section": "Protocols", "item": "BTL listing", "patterns": ["\\bBTL\\b", "BACnet\\s+Testing\\s+Laborator"]},
    {"section": "Network and front end", "item": "Operator workstation / front-end PC", "patterns": ["\\boperators?'?\\s+work\\s*stations?\\b", "\\bfront[- ]end\\b", "\\bwork\\s*stations?\\b"]},
    {"section": "Network and front end", "item": "Server", "patterns": ["\\bservers?\\b"]},
    {"section": "Network and front end", "item": "Supervisory / network controller (JACE)", "patterns": ["\\bJACE\\b", "\\bsupervisory\\s+(?:controller|device|engine)s?\\b", "\\bnetwork\\s+(?:area\\s+)?controllers?\\b", "\\bbuilding\\s+controllers?\\b", "\\bNAE\\b"]},
    {"section": "Network and front end", "item": "Graphics", "patterns": ["\\bgraphics?\\b", "\\bgraphical\\b"]},
    {"section": "Network and front end", "item": "UPS", "patterns": ["\\bUPS\\b", "\\buninterruptible\\s+power"]},
    {"section": "Network and front end", "item": "Network switches", "patterns": ["\\b(?:network|ethernet)\\s+switch(?:es)?\\b"]},
    {"section": "Network and front end", "item": "Remote access", "patterns": ["\\bremote\\s+access\\b", "\\bVPN\\b"]},
    {"section": "Network and front end", "item": "Tie-in to an existing system", "patterns": ["\\bexisting\\s+(?:BMS|BAS|EMS|DDC|front[- ]end|building\\s+(?:management|automation)\\s+system|temperature\\s+control)", "\\bextension\\s+of\\s+the\\s+existing\\b", "\\b(?:tie|connect|integrate)[sd]?\\s+(?:in\\s*)?(?:in)?to\\s+the\\s+existing\\b"]},
    {"section": "Network and front end", "item": "Cybersecurity / owner IT rules", "patterns": ["\\bcyber\\s*-?security\\b", "\\bowner'?s?\\s+IT\\b"]},
    {"section": "Electrical and conduit", "item": "EMT conduit", "patterns": ["\\bEMT\\b", "\\belectrical\\s+metallic\\s+tubing\\b"], "electrical": true},
    {"section": "Electrical and conduit", "item": "Wiring in conduit", "patterns": ["\\bin\\s+(?:a\\s+)?conduits?\\b", "\\bconduits?\\b"], "electrical": true},
    {"section": "Electrical and conduit", "item": "Plenum-rated cable", "patterns": ["\\bplenum[- ]?(?:rated|cable)\\b", "\\bCMP\\b"], "electrical": true},
    {"section": "Electrical and conduit", "item": "Power to controls panels", "patterns": ["\\b(?:120\\s*V|power)\\b[^.;]{0,60}\\b(?:BMS|BAS|DDC|ATC|control)\\s+panels?\\b"], "electrical": true},
    {"section": "Electrical and conduit", "item": "Work by the electrical contractor", "patterns": ["\\bby\\s+(?:the\\s+)?(?:electrical\\s+contractor|E\\.?C\\.?|Division\\s+26)\\b", "\\b(?:Division|Div\\.?)\\s+26\\b"], "electrical": true},
    {"section": "Electrical and conduit", "item": "Control transformers", "patterns": ["\\bcontrol\\s+transformers?\\b", "\\b24\\s*VAC?\\s+transformers?\\b", "\\b120\\s*V?\\s*/\\s*24\\s*V"], "electrical": true},
    {"section": "Electrical and conduit", "item": "Back boxes for thermostats and sensors", "patterns": ["\\bback\\s*-?box(?:es)?\\b", "\\bJ-?box(?:es)?\\b", "\\bjunction\\s+box(?:es)?\\b"], "electrical": true},
    {"section": "Electrical and conduit", "item": "Fire alarm / smoke detector interface", "patterns": ["\\bsmoke\\s+detectors?\\b", "\\bfire\\s+alarm\\b", "\\bduct\\s+detectors?\\b"], "electrical": true}
  ]
}
```

### `assets/reading_lists/overview_manufacturers.json` (create, content verbatim)

Names are matched **case-sensitively** in two forms: as written (Title Case), and in upper case. So "Carrier" and "CARRIER" match, but "carrier" doesn't. Every name is wrapped in `\b…\b`, and spaces inside a name match any whitespace. `not_before` / `not_after` hold words that must not come straight before or after the name, in either case form. `ask_if_missing: true` on a category puts it in "Searched but not found" when no maker in it is named.

```json
{
  "about": "Every manufacturer the Spec overview lists, by category. A maker is listed once, under its category here. Add makers here, never in code. Names match as written or in capitals; not_before / not_after stop false hits such as 'New York'.",
  "categories": [
    {"category": "Controls platform", "ask_if_missing": false, "makers": [
      {"name": "Honeywell", "names": ["Honeywell"]},
      {"name": "Johnson Controls", "names": ["Johnson Controls", "JCI"]},
      {"name": "Tridium / Niagara", "names": ["Tridium", "Niagara"], "not_after": ["Falls"]},
      {"name": "Siemens", "names": ["Siemens"]},
      {"name": "Automated Logic", "names": ["Automated Logic", "ALC"]},
      {"name": "Distech Controls", "names": ["Distech"]},
      {"name": "Delta Controls", "names": ["Delta Controls"]},
      {"name": "Alerton", "names": ["Alerton"]},
      {"name": "KMC Controls", "names": ["KMC"]},
      {"name": "Schneider Electric", "names": ["Schneider", "Andover", "EcoStruxure", "Altivar"]},
      {"name": "Rockwell Automation (Allen-Bradley)", "names": ["Rockwell", "Allen-Bradley", "Allen Bradley"]},
      {"name": "Reliable Controls", "names": ["Reliable Controls"]}
    ]},
    {"category": "Sensors and transmitters", "ask_if_missing": true, "makers": [
      {"name": "ACI", "names": ["ACI", "Automation Components"]},
      {"name": "BAPI", "names": ["BAPI"]},
      {"name": "Vaisala", "names": ["Vaisala"]},
      {"name": "Setra", "names": ["Setra"]},
      {"name": "Veris", "names": ["Veris"]},
      {"name": "Dwyer", "names": ["Dwyer"]},
      {"name": "Kele", "names": ["Kele"]},
      {"name": "Mamac", "names": ["Mamac"]},
      {"name": "Greystone", "names": ["Greystone"]},
      {"name": "Senva", "names": ["Senva"]}
    ]},
    {"category": "Actuators and dampers", "ask_if_missing": true, "makers": [
      {"name": "Belimo", "names": ["Belimo"]},
      {"name": "Ruskin", "names": ["Ruskin"]},
      {"name": "Greenheck", "names": ["Greenheck"]},
      {"name": "Nailor", "names": ["Nailor"]}
    ]},
    {"category": "Control valves", "ask_if_missing": true, "makers": [
      {"name": "Bray", "names": ["Bray"]},
      {"name": "Keystone", "names": ["Keystone"]},
      {"name": "Fisher", "names": ["Fisher"]},
      {"name": "Griswold", "names": ["Griswold"]},
      {"name": "Flow Design (FDI)", "names": ["Flow Design"]}
    ]},
    {"category": "Airflow measuring", "ask_if_missing": true, "makers": [
      {"name": "Ebtron", "names": ["Ebtron", "EBTRON"]},
      {"name": "Air Monitor", "names": ["Air Monitor"]},
      {"name": "Paragon Controls", "names": ["Paragon Controls"]}
    ]},
    {"category": "Flow meters", "ask_if_missing": true, "makers": [
      {"name": "Onicon", "names": ["Onicon", "ONICON"]},
      {"name": "Flexim", "names": ["Flexim", "FLEXIM"]},
      {"name": "Dynasonic", "names": ["Dynasonic", "DynaSonic"]},
      {"name": "Badger Meter", "names": ["Badger Meter"]}
    ]},
    {"category": "Pressure and differential pressure", "ask_if_missing": false, "makers": [
      {"name": "Rosemount", "names": ["Rosemount"]}
    ]},
    {"category": "Gas detection", "ask_if_missing": true, "makers": [
      {"name": "MSA", "names": ["MSA"]},
      {"name": "Macurco", "names": ["Macurco"]},
      {"name": "Toxalert", "names": ["Toxalert"]},
      {"name": "Honeywell Analytics", "names": ["Honeywell Analytics"]}
    ]},
    {"category": "Variable frequency drives", "ask_if_missing": true, "makers": [
      {"name": "ABB", "names": ["ABB"]},
      {"name": "Danfoss", "names": ["Danfoss"]},
      {"name": "Yaskawa", "names": ["Yaskawa"]},
      {"name": "Toshiba", "names": ["Toshiba"]}
    ]},
    {"category": "Relays and current switches", "ask_if_missing": false, "makers": [
      {"name": "Functional Devices (RIB)", "names": ["Functional Devices", "RIB"]}
    ]},
    {"category": "Terminal units (VAV / fan-powered boxes)", "ask_if_missing": false, "makers": [
      {"name": "Titus", "names": ["Titus"]},
      {"name": "Price Industries", "names": ["Price Industries", "PRICE"], "not_before": ["UNIT", "CONTRACT", "BID", "LUMP SUM"], "not_after": ["LIST", "BREAKDOWN", "SCHEDULE"]},
      {"name": "Anemostat", "names": ["Anemostat"]},
      {"name": "Krueger", "names": ["Krueger"]},
      {"name": "Envirotec", "names": ["Envirotec", "Envirotech"]}
    ]},
    {"category": "Equipment makers (units with their own controls)", "ask_if_missing": false, "makers": [
      {"name": "Trane", "names": ["Trane"]},
      {"name": "Carrier", "names": ["Carrier"], "not_after": ["Sense", "SENSE"]},
      {"name": "York", "names": ["York"], "not_before": ["New", "NEW"]},
      {"name": "Daikin", "names": ["Daikin"]},
      {"name": "Mitsubishi", "names": ["Mitsubishi"]},
      {"name": "LG", "names": ["LG"]},
      {"name": "Lennox", "names": ["Lennox"]},
      {"name": "AAON", "names": ["AAON"]},
      {"name": "McQuay", "names": ["McQuay"]},
      {"name": "Liebert / Vertiv", "names": ["Liebert", "Vertiv"]},
      {"name": "Above Air", "names": ["Above Air"]},
      {"name": "Islandaire", "names": ["Islandaire"]},
      {"name": "PoweredAire", "names": ["PoweredAire", "Powered Aire"]},
      {"name": "Armstrong", "names": ["Armstrong"]},
      {"name": "Bell & Gossett", "names": ["Bell & Gossett", "Bell and Gossett", "B&G"]},
      {"name": "Taco", "names": ["Taco"]},
      {"name": "Grundfos", "names": ["Grundfos"]},
      {"name": "Aerco", "names": ["Aerco", "AERCO"]},
      {"name": "Lochinvar", "names": ["Lochinvar"]},
      {"name": "Cleaver-Brooks", "names": ["Cleaver-Brooks", "Cleaver Brooks"]}
    ]}
  ]
}
```

### `assets/reading_lists/ame_vendors.json` (create, content verbatim)

This is the user's own quote-source list, copied from the old tool's `ame_vendor_sources.py`. A maker "AME quotes" when its `name` from the overview list, or any of its `names`, equals (ignoring case) one of a vendor's `makers`. A vendor with `products_match` and no makers is added for a category whose name contains one of those words (ignoring case).

```json
{
  "about": "Who AME asks for a price, by manufacturer. The estimator's own list. Edit here, never in code.",
  "email_draft": "Could you please provide the pricing for the {maker} - {category}?\n\nPlease include unit pricing, lead time, and any applicable factory controls / BACnet notes.\n\nThank you.",
  "vendors": [
    {"vendor": "Mechanical Technologies", "products": "VFDs, Airflow Stations, Gas Detection", "makers": ["ABB", "Ruskin", "MSA"], "contact": "Jamie Scott jscott@mthvac.com; Larry Scholl lscholl@mthvac.com"},
    {"vendor": "AWACP", "products": "Airflow Stations and Gas Detection", "makers": [], "products_match": ["Airflow", "Gas detection"], "contact": "Joel Adelantar joeladelantar@awacp.com (732) 689-0387"},
    {"vendor": "Broudy Precision", "products": "General Controls", "makers": ["Honeywell", "JCI", "Johnson Controls", "Belimo", "ACI", "Vaisala"], "contact": "jchandler@broudyprecision.com; tsanroman@broudyprecision.com"},
    {"vendor": "Universal Supply Group", "products": "General Controls", "makers": ["Honeywell"], "contact": "Rory Fitzsimons rfitzsimons@usginc.com"},
    {"vendor": "Building Controls & Solutions", "products": "General Controls", "makers": ["Honeywell"], "contact": "AJ Hudak AJ.Hudak@building-controls.com"},
    {"vendor": "Accuspec", "products": "Air Valves, Flow Meters", "makers": ["Accutrol", "Onicon"], "contact": "Bill Theel btheel@accuspecinc.com; Sam Hall shall@accuspecinc.com"},
    {"vendor": "JT Lynne", "products": "Control Valves", "makers": ["Bray"], "contact": "Steve Valahovic steve.valahovic@jtlynnefe.com"},
    {"vendor": "Control Associates", "products": "Control Valves, DP", "makers": ["Keystone", "Fisher", "Rosemount"], "contact": "Chris Sneath csneath@control-associates.com"},
    {"vendor": "Technical Air", "products": "Airflow Stations", "makers": ["Ebtron"], "contact": "Dave Painter dpainter@technicalair.com"},
    {"vendor": "Pro Tech Solutions", "products": "DP / Pressure, Meters", "makers": ["Rosemount", "Dynasonic"], "contact": "Steve Pedraza spedraza@control-associates.com"},
    {"vendor": "Technical Devices, Inc", "products": "Flow Meters", "makers": ["Flexim"], "contact": "Dave Painter dpainter@technicalair.com"},
    {"vendor": "Engineered Air Solutions", "products": "Gas Detection", "makers": ["Macurco"], "contact": "B Sullivan bsullivan@engineeredairsolutions.com; Kevin Fitzpatrick kfitzpatrick@engineeredairsolutions.com; jthaker@engineeredairsolutions.com"},
    {"vendor": "NY Thermal Systems", "products": "Gas Detection", "makers": ["Toxalert"], "contact": "johnc@nythermalsystems.com"}
  ]
}
```

Accutrol isn't in the overview list. Add `{"name": "Accutrol", "names": ["Accutrol"]}` to a category `"Lab air valves"` with `ask_if_missing: false`.

---

### Task 1: The overview module

**Files:**
- Create: `assets/reading_lists/spec_overview.json`, `assets/reading_lists/overview_manufacturers.json` and `assets/reading_lists/ame_vendors.json`, with the content above.
- Create: `src/estimator/catalogue/overview.py`
- Test: `tests/test_overview.py`

**Interfaces (produces):**

```python
@dataclass(frozen=True)
class Place:
    document: str          # Document.relative
    page: int
    sheet: str | None      # the sheet number, when the page is a drawing sheet
    section: str | None    # the spec section number, when inside one
    strength: str          # "Controls spec" | "Controls drawing" | "Mechanical drawing" | "Mechanical spec" | "Electrical drawing"

@dataclass(frozen=True)
class Found:
    section: str           # "Protocols" | "Network and front end" | "Electrical and conduit"
    item: str
    places: tuple[Place, ...]   # strongest first, then document order; empty = not found
    quote: str                  # the sentence at the first place, word for word; "" when not found

@dataclass(frozen=True)
class MakerRow:
    category: str
    maker: str                  # the list's canonical "name"
    places: tuple[Place, ...]
    quote: str
    terms: str                  # "Basis of design" / "Or approved equal" / "No substitutions" / "" — from the quoted sentence
    ame_quotes: bool
    vendors: tuple[str, ...]    # "Broudy Precision — jchandler@…; tsanroman@…", one per matching vendor
    email_draft: str            # the template filled in, only when ame_quotes; else ""

@dataclass(frozen=True)
class SpecOverview:
    topics: tuple[Found, ...]       # every topic in spec_overview.json order, found or not
    makers: tuple[MakerRow, ...]    # only makers found; sorted by category order in the list, then maker name
    not_found: tuple[str, ...]      # plain lines: each topic not found, then each ask_if_missing category with no maker

def build_overview(pages, sheets, sections) -> SpecOverview
def short_place(places: tuple[Place, ...]) -> str
    # "M-601.00 (Marked_Mech.pdf, page 10)  (+4 other)"
    # "Specs.pdf · 23 09 23 · page 124  (+2 other)"
    # "" when empty. Uses the file's base name.
```

`not_found` wording:
- A topic: `"<item> — not found in the controls spec or the mechanical and controls drawings; ask the engineer if it matters"`
- A category: `"No <category, lower case> maker named — ask the engineer if the job needs one"`

`terms` comes from the quoted sentence. Check in this order and take the first that matches:
- `basis\s+of\s+design` → "Basis of design"
- `no\s+substitution` → "No substitutions"
- `or\s+(?:approved\s+)?equal` → "Or approved equal"
- otherwise ""

Each maker gets one row, at the strongest place first. A place is a unique (document, page). Collapse repeats on the same page.

**Tests (write first). Each builds a few `PageRecord` / `Sheet` / `SpecSection` objects by hand:**
1. "Provide BACnet MS/TP to each VAV controller." on a page inside a 23 09 23 section. The result is BACnet MS/TP found with strength "Controls spec", the quote is that sentence, and "BACnet (any mention)" is found too.
2. The same sentence on a page outside any section, not a drawing sheet. It is not found, and the not-found line appears for it.
3. "All BMS wiring shall be in EMT conduit." on an Electrical drawing sheet. EMT conduit is found with strength "Electrical drawing". "Provide EMT for all feeders." on the same sheet is not found, because the sentence has no controls word.
4. "Carrier Sense Multiple Access" on a controls page gives no Carrier row. "CARRIER 48TC ROOFTOP UNIT" on a Mechanical sheet gives a Carrier row.
5. "New York, NY 10001" gives no York row. "YORK YCAL CHILLER" gives one.
6. "UNIT PRICE" gives no Price row. "PRICE SDV VAV BOX" gives one.
7. "Actuators shall be Belimo or approved equal." in a controls section gives a Belimo row with `ame_quotes=True` and terms "Or approved equal". The vendors include "Broudy Precision — jchandler@broudyprecision.com; tsanroman@broudyprecision.com". The email draft starts "Could you please provide the pricing for the Belimo - Actuators and dampers?".
8. "Airflow stations shall be Ebtron." gives an Ebtron row whose vendors include Technical Air and AWACP (products match "Airflow").
9. "Trane" on a Mechanical sheet gives `ame_quotes=False`, no vendors and an empty draft.
10. The same maker on a Mechanical spec page (p.5) and a Controls spec page (p.40). Its places list the Controls spec first. `short_place` gives "Specs.pdf · 23 09 23 · page 40  (+1 other)".
11. A job with no gas-detection maker has "No gas detection maker named — ask the engineer if the job needs one" in `not_found`.
12. Page text with `\x04` in place of spaces ("BACnet\x04MS/TP") is still found, because it goes through `clean_text`.

- [ ] Write the tests, run them and watch them fail. Write `overview.py` and run the tests until they pass. Run the full suite.
- [ ] Commit: `feat: the Spec overview reads protocols, network, conduit and every manufacturer named`

### Task 2: The tab, the summary line and the Catalogue

**Files:**
- Modify: `src/estimator/catalogue/job.py`. Add `overview: SpecOverview` to `Catalogue`, as the last field with a default factory giving an empty `SpecOverview` so existing constructors keep working. Build it in `catalogue_job` with `build_overview(pages, sheets, sections)`. Add one line to `summary_lines`, placed after the Bid check lines: `"Spec overview: {n} manufacturers named ({k} AME gets prices for); protocols: {found protocol items, comma-separated, or 'none stated'}."`
- Modify: `src/estimator/evidence/workbook.py`. The tabs are `("Bid check", "Spec overview", "Flags", "Documents", "Pages", "Sheets", "Spec sections", "Equipment tags")`.
- Test: `tests/test_evidence.py` and `tests/test_catalogue_job.py`

**The Spec overview tab, top to bottom:**
1. **Title:** `"Spec overview — <job name>"` (bold, 14pt).
2. **Intro line:** "What the job says, found word for word. Nothing here is guessed: a row either quotes the job or says it wasn't found."
3. **Heading "1. Controls platform"** (bold, heading fill), with the rows "Bid check", "Why", "Other controls manufacturers named" and "Controls sections in the specs", taken from `catalogue.bid` and `catalogue.sections` as on the Bid check tab. The last row is "See the Bid check tab for every passage."
4. **Headings "2. Protocols", "3. Network and front end" and "4. Electrical and conduit".** The columns are: What | Found? ("Yes" / "Not found") | Where (`short_place`) | How strong (the first place's strength) | What the job says (word for word).
   - A "Yes" cell has a green fill (C6EFCE). A "Not found" cell has none.
5. **Heading "5. Manufacturers named on this job".** The columns are: Category | Manufacturer | AME gets prices for it? | Where | How strong | What the job says (word for word) | Basis of design / or equal | Ask for a price from | Email draft.
   - The manufacturer cell is always bold. It gets a green fill only when AME quotes it.
   - For AME makers, "Ask for a price from" is the vendors joined with a line break. Otherwise it reads "Not on AME's list — the estimator decides".
6. **Heading "6. Searched for but not found"**, then one line per `not_found` entry.

Wrap text in the quote and draft columns. Use widths similar to the other tabs.

**Tests:**
- The sheet names now include "Spec overview" as the second tab. Update the existing TABS test.
- A catalogue fixture with a controls-section page reading "Actuators shall be Belimo or approved equal. Provide BACnet MS/TP." writes a tab with:
  - a "BACnet MS/TP" row showing "Yes"
  - a Belimo row showing "Yes" under "AME gets prices for it?"
  - a Modbus row showing "Not found"
  - "Modbus — not found …" in section 6
- `summary_lines` has the Spec overview line.

- [ ] Write the tests, then the code, then run the full suite.
- [ ] Commit: `feat: the Evidence Package opens with the bid check, then the Spec overview`

### Task 3: The Learn check, and cutting noise on real jobs

**Files:**
- Modify: `tools/learn_check.py`. Add a second table to `out/learn/learn-check.md` and to the console output, headed "Spec overview". Its columns are Job | Manufacturers named | AME gets prices for | Protocols found | Not found (count).
- Modify: the three JSON reading lists, only where a real job shows a false hit.

**Steps:**
- [ ] Run `.venv/Scripts/python.exe tools/learn_check.py`. It uses the page cache, so it takes a few minutes. It must still exit 0, and the bid-check table must be unchanged.
- [ ] Open the Spec overview tab of every one of the ten Evidence Packages in `out/learn/*/`. For each manufacturer row, and each "Yes" topic, check that the quote really names that maker or topic in the sense meant. Look out for:
  - a place name (New York, Niagara Falls)
  - an ordinary word ("carrier", "price", "graphics" in an architectural note)
  - a company-suffix collision
  - a server that isn't the BMS server
  - "front end" meaning something else
- [ ] Fix each false hit **in the JSON reading lists**, with a `not_before` / `not_after` word or a tighter pattern. Add a test for each fix as a synthetic sentence in `tests/test_overview.py`. Never special-case a job in code.
- [ ] In `tests/data/learn_expectations.json`, add `"overview_makers_include": [...]` for 26-0246 and 26-0356. Use two or three makers each that you confirmed by hand in the quote. Make `learn_check.misses` report a missing one. Add a test in `tests/test_learn_check.py`.
- [ ] Run the full suite and the Learn check again (exit 0).
- [ ] Commit: `feat: the Learn check shows each job's Spec overview; false manufacturer hits cut`
- [ ] **Report** (`.superpowers/sdd/2026-09-25-spec-overview/report.md`):
  - the commits and test totals
  - the Spec overview table
  - every false hit you found and how the list now avoids it
  - any hit you left in because it's arguable, with the quote

## Self-review

Every section in Grok's layout has a home here:
- "BMS platform" → section 1
- "Protocols" → section 2
- "Network / FE" → section 3
- "Conduit" → section 4
- "End-device manufacturers" plus the vendor and email columns → section 5
- "Common categories to check" → the `ask_if_missing` lines in section 6
- "Searched but not found" → section 6

Grok's "Confidence" column becomes "How strong", which names the kind of place the quote came from. That is recall, not judgement.
