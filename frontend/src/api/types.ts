import type { AnswerValue, Answers, Definition } from "@/survey/types";

/** Localized definition as served by GET /api/run/surveys/{slug}/ */
export interface RunnerDefinition extends Definition {
  language: string;
  theme_code: string;
  /** Legal pages this deployment mounted (e.g. ["privacy"]); absent or empty means none. */
  legal_pages?: string[];
  /** Per-language "machine" | "reviewed"; the runner discloses a machine one to the respondent. */
  translation_status?: Record<string, "machine" | "reviewed">;
  /** The served language is machine-translated and the deployment declared it so: say it on the intro. */
  machine_notice?: boolean;
}

/**
 * Where the signed-in participant stands with an account survey, from the
 * server (GET /surveys/<slug>/status/). With `account` false the server keeps
 * no place for them and the response id the browser kept is the only pointer.
 */
export interface ParticipantStatus {
  account: boolean;
  in_progress: string | null;
  last_submitted: string | null;
  /** The active version offers "Update my answers". */
  revisable: boolean;
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
  /** The invitation administration this response answers, if any (RUN-5). */
  administration: string | null;
  answers: Answers;
  visible: string[];
  missing: string[];
  progress: { answered: number; total: number };
}

export interface AnswerResult {
  answer: { key: string; value: AnswerValue };
  /** Downstream answers the save invalidated; those in `pruned` survive with a reduced value. */
  invalidated: string[];
  pruned: Record<string, AnswerValue>;
  visible: string[];
  missing: string[];
  progress: { answered: number; total: number };
}

export interface OptionsSource {
  source: string;
  language: string;
  options: { key: string; label: string }[];
}

/** A rejected answer as the server reports it: a stable code plus typed params (see survey/answers.ts). */
export interface ApiIssue {
  code: string;
  params: Record<string, unknown>;
  message?: string;
}

export interface ApiErrorBody {
  detail?: string;
  missing?: string[];
  [field: string]: unknown;
}
