import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { validateAnswer } from "./answers";
import { applyCascade } from "./cascade";
import { missingKeys, progress } from "./completion";
import type { Answers, Definition } from "./types";
import { questionByKey, visibleKeys } from "./visibility";

const EXAMPLES = join(__dirname, "..", "..", "..", "examples");
const VECTOR_DIR = join(EXAMPLES, "vectors");
const SOURCE_OPTIONS = new Set(["GB", "FR", "DE"]);

interface Step {
  answer: { key: string; value: unknown };
  expect?: Record<string, unknown>;
}
interface Case {
  given?: Answers;
  key: string;
  value: unknown;
  canonical?: unknown;
}
interface Retained {
  given: Answers;
  answer: { key: string; value: unknown };
  expect: { invalidated: string[]; visible: string[]; answers: Answers; missing: string[] };
}
interface Vector {
  definition: string;
  initial?: { visible: string[] };
  steps?: Step[];
  retained?: Retained[];
  reject?: Case[];
  accept?: Case[];
  final?: { missing?: string[]; progress?: { answered: number; total: number } };
}

function store(def: Definition, answers: Answers, key: string, raw: unknown) {
  const questions = questionByKey(def);
  const q = questions[key];
  const value = validateAnswer(q, raw, answers, {
    skipPolicy: def.presentation?.skip_policy,
    sourceOptions: SOURCE_OPTIONS,
    questions,
  });
  const result = applyCascade(def, { ...answers, [key]: value });
  for (const k of Object.keys(answers)) delete answers[k];
  Object.assign(answers, result.answers);
  return result;
}

describe("shared engine vectors", () => {
  const files = readdirSync(VECTOR_DIR).filter((f) => f.endsWith(".json"));
  for (const file of files) {
    it(file, () => {
      const vector = JSON.parse(readFileSync(join(VECTOR_DIR, file), "utf-8")) as Vector;
      const def = JSON.parse(readFileSync(join(EXAMPLES, vector.definition), "utf-8")) as Definition;
      let answers: Answers = {};

      if (vector.initial) expect(visibleKeys(def, answers)).toEqual(vector.initial.visible);

      for (const step of vector.steps ?? []) {
        const { key, value } = step.answer;
        expect(visibleKeys(def, answers), `${key} visible before answering`).toContain(key);
        const result = store(def, answers, key, value);
        const e = step.expect ?? {};
        if ("invalidated" in e) expect(result.invalidated, key).toEqual(e.invalidated);
        if ("visible" in e) expect(result.visible, key).toEqual(e.visible);
        if ("answers" in e) expect(answers, key).toEqual(e.answers);
        if ("answers_subset" in e)
          for (const [k, v] of Object.entries(e.answers_subset as Answers)) expect(answers[k], key).toEqual(v);
        if ("missing" in e) expect(missingKeys(def, answers), key).toEqual(e.missing);
      }

      for (const c of vector.retained ?? []) {
        const given: Answers = { ...c.given };
        const result = store(def, given, c.answer.key, c.answer.value);
        expect(result.invalidated).toEqual(c.expect.invalidated);
        expect(result.visible).toEqual(c.expect.visible);
        expect(given).toEqual(c.expect.answers);
        expect(missingKeys(def, given)).toEqual(c.expect.missing);
      }

      for (const c of vector.reject ?? []) {
        const q = questionByKey(def)[c.key];
        expect(() => validateAnswer(q, c.value, c.given ?? {}, { sourceOptions: SOURCE_OPTIONS }), `${c.key} ${JSON.stringify(c.value)}`).toThrow();
      }
      for (const c of vector.accept ?? []) {
        const q = questionByKey(def)[c.key];
        const value = validateAnswer(q, c.value, c.given ?? {}, { sourceOptions: SOURCE_OPTIONS });
        if (c.canonical) expect(value).toEqual(c.canonical);
      }

      if (vector.final) {
        if (vector.final.missing) expect(missingKeys(def, answers)).toEqual(vector.final.missing);
        if (vector.final.progress) expect(progress(def, answers)).toEqual(vector.final.progress);
      }
      answers = {};
    });
  }
});
