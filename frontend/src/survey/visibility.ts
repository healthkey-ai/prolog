import {
  ANSWERABLE,
  type AnswerValue,
  type Answers,
  type Condition,
  type Definition,
  type Question,
  exclusiveKeys,
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
  if (c.op === "contains" || c.op === "not_contains") {
    const items = "options" in a ? a.options : "order" in a ? a.order : [];
    // Both false until answered (above): not_contains means "answered, and
    // without this option" — a gate that opens on an answer, never on silence.
    return items.includes(c.value ?? "") === (c.op === "contains");
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
  const questions = questionByKey(def);
  def.sections.forEach((section, sectionIndex) => {
    if (!conditionsHold(section.visible_if, seen)) return;
    for (const q of section.questions) {
      if (!conditionsHold(q.visible_if, seen)) continue;
      if (q.type === "matrix" && dynamicRowsEmpty(q, seen, questions)) continue;
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
function dynamicRowsEmpty(q: Question, answers: Answers, questions: Record<string, Question>): boolean {
  const cfg = questionConfig(q);
  return Boolean(cfg.rows_from) && !(cfg.rows && cfg.rows.length) && matrixRows(q, answers, questions).length === 0;
}

/**
 * Hidden answerable questions that may still appear. A hidden question is
 * *closed* — it will not be asked — when something it depends on has been
 * decided against it: a gating question holding a row (a value or a skip) with
 * which the condition is false, or a gate that is itself closed. It is
 * *pending* while every false condition rests on a question the respondent has
 * simply not reached yet. Mirrors visibility.py.
 */
export function pendingKeys(def: Definition, answers: Answers): string[] {
  const shown = new Set(visibleQuestions(def, answers).map((v) => v.key));
  // Conditions are judged on visible answers only, as visibleQuestions does.
  const seen: Answers = Object.fromEntries(Object.entries(answers).filter(([k]) => shown.has(k)));
  const closed = new Set<string>();
  const pending: string[] = [];
  const settled = (key: string) => (shown.has(key) ? key in answers : closed.has(key));
  for (const section of def.sections) {
    for (const q of section.questions) {
      if (shown.has(q.key)) continue;
      const conditions = [...(section.visible_if ?? []), ...(q.visible_if ?? [])];
      let falseConditions = conditions.filter((c) => !evaluateCondition(c, seen)).map((c) => c.question);
      // A rows_from matrix hidden for want of rows waits on its source the
      // same way a condition waits on its question.
      if (!falseConditions.length && q.type === "matrix") {
        const source = questionConfig(q).rows_from;
        falseConditions = source ? [source] : [];
      }
      if (falseConditions.some(settled)) closed.add(q.key);
      else if (ANSWERABLE.has(q.type)) pending.push(q.key);
    }
  }
  return pending;
}

export function visibleKeys(def: Definition, answers: Answers): string[] {
  return visibleQuestions(def, answers).map((v) => v.key);
}

/**
 * Current rows of a matrix: fixed rows or the source question's selection.
 * An `exclusive` source option ("none of these") is never a row: there is
 * nothing to rate about it, so a selection of only exclusive options leaves
 * the matrix with no rows (and hidden). Mirrors visibility.py.
 */
export function matrixRows(q: Question, answers: Answers, questions: Record<string, Question>): string[] {
  const cfg = questionConfig(q);
  if (cfg.rows && cfg.rows.length) return cfg.rows.map((r) => r.key);
  const sourceKey = cfg.rows_from ?? "";
  const source = answers[sourceKey];
  if (!isAnswered(source)) return [];
  if (!source || !("options" in source)) return [];
  const sourceQuestion = questions[sourceKey];
  const exclusive = sourceQuestion ? exclusiveKeys(sourceQuestion) : new Set<string>();
  return source.options.filter((k) => !exclusive.has(k));
}
