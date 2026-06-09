# Legal Poke MVP Vendor Register

Per compliance plan §6 ("Vendor Reality Check"). This document tracks the
third-party services that touch user data, what we share with them, and the
contractual / settings posture for retention and training.

**Status:** living document — verify each row before launch and after any
vendor account/setting change.

## Summary table

| Vendor | Purpose | Data Shared | Training? | Retention | DPA | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| MeetingBaas | Meeting bot dispatch + audio capture | Meeting URL, audio stream, calendar OAuth refresh token | Verify — check MB ToS | Default unknown; we call `mb.bots.leave` on end. Need to verify post-meeting recording retention. | Not signed | `recording_mode: 'audio_only'` set on every dispatch. Calendar webhook is signed via svix. |
| AssemblyAI | Real-time speech-to-text + PII redaction | Audio frames (in-flight only) | **Must opt out via dashboard** before launch | Streaming: zero-retention IF opted out of training-data usage | Not signed | Streaming v3 with `u3-rt-pro`. PII redacted server-side before transcript reaches us. No pre-recorded API used. |
| OpenAI (via `@convex-dev/agent`) | Legal note generation (LLM) | Per-meeting transcript text (PII already redacted upstream), agent prompt | OpenAI default opt-out for API tier; verify | Default 30 days per OpenAI API tier; verify | Not signed | Model name in `LEGAL_POKE_AGENT_MODEL`. No raw audio sent. |
| Convex | Application database + serverless runtime | All product data, audit log, consent records | No | Live; user-controlled via in-app delete | Verify | SOC 2 Type II. Encryption at rest. |
| Clerk | User authentication | Email, name, OAuth identities | No | Live; user-controlled | Verify | JWT template "convex" configured. |
| Google (Calendar API) | Calendar event sync via MeetingBaas | OAuth scope `calendar.readonly` (read-only) | No | Tokens held by MeetingBaas, not us | N/A — we delegate to MB | We never hold the Google refresh token. |

## Pre-launch verification checklist

For each vendor, before letting any external user touch the product:

- [ ] **MeetingBaas** — confirm default recording retention; if MB keeps a copy after streaming, call their support to enable zero-retention or explicitly delete `bot_data` after every meeting ends.
- [ ] **AssemblyAI** — in dashboard, opt out of training data usage (account-level setting). This is what makes the streaming zero-retention claim real.
- [ ] **OpenAI** — confirm API tier opt-out is the default; if our project key is on the consumer tier, switch to the API tier and confirm "do not train" status.
- [ ] **Convex** — confirm SOC 2 report is current; sign DPA via Convex billing/legal portal.
- [ ] **Clerk** — sign DPA via Clerk dashboard.
- [ ] **Google Cloud Console** — verify OAuth consent screen status. While in Testing mode we only support Test Users; production sign-off needs verification flow.

## Data sharing matrix per pipeline step

```
Step                     | Vendor(s) reached         | Data shared
-------------------------+----------------------------+--------------------------------
User signs in            | Clerk                      | Email
Connect Google Calendar  | Google → MeetingBaas       | OAuth refresh token (only MB)
List events              | MeetingBaas                | (no user content; cal_id query)
Send bot                 | MeetingBaas                | Meeting URL, callback URL
Bot joins + streams      | MeetingBaas → zelda → AAI  | Audio frames (in-flight only)
Live transcript          | AssemblyAI → zelda → Convex| Redacted text (no audio in our DB)
Notes generation         | OpenAI                     | Redacted transcript text
Notes view/edit          | Convex                     | Stored generated notes
Delete                   | MeetingBaas + Convex       | Delete bot_data, cascade DB rows
```

## Subprocessors (their vendors)

| Our vendor | Their key subprocessors | Why it matters |
| --- | --- | --- |
| MeetingBaas | AWS / GCP for bot compute, Cloudflare for delivery (typical) | Confirm in MB DPA |
| AssemblyAI | AWS | Standard cloud provider chain |
| OpenAI | Microsoft Azure | Standard |
| Convex | AWS | Standard |
| Clerk | AWS | Standard |

## Privacy claim posture

Per compliance plan ("Product Positioning Rule"), we do **not** claim:
- Fully compliant
- Privilege-preserving
- Zero-retention (not until AAI training opt-out + MB recording deletion are
  verified per the checklist above)
- Safe for all jurisdictions

Acceptable language until counsel review:
> Legal Poke is designed with privacy-conscious defaults, explicit recording consent, limited retention of raw audio, and controls to help users manage sensitive legal notes.

## Change log

| Date | Change | Author |
| --- | --- | --- |
| 2026-06-09 | Initial register created | system |
