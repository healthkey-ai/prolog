import { OptionCard } from "../ui/OptionCard";
import { RadioGroup } from "../ui/radio-group";
import { OtherTextInput } from "./OtherTextInput";
import type { RendererProps } from "./types";
import type { OptionValue } from "@/survey/types";

export function SingleChoice({ question, value, onChange }: RendererProps<OptionValue>) {
  const options = question.options ?? [];
  return (
    <RadioGroup
      value={value?.option ?? ""}
      onValueChange={(key) => {
        const o = options.find((x) => x.key === key);
        onChange({ option: key }, { commit: !o?.free_text });
      }}
      aria-label={question.text as string}
      className="gap-3"
    >
      {options.map((o) => {
        const checked = value?.option === o.key;
        return (
          <OptionCard key={o.key} kind="radio" value={o.key} label={o.label as string} checked={checked} data-testid={`option-${o.key}`}>
            {o.free_text && checked && (
              <OtherTextInput autoFocus value={value?.other_text} onChange={(text) => onChange({ option: o.key, other_text: text })} onCommit={(text) => onChange({ option: o.key, other_text: text }, { commit: true })} />
            )}
          </OptionCard>
        );
      })}
    </RadioGroup>
  );
}
