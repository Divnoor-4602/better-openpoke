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
import type * as auth from "../auth.js";
import type * as error from "../error.js";
import type * as http from "../http.js";
import type * as integrations_agent_actions from "../integrations/agent/actions.js";
import type * as integrations_agent_base from "../integrations/agent/base.js";
import type * as integrations_clerk_user from "../integrations/clerk/user.js";
import type * as integrations_zelda_client from "../integrations/zelda/client.js";
import type * as integrations_zelda_index from "../integrations/zelda/index.js";
import type * as integrations_zelda_sessions_functions from "../integrations/zelda/sessions/functions.js";
import type * as integrations_zelda_sessions_sessions from "../integrations/zelda/sessions/sessions.js";
import type * as integrations_zelda_token from "../integrations/zelda/token.js";
import type * as meeting_validators from "../meeting/validators.js";
import type * as meeting_transcription_turn_validators from "../meeting_transcription_turn/validators.js";
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
  auth: typeof auth;
  error: typeof error;
  http: typeof http;
  "integrations/agent/actions": typeof integrations_agent_actions;
  "integrations/agent/base": typeof integrations_agent_base;
  "integrations/clerk/user": typeof integrations_clerk_user;
  "integrations/zelda/client": typeof integrations_zelda_client;
  "integrations/zelda/index": typeof integrations_zelda_index;
  "integrations/zelda/sessions/functions": typeof integrations_zelda_sessions_functions;
  "integrations/zelda/sessions/sessions": typeof integrations_zelda_sessions_sessions;
  "integrations/zelda/token": typeof integrations_zelda_token;
  "meeting/validators": typeof meeting_validators;
  "meeting_transcription_turn/validators": typeof meeting_transcription_turn_validators;
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
