import pytest

from estimator.text import squash, strip_list_marker


def test_squash_collapses_every_kind_of_space():
    assert squash("  Furnish\xa0\xa0and\tInstall  UPS \n") == "Furnish and Install UPS"


@pytest.mark.parametrize("pasted, clean", [
    ("1.\xa0\xa0\xa0\xa0\xa0\xa0\xa0\xa0 *Qty (1) BACnet Data Cabinet", "*Qty (1) BACnet Data Cabinet"),
    ("44.\xa0\xa0\xa0\xa0 *Qty (1) Can Wash Kitchen Exhaust Fan EF-9 ", "*Qty (1) Can Wash Kitchen Exhaust Fan EF-9"),
    ("o\xa0\xa0 Furnish and Install UPS", "Furnish and Install UPS"),
    ("⮚\xa0\xa0\xa0\xa0\xa0 Keyboard ", "Keyboard"),
    ("·\xa0\xa0\xa0\xa0\xa0\xa0\xa0\xa0 Front End Web Enabled BMS System", "Front End Web Enabled BMS System"),
    ("•  Front End Web Enabled BMS System", "Front End Web Enabled BMS System"),
    ("Outside Air Temperature", "Outside Air Temperature"),
    ("2 Year Workmanship and Material Guarantee", "2 Year Workmanship and Material Guarantee"),
    ("o  1. something", "1. something"),
])
def test_strip_list_marker(pasted, clean):
    assert strip_list_marker(pasted) == clean
