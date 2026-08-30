import { useTranslation } from "react-i18next";

export function Unsupported({ type }: { type: string }) {
  const { t } = useTranslation();
  return (
    <p className="rounded-[var(--p-radius-card)] border border-error/40 bg-surface p-4 text-error" role="alert">
      {t("unsupported")} ({type})
    </p>
  );
}
