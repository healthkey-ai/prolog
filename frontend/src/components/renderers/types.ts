import type { AnswerValue, Question } from "@/survey/types";

export interface RendererProps<V extends AnswerValue = AnswerValue> {
  question: Question;
  value: V | undefined;
  /** Update the draft; `commit` saves immediately (instant controls), `advance` also moves on once saved. */
  onChange: (value: V | undefined, opts?: { commit?: boolean; advance?: boolean }) => void;
  language: string;
  disabled?: boolean;
  /** Errors from the last save attempt or local validation. */
  errors?: string[];
}

/** Sizing applied to shadcn Input/Textarea in the runner (≥52px targets, 17px text). */
export const inputClass = "min-h-[52px] rounded-[var(--p-radius-input)] bg-card px-4 py-3 text-[1.05rem] md:text-[1.05rem]";
