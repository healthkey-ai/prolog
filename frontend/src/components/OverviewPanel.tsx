import { useTranslation } from "react-i18next";
import { Sheet } from "./ui/Sheet";
import type { OverviewSection, QuestionStatus } from "@/survey/navigation";
import type { AnswerValue, Question, Section } from "@/survey/types";
import { cn } from "@/lib/utils";

interface Props {
  open: boolean;
  onClose: () => void;
  sections: OverviewSection[];
  definitionSections: Section[];
  answers: Record<string, AnswerValue>;
  onNavigate: (key: string) => void;
  countryLabels?: Record<string, string>;
}

const GLYPH: Record<QuestionStatus, string> = { answered: "✓", skipped: "–", current: "●", unanswered: "○", unreachable: "○" };

function summarize(q: Question, value: AnswerValue | undefined, countryLabels?: Record<string, string>): string {
  if (!value) return "";
  if ("skipped" in value) return "";
  const labelOf = (k: string) => (q.options ?? []).find((o) => o.key === k)?.label as string | undefined;
  if ("option" in value) return (labelOf(value.option) ?? countryLabels?.[value.option] ?? value.option) + (value.other_text ? ` — ${value.other_text}` : "");
  if ("options" in value) return value.options.map((k) => labelOf(k) ?? k).join(", ");
  if ("value" in value) return String(value.value);
  if ("order" in value) return value.order.map((k, i) => `${i + 1}. ${labelOf(k) ?? k}`).join(" ");
  if ("ratings" in value) return Object.values(value.ratings).join(" · ");
  if ("text" in value) return value.text;
  if ("number" in value) return String(value.number);
  if ("date" in value) return value.date;
  if ("provided" in value) return value.provided ? "✓" : "";
  return "";
}

export function OverviewPanel({ open, onClose, sections, definitionSections, answers, onNavigate, countryLabels }: Props) {
  const { t } = useTranslation();
  const statusLabel: Record<QuestionStatus, string> = {
    answered: t("overview.answered"),
    skipped: t("overview.skipped"),
    current: t("overview.current"),
    unanswered: t("overview.unanswered"),
    unreachable: t("overview.unreachable"),
  };
  return (
    <Sheet open={open} onClose={onClose} title={t("overview.title")} closeLabel={t("overview.close")}>
      <nav aria-label={t("overview.title")}>
        {sections.map((s) => (
          <section key={s.key} className="py-2">
            <h3 className="px-1 py-2 text-[13px] font-medium uppercase tracking-[0.08em] text-ink-soft">{definitionSections[s.sectionIndex].title as string}</h3>
            <ul className="divide-y divide-line">
              {s.rows.map((row) => (
                <li key={row.key}>
                  <button
                    type="button"
                    disabled={!row.navigable}
                    onClick={() => {
                      onNavigate(row.key);
                      onClose();
                    }}
                    aria-current={row.status === "current" ? "step" : undefined}
                    className={cn(
                      "flex w-full items-start gap-3 rounded-[var(--p-radius-input)] px-1 py-3 text-left hover:bg-tint disabled:cursor-not-allowed disabled:opacity-50",
                    )}
                    data-testid={`overview-${row.key}`}
                  >
                    <span
                      className={cn(
                        "mt-0.5 w-4 text-center",
                        row.status === "answered" && "text-success",
                        row.status === "skipped" && "text-ink-soft",
                        row.status === "current" && "text-primary",
                        (row.status === "unanswered" || row.status === "unreachable") && "text-line",
                      )}
                      aria-hidden
                    >
                      {GLYPH[row.status]}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate">{row.question.text as string}</span>
                      <span className="block truncate text-sm text-ink-soft">
                        {row.status === "skipped" ? t("overview.skipped") : summarize(row.question, answers[row.key], countryLabels) || t("overview.noAnswer")}
                      </span>
                    </span>
                    <span className="sr-only">{statusLabel[row.status]}</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </nav>
    </Sheet>
  );
}
