import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router";
import { accountStatus, useParticipantStatus, useResponse, useSurveyDefinition } from "@/api/hooks";
import { useDefinitionLanguage } from "@/i18n/useDefinitionLanguage";
import { storedResponseId } from "@/lib/storage";
import { firstOpenKey } from "@/survey/navigation";
import { Button } from "@/components/ui/button";
import { Decor } from "@/components/Decor";
import { Eyebrow } from "@/components/Eyebrow";
import { useThemeExit, useThemeLayout, useThemeLogo } from "@/theme/useTheme";
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
  // Whether this can be updated is the active version's to say, not the
  // version this response answered (see IntroPage).
  const status = useParticipantStatus(slug);
  const known = accountStatus(status);
  const def = definition.data;
  useDefinitionLanguage(def?.language);
  usePageTitle(def ? t("app.pageTitle", { survey: def.title as string, step: t("complete.title") }) : undefined);
  const layout = useThemeLayout();
  const logo = useThemeLogo(layout.immersiveIntro, "intro");
  const immersive = layout.immersiveIntro;
  const submitted = response.data?.status === "submitted";
  const exit = useThemeExit();

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

  if (!submitted || status.isPending) return <p className="p-8 text-ink-soft">{t("app.loading")}</p>;

  const text = def?.completion as string | undefined;
  // A profile kept up to date (participation.revisable): updating starts from
  // the intro, on the active version (its consent, if it asks one).
  // An update starts from the last submission, so only that one offers it.
  const revisable = known
    ? known.revisable && known.last_submitted === id
    : Boolean(def?.participation?.revisable) && !response.data?.administration;
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
        {(exit || revisable) && (
          <div className="flex flex-wrap gap-3">
            {exit && (
              <Button asChild variant={immersive ? "onPrimary" : "primary"} size="runner">
                <a href={exit} data-testid="exit">
                  {t("complete.exit")}
                </a>
              </Button>
            )}
            {revisable && (
              // Beside "Back to home" it is the second choice, not a second primary.
              <Button variant={immersive ? "onPrimary" : exit ? "surface" : "primary"} size="runner" onClick={update} data-testid="update">
                {t("intro.update")}
              </Button>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
