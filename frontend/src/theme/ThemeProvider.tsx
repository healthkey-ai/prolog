import { createContext, useContext, useEffect, useLayoutEffect, useMemo, type ReactNode } from "react";
import { useParams, useSearchParams } from "react-router";
import { ApiError } from "@/api/client";
import { useResponse, useSurveyDefinition, useTheme } from "@/api/hooks";
import { clearResponseId, storedResponseId } from "@/lib/storage";
import { applyTheme } from "./applyTheme";
import type { Theme } from "./types";

interface ThemeContextValue {
  theme: Theme | null;
  ready: boolean;
}

const ThemeContext = createContext<ThemeContextValue>({ theme: null, ready: true });

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
  const definition = useSurveyDefinition(slug, response.data?.language, invite, stale ? undefined : responseId, { enabled: !responseId || !response.isPending });
  const code = definition.data?.theme_code;
  const theme = useTheme(code);

  useEffect(() => {
    if (response.error instanceof ApiError && response.error.status === 404) clearResponseId(slug);
  }, [response.error, slug]);

  useLayoutEffect(() => {
    if (theme.data) applyTheme(theme.data);
  }, [theme.data]);

  const ready = !code ? definition.isError || definition.isSuccess : theme.isSuccess || theme.isError;
  const value = useMemo(() => ({ theme: theme.data ?? null, ready }), [theme.data, ready]);
  return <ThemeContext.Provider value={value}>{ready ? children : null}</ThemeContext.Provider>;
}
