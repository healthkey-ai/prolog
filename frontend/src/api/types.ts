import type { AnswerValue, Answers, Definition } from "@/survey/types";

/** Localized definition as served by GET /api/run/surveys/{slug}/ */
export interface RunnerDefinition extends Definition {
  language: string;
  theme_code: string;
  translation_status: Record<string, "machine" | "reviewed">;
}

export interface ResponseSummary {
  id: string;
  slug: string;
  version: string;
  language: string;
  status: "in_progress" | "submitted";
  started_at: string;
  submitted_at: string | null;
  last_question_key: string;
  answers: Answers;
  visible: string[];
  missing: string[];
  progress: { answered: number; total: number };
}

export interface AnswerResult {
  answer: { key: string; value: AnswerValue };
  invalidated: string[];
  visible: string[];
  missing: string[];
  progress: { answered: number; total: number };
}

export interface OptionsSource {
  source: string;
  language: string;
  options: { key: string; label: string }[];
}

export interface ApiErrorBody {
  detail?: string;
  missing?: string[];
  [field: string]: unknown;
}
