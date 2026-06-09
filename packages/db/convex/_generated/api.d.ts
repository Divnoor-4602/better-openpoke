/* eslint-disable */
/**
 * Generated `api` utility.
 *
 * THIS CODE IS AUTOMATICALLY GENERATED.
 *
 * To regenerate, run `npx convex dev`.
 * @module
 */

import type * as api_ from "../api.js";
import type * as audit_event_mutations from "../audit_event/mutations.js";
import type * as audit_event_validators from "../audit_event/validators.js";
import type * as auth from "../auth.js";
import type * as calendar_connection_mutations from "../calendar_connection/mutations.js";
import type * as calendar_connection_queries from "../calendar_connection/queries.js";
import type * as calendar_connection_validators from "../calendar_connection/validators.js";
import type * as calendar_event_validators from "../calendar_event/validators.js";
import type * as compliance_consent from "../compliance/consent.js";
import type * as crons from "../crons.js";
import type * as error from "../error.js";
import type * as http from "../http.js";
import type * as integrations_agent_actions from "../integrations/agent/actions.js";
import type * as integrations_agent_base from "../integrations/agent/base.js";
import type * as integrations_clerk_user from "../integrations/clerk/user.js";
import type * as integrations_google_client from "../integrations/google/client.js";
import type * as integrations_google_index from "../integrations/google/index.js";
import type * as integrations_google_oauth_functions from "../integrations/google/oauth/functions.js";
import type * as integrations_google_oauth_oauth from "../integrations/google/oauth/oauth.js";
import type * as integrations_meetingbaas_bots_bots from "../integrations/meetingbaas/bots/bots.js";
import type * as integrations_meetingbaas_bots_functions from "../integrations/meetingbaas/bots/functions.js";
import type * as integrations_meetingbaas_calendar_calendar from "../integrations/meetingbaas/calendar/calendar.js";
import type * as integrations_meetingbaas_calendar_functions from "../integrations/meetingbaas/calendar/functions.js";
import type * as integrations_meetingbaas_client from "../integrations/meetingbaas/client.js";
import type * as integrations_meetingbaas_index from "../integrations/meetingbaas/index.js";
import type * as integrations_zelda_client from "../integrations/zelda/client.js";
import type * as integrations_zelda_index from "../integrations/zelda/index.js";
import type * as integrations_zelda_sessions_functions from "../integrations/zelda/sessions/functions.js";
import type * as integrations_zelda_sessions_sessions from "../integrations/zelda/sessions/sessions.js";
import type * as integrations_zelda_token from "../integrations/zelda/token.js";
import type * as meeting_actions from "../meeting/actions.js";
import type * as meeting_jobs from "../meeting/jobs.js";
import type * as meeting_mutations from "../meeting/mutations.js";
import type * as meeting_queries from "../meeting/queries.js";
import type * as meeting_validators from "../meeting/validators.js";
import type * as meeting_notes_actions from "../meeting_notes/actions.js";
import type * as meeting_notes_mutations from "../meeting_notes/mutations.js";
import type * as meeting_notes_validators from "../meeting_notes/validators.js";
import type * as meeting_transcription_turn_validators from "../meeting_transcription_turn/validators.js";
import type * as oauth_state_mutations from "../oauth_state/mutations.js";
import type * as oauth_state_validators from "../oauth_state/validators.js";
import type * as public_calendar_actions from "../public/calendar/actions.js";
import type * as public_calendar_mutations from "../public/calendar/mutations.js";
import type * as public_calendar_queries from "../public/calendar/queries.js";
import type * as public_meeting_actions from "../public/meeting/actions.js";
import type * as public_meeting_mutations from "../public/meeting/mutations.js";
import type * as public_meeting_queries from "../public/meeting/queries.js";
import type * as public_meeting_notes_mutations from "../public/meeting_notes/mutations.js";
import type * as public_meeting_notes_queries from "../public/meeting_notes/queries.js";
import type * as public_user_queries from "../public/user/queries.js";
import type * as types from "../types.js";
import type * as user_helpers from "../user/helpers.js";
import type * as user_validators from "../user/validators.js";

import type {
  ApiFromModules,
  FilterApi,
  FunctionReference,
} from "convex/server";

declare const fullApi: ApiFromModules<{
  api: typeof api_;
  "audit_event/mutations": typeof audit_event_mutations;
  "audit_event/validators": typeof audit_event_validators;
  auth: typeof auth;
  "calendar_connection/mutations": typeof calendar_connection_mutations;
  "calendar_connection/queries": typeof calendar_connection_queries;
  "calendar_connection/validators": typeof calendar_connection_validators;
  "calendar_event/validators": typeof calendar_event_validators;
  "compliance/consent": typeof compliance_consent;
  crons: typeof crons;
  error: typeof error;
  http: typeof http;
  "integrations/agent/actions": typeof integrations_agent_actions;
  "integrations/agent/base": typeof integrations_agent_base;
  "integrations/clerk/user": typeof integrations_clerk_user;
  "integrations/google/client": typeof integrations_google_client;
  "integrations/google/index": typeof integrations_google_index;
  "integrations/google/oauth/functions": typeof integrations_google_oauth_functions;
  "integrations/google/oauth/oauth": typeof integrations_google_oauth_oauth;
  "integrations/meetingbaas/bots/bots": typeof integrations_meetingbaas_bots_bots;
  "integrations/meetingbaas/bots/functions": typeof integrations_meetingbaas_bots_functions;
  "integrations/meetingbaas/calendar/calendar": typeof integrations_meetingbaas_calendar_calendar;
  "integrations/meetingbaas/calendar/functions": typeof integrations_meetingbaas_calendar_functions;
  "integrations/meetingbaas/client": typeof integrations_meetingbaas_client;
  "integrations/meetingbaas/index": typeof integrations_meetingbaas_index;
  "integrations/zelda/client": typeof integrations_zelda_client;
  "integrations/zelda/index": typeof integrations_zelda_index;
  "integrations/zelda/sessions/functions": typeof integrations_zelda_sessions_functions;
  "integrations/zelda/sessions/sessions": typeof integrations_zelda_sessions_sessions;
  "integrations/zelda/token": typeof integrations_zelda_token;
  "meeting/actions": typeof meeting_actions;
  "meeting/jobs": typeof meeting_jobs;
  "meeting/mutations": typeof meeting_mutations;
  "meeting/queries": typeof meeting_queries;
  "meeting/validators": typeof meeting_validators;
  "meeting_notes/actions": typeof meeting_notes_actions;
  "meeting_notes/mutations": typeof meeting_notes_mutations;
  "meeting_notes/validators": typeof meeting_notes_validators;
  "meeting_transcription_turn/validators": typeof meeting_transcription_turn_validators;
  "oauth_state/mutations": typeof oauth_state_mutations;
  "oauth_state/validators": typeof oauth_state_validators;
  "public/calendar/actions": typeof public_calendar_actions;
  "public/calendar/mutations": typeof public_calendar_mutations;
  "public/calendar/queries": typeof public_calendar_queries;
  "public/meeting/actions": typeof public_meeting_actions;
  "public/meeting/mutations": typeof public_meeting_mutations;
  "public/meeting/queries": typeof public_meeting_queries;
  "public/meeting_notes/mutations": typeof public_meeting_notes_mutations;
  "public/meeting_notes/queries": typeof public_meeting_notes_queries;
  "public/user/queries": typeof public_user_queries;
  types: typeof types;
  "user/helpers": typeof user_helpers;
  "user/validators": typeof user_validators;
}>;

/**
 * A utility for referencing Convex functions in your app's public API.
 *
 * Usage:
 * ```js
 * const myFunctionReference = api.myModule.myFunction;
 * ```
 */
export declare const api: FilterApi<
  typeof fullApi,
  FunctionReference<any, "public">
>;

/**
 * A utility for referencing Convex functions in your app's internal API.
 *
 * Usage:
 * ```js
 * const myFunctionReference = internal.myModule.myFunction;
 * ```
 */
export declare const internal: FilterApi<
  typeof fullApi,
  FunctionReference<any, "internal">
>;

export declare const components: {
  agent: import("@convex-dev/agent/_generated/component.js").ComponentApi<"agent">;
};
