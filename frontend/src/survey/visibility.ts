import {
  type AnswerValue,
  type Answers,
  type Condition,
  type Definition,
  type Question,
  questionConfig,
  questionRequired,
} from "./types";

export interface VisibleQuestion {
  key: string;
  sectionKey: string;
  sectionIndex: number;
  index: number;
  type: Question["type"];
  required: boolean;
  question: Question;
}

export function questionByKey(def: Definition): Record<string, Question> {
  const out: Record<string, Question> = {};
  for (const s of def.sections) for (const q of s.questions) out[q.key] = q;
  return out;
}

/** True when an answer exists and carries a value (not a skip). */
export function isAnswered(answer: AnswerValue | undefined): boolean {
  if (!answer || ("skipped" in answer && answer.skipped)) return false;
  if ("options" in answer) return answer.options.length > 0;
  if ("order" in answer) return answer.order.length > 0;
  if ("ratings" in answer) return Object.keys(answer.ratings).length > 0;
  if ("provided" in answer) return answer.provided;
  return true;
}

function scalar(answer: AnswerValue): string | null {
  if ("option" in answer) return String(answer.option);
  if ("value" in answer) return String(answer.value);
  return null;
}

/** Every operator is false when the referenced question is unanswered. */
export function evaluateCondition(c: Condition, answers: Answers): boolean {
  const answer = answers[c.question];
  if (!isAnswered(answer)) return false;
  const a = answer as AnswerValue;
  if (c.op === "answered") return true;
  if (c.op === "contains") {
    const items = "options" in a ? a.options : "order" in a ? a.order : [];
    return items.includes(c.value ?? "");
  }
  const s = scalar(a);
  if (s === null) return false;
  if (c.op === "eq") return s === c.value;
  if (c.op === "neq") return s !== c.value;
  if (c.op === "in") return (c.values ?? []).includes(s);
  return false;
}

export function conditionsHold(conditions: Condition[] | undefined, answers: Answers): boolean {
  return (conditions ?? []).every((c) => evaluateCondition(c, answers));
}

/**
 * One forward pass in presentation order — the DAG's topological order.
 * Conditions see only the answers of questions that are themselves visible
 * (`seen`): a hidden question's stale answer must not keep anything downstream
 * open, otherwise a multi-hop cascade would stop after one hop.
 */
export function visibleQuestions(def: Definition, answers: Answers): VisibleQuestion[] {
  const out: VisibleQuestion[] = [];
  const seen: Answers = {};
  def.sections.forEach((section, sectionIndex) => {
    if (!conditionsHold(section.visible_if, seen)) return;
    for (const q of section.questions) {
      if (!conditionsHold(q.visible_if, seen)) continue;
      if (q.type === "matrix" && dynamicRowsEmpty(q, seen)) continue;
      if (q.key in answers) seen[q.key] = answers[q.key];
      out.push({
        key: q.key,
        sectionKey: section.key,
        sectionIndex,
        index: out.length,
        type: q.type,
        required: questionRequired(q),
        question: q,
      });
    }
  });
  return out;
}

/**
 * A `rows_from` matrix has nothing to ask while its source has no selection, so
 * it is hidden rather than left visible with zero rows (which could neither be
 * answered nor, under a hard skip policy, skipped). Mirrors visibility.py.
 */
function dynamicRowsEmpty(q: Question, answers: Answers): boolean {
  const cfg = questionConfig(q);
  return Boolean(cfg.rows_from) && !(cfg.rows && cfg.rows.length) && matrixRows(q, answers).length === 0;
}

export function visibleKeys(def: Definition, answers: Answers): string[] {
  return visibleQuestions(def, answers).map((v) => v.key);
}

/** Current rows of a matrix: fixed rows or the source question's selection. */
export function matrixRows(q: Question, answers: Answers): string[] {
  const cfg = questionConfig(q);
  if (cfg.rows && cfg.rows.length) return cfg.rows.map((r) => r.key);
  const source = answers[cfg.rows_from ?? ""];
  if (!isAnswered(source)) return [];
  return source && "options" in source ? [...source.options] : [];
}
