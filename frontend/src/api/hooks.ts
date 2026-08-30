import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { AnswerResult, OptionsSource, ResponseSummary, RunnerDefinition } from "./types";
import type { AnswerValue } from "@/survey/types";

export const keys = {
  definition: (slug: string, lang?: string) => ["definition", slug, lang ?? ""] as const,
  response: (id: string) => ["response", id] as const,
  options: (source: string, lang: string) => ["options", source, lang] as const,
};

export function useSurveyDefinition(slug: string | undefined, lang?: string) {
  return useQuery({
    queryKey: keys.definition(slug ?? "", lang),
    queryFn: () => api.get<RunnerDefinition>(`/surveys/${slug}/${lang ? `?lang=${encodeURIComponent(lang)}` : ""}`),
    enabled: Boolean(slug),
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
    mutationFn: (body: { slug: string; language: string; consent?: { version: string; agreed: boolean } }) =>
      api.post<ResponseSummary>("/responses/", body),
    onSuccess: (data) => qc.setQueryData(keys.response(data.id), data),
  });
}

export function usePatchResponse(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { last_question_key?: string; language?: string }) => api.patch<ResponseSummary>(`/responses/${id}/`, body),
    onSuccess: (data) => qc.setQueryData(keys.response(id), data),
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
        for (const k of result.invalidated) {
          // A pruned matrix keeps a reduced value; a deleted answer disappears. Refetch settles both.
          delete answers[k];
        }
        return { ...current, answers, visible: result.visible, missing: result.missing, progress: result.progress, last_question_key: key };
      });
      if (result.invalidated.length) void qc.invalidateQueries({ queryKey: keys.response(id) });
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
