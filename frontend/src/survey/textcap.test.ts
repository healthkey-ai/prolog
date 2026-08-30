import { describe, expect, it } from "vitest";
import { AnswerError, MAX_TEXT_LENGTH, validateAnswer } from "./answers";
import type { Question } from "./types";

const q: Question = { key: "free", type: "text", text: "x", config: {} };

describe("text answers have an absolute cap (mirrors answers.py)", () => {
  it("accepts up to MAX_TEXT_LENGTH code points and rejects one more", () => {
    expect((validateAnswer(q, { text: "a".repeat(MAX_TEXT_LENGTH) }, {}) as { text: string }).text.length).toBe(MAX_TEXT_LENGTH);
    expect(() => validateAnswer(q, { text: "a".repeat(MAX_TEXT_LENGTH + 1) }, {})).toThrow(AnswerError);
    try {
      validateAnswer(q, { text: "a".repeat(MAX_TEXT_LENGTH + 1) }, {});
    } catch (e) {
      expect((e as AnswerError).issues[0]).toEqual({ code: "text_too_long", params: { max: MAX_TEXT_LENGTH } });
    }
  });
  it("clamps a configured max_length above the cap", () => {
    const big: Question = { ...q, config: { max_length: MAX_TEXT_LENGTH * 10 } };
    expect(() => validateAnswer(big, { text: "a".repeat(MAX_TEXT_LENGTH + 1) }, {})).toThrow(AnswerError);
  });
});
