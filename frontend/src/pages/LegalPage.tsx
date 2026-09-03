import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router";
import { useLegalPage, useSurveyDefinition } from "@/api/hooks";
import { Decor } from "@/components/Decor";
import { renderMarkdown } from "@/survey/markdown";
import { usePageTitle } from "./usePageTitle";

/**
 * A deployment's legal page, inside the survey rather than off it.
 *
 * Served at /s/<slug>/<page> so it carries that survey's theme and stays on
 * the same origin: a respondent deciding whether to give an email address can
 * open it and come back without losing their place. The content is the
 * deployment's; PROlog ships none.
 */
export function LegalPage({ page }: { page: string }) {
  const { slug = "" } = useParams();
  const { t } = useTranslation();
  const definition = useSurveyDefinition(slug);
  const language = definition.data?.language;
  const legal = useLegalPage(page, language);
  usePageTitle(legal.data ? t(`legal.${page}`, { defaultValue: page }) : undefined);

  return (
    <div className="relative min-h-dvh overflow-hidden bg-ground text-ink">
      <Decor />
      <div className="relative mx-auto max-w-2xl px-6 py-16">
        <Link to={`/s/${slug}`} className="mb-8 inline-block text-sm text-primary underline" data-testid="legal-back">
          {t("legal.back")}
        </Link>
        {legal.isLoading && <p className="text-ink-soft">{t("app.loading")}</p>}
        {legal.isError && (
          <p className="text-error" role="alert" data-testid="legal-missing">
            {t("legal.missing")}
          </p>
        )}
        {legal.data && <article data-testid="legal-body">{renderMarkdown(legal.data.markdown)}</article>}
      </div>
    </div>
  );
}
