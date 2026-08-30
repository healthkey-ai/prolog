import type { RendererProps } from "./types";

export function Info({ question }: RendererProps) {
  return question.help ? <p className="text-ink-soft">{question.help as string}</p> : null;
}
