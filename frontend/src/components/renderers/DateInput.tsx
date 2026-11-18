import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { OptionCard } from "../ui/OptionCard";
import { RadioGroup } from "../ui/radio-group";
import { inputClass, type RendererProps } from "./types";
import { cn } from "@/lib/utils";
import { DEFAULT_PRECISION, datePrecision } from "@/survey/answers";
import { questionOptions, type DatePrecision, type DateValue } from "@/survey/types";

interface Parts {
  year: string;
  month: string;
  day: string;
}

const EMPTY: Parts = { year: "", month: "", day: "" };

function split(date: string | undefined): Parts {
  const [year = "", month = "", day = ""] = (date ?? "").split("-");
  return { year, month, day };
}

/** The date the parts spell at an accepted precision, or undefined while they are incomplete. */
export function composeDate(parts: Parts, precision: readonly DatePrecision[]): string | undefined {
  if (!/^\d{4}$/.test(parts.year)) return undefined;
  if (parts.day && !parts.month) return undefined;
  let date = parts.year;
  if (parts.month) date += `-${parts.month.padStart(2, "0")}`;
  if (parts.day) date += `-${parts.day.padStart(2, "0")}`;
  const p = datePrecision(date);
  return p && precision.includes(p) ? date : undefined;
}

function monthNames(language: string): string[] {
  let format: Intl.DateTimeFormat;
  try {
    format = new Intl.DateTimeFormat(language, { month: "long", timeZone: "UTC" });
  } catch {
    format = new Intl.DateTimeFormat("en", { month: "long", timeZone: "UTC" });
  }
  return Array.from({ length: 12 }, (_, i) => format.format(new Date(Date.UTC(2000, i, 1))));
}

/** A stored date as a reader would say it: "June 2019" for a month, the year alone for a year. */
export function displayDate(date: string, language: string): string {
  const [year, month] = date.split("-");
  if (datePrecision(date) !== "month") return date;
  return `${monthNames(language)[Number(month) - 1] ?? month} ${year}`;
}

const fieldClass = cn("h-[52px] w-full border border-input outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50", inputClass);

/**
 * A date at the precisions the definition accepts (config.precision): the
 * browser's date picker for a whole date, separate day, month and year fields
 * when a part may be left out ("the year only"). The question's own options
 * ("not sure", "still ongoing") are answers instead of a date: choosing one
 * clears the fields, and typing a date clears the choice.
 */
export function DateInput({ question, value, onChange, language }: RendererProps<DateValue>) {
  const { t } = useTranslation();
  const cfg = question.config ?? {};
  const precision = cfg.precision ?? DEFAULT_PRECISION;
  const options = questionOptions(question);
  const date = value && "date" in value ? value.date : undefined;
  const option = value && "option" in value ? value.option : undefined;
  const label = question.text as string;
  const whole = precision.length === 1 && precision[0] === "day";
  const [parts, setParts] = useState<Parts>(() => split(date));
  const months = useMemo(() => monthNames(language), [language]);

  const update = (next: Partial<Parts>, commit = false) => {
    const merged = { ...parts, ...next };
    setParts(merged);
    const composed = composeDate(merged, precision);
    onChange(composed ? { date: composed } : undefined, { commit });
  };
  const choose = (key: string) => {
    setParts(EMPTY);
    onChange({ option: key }, { commit: true });
  };
  const id = (part: string) => `date-${question.key}-${part}`;
  const hasDay = precision.includes("day");
  const hasMonth = hasDay || precision.includes("month");
  const dayOptional = precision.includes("month") || precision.includes("year");
  const monthOptional = precision.includes("year");

  return (
    <div className="flex flex-col gap-5">
      {whole ? (
        <Input
          type="date"
          className={inputClass}
          min={cfg.min_date}
          max={cfg.max_date}
          aria-label={label}
          value={date ?? ""}
          onChange={(e) => onChange(e.target.value ? { date: e.target.value } : undefined)}
          onBlur={(e) => onChange(e.target.value ? { date: e.target.value } : undefined, { commit: true })}
          data-testid="date-input"
        />
      ) : (
        <div className="flex flex-wrap gap-3" data-testid="date-parts">
          {hasDay && (
            <div className="flex w-24 flex-col gap-1.5">
              <Label htmlFor={id("day")}>{t(dayOptional ? "date.dayOptional" : "date.day")}</Label>
              <input
                id={id("day")}
                inputMode="numeric"
                maxLength={2}
                autoComplete="off"
                className={fieldClass}
                value={parts.day}
                onChange={(e) => update({ day: e.target.value.replace(/\D/g, "") })}
                onBlur={() => update({}, true)}
                data-testid="date-day"
              />
            </div>
          )}
          {hasMonth && (
            <div className="flex min-w-40 flex-1 flex-col gap-1.5">
              <Label htmlFor={id("month")}>{t(monthOptional ? "date.monthOptional" : "date.month")}</Label>
              <select id={id("month")} className={fieldClass} value={parts.month} onChange={(e) => update({ month: e.target.value }, true)} data-testid="date-month">
                <option value="">{t(monthOptional ? "date.unknown" : "date.choose")}</option>
                {months.map((name, i) => (
                  <option key={name} value={String(i + 1).padStart(2, "0")}>
                    {name}
                  </option>
                ))}
              </select>
            </div>
          )}
          <div className="flex w-32 flex-col gap-1.5">
            <Label htmlFor={id("year")}>{t("date.year")}</Label>
            <input
              id={id("year")}
              inputMode="numeric"
              maxLength={4}
              autoComplete="off"
              placeholder={t("date.yearPlaceholder")}
              className={fieldClass}
              value={parts.year}
              onChange={(e) => update({ year: e.target.value.replace(/\D/g, "") })}
              onBlur={() => update({}, true)}
              data-testid="date-year"
            />
          </div>
        </div>
      )}
      {options.length > 0 && (
        <RadioGroup value={option ?? ""} onValueChange={choose} aria-label={label} className="gap-3">
          {options.map((o) => (
            <OptionCard key={o.key} kind="radio" value={o.key} label={o.label as string} checked={option === o.key} data-testid={`option-${o.key}`} />
          ))}
        </RadioGroup>
      )}
    </div>
  );
}
