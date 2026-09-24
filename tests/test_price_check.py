from estimator.price_sheet.check import price_check
from estimator.price_sheet.write import write_price_sheet


def test_price_check_on_26_0246(test_job, workup_template, price_book, sent_workup, tmp_path):
    sheet = write_price_sheet(test_job, workup_template, price_book, tmp_path / "26-0246 Price Sheet.xlsx")
    report = price_check(sheet, sent_workup, price_book, "26-0246")
    assert report.startswith("# Price check — 26-0246")
    assert "| Furnish BMS Server | 1 | $2,500.00 | $2,000.00 |" in report
    assert "| Furnish and Install Space Temperature / CO2 Sensor | 58 | $182.00 | $380.00 |" in report
    assert "## No price book match yet" in report
    assert "BACnet IP Router" in report
