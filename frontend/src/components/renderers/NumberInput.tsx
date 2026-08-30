import { useTranslation } from "react-i18next";
import { inputClass, type RendererProps } from "./types";
import type { NumberValue } from "@/survey/types";

export function NumberInput({ question, value, onChange, disabled }: RendererProps<NumberValue>) {
  const { t } = useTranslation();
  const cfg = question.config ?? {};
  const parse = (s: string) => {
    if (s === "") return undefined;
    const n = Number(s);
    return Number.isNaN(n) ? undefined : { number: n };
  };
  return (
    <input
      type="number"
      inputMode={cfg.integer ? "numeric" : "decimal"}
      step={cfg.integer ? 1 : "any"}
      min={cfg.min_value}
      max={cfg.max_value}
      className={inputClass}
      placeholder={t("number.placeholder")}
      aria-label={question.text as string}
      disabled={disabled}
      value={value?.number ?? ""}
      onChange={(e) => onChange(parse(e.target.value))}
      onBlur={(e) => onChange(parse(e.target.value), { commit: true })}
      data-testid="number-input"
    />
  );
}
