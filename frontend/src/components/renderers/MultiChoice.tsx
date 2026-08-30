import { useTranslation } from "react-i18next";
import { OptionCard } from "../ui/OptionCard";
import { inputClass, type RendererProps } from "./types";
import type { OptionsValue } from "@/survey/types";

/** Multi-select with max-N counter, inert cards at the limit, exclusive options and inline "Other" (Q-4). */
export function MultiChoice({ question, value, onChange, disabled }: RendererProps<OptionsValue>) {
  const { t } = useTranslation();
  const options = question.options ?? [];
  const max = question.config?.max_selections;
  const selected = value?.options ?? [];
  const atLimit = max !== undefined && selected.length >= max;
  const exclusiveKeys = new Set(options.filter((o) => o.exclusive).map((o) => o.key));

  const toggle = (key: string) => {
    let next: string[];
    if (selected.includes(key)) {
      next = selected.filter((k) => k !== key);
    } else if (exclusiveKeys.has(key)) {
      next = [key];
    } else {
      next = [...selected.filter((k) => !exclusiveKeys.has(k)), key];
    }
    const ordered = options.map((o) => o.key).filter((k) => next.includes(k));
    const keepOther = ordered.some((k) => options.find((o) => o.key === k)?.free_text);
    if (!ordered.length) {
      onChange(undefined);
      return;
    }
    const otherText = keepOther ? value?.other_text : undefined;
    onChange({ options: ordered, ...(otherText ? { other_text: otherText } : {}) }, { commit: !keepOther || Boolean(otherText) });
  };

  return (
    <div>
      {max !== undefined && (
        <p className="mb-3 inline-block rounded-full bg-tint px-3 py-1 text-sm text-ink" aria-live="polite" data-testid="multi-counter">
          {t("multi.counter", { count: selected.length, max })} · {t("multi.limit", { max })}
        </p>
      )}
      <div className="flex flex-col gap-3" role="group">
        {options.map((o) => {
          const checked = selected.includes(o.key);
          const inert = !checked && atLimit && !exclusiveKeys.has(o.key);
          return (
            <OptionCard
              key={o.key}
              kind="checkbox"
              name={question.key}
              value={o.key}
              label={o.label as string}
              checked={checked}
              disabled={disabled}
              inert={inert}
              onChange={() => toggle(o.key)}
              className="transition-opacity duration-150"
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
                  onChange={(e) => onChange({ options: selected, other_text: e.target.value })}
                  onBlur={() => onChange({ options: selected, other_text: value?.other_text?.trim() || undefined }, { commit: true })}
                  data-testid="other-text"
                />
              )}
            </OptionCard>
          );
        })}
      </div>
    </div>
  );
}
