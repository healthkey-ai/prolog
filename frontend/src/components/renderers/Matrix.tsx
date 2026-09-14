import { useTranslation } from "react-i18next";
import { ScaleControl } from "./Scale";
import type { RendererProps } from "./types";
import { optionLabel, type AnswerValue, type MatrixValue, type Question, type Rating } from "@/survey/types";
import { matrixRows } from "@/survey/visibility";

interface Props extends RendererProps<MatrixValue> {
  answers: Record<string, AnswerValue>;
  questions: Record<string, Question>;
}

/** One card per row (fixed rows or the source selection), a scale per row, legend once (Q-7). */
export function Matrix({ question, value, onChange, answers, questions }: Props) {
  const { t } = useTranslation();
  const cfg = question.config ?? {};
  const scale = cfg.scale!;
  const rows = matrixRows(question, answers, questions);
  const source = cfg.rows_from ? questions[cfg.rows_from] : undefined;
  const sourceAnswer = cfg.rows_from ? answers[cfg.rows_from] : undefined;

  const labelOf = (row: string): string => {
    const fixed = cfg.rows?.find((r) => r.key === row);
    if (fixed) return fixed.label as string;
    const option = source?.options?.find((o) => o.key === row);
    if (option?.free_text && sourceAnswer && "other_text" in sourceAnswer && sourceAnswer.other_text) return sourceAnswer.other_text;
    return (source && optionLabel(source, row)) ?? row;
  };

  // Only the current rows, in rows order: while the source question's save is
  // still in flight the cached value may hold rows it no longer selects, and
  // committing them would fail validation ("unknown rows") for a matrix that
  // looks complete. Rows order is the server's canonical shape (and the one
  // survey/answers.ts produces), so a matrix rated out of order still compares
  // equal to the stored answer and Next does not re-save it.
  const inRowOrder = (src: Record<string, Rating>): Record<string, Rating> => Object.fromEntries(rows.filter((r) => r in src).map((r) => [r, src[r]]));
  const ratings = inRowOrder(value?.ratings ?? {});
  const rate = (row: string, v: Rating) => {
    const next = inRowOrder({ ...ratings, [row]: v });
    const complete = rows.every((r) => r in next);
    onChange({ ratings: next }, { commit: complete });
  };
  const points = Array.from({ length: scale.max - scale.min + 1 }, (_, i) => scale.min + i);
  const labels = scale.point_labels as string[] | undefined;
  const notApplicable = scale.not_applicable as string | undefined;
  const legend = labels ? points.map((p, i) => `${p} ${labels[i]}`).join(" · ") : `${scale.min} ${scale.min_label ?? ""} → ${scale.max} ${scale.max_label ?? ""}`;

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-ink-soft" data-testid="matrix-legend">
        <span className="sr-only">{t("matrix.legend")}: </span>
        {notApplicable ? `${legend} · ${notApplicable}` : legend}
      </p>
      {rows.map((row) => (
        <div key={row} className="rounded-[var(--p-radius-card)] border border-border bg-card p-4" data-testid={`matrix-row-${row}`}>
          <p className="mb-3 font-heading text-[1.05rem]" id={`${question.key}-${row}-label`}>
            {labelOf(row)}
          </p>
          <ScaleControl
            min={scale.min}
            max={scale.max}
            value={ratings[row]}
            onSelect={(v) => rate(row, v)}
            name={`${question.key}-${row}`}
            notApplicable={notApplicable}
            labelledBy={`${question.key}-${row}-label`}
            ariaLabel={labelOf(row)}
          />
        </div>
      ))}
    </div>
  );
}
