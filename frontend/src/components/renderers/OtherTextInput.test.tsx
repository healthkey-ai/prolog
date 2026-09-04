import { act, createElement, useState } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import { OtherTextInput, withOtherText } from "./OtherTextInput";
import type { OptionValue } from "@/survey/types";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

describe("withOtherText", () => {
  it("attaches non-empty text and drops the field otherwise", () => {
    expect(withOtherText({ option: "o" }, "hi")).toEqual({ option: "o", other_text: "hi" });
    expect(withOtherText({ option: "o", other_text: "old" }, undefined)).toEqual({ option: "o" });
    expect(withOtherText({ options: ["a", "o"] }, "")).toEqual({ options: ["a", "o"] });
    expect(withOtherText({ order: ["o", "a"] }, "x")).toEqual({ order: ["o", "a"], other_text: "x" });
  });
});

describe("OtherTextInput", () => {
  const cleanups: (() => void)[] = [];
  afterEach(() => cleanups.splice(0).forEach((fn) => fn()));

  it("drafts on every keystroke and commits the trimmed text on blur (the same wiring for every renderer)", () => {
    const onChange = vi.fn();
    // Hosted like a renderer hosts it: the draft flows back in as the controlled value.
    function Host() {
      const [value, setValue] = useState<OptionValue | undefined>(undefined);
      return (
        <OtherTextInput
          base={{ option: "o" }}
          value={value?.other_text}
          onChange={(next, opts) => {
            setValue(next);
            onChange(next, opts);
          }}
        />
      );
    }
    const container = document.createElement("div");
    const root = createRoot(container);
    act(() => root.render(createElement(Host)));
    cleanups.push(() => act(() => root.unmount()));
    const input = container.querySelector("input")!;
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, " hi ");
    act(() => {
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    expect(onChange).toHaveBeenLastCalledWith({ option: "o", other_text: " hi " }, undefined);
    act(() => {
      input.dispatchEvent(new FocusEvent("focusout", { bubbles: true }));
    });
    expect(onChange).toHaveBeenLastCalledWith({ option: "o", other_text: "hi" }, { commit: true });
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, "   ");
    act(() => {
      input.dispatchEvent(new FocusEvent("focusout", { bubbles: true }));
    });
    expect(onChange).toHaveBeenLastCalledWith({ option: "o" }, { commit: true });
  });
});
