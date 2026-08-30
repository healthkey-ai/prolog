import { useTranslation } from "react-i18next";
import { MAX_OTHER_TEXT } from "@/survey/answers";
import { Input } from "../ui/input";
import { inputClass } from "./types";

interface Props {
  value: string | undefined;
  /** Every keystroke updates the draft; blur commits the trimmed text (empty clears it). */
  onChange: (text: string) => void;
  onCommit: (text: string | undefined) => void;
  autoFocus?: boolean;
}

/** The free-text field shown under a selected "Other" option (single, multi and ranking). */
export function OtherTextInput({ value, onChange, onCommit, autoFocus }: Props) {
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
      onChange={(e) => onChange(e.target.value)}
      onBlur={(e) => onCommit(e.target.value.trim() || undefined)}
      data-testid="other-text"
    />
  );
}
