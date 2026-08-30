import { describe, expect, it } from "vitest";
import { implicitAnswer, validateAnswer } from "./answers";
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

describe("implicitAnswer", () => {
  it("is a required ranking's displayed order, optional items excluded", () => {
    expect(implicitAnswer(ranking)).toEqual({ order: ["a", "b"] });
  });
  it("is nothing for an optional ranking or any other type", () => {
    expect(implicitAnswer({ ...ranking, required: false })).toBeUndefined();
    expect(implicitAnswer({ key: "t", type: "text", text: { en: "t" } })).toBeUndefined();
  });
});

describe("text length", () => {
  it("counts code points like the server, not UTF-16 units", () => {
    const q: Question = { key: "t", type: "text", text: { en: "t" }, config: { max_length: 6 } };
    expect(validateAnswer(q, { text: "😀😀😀😀😀😀" }, {})).toEqual({ text: "😀😀😀😀😀😀" });
    expect(() => validateAnswer(q, { text: "😀😀😀😀😀😀😀" }, {})).toThrow(/exceeds 6/);
  });
});
