import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { RESPONSE_ID, SLUG, blur, click, deferred, definition, installDom, mount, response, runnerServer, t, type, type Mounted } from "./testHarness";

const ANSWERS = `/responses/${RESPONSE_ID}/answers/`;
const TEXT = (m: Mounted) => m.$<HTMLInputElement>("text-input")!;
const NEXT = (m: Mounted) => m.$<HTMLButtonElement>("next")!;
const BACK = (m: Mounted) => [...m.container.querySelectorAll("button")].find((b) => b.textContent === t("nav.back")) ?? null;
const saved = (value: unknown, key = "q1") => ({ body: { answer: { key, value }, invalidated: [], pruned: {}, visible: ["q1", "q2", "q3"], missing: ["q2", "q3"], progress: { answered: 1, total: 3 } } });

describe("WizardPage", () => {
  let m: Mounted | null = null;
  beforeEach(() => installDom());
  afterEach(() => {
    m?.unmount();
    m = null;
    vi.unstubAllGlobals();
    vi.useRealTimers();
    localStorage.clear();
  });

  it("shows the definition error with a retry when the definition GET fails but the response loaded", async () => {
    const server = runnerServer();
    let fail = true;
    server.on("GET", `/surveys/${SLUG}/`, () => (fail ? { status: 429, body: { detail: "throttled" } } : { body: definition() }));
    m = mount(`/s/${SLUG}/q/q1`);
    await m.flush();
    expect(m.text()).not.toContain(t("app.loading"));
    expect(m.$("definition-error")?.textContent).toContain(t("app.throttled"));
    fail = false;
    click(m.$("definition-retry"));
    await m.flush();
    expect(m.$("question-q1")).not.toBeNull();
  });

  it("offers no retry for a survey that is gone (404) and says why", async () => {
    const server = runnerServer();
    server.on("GET", `/surveys/${SLUG}/`, { status: 404, body: { detail: "no" } });
    m = mount(`/s/${SLUG}/q/q1`);
    await m.flush();
    expect(m.$("definition-error")?.textContent).toContain(t("app.notFound"));
    expect(m.$("definition-retry")).toBeNull();
  });

  it("titles the document with the survey and the step", async () => {
    runnerServer();
    m = mount(`/s/${SLUG}/q/q1`);
    await m.flush();
    expect(document.title).toBe(`Example instrument – ${t("question.eyebrow", { number: 1, total: 3 })}`);
    m.unmount();
    m = null;
    expect(document.title).not.toContain("Example instrument");
  });

  it("records the clearing of an optional answer as a skip so Back cannot bring the old value back", async () => {
    const server = runnerServer(definition(), response({ answers: { q1: { text: "old" } }, last_question_key: "q2" }));
    server.on("PUT", ANSWERS, (call) => saved(call.body && (call.body as { value: unknown }).value));
    m = mount(`/s/${SLUG}/q/q1`);
    await m.flush();
    expect(TEXT(m).value).toBe("old");
    type(TEXT(m), "");
    blur(TEXT(m));
    await m.flush();
    expect(server.of("PUT", ANSWERS).map((c) => c.body)).toEqual([{ value: { skipped: true } }]);
    // Leave and return through the URL (as Back / the overview do): the field stays empty.
    await m.navigate(`/s/${SLUG}/q/q2`);
    await m.navigate(`/s/${SLUG}/q/q1`);
    expect(TEXT(m).value).toBe("");
  });

  it("asks before dropping a cleared required answer on Back, then records the skip and goes back", async () => {
    const server = runnerServer(definition(), response({ answers: { q1: { text: "one" }, q2: { text: "two" } }, last_question_key: "q2" }));
    server.on("PUT", ANSWERS, (call) => saved((call.body as { value: unknown }).value, "q2"));
    m = mount(`/s/${SLUG}/q/q2`);
    await m.flush();
    type(TEXT(m), "");
    blur(TEXT(m));
    await m.flush();
    expect(server.of("PUT", ANSWERS)).toHaveLength(0); // soft policy: nothing recorded yet
    click(BACK(m));
    await m.flush();
    expect(m.pathname()).toBe(`/s/${SLUG}/q/q2`);
    expect(m.container.querySelector("[role=alertdialog]")).not.toBeNull();
    click(m.$("skip-confirm"));
    await m.flush();
    expect(server.of("PUT", ANSWERS).map((c) => c.body)).toEqual([{ value: { skipped: true } }]);
    expect(m.pathname()).toBe(`/s/${SLUG}/q/q1`);
  });

  it("blocks Back on a cleared hard-required answer with the hard-skip message", async () => {
    const server = runnerServer(definition({ presentation: { section_interstitials: false, skip_policy: "hard" } }), response({ answers: { q1: { text: "one" }, q2: { text: "two" } }, last_question_key: "q2" }));
    m = mount(`/s/${SLUG}/q/q2`);
    await m.flush();
    type(TEXT(m), "");
    blur(TEXT(m));
    click(BACK(m));
    await m.flush();
    expect(m.pathname()).toBe(`/s/${SLUG}/q/q2`);
    expect(m.$("error-banner")?.textContent).toContain(t("skip.hard"));
    expect(server.of("PUT", ANSWERS)).toHaveLength(0);
  });

  it("brings the participant back with the message when a save is refused after they moved on", async () => {
    const server = runnerServer();
    const put = deferred();
    server.on("PUT", ANSWERS, () => put.promise);
    m = mount(`/s/${SLUG}/q/q1`);
    await m.flush();
    type(TEXT(m), "hello");
    blur(TEXT(m));
    await m.flush();
    await m.navigate(`/s/${SLUG}/q/q2`); // browser history, while the PUT is still out
    expect(m.$("question-q2")).not.toBeNull();
    put.resolve({ status: 400, body: { value: [{ code: "text_too_long", params: { max: 3 } }] } });
    await m.flush();
    expect(m.pathname()).toBe(`/s/${SLUG}/q/q1`);
    expect(m.$("error-banner")?.textContent).toContain(t("error.text_too_long", { max: 3 }));
  });

  it("shows 'could not save' with a Retry that re-sends the answer after a 5xx", async () => {
    vi.useFakeTimers();
    const server = runnerServer();
    let status = 503;
    server.on("PUT", ANSWERS, (call) => (status === 200 ? saved((call.body as { value: unknown }).value) : { status, body: { detail: "down" } }));
    m = mount(`/s/${SLUG}/q/q1`);
    await m.flush();
    type(TEXT(m), "hello");
    blur(TEXT(m));
    await m.flush();
    await m.flush(3);
    await vi.advanceTimersByTimeAsync(10_000); // the hook's retries with backoff
    await m.flush();
    expect(server.of("PUT", ANSWERS).length).toBeGreaterThan(1);
    expect(m.text()).toContain(t("nav.saveFailed"));
    expect(NEXT(m).disabled).toBe(true);
    status = 200;
    const before = server.of("PUT", ANSWERS).length;
    click([...m.container.querySelectorAll("button")].find((b) => b.textContent === t("app.retry"))!);
    await m.flush();
    expect(server.of("PUT", ANSWERS).length).toBe(before + 1);
    expect(server.of("PUT", ANSWERS).at(-1)?.body).toEqual({ value: { text: "hello" } });
    expect(NEXT(m).disabled).toBe(false);
  });

  it("locks the runner with the closed message when the survey closes mid-response (410)", async () => {
    const server = runnerServer();
    server.on("PUT", ANSWERS, { status: 410, body: { detail: "closed" } });
    m = mount(`/s/${SLUG}/q/q1`);
    await m.flush();
    type(TEXT(m), "hello");
    blur(TEXT(m));
    await m.flush();
    expect(m.text()).toContain(t("app.closed"));
    expect(NEXT(m).disabled).toBe(true);
  });

  it("goes to the first missing question and keeps the alert when submit reports missing answers", async () => {
    const server = runnerServer(definition(), response({ answers: { q1: { text: "a" }, q2: { text: "b" }, q3: { option: "a" } }, last_question_key: "q3", missing: [] }));
    server.on("POST", `/responses/${RESPONSE_ID}/submit/`, { status: 400, body: { missing: ["q2"] } });
    m = mount(`/s/${SLUG}/q/q3`);
    await m.flush();
    expect(NEXT(m).textContent).toBe(t("nav.finish"));
    click(NEXT(m));
    await m.flush();
    expect(m.pathname()).toBe(`/s/${SLUG}/q/q2`);
    expect(m.text()).toContain(t("complete.missing"));
  });

  it("waits for an in-flight blur save before submitting", async () => {
    const server = runnerServer(definition(), response({ answers: { q1: { text: "a" }, q2: { text: "b" } }, last_question_key: "q3" }));
    const put = deferred();
    server.on("PUT", ANSWERS, () => put.promise);
    server.on("POST", `/responses/${RESPONSE_ID}/submit/`, { body: response({ status: "submitted" }) });
    m = mount(`/s/${SLUG}/q/q3`);
    await m.flush();
    click(m.$("option-a"));
    await m.flush();
    click(NEXT(m));
    await m.flush();
    expect(server.of("POST")).toHaveLength(0); // Finish is waiting on the PUT
    put.resolve(saved({ option: "a" }, "q3"));
    await m.flush();
    expect(server.of("POST")).toHaveLength(1);
    expect(m.pathname()).toBe(`/s/${SLUG}/complete`);
  });

  it("says so, with a retry, when a language switch fails", async () => {
    const server = runnerServer();
    let fail = true;
    server.on("PATCH", `/responses/${RESPONSE_ID}/`, (call) => (fail && "language" in (call.body as object) ? { status: 503, body: {} } : { body: { ...response(), ...(call.body as object) } }));
    m = mount(`/s/${SLUG}/q/q1`);
    await m.flush();
    // Radix's listbox does not open in jsdom: fire the Select's onValueChange as a pick would.
    const { onLanguage } = findOnLanguage(m);
    onLanguage("fr");
    await m.flush();
    expect(m.$("language-error")?.textContent).toContain(t("app.error"));
    fail = false;
    click(m.$("language-error")!.querySelector("button"));
    await m.flush();
    expect(m.$("language-error")).toBeNull();
    expect(server.of("PATCH").map((c) => c.body)).toEqual([{ language: "fr" }, { language: "fr" }]);
  });

  it("records deselecting the last multi-choice option as a skip, like clearing a dropdown", async () => {
    const multi = definition();
    multi.sections[1].questions = [{ key: "q3", type: "multi", text: "Pick some", required: false, options: [{ key: "a", label: "A" }, { key: "b", label: "B" }] }];
    const server = runnerServer(multi, response({ answers: { q1: { text: "one" }, q2: { text: "two" }, q3: { options: ["a"] } }, last_question_key: "q3" }));
    server.on("PUT", ANSWERS, (call) => saved((call.body as { value: unknown }).value, "q3"));
    m = mount(`/s/${SLUG}/q/q3`);
    const a = await m.until<HTMLButtonElement>("option-a"); // the multi renderer is code-split
    expect(a.getAttribute("aria-checked")).toBe("true");
    click(a);
    await m.flush();
    expect(server.of("PUT", ANSWERS).map((c) => c.body)).toEqual([{ value: { skipped: true } }]);
    expect(m.$("option-a")!.getAttribute("aria-checked")).toBe("false");
  });

  it("says so, with a retry, when the definition in the new language cannot be fetched after a language switch", async () => {
    const server = runnerServer();
    const fr = definition({ language: "fr" });
    fr.sections[0].questions[0] = { ...fr.sections[0].questions[0], text: "Note facultative" };
    let fail = true;
    server.on("GET", `/surveys/${SLUG}/`, (call) => (call.path.includes("lang=fr") ? (fail ? { status: 503, body: {} } : { body: fr }) : { body: definition() }));
    m = mount(`/s/${SLUG}/q/q1`);
    await m.flush();
    const { onLanguage } = findOnLanguage(m);
    onLanguage("fr");
    await m.flush();
    expect(server.of("PATCH").map((c) => c.body)).toEqual([{ language: "fr" }]);
    // keepPreviousData holds the old localisation only while the re-keyed GET is
    // pending; once it fails there is no data, so the definition error (not a
    // silent snap-back) takes the screen, with its retry.
    expect(m.$("definition-error")?.textContent).toContain(t("app.error"));
    fail = false;
    click(m.$("definition-retry"));
    await m.flush();
    expect(m.$("definition-error")).toBeNull();
    expect(m.$("question-q1")?.textContent).toContain("Note facultative");
    expect(server.of("PATCH")).toHaveLength(1); // the retry refetches the definition; it does not PATCH again
  });

  it("renders a step counter instead of the bar for presentation.progress: steps", async () => {
    runnerServer(definition({ presentation: { section_interstitials: false, progress: "steps" } }));
    m = mount(`/s/${SLUG}/q/q2`);
    await m.flush();
    const steps = m.$("progress-steps")!;
    expect(steps.getAttribute("aria-valuetext")).toBe(t("header.steps", { number: 2, total: 3 }));
    expect(steps.getAttribute("aria-valuenow")).toBe("2");
    expect(m.container.querySelectorAll("[role=progressbar]")).toHaveLength(1);
  });

  it("moves focus to the section heading on the interstitial, and titles the document with the section", async () => {
    const server = runnerServer(definition({ presentation: { section_interstitials: true } }), response({ answers: { q1: { text: "a" } }, last_question_key: "q2" }));
    server.on("PUT", ANSWERS, (call) => saved((call.body as { value: unknown }).value, "q2"));
    m = mount(`/s/${SLUG}/q/q2`);
    await m.flush();
    type(TEXT(m), "two");
    click(NEXT(m));
    await m.flush();
    const interstitial = m.$("interstitial")!;
    expect(interstitial).not.toBeNull();
    expect(document.activeElement).toBe(interstitial.querySelector("h1"));
    expect(document.title).toBe("Example instrument – Second part");
  });
});

/** The wizard's language handler, as the header Select would call it. */
function findOnLanguage(m: Mounted): { onLanguage: (lang: string) => void } {
  const trigger = m.$<HTMLButtonElement>("language-switch")!;
  // Radix Select stores the root's onValueChange on its context, not the DOM; walk React's fiber
  // from the trigger up to the Select root to find the prop the page passed in.
  let fiber = Object.entries(trigger).find(([k]) => k.startsWith("__reactFiber"))?.[1] as { return?: unknown; memoizedProps?: Record<string, unknown> } | undefined;
  while (fiber) {
    const onValueChange = fiber.memoizedProps?.onValueChange;
    if (typeof onValueChange === "function") return { onLanguage: (lang) => act(() => (onValueChange as (l: string) => void)(lang)) };
    fiber = fiber.return as typeof fiber;
  }
  throw new Error("Select root not found");
}
