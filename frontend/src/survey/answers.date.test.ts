import { describe, expect, it } from "vitest";
import { AnswerError, validateAnswer } from "./answers";
import type { Question } from "./types";

const date: Question = { key: "d", type: "date", text: { en: "d" } };

/** Engine parity: Python's `date.fromisoformat` has no year 0 (MINYEAR is 1); the TS check must refuse it too. */
describe("date year bounds", () => {
  it("rejects year 0000 as date_invalid, like the Python engine", () => {
    let err: unknown;
    try {
      validateAnswer(date, { date: "0000-01-01" }, {});
    } catch (e) {
      err = e;
    }
    expect(err).toBeInstanceOf(AnswerError);
    expect((err as AnswerError).issues).toEqual([{ code: "date_invalid", params: {} }]);
  });

  it("accepts year 0001 and later", () => {
    expect(validateAnswer(date, { date: "0001-01-01" }, {})).toEqual({ date: "0001-01-01" });
    expect(validateAnswer(date, { date: "2025-05-01" }, {})).toEqual({ date: "2025-05-01" });
  });
});
