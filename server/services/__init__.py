"""Service layer components with lazy imports."""

from __future__ import annotations

from typing import Any

_EXPORTS = {
    "ConversationLog": (".conversation", "ConversationLog"),
    "SummaryState": (".conversation", "SummaryState"),
    "handle_chat_request": (".conversation.chat_handler", "handle_chat_request"),
    "get_conversation_log": (".conversation", "get_conversation_log"),
    "get_working_memory_log": (".conversation", "get_working_memory_log"),
    "schedule_summarization": (".conversation", "schedule_summarization"),
    "ExecutionAgentLogStore": (".execution", "ExecutionAgentLogStore"),
    "ExecutionEventStore": (".execution", "ExecutionEventStore"),
    "get_execution_agent_logs": (".execution", "get_execution_agent_logs"),
    "get_execution_event_store": (".execution", "get_execution_event_store"),
    "GmailSeenStore": (".gmail", "GmailSeenStore"),
    "ImportantEmailWatcher": (".gmail", "ImportantEmailWatcher"),
    "classify_email_importance": (".gmail", "classify_email_importance"),
    "disconnect_account": (".gmail", "disconnect_account"),
    "execute_gmail_tool": (".gmail", "execute_gmail_tool"),
    "fetch_status": (".gmail", "fetch_status"),
    "get_active_gmail_user_id": (".gmail", "get_active_gmail_user_id"),
    "get_important_email_watcher": (".gmail", "get_important_email_watcher"),
    "initiate_connect": (".gmail", "initiate_connect"),
    "MemoryStore": (".memory", "MemoryStore"),
    "get_memory_store": (".memory", "get_memory_store"),
    "get_memory_index_worker": (".memory.worker", "get_memory_index_worker"),
    "get_trigger_scheduler": (".trigger_scheduler", "get_trigger_scheduler"),
    "get_trigger_service": (".triggers", "get_trigger_service"),
    "TimezoneStore": (".timezone_store", "TimezoneStore"),
    "get_timezone_store": (".timezone_store", "get_timezone_store"),
}


def __getattr__(name: str) -> Any:
    if name not in _EXPORTS:
        raise AttributeError(name)
    module_name, attr_name = _EXPORTS[name]
    from importlib import import_module

    module = import_module(module_name, __name__)
    return getattr(module, attr_name)


__all__ = tuple(sorted(_EXPORTS))
