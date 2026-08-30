import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "./ui/Button";
import { cn } from "@/lib/utils";

export type SaveState = "idle" | "saving" | "saved" | "error";

interface ShellProps {
  sectionLabel: string;
  sectionNumber: number;
  sectionTotal: number;
  progress: number; // 0..1
  showProgress: boolean;
  onOverview?: () => void;
  languages: string[];
  language: string;
  onLanguage: (lang: string) => void;
  children: ReactNode;
  onBack?: () => void;
  onNext: () => void;
  nextLabel: string;
  nextDisabled?: boolean;
  saveState: SaveState;
  onRetry?: () => void;
  footerExtra?: ReactNode;
  logo?: ReactNode;
}

const LANGUAGE_NAMES: Record<string, string> = {
  en: "English",
  es: "Español",
  pt: "Português",
  fr: "Français",
  de: "Deutsch",
  it: "Italiano",
  nl: "Nederlands",
};

export function languageName(code: string): string {
  return LANGUAGE_NAMES[code] ?? code.toUpperCase();
}

export function Shell(p: ShellProps) {
  const { t } = useTranslation();
  return (
    <div className="flex min-h-dvh flex-col bg-ground">
      <header className="sticky top-0 z-10 bg-surface">
        <div className="mx-auto flex max-w-[var(--p-content-max)] items-center gap-3 px-4 py-3">
          <div className="flex items-center gap-3 overflow-hidden" data-logo-slot>
            {p.logo}
            <p className="truncate text-[13px] font-medium uppercase tracking-[0.08em] text-ink-soft">
              {t("header.section", { number: p.sectionNumber, total: p.sectionTotal })}
              {p.sectionLabel ? ` · ${p.sectionLabel}` : ""}
            </p>
          </div>
          <div className="ml-auto flex items-center gap-2">
            {p.languages.length > 1 && (
              <label className="sr-only" htmlFor="language-switch">
                {t("header.language")}
              </label>
            )}
            {p.languages.length > 1 && (
              <select
                id="language-switch"
                value={p.language}
                onChange={(e) => p.onLanguage(e.target.value)}
                className="min-h-[44px] rounded-[var(--p-radius-input)] border border-line bg-surface px-2 text-sm"
              >
                {p.languages.map((l) => (
                  <option key={l} value={l}>
                    {languageName(l)}
                  </option>
                ))}
              </select>
            )}
            {p.onOverview && (
              <Button variant="text" onClick={p.onOverview} className="min-h-[44px] px-3 text-sm">
                {t("header.overview")}
              </Button>
            )}
          </div>
        </div>
        {p.showProgress && (
          <div className="h-1.5 w-full bg-tint" role="progressbar" aria-label={t("header.progress")} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(p.progress * 100)}>
            <div className="h-full bg-accent transition-[width] duration-300 ease-out" style={{ width: `${Math.round(p.progress * 100)}%` }} />
          </div>
        )}
      </header>

      <main className="mx-auto w-full max-w-[var(--p-content-max)] flex-1 px-4 py-6 sm:px-6 sm:py-10">{p.children}</main>

      <footer className="sticky bottom-0 border-t border-line bg-surface shadow-[var(--p-shadow)]">
        {p.footerExtra}
        <div className="mx-auto flex max-w-[var(--p-content-max)] items-center gap-3 px-4 py-3">
          {p.onBack ? (
            <Button variant="text" onClick={p.onBack}>
              {t("nav.back")}
            </Button>
          ) : (
            <span />
          )}
          <p className="flex-1 text-center text-sm text-ink-soft" aria-live="polite">
            {p.saveState === "saving" && t("nav.saving")}
            {p.saveState === "saved" && <span className="text-success">✓ {t("nav.saved")}</span>}
            {p.saveState === "error" && (
              <span className="text-error">
                {t("nav.saveFailed")}{" "}
                {p.onRetry && (
                  <button type="button" onClick={p.onRetry} className="underline">
                    {t("app.retry")}
                  </button>
                )}
              </span>
            )}
          </p>
          <Button onClick={p.onNext} disabled={p.nextDisabled} className={cn("min-w-28")} data-testid="next">
            {p.nextLabel}
          </Button>
        </div>
      </footer>
    </div>
  );
}
