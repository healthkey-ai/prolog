import type { ApiErrorBody, ApiIssue } from "./types";
import type { AnswerIssue } from "@/survey/types";

function isIssue(v: unknown): v is ApiIssue {
  return typeof v === "object" && v !== null && typeof (v as ApiIssue).code === "string";
}

export class ApiError extends Error {
  status: number;
  body: ApiErrorBody;
  constructor(status: number, body: ApiErrorBody) {
    super(body.detail ?? `Request failed (${status})`);
    this.status = status;
    this.body = body;
  }
  /** Structured rejections, e.g. from {"value": [{code, params, message}]}; never English text. */
  get issues(): AnswerIssue[] {
    const out: AnswerIssue[] = [];
    for (const [k, v] of Object.entries(this.body)) {
      if (k === "detail" || !Array.isArray(v)) continue;
      for (const item of v) if (isIssue(item)) out.push({ code: item.code, params: item.params ?? {} });
    }
    return out;
  }
  /** Plain field errors as flat strings, e.g. from {"language": "not offered"} */
  get fieldErrors(): string[] {
    const out: string[] = [];
    for (const [k, v] of Object.entries(this.body)) {
      if (k === "detail") continue;
      if (Array.isArray(v)) out.push(...v.filter((x) => !isIssue(x)).map(String));
      else if (typeof v === "string") out.push(v);
    }
    return out;
  }
}

/**
 * The server never answered within the deadline (half-open socket, a proxy
 * that accepted the request and hung). Not an ApiError: there is no status,
 * and callers' retry predicates treat it as transient.
 */
export class ApiTimeoutError extends Error {
  timeoutMs: number;
  constructor(timeoutMs: number) {
    super(`Request timed out after ${timeoutMs} ms`);
    this.name = "ApiTimeoutError";
    this.timeoutMs = timeoutMs;
  }
}

/**
 * The resource no longer exists for this participant: purged (404), or an
 * account session that expired so the stored response id is refused (403).
 */
export const isGone = (e: unknown): boolean => e instanceof ApiError && (e.status === 403 || e.status === 404);
/** The survey has closed (410): nothing to retry. */
export const isClosed = (e: unknown): boolean => e instanceof ApiError && e.status === 410;
/**
 * A definitive answer (any 4xx: gone, closed, forbidden, refused, throttled)
 * that a retry cannot change; 5xx, timeouts and network failures are not.
 */
export const isTerminal = (e: unknown): boolean => e instanceof ApiError && e.status >= 400 && e.status < 500;

const BASE = import.meta.env.VITE_API_BASE ?? "/api/run";
/** Deadline per request; `VITE_API_TIMEOUT_MS` overrides it for a deployment. */
export const DEFAULT_TIMEOUT_MS = Number(import.meta.env.VITE_API_TIMEOUT_MS) || 20_000;

export interface RequestOptions {
  timeoutMs?: number;
}

/** Django's CSRF cookie; session-authenticated (account) participants must echo it on writes. */
function csrfToken(): string | undefined {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : undefined;
}

async function request<T>(method: string, path: string, body?: unknown, { timeoutMs = DEFAULT_TIMEOUT_MS }: RequestOptions = {}): Promise<T> {
  const csrf = method === "GET" ? undefined : csrfToken();
  // A request that never settles would hold every later save of its key (and
  // the Next button) until the browser's own socket timeout, minutes away.
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let res: Response;
  let text: string;
  try {
    res = await fetch(`${BASE}${path}`, {
      method,
      headers: {
        Accept: "application/json; version=1",
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(csrf ? { "X-CSRFToken": csrf } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      credentials: "same-origin",
      signal: controller.signal,
    });
    if (res.status === 204) return undefined as T;
    text = await res.text();
  } catch (err) {
    if (controller.signal.aborted) throw new ApiTimeoutError(timeoutMs);
    throw err;
  } finally {
    clearTimeout(timer);
  }
  let data: unknown;
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    // A proxy error page (HTML 502/504) must still surface as an ApiError with
    // its status; a 2xx that is not JSON (an SPA fallback or captive portal
    // answering for the API) is not a result either, so it is an error too.
    data = { detail: res.ok ? "unexpected_response" : res.statusText || `Request failed (${res.status})` };
    if (res.ok) throw new ApiError(res.status, data as ApiErrorBody);
  }
  if (!res.ok) throw new ApiError(res.status, data as ApiErrorBody);
  return data as T;
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) => request<T>("GET", path, undefined, options),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) => request<T>("POST", path, body, options),
  put: <T>(path: string, body?: unknown, options?: RequestOptions) => request<T>("PUT", path, body, options),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions) => request<T>("PATCH", path, body, options),
};
