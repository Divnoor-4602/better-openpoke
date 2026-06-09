# Legal Poke Privacy Policy (DRAFT — requires counsel review before launch)

> **Status:** Draft only. Per compliance plan §8, this document must be
> reviewed by privacy/legal-ethics counsel before any external user signs up.

## What we collect

- Account information: email address, name (via Clerk)
- Calendar connection metadata: the email address of your connected calendar, the calendar ID, and an auto-join preference flag (via MeetingBaas; the underlying Google OAuth refresh token is held by MeetingBaas, not by us)
- Meeting metadata: meeting URL, scheduled times, bot status, your consent acknowledgement
- Meeting transcripts: PII-redacted transcripts produced by AssemblyAI from in-flight audio. Raw audio is never written to our database.
- Generated notes: AI-generated summaries (we treat these as your product data)
- Audit log: timestamps of consent acknowledgements, meeting creation, deletions

## What we do **not** collect

- Raw audio files (streamed only; not stored on our side)
- Pre-recording-redaction transcript text (AssemblyAI strips PII before we receive turns)
- Other Google Calendar data beyond what's needed to schedule bots

## Who we share with

See `docs/legal-poke/vendor-register.md` for the current vendor list, what we
share with each, and the contractual status. Notable:

- **MeetingBaas** receives meeting URLs, audio in-flight, and your calendar OAuth token (held by them, not us)
- **AssemblyAI** receives in-flight audio for transcription
- **OpenAI** (via our agent) receives PII-redacted transcript text to produce notes
- **Convex** stores everything we keep (transcripts, notes, metadata, audit log)
- **Clerk** stores your account/auth identity

## Retention

| Data | How long we keep it |
| --- | --- |
| Audio | Not retained at all on our side. Verify vendor zero-retention on dashboards. |
| Transcripts (per turn) | Until you delete the meeting |
| Generated notes | Until you delete them or the meeting |
| Audit log | Until you delete your account |
| Calendar connection | Until you disconnect |

## Your controls

- Delete a meeting (cascades to its transcript turns + notes) from the meeting list
- Delete generated notes individually from the notes page
- Disconnect your calendar from settings
- Disable auto-join from the calendar section
- Request full account deletion via support (manual until self-serve is built)

## AI-generated content limitations

> AI-generated notes may be incomplete or inaccurate. Review before relying on, filing, or sharing.

This disclaimer is shown in-product on every notes page.

## Recording consent

Recording in legal contexts requires participant consent. Legal Poke does not
record without your active, per-meeting acknowledgement that you have obtained
the required consent from all participants. We store the exact consent text
and the version you agreed to, along with the timestamp, as audit evidence.

## Contact

For privacy concerns or data deletion requests: *(to be added before launch)*

---

**TODO before launch:**
- Counsel review
- Add contact email
- List subprocessors per vendor
- Add jurisdictional disclaimers
- Confirm vendor-register checklist is green
