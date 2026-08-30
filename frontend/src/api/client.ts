import type { ApiErrorBody } from "./types";

export class ApiError extends Error {
  status: number;
  body: ApiErrorBody;
  constructor(status: number, body: ApiErrorBody) {
    super(body.detail ?? `Request failed (${status})`);
    this.status = status;
    this.body = body;
  }
  /** Field errors as flat strings, e.g. from {"value": ["..."]} */
  get fieldErrors(): string[] {
    const out: string[] = [];
    for (const [k, v] of Object.entries(this.body)) {
      if (k === "detail") continue;
      if (Array.isArray(v)) out.push(...v.map(String));
      else if (typeof v === "string") out.push(v);
    }
    return out;
  }
}

const BASE = import.meta.env.VITE_API_BASE ?? "/api/run";

/** Django's CSRF cookie; session-authenticated (account) participants must echo it on writes. */
function csrfToken(): string | undefined {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : undefined;
}

async function request<T>(method: string, path: string, body?: unknown, headers: Record<string, string> = {}): Promise<T> {
  const csrf = method === "GET" ? undefined : csrfToken();
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: {
      Accept: "application/json; version=1",
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(csrf ? { "X-CSRFToken": csrf } : {}),
      ...headers,
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    credentials: "same-origin",
  });
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let data: unknown = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    // A proxy error page (HTML 502/504) must still surface as an ApiError with its status.
    data = { detail: res.statusText || `Request failed (${res.status})` };
  }
  if (!res.ok) throw new ApiError(res.status, data as ApiErrorBody);
  return data as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, body),
  patch: <T>(path: string, body?: unknown) => request<T>("PATCH", path, body),
};
