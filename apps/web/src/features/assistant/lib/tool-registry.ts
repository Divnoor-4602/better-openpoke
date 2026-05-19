import type { PhosphorIcon } from '@phosphor-icons/core'
import type { ComponentType } from 'react'

import {
  AddressBookIcon,
  ArrowBendUpLeftIcon,
  ArrowBendUpRightIcon,
  BellIcon,
  BrainIcon,
  CalendarPlusIcon,
  ChatCircleIcon,
  ChatsIcon,
  ClockIcon,
  EnvelopeIcon,
  EnvelopeOpenIcon,
  HourglassIcon,
  ListBulletsIcon,
  MagnifyingGlassIcon,
  NotepadIcon,
  PaperPlaneTiltIcon,
  PencilSimpleIcon,
  PenIcon,
  TrashIcon,
  UsersIcon,
  VideoCameraIcon,
} from '@phosphor-icons/react'

import GmailIcon from '@/assets/gmail-icon'
import GoogleCalendarIcon from '@/assets/google-calendar-icon'
import GoogleMeetIcon from '@/assets/google-meet-icon'

import type { NormalizedToolCall, ToolCallState } from './agent-state'

export type IconName = PhosphorIcon['name']

export type ToolCategory =
  | 'calendar'
  | 'gmail'
  | 'interaction'
  | 'meet'
  | 'memory'
  | 'triggers'
  | 'unknown'

export type ToolIcon = ComponentType<{ className?: string }>

export type ToolMeta = {
  actionIcon: null | ToolIcon
  category: ToolCategory
  labels: {
    cancelled: string
    error: string
    running: string
    success: string
  }
  primaryIcon: null | ToolIcon
}

// Phosphor icon names → components. Only the ones we use — keeps the bundle tight.
const ACTION_ICONS: Partial<Record<IconName, ToolIcon>> = {
  'address-book': AddressBookIcon,
  'arrow-bend-up-left': ArrowBendUpLeftIcon,
  'arrow-bend-up-right': ArrowBendUpRightIcon,
  bell: BellIcon,
  brain: BrainIcon,
  'calendar-plus': CalendarPlusIcon,
  'chat-circle': ChatCircleIcon,
  chats: ChatsIcon,
  clock: ClockIcon,
  envelope: EnvelopeIcon,
  'envelope-open': EnvelopeOpenIcon,
  hourglass: HourglassIcon,
  'list-bullets': ListBulletsIcon,
  'magnifying-glass': MagnifyingGlassIcon,
  notepad: NotepadIcon,
  'paper-plane-tilt': PaperPlaneTiltIcon,
  pen: PenIcon,
  'pencil-simple': PencilSimpleIcon,
  trash: TrashIcon,
  users: UsersIcon,
  'video-camera': VideoCameraIcon,
}

// Author labels as a 3-tuple: [running, success, actionPhrase].
// - running:        present continuous,  shown while in flight  ("Creating Gmail draft")
// - success:        past tense,          shown on success       ("Created Gmail draft")
// - actionPhrase:   bare infinitive,     templated into error   → "Failed to create Gmail draft"
type LabelTuple = [running: string, success: string, actionPhrase: string]

const buildLabels = (tuple: LabelTuple): ToolMeta['labels'] => ({
  cancelled: `Cancelled ${tuple[2]}`,
  error: `Failed to ${tuple[2]}`,
  running: tuple[0],
  success: tuple[1],
})

const gmail = (
  labels: LabelTuple,
  action: IconName | null = null,
): ToolMeta => ({
  actionIcon: action ? (ACTION_ICONS[action] ?? null) : null,
  category: 'gmail',
  labels: buildLabels(labels),
  primaryIcon: GmailIcon,
})

const calendar = (
  labels: LabelTuple,
  action: IconName | null = null,
): ToolMeta => ({
  actionIcon: action ? (ACTION_ICONS[action] ?? null) : null,
  category: 'calendar',
  labels: buildLabels(labels),
  primaryIcon: GoogleCalendarIcon,
})

const meet = (
  labels: LabelTuple,
  action: IconName | null = null,
): ToolMeta => ({
  actionIcon: action ? (ACTION_ICONS[action] ?? null) : null,
  category: 'meet',
  labels: buildLabels(labels),
  primaryIcon: GoogleMeetIcon,
})

const plain = (
  category: ToolCategory,
  labels: LabelTuple,
  action: IconName | null = null,
): ToolMeta => ({
  actionIcon: action ? (ACTION_ICONS[action] ?? null) : null,
  category,
  labels: buildLabels(labels),
  primaryIcon: null,
})

const REGISTRY: Record<string, ToolMeta> = {
  calendar_create_event: calendar(
    ['Creating event', 'Created event', 'create event'],
    'calendar-plus',
  ),
  calendar_delete_event: calendar(
    ['Deleting event', 'Deleted event', 'delete event'],
    'trash',
  ),
  calendar_find_free_slots: calendar(
    ['Finding free slots', 'Found free slots', 'find free slots'],
    'clock',
  ),
  calendar_get_event: calendar(
    ['Fetching event', 'Fetched event', 'fetch event'],
    'magnifying-glass',
  ),
  calendar_list_calendars: calendar(
    ['Listing calendars', 'Listed calendars', 'list calendars'],
    'list-bullets',
  ),
  // Calendar
  calendar_list_events: calendar(
    ['Listing events', 'Listed events', 'list events'],
    'list-bullets',
  ),
  calendar_update_event: calendar(
    ['Updating event', 'Updated event', 'update event'],
    'pencil-simple',
  ),
  // Triggers
  createTrigger: plain(
    'triggers',
    ['Creating trigger', 'Created trigger', 'create trigger'],
    'bell',
  ),
  // Gmail
  gmail_create_draft: gmail(
    ['Creating Gmail draft', 'Created Gmail draft', 'create Gmail draft'],
    'pen',
  ),
  gmail_delete_draft: gmail(
    ['Deleting draft', 'Deleted draft', 'delete draft'],
    'trash',
  ),
  gmail_execute_draft: gmail(
    ['Sending email', 'Sent email', 'send email'],
    'paper-plane-tilt',
  ),
  gmail_fetch_emails: gmail(
    ['Fetching emails', 'Fetched emails', 'fetch emails'],
    'envelope',
  ),
  gmail_fetch_message_by_id: gmail(
    ['Fetching email', 'Fetched email', 'fetch email'],
    'envelope-open',
  ),
  gmail_fetch_thread: gmail(
    ['Fetching thread', 'Fetched thread', 'fetch thread'],
    'chats',
  ),

  gmail_forward_email: gmail(
    ['Forwarding email', 'Forwarded email', 'forward email'],
    'arrow-bend-up-right',
  ),
  gmail_get_contacts: gmail(
    ['Getting contacts', 'Got contacts', 'get contacts'],
    'address-book',
  ),

  gmail_get_people: gmail(
    ['Getting people', 'Got people', 'get people'],
    'users',
  ),
  gmail_list_drafts: gmail(
    ['Listing drafts', 'Listed drafts', 'list drafts'],
    'notepad',
  ),
  gmail_reply_to_thread: gmail(
    ['Replying to thread', 'Replied to thread', 'reply to thread'],
    'arrow-bend-up-left',
  ),
  gmail_search_people: gmail(
    ['Searching contacts', 'Searched contacts', 'search contacts'],
    'address-book',
  ),
  listTriggers: plain(
    'triggers',
    ['Listing triggers', 'Listed triggers', 'list triggers'],
    'list-bullets',
  ),
  // Meet
  meet_create_meeting: meet(
    ['Creating Meet space', 'Created Meet space', 'create Meet space'],
    'video-camera',
  ),
  meet_get_meeting: meet(
    ['Fetching Meet space', 'Fetched Meet space', 'fetch Meet space'],
    'video-camera',
  ),
  // Gmail-adjacent: email search task
  return_search_results: gmail(
    [
      'Compiling search results',
      'Compiled search results',
      'compile search results',
    ],
    'envelope',
  ),

  // Memory
  search_memory: plain(
    'memory',
    ['Searching memory', 'Searched memory', 'search memory'],
    'brain',
  ),

  // Interaction-scope email tool
  send_draft: gmail(['Drafting email', 'Drafted email', 'draft email'], 'pen'),
  // Interaction
  send_message_to_agent: plain(
    'interaction',
    ['Dispatching to agent', 'Dispatched to agent', 'dispatch to agent'],
    'paper-plane-tilt',
  ),
  send_message_to_user: plain(
    'interaction',
    ['Replying to user', 'Replied to user', 'reply to user'],
    'chat-circle',
  ),
  send_messages_to_agents: plain(
    'interaction',
    ['Dispatching to agents', 'Dispatched to agents', 'dispatch to agents'],
    'paper-plane-tilt',
  ),

  task_email_search: gmail(
    ['Searching email', 'Searched email', 'search email'],
    'envelope',
  ),

  updateTrigger: plain(
    'triggers',
    ['Updating trigger', 'Updated trigger', 'update trigger'],
    'pencil-simple',
  ),
  wait: plain('interaction', ['Waiting', 'Waited', 'wait'], 'hourglass'),
}

export const getToolMeta = (toolName: string): ToolMeta =>
  REGISTRY[toolName] ?? {
    actionIcon: null,
    category: 'unknown',
    labels: {
      cancelled: toolName,
      error: toolName,
      running: toolName,
      success: toolName,
    },
    primaryIcon: null,
  }

// Resolve the human label for a given lifecycle state.
export const getToolLabel = (meta: ToolMeta, state: ToolCallState): string => {
  if (state === 'start' || state === 'running') return meta.labels.running
  if (state === 'error') return meta.labels.error
  if (state === 'cancel') return meta.labels.cancelled
  return meta.labels.success
}

// Brand icons for the header badge cluster. Categories without an entry are skipped.
export const CATEGORY_BRAND_ICONS: Partial<Record<ToolCategory, ToolIcon>> = {
  calendar: GoogleCalendarIcon,
  gmail: GmailIcon,
  meet: GoogleMeetIcon,
}

// Stable left-to-right display order for the header badge cluster.
export const CATEGORY_ORDER: ToolCategory[] = [
  'gmail',
  'meet',
  'calendar',
  'triggers',
  'memory',
  'interaction',
  'unknown',
]

// Categories present in the given calls that have a brand icon, in stable order.
export const getActiveBrandCategories = (
  calls: NormalizedToolCall[],
): ToolCategory[] => {
  const present = new Set<ToolCategory>(
    calls.map((c) => getToolMeta(c.toolName).category),
  )
  return CATEGORY_ORDER.filter(
    (cat) => present.has(cat) && CATEGORY_BRAND_ICONS[cat],
  )
}
