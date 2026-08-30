import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router";
import { ApiError } from "@/api/client";
import { useContact, useIdentity, useOptionsSource, usePatchResponse, useResponse, useSaveAnswer, useSubmitResponse, useSurveyDefinition } from "@/api/hooks";
import { OverviewPanel } from "@/components/OverviewPanel";
import { QuestionScreen } from "@/components/QuestionScreen";
import { SectionInterstitial } from "@/components/SectionInterstitial";
import { Shell, type SaveState } from "@/components/Shell";
import { ErrorBanner } from "@/components/ErrorBanner";
import { SkipConfirm } from "@/components/SkipConfirm";
import { useDefinitionLanguage } from "@/i18n/useDefinitionLanguage";
import { storedResponseId } from "@/lib/storage";
import { implicitAnswer, validateAnswer } from "@/survey/answers";
import { missingKeys } from "@/survey/completion";
import { firstOpenKey, overview, position, progressFraction, type Position } from "@/survey/navigation";
import { ANSWERABLE, questionRequired, skipPolicy, type AnswerValue } from "@/survey/types";
import { isAnswered, questionByKey } from "@/survey/visibility";
import { useThemeLogo } from "@/theme/useTheme";

export function WizardPage() {
  const { slug = "", key = "" } = useParams();
  const { t } = useTranslation();
  const navigate = useNavigate();
  const id = storedResponseId(slug);
  const response = useResponse(id);
  // Response-bound: the server serves the version (and language) this response
  // uses, and accepts the response id as the credential for invited/account flows.
  const definition = useSurveyDefinition(slug, response.data?.language, undefined, id);
  const save = useSaveAnswer(id ?? "");
  const patch = usePatchResponse(id ?? "");
  const submit = useSubmitResponse(id ?? "");
  const contact = useContact(id ?? "");
  const identity = useIdentity(id ?? "");
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
  // The route key at render time, so a save that settles after the participant
  // moved on can tell whether its question is still on screen.
  const keyRef = useRef(key);
  // Per-question save sequence: only the latest save of a question may set the
  // page's save state (an older PUT settling late must not raise an error the
  // newer, successful one has already superseded — nor offer to retry its value).
  const saveSeq = useRef(new Map<string, number>());
  // Every save in flight (a blur commit on an earlier question may still be
  // retrying), so Finish waits for all of them instead of racing them on the server.
  const pendingSaves = useRef(new Set<Promise<boolean>>());
  // Field errors for a question the participant has already left, shown once
  // they are back on it (the key effect would otherwise clear them).
  const pendingErrors = useRef<{ key: string; errors: string[] } | null>(null);
  // Set when a failed submit sends the participant to the first missing question:
  // that navigation must keep the "questions missing" alert, not clear it.
  const bouncedToMissing = useRef(false);

  const def = definition.data;
  const answers = response.data?.answers ?? {};
  const pos = useMemo(() => (def ? position(def, answers, key) : null), [def, answers, key]);
  const questions = useMemo(() => (def ? questionByKey(def) : {}), [def]);
  const country = useOptionsSource(def && pos?.visible.some((v) => v.question.config?.options_source) ? "iso3166_countries" : undefined, def?.language ?? "en");
  const countryLabels = useMemo(() => Object.fromEntries((country.data?.options ?? []).map((o) => [o.key, o.label])), [country.data]);

  useDefinitionLanguage(def?.language);

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
  // so no reset effect is needed.
  const resetSubmit = submit.reset;
  useEffect(() => {
    keyRef.current = key;
    setSkipPrompt(false);
    const pending = pendingErrors.current;
    pendingErrors.current = null;
    setLocalErrors(pending && pending.key === key ? pending.errors : []);
    setInterstitial(null); // leaving an interstitial via the overview or browser history
    // A stale "questions missing" alert must not follow the participant, except on
    // the navigation that raised it; it clears on their next move.
    if (bouncedToMissing.current) bouncedToMissing.current = false;
    else resetSubmit();
  }, [key, resetSubmit]);

  const refetchResponse = response.refetch;
  const flashSaved = useCallback(() => {
    setSaveState("saved");
    if (savedTimer.current) window.clearTimeout(savedTimer.current);
    savedTimer.current = window.setTimeout(() => setSaveState("idle"), 1500);
  }, []);

  const persist = useCallback(
    async (qKey: string, value: AnswerValue): Promise<boolean> => {
      const seq = (saveSeq.current.get(qKey) ?? 0) + 1;
      saveSeq.current.set(qKey, seq);
      const latest = () => saveSeq.current.get(qKey) === seq;
      setSaveState("saving");
      const run = (async () => {
        try {
          await save.mutateAsync({ key: qKey, value });
          if (!latest()) return false; // superseded by a newer save of this question
          lastFailed.current = null;
          flashSaved();
          return true;
        } catch (err) {
          if (!latest()) return false;
          if (err instanceof ApiError && err.status === 410) {
            // The survey closed mid-response: nothing to retry, the footer explains.
            lastFailed.current = null;
            setSaveState("closed");
            return false;
          }
          if (err instanceof ApiError && err.status === 400) {
            const errors = err.fieldErrors.length ? err.fieldErrors : [t("app.error")];
            setSaveState("idle");
            if (qKey === keyRef.current) {
              setLocalErrors(errors);
            } else {
              // The participant moved on before the server refused this answer; its
              // optimistic value is reverted, so bring them back to it with the message.
              pendingErrors.current = { key: qKey, errors };
              navigate(`/s/${slug}/q/${qKey}`);
            }
            return false;
          }
          if (err instanceof ApiError) void refetchResponse(); // 409 submitted elsewhere / 404 gone: let the redirect effect take over
          lastFailed.current = { key: qKey, value };
          setSaveState("error");
          return false;
        }
      })();
      pendingSaves.current.add(run);
      try {
        return await run;
      } finally {
        pendingSaves.current.delete(run);
      }
    },
    [save, flashSaved, refetchResponse, navigate, slug, t],
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
  // Before any interaction a question may already hold a valid answer (a required
  // ranking's displayed order); deriving it here rather than in the lazily loaded
  // renderer means Next cannot race the renderer's chunk.
  const draftValue = draftKey === key ? draft : (answers[key] ?? implicitAnswer(question));
  const hasDraft = isAnswerable && draftValue !== undefined && (isAnswered(draftValue) || ("provided" in draftValue && !draftValue.provided));
  // An explicit clear (renderer sent `undefined`) means "no answer" even when a
  // value is stored: Next must then go through the skip flow, not keep the old value.
  const cleared = draftKey === key && draft === undefined;
  const section = def.sections[current.sectionIndex];

  const onChange = (value: AnswerValue | undefined, opts?: { commit?: boolean; advance?: boolean }) => {
    setDraft(value);
    setDraftKey(key);
    setSkipPrompt(false);
    setLocalErrors([]);
    if (opts?.commit && value !== undefined) {
      // Blur on an unchanged text/number/date field must not PUT the same value again.
      const unchanged = JSON.stringify(value) === JSON.stringify(answers[key]);
      void (unchanged ? Promise.resolve(true) : commit(value)).then((ok) => {
        if (ok && opts.advance) void advance(after(value));
      });
    }
  };

  const commit = async (value: AnswerValue): Promise<boolean> => {
    try {
      validateAnswer(question, value, answers, { skipPolicy: policy, sourceOptions: new Set(Object.keys(countryLabels)), questions });
    } catch (e) {
      const errors = (e as { errors?: string[] }).errors ?? [String(e)];
      setLocalErrors(question.type === "matrix" && errors.some((m) => m.startsWith("every row must be rated")) ? [t("matrix.incomplete")] : errors);
      return false;
    }
    return persist(key, value);
  };

  /**
   * Move on from `p` — the position *after* the value just saved, which may
   * have revealed or hidden questions; the render-time `pos` is stale by then.
   */
  const advance = async (p: Position = pos) => {
    setSkipPrompt(false);
    if (p.isLast) {
      // Finish must not race any autosave still in flight (a blur commit on an
      // earlier question, or a click commit right before Finish): the server
      // would read the answers before that PUT lands and report the question
      // missing — or, for an optional one, submit without it.
      while (pendingSaves.current.size) {
        const outcomes = await Promise.all([...pendingSaves.current]);
        if (outcomes.some((ok) => !ok)) return;
      }
      submit.mutate(undefined, {
        onSuccess: () => navigate(`/s/${slug}/complete`),
        onError: (err) => {
          if (err instanceof ApiError && err.status === 410) {
            setSaveState("closed");
            return;
          }
          const missing = err instanceof ApiError ? err.body.missing : undefined;
          if (!missing?.length) return;
          if (missing[0] !== key) bouncedToMissing.current = true;
          goTo(missing[0]);
        },
      });
      return;
    }
    const next = p.visible[p.index + 1];
    if (!next) return; // the URL question is no longer visible; the redirect effect relocates
    if (def.presentation?.section_interstitials !== false && next.sectionIndex !== current.sectionIndex) {
      setInterstitial(next.sectionIndex);
      return;
    }
    goTo(next.key);
  };

  const after = (value: AnswerValue) => position(def, { ...answers, [key]: value }, key);

  const onNext = async () => {
    if (interstitial !== null) {
      const target = pos.visible.find((v) => v.sectionIndex === interstitial);
      setInterstitial(null);
      if (target) goTo(target.key);
      return;
    }
    if (saveState === "error" || saveState === "closed") return;
    if (!isAnswerable) {
      await advance();
      return;
    }
    const stored = cleared ? undefined : answers[key];
    if (hasDraft && draftValue !== undefined) {
      if (JSON.stringify(stored) !== JSON.stringify(draftValue)) {
        if (!(await commit(draftValue))) return;
      } else if (missingKeys(def, answers).includes(key)) {
        // Stored but no longer complete (a rows_from matrix whose source gained
        // rows after it was rated): the server would bounce the submit back here.
        setLocalErrors([t("matrix.incomplete")]);
        return;
      }
      await advance(after(draftValue));
      return;
    }
    if (stored !== undefined) {
      await advance();
      return;
    }
    // Unanswered.
    if (!required || policy === "none") {
      if (await persist(key, { skipped: true })) await advance(after({ skipped: true }));
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
    if (await persist(key, { skipped: true })) await advance(after({ skipped: true }));
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

  // The overview sheet is unmounted while closed; don't walk the DAG twice per keystroke for it.
  const rows = overviewOpen ? overview(def, answers, key, response.data.last_question_key) : [];
  const progressValue = progressFraction(pos, hasDraft || answers[key] !== undefined);

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
        nextDisabled={saveState === "error" || saveState === "closed" || submit.isPending || (policy === "hard" && required && isAnswerable && !hasDraft && answers[key] === undefined)}
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
            onSubmitEmail={async (email) => {
              // Identity capture goes to the host's identity service; contact capture is stored unlinked.
              await (question.config?.link_identity ? identity.mutateAsync({ email, key }) : contact.mutateAsync({ email, key }));
              setDraftKey(key);
              setDraft({ provided: true });
              flashSaved();
            }}
          />
        )}
        {submit.isError && saveState !== "closed" && (
          <p className="mt-6 text-sm text-error" role="alert">
            {submit.error instanceof ApiError && submit.error.body.missing ? t("complete.missing") : t("app.error")}
          </p>
        )}
      </Shell>
      <OverviewPanel open={overviewOpen} onClose={() => setOverviewOpen(false)} sections={rows} definitionSections={def.sections} answers={answers} onNavigate={goTo} countryLabels={countryLabels} />
    </>
  );
}
