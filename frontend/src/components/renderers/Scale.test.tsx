import { describe, expect, it } from "vitest";
import { createRoot } from "react-dom/client";
import { act } from "react";
import { ScaleControl } from "./Scale";

/** Render into a detached container; only layout classes are under test. */
function render(points: { min: number; max: number }) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(<ScaleControl {...points} value={undefined} onSelect={() => {}} name="q" ariaLabel="q" />);
  });
  return {
    container,
    cleanup: () => {
      act(() => root.unmount());
      container.remove();
    },
  };
}

describe("ScaleControl layout", () => {
  it("lays the points out in one flexible row that only wraps when they cannot fit", () => {
    const { container, cleanup } = render({ min: 1, max: 5 });
    const group = container.querySelector('[role="radiogroup"]') as HTMLElement;
    const items = container.querySelectorAll('[data-testid^="scale-q-"]');
    expect(items).toHaveLength(5);
    // No computed grid template: a five-point scale wrapped on a wide viewport
    // when auto-fit lost a column to sub-pixel rounding.
    expect(group.style.gridTemplateColumns).toBe("");
    expect(group.className).toContain("flex-wrap");
    for (const item of items) {
      // Each point grows to share the row but never shrinks below the 44 px target.
      expect(item.className).toContain("flex-1");
      expect(item.className).toContain("basis-[44px]");
      expect(item.className).toContain("min-w-[44px]");
    }
    cleanup();
  });
});

describe("the not-applicable choice", () => {
  function renderWith(props: Partial<Parameters<typeof ScaleControl>[0]>, onSelect: (v: number | "na") => void) {
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    act(() => {
      root.render(<ScaleControl min={1} max={5} value={undefined} onSelect={onSelect} name="q" ariaLabel="q" {...props} />);
    });
    return { container, cleanup: () => { act(() => root.unmount()); container.remove(); } };
  }

  it("is absent unless the scale offers it", () => {
    const { container, cleanup } = renderWith({}, () => {});
    expect(container.querySelector('[data-testid="scale-q-na"]')).toBeNull();
    expect(container.querySelectorAll('[data-testid^="scale-q-"]')).toHaveLength(5);
    cleanup();
  });

  it("sits in the same radio group as the points and selects as 'na', never as a number", () => {
    const chosen: (number | "na")[] = [];
    const { container, cleanup } = renderWith({ notApplicable: "Not applicable" }, (v) => chosen.push(v));
    const na = container.querySelector('[data-testid="scale-q-na"]') as HTMLButtonElement;
    expect(na).not.toBeNull();
    expect(na.textContent).toBe("Not applicable");
    // one group: a radio, like the points, so choosing it un-chooses a point
    expect(na.getAttribute("role")).toBe("radio");
    expect(container.querySelectorAll('[role="radio"]')).toHaveLength(6);
    act(() => na.click());
    expect(chosen).toEqual(["na"]);
    cleanup();
  });

  it("shows as chosen when the stored rating is 'na'", () => {
    const { container, cleanup } = renderWith({ notApplicable: "Not applicable", value: "na" }, () => {});
    const na = container.querySelector('[data-testid="scale-q-na"]') as HTMLButtonElement;
    expect(na.getAttribute("data-state")).toBe("checked");
    expect(container.querySelector('[data-testid="scale-q-3"]')?.getAttribute("data-state")).toBe("unchecked");
    cleanup();
  });
});
