"""Service layer components with lazy imports."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .conversation import (
        ConversationLog as ConversationLog,
        SummaryState as SummaryState,
        get_conversation_log as get_conversation_log,
        get_working_memory_log as get_working_memory_log,
        schedule_summarization as schedule_summarization,
    )
    from .conversation.chat_handler import handle_chat_request as handle_chat_request
    from .execution import (
        ExecutionAgentLogStore as ExecutionAgentLogStore,
        ExecutionEventStore as ExecutionEventStore,
        get_execution_agent_logs as get_execution_agent_logs,
        get_execution_event_store as get_execution_event_store,
    )
    from .gmail import (
        GmailSeenStore as GmailSeenStore,
        ImportantEmailWatcher as ImportantEmailWatcher,
        classify_email_importance as classify_email_importance,
        disconnect_account as disconnect_account,
        execute_google_tool as execute_google_tool,
        fetch_status as fetch_status,
        get_important_email_watcher as get_important_email_watcher,
        initiate_connect as initiate_connect,
        resolve_workspace_gmail_user_id as resolve_workspace_gmail_user_id,
    )
    from .memory import (
        MemoryStore as MemoryStore,
        get_memory_store as get_memory_store,
    )
    from .memory.worker import get_memory_index_worker as get_memory_index_worker
    from .timezone_store import (
        TimezoneStore as TimezoneStore,
        get_timezone_store as get_timezone_store,
    )
    from .trigger_scheduler import get_trigger_scheduler as get_trigger_scheduler
    from .triggers import get_trigger_service as get_trigger_service

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
    "execute_google_tool": (".gmail", "execute_google_tool"),
    "fetch_status": (".gmail", "fetch_status"),
    "resolve_workspace_gmail_user_id": (".gmail", "resolve_workspace_gmail_user_id"),
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


def __getattr__(name: str) -> object:
    if name not in _EXPORTS:
        raise AttributeError(name)
    module_name, attr_name = _EXPORTS[name]
    from importlib import import_module

    module = import_module(module_name, __name__)
    return getattr(module, attr_name)  # pyright: ignore[reportAny]


__all__ = (
    "ConversationLog",
    "ExecutionAgentLogStore",
    "ExecutionEventStore",
    "GmailSeenStore",
    "ImportantEmailWatcher",
    "MemoryStore",
    "SummaryState",
    "TimezoneStore",
    "classify_email_importance",
    "disconnect_account",
    "execute_google_tool",
    "fetch_status",
    "get_conversation_log",
    "get_execution_agent_logs",
    "get_execution_event_store",
    "get_important_email_watcher",
    "get_memory_index_worker",
    "get_memory_store",
    "get_timezone_store",
    "get_trigger_scheduler",
    "get_trigger_service",
    "get_working_memory_log",
    "handle_chat_request",
    "initiate_connect",
    "resolve_workspace_gmail_user_id",
    "schedule_summarization",
)
