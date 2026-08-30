import { Navigate, Route, Routes } from "react-router";
import { useTranslation } from "react-i18next";
import { CompletePage } from "./pages/CompletePage";
import { IntroPage } from "./pages/IntroPage";
import { WizardPage } from "./pages/WizardPage";

function Home() {
  const { t } = useTranslation();
  return (
    <main className="mx-auto max-w-[var(--p-content-max)] px-6 py-16">
      <p className="text-xs font-semibold uppercase tracking-wider text-ink-soft">PROlog</p>
      <h1 className="mt-2 text-3xl">{t("app.title")}</h1>
      <p className="mt-4 text-ink-soft">
        Open a survey at <code>/s/&lt;slug&gt;</code>.
      </p>
    </main>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/s/:slug" element={<IntroPage />} />
      <Route path="/s/:slug/q/:key" element={<WizardPage />} />
      <Route path="/s/:slug/complete" element={<CompletePage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
