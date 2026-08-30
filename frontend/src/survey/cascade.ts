import { isAnswered, matrixRows, questionByKey, visibleKeys } from "./visibility";
import type { Answers, Definition } from "./types";

export interface CascadeResult {
  answers: Answers;
  invalidated: string[];
  visible: string[];
}

/** Recompute visibility over the whole DAG (one pass) and drop what no longer applies. */
export function applyCascade(def: Definition, answers: Answers): CascadeResult {
  const questions = questionByKey(def);
  const surviving: Answers = { ...answers };
  const invalidated: string[] = [];
  const visible = visibleKeys(def, surviving);
  const visibleSet = new Set(visible);

  for (const key of Object.keys(surviving)) {
    if (!visibleSet.has(key)) {
      delete surviving[key];
      invalidated.push(key);
    }
  }

  for (const [key, value] of Object.entries(surviving)) {
    const q = questions[key];
    if (!q || q.type !== "matrix" || !isAnswered(value) || !("ratings" in value)) continue;
    const rows = matrixRows(q, surviving, questions);
    const ratings = Object.fromEntries(Object.entries(value.ratings).filter(([r]) => rows.includes(r)));
    if (Object.keys(ratings).length !== Object.keys(value.ratings).length) {
      if (Object.keys(ratings).length) surviving[key] = { ratings };
      else delete surviving[key];
      invalidated.push(key);
    }
  }

  const order = Object.keys(questions);
  invalidated.sort((a, b) => order.indexOf(a) - order.indexOf(b));
  return { answers: surviving, invalidated, visible };
}
