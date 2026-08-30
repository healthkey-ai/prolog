import type { AnswerValue, Question } from "@/survey/types";

export interface RendererProps<V extends AnswerValue = AnswerValue> {
  question: Question;
  value: V | undefined;
  /** Update the draft; `commit` asks the wizard to save immediately (instant controls). */
  onChange: (value: V | undefined, opts?: { commit?: boolean }) => void;
  language: string;
  disabled?: boolean;
  /** Errors from the last save attempt or local validation. */
  errors?: string[];
}

export const inputClass =
  "w-full min-h-[52px] rounded-[var(--p-radius-input)] border border-line bg-surface px-4 py-3 text-[1.05rem] text-ink placeholder:text-ink-soft focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus";
