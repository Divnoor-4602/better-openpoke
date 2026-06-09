import type { api } from '@general-poke/db/api'
import type { FunctionReturnType } from 'convex/server'

import { SignOutButton, useUser } from '@clerk/tanstack-react-start'
import {
  AUTO_JOIN_CONSENT_TEXT,
  AUTO_JOIN_CONSENT_VERSION,
  MEETING_CONSENT_TEXT,
  MEETING_CONSENT_VERSION,
} from '@general-poke/db/compliance'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@general-poke/ui/components/alert-dialog'
import { Link, useNavigate } from '@tanstack/react-router'
import { FileText, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'

import { ConsentModal } from '@/features/compliance/components/consent-modal'
import {
  useCalendarConnectionQuery,
  useCalendarEventsQuery,
  useCancelBotForEventAction,
  useDisconnectCalendarAction,
  useScheduleBotForEventAction,
  useSetAutoJoinMutation,
  useStartGoogleOauthAction,
} from '@/lib/convex/calendar'
import {
  useDeleteMeetingAction,
  useMyMeetingsQuery,
  useStartAdHocMeetingAction,
} from '@/lib/convex/meetings'

type MeetingRow = FunctionReturnType<
  typeof api.public.meeting.queries.listMyMeetings
>[number]

const PLATFORM_LABEL: Record<string, string> = {
  meet: 'Google Meet',
  teams: 'Microsoft Teams',
  zoom: 'Zoom',
}

const formatDateRange = (startIso: string, endIso: string) => {
  const start = new Date(startIso)
  const end = new Date(endIso)
  const day = start.toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    weekday: 'short',
  })
  const startTime = start.toLocaleTimeString(undefined, {
    hour: 'numeric',
    minute: '2-digit',
  })
  const endTime = end.toLocaleTimeString(undefined, {
    hour: 'numeric',
    minute: '2-digit',
  })
  return `${day} · ${startTime} – ${endTime}`
}

export const Welcome = () => {
  const { user } = useUser()
  const connectionQuery = useCalendarConnectionQuery({ provider: 'google' })
  const startOauth = useStartGoogleOauthAction()
  const disconnect = useDisconnectCalendarAction()
  const setAutoJoin = useSetAutoJoinMutation()
  const scheduleBot = useScheduleBotForEventAction()
  const cancelBot = useCancelBotForEventAction()
  const connection = connectionQuery.data
  const eventsQuery = useCalendarEventsQuery({
    enabled: !!connection,
    provider: 'google',
  })
  const meetingsQuery = useMyMeetingsQuery()
  const startAdHoc = useStartAdHocMeetingAction()
  const deleteMeeting = useDeleteMeetingAction()
  const navigate = useNavigate()
  const [adHocUrl, setAdHocUrl] = useState('')
  const [adHocTitle, setAdHocTitle] = useState('')
  const [adHocError, setAdHocError] = useState<null | string>(null)
  const [pendingDeleteMeetingId, setPendingDeleteMeetingId] = useState<
    null | string
  >(null)

  // Consent flow state — `pendingAction` is the operation deferred until
  // the modal's confirm fires.
  const [pendingAction, setPendingAction] = useState<
    | null
    | { enable: boolean; kind: 'autojoin' }
    | {
        eventId: string
        kind: 'schedule'
        meetingUrl: string
        seriesId: string
        title?: string
      }
    | { kind: 'adhoc' }
  >(null)

  if (!user) return null

  const search =
    typeof window === 'undefined'
      ? new URLSearchParams()
      : new URLSearchParams(window.location.search)
  const calendarStatus = search.get('calendar')
  const reason = search.get('reason')

  const handleConnect = async () => {
    const result = await startOauth.mutateAsync({})
    window.location.assign(result.url)
  }

  const handleDisconnect = async () => {
    await disconnect.mutateAsync({ provider: 'google' })
  }

  const handleToggleAutoJoin = async () => {
    if (!connection) return
    const enabling = !connection.autoJoinEnabled
    if (enabling) {
      // Enabling auto-join needs explicit acknowledgement; show modal first.
      setPendingAction({ enable: true, kind: 'autojoin' })
      return
    }
    await setAutoJoin.mutateAsync({
      enabled: false,
      provider: 'google',
    })
  }

  const handleConfirmPending = async () => {
    if (!pendingAction) return
    try {
      if (pendingAction.kind === 'adhoc') {
        const result = await startAdHoc.mutateAsync({
          consentVersion: MEETING_CONSENT_VERSION,
          meetingUrl: adHocUrl.trim(),
          title: adHocTitle.trim() || undefined,
        })
        setAdHocUrl('')
        setAdHocTitle('')
        setPendingAction(null)
        await navigate({
          params: { meetingId: result.meetingId },
          to: '/meetings/$meetingId',
        })
        return
      }
      if (pendingAction.kind === 'autojoin') {
        await setAutoJoin.mutateAsync({
          autoJoinConsentVersion: AUTO_JOIN_CONSENT_VERSION,
          enabled: pendingAction.enable,
          provider: 'google',
        })
        setPendingAction(null)
        return
      }
      if (connection) {
        await scheduleBot.mutateAsync({
          consentVersion: MEETING_CONSENT_VERSION,
          eventId: pendingAction.eventId,
          mbCalendarId: connection.mbCalendarId,
          meetingUrl: pendingAction.meetingUrl,
          provider: 'google',
          seriesId: pendingAction.seriesId,
          title: pendingAction.title,
        })
        void eventsQuery.refetch()
        setPendingAction(null)
        return
      }
    } catch (err) {
      if (pendingAction.kind === 'adhoc') {
        setAdHocError((err as Error).message)
      }
      setPendingAction(null)
    }
  }

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6 p-6">
      <div className="text-lg">
        Welcome, {user.emailAddresses[0].emailAddress}
      </div>

      {calendarStatus === 'connected' && (
        <div className="rounded border border-green-300 bg-green-50 p-3 text-green-700">
          Calendar connected.
        </div>
      )}
      {calendarStatus === 'error' && (
        <div className="rounded border border-red-300 bg-red-50 p-3 text-red-700">
          Connection failed{reason ? `: ${reason}` : ''}
        </div>
      )}

      <section className="flex flex-col gap-3 rounded border p-4">
        <h2 className="font-semibold">Google Calendar</h2>

        {connectionQuery.isPending ? (
          <div className="text-sm text-gray-500">Loading…</div>
        ) : connection ? (
          <>
            <div className="text-sm">
              Connected as{' '}
              <span className="font-mono">{connection.accountEmail}</span>
            </div>
            <div className="text-sm text-gray-500">
              Status: {connection.status}
            </div>

            <label className="flex items-center gap-2 text-sm">
              <input
                checked={connection.autoJoinEnabled}
                disabled={setAutoJoin.isPending}
                onChange={handleToggleAutoJoin}
                type="checkbox"
              />
              Auto-join meetings on this calendar
            </label>

            <button
              className="self-start rounded bg-red-600 px-3 py-1 text-white disabled:opacity-50"
              disabled={disconnect.isPending}
              onClick={handleDisconnect}
              type="button"
            >
              {disconnect.isPending ? 'Disconnecting…' : 'Disconnect'}
            </button>
          </>
        ) : (
          <>
            <div className="text-sm text-gray-600">No calendar connected.</div>
            <button
              className="self-start rounded bg-blue-600 px-3 py-1 text-white disabled:opacity-50"
              disabled={startOauth.isPending}
              onClick={handleConnect}
              type="button"
            >
              {startOauth.isPending
                ? 'Redirecting…'
                : 'Connect Google Calendar'}
            </button>
          </>
        )}
      </section>

      {connection && (
        <section className="flex flex-col gap-3 rounded border p-4">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold">Upcoming events</h2>
            <button
              className="text-sm text-blue-600 hover:underline disabled:opacity-50"
              disabled={eventsQuery.isFetching}
              onClick={() => eventsQuery.refetch()}
              type="button"
            >
              {eventsQuery.isFetching ? 'Refreshing…' : 'Refresh'}
            </button>
          </div>

          {eventsQuery.isPending ? (
            <div className="text-sm text-gray-500">Loading events…</div>
          ) : eventsQuery.error ? (
            <div className="text-sm text-red-600">
              Failed to load events: {eventsQuery.error.message}
            </div>
          ) : eventsQuery.data.events.length > 0 ? (
            <ul className="flex flex-col gap-3">
              {eventsQuery.data.events.map((event) => (
                <li
                  className="flex flex-col gap-1 rounded border border-gray-200 bg-gray-50 p-3"
                  key={event.eventId}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="font-medium">
                      {event.title || 'Untitled'}
                    </div>
                    {event.botScheduled && (
                      <span className="rounded bg-green-100 px-2 py-0.5 text-xs text-green-700">
                        Bot scheduled
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-gray-600">
                    {formatDateRange(event.startTime, event.endTime)}
                  </div>
                  <div className="flex items-center gap-2 text-xs">
                    {event.meetingPlatform ? (
                      <span className="rounded bg-blue-100 px-2 py-0.5 text-blue-700">
                        {PLATFORM_LABEL[event.meetingPlatform] ??
                          event.meetingPlatform}
                      </span>
                    ) : (
                      <span className="rounded bg-yellow-100 px-2 py-0.5 text-yellow-800">
                        No meeting link
                      </span>
                    )}
                    {event.status !== 'confirmed' && (
                      <span className="rounded bg-gray-200 px-2 py-0.5 text-gray-700">
                        {event.status}
                      </span>
                    )}
                  </div>
                  {event.meetingUrl && (
                    <a
                      className="break-all text-xs text-blue-600 hover:underline"
                      href={event.meetingUrl}
                      rel="noreferrer"
                      target="_blank"
                    >
                      {event.meetingUrl}
                    </a>
                  )}

                  {connection && event.meetingUrl && (
                    <div className="flex gap-2 pt-1">
                      {event.botScheduled ? (
                        <button
                          className="rounded bg-gray-700 px-2 py-1 text-xs text-white disabled:opacity-50"
                          disabled={cancelBot.isPending}
                          onClick={async () => {
                            await cancelBot.mutateAsync({
                              eventId: event.eventId,
                              mbCalendarId: connection.mbCalendarId,
                              provider: 'google',
                            })
                            void eventsQuery.refetch()
                          }}
                          type="button"
                        >
                          {cancelBot.isPending ? 'Cancelling…' : 'Cancel bot'}
                        </button>
                      ) : (
                        <button
                          className="rounded bg-blue-600 px-2 py-1 text-xs text-white disabled:opacity-50"
                          disabled={scheduleBot.isPending}
                          onClick={() => {
                            setPendingAction({
                              eventId: event.eventId,
                              kind: 'schedule',
                              meetingUrl: event.meetingUrl!,
                              seriesId: event.seriesId,
                              title: event.title || undefined,
                            })
                          }}
                          type="button"
                        >
                          {scheduleBot.isPending
                            ? 'Scheduling…'
                            : 'Schedule bot'}
                        </button>
                      )}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <div className="text-sm text-gray-500">No upcoming events.</div>
          )}
        </section>
      )}

      <section className="flex flex-col gap-3 rounded border p-4">
        <h2 className="font-semibold">New meeting</h2>
        <p className="text-xs text-gray-500">
          Paste a Google Meet, Zoom, or Teams link and we&apos;ll send a bot to
          join, record, and transcribe.
        </p>
        <input
          aria-label="Meeting URL"
          className="rounded border border-gray-300 px-3 py-2 text-sm outline-none focus:border-blue-500"
          onChange={(e) => {
            setAdHocUrl(e.target.value)
            setAdHocError(null)
          }}
          placeholder="https://meet.google.com/abc-defg-hij"
          value={adHocUrl}
        />
        <input
          aria-label="Meeting title (optional)"
          className="rounded border border-gray-300 px-3 py-2 text-sm outline-none focus:border-blue-500"
          onChange={(e) => setAdHocTitle(e.target.value)}
          placeholder="Title (optional)"
          value={adHocTitle}
        />
        {adHocError && <div className="text-xs text-red-600">{adHocError}</div>}
        <button
          className="flex items-center justify-center gap-2 self-start rounded bg-blue-600 px-3 py-2 text-sm text-white disabled:opacity-50"
          disabled={!adHocUrl.trim() || startAdHoc.isPending}
          onClick={() => {
            setAdHocError(null)
            setPendingAction({ kind: 'adhoc' })
          }}
          type="button"
        >
          <Plus className="size-4" />
          {startAdHoc.isPending ? 'Sending bot…' : 'Send bot'}
        </button>
      </section>

      <section className="flex flex-col gap-3 rounded border p-4">
        <h2 className="font-semibold">My meetings</h2>
        {meetingsQuery.isPending ? (
          <div className="text-sm text-gray-500">Loading…</div>
        ) : meetingsQuery.data && meetingsQuery.data.length > 0 ? (
          <ul className="flex flex-col gap-3">
            {meetingsQuery.data.map((meeting: MeetingRow) => (
              <li
                className="flex items-start justify-between gap-2 rounded border border-gray-200 bg-gray-50 p-3 hover:bg-gray-100"
                key={meeting._id}
              >
                <Link
                  className="flex min-w-0 flex-col gap-0.5"
                  params={{ meetingId: meeting._id }}
                  to="/meetings/$meetingId"
                >
                  <div className="truncate font-medium">
                    {meeting.title || 'Untitled meeting'}
                  </div>
                  <div className="text-xs text-gray-500">
                    {meeting.status} ·{' '}
                    {new Date(meeting._creationTime).toLocaleString()}
                  </div>
                </Link>
                <div className="flex shrink-0 items-center gap-2">
                  <NotesStatusPill meeting={meeting} />
                  <button
                    aria-label="Delete meeting"
                    className="rounded p-1.5 text-gray-400 hover:bg-red-50 hover:text-red-600 disabled:opacity-50"
                    disabled={deleteMeeting.isPending}
                    onClick={() => setPendingDeleteMeetingId(meeting._id)}
                    type="button"
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <div className="text-sm text-gray-500">No meetings yet.</div>
        )}
      </section>

      <SignOutButton />

      <ConsentModal
        cancelLabel="Cancel"
        confirmLabel="Confirm and proceed"
        isPending={
          startAdHoc.isPending || scheduleBot.isPending || setAutoJoin.isPending
        }
        onCancel={() => setPendingAction(null)}
        onConfirm={handleConfirmPending}
        open={pendingAction !== null}
        text={
          pendingAction?.kind === 'autojoin'
            ? AUTO_JOIN_CONSENT_TEXT
            : MEETING_CONSENT_TEXT
        }
        title={
          pendingAction?.kind === 'autojoin'
            ? 'Enable auto-join'
            : 'Recording consent'
        }
      />

      <AlertDialog
        onOpenChange={(open) => {
          if (!open) setPendingDeleteMeetingId(null)
        }}
        open={pendingDeleteMeetingId !== null}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete meeting</AlertDialogTitle>
            <AlertDialogDescription>
              This permanently deletes the meeting, its transcript, and any
              generated notes. The bot&apos;s recording at MeetingBaas will also
              be removed. This action can&apos;t be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={async () => {
                if (!pendingDeleteMeetingId) return
                await deleteMeeting.mutateAsync({
                  meetingId: pendingDeleteMeetingId as never,
                })
                setPendingDeleteMeetingId(null)
              }}
              variant="destructive"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

const NotesStatusPill = ({ meeting }: { meeting: MeetingRow }) => {
  if (meeting.noteId) {
    return (
      <Link
        className="flex items-center gap-1.5 rounded bg-purple-600 px-2 py-1 text-xs text-white hover:bg-purple-700"
        params={{ noteId: meeting.noteId }}
        to="/notes/$noteId"
      >
        <FileText className="size-3.5" />
        View notes
      </Link>
    )
  }
  if (meeting.status === 'failed') {
    return (
      <span
        className="rounded bg-red-100 px-2 py-1 text-xs text-red-700"
        title={meeting.failureReason ?? 'Meeting failed'}
      >
        Failed
      </span>
    )
  }
  if (meeting.notesStatus === 'no_transcript') {
    return (
      <span className="rounded bg-yellow-100 px-2 py-1 text-xs text-yellow-800">
        No transcript recorded
      </span>
    )
  }
  if (meeting.notesStatus === 'failed') {
    return (
      <span
        className="rounded bg-red-100 px-2 py-1 text-xs text-red-700"
        title={meeting.notesError ?? 'Notes generation failed'}
      >
        Notes failed
      </span>
    )
  }
  if (meeting.status === 'ended') {
    return (
      <span className="rounded bg-gray-200 px-2 py-1 text-xs text-gray-600">
        Generating notes…
      </span>
    )
  }
  return (
    <span className="rounded bg-gray-200 px-2 py-1 text-xs text-gray-600">
      Awaiting summary
    </span>
  )
}
