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


class _RemoteTraceback(Exception):
    def __init__(self, tb: str) -> None:
        self.tb = tb


def test_describe_failure_prefers_the_remote_traceback_of_a_process_pool():
    remote = (
        'Traceback (most recent call last):\n'
        '  File "/app/parse_pool.py", line 39, in _parse_in_worker\n    return x\n'
        '  File "/app/java/declarations.py", line 288, in walk\n    expression[0]\n'
        "IndexError: list index out of range\n"
    )
    exc = IndexError("list index out of range")
    exc.__cause__ = _RemoteTraceback(remote)
    assert describe_failure(exc) == "IndexError: list index out of range (declarations.py:288 in walk)"
