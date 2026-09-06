"""Focused unit tests for router-independent chat service behavior."""

from services.chat_service import build_chat_prompt, build_pinned_context


def test_prompt_keeps_the_pinned_file_as_primary_context():
    prompt = build_chat_prompt(
        context="<untrusted_source>other file</untrusted_source>",
        pinned_context="<untrusted_pinned_code>focused</untrusted_pinned_code>",
        message="What does it do?",
        pinned_file="src/payroll.cbl",
        multi_project_names=[],
    )

    assert "pinned code as the primary subject" in prompt
    assert "Question: What does it do?" in prompt
    assert "<untrusted_context>" in prompt


def test_non_file_focus_is_included_without_repository_context():
    context = build_pinned_context(
        pinned_file=None,
        pinned_line=None,
        pinned_label=None,
        pinned_context="IFC space: server room",
        pinned_chunks=[],
        repository_id=None,
    )

    assert "<untrusted_focused_object>" in context
    assert "IFC space: server room" in context
