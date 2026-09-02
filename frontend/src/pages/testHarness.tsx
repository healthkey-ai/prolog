/**
 * Test-only harness for the runner pages (vitest + jsdom, no testing-library):
 * a stubbed `fetch` that plays the API, fixtures for a small definition and
 * response, and a mount that renders the routes under the providers a page
 * expects. The pages are exercised through the real hooks, router and
 * i18next, so the failure paths tested here are the ones a participant hits.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, createElement, type ReactElement, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from "react-router";
import { vi } from "vitest";
import i18n from "@/i18n";
import type { ResponseSummary, RunnerDefinition } from "@/api/types";
import { CompletePage } from "./CompletePage";
import { IntroPage } from "./IntroPage";
import { WizardPage } from "./WizardPage";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

export const SLUG = "test-survey";
export const RESPONSE_ID = "r1";

export function definition(overrides: Partial<RunnerDefinition> = {}): RunnerDefinition {
  return {
    slug: SLUG,
    version: "1",
    default_language: "en",
    languages: ["en", "fr"],
    title: "Example instrument",
    language: "en",
    theme_code: "default",
    presentation: { section_interstitials: false },
    sections: [
      {
        key: "s1",
        title: "First part",
        questions: [
          { key: "q1", type: "text", text: "Optional note", required: false },
          { key: "q2", type: "text", text: "Required note" },
        ],
      },
      {
        key: "s2",
        title: "Second part",
        description: "About the second part",
        questions: [
          {
            key: "q3",
            type: "single",
            text: "Pick one",
            options: [
              { key: "a", label: "A" },
              { key: "b", label: "B" },
            ],
          },
        ],
      },
    ],
    ...overrides,
  };
}

export function response(overrides: Partial<ResponseSummary> = {}): ResponseSummary {
  return {
    id: RESPONSE_ID,
    slug: SLUG,
    version: "1",
    language: "en",
    status: "in_progress",
    started_at: "2026-01-01T00:00:00Z",
    submitted_at: null,
    last_question_key: "q1",
    administration: null,
    answers: {},
    visible: ["q1", "q2", "q3"],
    missing: ["q2", "q3"],
    progress: { answered: 0, total: 3 },
    ...overrides,
  };
}

export interface Reply {
  status?: number;
  body?: unknown;
}
export interface Call {
  method: string;
  path: string;
  body: unknown;
}
type Handler = (call: Call, count: number) => Reply | Promise<Reply>;

/** The stubbed API: routes matched by method and path (string prefix or RegExp), last registered wins. */
export function fakeServer() {
  const routes: { method: string; path: string | RegExp; handler: Handler; count: number }[] = [];
  const calls: Call[] = [];
  const on = (method: string, path: string | RegExp, handler: Handler | Reply) => {
    routes.unshift({ method, path, handler: typeof handler === "function" ? handler : () => handler, count: 0 });
  };
  const match = (call: Call) =>
    routes.find((r) => r.method === call.method && (typeof r.path === "string" ? call.path.startsWith(r.path) : r.path.test(call.path)));
  vi.stubGlobal("fetch", async (input: string | URL | Request, init?: RequestInit): Promise<Response> => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const path = url.replace(/^\/api\/run/, "");
    const call: Call = { method: init?.method ?? "GET", path, body: init?.body ? JSON.parse(String(init.body)) : undefined };
    calls.push(call);
    const route = match(call);
    const reply = route ? await route.handler(call, ++route.count) : { status: 404, body: { detail: "not found" } };
    const status = reply.status ?? 200;
    return new Response(status === 204 ? null : JSON.stringify(reply.body ?? {}), { status, headers: { "Content-Type": "application/json" } });
  });
  /** The calls of one method (and path prefix) so far. */
  const of = (method: string, prefix = "") => calls.filter((c) => c.method === method && c.path.startsWith(prefix));
  return { on, calls, of };
}

/** A promise the test settles by hand (a request the server has not answered yet). */
export function deferred<T = Reply>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

/** A server that serves the fixture definition and response for the wizard. */
export function runnerServer(def: RunnerDefinition = definition(), res: ResponseSummary = response()) {
  const server = fakeServer();
  server.on("GET", `/surveys/${SLUG}/`, { body: def });
  server.on("GET", `/responses/${RESPONSE_ID}/`, { body: res });
  server.on("PATCH", `/responses/${RESPONSE_ID}/`, (call) => ({ body: { ...res, ...(call.body as object) } }));
  return server;
}

let probe: { pathname: string; navigate: (to: string) => void } = { pathname: "", navigate: () => undefined };
function LocationProbe() {
  const location = useLocation();
  const navigate = useNavigate();
  probe = { pathname: location.pathname, navigate };
  return null;
}

/** The runner's routes, with stand-ins where a page under test navigates away. */
export function runnerRoutes(): ReactElement {
  return createElement(
    Routes,
    null,
    createElement(Route, { path: "/s/:slug", element: createElement(IntroPage) }),
    createElement(Route, { path: "/s/:slug/q/:key", element: createElement(WizardPage) }),
    createElement(Route, { path: "/s/:slug/complete", element: createElement(CompletePage) }),
  );
}

export interface Mounted {
  container: HTMLElement;
  /** Let pending promises, effects and (with fake timers) due timers run. */
  flush: (rounds?: number) => Promise<void>;
  pathname: () => string;
  /** Navigate like the browser's history would (outside the page's own Back / Next). */
  navigate: (to: string) => Promise<void>;
  unmount: () => void;
  $: <T extends HTMLElement = HTMLElement>(testId: string) => T | null;
  /** Like `$`, but searches the whole document: Radix portals (dialogs, popovers) render outside the container. */
  $doc: <T extends HTMLElement = HTMLElement>(testId: string) => T | null;
  /**
   * Flush until `testId` appears, or fail saying what never arrived.
   *
   * A renderer is code-split, so how many flushes it takes to arrive depends on
   * how fast the machine resolves its chunk — a fixed count passes locally and
   * fails on a slower CI runner.
   */
  until: <T extends HTMLElement = HTMLElement>(testId: string, rounds?: number) => Promise<T>;
  text: () => string;
}

export function mount(path: string, element: ReactNode = runnerRoutes()): Mounted {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() =>
    root.render(
      createElement(
        QueryClientProvider,
        { client: qc },
        createElement(MemoryRouter, { initialEntries: [path] }, createElement(LocationProbe), element),
      ),
    ),
  );
  const flush = async (rounds = 4) => {
    for (let i = 0; i < rounds; i++) {
      await act(async () => {
        if (vi.isFakeTimers()) await vi.advanceTimersByTimeAsync(0);
        else await new Promise((r) => setTimeout(r, 0));
      });
    }
  };
  return {
    container,
    flush,
    pathname: () => probe.pathname,
    navigate: async (to) => {
      act(() => probe.navigate(to));
      await flush();
    },
    unmount: () => {
      act(() => root.unmount());
      container.remove();
    },
    $: (testId) => container.querySelector(`[data-testid="${testId}"]`),
    $doc: (testId) => document.body.querySelector(`[data-testid="${testId}"]`),
    until: async <T extends HTMLElement = HTMLElement>(testId: string, rounds = 40) => {
      for (let i = 0; i < rounds; i++) {
        const found = container.querySelector<T>(`[data-testid="${testId}"]`);
        if (found) return found;
        await flush(1);
      }
      throw new Error(`"${testId}" never appeared after ${rounds} flushes`);
    },
    text: () => container.textContent ?? "",
  };
}

/** jsdom lacks matchMedia (the overview sheet asks for it). */
export function installDom() {
  window.matchMedia ??= (query: string) =>
    ({ matches: false, media: query, onchange: null, addEventListener: () => undefined, removeEventListener: () => undefined, addListener: () => undefined, removeListener: () => undefined, dispatchEvent: () => false }) as MediaQueryList;
  localStorage.setItem(`prolog:response:${SLUG}`, RESPONSE_ID);
}

/** Type into a controlled input the way React sees it (native setter + input event). */
export function type(input: HTMLInputElement | HTMLTextAreaElement, value: string) {
  const proto = input instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, "value")!.set!.call(input, value);
  act(() => {
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

export function blur(el: HTMLElement) {
  act(() => {
    el.dispatchEvent(new FocusEvent("focusout", { bubbles: true }));
  });
}

export function click(el: HTMLElement | null) {
  if (!el) throw new Error("nothing to click");
  act(() => {
    el.click();
  });
}

export const t = (key: string, opts?: Record<string, unknown>) => i18n.t(key, opts);
