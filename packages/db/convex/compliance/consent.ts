// Single source of truth for consent text shown to users and recorded server-side.
// Bump the version when the text changes — the server rejects acknowledgements
// against older versions so we always know what each user actually agreed to.

export const MEETING_CONSENT_VERSION = 'v1'
export const MEETING_CONSENT_TEXT =
  'I confirm I have obtained all required consent from participants before recording or transcribing this conversation.'

export const AUTO_JOIN_CONSENT_VERSION = 'v1'
export const AUTO_JOIN_CONSENT_TEXT =
  'I confirm I will obtain consent from all participants in auto-joined meetings before they begin. I understand that a bot named "Legal Poke Notes" will join my upcoming calendar events automatically without further per-meeting confirmation.'

export const AI_DISCLAIMER_TEXT =
  'AI-generated notes may be incomplete or inaccurate. Review before relying on, filing, or sharing.'
