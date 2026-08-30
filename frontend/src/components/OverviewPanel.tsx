import { useTranslation } from "react-i18next";
import { Button } from "./ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "./ui/sheet";
import { useMediaQuery } from "@/lib/useMediaQuery";
import type { OverviewSection, QuestionStatus } from "@/survey/navigation";
import { optionLabel, type AnswerValue, type Question, type Section } from "@/survey/types";
import { Eyebrow } from "./Eyebrow";
import { cn } from "@/lib/utils";

interface Props {
  open: boolean;
  onClose: () => void;
  sections: OverviewSection[];
  definitionSections: Section[];
  answers: Record<string, AnswerValue>;
  onNavigate: (key: string) => void;
  /** Labels of option-source values (e.g. country names), by source then key. */
  sourceLabels?: Record<string, Record<string, string>>;
}

const GLYPH: Record<QuestionStatus, string> = { answered: "✓", skipped: "–", current: "●", unanswered: "○", unreachable: "○" };

function summarize(q: Question, value: AnswerValue | undefined, sourceLabels?: Record<string, Record<string, string>>): string {
  if (!value) return "";
  if ("skipped" in value) return "";
  const labelOf = (k: string) => optionLabel(q, k);
  const source = q.config?.options_source;
  if ("option" in value) return (labelOf(value.option) ?? (source ? sourceLabels?.[source]?.[value.option] : undefined) ?? value.option) + (value.other_text ? ` — ${value.other_text}` : "");
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

export function OverviewPanel({ open, onClose, sections, definitionSections, answers, onNavigate, sourceLabels }: Props) {
  const { t } = useTranslation();
  const statusLabel: Record<QuestionStatus, string> = {
    answered: t("overview.answered"),
    skipped: t("overview.skipped"),
    current: t("overview.current"),
    unanswered: t("overview.unanswered"),
    unreachable: t("overview.unreachable"),
  };
  const desktop = useMediaQuery("(min-width: 1024px)");
  return (
    <Sheet open={open} onOpenChange={(o) => !o && onClose()}>
      <SheetContent side={desktop ? "right" : "bottom"} className="max-h-[85vh] overflow-y-auto rounded-t-[var(--p-radius-sheet)] bg-card text-foreground lg:max-h-none lg:w-[420px] lg:rounded-none lg:rounded-l-[var(--p-radius-sheet)] sm:max-w-none" showCloseButton={false}>
        <SheetHeader className="flex-row items-center justify-between border-b border-border">
          <SheetTitle className="text-lg">{t("overview.title")}</SheetTitle>
          <SheetDescription className="sr-only">{t("overview.title")}</SheetDescription>
          <Button variant="text" size="runner-sm" onClick={onClose}>
            {t("overview.close")}
          </Button>
        </SheetHeader>
        <nav aria-label={t("overview.title")} className="px-4 pb-4">
        {sections.map((s) => (
          <section key={s.key} className="py-2">
            <Eyebrow as="h3" className="px-1 py-2">{definitionSections[s.sectionIndex].title as string}</Eyebrow>
            <ul className="divide-y divide-line">
              {s.rows.map((row) => (
                <li key={row.key}>
                  <Button
                    variant="ghost"
                    disabled={!row.navigable}
                    onClick={() => {
                      onNavigate(row.key);
                      onClose();
                    }}
                    aria-current={row.status === "current" ? "step" : undefined}
                    className={cn("flex h-auto w-full items-start justify-start gap-3 whitespace-normal rounded-[var(--p-radius-input)] px-1 py-3 text-left font-body text-base")}
                    data-testid={`overview-${row.key}`}
                  >
                    <span
                      className={cn(
                        "mt-0.5 w-4 text-center",
                        row.status === "answered" && "text-success",
                        row.status === "skipped" && "text-ink-soft",
                        row.status === "current" && "text-primary",
                        (row.status === "unanswered" || row.status === "unreachable") && "text-border",
                      )}
                      aria-hidden
                    >
                      {GLYPH[row.status]}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate">{row.question.text as string}</span>
                      <span className="block truncate text-sm text-ink-soft">
                        {row.status === "skipped" ? t("overview.skipped") : summarize(row.question, answers[row.key], sourceLabels) || t("overview.noAnswer")}
                      </span>
                    </span>
                    <span className="sr-only">{statusLabel[row.status]}</span>
                  </Button>
                </li>
              ))}
            </ul>
          </section>
        ))}
        </nav>
      </SheetContent>
    </Sheet>
  );
}
