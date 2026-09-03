# The survey administration console — a design

> **Status:** proposed, 2026-09-03. For review before any of it is built.
>
> **Artifacts this describes:** [`administration.md`](administration.md) — the same tasks, done from a terminal · [`definitions/survey-definition.md`](definitions/survey-definition.md) — what a definition contains · [`../schema/survey-definition.schema.json`](../schema/survey-definition.schema.json) — what it is verified against · [`deployment.md`](deployment.md) — where definitions are mounted

Everything an administrator does today needs a shell: `validate_definition`, `load_definition`, `--activate`, `export_responses`. That is workable for one instrument, run by whoever deployed it. It does not work for a deployment running several, administered by people who do not have — and should not need — a terminal on a production host.

This is a console for exactly that, and no more.

## What it is for

| | |
| --- | --- |
| **Create** | upload a definition, or pick one the deployment has mounted, and load it |
| **Verify** | validate a definition against the schema, writing nothing |
| **Publish** | activate a draft; archive what it replaces |
| **Delete** | remove a survey that has nothing to lose |
| **Point at the source** | show which definition file and which schema this instrument came from and is checked against |

**Not** a survey builder. Definitions are authored as files and reviewed like code — diffable, revertible, and testable before anyone answers them. A browser question editor is a different product, and it would spend its life fighting the rules that make a version trustworthy.

**Not** audience management. Who a survey is for is the host's question, not the runner's, and it is out of scope here.

---

## 1. A version is immutable; the console has to be honest about that

A response records *which version it answered*. A published version therefore cannot change, and the loader refuses to re-load one whose content differs. The console must not offer an Edit button that turns out to mean "create a new version" — it should say what it does:

```
upload → verify → draft → active → archived
```

Editing wording or structure is uploading a new version. Changing a theme or an effective date is not, and can be offered directly.

## 2. Delete, and why it is safe here

`SurveyVersion.survey` and `SurveyResponse.survey_version` are both `PROTECT`. A survey with versions, or a version with responses, **cannot** be deleted — the database refuses before any code does. That is the right default and the console keeps it:

| State | Delete |
| --- | --- |
| Draft, never activated, no responses | allowed |
| Has responses | **refused**, with the count and where to export them |
| Archived with responses | refused; archived already means "kept, not offered" |

The console surfaces the refusal as a **reason**, not a stack trace: *"3,412 responses are bound to this survey. Export them first; deleting it would destroy what people told you."* No force flag in the UI. A deployment that genuinely wants the data gone has `purge_abandoned_responses`, an export, and a database — all deliberate, none of them a button next to a list.

## 3. Where a definition comes from

Two sources, because deployments differ:

- **Upload** a JSON file from the browser. The common case, and the one that needs no shell.
- **Pick a mounted file** from `PROLOG_DEFINITION_DIRS`. A deployment that ships definitions in its image already has them on disk; re-uploading a copy invites the two drifting apart.

Either way the console shows **what it is verifying against**: the schema at `PROLOG_SCHEMA_DIR`, its `schema_version`, and a link to read it. "Valid" means nothing to an administrator who cannot see what it was checked against — and a deployment may be running an older runner than the definition was written for, which is exactly when that matters.

## 4. Verify writes nothing

The verify step calls the same `validate_definition` the command does, and persists nothing at all. It reports what the validator distinguishes:

- **Errors** refuse the file. Every error, not the first: fixing them is a loop, and a loop of one-at-a-time is a bad afternoon.
- **Warnings** do not refuse it — an option nothing can select, a language still machine-translated. They are the things that are legal and probably not meant.

Before anything is written, the console says what *would* happen: whether this is a new instrument or a new version of one that exists, its slug and version, and — if that version already exists with different content — that loading it will be refused, because a published version is immutable.

Loading always produces a **draft**. Activation is a separate press, as `--activate` is a separate flag.

## 5. Activation says what it costs

A confirmation that names consequences rather than asking whether you are sure: which version becomes active, which one is archived by it, whether the non-default languages are reviewed, and whether the instrument is inside its effective window.

Activating with unreviewed machine translations stays refused unless the deployment has opted in (`PROLOG_MACHINE_LANGUAGES`), and then the confirmation says respondents will see the disclosure.

## 6. Who is an administrator

The runner does not know. In the standalone profile it is a Django staff user; in the integrated profile the host has its own idea — roles, organisations, trust — and the runner must not reimplement it.

So the same shape as the participant resolver: **`PROLOG_ADMIN_PERMISSION`**, a dotted path to a DRF permission class, defaulting to `rest_framework.permissions.IsAdminUser`. A host sets it to its own; PROlog asks it and takes the answer. No permission model in this repository beyond "the deployment says who".

## 7. Where it lives

The console is part of the runner's own front end — same build, same theme, no second application to deploy — under **`/s/manage`**:

- it works in both profiles unchanged, because the integrated host already routes `/s/…` to the runner and needs no new mount;
- React Router ranks a static segment above a dynamic one, so `/s/manage` wins over `/s/:slug` — worth a test rather than a comment, since a survey slugged `manage` would otherwise be unreachable.

The API is a new tree beside the runner's, guarded by `PROLOG_ADMIN_PERMISSION`:

| | |
| --- | --- |
| `GET /api/admin/surveys/` | instruments, their active version, response counts |
| `GET /api/admin/surveys/<slug>/` | versions, sources, response summary |
| `GET /api/admin/definitions/` | files mounted in `PROLOG_DEFINITION_DIRS` |
| `GET /api/admin/schema/` | the schema being validated against |
| `POST /api/admin/surveys/verify/` | issues out, **nothing written** |
| `POST /api/admin/surveys/` | load as a draft |
| `POST /api/admin/surveys/<slug>/versions/<version>/activate/` | |
| `POST /api/admin/surveys/<slug>/versions/<version>/archive/` | |
| `DELETE /api/admin/surveys/<slug>/` | refused while anything depends on it |
| `GET /api/admin/surveys/<slug>/responses.csv` | the existing export over HTTP |
| `GET /api/admin/surveys/<slug>/translations.csv?language=es` | the review sheet |

The participant-facing `/api/run/…` tree is untouched. It is `AllowAny` by design and must not grow an endpoint that assumes otherwise.

## 8. Decisions to settle before building

1. **Does the console need the response *data*, or only counts?** Counts and a CSV download are cheap and answer most questions. Rendering individual responses in a browser puts patient-entered free text on a screen with a different audience from the export, and deserves its own thought.
2. **Should deleting a *draft* be allowed to cascade its questions and options?** They are `CASCADE` already, so it works; the question is whether the UI should say so.
3. **One console for many deployments?** This assumes one deployment, one console, at its own origin. A multi-tenant console is the host's product, not the runner's.
4. **Invitations and repeat administrations** exist in the engine and are not in this design. Worth deciding whether the console ever covers "invite these people on this date", or stays a library of instruments.
