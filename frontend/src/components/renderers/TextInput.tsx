import { useTranslation } from "react-i18next";
import { Input } from "../ui/input";
import { Textarea } from "../ui/textarea";
import { inputClass, type RendererProps } from "./types";
import { MAX_TEXT_LENGTH, strip } from "@/survey/answers";
import type { TextValue } from "@/survey/types";

export function TextInput({ question, value, onChange }: RendererProps<TextValue>) {
  const { t } = useTranslation();
  const cfg = question.config ?? {};
  const multiline = cfg.multiline ?? false; // the server fills the default (normalize.py)
  const limit = Math.min(cfg.max_length || MAX_TEXT_LENGTH, MAX_TEXT_LENGTH); // the engines cap every text answer
  const text = value?.text ?? "";
  const common = {
    className: inputClass,
    value: text,
    maxLength: limit,
    "aria-label": question.text as string,
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => onChange(e.target.value ? { text: e.target.value } : undefined),
    onBlur: () => onChange(strip(text) ? { text: strip(text) } : undefined, { commit: true }),
    "data-testid": "text-input",
  };
  return (
    <div>
      {multiline ? <Textarea rows={6} {...common} /> : <Input type="text" {...common} />}
      {cfg.max_length && (
        <p className="mt-1 text-right text-sm text-muted-foreground" aria-live="polite">
          {t("text.remaining", { count: limit - [...text].length })}
        </p>
      )}
    </div>
  );
}
