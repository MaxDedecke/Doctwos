"""Regression contract for the O-323 SSE timing protocol."""

from api.chat import ChatSseTelemetry


def test_chat_sse_telemetry_keeps_monotonic_milestones_and_eval_metrics():
    ticks = iter((10.000, 10.031, 10.052, 10.078, 10.093, 10.101))
    telemetry = ChatSseTelemetry(10.000, clock=lambda: next(ticks))

    assert telemetry.record("request_received") == {
        "type": "telemetry", "event": "request_received", "monotonic_ms": 0,
    }
    telemetry.retrieval_wait_ms = 17
    assert telemetry.record_first_tool_call() == {
        "type": "telemetry", "event": "first_tool_call", "monotonic_ms": 31,
    }
    assert telemetry.record_first_tool_call() is None
    assert telemetry.tool_count == 2
    assert telemetry.record("tool_end")["monotonic_ms"] == 52
    assert telemetry.record_first_token() == {
        "type": "telemetry", "event": "first_token", "monotonic_ms": 78,
    }
    assert telemetry.record_model_end() == {
        "type": "telemetry", "event": "model_end", "monotonic_ms": 93,
    }

    # The message save occurs after persistence, so its timestamp is allowed
    # to be later than model completion and becomes the full response time.
    assert telemetry.record_message_saved() == {
        "type": "telemetry", "event": "message_saved", "monotonic_ms": 101,
    }
    assert telemetry.metrics() == {
        "response_time_ms": 101,
        "first_token_ms": 78,
        "tool_count": 2,
        "retrieval_wait_ms": 17,
        "first_tool_call_ms": 31,
        "model_end_ms": 93,
    }
