import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import type { Answers, Definition } from "./types";
import { evaluateCondition, pendingKeys, visibleKeys } from "./visibility";

const history = JSON.parse(readFileSync(join(__dirname, "..", "..", "..", "examples", "sample-history.json"), "utf-8")) as Definition;

describe("any groups (mirrors test_engine.py)", () => {
  it("stay pending while one of their questions is still ahead", () => {
    const answers: Answers = {};
    expect(pendingKeys(history, answers)).toContain("review");
    // "stopped" makes the first branch false, but "ended" is still ahead
    answers.taking = { option: "stopped" };
    expect(visibleKeys(history, answers)).not.toContain("review");
    expect(pendingKeys(history, answers)).toContain("review");
    // a date (not "not sure") settles the second branch: now closed
    answers.ended = { date: "2021-03" };
    expect(pendingKeys(history, answers)).not.toContain("review");
  });
});

describe("conditions on a date question's options", () => {
  const cond = { question: "ended", op: "neq" as const, value: "not_sure" };
  it("hold neq for a date, which is none of the options", () => {
    expect(evaluateCondition(cond, { ended: { date: "2021" } })).toBe(true);
    expect(evaluateCondition(cond, { ended: { option: "not_sure" } })).toBe(false);
    expect(evaluateCondition({ ...cond, op: "eq" }, { ended: { date: "2021" } })).toBe(false);
    expect(evaluateCondition(cond, {})).toBe(false);
  });
});
