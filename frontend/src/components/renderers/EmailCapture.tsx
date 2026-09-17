import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useLocation, useParams } from "react-router";
import { useSurveyDefinition } from "@/api/hooks";
import { ApiError } from "@/api/client";
import { storedResponseId } from "@/lib/storage";
import { renderInline } from "@/survey/markdown";
import { forget, recall, remember } from "@/survey/scratch";
import { Alert, AlertDescription } from "../ui/alert";
import { Button } from "../ui/button";
import { Checkbox } from "../ui/checkbox";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { inputClass, type RendererProps } from "./types";
import type { EmailValue } from "@/survey/types";

interface Props extends RendererProps<EmailValue> {
  /** Captures the address; resolves to the receipt a later correction needs (contact capture only). */
  onSubmitEmail: (email: string, consents: string[], receipt?: string) => Promise<string | undefined>;
  /** Removes the captured address (contact capture only); the question stands as declined afterwards. */
  onRemoveEmail: (receipt: string) => Promise<void>;
}

/** What this browser knows of a capture it made: the address as typed, the ticks, and the receipt that lets it correct them. */
interface Captured {
  email: string;
  ticked: string[];
  receipt?: string;
}

/** Contact/identity capture (Q-11, CON-3/4): the address goes to its own endpoint, never into the answer. */
export function EmailCapture({ question, value, onChange, onSubmitEmail, onRemoveEmail }: Props) {
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
  // The server never returns an address, so what this screen can show after a
  // capture is what this browser typed — kept in memory only (see scratch.ts):
  // gone on reload, and never in browser storage. The unsaved draft likewise
  // survives a detour to the notice.
  const responseId = storedResponseId(slug) ?? slug;
  const draftKey = `capture:${responseId}:${question.key}`;
  const capturedKey = `captured:${responseId}:${question.key}`;
  const draft = recall<Captured>(draftKey);
  const [captured, setCaptured] = useState<Captured | undefined>(() => recall<Captured>(capturedKey));
  const [email, setEmail] = useState(draft?.email ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // The consents offered with the address (CON-3/4), each its own tick box,
  // none pre-ticked: a consent is something the participant does, not
  // something they fail to undo.
  const consents = question.config?.consents ?? [];
  const consentsMin = question.config?.consents_min ?? 0;
  const consentsNote = (question.config?.consents_note as string | undefined) ?? "";
  // The note is where a deployment puts its own link to the notice; a second
  // link to the same page under the buttons would only be noise.
  const noteLinksPrivacy = consents.length > 0 && /\]\(privacy\)/.test(consentsNote);
  const [ticked, setTicked] = useState<string[]>(draft?.ticked ?? []);
  const [consentError, setConsentError] = useState(false);
  const provided = value?.provided === true;
  // Correcting a saved address: the form again, filled with what was saved.
  // Only contact capture can be corrected — the receipt opens the contact
  // row; an identity is the host's account, changed there.
  const [editing, setEditing] = useState(false);
  const correctable = Boolean(captured?.receipt) && !question.config?.link_identity;
  useEffect(() => {
    if (email || ticked.length) remember(draftKey, { email, ticked });
    else forget(draftKey);
  }, [draftKey, email, ticked]);

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
      const keys = consents.map((c) => c.key).filter((k) => ticked.includes(k));
      const receipt = await onSubmitEmail(email, keys, editing ? captured?.receipt : undefined);
      const done = { email, ticked: keys, receipt };
      remember(capturedKey, done);
      setCaptured(done);
      setEditing(false);
      forget(draftKey);
    } catch (err) {
      // The address never reaches the answer; the endpoint's status says what went wrong.
      const status = err instanceof ApiError ? err.status : 0;
      setError(t(status === 503 ? "email.unavailable" : status === 429 ? "app.throttled" : "app.error"));
    } finally {
      setBusy(false);
    }
  };

  const startEditing = () => {
    setEmail(captured?.email ?? "");
    setTicked(captured?.ticked ?? []);
    setError(null);
    setConsentError(false);
    setEditing(true);
  };

  const remove = async () => {
    if (!captured?.receipt) return;
    setBusy(true);
    setError(null);
    try {
      await onRemoveEmail(captured.receipt);
      forget(capturedKey);
      forget(draftKey);
      setCaptured(undefined);
      setEmail("");
      setTicked([]);
    } catch (err) {
      const status = err instanceof ApiError ? err.status : 0;
      setError(t(status === 429 ? "app.throttled" : "app.error"));
    } finally {
      setBusy(false);
    }
  };

  const decline = () => {
    forget(draftKey);
    onChange({ provided: false }, { commit: true, advance: true });
  };

  return (
    <div className="flex flex-col gap-4">
      {question.help && (
        <Alert role="note" className="bg-accent [&>svg]:hidden">
          <AlertDescription className="text-[0.95rem] text-foreground">{question.help as string}</AlertDescription>
        </Alert>
      )}
      {provided && !editing ? (
        <div className="flex flex-col gap-3">
          <p className="text-success" role="status">
            {t("email.saved")}
          </p>
          {captured && (
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2" data-testid="email-captured">
              <span className="text-[0.95rem]">
                <span className="text-ink-soft">{t("email.savedAs")}</span> <span className="font-medium">{captured.email}</span>
              </span>
              {correctable && (
                <>
                  <Button variant="surface" size="runner-sm" onClick={startEditing} disabled={busy} data-testid="email-change">
                    {t("email.change")}
                  </Button>
                  <Button variant="link" size="runner-sm" className="text-error" onClick={remove} disabled={busy} data-testid="email-remove">
                    {t("email.remove")}
                  </Button>
                </>
              )}
            </div>
          )}
          {error && (
            <Alert variant="destructive" role="alert" className="[&>svg]:hidden">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
        </div>
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
              {consentsNote && (
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
            {editing ? (
              <Button variant="surface" size="runner" onClick={() => setEditing(false)} disabled={busy} data-testid="email-cancel">
                {t("email.cancel")}
              </Button>
            ) : (
              <Button variant="surface" size="runner" onClick={decline} disabled={busy} data-testid="email-skip">
                {t("email.skip")}
              </Button>
            )}
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
