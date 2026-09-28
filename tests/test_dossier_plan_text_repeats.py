from estimator.writing.dossier import _collapse_repeats


def test_a_label_repeated_at_every_symbol_is_given_once_with_its_count():
    assert _collapse_repeats("GPU-1 GPU-1 GPU-1 GPU-1 NOTES: EACH RACK EPIV EPIV EPIV") == "GPU-1 ×4 NOTES: EACH RACK EPIV ×3"


def test_a_word_said_twice_is_left_alone():
    assert _collapse_repeats("VERY VERY LONG PIPE") == "VERY VERY LONG PIPE"
