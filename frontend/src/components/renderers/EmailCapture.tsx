import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Alert, AlertDescription } from "../ui/alert";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { inputClass, type RendererProps } from "./types";
import type { EmailValue } from "@/survey/types";

interface Props extends RendererProps<EmailValue> {
  onSubmitEmail: (email: string) => Promise<void>;
  /** Decline: records {provided: false} and moves on. */
  onDecline?: () => void;
}

/** Contact/identity capture (Q-11, CON-3/4): the address goes to its own endpoint, never into the answer. */
export function EmailCapture({ question, value, onChange, onSubmitEmail, onDecline, disabled }: Props) {
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
      {question.help && (
        <Alert role="note" className="bg-accent [&>svg]:hidden">
          <AlertDescription className="text-[0.95rem] text-foreground">{question.help as string}</AlertDescription>
        </Alert>
      )}
      {provided ? (
        <p className="text-success" role="status">
          {t("email.saved")}
        </p>
      ) : (
        <>
          <Input
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
            <Alert variant="destructive" role="alert" className="[&>svg]:hidden">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
          <div className="flex flex-wrap gap-3">
            <Button variant="primary" size="runner" onClick={submit} disabled={disabled || busy || !email} data-testid="email-save">
              {t("email.save")}
            </Button>
            <Button variant="surface" size="runner" onClick={() => (onDecline ? onDecline() : onChange({ provided: false }, { commit: true }))} disabled={disabled || busy} data-testid="email-skip">
              {t("email.skip")}
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
