import { useEffect, useId, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Eyebrow } from "./Eyebrow";

/**
 * The card shown on entering a new section. It is a step change like a
 * question is, so focus moves to its heading when it appears (or changes
 * section) — the screen reader announces the title as it does a question's —
 * and the card is a labelled region for AT navigation.
 */
export function SectionInterstitial({ number, title, description }: { number: number; title: string; description?: string }) {
  const { t } = useTranslation();
  const heading = useRef<HTMLHeadingElement>(null);
  const headingId = useId();
  useEffect(() => {
    heading.current?.focus();
  }, [number, title]);
  return (
    <section className="rounded-[var(--p-radius-card)] border border-line bg-surface p-6 sm:p-8" aria-labelledby={headingId} data-testid="interstitial">
      {/* Decorative accent in the theme's secondary colour (never used for text). */}
      <span className="mb-4 block h-1.5 w-12 rounded-full bg-brand-secondary" aria-hidden />
      <Eyebrow>{t("interstitial.eyebrow", { number })}</Eyebrow>
      <h1 ref={heading} id={headingId} tabIndex={-1} className="mt-2 text-2xl outline-none">
        {title}
      </h1>
      {description && <p className="mt-3 text-ink-soft">{description}</p>}
    </section>
  );
}
