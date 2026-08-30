import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router";
import "./i18n";
import "./styles/app.css";
import App from "./App";
import { isTerminal } from "./api/client";

const queryClient = new QueryClient({
  // One retry for transient failures; a definitive 4xx (gone, closed,
  // forbidden, throttled) goes straight to the page that explains it.
  defaultOptions: { queries: { retry: (count, error) => count < 1 && !isTerminal(error), refetchOnWindowFocus: false } },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
