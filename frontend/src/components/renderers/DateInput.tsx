import { Input } from "../ui/input";
import { inputClass, type RendererProps } from "./types";
import type { DateValue } from "@/survey/types";

export function DateInput({ question, value, onChange }: RendererProps<DateValue>) {
  const cfg = question.config ?? {};
  return (
    <Input
      type="date"
      className={inputClass}
      min={cfg.min_date}
      max={cfg.max_date}
      aria-label={question.text as string}
      value={value?.date ?? ""}
      onChange={(e) => onChange(e.target.value ? { date: e.target.value } : undefined)}
      onBlur={(e) => onChange(e.target.value ? { date: e.target.value } : undefined, { commit: true })}
      data-testid="date-input"
    />
  );
}
