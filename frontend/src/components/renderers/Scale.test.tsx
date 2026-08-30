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
