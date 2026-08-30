import { useTranslation } from "react-i18next";
import { Input } from "../ui/input";
import { Textarea } from "../ui/textarea";
import { inputClass, type RendererProps } from "./types";
import type { TextValue } from "@/survey/types";

export function TextInput({ question, value, onChange, disabled }: RendererProps<TextValue>) {
  const { t } = useTranslation();
  const cfg = question.config ?? {};
  const multiline = cfg.multiline ?? (cfg.max_length ?? 0) > 200;
  const text = value?.text ?? "";
  const common = {
    className: inputClass,
    value: text,
    maxLength: cfg.max_length,
    disabled,
    "aria-label": question.text as string,
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => onChange(e.target.value ? { text: e.target.value } : undefined),
    onBlur: () => onChange(text.trim() ? { text: text.trim() } : undefined, { commit: true }),
    "data-testid": "text-input",
  };
  return (
    <div>
      {multiline ? <Textarea rows={6} {...common} /> : <Input type="text" {...common} />}
      {cfg.max_length && (
        <p className="mt-1 text-right text-sm text-muted-foreground" aria-live="polite">
          {t("text.remaining", { count: cfg.max_length - text.length })}
        </p>
      )}
    </div>
  );
}
