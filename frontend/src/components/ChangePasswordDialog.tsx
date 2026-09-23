import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ApiError } from "@/api/client";
import { useChangeReportPassword } from "@/api/report";
import { PasswordField } from "@/components/PasswordField";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";

/**
 * A reader changing their own password, so a temporary one an operator set
 * does not have to live on in somebody's message history.
 *
 * Every refusal shown here is the host's own words: its policy — length,
 * reuse, how common the word is — is the only policy there is.
 */
export function ChangePasswordDialog({ slug }: { slug: string }) {
  const { t } = useTranslation();
  const change = useChangeReportPassword(slug);
  const [open, setOpen] = useState(false);
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [mismatch, setMismatch] = useState(false);
  const [done, setDone] = useState(false);

  const reasons =
    change.error instanceof ApiError && Array.isArray(change.error.body?.new_password)
      ? (change.error.body.new_password as string[])
      : change.isError
        ? [t("app.error")]
        : [];

  const reset = () => {
    setCurrent("");
    setNext("");
    setConfirm("");
    setMismatch(false);
    change.reset();
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (!o) {
          reset();
          setDone(false);
        }
      }}
    >
      <DialogTrigger asChild>
        <Button variant="surface" size="runner-sm" data-testid="report-change-password">
          {t("password.change")}
        </Button>
      </DialogTrigger>
      <DialogContent data-testid="report-password-dialog">
        <DialogHeader>
          <DialogTitle>{t("password.change")}</DialogTitle>
        </DialogHeader>
        {done ? (
          <>
            <p className="text-success" role="status" data-testid="report-password-done">
              {t("password.changed")}
            </p>
            <DialogFooter>
              <Button variant="primary" size="runner" onClick={() => setOpen(false)}>
                {t("password.close")}
              </Button>
            </DialogFooter>
          </>
        ) : (
          <form
            className="flex flex-col gap-4"
            onSubmit={(e) => {
              e.preventDefault();
              if (next !== confirm) {
                setMismatch(true);
                return;
              }
              setMismatch(false);
              change.mutate(
                { current_password: current, new_password: next },
                {
                  onSuccess: () => {
                    reset();
                    setDone(true);
                  },
                },
              );
            }}
          >
            <PasswordField label={t("password.current")} value={current} onChange={setCurrent} autoComplete="current-password" testId="report-password-current" />
            <PasswordField label={t("password.new")} value={next} onChange={setNext} autoComplete="new-password" testId="report-password-new" />
            <PasswordField label={t("password.confirm")} value={confirm} onChange={setConfirm} autoComplete="new-password" testId="report-password-confirm" />
            {mismatch && (
              <p className="text-sm text-error" role="alert" data-testid="report-password-mismatch">
                {t("password.mismatch")}
              </p>
            )}
            {reasons.length > 0 && (
              <ul className="flex flex-col gap-1 text-sm text-error" role="alert" data-testid="report-password-error">
                {reasons.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            )}
            <DialogFooter>
              <Button type="submit" variant="primary" size="runner" disabled={change.isPending || !current || !next || !confirm} data-testid="report-password-save">
                {t("password.save")}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
