# Custom Tool UI Candidates

Inventory of execution / interaction agent tools and which ones deserve dedicated chat UI components beyond plain Streamdown markdown.

Already planned (not listed below): **email list**, **single email**, **draft email** (`send_draft` / `gmail_create_draft`).

Hidden tools (`HIDDEN_TOOL_NAMES` in `apps/web/src/features/assistant/lib/agent-state.ts:33`) are never rendered and are excluded: `send_message_to_agent`, `send_messages_to_agents`, `send_message_to_user`, `wait`.

## High value — build these

### Calendar — `server/agents/execution_agent/tools/calendar.py`

| Tool | UI | Notes |
|---|---|---|
| `calendar_list_events` | Agenda card | Day-grouped list: time, title, attendees. Same shape as email list. |
| `calendar_get_event` | Event card | Title, time range, attendees, location, description, "Open in Google Calendar" link. |
| `calendar_create_event` | Event card | Reuse the same component; add a "Created" badge. |
| `calendar_update_event` | Event card | Reuse; "Updated" badge with changed-fields highlight. |
| `calendar_find_free_slots` | Time-slot picker | Visual blocks the user can scan/click. **Highest ROI** — unreadable as JSON, instantly clear as a grid. |

### Meet — `server/agents/execution_agent/tools/meet.py`

| Tool | UI | Notes |
|---|---|---|
| `meet_create_meeting` | Meeting card | Meet link + copy button + Join CTA + start time. |
| `meet_get_meeting` | Meeting card | Same component. |

### Triggers — `server/agents/execution_agent/tools/triggers.py` (Poke's signature feature)

| Tool | UI | Notes |
|---|---|---|
| `createTrigger` | Trigger card | Schedule (cron / next fire time), payload preview, enabled toggle. |
| `updateTrigger` | Trigger card | Reuse with diff/changed-field highlight. |
| `listTriggers` | Triggers list | Same card stacked, with active/paused badges. |

## Medium value

### Contacts — `server/agents/execution_agent/tools/gmail.py`

| Tool | UI | Notes |
|---|---|---|
| `gmail_get_contacts` | Contact chips/list | Avatar + name + email. Click to compose. |
| `gmail_get_people` | Contact chips/list | Same component. |
| `gmail_search_people` | Contact chips/list | Same component. |

### Email action confirmations (not the email itself)

| Tool | UI | Notes |
|---|---|---|
| `gmail_execute_draft` | "Sent" confirmation card | Subject + recipient + timestamp. Lighter than a full email card. |
| `gmail_forward_email` | "Forwarded" confirmation card | Same shape. |
| `gmail_reply_to_thread` | "Replied" confirmation card | Same shape. |

## Skip — text/toast is sufficient

- `gmail_delete_draft`
- `calendar_delete_event`
- `gmail_list_drafts` — folds into the email-list component
- `search_memory` — internal/debug; the existing collapsible `Tools` view is enough

## Suggested build order

1. **Event card** — one component covers `calendar_get_event` / `_create_event` / `_update_event` (3 tools, 1 component).
2. **Trigger card** + **triggers list** — Poke differentiator.
3. **Free-slot picker** — highest visual win, but more design work.
4. **Meet card** — small and easy.
5. **Contacts** — only if a dedicated "find people" flow surfaces.
6. **Sent/forwarded/replied confirmation cards** — last; mostly cosmetic.

## Architecture note

All of these slot into the same pipeline. Extend `MessageBlock` in `apps/web/src/features/assistant/lib/agent-state.ts:223` with a `{ type: 'tool-ui', toolName, output }` variant (or branch inside the existing `Tools` component on `toolName`) so `assistant-message.tsx` stays a thin router between:

- Streamdown text blocks (markdown)
- Generic collapsible tool calls (current `Tools` fallback)
- Rich tool UI cards (this list)

New cards should be additive — the generic `Tools` component remains the fallback for any tool without a dedicated renderer.
