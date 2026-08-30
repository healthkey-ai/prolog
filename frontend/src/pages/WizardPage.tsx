import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router";
import { ApiError } from "@/api/client";
import { useContact, useOptionsSource, usePatchResponse, useResponse, useSaveAnswer, useSubmitResponse, useSurveyDefinition } from "@/api/hooks";
import { OverviewPanel } from "@/components/OverviewPanel";
import { QuestionScreen } from "@/components/QuestionScreen";
import { SectionInterstitial } from "@/components/SectionInterstitial";
import { Shell, type SaveState } from "@/components/Shell";
import { ErrorBanner } from "@/components/ErrorBanner";
import { SkipConfirm } from "@/components/SkipConfirm";
import i18n from "@/i18n";
import { storedResponseId } from "@/lib/storage";
import { validateAnswer } from "@/survey/answers";
import { firstOpenKey, overview, position } from "@/survey/navigation";
import { ANSWERABLE, questionRequired, skipPolicy, type AnswerValue } from "@/survey/types";
import { isAnswered, questionByKey } from "@/survey/visibility";
import { useThemeLogo } from "@/theme/useTheme";

export function WizardPage() {
  const { slug = "", key = "" } = useParams();
  const { t } = useTranslation();
  const navigate = useNavigate();
  const id = storedResponseId(slug);
  const response = useResponse(id);
  const definition = useSurveyDefinition(slug, response.data?.language);
  const save = useSaveAnswer(id ?? "");
  const patch = usePatchResponse(id ?? "");
  const submit = useSubmitResponse(id ?? "");
  const contact = useContact(id ?? "");
  const logo = useThemeLogo();

  const [draft, setDraft] = useState<AnswerValue | undefined>(undefined);
  const [draftKey, setDraftKey] = useState<string | null>(null);
  const [skipPrompt, setSkipPrompt] = useState(false);
  const [overviewOpen, setOverviewOpen] = useState(false);
  const [interstitial, setInterstitial] = useState<number | null>(null);
  const [localErrors, setLocalErrors] = useState<string[]>([]);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const savedTimer = useRef<number | null>(null);
  const lastFailed = useRef<{ key: string; value: AnswerValue } | null>(null);

  const def = definition.data;
  const answers = response.data?.answers ?? {};
  const pos = useMemo(() => (def ? position(def, answers, key) : null), [def, answers, key]);
  const questions = useMemo(() => (def ? questionByKey(def) : {}), [def]);
  const country = useOptionsSource(def && pos?.visible.some((v) => v.question.config?.options_source) ? "iso3166_countries" : undefined, def?.language ?? "en");
  const countryLabels = useMemo(() => Object.fromEntries((country.data?.options ?? []).map((o) => [o.key, o.label])), [country.data]);

  useEffect(() => {
    if (def) {
      void i18n.changeLanguage(def.language);
      document.documentElement.lang = def.language;
    }
  }, [def]);

  // Redirect: no response, submitted, or the URL question is not visible.
  useEffect(() => {
    if (!id) {
      navigate(`/s/${slug}`, { replace: true });
      return;
    }
    if (response.isError) {
      navigate(`/s/${slug}`, { replace: true });
      return;
    }
    if (response.data?.status === "submitted") {
      navigate(`/s/${slug}/complete`, { replace: true });
      return;
    }
    if (def && response.data && pos && pos.index < 0) {
      const target = firstOpenKey(def, response.data.answers, response.data.last_question_key);
      if (target && target !== key) navigate(`/s/${slug}/q/${target}`, { replace: true });
    }
  }, [id, def, response.data, response.isError, pos, key, slug, navigate]);

  // The draft is keyed on the question: a stale draft from another question is ignored,
  // so no reset effect is needed (a reset would race with renderers that register a
  // default draft on mount, e.g. ranking).
  useEffect(() => {
    setSkipPrompt(false);
    setLocalErrors([]);
  }, [key]);

  const flashSaved = useCallback(() => {
    setSaveState("saved");
    if (savedTimer.current) window.clearTimeout(savedTimer.current);
    savedTimer.current = window.setTimeout(() => setSaveState("idle"), 1500);
  }, []);

  const persist = useCallback(
    async (qKey: string, value: AnswerValue): Promise<boolean> => {
      setSaveState("saving");
      try {
        await save.mutateAsync({ key: qKey, value });
        lastFailed.current = null;
        flashSaved();
        return true;
      } catch (err) {
        if (err instanceof ApiError && err.status === 400) {
          setLocalErrors(err.fieldErrors);
          setSaveState("idle");
        } else {
          lastFailed.current = { key: qKey, value };
          setSaveState("error");
        }
        return false;
      }
    },
    [save, flashSaved],
  );

  const goTo = useCallback(
    (target: string) => {
      navigate(`/s/${slug}/q/${target}`);
      if (id) patch.mutate({ last_question_key: target });
    },
    [navigate, slug, id, patch],
  );

  if (!def || !response.data || !pos || !pos.current) {
    return <p className="p-8 text-ink-soft">{response.isError ? t("app.error") : t("app.loading")}</p>;
  }

  const current = pos.current;
  const question = current.question;
  const policy = skipPolicy(def);
  const required = questionRequired(question);
  const isAnswerable = ANSWERABLE.has(question.type);
  const draftValue = draftKey === key ? draft : answers[key];
  const hasDraft = isAnswerable && draftValue !== undefined && (isAnswered(draftValue) || ("provided" in draftValue && !draftValue.provided));
  const section = def.sections[current.sectionIndex];

  const onChange = (value: AnswerValue | undefined, opts?: { commit?: boolean }) => {
    setDraft(value);
    setDraftKey(key);
    setSkipPrompt(false);
    setLocalErrors([]);
    if (opts?.commit && value !== undefined) void commit(value);
  };

  const commit = async (value: AnswerValue): Promise<boolean> => {
    try {
      validateAnswer(question, value, answers, { skipPolicy: policy, sourceOptions: new Set(Object.keys(countryLabels)) });
    } catch (e) {
      const errors = (e as { errors?: string[] }).errors ?? [String(e)];
      setLocalErrors(question.type === "matrix" && errors.some((m) => m.startsWith("every row must be rated")) ? [t("matrix.incomplete")] : errors);
      return false;
    }
    return persist(key, value);
  };

  const advance = () => {
    setSkipPrompt(false);
    if (pos.isLast) {
      submit.mutate(undefined, {
        onSuccess: () => navigate(`/s/${slug}/complete`),
        onError: (err) => {
          const missing = err instanceof ApiError ? err.body.missing : undefined;
          if (missing?.length) goTo(missing[0]);
        },
      });
      return;
    }
    const next = pos.visible[pos.index + 1];
    if (def.presentation?.section_interstitials !== false && next.sectionIndex !== current.sectionIndex) {
      setInterstitial(next.sectionIndex);
      return;
    }
    goTo(next.key);
  };

  const onNext = async () => {
    if (interstitial !== null) {
      const target = pos.visible.find((v) => v.sectionIndex === interstitial);
      setInterstitial(null);
      if (target) goTo(target.key);
      return;
    }
    if (saveState === "error") return;
    if (!isAnswerable) {
      advance();
      return;
    }
    const stored = answers[key];
    if (hasDraft && draftValue !== undefined) {
      if (JSON.stringify(stored) !== JSON.stringify(draftValue)) {
        if (!(await commit(draftValue))) return;
      }
      advance();
      return;
    }
    if (stored !== undefined) {
      advance();
      return;
    }
    // Unanswered.
    if (!required || policy === "none") {
      if (await persist(key, { skipped: true })) advance();
      return;
    }
    if (policy === "hard") {
      setLocalErrors([t("skip.hard")]);
      return;
    }
    setSkipPrompt(true);
  };

  const onSkip = async () => {
    setSkipPrompt(false);
    if (await persist(key, { skipped: true })) advance();
  };

  const onBack = () => {
    if (interstitial !== null) {
      setInterstitial(null);
      return;
    }
    if (pos.previousKey) goTo(pos.previousKey);
  };

  const onLanguage = (lang: string) => {
    patch.mutate({ language: lang });
  };

  const retry = () => {
    if (lastFailed.current) void persist(lastFailed.current.key, lastFailed.current.value);
  };

  const rows = overview(def, answers, key, response.data.last_question_key);
  const progressValue = pos.questionTotal ? Math.min(1, (pos.questionNumber - (hasDraft || answers[key] ? 0 : 1)) / pos.questionTotal) : 0;

  return (
    <>
      <Shell
        sectionLabel={interstitial !== null ? (def.sections[interstitial].title as string) : (section.title as string)}
        sectionNumber={interstitial !== null ? pos.visibleSectionIndexes.indexOf(interstitial) + 1 : pos.sectionNumber}
        sectionTotal={pos.sectionTotal}
        progress={progressValue}
        showProgress={def.presentation?.progress !== "none"}
        onOverview={def.presentation?.overview !== false ? () => setOverviewOpen(true) : undefined}
        languages={def.languages}
        language={def.language}
        onLanguage={onLanguage}
        onBack={pos.previousKey || interstitial !== null ? onBack : undefined}
        onNext={onNext}
        nextLabel={interstitial !== null ? t("interstitial.continue") : pos.isLast ? t("nav.finish") : t("nav.next")}
        nextDisabled={saveState === "error" || submit.isPending || (policy === "hard" && required && isAnswerable && !hasDraft && answers[key] === undefined)}
        saveState={saveState}
        onRetry={retry}
        footerExtra={skipPrompt ? <SkipConfirm onSkip={onSkip} onAnswer={() => setSkipPrompt(false)} /> : localErrors.length ? <ErrorBanner errors={localErrors} /> : null}
        logo={logo}
      >
        {interstitial !== null ? (
          <SectionInterstitial number={pos.visibleSectionIndexes.indexOf(interstitial) + 1} title={def.sections[interstitial].title as string} description={def.sections[interstitial].description as string | undefined} />
        ) : (
          <QuestionScreen
            key={key}
            question={question}
            value={draftValue}
            onChange={onChange}
            language={def.language}
            questionNumber={pos.questionNumber}
            questionTotal={pos.questionTotal}
            answers={answers}
            questions={questions}
            onDeclineEmail={async () => {
              if (await persist(key, { provided: false })) advance();
            }}
            onSubmitEmail={async (email) => {
              await contact.mutateAsync(email);
              setDraftKey(key);
              setDraft({ provided: true });
              flashSaved();
            }}
          />
        )}
        {submit.isError && (
          <p className="mt-6 text-sm text-error" role="alert">
            {t("complete.missing")}
          </p>
        )}
      </Shell>
      <OverviewPanel open={overviewOpen} onClose={() => setOverviewOpen(false)} sections={rows} definitionSections={def.sections} answers={answers} onNavigate={goTo} countryLabels={countryLabels} />
    </>
  );
}
