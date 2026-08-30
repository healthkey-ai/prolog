import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "./ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";
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
          <div className="flex items-center gap-3 overflow-hidden">
            {p.logo}
            <p className="truncate text-[13px] font-medium uppercase tracking-[0.08em] text-ink-soft">
              {t("header.section", { number: p.sectionNumber, total: p.sectionTotal })}
              {p.sectionLabel ? ` · ${p.sectionLabel}` : ""}
            </p>
          </div>
          <div className="ml-auto flex items-center gap-2">
            {p.languages.length > 1 && (
              <Select value={p.language} onValueChange={p.onLanguage}>
                <SelectTrigger id="language-switch" aria-label={t("header.language")} className="min-h-[44px] bg-card" data-testid="language-switch">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {p.languages.map((l) => (
                    <SelectItem key={l} value={l} data-testid={`language-${l}`}>
                      {languageName(l)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            {p.onOverview && (
              <Button variant="text" size="runner-sm" onClick={p.onOverview}>
                {t("header.overview")}
              </Button>
            )}
          </div>
        </div>
        {p.showProgress && (
          <div className="h-1.5 w-full bg-tint" role="progressbar" aria-label={t("header.progress")} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(p.progress * 100)}>
            <div className="h-full bg-brand-accent transition-[width] duration-300 ease-out" style={{ width: `${Math.round(p.progress * 100)}%` }} />
          </div>
        )}
      </header>

      <main className="mx-auto w-full max-w-[var(--p-content-max)] flex-1 px-4 py-6 sm:px-6 sm:py-10">{p.children}</main>

      <footer className="sticky bottom-0 border-t border-line bg-surface shadow-[var(--p-shadow)]">
        {p.footerExtra}
        <div className="mx-auto flex max-w-[var(--p-content-max)] items-center gap-3 px-4 py-3">
          {p.onBack ? (
            <Button variant="text" size="runner" onClick={p.onBack}>
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
                  <Button variant="link" size="xs" onClick={p.onRetry} className="text-error">
                    {t("app.retry")}
                  </Button>
                )}
              </span>
            )}
          </p>
          <Button variant="primary" size="runner" onClick={p.onNext} disabled={p.nextDisabled} className={cn("min-w-28")} data-testid="next">
            {p.nextLabel}
          </Button>
        </div>
      </footer>
    </div>
  );
}
