import re

from estimator.price_sheet.check import price_check
from estimator.price_sheet.write import write_price_sheet
from estimator.scope import Run


def test_price_check_on_26_0246(test_job, workup_template, price_book, sent_workup, tmp_path):
    sheet = write_price_sheet(test_job, workup_template, price_book, tmp_path / "26-0246 Price Sheet.xlsx")
    report = price_check(sheet, sent_workup, price_book, "26-0246")
    assert report.startswith("# Price check — 26-0246")
    assert "| Furnish BMS Server | 1 | $2,500.00 | $2,000.00 |" in report
    assert "| Furnish and Install Space Temperature / CO2 Sensor | 58 | $182.00 | $380.00 |" in report
    assert "## No price book match yet" in report
    assert "BACnet IP Router" in report


def test_a_bar_in_a_line_does_not_break_the_table(small_job, workup_template, price_book, tmp_path):
    """A "|" in a line (some block headers have one) must not be read as a table column break."""
    item = small_job.front_end.items[1]
    assert item.text == "Furnish BMS Server"                 # priced by the book, until we change its text below
    changed = item.model_copy(update={"runs": (Run(text="Furnish BMS Server | Backup", bold=True),)})
    items = list(small_job.front_end.items)
    items[1] = changed
    front_end = small_job.front_end.model_copy(update={"items": tuple(items)})
    job = small_job.model_copy(update={"front_end": front_end})

    sheet = write_price_sheet(job, workup_template, price_book, tmp_path / "bar.xlsx")
    report = price_check(sheet, sheet, price_book, "Bar test")   # compared against itself: simplest and still real

    assert "Furnish BMS Server \\| Backup" in report

    tables, current = [], []
    for raw in report.splitlines():
        if raw.startswith("|"):
            current.append(raw)
        elif current:
            tables.append(current)
            current = []
    if current:
        tables.append(current)
    assert tables

    def unescaped_pipes(row: str) -> int:
        return len(re.findall(r"(?<!\\)\|", row))

    for table in tables:
        header_pipes = unescaped_pipes(table[0])
        for row in table:
            assert unescaped_pipes(row) == header_pipes, row
