import { beforeEach, describe, expect, it } from "vitest";
import { fakeServer, installDom, mount, SLUG, definition, themedRoutes } from "@/pages/testHarness";

describe("ThemeProvider decides when the pages appear", () => {
  beforeEach(() => {
    installDom();
    localStorage.clear();
  });

  it("shows the survey's own message when there is no active version", async () => {
    // What an administrator gets from loading a definition and not activating
    // it: the API answers 404 "survey is not active".
    const server = fakeServer();
    server.on("GET", `/surveys/${SLUG}/`, { status: 404, body: { detail: "survey is not active" } });

    const m = mount(`/s/${SLUG}`, themedRoutes());
    await m.flush(12);

    expect(m.$("definition-error")).not.toBeNull();
    // Two mounts of one query, not a storm: the pages used to unmount whenever
    // the definition refetched, and remounting refetched it again.
    expect(server.calls.length).toBeLessThanOrEqual(3);
  });

  it("waits for the theme before rendering, so nothing flashes unthemed", async () => {
    const server = fakeServer();
    server.on("GET", `/surveys/${SLUG}/`, { body: definition() });
    server.on("GET", "/themes/default/", { body: { code: "default", colors: { light: {} } } });

    const m = mount(`/s/${SLUG}`, themedRoutes());
    await m.flush(1);
    expect(m.text()).toBe("");

    await m.flush(12);
    expect(m.text()).toContain("Example instrument");
    expect(server.of("GET", "/surveys/").length).toBeLessThanOrEqual(3);
  });
});
