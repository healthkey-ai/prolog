import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router";
import { ApiError, isClosed, isGone } from "@/api/client";
import {
  SupersededError,
  useCreateResponse,
  usePatchResponse,
  useResponse,
  useSurveyDefinition,
} from "@/api/hooks";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { OptionCard } from "@/components/ui/OptionCard";
import { RadioGroup } from "@/components/ui/radio-group";
import { Eyebrow } from "@/components/Eyebrow";
import { LanguageSwitch } from "@/components/LanguageSwitch";
import { languageName } from "@/i18n/languageName";
import { renderInline } from "@/survey/markdown";
import { forget, recall, remember } from "@/survey/scratch";
import { storeResponseId, storedResponseId } from "@/lib/storage";
import { firstOpenKey } from "@/survey/navigation";
import { needsLanguageStep } from "@/survey/languageStep";
import { useDefinitionLanguage } from "@/i18n/useDefinitionLanguage";
import { Decor } from "@/components/Decor";
import { DefinitionError } from "@/components/DefinitionError";
import { useThemeLayout, useThemeLogo } from "@/theme/useTheme";
import { httpUrl } from "./httpUrl";
import { usePageTitle } from "./usePageTitle";

export function IntroPage() {
  const { slug = "" } = useParams();
  const location = useLocation();
  const [search] = useSearchParams();
  const invite = search.get("invite") ?? undefined;
  // A link may name the language, which answers the question before it is asked.
  const requestedLanguage = search.get("lang") ?? undefined;
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [language, setLanguage] = useState<string | undefined>(undefined);
  const existingId = storedResponseId(slug);
  const existing = useResponse(existingId);
  const create = useCreateResponse();
  const patch = usePatchResponse(existingId ?? "");
  // The tick survives a detour to the notice (memory only; see scratch.ts).
  const [agreed, setAgreedState] = useState(() => recall<boolean>(`consent:${slug}`) ?? false);
  const setAgreed = (on: boolean) => {
    setAgreedState(on);
    remember(`consent:${slug}`, on);
  };
  const [consentError, setConsentError] = useState(false);
  // "Start a new response" / "Start again": show the start form (with the
  // consent notice) instead of the resume card; the old id is only replaced
  // once the new response exists.
  const [fresh, setFresh] = useState(false);
  // Discarding an unfinished response is destructive, so it is confirmed in an
  // alert dialog (focus-trapped, themed) rather than a browser confirm box.
  const [confirmingStartAgain, setConfirmingStartAgain] = useState(false);
  // A stored response answers a different administration than the link's (a
  // repeat administration, RUN-5): it is not the one to resume, so this visit
  // starts the response for its own administration instead.
  const otherAdministration = Boolean(
    invite && existing.data && existing.data.administration !== invite,
  );
  // The stored id no longer resolves: purged response, or an expired account session.
  const existingGone = isGone(existing.error);
  // Whether a stored response is resumed at all is only known from the
  // definition; until it says otherwise a stored id is taken as resumable (the
  // common case). A `resume: "none"` survey then unbinds, so the id of an
  // earlier same-tab response never pins the intro to that response's version.
  const [noResume, setNoResume] = useState(false);
  // The respondent has picked on the language step (or there was none to pick).
  const [languageSettled, setLanguageSettled] = useState(false);
  // Response-bound, like ThemeProvider and the wizard: the server serves the
  // version this response uses and takes its id as the credential, so a
  // returning invited/account participant without the token is not refused
  // here, the resume point is computed against the right version, and the
  // cache entry is shared. Falls back to the plain query for a fresh start.
  const bound =
    existingId &&
    !noResume &&
    !existing.isError &&
    !fresh &&
    !otherAdministration
      ? existingId
      : undefined;
  const definition = useSurveyDefinition(slug, {
    lang:
      language ??
      requestedLanguage ??
      (bound ? existing.data?.language : undefined),
    invite,
    responseId: bound,
    enabled: !existingId || !existing.isPending,
  });
  const layout = useThemeLayout();
  const logo = useThemeLogo(layout.immersiveIntro, "intro");
  // A top-right logo floats above the column rather than sitting in the top
  // row: the row is then only as tall as the language control, and the title
  // moves up beside the mark — the intro fits a screen it otherwise would
  // not. The control keeps clear of the mark by the mark's measured width,
  // and sits level with its middle — shifted, not spaced, so the row stays
  // as short as the control and the words keep the room they gained.
  const floatingLogo = layout.logoPlacement === "top-right" && logo !== null;
  const logoBox = useRef<HTMLDivElement>(null);
  const topRow = useRef<HTMLDivElement>(null);
  const [fit, setFit] = useState({ width: 0, shift: 0 });
  useEffect(() => {
    const el = logoBox.current;
    const row = topRow.current;
    if (!el || !row || typeof ResizeObserver === "undefined") return;
    // offsetTop is layout position, untouched by the row's own transform.
    const measure = () =>
      setFit({
        width: el.offsetWidth,
        shift: el.offsetTop + el.offsetHeight / 2 - (row.offsetTop + row.offsetHeight / 2),
      });
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    observer.observe(row);
    return () => observer.disconnect();
  }, [floatingLogo]);
  useDefinitionLanguage(definition.data?.language);
  usePageTitle(definition.data?.title as string | undefined);
  useEffect(() => {
    if (definition.data)
      setNoResume(definition.data.participation?.resume === "none");
  }, [definition.data]);

  if (definition.isLoading)
    return <p className="p-8 text-ink-soft">{t("app.loading")}</p>;
  if (definition.isError || !definition.data) {
    return (
      <DefinitionError
        error={definition.error}
        onRetry={() => void definition.refetch()}
        retrying={definition.isFetching}
      />
    );
  }
  const def = definition.data;
  const consent = def.consent;
  const consentRequired = Boolean(consent && (consent.required ?? true));
  // "none": no resume on a later visit (shared devices); the id lives only in this tab.
  const resumable = def.participation?.resume !== "none";
  // An anonymous survey takes no invitation (linking would join an address to the
  // answers); a stray or stale ?invite= on its link is ignored, as the server does on GET.
  const invitation =
    invite && !def.participation?.anonymous ? invite : undefined;
  // "Start again" can only discard when the server would create a fresh response:
  // an invitation link and an account survey both resume the same response instead.
  const canStartAgain = !invite && def.participation?.resume !== "account";
  // A stored response still loading must not show the start form: Start would
  // replace the stored id without the "start again" confirmation.
  if (resumable && existingId && existing.isPending)
    return <p className="p-8 text-ink-soft">{t("app.loading")}</p>;
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
        consent:
          consent && agreed
            ? { version: consent.version, agreed: true }
            : undefined,
        invitation,
      });
    } catch {
      return; // create.isError renders the message (below both the resume card and the start form)
    }
    storeResponseId(slug, response.id, resumable);
    forget(`consent:${slug}`);
    const key = firstOpenKey(def, response.answers, response.last_question_key);
    navigate(`/s/${slug}/q/${key}`);
  };

  const resume = () => {
    const r = existing.data!;
    if (r.status === "submitted") {
      navigate(`/s/${slug}/complete`);
      return;
    }
    navigate(
      `/s/${slug}/q/${firstOpenKey(def, r.answers, r.last_question_key)}`,
    );
  };

  const startAgain = () => {
    setConfirmingStartAgain(false);
    // The stored id is replaced only once the new response exists (storeResponseId
    // in start): clearing it first would orphan the unfinished response should
    // the create fail. Consent surveys show the start form with the notice first.
    if (consentRequired) setFresh(true);
    else void start();
  };

  const immersive = layout.immersiveIntro;
  const ground = immersive
    ? "bg-primary text-on-primary"
    : "bg-ground text-ink";
  const soft = immersive ? "text-on-primary/80" : "text-ink-soft";
  const hasExisting = resumable && Boolean(bound && existing.data);
  // Ask for the language before the intro, where the definition says to: the
  // intro and the consent notice are what has to be understood before agreeing
  // to anything, so a survey launched in several languages may not want them
  // read in whichever one the browser guessed. A resumed response already has
  // a language and is never asked again.
  const askLanguageFirst =
    !hasExisting &&
    !languageSettled &&
    needsLanguageStep({
      languages: def.languages,
      mode: def.presentation?.language_step,
      preferred:
        typeof navigator === "undefined" ? [] : [...navigator.languages],
      requested: requestedLanguage,
    });
  // Only an absolute http(s) URL becomes a link; anything else in the definition is not rendered.
  const privacyUrl = httpUrl(consent?.privacy_url);
  // A notice this deployment serves itself, on this origin and under this
  // theme: preferred over an off-site link, because the respondent is deciding
  // whether to trust the survey and should not have to leave it to find out.
  const hasLocalPrivacy = def.legal_pages?.includes("privacy") ?? false;
  // The language being read is machine-translated and the deployment has
  // declared it will serve it that way (PROLOG_MACHINE_LANGUAGES). Saying so
  // is the condition on serving it: a respondent judging a clinical question
  // deserves to know a machine wrote the words, and which language a person
  // did write. The server decides — a version merely previewed for review
  // (--allow-unreviewed) says nothing, as documented.
  const machineTranslated = Boolean(def.machine_notice);

  if (askLanguageFirst) {
    return (
      <div
        className={`relative min-h-dvh overflow-hidden ${ground}`}
        data-immersive={immersive || undefined}
      >
        <Decor />
        <div className="relative mx-auto flex min-h-dvh max-w-2xl flex-col justify-center gap-[clamp(0.65rem,2vh,1.25rem)] px-6 py-[clamp(0.75rem,3vh,2.25rem)]">
          <div
            className={`flex ${layout.logoPlacement === "top-right" ? "justify-end" : "justify-start"}`}
          >
            {logo}
          </div>
          {/* Each language names itself. Translating "Spanish" into the language
              a respondent cannot read is how a picker fails the people who need it. */}
          <h1 className="text-[2.1rem] leading-[1.1]">{t("intro.language")}</h1>
          <RadioGroup
            value={def.language}
            onValueChange={(l) => {
              setLanguage(l);
              setLanguageSettled(true);
            }}
            aria-label={t("intro.language")}
            className="grid gap-3 sm:grid-cols-2"
            data-testid="language-step"
          >
            {def.languages.map((l) => (
              <OptionCard
                key={l}
                kind="radio"
                value={l}
                label={languageName(l)}
                checked={false}
                className="text-foreground"
                data-testid={`lang-first-${l}`}
              />
            ))}
          </RadioGroup>
        </div>
      </div>
    );
  }

  return (
    <div
      className={`relative min-h-dvh overflow-hidden ${ground}`}
      data-immersive={immersive || undefined}
    >
      {immersive && <Decor />}
      {/* Spacing scales with the viewport's height rather than stepping at a
          width breakpoint, because what makes this page scroll is short
          screens, not narrow ones. Below 800px of height — a phone, or a 768px laptop — the
          type tightens a step as well (title, paragraph leading, padding),
          which is what gets a ten-line intro and its Start button onto one
          iPhone-13 screen. A 568px screen (iPhone SE) still scrolls: the
          content is genuinely taller than that, and the floors keep it
          readable rather than squeezing it to fit. */}
      <main className="relative mx-auto flex min-h-dvh max-w-[var(--p-content-max)] flex-col gap-[clamp(0.65rem,2vh,1.25rem)] px-6 py-[clamp(0.75rem,3vh,2.25rem)] [@media(max-height:800px)]:gap-[clamp(0.5rem,1.6vh,1rem)] [@media(max-height:800px)]:py-[clamp(0.5rem,2vh,1.5rem)]">
        {/* The same control as the wizard header, in the same place: top row,
            for a first visit and a return alike. For a returning respondent
            with an unfinished response the choice is also the response's
            language, so it is written there — the wizard reads it from there —
            and snaps back if that write fails, so the screen never shows a
            language the survey would not continue in. A submitted response is
            not written to (the server would refuse, and there is nothing to
            continue): the choice stays on this screen. */}
        {floatingLogo && (
          <div
            ref={logoBox}
            className="absolute right-6 top-[clamp(0.4rem,1.5vh,1.1rem)] [@media(max-height:800px)]:top-[clamp(0.3rem,1vh,0.75rem)]"
            data-testid="intro-logo"
          >
            {logo}
          </div>
        )}
        <div
          ref={topRow}
          className={`flex items-center gap-3 ${layout.logoPlacement === "top-right" ? "justify-end" : "justify-between"}`}
          style={
            floatingLogo
              ? { paddingRight: fit.width ? fit.width + 12 : undefined, transform: fit.shift ? `translateY(${fit.shift}px)` : undefined }
              : undefined
          }
        >
          {layout.logoPlacement !== "top-right" && logo}
          {def.presentation?.language_step !== "first" && (
            <LanguageSwitch
              languages={def.languages}
              language={def.language}
              onPrimary={immersive}
              onLanguage={(l) => {
                setLanguage(l);
                if (hasExisting && bound && existing.data?.status !== "submitted")
                  patch.mutate(
                    { language: l },
                    {
                      onError: (e) => {
                        // A later switch overtook this one: its choice stands.
                        if (e instanceof SupersededError) return;
                        // Refused because the response can no longer be
                        // written (submitted meanwhile, survey closed): the
                        // screen can still be read in the chosen language.
                        if (e instanceof ApiError && (e.status === 409 || e.status === 410)) return;
                        setLanguage(undefined);
                      },
                    },
                  );
              }}
            />
          )}
        </div>
        {/* Auto margins, not justify-center: they centre the block when there is
            room and resolve to nothing when there is not, so a tall intro on a
            short screen starts at the top and scrolls rather than losing its
            first lines above the fold. */}
        <div
          className="my-auto flex flex-col gap-[inherit]"
          data-testid="intro-body"
        >
          <Eyebrow onPrimary={immersive}>{t("intro.eyebrow")}</Eyebrow>
          <h1 className="text-[2.1rem] leading-[1.1] sm:text-[3rem] [@media(max-height:800px)]:text-[1.85rem] [@media(max-height:800px)]:sm:text-[2.6rem]">
            {def.title as string}
          </h1>
          {def.intro && (
            <p
              className={`text-[1.05rem] [@media(max-height:800px)]:text-[1rem] [@media(max-height:800px)]:leading-[1.45] ${soft}`}
            >
              {def.intro as string}
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            {def.estimated_minutes && (
              <span
                className={`rounded-full border px-3 py-1 text-sm ${immersive ? "border-on-primary/40" : "border-line bg-surface"}`}
              >
                {t("intro.minutes", { count: def.estimated_minutes })}
              </span>
            )}
            {def.participation?.anonymous && (
              <span
                className={`rounded-full border px-3 py-1 text-sm ${immersive ? "border-on-primary/40" : "border-line bg-surface"}`}
              >
                {t("intro.anonymous")}
              </span>
            )}
          </div>

          {hasExisting ? (
            <div
              className="rounded-[var(--p-radius-card)] bg-surface p-5 text-ink shadow-[var(--p-shadow)] [@media(max-height:800px)]:p-4"
              data-testid="resume-card"
            >
              <h2 className="text-lg">{t("intro.welcomeBack")}</h2>
              <p className="mt-1 text-ink-soft [@media(max-height:800px)]:leading-snug">
                {existing.data!.status === "submitted"
                  ? t("intro.submitted")
                  : t("intro.resumeHint")}
              </p>
              <div className="mt-4 flex flex-wrap gap-3 [@media(max-height:800px)]:mt-3">
                <Button
                  variant="primary"
                  size="runner"
                  onClick={resume}
                  data-testid="resume"
                >
                  {t("intro.continue")}
                </Button>
                {existing.data!.status !== "submitted" ? (
                  canStartAgain && (
                    <Button
                      variant="text"
                      size="runner"
                      onClick={() => setConfirmingStartAgain(true)}
                      data-testid="start-again"
                    >
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
              <AlertDialog
                open={confirmingStartAgain}
                onOpenChange={setConfirmingStartAgain}
              >
                <AlertDialogContent data-testid="start-again-dialog">
                  <AlertDialogHeader>
                    <AlertDialogTitle>{t("intro.startAgain")}</AlertDialogTitle>
                    <AlertDialogDescription>
                      {t("intro.startAgainConfirm")}
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel data-testid="start-again-cancel">
                      {t("common.cancel")}
                    </AlertDialogCancel>
                    <AlertDialogAction
                      onClick={startAgain}
                      data-testid="start-again-confirm"
                    >
                      {t("intro.startAgainAction")}
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </div>
          ) : (
            <>
              {machineTranslated && (
                <p
                  className="rounded-[var(--p-radius-card)] bg-surface p-4 text-[0.95rem] text-ink [@media(max-height:800px)]:p-3 [@media(max-height:800px)]:text-[0.9rem] [@media(max-height:800px)]:leading-snug"
                  role="note"
                  data-testid="machine-translation"
                >
                  {t("intro.machineTranslation", {
                    source: languageName(def.default_language),
                    language: languageName(def.language),
                  })}
                </p>
              )}
              {consent && (
                <div className="rounded-[var(--p-radius-card)] bg-surface p-5 text-ink">
                  {/* Inline links in the notice text: `[…](privacy)` reaches the
                      survey's own privacy page, which is what a consent sentence
                      usually needs to point at. */}
                  <p className="text-[0.95rem]">
                    {renderInline(consent.text as string, "consent", {
                      legalPages: { keys: def.legal_pages ?? [], href: (page) => `/s/${slug}/${page}`, from: location.pathname + location.search },
                    })}
                  </p>
                  {!hasLocalPrivacy && privacyUrl && (
                    <a
                      href={privacyUrl}
                      className="mt-2 inline-block text-sm text-primary underline"
                      target="_blank"
                      rel="noreferrer"
                    >
                      {privacyUrl}
                    </a>
                  )}
                  <div className="mt-2 flex min-h-[44px] items-center gap-3">
                    <Checkbox
                      id="consent"
                      className="size-5"
                      checked={agreed}
                      onCheckedChange={(c) => {
                        setAgreed(c === true);
                        setConsentError(false);
                      }}
                      data-testid="consent"
                    />
                    <Label
                      htmlFor="consent"
                      className="flex min-h-[44px] items-center font-normal leading-snug"
                    >
                      {t("intro.consentAgree")}
                    </Label>
                  </div>
                  {consentError && (
                    <p className="mt-2 text-sm text-error" role="alert">
                      {t("intro.consentRequired")}
                    </p>
                  )}
                </div>
              )}
              <div>
                <Button
                  variant={immersive ? "onPrimary" : "primary"}
                  size="runner"
                  onClick={start}
                  disabled={create.isPending || definition.isPlaceholderData}
                  className="px-8"
                  data-testid="start"
                >
                  {t("intro.start")}
                </Button>
              </div>
            </>
          )}
          {/* Outside both branches, like the create error below it: somebody
            resuming has the same right to read the notice as somebody
            starting, and the resume card is the whole screen for them. */}
          {hasLocalPrivacy && (
            <Link
              to={`/s/${slug}/privacy`}
              // Page furniture, not a third action: it sits under Continue /
              // Start again, and a button-shaped thing there would compete with
              // the one the respondent came to press. Muted and set apart, so it
              // is found by somebody looking for it rather than pressed by
              // somebody who was not.
              className={`mt-2 self-start text-sm underline ${immersive ? "text-on-primary/70" : "text-ink-soft"}`}
              data-testid="privacy-link"
            >
              {t("legal.privacy")}
            </Link>
          )}
          {/* Outside both branches: "Start again" / "Start a new response" call start() from the resume card too. */}
          {create.isError && (
            <p
              className={`text-sm ${immersive ? "" : "text-error"}`}
              role="alert"
              data-testid="create-error"
            >
              {isClosed(create.error)
                ? t("app.closed")
                : create.error instanceof ApiError &&
                    create.error.status === 403
                  ? t("app.forbidden")
                  : create.error instanceof ApiError &&
                      create.error.status === 429
                    ? t("app.throttled")
                    : t("app.error")}
            </p>
          )}
        </div>
      </main>
    </div>
  );
}
