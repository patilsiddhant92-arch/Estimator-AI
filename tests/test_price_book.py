import pytest

from estimator.price_sheet.price_book import BookItem, PriceBook, price_key


@pytest.mark.parametrize("line, key", [
    ("o  Furnish and Install BACnet IP Router – (Qty. 7 Total)", "bacnet ip router"),
    ("Furnish NEMA 12K Enclosure – (Qty. 5 Total) Installation by Others", "nema 12k enclosure"),
    # "install" and "install and wire" are kept, not stripped: an install-only line prices a
    # device furnished by others, which the book must never guess a price for (M1).
    ("Install and wire Programmable Thermostat (Furnished by Unit Mfr.)",
     "install and wire programmable thermostat (furnished by unit mfr.)"),
    ("Furnish and Wire Filter DP Switch", "filter dp switch"),
    ("Furnish UPS", "ups"),
])
def test_price_key(line, key):
    assert price_key(line) == key


@pytest.mark.parametrize("line", [
    "o  Furnish and Install Space Temperature Sensor (Qty. 6 Total)",   # the renderer's form: no dash
    "Furnish and Install Space Temperature Sensor (Qty. ##)",           # an unknown count
    "Furnish and Install Space Temperature Sensor - (Qty. 6 Total)",    # the old dash form
    "Furnish and Install Space Temperature Sensor – (Qty. 6 Total)",
    "Furnish and Install Space Temperature Sensor (Qty. 6)",
])
def test_price_key_takes_off_every_quantity_form(line):
    assert price_key(line) == "space temperature sensor"


def test_price_key_keeps_a_bracket_that_is_part_of_the_name():
    assert price_key("Furnish Sensor (Wall Mount)") == "sensor (wall mount)"


@pytest.mark.parametrize("line", [
    "o  Furnish and Install Space Temperature Sensor (Qty. 6 Total)",   # the renderer's form: no dash
    "Furnish and Install Space Temperature Sensor (Qty. ##)",           # an unknown count
    "Furnish and Install Space Temperature Sensor - (Qty. 6 Total)",    # the old dash form
    "Furnish and Install Space Temperature Sensor – (Qty. 6 Total)",
    "Furnish and Install Space Temperature Sensor (Qty. 6)",
])
def test_price_key_takes_off_every_quantity_form(line):
    assert price_key(line) == "space temperature sensor"


def test_price_key_keeps_a_bracket_that_is_part_of_the_name():
    assert price_key("Furnish Sensor (Wall Mount)") == "sensor (wall mount)"


def test_every_priced_row_is_loaded(price_book):
    """The revised workbook (T-002): 53 priced parts, 19 panels and 42 valves and meters."""
    assert len(price_book.items) == 114
    assert sum(1 for i in price_book.items if i.sheet == "Std Parts Pricing") == 53
    assert sum(1 for i in price_book.items if i.sheet == "BMS-DDC-Panels") == 19
    assert sum(1 for i in price_book.items if i.sheet == "Control Valves & Meters") == 42


@pytest.mark.parametrize("line, price", [
    ("Furnish and Install Space Temperature Sensor", 142.0),
    ("Furnish UPS", 500.0),
    ("Furnish BMS Server", 2500.0),
    ("o  Furnish and Install Discharge Air Temperature Sensor – (Qty. 2 Total)", 25.0),
    ("Furnish and Install Space Temperature / CO2 Sensor", 182.0),
    ("Furnish and Install BACnet Thermostat – (Qty. 42 Total)", 355.0),
])
def test_known_prices(price_book, line, price):
    assert price_book.lookup(line).price == price


def test_no_guessing(price_book):
    assert price_book.lookup("Furnish and Install DDC Controller") is None        # the book prices it by size
    assert price_book.lookup("Furnish Network Level Control Panel") is None
    assert price_book.lookup("Furnish and Wire Hot Water Control Valve and Actuator") is None   # valves by size


def test_install_only_lines_are_never_priced_from_the_furnish_and_install_price(price_book):
    """M1: "Install Space Temperature Sensor" names a device furnished by others — pricing it
    from the book's "Furnish and Install Space Temperature Sensor" entry would guess a price
    for a part AME isn't supplying."""
    assert price_book.lookup("Install Space Temperature Sensor") is None
    assert price_book.lookup("Install and wire Duct Static Pressure Sensor") is None


def test_the_books_own_doubts_are_kept(price_book):
    """The revised workbook's "Below is not completed" rows (the plant controllers) are priced but questioned."""
    assert price_book.lookup("Furnish Plant Controller with 32 UIO").needs_review is True
    assert price_book.lookup("Furnish and Wire Filter DP Switch").needs_review is False
    assert price_book.lookup("Furnish and Install Space Temperature Sensor").needs_review is False


def test_rows_without_a_price_are_not_items(price_book):
    assert price_book.lookup("Furnish Enable/Disable") is None
    assert {"Enable/Disable", "Global Sensor"}.isdisjoint({i.name for i in price_book.items})


def test_a_confirmed_alias_prices_a_line(price_book):
    book = PriceBook(price_book.items, {"Furnish and Install Damper Actuator": "Standard Damper Actuator"})
    assert book.lookup("o  Furnish and Install Damper Actuator – (Qty. 3 Total)").price == 320.0


def test_an_alias_to_a_missing_item_is_refused(price_book):
    with pytest.raises(ValueError, match="isn't in the price book"):
        PriceBook(price_book.items, {"damper actuator": "Golden Damper Actuator"})


def test_two_items_that_read_the_same_are_refused():
    items = [BookItem("UPS", 500, "a", 1, False), BookItem("Furnish UPS", 450, "a", 2, False)]
    with pytest.raises(ValueError, match="same"):
        PriceBook(items, {})


def test_closest_names_help_an_estimator_confirm_a_match(price_book):
    assert "Standard Damper Actuator" in [i.name for i in price_book.closest("Furnish and Install Damper Actuator")]
