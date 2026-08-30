import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, ApiTimeoutError, api, isTerminal } from "./client";

type FetchInit = { signal?: AbortSignal };

/** A fetch stub answering with `body`; a stub that never answers honours the abort signal like the real one. */
function stubFetch(body: string | null, init: ResponseInit = { status: 200 }) {
  return vi.spyOn(globalThis, "fetch").mockImplementation((_url, options?: RequestInit) => {
    if (body === null) {
      return new Promise<Response>((_resolve, reject) => {
        (options as FetchInit | undefined)?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
      });
    }
    return Promise.resolve(new Response(body, init));
  });
}

describe("api client", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it("parses a JSON 2xx", async () => {
    stubFetch('{"id": "r1"}');
    await expect(api.get<{ id: string }>("/responses/r1/")).resolves.toEqual({ id: "r1" });
  });

  it("rejects a 2xx whose body is not JSON (an SPA fallback page) as an ApiError", async () => {
    stubFetch("<!doctype html><html><body>app</body></html>", { status: 200, statusText: "OK" });
    const err = await api.get("/responses/r1/").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(200);
  });

  it("keeps a non-JSON error page as an ApiError with its status", async () => {
    stubFetch("<html>502</html>", { status: 502, statusText: "Bad Gateway" });
    const err = await api.get("/responses/r1/").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(502);
  });

  it("gives up on a request that never answers", async () => {
    vi.useFakeTimers();
    stubFetch(null);
    const pending = api.put("/responses/r1/answers/q1/", { value: { option: "a" } });
    const outcome = pending.catch((e: unknown) => e);
    await vi.advanceTimersByTimeAsync(25_000);
    const err = await outcome;
    expect(err).toBeInstanceOf(ApiTimeoutError);
    expect(err).not.toBeInstanceOf(ApiError); // so useSaveAnswer's retry predicate retries it
  });

  it("honours a per-call timeout", async () => {
    vi.useFakeTimers();
    stubFetch(null);
    const outcome = api.get("/responses/r1/", { timeoutMs: 50 }).catch((e: unknown) => e);
    await vi.advanceTimersByTimeAsync(60);
    expect(await outcome).toBeInstanceOf(ApiTimeoutError);
  });
});

describe("isTerminal", () => {
  it("is true only for a definitive 4xx", () => {
    for (const status of [400, 403, 404, 410, 429]) expect(isTerminal(new ApiError(status, {}))).toBe(true);
    for (const status of [200, 500, 502, 503]) expect(isTerminal(new ApiError(status, {}))).toBe(false);
    expect(isTerminal(new ApiTimeoutError(1))).toBe(false);
    expect(isTerminal(new Error("network"))).toBe(false);
  });
});
