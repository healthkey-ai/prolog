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

async function request<T>(method: string, path: string, body?: unknown, headers: Record<string, string> = {}): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: { Accept: "application/json; version=1", ...(body !== undefined ? { "Content-Type": "application/json" } : {}), ...headers },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    credentials: "same-origin",
  });
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  const data = text ? JSON.parse(text) : {};
  if (!res.ok) throw new ApiError(res.status, data);
  return data as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, body),
  patch: <T>(path: string, body?: unknown) => request<T>("PATCH", path, body),
};
