import { lazy, type ComponentType } from "react";
import type { RendererProps } from "./types";

/** Question types whose renderers are code-split (the rest render inline in QuestionScreen). */
export type ExtraType = "multi" | "ranking" | "matrix";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyRenderer = ComponentType<any>;

/**
 * Renderers for the complex question types, code-split so the common path
 * (single/dropdown/scale/text) does not pay for dnd-kit (NFR-7). Every
 * QuestionType is covered here or inline: the definition schema and the
 * runner's QuestionType union carry the same eleven members.
 */
export const extraRenderers: Record<ExtraType, AnyRenderer> = {
  multi: lazy(() => import("./MultiChoice").then((m) => ({ default: m.MultiChoice }))),
  ranking: lazy(() => import("./Ranking").then((m) => ({ default: m.Ranking }))),
  matrix: lazy(() => import("./Matrix").then((m) => ({ default: m.Matrix }))),
};

export type { RendererProps };
