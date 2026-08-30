import { lazy, type ComponentType } from "react";
import type { RendererProps } from "./types";
import type { AnswerValue, Question, QuestionType } from "@/survey/types";

export interface ExtraProps {
  answers: Record<string, AnswerValue>;
  questions: Record<string, Question>;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyRenderer = ComponentType<any>;

/**
 * Renderers for the complex question types, code-split so the common path
 * (single/dropdown/scale/text) does not pay for dnd-kit (NFR-7).
 */
export const extraRenderers: Partial<Record<QuestionType, AnyRenderer>> = {
  multi: lazy(() => import("./MultiChoice").then((m) => ({ default: m.MultiChoice }))),
  ranking: lazy(() => import("./Ranking").then((m) => ({ default: m.Ranking }))),
  matrix: lazy(() => import("./Matrix").then((m) => ({ default: m.Matrix }))),
};

export type { RendererProps };
