"""Fixes from the 2026-10-09 outside review of HarkPro."""
from harkpro import appio, coverage
from harkpro.qc import scope as qscope


def test_full_prefix_range_expands():
    tags = appio.tags_in("VAV-14-01 THRU VAV-14-15")
    assert len(tags) == 15 and "VAV1407" in tags


def test_short_range_still_expands():
    assert appio.tags_in("VAV-01 thru 03") == {"VAV01", "VAV02", "VAV03"}


def test_schedule_count_prints_not_the_highest():
    count = {"value": 15, "others": [{"value": 30, "source": "plan"}]}
    assert appio._qty(count) == 15
    assert qscope._qty(count) == 15


def test_non_controls_mc_dismissal_stands():
    assert coverage.reason_problem("piping and valve bodies by mechanical contractor") == ""
    assert coverage.reason_problem("thermostat by MC") != ""


def test_short_quotes_do_not_cover_each_other():
    assert not coverage._same_passage("by MC", "space thermostat furnished by MC, wired by EC")
    assert coverage._same_passage("provide drip pan leak detector wired to local alarm panel",
                                  "Provide drip pan leak detector wired to local alarm panel.")


def test_range_expands_without_the_app(monkeypatch):
    import builtins
    real = builtins.__import__

    def no_app(name, *a, **k):
        if name.startswith("estimator"):
            raise ImportError(name)
        return real(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", no_app)
    assert appio.tags_in("VAV-01 thru 03") == {"VAV01", "VAV02", "VAV03"}
    assert len(appio.tags_in("VAV-14-01 THRU VAV-14-15")) == 15
