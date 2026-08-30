import { useTranslation } from "react-i18next";

export function SectionInterstitial({ number, title, description }: { number: number; title: string; description?: string }) {
  const { t } = useTranslation();
  return (
    <div className="rounded-[var(--p-radius-card)] border border-line bg-surface p-6 sm:p-8" data-testid="interstitial">
      <p className="text-[13px] font-medium uppercase tracking-[0.08em] text-ink-soft">{t("interstitial.eyebrow", { number })}</p>
      <h1 className="mt-2 text-2xl">{title}</h1>
      {description && <p className="mt-3 text-ink-soft">{description}</p>}
    </div>
  );
}
