import { ANSWERABLE, type Answers, type Definition } from "./types";
import { isAnswered, matrixRows, pendingKeys, questionByKey, visibleQuestions } from "./visibility";

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
 * Progress over the whole instrument, so the total never moves. `total` counts
 * every answerable question in the definition, visible or not; `answered` is
 * everything settled — visible questions with an answer (a pruned matrix counts
 * as open, exactly as `missingKeys` reports it; a skip counts as answered) and
 * hidden questions whose branch is closed. Only hidden questions that may still
 * appear (`pendingKeys`) are left out. Mirrors completion.py.
 */
export function progress(def: Definition, answers: Answers): { answered: number; total: number } {
  const total = def.sections.flatMap((s) => s.questions).filter((q) => ANSWERABLE.has(q.type)).length;
  return { answered: total - missingKeys(def, answers).length - pendingKeys(def, answers).length, total };
}
