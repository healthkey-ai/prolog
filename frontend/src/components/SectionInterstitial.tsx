import { useTranslation } from "react-i18next";
import { Eyebrow } from "./Eyebrow";

export function SectionInterstitial({ number, title, description }: { number: number; title: string; description?: string }) {
  const { t } = useTranslation();
  return (
    <div className="rounded-[var(--p-radius-card)] border border-line bg-surface p-6 sm:p-8" data-testid="interstitial">
      <Eyebrow>{t("interstitial.eyebrow", { number })}</Eyebrow>
      <h1 className="mt-2 text-2xl">{title}</h1>
      {description && <p className="mt-3 text-ink-soft">{description}</p>}
    </div>
  );
}
