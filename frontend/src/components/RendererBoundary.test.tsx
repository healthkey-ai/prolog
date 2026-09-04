import { act, createElement } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import i18n from "@/i18n";
import { RendererBoundary } from "./RendererBoundary";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

function Broken(): never {
  throw new Error("Failed to fetch dynamically imported module");
}

describe("RendererBoundary", () => {
  const cleanups: (() => void)[] = [];
  afterEach(() => {
    cleanups.splice(0).forEach((fn) => fn());
    vi.restoreAllMocks();
  });

  it("replaces a renderer that throws (a stale chunk) with the message and a reload action", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined); // React logs the caught error
    const onReload = vi.fn();
    const container = document.createElement("div");
    const root = createRoot(container);
    act(() => root.render(createElement("main", null, createElement("h1", null, "still here"), createElement(RendererBoundary, { onReload, children: createElement(Broken) }))));
    cleanups.push(() => act(() => root.unmount()));
    expect(container.querySelector("h1")?.textContent).toBe("still here"); // the rest of the page survives
    const fallback = container.querySelector("[data-testid=renderer-error]")!;
    expect(fallback.textContent).toContain(i18n.t("app.error"));
    act(() => fallback.querySelector("button")!.click());
    expect(onReload).toHaveBeenCalledTimes(1);
  });
});
