import { OptionCard } from "../ui/OptionCard";
import { RadioGroup } from "../ui/radio-group";
import { OtherTextInput } from "./OtherTextInput";
import type { RendererProps } from "./types";
import { offeredOptionKeys } from "@/survey/visibility";
import { freeTextKeys, optionLabel, questionOptions, type AnswerValue, type OptionValue, type Question } from "@/survey/types";

interface Props extends RendererProps<OptionValue> {
  answers?: Record<string, AnswerValue>;
  questions?: Record<string, Question>;
}

export function SingleChoice({ question, value, onChange, answers = {}, questions = {} }: Props) {
  const sourceKey = question.config?.options_from;
  const source = sourceKey ? questions[sourceKey] : undefined;
  const sourceAnswer = sourceKey ? answers[sourceKey] : undefined;
  // With options_from the list is what the source question selected, labelled
  // as the source labels it — a free-text "Other" by what was typed there, so
  // the respondent recognises their own words (as the matrix does for rows).
  const options = sourceKey
    ? offeredOptionKeys(question, answers, questions).map((key) => {
        const own = questionOptions(question).find((o) => o.key === key);
        if (own) return own;
        const fromSource = source?.options?.find((o) => o.key === key);
        const typed = fromSource?.free_text && sourceAnswer && "other_text" in sourceAnswer ? sourceAnswer.other_text : undefined;
        return { key, label: typed || (source && optionLabel(source, key)) || key };
      })
    : questionOptions(question);
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
