import type { ComponentType } from "react";
import type { RendererProps } from "./types";
import type { AnswerValue, QuestionType } from "@/survey/types";

/** Renderers registered by later phases (multi, ranking, matrix) plug in here. */
export const extraRenderers: Partial<Record<QuestionType, ComponentType<RendererProps<never> & { answers: Record<string, AnswerValue> }>>> = {};
