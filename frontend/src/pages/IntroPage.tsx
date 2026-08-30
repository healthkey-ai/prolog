import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams, useSearchParams } from "react-router";
import { ApiError } from "@/api/client";
import { useCreateResponse, useResponse, useSurveyDefinition } from "@/api/hooks";
import { Button } from "@/components/ui/Button";
import { OptionCard } from "@/components/ui/OptionCard";
import { languageName } from "@/components/Shell";
import { clearResponseId, storeResponseId, storedResponseId } from "@/lib/storage";
import { firstOpenKey } from "@/survey/navigation";
import i18n from "@/i18n";
import { Decor } from "@/components/Decor";
import { useThemeLayout, useThemeLogo } from "@/theme/useTheme";

export function IntroPage() {
  const { slug = "" } = useParams();
  const [search] = useSearchParams();
  const invite = search.get("invite") ?? undefined;
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [language, setLanguage] = useState<string | undefined>(undefined);
  const definition = useSurveyDefinition(slug, language, invite);
  const existingId = storedResponseId(slug);
  const existing = useResponse(existingId);
  const create = useCreateResponse();
  const [agreed, setAgreed] = useState(false);
  const [consentError, setConsentError] = useState(false);
  const layout = useThemeLayout();
  const logo = useThemeLogo(layout.immersiveIntro);

  useEffect(() => {
    if (definition.data) void i18n.changeLanguage(definition.data.language);
  }, [definition.data]);
  useEffect(() => {
    if (definition.data) document.documentElement.lang = definition.data.language;
  }, [definition.data]);

  if (definition.isLoading) return <p className="p-8 text-ink-soft">{t("app.loading")}</p>;
  if (definition.isError || !definition.data) {
    const status = definition.error instanceof ApiError ? definition.error.status : 0;
    return <p className="p-8 text-error">{status === 404 ? t("app.notFound") : t("app.error")}</p>;
  }
  const def = definition.data;
  const consent = def.consent;
  const consentRequired = Boolean(consent && (consent.required ?? true));

  const start = async () => {
    if (consentRequired && !agreed) {
      setConsentError(true);
      return;
    }
    const response = await create.mutateAsync({
      slug,
      language: def.language,
      consent: consent ? { version: consent.version, agreed } : undefined,
      invitation: invite,
    });
    storeResponseId(slug, response.id);
    const key = firstOpenKey(def, response.answers, response.last_question_key);
    navigate(`/s/${slug}/q/${key}`);
  };

  const resume = () => {
    const r = existing.data!;
    if (r.status === "submitted") {
      navigate(`/s/${slug}/complete`);
      return;
    }
    navigate(`/s/${slug}/q/${firstOpenKey(def, r.answers, r.last_question_key)}`);
  };

  const startAgain = () => {
    if (!window.confirm(t("intro.startAgainConfirm"))) return;
    clearResponseId(slug);
    void start();
  };

  const immersive = layout.immersiveIntro;
  const ground = immersive ? "bg-primary text-on-primary" : "bg-ground text-ink";
  const soft = immersive ? "text-on-primary/80" : "text-ink-soft";
  const hasExisting = existingId && existing.data && !existing.isError;

  return (
    <div className={`relative min-h-dvh overflow-hidden ${ground}`} data-immersive={immersive || undefined}>
      {immersive && <Decor />}
      <main className="relative mx-auto flex max-w-[var(--p-content-max)] flex-col gap-6 px-6 py-12 sm:py-20">
        <div className={`flex ${layout.logoPlacement === "top-right" ? "justify-end" : "justify-start"}`}>{logo}</div>
        <p className={`text-[13px] font-medium uppercase tracking-[0.08em] ${immersive ? "text-on-primary/80" : "text-ink-soft"}`}>{t("intro.eyebrow")}</p>
        <h1 className="text-[2.1rem] leading-[1.1] sm:text-[3rem]">{def.title as string}</h1>
        {def.intro && <p className={`text-[1.05rem] ${soft}`}>{def.intro as string}</p>}
        <div className="flex flex-wrap gap-2">
          {def.estimated_minutes && <span className={`rounded-full border px-3 py-1 text-sm ${immersive ? "border-on-primary/40" : "border-line bg-surface"}`}>{t("intro.minutes", { count: def.estimated_minutes })}</span>}
          {def.participation?.anonymous && <span className={`rounded-full border px-3 py-1 text-sm ${immersive ? "border-on-primary/40" : "border-line bg-surface"}`}>{t("intro.anonymous")}</span>}
        </div>

        {hasExisting ? (
          <div className="rounded-[var(--p-radius-card)] bg-surface p-5 text-ink shadow-[var(--p-shadow)]" data-testid="resume-card">
            <h2 className="text-lg">{t("intro.welcomeBack")}</h2>
            <p className="mt-1 text-ink-soft">{existing.data!.status === "submitted" ? t("intro.submitted") : t("intro.resumeHint")}</p>
            <div className="mt-4 flex flex-wrap gap-3">
              <Button onClick={resume} data-testid="resume">
                {t("intro.continue")}
              </Button>
              {existing.data!.status !== "submitted" && (
                <Button variant="text" onClick={startAgain} data-testid="start-again">
                  {t("intro.startAgain")}
                </Button>
              )}
            </div>
          </div>
        ) : (
          <>
            {def.languages.length > 1 && (
              <fieldset className="border-0 p-0">
                <legend className={`mb-3 text-sm ${soft}`}>{t("intro.language")}</legend>
                <div className="grid gap-3 sm:grid-cols-3">
                  {def.languages.map((l) => (
                    <OptionCard key={l} kind="radio" name="language" value={l} label={languageName(l)} checked={def.language === l} onChange={() => setLanguage(l)} className="text-ink" data-testid={`lang-${l}`} />
                  ))}
                </div>
              </fieldset>
            )}
            {consent && (
              <div className="rounded-[var(--p-radius-card)] bg-surface p-5 text-ink">
                <p className="text-[0.95rem]">{consent.text as string}</p>
                {consent.privacy_url && (
                  <a href={consent.privacy_url} className="mt-2 inline-block text-sm text-primary underline" target="_blank" rel="noreferrer">
                    {consent.privacy_url}
                  </a>
                )}
                <label className="mt-4 flex items-start gap-3">
                  <input type="checkbox" className="mt-1 size-5 accent-primary" checked={agreed} onChange={(e) => { setAgreed(e.target.checked); setConsentError(false); }} data-testid="consent" />
                  <span>{t("intro.consentAgree")}</span>
                </label>
                {consentError && (
                  <p className="mt-2 text-sm text-error" role="alert">
                    {t("intro.consentRequired")}
                  </p>
                )}
              </div>
            )}
            <div>
              <Button variant={immersive ? "onPrimary" : "primary"} onClick={start} disabled={create.isPending} className="px-8" data-testid="start">
                {t("intro.start")}
              </Button>
              {create.isError && (
                <p className="mt-2 text-sm" role="alert">
                  {t("app.error")}
                </p>
              )}
            </div>
          </>
        )}
      </main>
    </div>
  );
}
