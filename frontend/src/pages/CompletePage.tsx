import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router";
import { useResponse, useSurveyDefinition } from "@/api/hooks";
import { useDefinitionLanguage } from "@/i18n/useDefinitionLanguage";
import { storedResponseId } from "@/lib/storage";
import { firstOpenKey } from "@/survey/navigation";
import { Button } from "@/components/ui/button";
import { Decor } from "@/components/Decor";
import { Eyebrow } from "@/components/Eyebrow";
import { useThemeLayout, useThemeLogo } from "@/theme/useTheme";
import { usePageTitle } from "./usePageTitle";

export function CompletePage() {
  const { slug = "" } = useParams();
  const { t } = useTranslation();
  const navigate = useNavigate();
  // The response this page was opened for: storing an update's id must not turn
  // the page into a redirect to that update's first open question.
  const [id] = useState(() => storedResponseId(slug));
  const response = useResponse(id);
  const definition = useSurveyDefinition(slug, { lang: response.data?.language, responseId: id });
  const def = definition.data;
  useDefinitionLanguage(def?.language);
  usePageTitle(def ? t("app.pageTitle", { survey: def.title as string, step: t("complete.title") }) : undefined);
  const layout = useThemeLayout();
  const logo = useThemeLogo(layout.immersiveIntro, "intro");
  const immersive = layout.immersiveIntro;
  const submitted = response.data?.status === "submitted";

  // This page asserts "submitted and read-only", so it only stands for a
  // submitted response. Browser Back after "Start a new response", a bookmark,
  // or no stored id at all lands here too: those go to the resume point (or
  // the intro), mirroring the wizard's redirect effect.
  useEffect(() => {
    if (!id || (response.isError && !response.data)) {
      navigate(`/s/${slug}`, { replace: true });
      return;
    }
    if (!response.data || submitted) return;
    if (def) {
      const key = firstOpenKey(def, response.data.answers, response.data.last_question_key);
      navigate(key ? `/s/${slug}/q/${key}` : `/s/${slug}`, { replace: true });
    } else if (definition.isError) {
      navigate(`/s/${slug}`, { replace: true });
    }
  }, [id, response.isError, response.data, submitted, def, definition.isError, slug, navigate]);

  if (!submitted) return <p className="p-8 text-ink-soft">{t("app.loading")}</p>;

  const text = def?.completion as string | undefined;
  // A profile kept up to date (participation.revisable): updating starts from
  // the intro, on the active version (its consent, if it asks one).
  const revisable = Boolean(def?.participation?.revisable) && !response.data?.administration;
  const update = () => navigate(`/s/${slug}`, { state: { update: true } });
  return (
    <div className={`relative min-h-dvh overflow-hidden ${immersive ? "bg-primary text-on-primary" : "bg-ground text-ink"}`} data-immersive={immersive || undefined} data-testid="complete">
      {immersive && <Decor />}
      <main className="relative mx-auto flex max-w-[var(--p-content-max)] flex-col gap-5 px-6 py-12 sm:py-20">
        <div className={`flex ${layout.logoPlacement === "top-right" ? "justify-end" : "justify-start"}`}>{logo}</div>
        <Eyebrow onPrimary={immersive}>{t("complete.eyebrow")}</Eyebrow>
        <h1 className="text-[2.1rem] leading-[1.1] sm:text-[3rem]">{t("complete.title")}</h1>
        <p className={`text-[1.05rem] ${immersive ? "text-on-primary/85" : "text-ink-soft"}`}>{text ?? t("complete.body")}</p>
        <p className={`text-sm ${immersive ? "text-on-primary/70" : "text-ink-soft"}`}>
          {t(revisable ? "complete.revisable" : "complete.readonly")}
        </p>
        {revisable && (
          <div className="flex flex-wrap gap-3">
            <Button variant={immersive ? "onPrimary" : "primary"} size="runner" onClick={update} data-testid="update">
              {t("intro.update")}
            </Button>
          </div>
        )}
      </main>
    </div>
  );
}
