import { describe, expect, it } from "vitest";
import { createRoot } from "react-dom/client";
import { act } from "react";
import { composeDate, displayDate, DateInput } from "./DateInput";
import type { DatePrecision, DateValue, Question } from "@/survey/types";

describe("composeDate", () => {
  const monthOrYear: DatePrecision[] = ["month", "year"];
  it("spells a date at an accepted precision", () => {
    expect(composeDate({ year: "2019", month: "06", day: "" }, monthOrYear)).toBe("2019-06");
    expect(composeDate({ year: "2019", month: "", day: "" }, monthOrYear)).toBe("2019");
    expect(composeDate({ year: "2019", month: "6", day: "5" }, ["day"])).toBe("2019-06-05");
  });
  it("is undefined while the parts are incomplete for the precisions accepted", () => {
    expect(composeDate({ year: "201", month: "06", day: "" }, monthOrYear)).toBeUndefined();
    expect(composeDate({ year: "2019", month: "", day: "" }, ["month"])).toBeUndefined();
    expect(composeDate({ year: "2019", month: "06", day: "15" }, monthOrYear)).toBeUndefined();
    expect(composeDate({ year: "2019", month: "", day: "15" }, ["day", "month", "year"])).toBeUndefined();
  });
});

describe("displayDate", () => {
  it("names the month, and leaves a year or a whole date as given", () => {
    expect(displayDate("2019-06", "en")).toBe("June 2019");
    expect(displayDate("2019", "en")).toBe("2019");
    expect(displayDate("2019-06-05", "en")).toBe("2019-06-05");
  });
});

const QUESTION: Question = {
  key: "started",
  type: "date",
  text: "When did you start it?",
  config: { precision: ["month", "year"] },
  options: [{ key: "not_sure", label: "I am not sure" }],
};

function render(value: DateValue | undefined) {
  const calls: Array<[DateValue | undefined, { commit?: boolean } | undefined]> = [];
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(<DateInput question={QUESTION} value={value} language="en" onChange={(v, o) => calls.push([v, o])} />);
  });
  const $ = (id: string) => container.querySelector(`[data-testid="${id}"]`) as HTMLInputElement & HTMLSelectElement;
  const type = (el: HTMLInputElement | HTMLSelectElement, text: string) =>
    act(() => {
      const proto = el instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto, "value")!.set!.call(el, text);
      el.dispatchEvent(new Event(el instanceof HTMLSelectElement ? "change" : "input", { bubbles: true }));
    });
  return { container, calls, $, type, cleanup: () => (act(() => root.unmount()), container.remove()) };
}

describe("DateInput with month or year", () => {
  it("asks for the month and the year separately, the month optional, and no day", () => {
    const { $, container, cleanup } = render(undefined);
    expect($("date-day")).toBeNull();
    expect($("date-month").options[0].textContent).toBe("date.unknown");
    expect($("date-month").options[6].textContent).toBe("June");
    expect(container.querySelector('[data-testid="option-not_sure"]')).not.toBeNull();
    cleanup();
  });

  it("answers with the year alone, then with the month once one is chosen", () => {
    const { $, type, calls, cleanup } = render(undefined);
    type($("date-year"), "2019");
    expect(calls.at(-1)?.[0]).toEqual({ date: "2019" });
    type($("date-month"), "06");
    expect(calls.at(-1)).toEqual([{ date: "2019-06" }, { commit: true }]);
    cleanup();
  });

  it("shows a stored partial date in its fields", () => {
    const { $, cleanup } = render({ date: "2019-06" });
    expect($("date-year").value).toBe("2019");
    expect($("date-month").value).toBe("06");
    cleanup();
  });
});
