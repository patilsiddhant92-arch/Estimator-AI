"""Put a sent proposal and a generated one side by side, page by page, for checking by eye.

Also opens the generated price sheet in Excel, lets it recalculate, and prints
the totals — proving the template's formulas still work, and catching any
formula that now shows an error.

Needs Microsoft Word and Excel. Windows only.

    .venv/Scripts/python.exe tools/side_by_side.py SENT.docx GENERATED.docx --sheet GENERATED.xlsx --out FOLDER
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

_GAP = 20


def compose(left: Path, right: Path, out: Path) -> Path:
    a, b = Image.open(left).convert("RGB"), Image.open(right).convert("RGB")
    canvas = Image.new("RGB", (a.width + _GAP + b.width, max(a.height, b.height)), "white")
    canvas.paste(a, (0, 0))
    canvas.paste(b, (a.width + _GAP, 0))
    canvas.save(out)
    return out


def _powershell(script: str) -> str:
    done = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                          capture_output=True, text=True, timeout=600)
    if done.returncode != 0:
        raise RuntimeError(done.stderr.strip() or done.stdout.strip())
    return done.stdout


def _to_pdf(documents: list[Path]) -> None:
    pairs = ",".join(f"@('{d}','{d.with_suffix('.pdf')}')" for d in documents)
    _powershell(f"""
$ErrorActionPreference = 'Stop'
$word = New-Object -ComObject Word.Application
$word.Visible = $false; $word.DisplayAlerts = 0
try {{
  foreach ($pair in @({pairs})) {{
    $doc = $word.Documents.Open($pair[0], $false, $true, $false)
    $doc.SaveAs2($pair[1], 17)
    $doc.Close(0)
  }}
}} finally {{ $word.Quit() }}
""")


def _render(pdf: Path, folder: Path, stem: str) -> list[Path]:
    import fitz
    pages = []
    with fitz.open(str(pdf)) as document:
        for number, page in enumerate(document, 1):
            path = folder / f"{stem}-{number:02d}.png"
            page.get_pixmap(dpi=70).save(str(path))
            pages.append(path)
    return pages


def _excel_check(workbooks: list[Path]) -> list[list[dict]]:
    """Open each workbook in Excel, recalculate, and report each sheet's error cells and totals."""
    paths = ",".join(f"'{w}'" for w in workbooks)
    out = _powershell(f"""
$ErrorActionPreference = 'Stop'
$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false; $excel.DisplayAlerts = $false
$all = @()
try {{
  foreach ($path in @({paths})) {{
    $wb = $excel.Workbooks.Open($path, 0, $true)
    $excel.CalculateFull()
    $sheets = @()
    foreach ($ws in $wb.Worksheets) {{
      $errors = ''
      try {{ $errors = $ws.UsedRange.SpecialCells(-4123, 16).Address(0, 0) }} catch {{ }}
      $row = @{{ name = $ws.Name; errors = $errors }}
      if ($ws.Name -ne 'Summary') {{
        $row.hours = $ws.Range('B401').Value2; $row.material = $ws.Range('F401').Value2; $row.sell = $ws.Range('E436').Value2
      }}
      $sheets += $row
    }}
    $wb.Close($false)
    $all += ,$sheets
  }}
}} finally {{ $excel.Quit() }}
ConvertTo-Json -InputObject $all -Depth 4
""")
    return json.loads(out)


def _cells(address: str) -> set[str]:
    """Expand an Excel address like "E437,L24:L30" into single cells."""
    from openpyxl.utils import get_column_letter, range_boundaries
    cells = set()
    for area in filter(None, (address or "").split(",")):
        min_col, min_row, max_col, max_row = range_boundaries(area)
        for col in range(min_col, max_col + 1):
            for row in range(min_row, max_row + 1):
                cells.add(f"{get_column_letter(col)}{row}")
    return cells


_WORKUP_TEMPLATE = Path(__file__).resolve().parents[1] / "assets" / "templates" / "PriceWorkup_Template - 12-21-25.xlsx"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("sent", type=Path)
    parser.add_argument("generated", type=Path)
    parser.add_argument("--sheet", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workup-template", type=Path, default=_WORKUP_TEMPLATE)
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)

    work = Path(tempfile.mkdtemp(prefix="estimator-"))
    sent, generated = work / "sent.docx", work / "generated.docx"
    shutil.copy2(args.sent, sent)
    shutil.copy2(args.generated, generated)
    _to_pdf([sent, generated])
    left, right = _render(sent.with_suffix(".pdf"), work, "sent"), _render(generated.with_suffix(".pdf"), work, "generated")
    blank = work / "blank.png"
    Image.new("RGB", Image.open(left[0]).size, "white").save(blank)
    for number in range(max(len(left), len(right))):
        compose(left[number] if number < len(left) else blank,
                right[number] if number < len(right) else blank,
                args.out / f"page-{number + 1:02d}.png")
    print(f"{max(len(left), len(right))} pages written to {args.out} — sent on the left, generated on the right.")
    print(f"The sent proposal has {len(left)} pages; the generated one has {len(right)}.")
    print("The sent proposal's cover shows today's date: its date field updates whenever Word opens it. "
          "The generated one shows the date it was issued.")

    # Unused price sheets divide by zero in the template's own margin formulas, so compare
    # with the empty template and report only errors the template did not already have.
    template, sheet = work / "template.xlsx", work / "sheet.xlsx"
    shutil.copy2(args.workup_template, template)
    shutil.copy2(args.sheet, sheet)
    before, after = _excel_check([template, sheet])
    new_errors = []
    for empty, filled in zip(before, after):
        fresh = sorted(_cells(filled["errors"]) - _cells(empty["errors"]))
        if fresh:
            new_errors.append(f"{filled['name']}: {', '.join(fresh)}")
    for row in after:
        if row["name"] != "Summary" and row.get("hours"):
            print(f"{row['name']}: {row['hours']:g} tech hours, material ${row['material']:,.2f}, "
                  f"sell price ${row['sell']:,.2f}")
    if new_errors:
        print("Excel shows formula errors the empty template doesn't have:")
        for line in new_errors:
            print(f"    {line}")
        return 1
    print("Excel recalculated every formula, and none shows an error the template doesn't already have.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
