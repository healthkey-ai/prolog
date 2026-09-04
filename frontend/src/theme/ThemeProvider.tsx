import { createContext, useContext, useEffect, useLayoutEffect, useMemo, useRef, type ReactNode } from "react";
import { useParams, useSearchParams } from "react-router";
import { ApiError } from "@/api/client";
import { useResponse, useSurveyDefinition, useTheme } from "@/api/hooks";
import { clearResponseId, storedResponseId } from "@/lib/storage";
import { applyTheme } from "./applyTheme";
import type { Theme } from "./types";

interface ThemeContextValue {
  theme: Theme | null;
}

const ThemeContext = createContext<ThemeContextValue>({ theme: null });

export function useThemeContext(): ThemeContextValue {
  return useContext(ThemeContext);
}

/**
 * Resolves the survey's theme code from its definition, loads the theme and
 * applies it before rendering the survey pages (THM-3, THM-4).
 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const { slug = "" } = useParams();
  const [search] = useSearchParams();
  const invite = search.get("invite") ?? undefined;
  const responseId = storedResponseId(slug);
  // Same query the pages use (response-bound when one exists, invite otherwise),
  // so invited/account participants are not refused here; fetching the response
  // now lets it run in parallel instead of after the theme.
  const response = useResponse(responseId);
  // A stored id that no longer resolves (purged response, expired account
  // session) must not leave the survey unthemed: fall back to the plain query.
  const stale = response.isError;
  // Wait for the response before asking for its definition: its language is part
  // of the key, so fetching at language "" first would fetch the definition twice.
  const definition = useSurveyDefinition(slug, { lang: response.data?.language, invite, responseId: stale ? undefined : responseId, enabled: !responseId || !response.isPending });
  const code = definition.data?.theme_code;
  const theme = useTheme(code);

  useEffect(() => {
    // 404 only, not the wider "gone" test: a 403 on an account survey is a session
    // problem, and the stored id must survive a re-login to resume that response.
    if (response.error instanceof ApiError && response.error.status === 404) clearResponseId(slug);
  }, [response.error, slug]);

  useLayoutEffect(() => {
    if (theme.data) applyTheme(theme.data);
  }, [theme.data]);

  // Sticky: once the definition (and its theme, if it has one) has settled,
  // the pages stay mounted. A plain "has it settled?" flickers false whenever
  // a query refetches, which unmounts the pages — and remounting them refetches
  // the definition, which flickers it again. On a survey with no active version
  // that loop doubled every round: hundreds of requests a second, and a page
  // that never rendered the "not available" message it had ready.
  const settled = !code ? definition.isError || definition.isSuccess : theme.isSuccess || theme.isError;
  const readyRef = useRef(false);
  if (settled) readyRef.current = true;
  const ready = readyRef.current;
  const value = useMemo(() => ({ theme: theme.data ?? null }), [theme.data]);
  return <ThemeContext.Provider value={value}>{ready ? children : null}</ThemeContext.Provider>;
}
