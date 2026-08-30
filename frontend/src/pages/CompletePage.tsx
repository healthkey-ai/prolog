import { useTranslation } from "react-i18next";
import { useParams } from "react-router";
import { useResponse, useSurveyDefinition } from "@/api/hooks";
import { storedResponseId } from "@/lib/storage";
import { useThemeLayout } from "@/theme/useTheme";

export function CompletePage() {
  const { slug = "" } = useParams();
  const { t } = useTranslation();
  const id = storedResponseId(slug);
  const response = useResponse(id);
  const definition = useSurveyDefinition(slug, response.data?.language);
  const layout = useThemeLayout();
  const immersive = layout.immersiveIntro;
  const text = definition.data?.completion as string | undefined;
  return (
    <div className={`relative min-h-dvh overflow-hidden ${immersive ? "bg-primary text-on-primary" : "bg-ground text-ink"}`} data-immersive={immersive || undefined} data-testid="complete">
      {immersive && <div className="pointer-events-none absolute inset-0" aria-hidden data-decor-slot />}
      <main className="relative mx-auto flex max-w-[var(--p-content-max)] flex-col gap-5 px-6 py-12 sm:py-20">
        <div data-logo-slot />
        <p className={`text-[13px] font-medium uppercase tracking-[0.08em] ${immersive ? "text-on-primary/80" : "text-ink-soft"}`}>{t("complete.eyebrow")}</p>
        <h1 className="text-[2.1rem] leading-[1.1] sm:text-[3rem]">{t("complete.title")}</h1>
        <p className={`text-[1.05rem] ${immersive ? "text-on-primary/85" : "text-ink-soft"}`}>{text ?? t("complete.body")}</p>
        <p className={`text-sm ${immersive ? "text-on-primary/70" : "text-ink-soft"}`}>{t("complete.readonly")}</p>
      </main>
    </div>
  );
}
