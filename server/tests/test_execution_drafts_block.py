from __future__ import annotations

from server.agents.execution_agent.runtime import ExecutionAgentRuntime

# pyright: reportPrivateUsage=false


def test_capture_returns_to_subject_body_when_all_present() -> None:
    captured = ExecutionAgentRuntime._capture_created_draft(
        {
            "recipient_email": "alice@example.com",
            "subject": "Meeting Reminder",
            "body": "Hi Alice,\n\nReminder about tomorrow.",
            "cc": ["bob@example.com"],
            "bcc": ["ops@example.com"],
            "extra_recipients": ["carol@example.com"],
            "is_html": False,
            "thread_id": "thread-123",
            "attachment": {
                "name": "agenda.pdf",
                "mimetype": "application/pdf",
                "s3key": "attachments/agenda.pdf",
            },
        },
        {"data": {"response_data": {"id": "r-12345"}}},
    )
    assert captured == {
        "to": "alice@example.com",
        "subject": "Meeting Reminder",
        "body": "Hi Alice,\n\nReminder about tomorrow.",
        "draft_id": "r-12345",
        "cc": ["bob@example.com"],
        "bcc": ["ops@example.com"],
        "extra_recipients": ["carol@example.com"],
        "is_html": False,
        "thread_id": "thread-123",
        "attachment": {
            "name": "agenda.pdf",
            "mimetype": "application/pdf",
            "s3key": "attachments/agenda.pdf",
        },
    }


def test_capture_returns_none_when_body_missing() -> None:
    assert (
        ExecutionAgentRuntime._capture_created_draft(
            {"recipient_email": "a@x.com", "subject": "x"},
            {"data": {}},
        )
        is None
    )


def test_capture_tolerates_missing_draft_id() -> None:
    captured = ExecutionAgentRuntime._capture_created_draft(
        {
            "recipient_email": "a@x.com",
            "subject": "x",
            "body": "hi",
        },
        {"data": {}},
    )
    assert captured is not None
    assert captured["draft_id"] == ""


def test_render_block_emits_one_draft_element_per_entry() -> None:
    block = ExecutionAgentRuntime._render_created_drafts_block(
        [
            {
                "to": "a@x.com",
                "subject": "Hello",
                "body": "Body line 1\nBody line 2",
                "draft_id": "r-1",
                "cc": ["cc@x.com"],
                "bcc": ["bcc@x.com"],
                "extra_recipients": ["also@x.com"],
                "is_html": True,
                "thread_id": "thread-1",
                "attachment": {"name": "notes.txt", "mimetype": "text/plain"},
            },
            {
                "to": "b@y.com",
                "subject": "Hi & you",
                "body": "Body 2",
                "draft_id": "",
            },
        ]
    )
    assert block.startswith("<created_drafts>")
    assert block.endswith("</created_drafts>")
    # First draft has id, ampersand-bearing second escapes it
    assert '<draft to="a@x.com" subject="Hello" draft_id="r-1"' in block
    assert 'thread_id="thread-1"' in block
    assert "cc='[&quot;cc@x.com&quot;]'" in block
    assert "bcc='[&quot;bcc@x.com&quot;]'" in block
    assert "extra_recipients='[&quot;also@x.com&quot;]'" in block
    assert 'is_html="true"' in block
    assert (
        "attachment='{&quot;name&quot;: &quot;notes.txt&quot;, "
        "&quot;mimetype&quot;: &quot;text/plain&quot;}'"
    ) in block
    assert '<draft to="b@y.com" subject="Hi &amp; you">' in block
    # Body content embedded verbatim (newlines preserved)
    assert "<body>Body line 1\nBody line 2</body>" in block
    assert "<body>Body 2</body>" in block


def test_render_block_returns_empty_for_empty_input() -> None:
    assert ExecutionAgentRuntime._render_created_drafts_block([]) == ""
