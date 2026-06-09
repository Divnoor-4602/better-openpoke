# Legal Poke MVP Compliance Plan

> This is an engineering compliance plan, not legal advice. Because Legal Poke handles legal conversations, potentially privileged material, confidential facts, personally identifiable information, and recorded speech, privacy/legal-ethics counsel should review the actual product flows, vendor contracts, Terms, and Privacy Policy before launch.

## Goal

Legal Poke is an MVP, so the goal is not enterprise-grade compliance on day one. The goal is to make the product as compliant and safe as reasonably possible by reducing the biggest legal, privacy, and security risks early.

The MVP compliance floor is:

1. explicit recording consent
2. minimal retention of raw audio/transcripts
3. no sensitive content in logs
4. strict server-side authorization
5. honest vendor/privacy claims
6. user deletion controls
7. clear AI limitations and review disclaimers

## Governing Principle

Design the app as if every raw recording, transcript, AI prompt, AI response, generated note, redaction map, error payload, and log entry may contain privileged or confidential legal material.

Default behavior should be:

- no silent recording
- no hidden meeting capture
- no unnecessary retention
- no unnecessary vendor sharing
- no model training on customer data where contractually available
- no raw transcript/audio/prompt/AI-output exposure in logs
- no production legal content used for debugging unless explicitly approved and audited

## MVP Data Flow

Expected note-taking pipeline:

1. User starts a recording or uploads audio.
2. App shows/uses an explicit consent confirmation.
3. Server receives audio.
4. Audio is sent to a transcription provider.
5. Transcript is returned to the server.
6. Server sends transcript or a minimized/redacted version to the AI provider.
7. AI generates structured notes, categories, issues, summaries, action items, risks, and follow-ups.
8. Server stores the generated notes as user-owned product data.
9. Raw audio is deleted after transcription unless the user explicitly chooses to retain it.
10. User can delete recordings, transcripts, and generated notes.

Important distinction:

- AI responses are allowed and necessary because they become the user-facing notes.
- AI responses, prompts, and transcripts should not be casually dumped into logs, error tracking, or debug tables.

## Data Categories

Treat these as sensitive by default:

- raw audio
- raw transcript
- cleaned transcript
- redacted transcript
- redaction mapping table, if used
- AI prompt payloads
- AI responses
- generated notes
- categorized legal issues
- case/client metadata
- speaker/diarization metadata
- consent records
- audit logs
- export files

For each category, eventually document:

- where it is created
- where it is stored
- who can access it
- which vendors receive it
- retention period
- deletion behavior
- encryption status
- whether it may contain privileged/confidential data

## P0 MVP Requirements

These should be implemented before real legal users rely on the product.

### 1. Explicit Recording Consent

Before recording or transcription, require the user to confirm consent.

MVP behavior:

- user actively starts recording/transcription
- show consent/disclosure language
- require checkbox or equivalent confirmation
- store a timestamped consent record
- show visible recording state in the app

Suggested copy:

> I confirm I have obtained all required consent from participants before recording or transcribing this conversation.

Store at minimum:

- user ID
- organization ID, if applicable
- recording/session ID
- timestamp
- consent text/version
- confirmation method

Avoid for MVP:

- silent recording
- hidden meeting capture
- background/ambient capture without obvious user action
- auto-joining meetings without disclosure

### 2. Delete Raw Audio Quickly

Raw audio is one of the highest-risk data types.

MVP default:

- keep raw audio only long enough to transcribe
- delete raw audio after successful transcription
- delete failed/abandoned audio after a short timeout
- only retain audio longer if the user explicitly chooses that behavior

If audio is retained, make that visible to the user.

### 3. Do Not Log Sensitive Content

Logs must not include:

- raw audio
- audio URLs
- raw transcripts
- cleaned transcripts
- AI prompts
- AI responses
- generated note content
- client names
- matter details
- redaction maps
- privileged/confidential legal facts

Safe logs should use metadata only:

- request ID
- user ID
- organization ID
- job ID
- recording ID
- transcript ID
- note ID
- provider name
- status
- duration
- token count
- error code

Example safe event:

```json
{
  "event": "note_generation_completed",
  "userId": "user_123",
  "orgId": "org_123",
  "recordingId": "rec_123",
  "noteId": "note_123",
  "provider": "openai",
  "durationMs": 4000,
  "status": "success"
}
```

### 4. Strong Server-Side Authorization

Every sensitive resource must be scoped and checked server-side.

Sensitive resources include:

- recordings
- transcripts
- notes
- generated summaries
- categorized issues
- clients
- matters
- consent records
- exports
- deletion jobs

The frontend hiding UI is not enough. Every server route must verify that the authenticated user can access the requested object.

Required tests:

- user cannot access another user's recording
- user cannot access another user's transcript
- user cannot access another user's notes
- user cannot delete another user's data
- organization-scoped users cannot cross organization boundaries

### 5. AI Note Generation Is Allowed, But Controlled

The app may send transcripts to AI providers to generate:

- summaries
- categorized legal issues
- key facts
- action items
- deadlines
- risks
- missing information
- follow-up questions
- draft notes

The generated AI output may be stored as intentional product data.

Rules:

- store AI-generated notes only in the product data model
- treat generated notes as sensitive legal data
- do not log raw prompts or raw AI responses
- do not send unnecessary metadata to the AI provider
- include a visible AI accuracy disclaimer

Suggested disclaimer:

> AI-generated notes may be incomplete or inaccurate. Review before relying on, filing, or sharing.

### 6. Vendor Reality Check

Do not make privacy promises that vendors do not support.

Before launch, verify for transcription and AI providers:

- whether customer data is used for training
- retention settings/defaults
- deletion support
- DPA availability
- subprocessors
- whether humans may review submitted data
- security posture, such as SOC 2/ISO claims if available

Important:

> Zero-retention promises are only real if AssemblyAI/OpenAI/other vendors contractually support them. This is a contract and policy step, not just a settings toggle.

Create a lightweight vendor register containing:

| Vendor | Purpose | Data Shared | Training? | Retention | DPA Status | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Transcription provider | Audio to transcript | Audio, metadata | TBD | TBD | TBD | Verify before launch |
| AI provider | Generate notes/issues | Transcript or redacted transcript | TBD | TBD | TBD | Verify before launch |
| Hosting/database | App infrastructure | App data | TBD | TBD | TBD | Verify before launch |

### 7. Basic Deletion

Users should be able to delete:

- generated notes
- transcripts
- retained audio, if any
- recordings/sessions

MVP deletion should actually remove app-owned copies from the database/storage. Vendor deletion should be supported where possible and documented honestly.

### 8. Privacy Policy, Terms, and AI Limitations

Before external users, have lightweight but accurate legal documents covering:

- what data is collected
- what vendors process data
- recording consent responsibility
- AI-generated output limitations
- no legal advice disclaimer, if applicable
- retention/deletion behavior
- data security practices
- user responsibilities

These should be reviewed by counsel before public launch.

## P1 Strongly Recommended After MVP Floor

Add soon after the first MVP compliance layer:

- consent history UI
- retention settings
- export controls
- audit logs for sensitive actions
- admin/user access logs
- error monitoring scrubber
- vendor register completed with actual contract links/status
- MFA support if auth provider supports it easily
- incident response checklist
- redaction map isolation if redaction is implemented

## P2 Enterprise/Longer-Term Items

Can be deferred unless selling to larger firms or regulated customers:

- SOC 2 readiness
- SAML/SSO
- BYOK/customer-managed keys
- data residency controls
- legal hold
- advanced DLP
- biometric voice recognition
- persistent voiceprints
- enterprise audit dashboard
- field-level encryption
- customer-specific DPAs
- full subprocessor portal

## Redaction Round-Trip Warning

If the app implements redaction, remember:

- redaction protects downstream vendors from seeing certain sensitive information
- it does not protect Legal Poke if the backend keeps the original transcript and redaction map

If storing redaction maps:

- treat them as highly sensitive
- never log them
- never send them to AI vendors
- restrict access
- consider short retention
- consider separate encryption later

## Biometric / Speaker Identification Policy

For MVP, avoid persistent biometric speaker recognition.

Safer MVP approach:

- allow transient diarization like `Speaker 1`, `Speaker 2`
- do not create persistent voice profiles
- do not match speakers across meetings
- do not store voiceprints

If persistent speaker recognition is added later, require legal review, explicit opt-in, biometric disclosure, retention policy, and deletion rights.

## Server Implementation Checklist

- [ ] Add consent model/table.
- [ ] Add consent requirement before recording/transcription.
- [ ] Add visible recording/session state support.
- [ ] Add server-side authorization checks for every sensitive route.
- [ ] Add tests for cross-user/cross-org access denial.
- [ ] Add safe logger pattern/middleware.
- [ ] Remove `console.log` or debug logs containing sensitive content.
- [ ] Delete raw audio after successful transcription.
- [ ] Add cleanup job for failed/abandoned audio.
- [ ] Store generated notes as intentional product data.
- [ ] Prevent AI prompts/responses/transcripts from going to logs.
- [ ] Add user deletion endpoints.
- [ ] Add audit events for sensitive operations where practical.

## App Implementation Checklist

- [ ] Add pre-recording consent confirmation.
- [ ] Add visible recording indicator.
- [ ] Add AI output disclaimer near generated notes.
- [ ] Add delete controls for notes/transcripts/recordings.
- [ ] Add retention visibility if audio/transcripts are retained.
- [ ] Avoid UI patterns that imply silent/background capture.
- [ ] Add onboarding copy explaining consent and AI limitations.

## Verify Before Launch

- [ ] No raw transcripts in logs.
- [ ] No raw prompts in logs.
- [ ] No raw AI responses in logs.
- [ ] No raw audio URLs in logs.
- [ ] Raw audio deletion works.
- [ ] Failed upload/transcription cleanup works.
- [ ] Users cannot access other users' data.
- [ ] Organization boundaries are enforced.
- [ ] Consent records are created.
- [ ] AI disclaimer is visible.
- [ ] Delete flow removes app-owned data.
- [ ] Vendor claims are verified.
- [ ] Privacy Policy matches actual data flows.
- [ ] Terms/Privacy reviewed by counsel before public launch.

## Product Positioning Rule

Do not claim the app is fully compliant, privilege-preserving, zero-retention, or safe for all jurisdictions unless those claims are legally and technically verified.

Safer MVP language:

> Legal Poke is designed with privacy-conscious defaults, explicit recording consent, limited retention of raw audio, and controls to help users manage sensitive legal notes.
