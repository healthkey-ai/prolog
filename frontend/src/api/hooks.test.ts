import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, createElement } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, ApiTimeoutError, api } from "./client";
import { SupersededError, applyAnswerResult, keys, mergePatched, revertAnswer, usePatchResponse, useSaveAnswer, withEmailProvided } from "./hooks";
import type { AnswerResult, ResponseSummary } from "./types";

const base: ResponseSummary = {
  id: "r1",
  slug: "s",
  version: "1",
  language: "en",
  status: "in_progress",
  started_at: "2026-01-01T00:00:00Z",
  submitted_at: null,
  last_question_key: "q1",
  administration: null,
  answers: { q1: { option: "a" }, q2: { text: "hello" } },
  visible: ["q1", "q2", "q3"],
  missing: ["q3"],
  progress: { answered: 2, total: 3 },
};

const result = (value: AnswerResult["answer"]["value"], extra: Partial<AnswerResult> = {}): AnswerResult => ({
  answer: { key: "q1", value },
  invalidated: [],
  pruned: {},
  visible: ["q1", "q3"],
  missing: [],
  progress: { answered: 2, total: 2 },
  ...extra,
});

describe("applyAnswerResult", () => {
  it("stores the saved value and the server's cascade outcome", () => {
    const next = applyAnswerResult(base, "q1", result({ option: "b" }, { invalidated: ["q2"], pruned: { q3: { text: "kept" } } }));
    expect(next.answers).toEqual({ q1: { option: "b" }, q3: { text: "kept" } });
    expect(next.visible).toEqual(["q1", "q3"]);
    expect(next.missing).toEqual([]);
    expect(next.progress).toEqual({ answered: 2, total: 2 });
    expect(next.last_question_key).toBe("q1");
    expect(base.answers.q2).toEqual({ text: "hello" }); // input untouched
  });
});

describe("revertAnswer", () => {
  it("restores only the failed key's previous value", () => {
    const optimistic = { ...base, answers: { ...base.answers, q1: { option: "z" }, q2: { text: "newer" } } };
    const next = revertAnswer(optimistic, "q1", { previous: { option: "a" }, had: true });
    expect(next.answers).toEqual({ q1: { option: "a" }, q2: { text: "newer" } });
  });
  it("removes the key when there was no previous value", () => {
    const optimistic = { ...base, answers: { ...base.answers, q3: { option: "x" } } };
    const next = revertAnswer(optimistic, "q3", { previous: undefined, had: false });
    expect(next.answers).toEqual(base.answers);
  });
});

describe("mergePatched", () => {
  const server = { ...base, language: "en", last_question_key: "q2" };
  it("takes only the fields the PATCH set", () => {
    const switched = { ...base, language: "fr" };
    expect(mergePatched(switched, { last_question_key: "q2" }, server)).toEqual({ ...switched, last_question_key: "q2" });
    expect(mergePatched(base, { language: "fr" }, { ...server, language: "fr" })).toEqual({ ...base, language: "fr" });
  });
});

describe("withEmailProvided", () => {
  it("marks the email question answered and no longer missing", () => {
    const next = withEmailProvided({ ...base, missing: ["q3", "email"] }, "email");
    expect(next.answers.email).toEqual({ provided: true });
    expect(next.missing).toEqual(["q3"]);
  });
});

describe("useSaveAnswer", () => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  const cleanups: (() => void)[] = [];
  afterEach(() => {
    cleanups.splice(0).forEach((fn) => fn());
    vi.restoreAllMocks();
  });

  function deferred<T>() {
    let resolve!: (value: T) => void;
    let reject!: (reason: unknown) => void;
    const promise = new Promise<T>((res, rej) => {
      resolve = res;
      reject = rej;
    });
    return { promise, resolve, reject };
  }

  /**
   * Mount the hook under a QueryClient seeded with `base`; returns the hook's latest value.
   * `retry: true` keeps the hook's own retry predicate and backoff (use fake timers and `tick`).
   */
  function mount({ retry = false } = {}) {
    const qc = new QueryClient({ defaultOptions: { mutations: retry ? {} : { retry: false } } });
    qc.setQueryData(keys.response("r1"), base);
    const hook: { current: ReturnType<typeof useSaveAnswer> | null } = { current: null };
    function Harness() {
      hook.current = useSaveAnswer("r1");
      return null;
    }
    const root = createRoot(document.createElement("div"));
    act(() => root.render(createElement(QueryClientProvider, { client: qc }, createElement(Harness))));
    cleanups.push(() => act(() => root.unmount()));
    const save = (value: AnswerResult["answer"]["value"]) => {
      let p!: Promise<AnswerResult>;
      act(() => {
        p = hook.current!.mutateAsync({ key: "q1", value });
        p.catch(() => undefined); // outcomes are asserted explicitly below
      });
      return p;
    };
    const settle = () => act(async () => new Promise<void>((r) => setTimeout(r, 0)));
    /** Under fake timers: let `ms` elapse (the retry backoff) and flush what it triggered. */
    const tick = (ms: number) => act(() => vi.advanceTimersByTimeAsync(ms));
    const cached = () => qc.getQueryData<ResponseSummary>(keys.response("r1"))!.answers.q1;
    return { save, settle, tick, cached };
  }

  it("sends a save of a key only after the previous save of that key has settled", async () => {
    const first = deferred<AnswerResult>();
    const second = deferred<AnswerResult>();
    const put = vi.spyOn(api, "put").mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    const { save, settle, cached } = mount();
    const a = save({ option: "b" });
    await settle();
    expect(put).toHaveBeenCalledTimes(1);
    const b = save({ option: "c" });
    await settle();
    expect(put).toHaveBeenCalledTimes(1); // queued behind the first, not on the wire
    first.resolve(result({ option: "b" }));
    await expect(a).rejects.toBeInstanceOf(SupersededError);
    await settle();
    expect(put).toHaveBeenCalledTimes(2);
    expect(put).toHaveBeenLastCalledWith("/responses/r1/answers/q1/", { value: { option: "c" } });
    second.resolve(result({ option: "c" }));
    await b;
    await settle();
    expect(cached()).toEqual({ option: "c" });
  });

  it("reverts a failed save to the latest persisted value, not to the value before the run", async () => {
    const first = deferred<AnswerResult>();
    const second = deferred<AnswerResult>();
    vi.spyOn(api, "put").mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    const { save, settle, cached } = mount();
    const a = save({ option: "b" }); // V1
    await settle();
    const b = save({ option: "c" }); // V2
    await settle();
    expect(cached()).toEqual({ option: "c" }); // optimistic
    first.resolve(result({ option: "b" })); // V1 persisted while V2 is outstanding
    await expect(a).rejects.toBeInstanceOf(SupersededError);
    await settle();
    second.reject(new ApiError(400, { detail: "refused" }));
    await expect(b).rejects.toBeInstanceOf(ApiError);
    await settle();
    expect(cached()).toEqual({ option: "b" }); // V1, not the pre-run V0 {option: "a"}
  });

  it.each([
    ["a 5xx", () => new ApiError(503, { detail: "unavailable" })],
    ["a timeout", () => new ApiTimeoutError(1)],
  ])("retries %s with backoff and applies the eventual result", async (_what, failure) => {
    vi.useFakeTimers();
    const put = vi.spyOn(api, "put").mockRejectedValueOnce(failure()).mockResolvedValueOnce(result({ option: "b" }));
    const { save, tick, cached } = mount({ retry: true });
    const a = save({ option: "b" });
    await tick(0);
    expect(put).toHaveBeenCalledTimes(1);
    expect(cached()).toEqual({ option: "b" }); // optimistic value stays through the backoff
    await tick(1000);
    expect(put).toHaveBeenCalledTimes(2);
    await expect(a).resolves.toEqual(result({ option: "b" }));
    await tick(0);
    expect(cached()).toEqual({ option: "b" });
    vi.useRealTimers();
  });

  it("does not retry a save that a newer save overtook during the backoff", async () => {
    vi.useFakeTimers();
    const second = deferred<AnswerResult>();
    const put = vi.spyOn(api, "put").mockRejectedValueOnce(new ApiError(503, { detail: "unavailable" })).mockReturnValueOnce(second.promise);
    const { save, tick, cached } = mount({ retry: true });
    const a = save({ option: "b" }); // V1: fails, TanStack schedules a retry
    await tick(0);
    expect(put).toHaveBeenCalledTimes(1);
    const b = save({ option: "c" }); // V2, issued while V1 waits for its retry
    await tick(0);
    expect(put).toHaveBeenCalledTimes(2);
    expect(put).toHaveBeenLastCalledWith("/responses/r1/answers/q1/", { value: { option: "c" } });
    await tick(8000); // every backoff V1 could take: its retry must never reach the wire
    expect(put).toHaveBeenCalledTimes(2);
    second.resolve(result({ option: "c" }));
    await expect(b).resolves.toEqual(result({ option: "c" }));
    await expect(a).rejects.toBeInstanceOf(SupersededError);
    await tick(0);
    expect(put).toHaveBeenCalledTimes(2);
    expect(cached()).toEqual({ option: "c" });
    vi.useRealTimers();
  });

  it("surfaces a timed-out save as a failure once retries are exhausted", async () => {
    vi.useFakeTimers();
    const put = vi.spyOn(api, "put").mockRejectedValue(new ApiTimeoutError(1));
    const { save, tick, cached } = mount({ retry: true });
    const a = save({ option: "b" });
    const outcome = a.catch((e: unknown) => e);
    await tick(0);
    await tick(1000);
    await tick(2000);
    await tick(4000);
    expect(put).toHaveBeenCalledTimes(4);
    expect(await outcome).toBeInstanceOf(ApiTimeoutError);
    await tick(0);
    expect(cached()).toEqual({ option: "a" }); // reverted
    vi.useRealTimers();
  });
});

describe("usePatchResponse", () => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  const cleanups: (() => void)[] = [];
  afterEach(() => {
    cleanups.splice(0).forEach((fn) => fn());
    vi.restoreAllMocks();
  });

  function deferred<T>() {
    let resolve!: (value: T) => void;
    let reject!: (reason: unknown) => void;
    const promise = new Promise<T>((res, rej) => {
      resolve = res;
      reject = rej;
    });
    return { promise, resolve, reject };
  }

  function mount() {
    const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
    qc.setQueryData(keys.response("r1"), base);
    const hook: { current: ReturnType<typeof usePatchResponse> | null } = { current: null };
    function Harness() {
      hook.current = usePatchResponse("r1");
      return null;
    }
    const root = createRoot(document.createElement("div"));
    act(() => root.render(createElement(QueryClientProvider, { client: qc }, createElement(Harness))));
    cleanups.push(() => act(() => root.unmount()));
    const patch = (body: Parameters<ReturnType<typeof usePatchResponse>["mutateAsync"]>[0]) => {
      let p!: ReturnType<ReturnType<typeof usePatchResponse>["mutateAsync"]>;
      act(() => {
        p = hook.current!.mutateAsync(body);
        p.catch(() => undefined);
      });
      return p;
    };
    const settle = () => act(async () => new Promise<void>((r) => setTimeout(r, 0)));
    const cached = () => qc.getQueryData<ResponseSummary>(keys.response("r1"))!;
    return { patch, settle, cached };
  }

  it("sends language switches one at a time and only the latest one touches the cache", async () => {
    const first = deferred<{ language: string; last_question_key: string }>();
    const second = deferred<{ language: string; last_question_key: string }>();
    const call = vi.spyOn(api, "patch").mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    const { patch, settle, cached } = mount();
    const fr = patch({ language: "fr" });
    await settle();
    expect(call).toHaveBeenCalledTimes(1);
    const pt = patch({ language: "pt" });
    await settle();
    expect(call).toHaveBeenCalledTimes(1); // queued behind the first
    first.resolve({ language: "fr", last_question_key: "q1" }); // the older reply
    await expect(fr).rejects.toBeInstanceOf(SupersededError);
    await settle();
    expect(cached().language).toBe("en"); // not applied
    expect(call).toHaveBeenCalledTimes(2);
    expect(call).toHaveBeenLastCalledWith("/responses/r1/", { language: "pt" });
    second.resolve({ language: "pt", last_question_key: "q1" });
    await pt;
    await settle();
    expect(cached().language).toBe("pt");
  });

  it("does not let a language switch supersede a position update", async () => {
    const first = deferred<{ language: string; last_question_key: string }>();
    const second = deferred<{ language: string; last_question_key: string }>();
    vi.spyOn(api, "patch").mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    const { patch, settle, cached } = mount();
    const pos = patch({ last_question_key: "q2" });
    const lang = patch({ language: "fr" });
    await settle();
    first.resolve({ language: "en", last_question_key: "q2" });
    await pos;
    await settle();
    second.resolve({ language: "fr", last_question_key: "q2" });
    await lang;
    await settle();
    expect(cached()).toMatchObject({ language: "fr", last_question_key: "q2" });
  });
});
