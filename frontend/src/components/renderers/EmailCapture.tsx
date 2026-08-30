import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "../ui/Button";
import { inputClass, type RendererProps } from "./types";
import type { EmailValue } from "@/survey/types";

interface Props extends RendererProps<EmailValue> {
  onSubmitEmail: (email: string) => Promise<void>;
}

/** Contact/identity capture (Q-11, CON-3/4): the address goes to its own endpoint, never into the answer. */
export function EmailCapture({ question, value, onChange, onSubmitEmail, disabled }: Props) {
  const { t } = useTranslation();
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const provided = value?.provided === true;

  const submit = async () => {
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setError(t("email.invalid"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await onSubmitEmail(email);
    } catch {
      setError(t("app.error"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      {question.help && <div className="rounded-[var(--p-radius-card)] bg-tint p-4 text-[0.95rem] text-ink">{question.help as string}</div>}
      {provided ? (
        <p className="text-success" role="status">
          {t("email.saved")}
        </p>
      ) : (
        <>
          <input
            type="email"
            autoComplete="email"
            className={inputClass}
            placeholder={t("email.placeholder")}
            aria-label={question.text as string}
            aria-invalid={Boolean(error)}
            value={email}
            disabled={disabled || busy}
            onChange={(e) => setEmail(e.target.value)}
            data-testid="email-input"
          />
          {error && (
            <p className="text-sm text-error" role="alert">
              {error}
            </p>
          )}
          <div className="flex flex-wrap gap-3">
            <Button onClick={submit} disabled={disabled || busy || !email} data-testid="email-save">
              {t("email.save")}
            </Button>
            <Button variant="secondary" onClick={() => onChange({ provided: false }, { commit: true })} disabled={disabled || busy} data-testid="email-skip">
              {t("email.skip")}
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
