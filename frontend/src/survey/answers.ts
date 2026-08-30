/**
 * Client-side mirror of the server's per-type answer validation. Used for
 * immediate feedback only; the server remains authoritative (RUN-15).
 */
import { matrixRows } from "./visibility";
import {
  type AnswerIssue,
  type AnswerValue,
  type Answers,
  type Question,
  type SkipPolicy,
  exclusiveKeys,
  freeTextKeys,
  questionConfig,
  questionOptions,
  questionRequired,
} from "./types";

/** Rejection codes, mirrored from backend/prolog_surveys/engine/answers.py MESSAGES. */
export type AnswerIssueCode =
  | "info_no_answer"
  | "value_not_object"
  | "skip_shape"
  | "skip_not_allowed"
  | "not_visible"
  | "other_text_not_string"
  | "other_text_without_free_option"
  | "other_text_too_long"
  | "option_required"
  | "option_unknown"
  | "options_not_list"
  | "options_duplicate"
  | "options_unknown"
  | "min_selections"
  | "max_selections"
  | "exclusive_combined"
  | "value_not_integer"
  | "value_out_of_range"
  | "order_not_list"
  | "order_duplicate"
  | "order_unknown"
  | "order_incomplete"
  | "ratings_not_object"
  | "matrix_no_rows"
  | "rows_unknown"
  | "rows_incomplete"
  | "rating_not_integer"
  | "rating_out_of_range"
  | "text_required"
  | "text_too_long"
  | "number_required"
  | "number_not_finite"
  | "number_not_integer"
  | "number_too_small"
  | "number_too_large"
  | "date_format"
  | "date_invalid"
  | "date_too_early"
  | "date_too_late"
  | "email_via_endpoint"
  | "unsupported_type";

export type { AnswerIssue } from "./types";

export class AnswerError extends Error {
  issues: AnswerIssue[];
  constructor(issues: AnswerIssue[]) {
    super(issues.map((i) => `${i.code} ${JSON.stringify(i.params)}`).join("; "));
    this.issues = issues;
  }
}

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
export const MAX_OTHER_TEXT = 500;

function fail(code: AnswerIssueCode, params: Record<string, unknown> = {}): never {
  throw new AnswerError([{ code, params }]);
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function isStringArray(v: unknown): v is string[] {
  return Array.isArray(v) && v.every((x) => typeof x === "string");
}

function isInt(v: unknown): v is number {
  return typeof v === "number" && Number.isInteger(v);
}

/** Length in code points, as Python's len() counts (an emoji is 1, not 2). */
function length(text: string): number {
  return [...text].length;
}

/**
 * The answer a question carries before the participant touches it, if any: a
 * required ranking's displayed order is itself a valid answer, so Next accepts
 * it (RUN-…/Q-6). Optional rankings stay unanswered so they can be skipped.
 */
export function implicitAnswer(q: Question): AnswerValue | undefined {
  if (q.type !== "ranking" || !questionRequired(q)) return undefined;
  return { order: defaultOrder(q) };
}

/**
 * The order a ranking shows before the participant touches it: the options in
 * definition order minus `config.optional_items`. The renderer and
 * `implicitAnswer` share this so the displayed list and the answer Next
 * accepts cannot diverge.
 */
export function defaultOrder(q: Question): string[] {
  const optional = new Set(questionConfig(q).optional_items ?? []);
  return questionOptions(q).filter((o) => !optional.has(o.key)).map((o) => o.key);
}

function optionKeys(q: Question): string[] {
  return questionOptions(q).map((o) => o.key);
}

function otherText(raw: Record<string, unknown>, q: Question, selected: string[]): { other_text?: string } {
  const text = raw.other_text;
  if (text === undefined || text === null) return {};
  if (typeof text !== "string") fail("other_text_not_string");
  const trimmed = text.trim();
  if (!trimmed) return {};
  const free = freeTextKeys(q);
  if (!selected.some((k) => free.has(k))) fail("other_text_without_free_option");
  if (length(trimmed) > MAX_OTHER_TEXT) fail("other_text_too_long", { max: MAX_OTHER_TEXT });
  return { other_text: trimmed };
}

export interface ValidateOptions {
  skipPolicy?: SkipPolicy;
  /** Keys provided by a dropdown's options_source (e.g. ISO country codes). */
  sourceOptions?: ReadonlySet<string>;
  /** The definition's questions by key (needed for dynamic matrix rows). */
  questions?: Record<string, Question>;
}

export function validateAnswer(
  q: Question,
  raw: unknown,
  answers: Answers,
  opts: ValidateOptions = {},
): AnswerValue {
  if (q.type === "info") fail("info_no_answer");
  if (!isRecord(raw)) fail("value_not_object");
  if (raw.skipped) {
    if (Object.keys(raw).length !== 1 || raw.skipped !== true) fail("skip_shape");
    if (questionRequired(q) && (opts.skipPolicy ?? "soft") === "hard") fail("skip_not_allowed");
    return { skipped: true };
  }
  const cfg = questionConfig(q);

  if (q.type === "single" || q.type === "dropdown") {
    const option = raw.option;
    if (typeof option !== "string" || !option) fail("option_required");
    const allowed = new Set(optionKeys(q));
    if (q.type === "dropdown" && cfg.options_source) for (const k of opts.sourceOptions ?? []) allowed.add(k);
    if (!allowed.has(option)) fail("option_unknown", { option });
    return { option, ...otherText(raw, q, [option]) };
  }

  if (q.type === "multi") {
    const options = raw.options;
    if (!isStringArray(options)) fail("options_not_list");
    if (new Set(options).size !== options.length) fail("options_duplicate");
    const allowed = optionKeys(q);
    const unknown = options.filter((o) => !allowed.includes(o));
    if (unknown.length) fail("options_unknown", { options: unknown });
    const min = cfg.min_selections ?? 1;
    if (options.length < min) fail("min_selections", { min });
    if (cfg.max_selections !== undefined && options.length > cfg.max_selections) fail("max_selections", { max: cfg.max_selections });
    const exclusive = exclusiveKeys(q);
    if (options.length > 1 && options.some((o) => exclusive.has(o))) fail("exclusive_combined");
    const ordered = allowed.filter((k) => options.includes(k));
    return { options: ordered, ...otherText(raw, q, ordered) };
  }

  if (q.type === "scale") {
    const value = raw.value;
    const scale = cfg.scale!;
    if (!isInt(value)) fail("value_not_integer");
    if (value < scale.min || value > scale.max) fail("value_out_of_range", { min: scale.min, max: scale.max });
    return { value };
  }

  if (q.type === "ranking") {
    const order = raw.order;
    if (!isStringArray(order)) fail("order_not_list");
    if (new Set(order).size !== order.length) fail("order_duplicate");
    const allowed = optionKeys(q);
    const unknown = order.filter((o) => !allowed.includes(o));
    if (unknown.length) fail("order_unknown", { items: unknown });
    const optional = new Set(cfg.optional_items ?? []);
    const missing = allowed.filter((k) => !order.includes(k) && !optional.has(k));
    if (missing.length) fail("order_incomplete", { missing });
    return { order: [...order], ...otherText(raw, q, order) };
  }

  if (q.type === "matrix") {
    const ratings = raw.ratings;
    if (!isRecord(ratings)) fail("ratings_not_object");
    const rows = matrixRows(q, answers, opts.questions ?? {});
    if (!rows.length) fail("matrix_no_rows");
    const unknown = Object.keys(ratings).filter((r) => !rows.includes(r));
    if (unknown.length) fail("rows_unknown", { rows: unknown });
    const missing = rows.filter((r) => !(r in ratings));
    if (missing.length) fail("rows_incomplete", { missing });
    const scale = cfg.scale!;
    // Built in rows order (as the server returns it), so a draft rated out of
    // order compares equal to the stored value.
    const out: Record<string, number> = {};
    for (const row of rows) {
      const v = ratings[row];
      if (!isInt(v)) fail("rating_not_integer", { row });
      if (v < scale.min || v > scale.max) fail("rating_out_of_range", { row, min: scale.min, max: scale.max });
      out[row] = v;
    }
    return { ratings: out };
  }

  if (q.type === "text") {
    const text = raw.text;
    if (typeof text !== "string" || !text.trim()) fail("text_required");
    if (cfg.max_length && length(text) > cfg.max_length) fail("text_too_long", { max: cfg.max_length });
    return { text: text.trim() };
  }

  if (q.type === "number") {
    const n = raw.number;
    if (typeof n !== "number") fail("number_required");
    if (!Number.isFinite(n)) fail("number_not_finite");
    if (cfg.integer && !Number.isInteger(n)) fail("number_not_integer");
    if (cfg.min_value !== undefined && n < cfg.min_value) fail("number_too_small", { min: cfg.min_value });
    if (cfg.max_value !== undefined && n > cfg.max_value) fail("number_too_large", { max: cfg.max_value });
    return { number: n };
  }

  if (q.type === "date") {
    const d = raw.date;
    if (typeof d !== "string" || !DATE_RE.test(d)) fail("date_format");
    const parsed = new Date(`${d}T00:00:00Z`);
    if (Number.isNaN(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== d) fail("date_invalid");
    if (cfg.min_date && d < cfg.min_date) fail("date_too_early", { min: cfg.min_date });
    if (cfg.max_date && d > cfg.max_date) fail("date_too_late", { max: cfg.max_date });
    return { date: d };
  }

  if (q.type === "email") {
    if (raw.provided === false && Object.keys(raw).length === 1) return { provided: false };
    fail("email_via_endpoint");
  }

  fail("unsupported_type", { type: q.type });
}
