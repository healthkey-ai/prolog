import { isAnswered, matrixRows, questionByKey, visibleKeys } from "./visibility";
import type { AnswerValue, Answers, Definition, Question } from "./types";

export interface CascadeResult {
  answers: Answers;
  invalidated: string[];
  visible: string[];
}

/**
 * `{provided: true}` on an email question records that an address was captured
 * (CON-3/4); hiding the question must not throw it away, or re-showing it would
 * capture the address twice. Mirrors cascade.py.
 */
export function retainedWhenHidden(question: Question | undefined, value: AnswerValue | undefined): boolean {
  return question?.type === "email" && value !== undefined && "provided" in value && value.provided === true;
}

/** Recompute visibility over the whole DAG (one pass) and drop what no longer applies. */
export function applyCascade(def: Definition, answers: Answers): CascadeResult {
  const questions = questionByKey(def);
  const surviving: Answers = { ...answers };
  const invalidated = new Set<string>();
  // Pruning a matrix can change what is visible (a question conditioned on it
  // being `answered`), which can hide further answers: walk again until a pass
  // prunes nothing, so the result is a fixed point. Mirrors cascade.py.
  let visible: string[];
  for (;;) {
    visible = visibleKeys(def, surviving);
    const visibleSet = new Set(visible);

    for (const key of Object.keys(surviving)) {
      if (!visibleSet.has(key) && !retainedWhenHidden(questions[key], surviving[key])) {
        delete surviving[key];
        invalidated.add(key);
      }
    }

    let pruned = false;
    for (const [key, value] of Object.entries(surviving)) {
      const q = questions[key];
      if (!q || q.type !== "matrix" || !isAnswered(value) || !("ratings" in value)) continue;
      const rows = matrixRows(q, surviving, questions);
      const ratings = Object.fromEntries(Object.entries(value.ratings).filter(([r]) => rows.includes(r)));
      if (Object.keys(ratings).length !== Object.keys(value.ratings).length) {
        if (Object.keys(ratings).length) surviving[key] = { ratings };
        else delete surviving[key];
        invalidated.add(key);
        pruned = true;
      }
    }
    if (!pruned) break;
  }

  const order = Object.keys(questions);
  return { answers: surviving, invalidated: [...invalidated].sort((a, b) => order.indexOf(a) - order.indexOf(b)), visible };
}
