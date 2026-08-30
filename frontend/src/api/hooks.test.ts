import { describe, expect, it } from "vitest";
import { applyAnswerResult, mergePatched, revertAnswer, withEmailProvided } from "./hooks";
import type { AnswerResult, ResponseSummary } from "./types";

const base: ResponseSummary = {
  id: "r1",
  slug: "s",
  version: "1",
  language: "en",
  status: "in_progress",
  started_at: "2026-01-01T00:00:00Z",
  submitted_at: null,
  last_question_key: "q1",
  administration: null,
  answers: { q1: { option: "a" }, q2: { text: "hello" } },
  visible: ["q1", "q2", "q3"],
  missing: ["q3"],
  progress: { answered: 2, total: 3 },
};

const result = (value: AnswerResult["answer"]["value"], extra: Partial<AnswerResult> = {}): AnswerResult => ({
  answer: { key: "q1", value },
  invalidated: [],
  pruned: {},
  visible: ["q1", "q3"],
  missing: [],
  progress: { answered: 2, total: 2 },
  ...extra,
});

describe("applyAnswerResult", () => {
  it("stores the saved value and the server's cascade outcome", () => {
    const next = applyAnswerResult(base, "q1", result({ option: "b" }, { invalidated: ["q2"], pruned: { q3: { text: "kept" } } }));
    expect(next.answers).toEqual({ q1: { option: "b" }, q3: { text: "kept" } });
    expect(next.visible).toEqual(["q1", "q3"]);
    expect(next.missing).toEqual([]);
    expect(next.progress).toEqual({ answered: 2, total: 2 });
    expect(next.last_question_key).toBe("q1");
    expect(base.answers.q2).toEqual({ text: "hello" }); // input untouched
  });
});

describe("revertAnswer", () => {
  it("restores only the failed key's previous value", () => {
    const optimistic = { ...base, answers: { ...base.answers, q1: { option: "z" }, q2: { text: "newer" } } };
    const next = revertAnswer(optimistic, "q1", { previous: { option: "a" }, had: true });
    expect(next.answers).toEqual({ q1: { option: "a" }, q2: { text: "newer" } });
  });
  it("removes the key when there was no previous value", () => {
    const optimistic = { ...base, answers: { ...base.answers, q3: { option: "x" } } };
    const next = revertAnswer(optimistic, "q3", { previous: undefined, had: false });
    expect(next.answers).toEqual(base.answers);
  });
});

describe("mergePatched", () => {
  const server = { ...base, language: "en", last_question_key: "q2" };
  it("takes only the fields the PATCH set", () => {
    const switched = { ...base, language: "fr" };
    expect(mergePatched(switched, { last_question_key: "q2" }, server)).toEqual({ ...switched, last_question_key: "q2" });
    expect(mergePatched(base, { language: "fr" }, { ...server, language: "fr" })).toEqual({ ...base, language: "fr" });
  });
});

describe("withEmailProvided", () => {
  it("marks the email question answered and no longer missing", () => {
    const next = withEmailProvided({ ...base, missing: ["q3", "email"] }, "email");
    expect(next.answers.email).toEqual({ provided: true });
    expect(next.missing).toEqual(["q3"]);
  });
});
