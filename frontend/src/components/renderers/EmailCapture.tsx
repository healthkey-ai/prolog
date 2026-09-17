import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useLocation, useParams } from "react-router";
import { useSurveyDefinition } from "@/api/hooks";
import { ApiError } from "@/api/client";
import { renderInline } from "@/survey/markdown";
import { forget, recall, remember } from "@/survey/scratch";
import { storedResponseId } from "@/lib/storage";
import { Alert, AlertDescription } from "../ui/alert";
import { Button } from "../ui/button";
import { Checkbox } from "../ui/checkbox";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { inputClass, type RendererProps } from "./types";
import type { EmailValue } from "@/survey/types";

interface Props extends RendererProps<EmailValue> {
  onSubmitEmail: (email: string, consents: string[]) => Promise<void>;
}

/** Contact/identity capture (Q-11, CON-3/4): the address goes to its own endpoint, never into the answer. */
export function EmailCapture({ question, value, onChange, onSubmitEmail }: Props) {
  const { t } = useTranslation();
  // The notice belongs on this screen more than anywhere else: this is where
  // somebody decides whether to hand over an address, and it opens on this
  // origin, so their place in the survey survives reading it.
  const { slug = "" } = useParams();
  const definition = useSurveyDefinition(slug);
  const legalKeys = definition.data?.legal_pages ?? [];
  const hasPrivacy = legalKeys.includes("privacy");
  // Opened from here, the notice comes back here (LegalPage reads `from`).
  const location = useLocation();
  const legalPages = { keys: legalKeys, href: (page: string) => `/s/${slug}/${page}`, from: location.pathname };
  // Reading the notice must not cost the participant what they had typed or
  // ticked: the unsaved state outlives this screen, in memory only.
  const scratchKey = `capture:${storedResponseId(slug) ?? slug}:${question.key}`;
  const draft = recall<{ email: string; ticked: string[] }>(scratchKey);
  const [email, setEmail] = useState(draft?.email ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // The consents offered with the address (CON-3/4), each its own tick box,
  // none pre-ticked: a consent is something the participant does, not
  // something they fail to undo.
  const consents = question.config?.consents ?? [];
  const consentsNote = (question.config?.consents_note as string | undefined) ?? "";
  // The note is where a deployment puts its own link to the notice; a second
  // link to the same page under the buttons would only be noise.
  const noteLinksPrivacy = consents.length > 0 && /\]\(privacy\)/.test(consentsNote);
  const consentsMin = question.config?.consents_min ?? 0;
  const [ticked, setTicked] = useState<string[]>(draft?.ticked ?? []);
  const [consentError, setConsentError] = useState(false);
  const provided = value?.provided === true;
  useEffect(() => {
    if (email || ticked.length) remember(scratchKey, { email, ticked });
    else forget(scratchKey);
  }, [scratchKey, email, ticked]);

  const submit = async () => {
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setError(t("email.invalid"));
      return;
    }
    if (ticked.length < consentsMin) {
      setConsentError(true);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      // In the question's order, whatever order the boxes were ticked in.
      await onSubmitEmail(
        email,
        consents.map((c) => c.key).filter((k) => ticked.includes(k)),
      );
      forget(scratchKey);
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
          {consents.length > 0 && (
            <fieldset className="flex flex-col gap-1" data-testid="email-consents">
              {question.config?.consents_label && (
                <legend className="mb-1 text-[0.95rem]" data-testid="email-consents-label">
                  {question.config.consents_label as string}
                </legend>
              )}
              {consents.map((c) => {
                const id = `consent-${c.key}`;
                return (
                  <div key={c.key} className="flex min-h-[44px] items-start gap-3">
                    <Checkbox
                      id={id}
                      className="mt-3 size-5"
                      checked={ticked.includes(c.key)}
                      disabled={busy}
                      onCheckedChange={(on) => {
                        setTicked((prev) => (on === true ? [...prev, c.key] : prev.filter((k) => k !== c.key)));
                        setConsentError(false);
                      }}
                      data-testid={`email-consent-${c.key}`}
                    />
                    <Label htmlFor={id} className="flex min-h-[44px] items-center text-[0.95rem] font-normal leading-snug">
                      {c.text as string}
                    </Label>
                  </div>
                );
              })}
              {question.config?.consents_note && (
                <p className="text-sm text-muted-foreground" data-testid="email-consents-note">
                  {renderInline(consentsNote, "consents-note", { legalPages })}
                </p>
              )}
              {consentError && (
                <p className="text-sm text-error" role="alert" data-testid="email-consents-error">
                  {t("email.consentsRequired")}
                </p>
              )}
            </fieldset>
          )}
          {error && (
            <Alert variant="destructive" role="alert" className="[&>svg]:hidden">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
          <div className="flex flex-wrap gap-3">
            <Button variant="primary" size="runner" onClick={submit} disabled={busy || !email} data-testid="email-save">
              {t("email.save")}
            </Button>
            <Button
              variant="surface"
              size="runner"
              onClick={() => {
                forget(scratchKey);
                onChange({ provided: false }, { commit: true, advance: true });
              }}
              disabled={busy}
              data-testid="email-skip"
            >
              {t("email.skip")}
            </Button>
          </div>
          {hasPrivacy && !noteLinksPrivacy && (
            <Link to={`/s/${slug}/privacy`} state={{ from: location.pathname }} className="text-sm text-primary underline" data-testid="email-privacy-link">
              {t("legal.privacy")}
            </Link>
          )}
        </>
      )}
    </div>
  );
}
