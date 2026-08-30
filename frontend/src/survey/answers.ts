/**
 * Client-side mirror of the server's per-type answer validation. Used for
 * immediate feedback only; the server remains authoritative (RUN-15).
 */
import { matrixRows } from "./visibility";
import {
  type AnswerValue,
  type Answers,
  type Question,
  type SkipPolicy,
  questionConfig,
  questionOptions,
  questionRequired,
} from "./types";

export class AnswerError extends Error {
  errors: string[];
  constructor(errors: string[]) {
    super(errors.join("; "));
    this.errors = errors;
  }
}

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
export const MAX_OTHER_TEXT = 500;

function fail(msg: string): never {
  throw new AnswerError([msg]);
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
  const optional = new Set(questionConfig(q).optional_items ?? []);
  return { order: questionOptions(q).filter((o) => !optional.has(o.key)).map((o) => o.key) };
}

function optionKeys(q: Question): string[] {
  return questionOptions(q).map((o) => o.key);
}

function otherText(raw: Record<string, unknown>, q: Question, selected: string[]): { other_text?: string } {
  const text = raw.other_text;
  if (text === undefined || text === null) return {};
  if (typeof text !== "string") fail("other_text must be a string");
  const trimmed = text.trim();
  if (!trimmed) return {};
  const free = new Set(questionOptions(q).filter((o) => o.free_text).map((o) => o.key));
  if (!selected.some((k) => free.has(k))) fail("other_text requires a free-text option to be selected");
  if (length(trimmed) > MAX_OTHER_TEXT) fail(`other_text exceeds ${MAX_OTHER_TEXT} characters`);
  return { other_text: trimmed };
}

export interface ValidateOptions {
  skipPolicy?: SkipPolicy;
  /** Keys provided by a dropdown's options_source (e.g. ISO country codes). */
  sourceOptions?: ReadonlySet<string>;
}

export function validateAnswer(
  q: Question,
  raw: unknown,
  answers: Answers,
  opts: ValidateOptions = {},
): AnswerValue {
  if (q.type === "info") fail("info questions take no answer");
  if (!isRecord(raw)) fail("value must be an object");
  if (raw.skipped) {
    if (Object.keys(raw).length !== 1 || raw.skipped !== true) fail('a skip is exactly {"skipped": true}');
    if (questionRequired(q) && (opts.skipPolicy ?? "soft") === "hard") fail("this question cannot be skipped");
    return { skipped: true };
  }
  const cfg = questionConfig(q);

  if (q.type === "single" || q.type === "dropdown") {
    const option = raw.option;
    if (typeof option !== "string" || !option) fail("option is required");
    const allowed = new Set(optionKeys(q));
    if (q.type === "dropdown" && cfg.options_source) for (const k of opts.sourceOptions ?? []) allowed.add(k);
    if (!allowed.has(option)) fail(`unknown option '${option}'`);
    return { option, ...otherText(raw, q, [option]) };
  }

  if (q.type === "multi") {
    const options = raw.options;
    if (!isStringArray(options)) fail("options must be a list of option keys");
    if (new Set(options).size !== options.length) fail("duplicate options");
    const allowed = optionKeys(q);
    const unknown = options.filter((o) => !allowed.includes(o));
    if (unknown.length) fail(`unknown options ${unknown.join(", ")}`);
    const min = cfg.min_selections ?? 1;
    if (options.length < min) fail(`select at least ${min}`);
    if (cfg.max_selections !== undefined && options.length > cfg.max_selections) fail(`select at most ${cfg.max_selections}`);
    const exclusive = new Set(questionOptions(q).filter((o) => o.exclusive).map((o) => o.key));
    if (options.length > 1 && options.some((o) => exclusive.has(o))) fail("an exclusive option cannot be combined with others");
    const ordered = allowed.filter((k) => options.includes(k));
    return { options: ordered, ...otherText(raw, q, ordered) };
  }

  if (q.type === "scale") {
    const value = raw.value;
    const scale = cfg.scale!;
    if (!isInt(value)) fail("value must be an integer");
    if (value < scale.min || value > scale.max) fail(`value must be between ${scale.min} and ${scale.max}`);
    return { value };
  }

  if (q.type === "ranking") {
    const order = raw.order;
    if (!isStringArray(order)) fail("order must be a list of option keys");
    if (new Set(order).size !== order.length) fail("duplicate items in order");
    const allowed = optionKeys(q);
    const unknown = order.filter((o) => !allowed.includes(o));
    if (unknown.length) fail(`unknown items ${unknown.join(", ")}`);
    const optional = new Set(cfg.optional_items ?? []);
    const missing = allowed.filter((k) => !order.includes(k) && !optional.has(k));
    if (missing.length) fail(`every item must be ranked; missing ${missing.join(", ")}`);
    return { order: [...order], ...otherText(raw, q, order) };
  }

  if (q.type === "matrix") {
    const ratings = raw.ratings;
    if (!isRecord(ratings)) fail("ratings must be an object of row -> value");
    const rows = matrixRows(q, answers);
    if (!rows.length) fail("this matrix currently has no rows");
    const unknown = Object.keys(ratings).filter((r) => !rows.includes(r));
    if (unknown.length) fail(`unknown rows ${unknown.join(", ")}`);
    const missing = rows.filter((r) => !(r in ratings));
    if (missing.length) fail(`every row must be rated; missing ${missing.join(", ")}`);
    const scale = cfg.scale!;
    const out: Record<string, number> = {};
    for (const row of rows) {
      const v = ratings[row];
      if (!isInt(v)) fail(`rating for '${row}' must be an integer`);
      if (v < scale.min || v > scale.max) fail(`rating for '${row}' must be between ${scale.min} and ${scale.max}`);
      out[row] = v;
    }
    return { ratings: out };
  }

  if (q.type === "text") {
    const text = raw.text;
    if (typeof text !== "string" || !text.trim()) fail("text is required");
    if (cfg.max_length && length(text) > cfg.max_length) fail(`text exceeds ${cfg.max_length} characters`);
    return { text: text.trim() };
  }

  if (q.type === "number") {
    const n = raw.number;
    if (typeof n !== "number" || !Number.isFinite(n)) fail("number is required");
    if (cfg.integer && !Number.isInteger(n)) fail("a whole number is required");
    if (cfg.min_value !== undefined && n < cfg.min_value) fail(`number must be at least ${cfg.min_value}`);
    if (cfg.max_value !== undefined && n > cfg.max_value) fail(`number must be at most ${cfg.max_value}`);
    return { number: n };
  }

  if (q.type === "date") {
    const d = raw.date;
    if (typeof d !== "string" || !DATE_RE.test(d)) fail("date must be YYYY-MM-DD");
    const parsed = new Date(`${d}T00:00:00Z`);
    if (Number.isNaN(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== d) fail("invalid date");
    if (cfg.min_date && d < cfg.min_date) fail(`date must be on or after ${cfg.min_date}`);
    if (cfg.max_date && d > cfg.max_date) fail(`date must be on or before ${cfg.max_date}`);
    return { date: d };
  }

  if (q.type === "email") {
    if (raw.provided === false && Object.keys(raw).length === 1) return { provided: false };
    fail("email addresses are submitted through the contact or identity endpoint");
  }

  fail(`unsupported question type '${q.type}'`);
}
