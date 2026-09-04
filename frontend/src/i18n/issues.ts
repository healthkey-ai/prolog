import type { TFunction } from "i18next";
import type { AnswerIssue } from "@/survey/types";

/**
 * Participant-facing text for answer rejections (local or from the server):
 * every code maps to an `error.<code>` chrome string; unknown codes fall back
 * to the generic one. Never shows the engine's English message.
 */
export function issueMessages(issues: AnswerIssue[], t: TFunction): string[] {
  const out: string[] = [];
  for (const issue of issues) {
    const text = t(`error.${issue.code}`, { ...issue.params, defaultValue: t("error.generic") });
    if (!out.includes(text)) out.push(text);
  }
  return out;
}
