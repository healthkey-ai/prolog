import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

export interface ReportVersionRow {
  label: string;
  /** The version these numbers are for; null on the whole-survey row. */
  version: string | null;
  respondents: number;
  completions: number;
  partials: number;
  contacts: number;
  completion_rate: number | null;
  average_response_time: string;
}

export interface ReportStats {
  versions: ReportVersionRow[];
  by_day: { day: string; started: number; completed: number }[];
  by_language: { language: string; respondents: number; completions: number }[];
  drop_off: { question_key: string; label: string; count: number }[];
}

export interface Report {
  survey: string;
  title: string;
  version: string;
  sign_in_available: boolean;
  viewer: { label: string; may_read_responses: boolean; may_read_contacts: boolean } | null;
  stats?: ReportStats;
}

const key = (slug: string) => ["report", slug];

/** The report: the door when nobody is signed in, the numbers when somebody is. */
export function useReport(slug: string) {
  return useQuery({
    queryKey: key(slug),
    queryFn: () => api.get<Report>(`/report/${slug}/`),
    staleTime: 30_000,
    retry: false,
  });
}

export function useReportLogin(slug: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { email: string; password: string }) => api.post<Report>(`/report/${slug}/login/`, body),
    onSuccess: (report) => qc.setQueryData(key(slug), report),
  });
}

export function useReportLogout(slug: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<void>(`/report/${slug}/logout/`),
    onSuccess: () => qc.invalidateQueries({ queryKey: key(slug) }),
  });
}

/**
 * Where a download goes. A plain link, so the browser saves the file the runner
 * streams. One version per file: an answer means what its own version says it
 * means, and two versions need not have the same columns.
 */
export function exportHref(slug: string, kind: "responses" | "contacts", version: string, includeInProgress = false): string {
  const params = new URLSearchParams({ version });
  if (includeInProgress) params.set("include_in_progress", "true");
  return `${import.meta.env.VITE_API_BASE ?? "/api/run"}/report/${slug}/export/${kind}.csv?${params}`;
}
