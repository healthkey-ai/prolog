import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router";
import { useSurveyDefinition } from "@/api/hooks";
import { ApiError } from "@/api/client";
import { Alert, AlertDescription } from "../ui/alert";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { inputClass, type RendererProps } from "./types";
import type { EmailValue } from "@/survey/types";

interface Props extends RendererProps<EmailValue> {
  onSubmitEmail: (email: string) => Promise<void>;
}

/** Contact/identity capture (Q-11, CON-3/4): the address goes to its own endpoint, never into the answer. */
export function EmailCapture({ question, value, onChange, onSubmitEmail }: Props) {
  const { t } = useTranslation();
  // The notice belongs on this screen more than anywhere else: this is where
  // somebody decides whether to hand over an address, and it opens on this
  // origin, so their place in the survey survives reading it.
  const { slug = "" } = useParams();
  const definition = useSurveyDefinition(slug);
  const hasPrivacy = definition.data?.legal_pages?.includes("privacy") ?? false;
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
    } catch (err) {
      // The address never reaches the answer; the endpoint's status says what went wrong.
      const status = err instanceof ApiError ? err.status : 0;
      setError(t(status === 503 ? "email.unavailable" : status === 429 ? "app.throttled" : "app.error"));
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
            disabled={busy}
            onChange={(e) => setEmail(e.target.value)}
            data-testid="email-input"
          />
          {error && (
            <Alert variant="destructive" role="alert" className="[&>svg]:hidden">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
          <div className="flex flex-wrap gap-3">
            <Button variant="primary" size="runner" onClick={submit} disabled={busy || !email} data-testid="email-save">
              {t("email.save")}
            </Button>
            <Button variant="surface" size="runner" onClick={() => onChange({ provided: false }, { commit: true, advance: true })} disabled={busy} data-testid="email-skip">
              {t("email.skip")}
            </Button>
          </div>
          {hasPrivacy && (
            <Link to={`/s/${slug}/privacy`} className="text-sm text-primary underline" data-testid="email-privacy-link">
              {t("legal.privacy")}
            </Link>
          )}
        </>
      )}
    </div>
  );
}
