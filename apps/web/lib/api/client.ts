import createClient from "openapi-fetch";

import type { paths } from "./schema";

/**
 * Typed REST client generated from the API's OpenAPI document (`pnpm --filter web gen:api`).
 * Requests are same-origin (`/api/v1/...` is rewritten to the API by next.config.ts), so the session cookie
 * travels automatically.
 */
export const api = createClient<paths>({ baseUrl: "" });

/** An API error with FastAPI's `{"detail": ...}` turned into one readable sentence. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: unknown,
  ) {
    super(describeDetail(status, detail));
    this.name = "ApiError";
  }
}

type ValidationItem = { loc?: (string | number)[]; msg?: string };

function describeDetail(status: number, detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    // 422 from request validation: "title: String should have at least 1 character"
    return (detail as ValidationItem[])
      .map((d) => {
        const field = d.loc?.filter((p) => p !== "body").join(".");
        return field ? `${field}: ${d.msg}` : (d.msg ?? "Invalid input");
      })
      .join("; ");
  }
  if (detail && typeof detail === "object" && "message" in detail) return String(detail.message);
  if (status === 401) return "Your session has ended. Please sign in again.";
  if (status === 403) return "You don't have access to this.";
  return `Request failed (${status})`;
}

type FetchResult<T> = { data?: T; error?: unknown; response: Response };

/** Resolve an openapi-fetch call to its data and status, or throw an ApiError. */
export async function unwrapWithStatus<T>(call: Promise<FetchResult<T>>): Promise<{ data: T; status: number }> {
  const { data, error, response } = await call;
  if (!response.ok) {
    const detail = error && typeof error === "object" && "detail" in error ? error.detail : error;
    throw new ApiError(response.status, detail);
  }
  return { data: data as T, status: response.status };
}

/** Resolve an openapi-fetch call to its data, or throw an ApiError. */
export async function unwrap<T>(call: Promise<FetchResult<T>>): Promise<T> {
  return (await unwrapWithStatus(call)).data;
}

export function isApiError(error: unknown, status?: number): error is ApiError {
  return error instanceof ApiError && (status === undefined || error.status === status);
}
