import { useTranslation } from "react-i18next";
import { OptionCard } from "../ui/OptionCard";
import { inputClass, type RendererProps } from "./types";
import type { OptionValue } from "@/survey/types";

export function SingleChoice({ question, value, onChange, disabled }: RendererProps<OptionValue>) {
  const { t } = useTranslation();
  const options = question.options ?? [];
  return (
    <div className="flex flex-col gap-3" role="radiogroup">
      {options.map((o) => {
        const checked = value?.option === o.key;
        return (
          <OptionCard
            key={o.key}
            kind="radio"
            name={question.key}
            value={o.key}
            label={o.label as string}
            checked={checked}
            disabled={disabled}
            onChange={() => onChange({ option: o.key }, { commit: !o.free_text })}
            data-testid={`option-${o.key}`}
          >
            {o.free_text && checked && (
              <input
                type="text"
                autoFocus
                className={`${inputClass} mt-3`}
                placeholder={t("single.other")}
                aria-label={t("single.other")}
                maxLength={500}
                value={value?.other_text ?? ""}
                onChange={(e) => onChange({ option: o.key, other_text: e.target.value })}
                onBlur={() => onChange({ option: o.key, other_text: value?.other_text?.trim() || undefined }, { commit: true })}
              />
            )}
          </OptionCard>
        );
      })}
    </div>
  );
}
