import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, createElement } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it } from "vitest";
import i18n from "@/i18n";
import App from "./App";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

describe("App", () => {
  const cleanups: (() => void)[] = [];
  afterEach(() => cleanups.splice(0).forEach((fn) => fn()));

  function render(path: string) {
    const container = document.createElement("div");
    const root = createRoot(container);
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    act(() => root.render(createElement(QueryClientProvider, { client: qc }, createElement(MemoryRouter, { initialEntries: [path] }, createElement(App)))));
    cleanups.push(() => act(() => root.unmount()));
    return container;
  }

  it("renders the home page with the app title", () => {
    const container = render("/");
    expect(container.querySelector("h1")?.textContent).toBe(i18n.t("app.title"));
    expect(container.querySelector("main")?.textContent).toContain("/s/<slug>");
  });

  it("sends an unknown path home", () => {
    const container = render("/nowhere");
    expect(container.querySelector("h1")?.textContent).toBe(i18n.t("app.title"));
  });
});
