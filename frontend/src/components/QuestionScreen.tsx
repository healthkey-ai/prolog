import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { DateInput } from "./renderers/DateInput";
import { Dropdown } from "./renderers/Dropdown";
import { EmailCapture } from "./renderers/EmailCapture";
import { Info } from "./renderers/Info";
import { NumberInput } from "./renderers/NumberInput";
import { Scale } from "./renderers/Scale";
import { SingleChoice } from "./renderers/SingleChoice";
import { TextInput } from "./renderers/TextInput";
import { Unsupported } from "./renderers/Unsupported";
import type { RendererProps } from "./renderers/types";
import { extraRenderers } from "./renderers/registry";
import { questionRequired, type AnswerValue, type Question } from "@/survey/types";

interface Props extends RendererProps {
  questionNumber: number;
  questionTotal: number;
  onSubmitEmail?: (email: string) => Promise<void>;
  answers: Record<string, AnswerValue>;
}

export function QuestionScreen(props: Props) {
  const { t } = useTranslation();
  const { question, questionNumber, questionTotal, errors } = props;
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    heading.current?.focus();
  }, [question.key]);
  const required = questionRequired(question);
  const isInfo = question.type === "info";

  return (
    <div className="animate-[fadeUp_200ms_ease-out]" data-testid={`question-${question.key}`} data-type={question.type}>
      <p className="text-[13px] font-medium uppercase tracking-[0.08em] text-ink-soft">
        {isInfo ? t("question.info") : t("question.eyebrow", { number: questionNumber, total: questionTotal })}
        {!isInfo && !required && <span className="ml-2 rounded bg-tint px-2 py-0.5 normal-case tracking-normal">{t("question.optional")}</span>}
      </p>
      <fieldset className="mt-2 border-0 p-0">
        <legend className="w-full">
          <h1 ref={heading} tabIndex={-1} className="text-[1.4rem] leading-snug outline-none sm:text-[1.65rem]">
            {question.text as string}
          </h1>
        </legend>
        {question.help && question.type !== "email" && question.type !== "info" && <p className="mt-2 text-ink-soft">{question.help as string}</p>}
        <div className="mt-6">{renderControl(question, props)}</div>
        {errors && errors.length > 0 && (
          <ul className="mt-3 text-sm text-error" role="alert">
            {errors.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        )}
      </fieldset>
    </div>
  );
}

function renderControl(question: Question, props: Props) {
  // Each renderer narrows the value type itself; the dispatcher passes the same props through.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const p = props as any;
  switch (question.type) {
    case "info":
      return <Info {...p} />;
    case "single":
      return <SingleChoice {...p} />;
    case "dropdown":
      return <Dropdown {...p} />;
    case "scale":
      return <Scale {...p} />;
    case "text":
      return <TextInput {...p} />;
    case "number":
      return <NumberInput {...p} />;
    case "date":
      return <DateInput {...p} />;
    case "email":
      return <EmailCapture {...p} onSubmitEmail={props.onSubmitEmail ?? (async () => {})} />;
    default: {
      const Extra = extraRenderers[question.type];
      return Extra ? <Extra {...p} answers={props.answers} /> : <Unsupported type={question.type} />;
    }
  }
}
