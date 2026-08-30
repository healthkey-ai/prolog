/**
 * Navigation model over the visible-question list (RUN-7…RUN-10).
 * Pure functions; the wizard page owns no navigation logic of its own.
 */
import { missingKeys } from "./completion";
import { ANSWERABLE, type Answers, type Definition } from "./types";
import { isAnswered, type VisibleQuestion, visibleQuestions } from "./visibility";

export type QuestionStatus = "answered" | "skipped" | "current" | "unanswered" | "unreachable";

export interface OverviewRow {
  key: string;
  sectionKey: string;
  status: QuestionStatus;
  navigable: boolean;
  question: VisibleQuestion["question"];
}

export interface OverviewSection {
  key: string;
  sectionIndex: number;
  rows: OverviewRow[];
}

export interface Position {
  visible: VisibleQuestion[];
  current: VisibleQuestion | null;
  index: number; // index within visible list, -1 if not visible
  previousKey: string | null;
  nextKey: string | null;
  isLast: boolean;
  /** 1-based question number among answerable visible questions. */
  questionNumber: number;
  questionTotal: number;
  visibleSectionIndexes: number[];
  sectionNumber: number; // 1-based among visible sections
  sectionTotal: number;
}

export function position(def: Definition, answers: Answers, currentKey: string | null): Position {
  const visible = visibleQuestions(def, answers);
  const index = currentKey ? visible.findIndex((v) => v.key === currentKey) : -1;
  const current = index >= 0 ? visible[index] : null;
  const answerable = visible.filter((v) => ANSWERABLE.has(v.type));
  const visibleSectionIndexes = [...new Set(visible.map((v) => v.sectionIndex))];
  return {
    visible,
    current,
    index,
    previousKey: index > 0 ? visible[index - 1].key : null,
    nextKey: index >= 0 && index < visible.length - 1 ? visible[index + 1].key : null,
    isLast: index === visible.length - 1,
    questionNumber: current ? answerable.filter((v) => v.index <= current.index).length : 0,
    questionTotal: answerable.length,
    visibleSectionIndexes,
    sectionNumber: current ? visibleSectionIndexes.indexOf(current.sectionIndex) + 1 : 0,
    sectionTotal: visibleSectionIndexes.length,
  };
}

/**
 * Where a participant should land: a fresh response starts at the first
 * visible question (info blocks included); a resumed one continues at the
 * first open question, or stays on the last reached one when nothing is open.
 */
export function firstOpenKey(def: Definition, answers: Answers, lastKey?: string | null): string | null {
  const visible = visibleQuestions(def, answers);
  if (!visible.length) return null;
  if (!lastKey && Object.keys(answers).length === 0) return visible[0].key;
  const missing = missingKeys(def, answers);
  if (!missing.length) return lastKey && visible.some((v) => v.key === lastKey) ? lastKey : visible[visible.length - 1].key;
  return missing[0];
}

/**
 * Furthest question the participant may jump to: everything up to and
 * including the first unanswered visible question (or the last reached one).
 */
export function reachableIndex(def: Definition, answers: Answers, lastKey?: string | null): number {
  const visible = visibleQuestions(def, answers);
  const missing = missingKeys(def, answers);
  const firstMissing = missing.length ? visible.findIndex((v) => v.key === missing[0]) : visible.length - 1;
  const last = lastKey ? visible.findIndex((v) => v.key === lastKey) : -1;
  return Math.max(firstMissing, last);
}

export function overview(def: Definition, answers: Answers, currentKey: string | null, lastKey?: string | null): OverviewSection[] {
  const visible = visibleQuestions(def, answers);
  const reachable = reachableIndex(def, answers, lastKey);
  const sections = new Map<number, OverviewSection>();
  for (const v of visible) {
    const value = answers[v.key];
    let status: QuestionStatus;
    if (v.key === currentKey) status = "current";
    else if (value && "skipped" in value) status = "skipped";
    else if (isAnswered(value) || (value && "provided" in value)) status = "answered";
    else if (v.index <= reachable) status = "unanswered";
    else status = "unreachable";
    const section = sections.get(v.sectionIndex) ?? { key: v.sectionKey, sectionIndex: v.sectionIndex, rows: [] };
    section.rows.push({ key: v.key, sectionKey: v.sectionKey, status, navigable: v.index <= reachable, question: v.question });
    sections.set(v.sectionIndex, section);
  }
  return [...sections.values()];
}
