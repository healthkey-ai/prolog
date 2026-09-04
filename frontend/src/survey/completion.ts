import { ANSWERABLE, type Answers, type Definition } from "./types";
import { isAnswered, matrixRows, questionByKey, visibleQuestions } from "./visibility";

/** Visible answerable questions without an answer row (RUN-18). */
export function missingKeys(def: Definition, answers: Answers): string[] {
  const questions = questionByKey(def);
  const missing: string[] = [];
  for (const v of visibleQuestions(def, answers)) {
    if (!ANSWERABLE.has(v.type)) continue;
    const value = answers[v.key];
    if (value === undefined) {
      missing.push(v.key);
      continue;
    }
    const q = questions[v.key];
    if (q.type === "matrix" && isAnswered(value) && "ratings" in value) {
      const rows = matrixRows(q, answers, questions);
      const rated = Object.keys(value.ratings);
      if (rows.length !== rated.length || !rows.every((r) => rated.includes(r))) missing.push(v.key);
    }
  }
  return missing;
}

/**
 * Answered = visible answerable questions that are not missing, so a pruned
 * matrix (rated, but not for every current row) counts as open, exactly as
 * `missingKeys` reports it; a skip counts as answered. Mirrors completion.py.
 */
export function progress(def: Definition, answers: Answers): { answered: number; total: number } {
  const total = visibleQuestions(def, answers).filter((v) => ANSWERABLE.has(v.type)).length;
  return { answered: total - missingKeys(def, answers).length, total };
}
