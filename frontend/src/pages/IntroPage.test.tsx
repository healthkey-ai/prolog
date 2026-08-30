import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SLUG, click, definition, installDom, mount, response, runnerServer, t, type Mounted } from "./testHarness";

describe("IntroPage", () => {
  let m: Mounted | null = null;
  beforeEach(() => installDom());
  afterEach(() => {
    m?.unmount();
    m = null;
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it("shows the create failure from 'Start again' although the resume card is still on screen", async () => {
    const server = runnerServer();
    server.on("POST", "/responses/", { status: 429, body: { detail: "throttled" } });
    m = mount(`/s/${SLUG}`);
    await m.flush();
    expect(m.$("resume-card")).not.toBeNull();
    click(m.$("start-again"));
    await m.flush();
    click(m.$doc("start-again-confirm"));
    await m.flush();
    expect(server.of("POST", "/responses/")).toHaveLength(1);
    expect(m.$("resume-card")).not.toBeNull();
    expect(m.$("create-error")?.textContent).toContain(t("app.throttled"));
  });

  it("confirms 'Start again' in an alert dialog, not a browser confirm box", async () => {
    const confirmSpy = vi.spyOn(window, "confirm");
    const server = runnerServer();
    m = mount(`/s/${SLUG}`);
    await m.flush();
    expect(m.$doc("start-again-dialog")).toBeNull();

    click(m.$("start-again"));
    await m.flush();
    const dialog = m.$doc("start-again-dialog");
    expect(dialog).not.toBeNull();
    expect(dialog?.getAttribute("role")).toBe("alertdialog");
    expect(dialog?.textContent).toContain(t("intro.startAgainConfirm"));
    // Cancelling discards nothing.
    click(m.$doc("start-again-cancel"));
    await m.flush();
    expect(server.of("POST", "/responses/")).toHaveLength(0);

    click(m.$("start-again"));
    await m.flush();
    click(m.$doc("start-again-confirm"));
    await m.flush();
    expect(server.of("POST", "/responses/")).toHaveLength(1);
    expect(confirmSpy).not.toHaveBeenCalled();
  });

  it("shows the create failure from 'Start a new response' on a submitted response", async () => {
    const server = runnerServer(definition(), response({ status: "submitted" }));
    server.on("POST", "/responses/", { status: 500, body: {} });
    m = mount(`/s/${SLUG}`);
    await m.flush();
    click(m.$("start-new"));
    await m.flush();
    expect(m.$("create-error")?.textContent).toContain(t("app.error"));
  });

  it("links the privacy notice only for an http(s) URL", async () => {
    const consent = { version: "1", text: "We store your answers.", privacy_url: "javascript:alert(1)" };
    runnerServer(definition({ consent }));
    localStorage.clear();
    m = mount(`/s/${SLUG}`);
    await m.flush();
    expect(m.container.querySelector("a[href]")).toBeNull();
    m.unmount();
    runnerServer(definition({ consent: { ...consent, privacy_url: "https://example.org/privacy" } }));
    m = mount(`/s/${SLUG}`);
    await m.flush();
    expect(m.container.querySelector("a[href]")?.getAttribute("href")).toBe("https://example.org/privacy");
    expect(document.title).toBe("Example instrument");
  });

  it("offers a retry when the definition fails to load", async () => {
    const server = runnerServer();
    let fail = true;
    server.on("GET", `/surveys/${SLUG}/`, () => (fail ? { status: 503, body: {} } : { body: definition() }));
    localStorage.clear();
    m = mount(`/s/${SLUG}`);
    await m.flush();
    expect(m.$("definition-error")?.textContent).toContain(t("app.error"));
    fail = false;
    click(m.$("definition-retry"));
    await m.flush();
    expect(m.$("start")).not.toBeNull();
  });
});
