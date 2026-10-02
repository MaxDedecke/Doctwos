from core.failure_location import describe_failure


def _boom():
    return [][0]


def test_describe_failure_names_innermost_frame():
    try:
        _boom()
    except IndexError as exc:
        text = describe_failure(exc)
    assert text.startswith("IndexError: list index out of range (test_failure_location.py:")
    assert text.endswith("in _boom)")


def test_describe_failure_without_traceback_keeps_plain_message():
    assert describe_failure(ValueError("x")) == "ValueError: x"
