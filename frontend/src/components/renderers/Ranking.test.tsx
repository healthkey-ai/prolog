import { act, createElement } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import i18n from "@/i18n";
import { Ranking } from "./Ranking";
import type { Question } from "@/survey/types";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const question: Question = {
  key: "rank",
  type: "ranking",
  text: "Order these",
  options: [
    { key: "a", label: "First thing" },
    { key: "b", label: "Second thing" },
    { key: "o", label: "Something else", free_text: true },
  ],
  config: { optional_items: ["o"] },
};

describe("Ranking", () => {
  const cleanups: (() => void)[] = [];
  afterEach(() => {
    cleanups.splice(0).forEach((fn) => fn());
    void i18n.changeLanguage("en");
  });

  function render(lang: string) {
    void i18n.changeLanguage(lang);
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    const onChange = vi.fn();
    act(() => root.render(createElement(Ranking, { question, value: { order: ["a", "b", "o"], other_text: "mine" }, onChange, language: lang })));
    cleanups.push(() => {
      act(() => root.unmount());
      container.remove();
    });
    return { container, onChange };
  }

  it("gives the drag handles localized screen-reader instructions instead of dnd-kit's English", () => {
    const { container } = render("fr");
    const handle = container.querySelector<HTMLButtonElement>("button[aria-describedby]")!;
    expect(handle).not.toBeNull();
    const instructions = document.getElementById(handle.getAttribute("aria-describedby")!)!;
    expect(instructions.textContent).toBe(i18n.t("ranking.srInstructions", { lng: "fr" }));
    expect(instructions.textContent).not.toContain("space bar");
  });

  it("removing the free-text item drops its text; removing another keeps it", () => {
    const { container, onChange } = render("en");
    act(() => container.querySelector<HTMLButtonElement>("[data-testid=ranking-remove-o]")!.click());
    expect(onChange).toHaveBeenLastCalledWith({ order: ["a", "b"] }, { commit: true });
  });
});
