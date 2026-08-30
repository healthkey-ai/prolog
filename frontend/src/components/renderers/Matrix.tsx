import { useTranslation } from "react-i18next";
import { ScaleControl } from "./Scale";
import type { RendererProps } from "./types";
import type { AnswerValue, MatrixValue, Question } from "@/survey/types";
import { matrixRows } from "@/survey/visibility";

interface Props extends RendererProps<MatrixValue> {
  answers: Record<string, AnswerValue>;
  questions: Record<string, Question>;
}

/** One card per row (fixed rows or the source selection), a scale per row, legend once (Q-7). */
export function Matrix({ question, value, onChange, answers, questions, disabled }: Props) {
  const { t } = useTranslation();
  const cfg = question.config ?? {};
  const scale = cfg.scale!;
  const rows = matrixRows(question, answers);
  const source = cfg.rows_from ? questions[cfg.rows_from] : undefined;
  const sourceAnswer = cfg.rows_from ? answers[cfg.rows_from] : undefined;

  const labelOf = (row: string): string => {
    const fixed = cfg.rows?.find((r) => r.key === row);
    if (fixed) return fixed.label as string;
    const option = source?.options?.find((o) => o.key === row);
    if (option?.free_text && sourceAnswer && "other_text" in sourceAnswer && sourceAnswer.other_text) return sourceAnswer.other_text;
    return (option?.label as string) ?? row;
  };

  const ratings = value?.ratings ?? {};
  const rate = (row: string, v: number) => {
    const next = { ...ratings, [row]: v };
    const complete = rows.every((r) => r in next);
    onChange({ ratings: next }, { commit: complete });
  };
  const points = Array.from({ length: scale.max - scale.min + 1 }, (_, i) => scale.min + i);
  const labels = scale.point_labels as string[] | undefined;

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-ink-soft" data-testid="matrix-legend">
        <span className="sr-only">{t("matrix.legend")}: </span>
        {labels ? points.map((p, i) => `${p} ${labels[i]}`).join(" · ") : `${scale.min} ${scale.min_label ?? ""} → ${scale.max} ${scale.max_label ?? ""}`}
      </p>
      {rows.map((row) => (
        <div key={row} className="rounded-[var(--p-radius-card)] border border-line bg-surface p-4" data-testid={`matrix-row-${row}`}>
          <p className="mb-3 font-heading text-[1.05rem]" id={`${question.key}-${row}-label`}>
            {labelOf(row)}
          </p>
          <ScaleControl min={scale.min} max={scale.max} value={ratings[row]} onSelect={(v) => rate(row, v)} name={`${question.key}-${row}`} disabled={disabled} ariaLabel={labelOf(row)} />
        </div>
      ))}
    </div>
  );
}
