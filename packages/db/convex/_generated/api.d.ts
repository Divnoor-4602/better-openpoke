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
import type * as integrations_zelda_token from "../integrations/zelda/token.js";
import type * as public_user_queries from "../public/user/queries.js";
import type * as types from "../types.js";
import type * as user_helpers from "../user/helpers.js";
import type * as user_validator from "../user/validator.js";

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
  "integrations/zelda/token": typeof integrations_zelda_token;
  "public/user/queries": typeof public_user_queries;
  types: typeof types;
  "user/helpers": typeof user_helpers;
  "user/validator": typeof user_validator;
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
