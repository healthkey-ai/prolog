import { useTranslation } from "react-i18next";
import { Input } from "../ui/input";
import { OptionCard } from "../ui/OptionCard";
import { RadioGroup } from "../ui/radio-group";
import { inputClass, type RendererProps } from "./types";
import type { OptionValue } from "@/survey/types";

export function SingleChoice({ question, value, onChange, disabled }: RendererProps<OptionValue>) {
  const { t } = useTranslation();
  const options = question.options ?? [];
  return (
    <RadioGroup
      value={value?.option ?? ""}
      onValueChange={(key) => {
        const o = options.find((x) => x.key === key);
        onChange({ option: key }, { commit: !o?.free_text });
      }}
      disabled={disabled}
      aria-label={question.text as string}
      className="gap-3"
    >
      {options.map((o) => {
        const checked = value?.option === o.key;
        return (
          <OptionCard key={o.key} kind="radio" value={o.key} label={o.label as string} checked={checked} disabled={disabled} data-testid={`option-${o.key}`}>
            {o.free_text && checked && (
              <Input
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
    </RadioGroup>
  );
}
