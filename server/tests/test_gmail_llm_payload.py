from __future__ import annotations

import json
from collections.abc import Mapping
from typing import cast

from server.services.gmail.llm_payload import shrink_gmail_tool_result


def _sample_payload() -> dict[str, object]:
    return {
        "data": {
            "messages": [
                {
                    "messageId": "abc123",
                    "threadId": "th-1",
                    "subject": "Quarterly review",
                    "sender": "alice@example.com",
                    "to": "me@example.com",
                    "messageTimestamp": "2026-05-16T12:00:00Z",
                    "labelIds": ["INBOX", "UNREAD"],
                    "preview": {
                        "subject": "Quarterly review",
                        "body": (
                            "Hi team, here is the quarterly summary with "
                            "tons of detail that should be truncated "
                        )
                        * 5,
                    },
                    "payload": {
                        "headers": [
                            {"name": "From", "value": "alice@example.com"}
                        ]
                    },
                    "attachmentList": [{"name": "q3.pdf"}],
                }
            ],
            "nextPageToken": "next-tok",
        }
    }


def _as_mapping(value: object) -> Mapping[str, object]:
    assert isinstance(value, Mapping), value
    return cast(Mapping[str, object], value)


def test_gmail_fetch_emails_is_shrunken() -> None:
    raw_out = shrink_gmail_tool_result("gmail_fetch_emails", _sample_payload())
    out = _as_mapping(raw_out)
    assert out.get("shrunken") is True
    assert out.get("nextPageToken") == "next-tok"
    msgs = out.get("messages")
    assert isinstance(msgs, list)
    msgs_list = cast(list[object], msgs)
    assert len(msgs_list) == 1
    msg = _as_mapping(msgs_list[0])
    assert msg["messageId"] == "abc123"
    assert msg["threadId"] == "th-1"
    assert msg["subject"] == "Quarterly review"
    assert msg["from"] == "alice@example.com"
    assert msg["to"] == "me@example.com"
    assert msg["labelIds"] == ["INBOX", "UNREAD"]
    assert msg["hasAttachment"] is True
    assert msg["attachmentCount"] == 1
    # snippet present and bounded
    snippet = msg["snippet"]
    assert isinstance(snippet, str)
    assert 0 < len(snippet) <= 151  # 150 + ellipsis


def test_composio_slug_also_shrinks() -> None:
    out = _as_mapping(shrink_gmail_tool_result("GOOGLESUPER_FETCH_EMAILS", _sample_payload()))
    assert out.get("shrunken") is True


def test_non_browse_tool_passes_through_unchanged() -> None:
    payload = _sample_payload()
    for name in (
        "calendar_list_events",
        "gmail_fetch_message_by_id",
        "gmail_fetch_thread",
        "GOOGLESUPER_FETCH_MESSAGE_BY_MESSAGE_ID",
        "GOOGLESUPER_FETCH_MESSAGE_BY_THREAD_ID",
        "gmail_create_draft",
    ):
        assert shrink_gmail_tool_result(name, payload) is payload, name


def test_malformed_payload_passes_through() -> None:
    assert shrink_gmail_tool_result("gmail_fetch_emails", "not a dict") == "not a dict"
    assert shrink_gmail_tool_result("gmail_fetch_emails", {}) == {}
    assert shrink_gmail_tool_result("gmail_fetch_emails", None) is None


def test_shrunken_payload_is_smaller_than_original() -> None:
    original = _sample_payload()
    raw_size = len(json.dumps(original))
    shrunk = shrink_gmail_tool_result("gmail_fetch_emails", original)
    shrunk_size = len(json.dumps(shrunk))
    assert shrunk_size < raw_size, (raw_size, shrunk_size)


def test_short_snippet_is_not_ellipsized() -> None:
    payload: dict[str, object] = {
        "data": {
            "messages": [
                {
                    "messageId": "m1",
                    "threadId": "t1",
                    "subject": "Hi",
                    "sender": "a@x.com",
                    "to": "b@x.com",
                    "messageTimestamp": "2026-05-16T00:00:00Z",
                    "preview": {"body": "short body"},
                }
            ]
        }
    }
    out = _as_mapping(shrink_gmail_tool_result("gmail_fetch_emails", payload))
    messages = out["messages"]
    assert isinstance(messages, list)
    first = _as_mapping(cast(list[object], messages)[0])
    assert first["snippet"] == "short body"
