import { describe, expect, it } from "vitest";
import { type AnswerError, defaultOrder, implicitAnswer, validateAnswer } from "./answers";
import type { Question } from "./types";

const ranking: Question = {
  key: "r",
  type: "ranking",
  text: { en: "r" },
  options: [
    { key: "a", label: { en: "a" } },
    { key: "b", label: { en: "b" } },
    { key: "c", label: { en: "c" } },
  ],
  config: { optional_items: ["c"] },
};

describe("defaultOrder", () => {
  it("is the options in definition order minus the optional items", () => {
    expect(defaultOrder(ranking)).toEqual(["a", "b"]);
    expect(defaultOrder({ ...ranking, config: {} })).toEqual(["a", "b", "c"]);
  });
});

describe("implicitAnswer", () => {
  it("is a required ranking's displayed order, optional items excluded", () => {
    expect(implicitAnswer(ranking)).toEqual({ order: ["a", "b"] });
    expect(implicitAnswer(ranking)).toEqual({ order: defaultOrder(ranking) });
  });
  it("is nothing for an optional ranking or any other type", () => {
    expect(implicitAnswer({ ...ranking, required: false })).toBeUndefined();
    expect(implicitAnswer({ key: "t", type: "text", text: { en: "t" } })).toBeUndefined();
  });
});

describe("matrix ratings", () => {
  it("come back in rows order whatever order they were rated in", () => {
    const q: Question = {
      key: "m",
      type: "matrix",
      text: { en: "m" },
      config: {
        scale: { min: 1, max: 5 },
        rows: [
          { key: "x", label: { en: "x" } },
          { key: "y", label: { en: "y" } },
          { key: "z", label: { en: "z" } },
        ],
      },
    };
    const value = validateAnswer(q, { ratings: { z: 3, x: 1, y: 2 } }, {});
    expect(Object.keys((value as { ratings: Record<string, number> }).ratings)).toEqual(["x", "y", "z"]);
    expect(JSON.stringify(value)).toBe(JSON.stringify({ ratings: { x: 1, y: 2, z: 3 } }));
  });
});

describe("text length", () => {
  it("counts code points like the server, not UTF-16 units", () => {
    const q: Question = { key: "t", type: "text", text: { en: "t" }, config: { max_length: 6 } };
    expect(validateAnswer(q, { text: "😀😀😀😀😀😀" }, {})).toEqual({ text: "😀😀😀😀😀😀" });
    let issues: unknown;
    try {
      validateAnswer(q, { text: "😀😀😀😀😀😀😀" }, {});
    } catch (e) {
      issues = (e as AnswerError).issues;
    }
    expect(issues).toEqual([{ code: "text_too_long", params: { max: 6 } }]);
  });
});
