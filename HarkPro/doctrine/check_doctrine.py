#!/usr/bin/env python3
"""Validate HarkPro/doctrine/lines.json (and that rulings.md is numbered).

Checks
  1. Schema: top-level keys, every family's required fields and types, every line's required fields,
     verb / control_type enums, owner fields present, required is a bool.
  2. Every line has a non-empty source (and every family has source_refs).
  3. No duplicate line ids and no duplicate family ids; ids start with their family id.
  4. parent / alt_group / variant references resolve inside the family.
  5. Optional (--docx PATH, needs python-docx): every line marked as exact template wording, with a single
     "Master Template ¶n" source and nothing redacted, matches paragraph n of the docx word for word
     (whitespace collapsed).
  6. Optional (--price-book PATH, needs openpyxl): every price_items / price_item name exists in the
     price book's item column (Parts Pricing col A, BMS-DDC-Panels col A).
  7. rulings.md: rulings numbered R1.. without gaps or duplicates; each ruling has a date or PENDING.

Usage:  python check_doctrine.py [--docx "Brain/Master Template.docx"] [--price-book "assets/price_book/AME Std Pricing Spreadsheet.xlsx"]
Exit code 0 when every check passes, 1 otherwise.
"""
import argparse, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
VERBS = {"furnish_install", "furnish", "furnish_wire", "install_wire", "install", "wire", "tie_in", "integration", "note"}
CONTROL = {"field_ddc", "packaged", "integration", "mixed"}
FAM_KEYS = {"id": str, "family": str, "aliases": list, "control_type": str, "lines": list, "client_notes": list,
            "tech_hours": dict, "price_items": list, "source_refs": list}
LINE_KEYS = {"id": str, "text": str, "verb": str, "applies_when": str, "required": bool, "source": str}
OWNER_KEYS = ("owner_furnish", "owner_install", "owner_wire")


def norm(s):
    return re.sub(r"\s+", " ", s.replace("\u00a0", " ")).strip()


def check(lines_path, docx_path=None, price_path=None, rulings_path=None):
    errs, warns = [], []
    d = json.load(open(lines_path, encoding="utf-8"))
    for k in ("about", "families", "format"):
        if k not in d:
            errs.append(f"top level: missing '{k}'")
    fam_ids, line_ids = set(), set()
    exact_checks = []
    price_refs = set()
    for fi, f in enumerate(d.get("families", [])):
        where = f"family[{fi}] {f.get('id')}"
        for k, t in FAM_KEYS.items():
            if k not in f:
                errs.append(f"{where}: missing '{k}'")
            elif not isinstance(f[k], t):
                errs.append(f"{where}: '{k}' must be {t.__name__}")
        if "exception_form" not in f:
            errs.append(f"{where}: missing 'exception_form' (null allowed)")
        if f.get("control_type") not in CONTROL:
            errs.append(f"{where}: control_type {f.get('control_type')!r} not in {sorted(CONTROL)}")
        if not f.get("source_refs"):
            errs.append(f"{where}: empty source_refs")
        if not f.get("aliases"):
            errs.append(f"{where}: empty aliases")
        th = f.get("tech_hours", {})
        for k in ("rule", "hours", "per"):
            if k not in th:
                errs.append(f"{where}: tech_hours missing '{k}'")
        if f.get("id") in fam_ids:
            errs.append(f"{where}: duplicate family id")
        fam_ids.add(f.get("id"))
        price_refs.update(f.get("price_items", []))
        ids_here = {l.get("id") for l in f.get("lines", [])}
        variants = set((f.get("variants") or {}).keys())
        alt_counts = {}
        if not f.get("lines"):
            errs.append(f"{where}: no lines")
        for li, l in enumerate(f.get("lines", [])):
            lw = f"{where} line[{li}] {l.get('id')}"
            for k, t in LINE_KEYS.items():
                if k not in l:
                    errs.append(f"{lw}: missing '{k}'")
                elif not isinstance(l[k], t):
                    errs.append(f"{lw}: '{k}' must be {t.__name__}")
            for k in OWNER_KEYS:
                if k not in l:
                    errs.append(f"{lw}: missing '{k}'")
            if l.get("verb") not in VERBS:
                errs.append(f"{lw}: verb {l.get('verb')!r} not in enum")
            if not str(l.get("source", "")).strip():
                errs.append(f"{lw}: empty source")
            if not str(l.get("text", "")).strip():
                errs.append(f"{lw}: empty text")
            if not str(l.get("applies_when", "")).strip():
                errs.append(f"{lw}: empty applies_when")
            if l.get("id") in line_ids:
                errs.append(f"{lw}: duplicate line id")
            line_ids.add(l.get("id"))
            if not str(l.get("id", "")).startswith(f"{f.get('id')}."):
                errs.append(f"{lw}: id does not start with family id")
            if "parent" in l and l["parent"] not in ids_here:
                errs.append(f"{lw}: parent {l['parent']} not in family")
            if "variant" in l and variants and l["variant"] not in variants:
                errs.append(f"{lw}: variant {l['variant']} not declared in family variants")
            if "alt_group" in l:
                alt_counts[l["alt_group"]] = alt_counts.get(l["alt_group"], 0) + 1
            if l.get("price_item"):
                price_refs.add(l["price_item"])
            if len(l.get("text", "")) > 160:
                warns.append(f"{lw}: text longer than 160 characters (rules.md line form)")
            m = re.fullmatch(r"Master Template ¶(\d+)", l.get("source", ""))
            if m and l.get("template_exact", True) and not l.get("redacted"):
                exact_checks.append((lw, int(m.group(1)), l["text"], bool(l.get("trimmed"))))
        for g, n in alt_counts.items():
            if n < 2:
                warns.append(f"{where}: alt_group {g} has only {n} line")

    if docx_path:
        try:
            import docx  # noqa
            from docx.oxml.ns import qn
            doc = docx.Document(docx_path)
            paras, i = {}, 0
            for child in doc.element.body.iterchildren():
                if child.tag.endswith('}p'):
                    i += 1
                    paras[i] = norm(''.join(x.text or '' for x in child.iter(qn('w:t'))))
            bad = 0
            for lw, n, text, trimmed in exact_checks:
                p = paras.get(n, "")
                # a template paragraph may carry a trailing orange hint after the line (e.g. "; applicable");
                # a 'trimmed' line need only appear inside its paragraph
                ok = norm(text) == p or p.startswith(norm(text)) or (trimmed and norm(text) in p)
                if not ok:
                    bad += 1
                    errs.append(f"{lw}: text differs from template ¶{n}: {p!r}")
            print(f"docx wording check: {len(exact_checks)} exact lines compared, {bad} mismatches")
        except ImportError:
            warns.append("python-docx not available: wording check skipped")

    if price_path:
        try:
            import openpyxl
            wb = openpyxl.load_workbook(price_path, data_only=True)
            names = set()
            for ws in wb:
                for row in ws.iter_rows(values_only=True):
                    for c in row[:2]:
                        if isinstance(c, str):
                            names.add(c)
            missing = sorted(p for p in price_refs if p not in names)
            for p in missing:
                errs.append(f"price item not in price book: {p!r}")
            print(f"price book check: {len(price_refs)} item names referenced, {len(missing)} missing")
        except ImportError:
            warns.append("openpyxl not available: price book check skipped")

    rp = rulings_path or os.path.join(os.path.dirname(lines_path), "rulings.md")
    if os.path.exists(rp):
        txt = open(rp, encoding="utf-8").read()
        nums = [int(x) for x in re.findall(r"^\s*(?:###\s*)?R(\d+)[a-z]?\b[.:]?", txt, re.M) if x]
        heads = re.findall(r"^### (R\d+[a-z]?)\b(.*)$", txt, re.M)
        seen = set()
        for h, rest in heads:
            if h in seen:
                errs.append(f"rulings.md: duplicate {h}")
            seen.add(h)
        base = sorted({int(re.match(r"R(\d+)", h).group(1)) for h, _ in heads})
        if base and base != list(range(1, base[-1] + 1)):
            errs.append(f"rulings.md: numbering has gaps: {base}")
        for h, rest in heads:
            body = txt.split(f"### {h}", 1)[1].split("\n### ", 1)[0]
            if not (re.search(r"20\d\d-\d\d-\d\d", rest + body) or "PENDING estimator" in rest + body):
                errs.append(f"rulings.md: {h} has no date and is not PENDING")
        print(f"rulings.md: {len(heads)} rulings")
    else:
        warns.append("rulings.md not found")

    nl = sum(len(f.get('lines', [])) for f in d.get('families', []))
    print(f"lines.json: {len(fam_ids)} families, {nl} lines, {len(line_ids)} unique ids")
    for w in warns:
        print("WARN", w)
    for e in errs:
        print("FAIL", e)
    print("OK" if not errs else f"{len(errs)} error(s)")
    return 0 if not errs else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lines", default=os.path.join(HERE, "lines.json"))
    ap.add_argument("--docx")
    ap.add_argument("--price-book")
    ap.add_argument("--rulings")
    a = ap.parse_args()
    sys.exit(check(a.lines, a.docx, a.price_book, a.rulings))
