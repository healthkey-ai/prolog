/**
 * Survey definition and answer types.
 *
 * Text fields are `string` once localized by the API, or an i18n object in a
 * raw definition file; the engine never reads text, so both are accepted.
 */
export type Text = string | Record<string, string>;

export type QuestionType =
  | "info"
  | "single"
  | "dropdown"
  | "multi"
  | "scale"
  | "ranking"
  | "matrix"
  | "text"
  | "number"
  | "date"
  | "email";

export interface Option {
  key: string;
  label: Text;
  exclusive?: boolean;
  free_text?: boolean;
}

export interface ScaleConfig {
  min: number;
  max: number;
  min_label?: Text;
  max_label?: Text;
  point_labels?: Text[];
  /** matrix only: a non-scored "not applicable" column; a row rated `"na"` counts as answered. */
  not_applicable?: Text;
}

/** The matrix rating that means "this row does not apply" (config.scale.not_applicable). */
export const NOT_APPLICABLE = "na";
export type Rating = number | typeof NOT_APPLICABLE;

export interface QuestionConfig {
  max_selections?: number;
  min_selections?: number;
  options_source?: string;
  /** Restrict `options_source` to these keys; the runner offers and accepts no others. */
  options_source_include?: string[];
  /** Order these `options_source` keys first. Ordering only: everything else stays offered. */
  options_source_priority?: string[];
  scale?: ScaleConfig;
  rows_from?: string;
  rows?: { key: string; label: Text }[];
  optional_items?: string[];
  max_length?: number;
  multiline?: boolean;
  min_value?: number;
  max_value?: number;
  integer?: boolean;
  min_date?: string;
  max_date?: string;
  store_separately?: boolean;
  link_identity?: boolean;
  /** Consents offered with the address, each recorded separately (CON-3/4). */
  consents?: CaptureConsent[];
  /** A line above the boxes, e.g. an invitation to tick what applies. */
  consents_label?: Text;
  /** How many of them must be ticked before an address is accepted; default 0. */
  consents_min?: number;
  /** A note under the tick boxes — withdrawal, where to read more; inline Markdown. */
  consents_note?: Text;
}

export interface CaptureConsent {
  key: string;
  text: Text;
}

export type ConditionOp = "eq" | "neq" | "in" | "contains" | "not_contains" | "answered";

export interface Condition {
  question: string;
  op: ConditionOp;
  value?: string;
  values?: string[];
}

export interface Question {
  key: string;
  type: QuestionType;
  text: Text;
  help?: Text;
  required?: boolean;
  options?: Option[];
  visible_if?: Condition[];
  config?: QuestionConfig;
}

export interface Section {
  key: string;
  title: Text;
  description?: Text;
  visible_if?: Condition[];
  questions: Question[];
}

export type SkipPolicy = "soft" | "hard" | "none";

export interface Presentation {
  /** Only "question" exists today; "section" is reserved and rejected by the validator. */
  mode?: "question";
  overview?: boolean;
  section_interstitials?: boolean;
  skip_policy?: SkipPolicy;
  progress?: "bar" | "steps" | "none";
  /** Where a multilingual survey asks for a language. Default "inline". */
  language_step?: "inline" | "first" | "auto";
}

export interface Participation {
  anonymous?: boolean;
  resume?: "browser_token" | "account" | "none";
}

export interface Consent {
  version: string;
  text: Text;
  required?: boolean;
  privacy_url?: string;
}

export interface Definition {
  slug: string;
  version: string;
  default_language: string;
  languages: string[];
  title: Text;
  intro?: Text;
  completion?: Text;
  estimated_minutes?: number;
  theme?: string;
  participation?: Participation;
  presentation?: Presentation;
  consent?: Consent;
  sections: Section[];
}

export type SkipValue = { skipped: true };
export type OptionValue = { option: string; other_text?: string };
export type OptionsValue = { options: string[]; other_text?: string };
export type ScaleValue = { value: number };
export type RankingValue = { order: string[]; other_text?: string };
export type MatrixValue = { ratings: Record<string, Rating> };
export type TextValue = { text: string };
export type NumberValue = { number: number };
export type DateValue = { date: string };
/** `consents` lists the keys ticked with the address — the marker is all the response holds. */
export type EmailValue = { provided: boolean; consents?: string[] };

export type AnswerValue =
  | SkipValue
  | OptionValue
  | OptionsValue
  | ScaleValue
  | RankingValue
  | MatrixValue
  | TextValue
  | NumberValue
  | DateValue
  | EmailValue;

export type Answers = Record<string, AnswerValue>;

/** One answer rejection: a stable code plus the values a message is built from (never English text). */
export interface AnswerIssue {
  code: string;
  params: Record<string, unknown>;
}

export const ANSWERABLE: ReadonlySet<QuestionType> = new Set([
  "single",
  "dropdown",
  "multi",
  "scale",
  "ranking",
  "matrix",
  "text",
  "number",
  "date",
  "email",
]);

export function questionRequired(q: Question): boolean {
  return q.required ?? q.type !== "info";
}

export function questionConfig(q: Question): QuestionConfig {
  return q.config ?? {};
}

export function questionOptions(q: Question): Option[] {
  return q.options ?? [];
}

/** Keys of the options that take free text (the "Other" options). */
export function freeTextKeys(q: Question): Set<string> {
  return new Set(questionOptions(q).filter((o) => o.free_text).map((o) => o.key));
}

/** Keys of the options that cannot be combined with any other ("none of these"). */
export function exclusiveKeys(q: Question): Set<string> {
  return new Set(questionOptions(q).filter((o) => o.exclusive).map((o) => o.key));
}

/** An option's (localized) label by key; undefined when the key is not one of the question's own options. */
export function optionLabel(q: Question, key: string): string | undefined {
  return questionOptions(q).find((o) => o.key === key)?.label as string | undefined;
}

export function skipPolicy(def: Definition): SkipPolicy {
  return def.presentation?.skip_policy ?? "soft";
}
