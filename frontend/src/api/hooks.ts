import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
 * previous language after a switch.
 */
export function useSurveyDefinition(slug: string | undefined, lang?: string, invite?: string, responseId?: string | null) {
  const params = new URLSearchParams();
  if (lang) params.set("lang", lang);
  if (invite) params.set("invite", invite);
  if (responseId) params.set("response", responseId);
  const qs = params.toString();
  return useQuery({
    queryKey: [...keys.definition(slug ?? "", lang), invite ?? "", responseId ?? ""],
    queryFn: () => api.get<RunnerDefinition>(`/surveys/${slug}/${qs ? `?${qs}` : ""}`),
    enabled: Boolean(slug),
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

export function usePatchResponse(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { last_question_key?: string; language?: string }) => api.patch<ResponseSummary>(`/responses/${id}/`, body),
    onSuccess: (data) => {
      // Merge only what PATCH owns: an answer PUT may still be in flight and its
      // optimistic value must survive a PATCH that raced it on the server.
      qc.setQueryData<ResponseSummary>(keys.response(id), (current) =>
        current ? { ...current, language: data.language, last_question_key: data.last_question_key } : data,
      );
    },
  });
}

/**
 * Autosave one answer (RUN-14). Optimistic cache update, retry with backoff,
 * and the server's cascade result replaces the optimistic state.
 */
export function useSaveAnswer(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ key, value }: { key: string; value: AnswerValue }) => api.put<AnswerResult>(`/responses/${id}/answers/${key}/`, { value }),
    retry: (count, error) => count < 3 && !(error instanceof Error && "status" in error && (error as { status: number }).status < 500),
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 8000),
    onMutate: async ({ key, value }) => {
      await qc.cancelQueries({ queryKey: keys.response(id) });
      const previous = qc.getQueryData<ResponseSummary>(keys.response(id));
      if (previous) qc.setQueryData<ResponseSummary>(keys.response(id), { ...previous, answers: { ...previous.answers, [key]: value }, last_question_key: key });
      return { previous };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.previous) qc.setQueryData(keys.response(id), ctx.previous);
    },
    onSuccess: (result, { key }) => {
      qc.setQueryData<ResponseSummary>(keys.response(id), (current) => {
        if (!current) return current;
        const answers = { ...current.answers, [key]: result.answer.value };
        for (const k of result.invalidated) delete answers[k];
        // A pruned matrix keeps its surviving rows; the server sends them back so the
        // cache is settled here (a refetch could be cancelled by the next save).
        Object.assign(answers, result.pruned);
        return { ...current, answers, visible: result.visible, missing: result.missing, progress: result.progress, last_question_key: key };
      });
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

export function useContact(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (email: string) => api.post<void>(`/responses/${id}/contact/`, { email }),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.response(id) }),
  });
}

/** Identity capture (CON-4): the address goes to the host platform's identity service. */
export function useIdentity(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (email: string) => api.post<void>(`/responses/${id}/identity/`, { email }),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.response(id) }),
  });
}
