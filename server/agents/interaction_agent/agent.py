"""Interaction agent helpers for prompt construction."""

from html import escape
from pathlib import Path
from typing import Dict, List

from ...services.memory import MemorySearchResult, get_memory_store

_prompt_path = Path(__file__).parent / "system_prompt.md"
SYSTEM_PROMPT = _prompt_path.read_text(encoding="utf-8").strip()


# Load and return the pre-defined system prompt from markdown file
def build_system_prompt() -> str:
    """Return the static system prompt for the interaction agent."""
    return SYSTEM_PROMPT


# Build structured message with conversation history, relevant memories, and current turn
def prepare_message_with_history(
    latest_text: str,
    transcript: str,
    message_type: str = "user",
) -> List[Dict[str, str]]:
    """Compose a message that bundles history, roster, and the latest turn."""
    sections: List[str] = []

    sections.append(_render_conversation_history(transcript))
    sections.append(f"<relevant_memories>\n{_render_relevant_memories(latest_text)}\n</relevant_memories>")
    sections.append(_render_current_turn(latest_text, message_type))

    content = "\n\n".join(sections)
    return [{"role": "user", "content": content}]


# Format conversation transcript into XML tags for LLM context
def _render_conversation_history(transcript: str) -> str:
    history = transcript.strip()
    if not history:
        history = "None"
    return f"<conversation_history>\n{history}\n</conversation_history>"


# Format relevant memories into XML tags for LLM awareness
def _render_relevant_memories(query: str) -> str:
    memories = get_memory_store().search(query, limit=8, context="prompt_context")

    if not memories:
        return "None"

    rendered: List[str] = []
    for rank, result in enumerate(memories, start=1):
        rendered.append(_render_memory_result(result, rank))

    return "\n".join(rendered)


def _render_memory_result(result: MemorySearchResult, rank: int) -> str:
    memory = result.memory
    memory_id = escape(memory.memory_id, quote=True)
    kind = escape(memory.kind, quote=True)
    title = escape(memory.title, quote=False)
    summary = escape(memory.summary or "None", quote=False)
    reason = escape(result.reason, quote=True)
    confidence = escape(result.confidence, quote=True)
    links = "\n".join(_render_memory_link(link.kind, link.value) for link in memory.links[:8])
    if not links:
        links = "None"
    events = "\n".join(
        (
            f'<event type="{escape(event.type, quote=True)}" '
            f'timestamp="{escape(event.timestamp or event.recorded_at, quote=True)}">'
            f"{escape(event.text, quote=False)}</event>"
        )
        for event in memory.recent_events[-5:]
    )
    if not events:
        events = "None"
    return "\n".join(
        [
            (
                f'<memory id="{memory_id}" kind="{kind}" rank="{rank}" '
                f'score="{result.score:.2f}" confidence="{confidence}" reason="{reason}">'
            ),
            f"<title>{title}</title>",
            f"<summary>{summary}</summary>",
            f"<links>\n{links}\n</links>",
            f"<recent_events>\n{events}\n</recent_events>",
            "</memory>",
        ]
    )


def _render_memory_link(kind: str, value: str) -> str:
    safe_value = escape(value, quote=True)
    if kind == "gmail_thread":
        return f'<gmail_thread id="{safe_value}" />'
    if kind == "gmail_message":
        return f'<gmail_message id="{safe_value}" />'
    if kind == "email_address":
        return f'<email value="{safe_value}" />'
    safe_kind = escape(kind, quote=True)
    return f'<link kind="{safe_kind}" value="{safe_value}" />'


# Wrap the current message in appropriate XML tags based on sender type
def _render_current_turn(latest_text: str, message_type: str) -> str:
    tag = "new_agent_message" if message_type == "agent" else "new_user_message"
    body = latest_text.strip()
    return f"<{tag}>\n{body}\n</{tag}>"
