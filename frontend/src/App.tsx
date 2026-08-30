import { useTranslation } from "react-i18next";

export default function App() {
  const { t } = useTranslation();
  return (
    <main className="mx-auto max-w-[var(--p-content-max)] px-6 py-16">
      <p className="text-xs font-semibold uppercase tracking-wider text-secondary">PROlog</p>
      <h1 className="mt-2 text-3xl">{t("app.title")}</h1>
      <p className="mt-4 text-ink-soft">
        Survey runner. Open a survey at <code>/s/&lt;slug&gt;</code>.
      </p>
    </main>
  );
}
