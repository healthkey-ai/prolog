import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router";
import { exportHref, useReport, useReportLogin, useReportLogout } from "@/api/report";
import { ApiError } from "@/api/client";
import { Decor } from "@/components/Decor";
import { Eyebrow } from "@/components/Eyebrow";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { inputClass } from "@/components/renderers/types";
import { usePageTitle } from "./usePageTitle";

/**
 * A survey's results, in the survey's own clothes: the numbers while fieldwork
 * runs, and the two exports. Who may read them is the deployment's question,
 * not PROlog's — the sign-in below hands the address and password straight to
 * the host and keeps neither.
 */
export function ReportPage() {
  const { slug = "" } = useParams();
  const { t } = useTranslation();
  const report = useReport(slug);
  const login = useReportLogin(slug);
  const logout = useReportLogout(slug);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  usePageTitle(report.data ? t("report.title") : undefined);

  const data = report.data;
  const viewer = data?.viewer ?? null;
  const signInFailed = login.isError && login.error instanceof ApiError && login.error.status === 403;

  return (
    <div className="relative min-h-dvh overflow-hidden bg-ground text-ink">
      <Decor />
      <div className="relative mx-auto max-w-3xl px-6 py-16">
        <Eyebrow>{t("report.eyebrow")}</Eyebrow>
        <h1 className="mt-2 text-[1.8rem] leading-snug">{data?.title ?? t("report.title")}</h1>

        {report.isLoading && <p className="mt-6 text-ink-soft">{t("app.loading")}</p>}
        {report.isError && (
          <p className="mt-6 text-error" role="alert">
            {t("app.error")}
          </p>
        )}

        {data && !viewer && (
          <form
            className="mt-8 flex max-w-sm flex-col gap-4"
            onSubmit={(e) => {
              e.preventDefault();
              login.mutate({ email, password });
            }}
          >
            {!data.sign_in_available ? (
              <p className="text-ink-soft" data-testid="report-no-auth">
                {t("report.noSignIn")}
              </p>
            ) : (
              <>
                <p className="text-ink-soft">{t("report.signInIntro")}</p>
                <div className="flex flex-col gap-1">
                  <Label htmlFor="report-email">{t("report.email")}</Label>
                  <Input id="report-email" type="email" autoComplete="username" className={inputClass} value={email} onChange={(e) => setEmail(e.target.value)} data-testid="report-email" />
                </div>
                <div className="flex flex-col gap-1">
                  <Label htmlFor="report-password">{t("report.password")}</Label>
                  <Input id="report-password" type="password" autoComplete="current-password" className={inputClass} value={password} onChange={(e) => setPassword(e.target.value)} data-testid="report-password" />
                </div>
                {login.isError && (
                  <p className="text-sm text-error" role="alert" data-testid="report-error">
                    {signInFailed ? t("report.signInFailed") : t("app.error")}
                  </p>
                )}
                <Button type="submit" variant="primary" size="runner" disabled={login.isPending || !email || !password} data-testid="report-sign-in">
                  {t("report.signIn")}
                </Button>
              </>
            )}
          </form>
        )}

        {data && viewer && data.stats && (
          <div className="mt-8 flex flex-col gap-10" data-testid="report-body">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-sm text-ink-soft">{t("report.signedInAs", { label: viewer.label })}</p>
              <Button variant="surface" size="runner-sm" onClick={() => logout.mutate()} data-testid="report-sign-out">
                {t("report.signOut")}
              </Button>
            </div>

            <section className="flex flex-col gap-3">
              <h2 className="text-lg">{t("report.downloads")}</h2>
              <p className="text-sm text-ink-soft">{t("report.downloadsNote")}</p>
              <div className="flex flex-wrap gap-3">
                <Button asChild variant="primary" size="runner">
                  <a href={exportHref(slug, "responses")} data-testid="report-download-responses">{t("report.downloadResponses")}</a>
                </Button>
                <Button asChild variant="surface" size="runner">
                  <a href={exportHref(slug, "responses", true)} data-testid="report-download-all">{t("report.downloadAll")}</a>
                </Button>
                {viewer.may_read_contacts && (
                  <Button asChild variant="surface" size="runner">
                    <a href={exportHref(slug, "contacts")} data-testid="report-download-contacts">{t("report.downloadContacts")}</a>
                  </Button>
                )}
              </div>
            </section>

            <Table
              caption={t("report.versions")}
              head={[t("report.version"), t("report.respondents"), t("report.completions"), t("report.partials"), t("report.completionRate"), t("report.averageTime")]}
              rows={data.stats.versions.map((v) => [v.label, v.respondents, v.completions, v.partials, percent(v.completion_rate), v.average_response_time])}
              testId="report-versions"
            />
            <Table
              caption={t("report.byLanguage")}
              head={[t("report.language"), t("report.respondents"), t("report.completions")]}
              rows={data.stats.by_language.map((r) => [r.language, r.respondents, r.completions])}
              empty={t("report.noneYet")}
              testId="report-languages"
            />
            <Table
              caption={t("report.byDay")}
              head={[t("report.day"), t("report.started"), t("report.completed")]}
              rows={data.stats.by_day.map((d) => [d.day, d.started, d.completed])}
              empty={t("report.noneYet")}
              testId="report-days"
            />
            <Table
              caption={t("report.dropOff")}
              note={t("report.dropOffNote")}
              head={[t("report.question"), t("report.responses")]}
              rows={data.stats.drop_off.map((d) => [d.label || d.question_key || t("report.beforeStarting"), d.count])}
              empty={t("report.noneYet")}
              testId="report-dropoff"
            />
          </div>
        )}
      </div>
    </div>
  );
}

function percent(rate: number | null): string {
  return rate === null ? "—" : `${Math.round(rate * 100)}%`;
}

function Table({ caption, note, head, rows, empty, testId }: { caption: string; note?: string; head: string[]; rows: (string | number)[][]; empty?: string; testId: string }) {
  return (
    <section className="flex flex-col gap-2" data-testid={testId}>
      <h2 className="text-lg">{caption}</h2>
      {note && <p className="text-sm text-ink-soft">{note}</p>}
      {rows.length === 0 ? (
        <p className="text-sm text-ink-soft">{empty}</p>
      ) : (
        <div className="overflow-x-auto rounded-[var(--p-radius-card)] bg-surface">
          <table className="w-full border-collapse text-left text-sm">
            <thead>
              <tr>
                {head.map((h) => (
                  <th key={h} scope="col" className="border-b border-border px-4 py-2 font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i}>
                  {row.map((cell, j) => (
                    <td key={j} className="border-b border-border px-4 py-2 tabular-nums last:border-0">
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
