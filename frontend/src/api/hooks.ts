import { keepPreviousData, useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useRef } from "react";
import { api } from "./client";
import type { AnswerResult, OptionsSource, ResponseSummary, RunnerDefinition } from "./types";
import type { AnswerValue } from "@/survey/types";
import type { Theme } from "@/theme/types";

export const keys = {
  definition: (slug: string, lang?: string) => ["definition", slug, lang ?? ""] as const,
  response: (id: string) => ["response", id] as const,
  options: (source: string, lang: string) => ["options", source, lang] as const,
  theme: (code: string) => ["theme", code] as const,
};

/**
 * The localized definition. With `responseId` the server serves the version
 * that response is bound to and accepts the response id as the credential, so
 * invited/account participants never need the invite token again after
 * starting. Pass the response's language as `lang` too: it keeps the URL
 * distinct per language, so the browser cache (max-age) cannot serve the
 * previous language after a switch. `enabled: false` holds the query (e.g.
 * until the response, and so its language, is known).
 */
export function useSurveyDefinition(slug: string | undefined, lang?: string, invite?: string, responseId?: string | null, options?: { enabled?: boolean }) {
  const params = new URLSearchParams();
  if (lang) params.set("lang", lang);
  if (invite) params.set("invite", invite);
  if (responseId) params.set("response", responseId);
  const qs = params.toString();
  return useQuery({
    queryKey: [...keys.definition(slug ?? "", lang), invite ?? "", responseId ?? ""],
    queryFn: () => api.get<RunnerDefinition>(`/surveys/${slug}/${qs ? `?${qs}` : ""}`),
    enabled: Boolean(slug) && (options?.enabled ?? true),
    staleTime: Infinity,
    // A language switch re-keys the query; keep rendering the previous
    // localisation meanwhile instead of unmounting the page (and its state).
    placeholderData: keepPreviousData,
  });
}

export function useTheme(code: string | undefined) {
  return useQuery({
    queryKey: keys.theme(code ?? ""),
    queryFn: () => api.get<Theme>(`/themes/${code}/`),
    enabled: Boolean(code),
    staleTime: Infinity,
  });
}

export function useResponse(id: string | null) {
  return useQuery({
    queryKey: keys.response(id ?? ""),
    queryFn: () => api.get<ResponseSummary>(`/responses/${id}/`),
    enabled: Boolean(id),
    staleTime: Infinity,
  });
}

export function useOptionsSource(source: string | undefined, lang: string) {
  return useQuery({
    queryKey: keys.options(source ?? "", lang),
    queryFn: () => api.get<OptionsSource>(`/options/${source}/?lang=${encodeURIComponent(lang)}`),
    enabled: Boolean(source),
    staleTime: Infinity,
  });
}

export function useCreateResponse() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { slug: string; language: string; consent?: { version: string; agreed: boolean }; invitation?: string }) =>
      api.post<ResponseSummary>("/responses/", body),
    onSuccess: (data) => qc.setQueryData(keys.response(data.id), data),
  });
}

export type ResponsePatch = { last_question_key?: string; language?: string };

/**
 * Merge a PATCH result into the cached response, taking only the fields this
 * PATCH set: a slow `last_question_key` PATCH that lands after a language
 * switch must not carry the old language back with it.
 */
export function mergePatched(current: ResponseSummary, patch: ResponsePatch, data: ResponseSummary): ResponseSummary {
  const next = { ...current };
  if (patch.language !== undefined) next.language = data.language;
  if (patch.last_question_key !== undefined) next.last_question_key = data.last_question_key;
  return next;
}

export function usePatchResponse(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ResponsePatch) => api.patch<ResponseSummary>(`/responses/${id}/`, body),
    onSuccess: (data, body) => {
      // Merge only what this PATCH owns: an answer PUT may still be in flight and its
      // optimistic value must survive a PATCH that raced it on the server.
      qc.setQueryData<ResponseSummary>(keys.response(id), (current) => (current ? mergePatched(current, body, data) : data));
    },
  });
}

/** The cached value of `key` before an optimistic save, so a failed save can put it back. */
export type SavedAnswerContext = { seq: number; previous: AnswerValue | undefined; had: boolean };

/** Apply the server's cascade result for a saved answer to the cached response. */
export function applyAnswerResult(current: ResponseSummary, key: string, result: AnswerResult): ResponseSummary {
  const answers = { ...current.answers, [key]: result.answer.value };
  for (const k of result.invalidated) delete answers[k];
  // A pruned matrix keeps its surviving rows; the server sends them back so the
  // cache is settled here (a refetch could be cancelled by the next save).
  Object.assign(answers, result.pruned);
  return { ...current, answers, visible: result.visible, missing: result.missing, progress: result.progress, last_question_key: key };
}

/** Undo the optimistic value of one key only; other keys' later saves stand. */
export function revertAnswer(current: ResponseSummary, key: string, ctx: Pick<SavedAnswerContext, "previous" | "had">): ResponseSummary {
  const answers = { ...current.answers };
  if (ctx.had && ctx.previous !== undefined) answers[key] = ctx.previous;
  else delete answers[key];
  return { ...current, answers };
}

/**
 * Autosave one answer (RUN-14). Optimistic cache update, retry with backoff,
 * and the server's cascade result replaces the optimistic state. Saves of the
 * same key are sequenced: only the latest one's outcome touches the cache, so
 * an older PUT that settles late (a ranking commits one per click) cannot
 * overwrite the newer value or revert it on failure.
 */
export function useSaveAnswer(id: string) {
  const qc = useQueryClient();
  const seqs = useRef(new Map<string, number>());
  // The cached value before the *first* of a run of outstanding saves of a key:
  // a later save in the run must not take an earlier one's optimistic value
  // for the value to revert to when it fails.
  const baselines = useRef(new Map<string, Pick<SavedAnswerContext, "previous" | "had">>());
  const latest = (key: string, ctx: SavedAnswerContext | undefined): ctx is SavedAnswerContext => ctx !== undefined && ctx.seq === seqs.current.get(key);
  return useMutation({
    mutationFn: ({ key, value }: { key: string; value: AnswerValue }) => api.put<AnswerResult>(`/responses/${id}/answers/${key}/`, { value }),
    retry: (count, error) => count < 3 && !(error instanceof Error && "status" in error && (error as { status: number }).status < 500),
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 8000),
    onMutate: async ({ key, value }): Promise<SavedAnswerContext> => {
      const seq = (seqs.current.get(key) ?? 0) + 1;
      seqs.current.set(key, seq);
      await qc.cancelQueries({ queryKey: keys.response(id) });
      const previous = qc.getQueryData<ResponseSummary>(keys.response(id));
      const base = baselines.current.get(key) ?? { previous: previous?.answers[key], had: previous !== undefined && key in previous.answers };
      baselines.current.set(key, base);
      if (previous) qc.setQueryData<ResponseSummary>(keys.response(id), { ...previous, answers: { ...previous.answers, [key]: value }, last_question_key: key });
      return { seq, ...base };
    },
    onSettled: (_data, _err, { key }, ctx) => {
      if (latest(key, ctx)) baselines.current.delete(key);
    },
    onError: (_err, { key }, ctx) => {
      if (!latest(key, ctx)) return;
      qc.setQueryData<ResponseSummary>(keys.response(id), (current) => current && revertAnswer(current, key, ctx));
    },
    onSuccess: (result, { key }, ctx) => {
      if (!latest(key, ctx)) return;
      qc.setQueryData<ResponseSummary>(keys.response(id), (current) => current && applyAnswerResult(current, key, result));
    },
  });
}

export function useSubmitResponse(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<ResponseSummary>(`/responses/${id}/submit/`),
    onSuccess: (data) => qc.setQueryData(keys.response(id), data),
  });
}

/** The answer the server stores once an address has been captured. */
export function withEmailProvided(current: ResponseSummary, key: string): ResponseSummary {
  return { ...current, answers: { ...current.answers, [key]: { provided: true } }, missing: current.missing.filter((k) => k !== key) };
}

/**
 * Write the captured state into the cache now (so Next sees stored === draft
 * and just advances) and refetch for the server's progress figures.
 */
function emailProvided(qc: QueryClient, id: string, key: string) {
  qc.setQueryData<ResponseSummary>(keys.response(id), (current) => current && withEmailProvided(current, key));
  return qc.invalidateQueries({ queryKey: keys.response(id) });
}

export function useContact(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ email }: { email: string; key: string }) => api.post<void>(`/responses/${id}/contact/`, { email }),
    onSuccess: (_data, { key }) => emailProvided(qc, id, key),
  });
}

/** Identity capture (CON-4): the address goes to the host platform's identity service. */
export function useIdentity(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ email }: { email: string; key: string }) => api.post<void>(`/responses/${id}/identity/`, { email }),
    onSuccess: (_data, { key }) => emailProvided(qc, id, key),
  });
}
