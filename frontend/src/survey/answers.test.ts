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

describe("text length (stripped value)", () => {
  it("applies the limit to what is stored, not to surrounding whitespace", () => {
    const q: Question = { key: "t", type: "text", text: { en: "t" }, config: { max_length: 3 } };
    expect(validateAnswer(q, { text: "  abc  " }, {})).toEqual({ text: "abc" });
    expect(() => validateAnswer(q, { text: "abcd" }, {})).toThrow();
  });
});

describe("multi exclusive option", () => {
  const q: Question = {
    key: "m",
    type: "multi",
    text: { en: "m" },
    config: { min_selections: 2 },
    options: [
      { key: "a", label: { en: "a" } },
      { key: "b", label: { en: "b" } },
      { key: "none", label: { en: "none" }, exclusive: true },
    ],
  };
  it("on its own satisfies min_selections", () => {
    expect(validateAnswer(q, { options: ["none"] }, {})).toEqual({ options: ["none"] });
  });
  it("still cannot be combined, and an ordinary short pick is still short", () => {
    let codes: string[] = [];
    try {
      validateAnswer(q, { options: ["none", "a"] }, {});
    } catch (e) {
      codes = (e as AnswerError).issues.map((i) => i.code);
    }
    expect(codes).toEqual(["exclusive_combined"]);
    codes = [];
    try {
      validateAnswer(q, { options: ["a"] }, {});
    } catch (e) {
      codes = (e as AnswerError).issues.map((i) => i.code);
    }
    expect(codes).toEqual(["min_selections"]);
  });
});

describe("dynamic matrix rows", () => {
  it("refuses to validate a rows_from matrix without the questions map", () => {
    const q: Question = {
      key: "m",
      type: "matrix",
      text: { en: "m" },
      config: { rows_from: "src", scale: { min: 1, max: 3 } },
    };
    const answers = { src: { options: ["none"] } };
    expect(() => validateAnswer(q, { ratings: { none: 1 } }, answers)).toThrow(/questions map/);
  });
});
