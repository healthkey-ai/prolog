import type { ReactNode } from "react";
import { ListIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "./ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";
import { cn } from "@/lib/utils";

export type SaveState = "idle" | "saving" | "saved" | "error" | "closed";

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
        <div className="mx-auto flex max-w-[var(--p-content-max)] items-center gap-2 px-3 py-2 sm:gap-3 sm:px-4 sm:py-3">
          <div className="flex min-w-0 flex-1 items-center gap-2 sm:gap-3">
            {p.logo}
            <div className="min-w-0">
              <p className="text-[12px] font-medium uppercase tracking-[0.08em] text-muted-foreground">
                <span className="sm:hidden">
                  {p.sectionNumber}/{p.sectionTotal}
                </span>
                <span className="hidden sm:inline">{t("header.section", { number: p.sectionNumber, total: p.sectionTotal })}</span>
              </p>
              {p.sectionLabel && <p className="line-clamp-2 text-[0.95rem] leading-tight text-foreground">{p.sectionLabel}</p>}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-1 sm:gap-2">
            {p.languages.length > 1 && (
              <Select value={p.language} onValueChange={p.onLanguage}>
                <SelectTrigger id="language-switch" aria-label={t("header.language")} className="min-h-[44px] bg-card px-2 sm:px-3" data-testid="language-switch">
                  <SelectValue>
                    <span className="sm:hidden">{p.language.toUpperCase()}</span>
                    <span className="hidden sm:inline">{languageName(p.language)}</span>
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {p.languages.map((l) => (
                    <SelectItem key={l} value={l} className="min-h-[44px]" data-testid={`language-${l}`}>
                      {languageName(l)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            {p.onOverview && (
              <Button variant="text" size="runner-sm" onClick={p.onOverview} aria-label={t("header.overview")} className="px-2 sm:px-4">
                <ListIcon className="size-5 sm:hidden" />
                <span className="hidden sm:inline">{t("header.overview")}</span>
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
            {p.saveState === "closed" && <span className="text-error">{t("app.closed")}</span>}
            {p.saveState === "error" && (
              <span className="text-error">
                {t("nav.saveFailed")}{" "}
                {p.onRetry && (
                  <Button variant="link" size="runner-sm" onClick={p.onRetry} className="text-error">
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
