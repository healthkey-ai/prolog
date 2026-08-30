import { describe, expect, it } from "vitest";
import { applyCascade } from "./cascade";
import type { Definition } from "./types";
import { visibleKeys } from "./visibility";

/** q1 gates q2; q2's answer gates q3. Changing q1 must cascade through q2 to q3. */
const chain = {
  slug: "chain",
  version: "1",
  languages: ["en"],
  default_language: "en",
  sections: [
    {
      key: "s",
      title: { en: "s" },
      questions: [
        { key: "q1", type: "single", text: { en: "q1" }, options: [{ key: "yes", label: { en: "y" } }, { key: "no", label: { en: "n" } }] },
        { key: "q2", type: "single", text: { en: "q2" }, options: [{ key: "a", label: { en: "a" } }, { key: "b", label: { en: "b" } }], visible_if: [{ question: "q1", op: "eq", value: "yes" }] },
        { key: "q3", type: "text", text: { en: "q3" }, visible_if: [{ question: "q2", op: "eq", value: "a" }] },
      ],
    },
  ],
} as unknown as Definition;

describe("multi-hop cascade", () => {
  it("a hidden question's stale answer does not keep its dependants visible", () => {
    const answers = { q1: { option: "no" }, q2: { option: "a" }, q3: { text: "hello" } };
    expect(visibleKeys(chain, answers)).toEqual(["q1"]);
    const result = applyCascade(chain, answers);
    expect(result.invalidated).toEqual(["q2", "q3"]);
    expect(Object.keys(result.answers)).toEqual(["q1"]);
    expect(result.visible).toEqual(["q1"]);
  });
});
