import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SLUG, definition, installDom, mount, response, runnerServer, t, type Mounted } from "./testHarness";

describe("CompletePage", () => {
  let m: Mounted | null = null;
  beforeEach(() => installDom());
  afterEach(() => {
    m?.unmount();
    m = null;
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it("thanks the participant only for a submitted response, and titles the document", async () => {
    runnerServer(definition(), response({ status: "submitted", submitted_at: "2026-01-02T00:00:00Z" }));
    m = mount(`/s/${SLUG}/complete`);
    await m.flush();
    expect(m.$("complete")).not.toBeNull();
    expect(m.text()).toContain(t("complete.readonly"));
    expect(document.title).toBe(`Example instrument – ${t("complete.title")}`);
  });

  it("sends an in-progress response (browser Back after 'Start a new response') to its resume point", async () => {
    runnerServer(definition(), response({ answers: { q1: { text: "a" } }, last_question_key: "q1" }));
    m = mount(`/s/${SLUG}/complete`);
    await m.flush();
    expect(m.$("complete")).toBeNull();
    expect(m.pathname()).toBe(`/s/${SLUG}/q/q2`);
  });

  it("sends a visitor with no stored response to the intro", async () => {
    runnerServer();
    localStorage.clear();
    m = mount(`/s/${SLUG}/complete`);
    await m.flush();
    expect(m.pathname()).toBe(`/s/${SLUG}`);
    expect(m.text()).not.toContain(t("complete.readonly"));
  });
});
