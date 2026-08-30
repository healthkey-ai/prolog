import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams, useSearchParams } from "react-router";
import { ApiError } from "@/api/client";
import { useCreateResponse, useResponse, useSurveyDefinition } from "@/api/hooks";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { OptionCard } from "@/components/ui/OptionCard";
import { RadioGroup } from "@/components/ui/radio-group";
import { Eyebrow } from "@/components/Eyebrow";
import { languageName } from "@/i18n/languageName";
import { storeResponseId, storedResponseId } from "@/lib/storage";
import { firstOpenKey } from "@/survey/navigation";
import { useDefinitionLanguage } from "@/i18n/useDefinitionLanguage";
import { Decor } from "@/components/Decor";
import { useThemeLayout, useThemeLogo } from "@/theme/useTheme";

export function IntroPage() {
  const { slug = "" } = useParams();
  const [search] = useSearchParams();
  const invite = search.get("invite") ?? undefined;
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [language, setLanguage] = useState<string | undefined>(undefined);
  const existingId = storedResponseId(slug);
  const existing = useResponse(existingId);
  const create = useCreateResponse();
  const [agreed, setAgreed] = useState(false);
  const [consentError, setConsentError] = useState(false);
  // "Start a new response" / "Start again": show the start form (with the
  // consent notice) instead of the resume card; the old id is only replaced
  // once the new response exists.
  const [fresh, setFresh] = useState(false);
  // A stored response answers a different administration than the link's (a
  // repeat administration, RUN-5): it is not the one to resume, so this visit
  // starts the response for its own administration instead.
  const otherAdministration = Boolean(invite && existing.data && existing.data.administration !== invite);
  // The stored id no longer resolves: purged response, or an expired account session.
  const existingGone = existing.error instanceof ApiError && (existing.error.status === 404 || existing.error.status === 403);
  // Response-bound, like ThemeProvider and the wizard: the server serves the
  // version this response uses and takes its id as the credential, so a
  // returning invited/account participant without the token is not refused
  // here, the resume point is computed against the right version, and the
  // cache entry is shared. Falls back to the plain query for a fresh start.
  const bound = existingId && !existing.isError && !fresh && !otherAdministration ? existingId : undefined;
  const definition = useSurveyDefinition(slug, language ?? (bound ? existing.data?.language : undefined), invite, bound, { enabled: !existingId || !existing.isPending });
  const layout = useThemeLayout();
  const logo = useThemeLogo(layout.immersiveIntro);
  useDefinitionLanguage(definition.data?.language);

  if (definition.isLoading) return <p className="p-8 text-ink-soft">{t("app.loading")}</p>;
  if (definition.isError || !definition.data) {
    const status = definition.error instanceof ApiError ? definition.error.status : 0;
    return <p className="p-8 text-error">{status === 404 ? t("app.notFound") : status === 410 ? t("app.closed") : t("app.error")}</p>;
  }
  const def = definition.data;
  const consent = def.consent;
  const consentRequired = Boolean(consent && (consent.required ?? true));
  // "none": no resume on a later visit (shared devices); the id lives only in this tab.
  const resumable = def.participation?.resume !== "none";
  // An anonymous survey takes no invitation (linking would join an address to the
  // answers); a stray or stale ?invite= on its link is ignored, as the server does on GET.
  const invitation = invite && !def.participation?.anonymous ? invite : undefined;
  // "Start again" can only discard when the server would create a fresh response:
  // an invitation link and an account survey both resume the same response instead.
  const canStartAgain = !invite && def.participation?.resume !== "account";
  // A stored response still loading must not show the start form: Start would
  // replace the stored id without the "start again" confirmation.
  if (resumable && existingId && existing.isPending) return <p className="p-8 text-ink-soft">{t("app.loading")}</p>;
  // A stored response that failed to load for any reason other than being gone
  // (network, throttle, outage) must not show the start form either: Start would
  // create a new response and replace the stored id, orphaning the unfinished one.
  if (resumable && existingId && existing.isError && !existingGone && !fresh) {
    return (
      <p className="p-8 text-error" role="alert">
        {t("app.error")}
      </p>
    );
  }

  const start = async () => {
    if (consentRequired && !agreed) {
      setConsentError(true);
      return;
    }
    let response;
    try {
      response = await create.mutateAsync({
        slug,
        // The chosen language, not `def.language`: after a switch `def` is the
        // previous localisation (keepPreviousData) until the new one arrives.
        language: language ?? def.language,
        consent: consent && agreed ? { version: consent.version, agreed: true } : undefined,
        invitation,
      });
    } catch {
      return; // create.isError renders the message
    }
    storeResponseId(slug, response.id, resumable);
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
    // The stored id is replaced only once the new response exists (storeResponseId
    // in start): clearing it first would orphan the unfinished response should
    // the create fail. Consent surveys show the start form with the notice first.
    if (consentRequired) setFresh(true);
    else void start();
  };

  const immersive = layout.immersiveIntro;
  const ground = immersive ? "bg-primary text-on-primary" : "bg-ground text-ink";
  const soft = immersive ? "text-on-primary/80" : "text-ink-soft";
  const hasExisting = resumable && existingId && existing.data && !existing.isError && !fresh && !otherAdministration;

  return (
    <div className={`relative min-h-dvh overflow-hidden ${ground}`} data-immersive={immersive || undefined}>
      {immersive && <Decor />}
      <main className="relative mx-auto flex max-w-[var(--p-content-max)] flex-col gap-6 px-6 py-12 sm:py-20">
        <div className={`flex ${layout.logoPlacement === "top-right" ? "justify-end" : "justify-start"}`}>{logo}</div>
        <Eyebrow onPrimary={immersive}>{t("intro.eyebrow")}</Eyebrow>
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
              <Button variant="primary" size="runner" onClick={resume} data-testid="resume">
                {t("intro.continue")}
              </Button>
              {existing.data!.status !== "submitted" ? (
                canStartAgain && (
                  <Button variant="text" size="runner" onClick={startAgain} data-testid="start-again">
                    {t("intro.startAgain")}
                  </Button>
                )
              ) : invite ? null : ( // an invitation is answered once; the server would return the same response
                <Button
                  variant="text"
                  size="runner"
                  onClick={() => {
                    if (consentRequired) setFresh(true);
                    else void start();
                  }}
                  data-testid="start-new"
                >
                  {t("intro.startNew")}
                </Button>
              )}
            </div>
          </div>
        ) : (
          <>
            {def.languages.length > 1 && (
              <fieldset className="border-0 p-0">
                <legend className={`mb-3 text-sm ${soft}`}>{t("intro.language")}</legend>
                <RadioGroup value={def.language} onValueChange={(l) => setLanguage(l)} aria-label={t("intro.language")} className="grid gap-3 sm:grid-cols-3">
                  {def.languages.map((l) => (
                    <OptionCard key={l} kind="radio" value={l} label={languageName(l)} checked={def.language === l} className="text-foreground" data-testid={`lang-${l}`} />
                  ))}
                </RadioGroup>
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
                <div className="mt-2 flex min-h-[44px] items-center gap-3">
                  <Checkbox id="consent" className="size-5" checked={agreed} onCheckedChange={(c) => { setAgreed(c === true); setConsentError(false); }} data-testid="consent" />
                  <Label htmlFor="consent" className="flex min-h-[44px] items-center font-normal leading-snug">{t("intro.consentAgree")}</Label>
                </div>
                {consentError && (
                  <p className="mt-2 text-sm text-error" role="alert">
                    {t("intro.consentRequired")}
                  </p>
                )}
              </div>
            )}
            <div>
              <Button variant={immersive ? "onPrimary" : "primary"} size="runner" onClick={start} disabled={create.isPending || definition.isPlaceholderData} className="px-8" data-testid="start">
                {t("intro.start")}
              </Button>
              {create.isError && (
                <p className="mt-2 text-sm" role="alert">
                  {create.error instanceof ApiError && create.error.status === 410 ? t("app.closed") : t("app.error")}
                </p>
              )}
            </div>
          </>
        )}
      </main>
    </div>
  );
}
