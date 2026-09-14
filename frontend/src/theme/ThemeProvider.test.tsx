import { beforeEach, describe, expect, it } from "vitest";
import { deferred, fakeServer, installDom, mount, SLUG, definition, themedRoutes } from "@/pages/testHarness";

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
    // The theme is held back by hand rather than by timing, so "nothing yet"
    // is a fact about the provider and not about how fast this machine is.
    const theme = deferred();
    server.on("GET", "/themes/default/", () => theme.promise);

    const m = mount(`/s/${SLUG}`, themedRoutes());
    await m.flush(6);
    expect(m.text()).toBe("");

    theme.resolve({ body: { code: "default", colors: { light: {} } } });
    await m.flush(12);
    expect(m.text()).toContain("Example instrument");
    expect(server.of("GET", "/surveys/").length).toBeLessThanOrEqual(3);
  });
});

describe("the logo's size is the theme's to set", () => {
  beforeEach(() => {
    installDom();
    localStorage.clear();
  });

  it("uses the intro height on the intro and the header height elsewhere, defaulting to 2rem", async () => {
    const server = fakeServer();
    server.on("GET", `/surveys/${SLUG}/`, { body: definition() });
    server.on("GET", "/themes/default/", {
      body: { code: "default", colors: { light: {} }, assets: { logo: "/logo.png" }, layout: { logo_height: "56px", intro_logo_height: "96px" } },
    });

    const m = mount(`/s/${SLUG}`, themedRoutes());
    await m.flush(12);

    // The theme's intro height is a ceiling: a short viewport gives the logo a tenth of itself.
    expect(m.$<HTMLImageElement>("theme-logo")?.style.height).toBe("min(96px, max(10dvh, 2.75rem))");
  });

  it("falls back to the header height on the intro when no intro height is given", async () => {
    const server = fakeServer();
    server.on("GET", `/surveys/${SLUG}/`, { body: definition() });
    server.on("GET", "/themes/default/", { body: { code: "default", colors: { light: {} }, assets: { logo: "/logo.png" }, layout: { logo_height: "3rem" } } });

    const m = mount(`/s/${SLUG}`, themedRoutes());
    await m.flush(12);

    expect(m.$<HTMLImageElement>("theme-logo")?.style.height).toBe("min(3rem, max(10dvh, 2.75rem))");
  });
});
