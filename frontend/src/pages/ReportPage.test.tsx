import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import { Route, Routes } from "react-router";
import { ReportPage } from "./ReportPage";
import { SLUG, fakeServer, installDom, mount, t, type Mounted } from "./testHarness";

const routes = () =>
  createElement(Routes, null, createElement(Route, { path: "/s/:slug/report", element: createElement(ReportPage) }));

const row = (extra: object) => ({ label: "1.0", version: "1.0", respondents: 40, completions: 30, partials: 10, contacts: 0, completion_rate: 0.75, average_response_time: "5 min 2 s", ...extra });

function report(stats: object) {
  return {
    survey: SLUG, title: "Test survey", version: "1.0", sign_in_available: true, password_change_available: false,
    viewer: { label: "reader@example.org", may_read_responses: true, may_read_contacts: false },
    stats: { min_count: 20, by_day: [], by_language: [], drop_off: [], ...stats },
  };
}

describe("ReportPage (RUN-24)", () => {
  let m: Mounted | null = null;
  beforeEach(() => installDom());
  afterEach(() => {
    m?.unmount();
    m = null;
    vi.unstubAllGlobals();
  });

  it("says 'fewer than N' for a count the deployment does not show, and drops it from the download", async () => {
    const server = fakeServer();
    server.on("GET", `/report/${SLUG}/`, {
      body: report({
        versions: [row({ completions: null, partials: null, completion_rate: null, average_response_time: "—" })],
        by_language: [{ language: "en", respondents: 40, completions: null }],
      }),
    });
    m = mount(`/s/${SLUG}/report`, routes());
    await m.flush();

    const versions = m.$("report-versions")?.textContent ?? "";
    expect(versions).toContain(t("report.fewerThan", { count: 20 }));
    expect(versions).toContain("40");
    expect(m.$("report-languages")?.textContent).toContain(t("report.fewerThan", { count: 20 }));
    expect(m.$("report-download-responses-1.0")?.textContent).toBe(t("report.downloadResponsesFew"));
    expect(m.$("report-download-all-1.0")?.textContent).toBe(t("report.downloadAll", { count: 40 }));
  });

  it("shows every count when none is hidden", async () => {
    const server = fakeServer();
    server.on("GET", `/report/${SLUG}/`, { body: report({ min_count: 0, versions: [row({})] }) });
    m = mount(`/s/${SLUG}/report`, routes());
    await m.flush();

    expect(m.$("report-versions")?.textContent).not.toContain(t("report.fewerThan", { count: 0 }));
    expect(m.$("report-download-responses-1.0")?.textContent).toBe(t("report.downloadResponses", { count: 30 }));
  });
});
