import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router";
import { ApiError, isClosed, isGone } from "@/api/client";
import { SupersededError, useContact, useIdentity, useOptionsSources, usePatchResponse, useResponse, useSaveAnswer, useSubmitResponse, useSurveyDefinition } from "@/api/hooks";
import { DefinitionError } from "@/components/DefinitionError";
import { OverviewPanel } from "@/components/OverviewPanel";
import { QuestionScreen } from "@/components/QuestionScreen";
import { SectionInterstitial } from "@/components/SectionInterstitial";
import { Shell, type SaveState } from "@/components/Shell";
import { ErrorBanner } from "@/components/ErrorBanner";
import { SkipConfirm } from "@/components/SkipConfirm";
import { Button } from "@/components/ui/button";
import { issueMessages } from "@/i18n/issues";
import { useDefinitionLanguage } from "@/i18n/useDefinitionLanguage";
import { storedResponseId } from "@/lib/storage";
import { AnswerError, implicitAnswer, validateAnswer } from "@/survey/answers";
import { missingKeys } from "@/survey/completion";
import { firstOpenKey, hasStoredAnswer, overview, position, progressFraction, type Position } from "@/survey/navigation";
import { ANSWERABLE, questionRequired, skipPolicy, type AnswerValue, type Question } from "@/survey/types";
import { questionByKey } from "@/survey/visibility";
import { useThemeLogo } from "@/theme/useTheme";
import { usePageTitle } from "./usePageTitle";

/**
 * How a save ended. Only "failed" stops the participant; "superseded" means a
 * newer save of the same question took over and reports for it.
 */
type SaveOutcome = "saved" | "failed" | "superseded";

/**
 * The open skip prompt (soft policy). `target` is where the participant was
 * going when it opened: Back or an overview jump from a question whose stored
 * answer they cleared; null when it was Next.
 */
type SkipPrompt = { target: string | null };

/** The server's view of the response differs from the cache (submitted in another tab, or gone). */
const stale = (err: unknown) => (err instanceof ApiError && err.status === 409) || isGone(err);

export function WizardPage() {
  const { slug = "", key = "" } = useParams();
  const { t } = useTranslation();
  const navigate = useNavigate();
  const id = storedResponseId(slug);
  const response = useResponse(id);
  // Response-bound: the server serves the version (and language) this response
  // uses, and accepts the response id as the credential for invited/account flows.
  const definition = useSurveyDefinition(slug, { lang: response.data?.language, responseId: id });
  const save = useSaveAnswer(id ?? "");
  const patch = usePatchResponse(id ?? "");
  const submit = useSubmitResponse(id ?? "");
  const contact = useContact(id ?? "");
  const identity = useIdentity(id ?? "");
  const logo = useThemeLogo();

  const [draft, setDraft] = useState<AnswerValue | undefined>(undefined);
  const [draftKey, setDraftKey] = useState<string | null>(null);
  const [skipPrompt, setSkipPrompt] = useState<SkipPrompt | null>(null);
  const [overviewOpen, setOverviewOpen] = useState(false);
  const [interstitial, setInterstitial] = useState<number | null>(null);
  const [localErrors, setLocalErrors] = useState<string[]>([]);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  // The language whose PATCH failed: the header Select snaps back to the
  // stored language, so the failure must be said and retryable.
  const [languageFailed, setLanguageFailed] = useState<string | null>(null);
  const savedTimer = useRef<number | null>(null);
  const lastFailed = useRef<{ key: string; value: AnswerValue } | null>(null);
  // The route key at render time, so a save that settles after the participant
  // moved on can tell whether its question is still on screen.
  const keyRef = useRef(key);
  // Every save in flight (a blur commit on an earlier question may still be
  // retrying), so Finish waits for all of them instead of racing them on the
  // server; and the latest one per question, so Next on an optimistically
  // stored answer waits for its PUT to land before a downstream PUT can overtake it.
  const pendingSaves = useRef(new Set<Promise<SaveOutcome>>());
  const pendingByKey = useRef(new Map<string, Promise<SaveOutcome>>());
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
  // Option sources (e.g. countries) of every visible dropdown, each fetched once:
  // the current question's list validates its answer, the overview shows labels.
  const sources = useMemo(() => [...new Set((pos?.visible ?? []).map((v) => v.question.config?.options_source).filter((s): s is string => Boolean(s)))], [pos]);
  const sourceLabels = useOptionsSources(sources, def?.language ?? "en");

  useDefinitionLanguage(def?.language);
  // "<survey> – <step>": the step is the section on an interstitial, otherwise the question number.
  const step =
    def && pos?.current
      ? interstitial !== null
        ? (def.sections[interstitial].title as string)
        : pos.current.type === "info"
          ? t("question.info")
          : t("question.eyebrow", { number: pos.questionNumber, total: pos.questionTotal })
      : undefined;
  usePageTitle(def && step ? t("app.pageTitle", { survey: def.title as string, step }) : undefined);

  // Redirect: no response, one that is gone, a submitted one, or a URL question that is not visible.
  useEffect(() => {
    if (!id) {
      navigate(`/s/${slug}`, { replace: true });
      return;
    }
    if (response.isError && (isGone(response.error) || !response.data)) {
      // A transient refetch error keeps the page (and its retry affordance): the
      // cached response is still good to work with.
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
  }, [id, def, response.data, response.isError, response.error, pos, key, slug, navigate]);

  // The draft is keyed on the question: a stale draft from another question is ignored,
  // so no reset effect is needed.
  const resetSubmit = submit.reset;
  useEffect(() => {
    keyRef.current = key;
    setSkipPrompt(null);
    setLanguageFailed(null);
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
    async (qKey: string, value: AnswerValue): Promise<SaveOutcome> => {
      setSaveState("saving");
      const run = (async (): Promise<SaveOutcome> => {
        try {
          await save.mutateAsync({ key: qKey, value });
          lastFailed.current = null;
          flashSaved();
          return "saved";
        } catch (err) {
          // A newer save of this question is in flight: it reports for both.
          if (err instanceof SupersededError) return "superseded";
          if (isClosed(err)) {
            // The survey closed mid-response: nothing to retry, the footer explains.
            lastFailed.current = null;
            setSaveState("closed");
            return "failed";
          }
          if (err instanceof ApiError && err.status === 400) {
            const errors = err.issues.length ? issueMessages(err.issues, t) : err.fieldErrors.length ? err.fieldErrors : [t("app.error")];
            setSaveState("idle");
            if (qKey === keyRef.current) {
              setLocalErrors(errors);
            } else {
              // The participant moved on before the server refused this answer; its
              // optimistic value is reverted, so bring them back to it with the message.
              pendingErrors.current = { key: qKey, errors };
              navigate(`/s/${slug}/q/${qKey}`);
            }
            return "failed";
          }
          if (stale(err)) void refetchResponse(); // submitted elsewhere / gone: let the redirect effect take over
          lastFailed.current = { key: qKey, value };
          setSaveState("error");
          return "failed";
        }
      })();
      pendingSaves.current.add(run);
      pendingByKey.current.set(qKey, run);
      try {
        return await run;
      } finally {
        pendingSaves.current.delete(run);
        if (pendingByKey.current.get(qKey) === run) pendingByKey.current.delete(qKey);
      }
    },
    [save, flashSaved, refetchResponse, navigate, slug, t],
  );

  /** The latest save of the current question, if one is still in flight, must land before moving on. */
  const settled = useCallback(async (): Promise<boolean> => {
    const pending = pendingByKey.current.get(key);
    return !pending || (await pending) !== "failed";
  }, [key]);

  const goTo = useCallback(
    async (target: string) => {
      // Back and the overview jump wait like Next does: a PUT for the target (or
      // for a question the current answer reveals) must not reach the server
      // before the current question's PUT. A failed save keeps the participant
      // here, with its error and retry.
      if (!(await settled())) return;
      navigate(`/s/${slug}/q/${target}`);
      if (id) patch.mutate({ last_question_key: target });
    },
    [settled, navigate, slug, id, patch],
  );

  // The definition failed (throttled, outage, network, or the survey is gone or
  // closed) and nothing older is cached: say so, with a retry where one makes
  // sense, instead of "Loading…" for good. A response error is handled by the
  // redirect effect (gone / nothing cached) or is transient (cached data stands).
  if (!def && definition.isError) {
    return <DefinitionError error={definition.error} onRetry={() => void definition.refetch()} retrying={definition.isFetching} />;
  }
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
  const hasDraft = isAnswerable && hasStoredAnswer(draftValue);
  // An explicit clear (renderer sent `undefined`) of a stored answer means "no
  // answer": leaving the question must then go through the skip flow, not keep
  // the old value. Once the clear is recorded as a skip there is nothing left to clear.
  const cleared = draftKey === key && draft === undefined && hasStoredAnswer(answers[key]);
  // A skippable question: its clear can be recorded (as a skip, the server's only
  // "no answer" state) without asking; soft/hard required ones go through the prompt / block.
  const skippable = !required || policy === "none";
  const section = def.sections[current.sectionIndex];

  /** Client-side check of a value against the same rules the server applies; the messages are chrome strings. */
  const localIssues = (q: Question, value: AnswerValue): string[] => {
    try {
      validateAnswer(q, value, answers, { skipPolicy: policy, sourceOptions: new Set(Object.keys(sourceLabels[q.config?.options_source ?? ""] ?? {})), questions });
      return [];
    } catch (e) {
      return e instanceof AnswerError ? issueMessages(e.issues, t) : [t("error.generic")];
    }
  };

  const onChange = (value: AnswerValue | undefined, opts?: { commit?: boolean; advance?: boolean }) => {
    setDraft(value);
    setDraftKey(key);
    setSkipPrompt(null);
    setLocalErrors([]);
    if (!opts?.commit) return;
    if (value !== undefined) {
      // Blur on an unchanged text/number/date field must not PUT the same value again.
      const unchanged = JSON.stringify(value) === JSON.stringify(answers[key]);
      void (unchanged ? Promise.resolve<SaveOutcome>("saved") : commit(value)).then((outcome) => {
        if (outcome === "saved" && opts.advance) void advance(after(value));
      });
    } else if (hasStoredAnswer(answers[key]) && skippable) {
      // An emptied field / cleared choice over a stored answer is recorded now
      // (the server has no "no answer", only a skip), so Back, the overview,
      // progress and browser history never bring the old value back. A required
      // question under soft/hard policy keeps the clear as a draft until the
      // participant leaves, when the skip flow asks or blocks (resolveCleared).
      void persist(key, { skipped: true });
    }
  };

  const commit = async (value: AnswerValue): Promise<SaveOutcome> => {
    const errors = localIssues(question, value);
    if (errors.length) {
      setLocalErrors(errors);
      return "failed";
    }
    return persist(key, value);
  };

  /**
   * Move on from `p` — the position *after* the value just saved, which may
   * have revealed or hidden questions; the render-time `pos` is stale by then.
   */
  const advance = async (p: Position = pos) => {
    setSkipPrompt(null);
    if (p.isLast) {
      // Finish must not race any autosave still in flight (a blur commit on an
      // earlier question, or a click commit right before Finish): the server
      // would read the answers before that PUT lands and report the question
      // missing — or, for an optional one, submit without it. A superseded save
      // is not a failure: the save that superseded it is awaited here too.
      while (pendingSaves.current.size) {
        const outcomes = await Promise.all([...pendingSaves.current]);
        if (outcomes.includes("failed")) return;
      }
      submit.mutate(undefined, {
        onSuccess: () => navigate(`/s/${slug}/complete`),
        onError: (err) => {
          if (isClosed(err)) {
            setSaveState("closed");
            return;
          }
          if (stale(err)) {
            // Submitted in another tab (409) or gone: the refreshed response
            // sends the participant to the right page.
            void refetchResponse();
            return;
          }
          const missing = err instanceof ApiError ? err.body.missing : undefined;
          if (!missing?.length) return;
          if (missing[0] !== key) bouncedToMissing.current = true;
          void goTo(missing[0]);
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
    await goTo(next.key);
  };

  const after = (value: AnswerValue) => position(def, { ...answers, [key]: value }, key);

  /**
   * Whether the participant may leave a question whose stored answer they
   * cleared — the same skip flow Next applies, so the deletion is never
   * dropped: a skippable question records the skip, a soft-required one asks
   * (the prompt remembers `target`), a hard-required one blocks. True when there
   * is nothing to resolve.
   */
  const resolveCleared = async (target: string | null): Promise<boolean> => {
    if (!cleared) return true;
    if (skippable) return (await persist(key, { skipped: true })) === "saved";
    if (policy === "hard") {
      setLocalErrors([t("skip.hard")]);
      return false;
    }
    setSkipPrompt({ target });
    return false;
  };

  /** Back and the overview jump: leave for `target` once a cleared answer is resolved. */
  const leave = async (target: string) => {
    if (!(await resolveCleared(target))) return;
    await goTo(target);
  };

  const onNext = async () => {
    if (interstitial !== null) {
      const target = pos.visible.find((v) => v.sectionIndex === interstitial);
      setInterstitial(null);
      if (target) await goTo(target.key);
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
        if ((await commit(draftValue)) !== "saved") return;
      } else {
        // Stored, possibly only optimistically: its PUT must land before a
        // downstream question's, or the server refuses the latter as not shown.
        if (!(await settled())) return;
        if (missingKeys(def, answers).includes(key)) {
          // Stored but no longer complete (a rows_from matrix whose source gained
          // rows after it was rated): the server would bounce the submit back here.
          setLocalErrors(localIssues(question, draftValue));
          return;
        }
      }
      await advance(after(draftValue));
      return;
    }
    if (stored !== undefined) {
      if (!(await settled())) return;
      await advance();
      return;
    }
    // Unanswered.
    if (skippable) {
      if ((await persist(key, { skipped: true })) === "saved") await advance(after({ skipped: true }));
      return;
    }
    if (policy === "hard") {
      setLocalErrors([t("skip.hard")]);
      return;
    }
    setSkipPrompt({ target: null });
  };

  const onSkip = async () => {
    const target = skipPrompt?.target ?? null;
    setSkipPrompt(null);
    if ((await persist(key, { skipped: true })) !== "saved") return;
    if (target) await goTo(target);
    else await advance(after({ skipped: true }));
  };

  const onBack = () => {
    if (interstitial !== null) {
      setInterstitial(null);
      return;
    }
    if (pos.previousKey) void leave(pos.previousKey);
  };

  const onLanguage = (lang: string) => {
    setLanguageFailed(null);
    patch.mutate(
      { language: lang },
      {
        onError: (err) => {
          if (isClosed(err)) {
            setSaveState("closed");
            return;
          }
          if (stale(err)) {
            void refetchResponse(); // submitted elsewhere / gone: the redirect effect takes over
            return;
          }
          setLanguageFailed(lang);
        },
      },
    );
  };

  const retry = () => {
    if (lastFailed.current) void persist(lastFailed.current.key, lastFailed.current.value);
  };

  // The overview sheet is unmounted while closed; don't walk the DAG for it per keystroke.
  const rows = overviewOpen ? overview(def, answers, key, response.data.last_question_key) : [];
  const progressValue = progressFraction(pos, hasDraft || answers[key] !== undefined);

  return (
    <>
      <Shell
        sectionLabel={interstitial !== null ? (def.sections[interstitial].title as string) : (section.title as string)}
        sectionNumber={interstitial !== null ? pos.visibleSectionIndexes.indexOf(interstitial) + 1 : pos.sectionNumber}
        sectionTotal={pos.sectionTotal}
        progress={progressValue}
        progressStyle={def.presentation?.progress ?? "bar"}
        step={pos.index + 1}
        stepTotal={pos.visible.length}
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
        footerExtra={skipPrompt ? <SkipConfirm onSkip={onSkip} onAnswer={() => setSkipPrompt(null)} /> : localErrors.length ? <ErrorBanner errors={localErrors} /> : null}
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
        {languageFailed && saveState !== "closed" && (
          <p className="mt-6 text-sm text-error" role="alert" data-testid="language-error">
            {t("app.error")}{" "}
            <Button variant="link" size="runner-sm" className="text-error" onClick={() => onLanguage(languageFailed)} disabled={patch.isPending}>
              {t("app.retry")}
            </Button>
          </p>
        )}
      </Shell>
      <OverviewPanel open={overviewOpen} onClose={() => setOverviewOpen(false)} sections={rows} definitionSections={def.sections} answers={answers} onNavigate={(target) => void leave(target)} sourceLabels={sourceLabels} />
    </>
  );
}
