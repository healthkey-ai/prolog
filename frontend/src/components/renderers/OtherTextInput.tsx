import { useTranslation } from "react-i18next";
import { MAX_OTHER_TEXT, strip } from "@/survey/answers";
import type { AnswerValue } from "@/survey/types";
import { Input } from "../ui/input";
import { inputClass, type RendererProps } from "./types";

/** `base` with the free text attached — or without the field at all when the text is empty. */
export function withOtherText<V extends AnswerValue>(base: V, text: string | undefined): V {
  const rest = { ...base } as V & { other_text?: string };
  delete rest.other_text;
  return text ? { ...rest, other_text: text } : rest;
}

interface Props<V extends AnswerValue> {
  /** The answer without its text (the selected option(s), the ranking order); the text is attached here. */
  base: V;
  value: string | undefined;
  onChange: RendererProps<V>["onChange"];
  autoFocus?: boolean;
}

/**
 * The free-text field shown under a selected "Other" option (single, multi and
 * ranking). It owns the wiring every renderer needs: each keystroke updates
 * the draft, blur commits the trimmed text (empty drops the field).
 */
export function OtherTextInput<V extends AnswerValue>({ base, value, onChange, autoFocus }: Props<V>) {
  const { t } = useTranslation();
  return (
    <Input
      type="text"
      autoFocus={autoFocus}
      className={`${inputClass} mt-3`}
      placeholder={t("single.other")}
      aria-label={t("single.other")}
      maxLength={MAX_OTHER_TEXT}
      value={value ?? ""}
      onChange={(e) => onChange(withOtherText(base, e.target.value))}
      onBlur={(e) => onChange(withOtherText(base, strip(e.target.value) || undefined), { commit: true })}
      data-testid="other-text"
    />
  );
}
