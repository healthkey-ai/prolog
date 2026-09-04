import { OptionCard } from "../ui/OptionCard";
import { RadioGroup } from "../ui/radio-group";
import { OtherTextInput } from "./OtherTextInput";
import type { RendererProps } from "./types";
import { freeTextKeys, type OptionValue } from "@/survey/types";

export function SingleChoice({ question, value, onChange }: RendererProps<OptionValue>) {
  const options = question.options ?? [];
  const free = freeTextKeys(question);
  return (
    <RadioGroup
      value={value?.option ?? ""}
      onValueChange={(key) => onChange({ option: key }, { commit: !free.has(key) })}
      aria-label={question.text as string}
      className="gap-3"
    >
      {options.map((o) => {
        const checked = value?.option === o.key;
        return (
          <OptionCard key={o.key} kind="radio" value={o.key} label={o.label as string} checked={checked} data-testid={`option-${o.key}`}>
            {o.free_text && checked && <OtherTextInput autoFocus base={{ option: o.key }} value={value?.other_text} onChange={onChange} />}
          </OptionCard>
        );
      })}
    </RadioGroup>
  );
}
