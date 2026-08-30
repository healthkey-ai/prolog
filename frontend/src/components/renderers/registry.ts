import type { ComponentType } from "react";
import { Matrix } from "./Matrix";
import { MultiChoice } from "./MultiChoice";
import { Ranking } from "./Ranking";
import type { RendererProps } from "./types";
import type { AnswerValue, Question, QuestionType } from "@/survey/types";

export interface ExtraProps {
  answers: Record<string, AnswerValue>;
  questions: Record<string, Question>;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyRenderer = ComponentType<any>;

/** Renderers for the complex question types (Phase 4). */
export const extraRenderers: Partial<Record<QuestionType, AnyRenderer>> = {
  multi: MultiChoice,
  ranking: Ranking,
  matrix: Matrix,
};

export type { RendererProps };
