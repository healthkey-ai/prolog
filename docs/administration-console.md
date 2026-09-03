# The survey administration console — a design

> **Status:** partly built, 2026-09-03. §2.1 (verify and load) and §2.2's
> Publish action are done, and so is the removal of the data admins.
> Activate/archive actions, the delete guard and the export actions are not.
>
> **Artifacts this describes:** [`administration.md`](administration.md) — the same tasks, done from a terminal · [`../backend/prolog_surveys/admin.py`](../backend/prolog_surveys/admin.py) — what already exists · [`definitions/survey-definition.md`](definitions/survey-definition.md) — what a definition contains · [`../schema/survey-definition.schema.json`](../schema/survey-definition.schema.json) — what it is verified against

Everything an administrator does today needs a shell: `validate_definition`, `load_definition`, `--activate`, `export_responses`. That is workable for one instrument run by whoever deployed it, and not for a deployment running several, administered by people who should not need a terminal on a production host.

**Build it in Django admin.** The app already registers one, it already appears inside a host that installs the app, and it already gets the parts that are tedious and easy to get wrong — authentication, permissions, lists, filters, search, delete confirmation — for nothing.

---

## 1. Most of it already exists

`prolog_surveys/admin.py` registers Survey, SurveyQuestion, SurveyResponse, SurveyContact, SurveyConsent and SurveyInvitation, and it is already written defensively:

| | |
| --- | --- |
| Contacts and consents | read-only — `ReadOnlyMixin` refuses add and change |
| Questions and responses | **not registered at all.** Questions are the definition's, and a second view of them is one nobody validated; responses belong to the API and the exports, whose audience is not an administrator's |
| `SurveyVersion` | **not registered on its own**; visible only as a read-only inline, so the `definition` JSON cannot be edited into a shape the validator never saw |
| Survey's loader-owned fields | `slug`, `title`, `theme_code`, `allow_anonymous_participation` become read-only once the row exists: the loader rewrites them on every load, so an edit here would drift until the next load silently reverted it |
| Contact addresses | deliberately absent from list views |

A host that installs the app gets all of this at `/admin/prolog_surveys/…` with no work — which is exactly how PRomop got it.

So this design is not "build a console". It is **four additions to one that is already there**, and a rule about what must never become editable.

## 2. What to add

### 2.1 Load a definition — a custom admin view  ✅ built

A button on the Survey changelist, **Verify and load a definition**, opening a form with two ways in:

- **upload** a JSON file, or
- **pick one the deployment already mounts** in `PROLOG_DEFINITION_DIRS` — a deployment that ships definitions in its image should not have to upload a second copy that then drifts from the first.

The form posts to a view that **verifies before it writes anything**, and shows:

- **errors**, which refuse the file — all of them, not the first, because fixing them is a loop;
- **warnings**, which do not — an option nothing can select, a language still machine-translated;
- **what would happen**: new instrument or new version of an existing one, its slug and version; where that version already exists with different content, either the confirmation described in §2.2 (it is unpublished, so its responses are test data) or a refusal (it is published, so its content is final);
- **which schema it was checked against**, with its `schema_version` and a link. "Valid" means little to an administrator who cannot see what it was checked against, and a deployment can be running an older runner than the definition was written for.

Loading always produces a **draft**. Activation is a separate act, as `--activate` is a separate flag.

### 2.2 Publish — an action on the version's row  ✅ built

A version's content stays re-loadable until it is **published**, and publishing
is its own act because it is the irreversible one. The **Content** column on
the survey's page says which state a version is in and carries the action:

- *re-loadable until then*, with a **Publish…** link — the definition can be
  loaded over it again, and the responses against it are test data;
- *Published 2026-09-03 14:02 — frozen*, or *Archived — frozen*.

Two screens follow from that:

- **Publish…** confirms first, and says what it costs: a changed file will be
  refused from now on, the responses stop being test data, and it cannot be
  undone. It neither activates nor deactivates anything.
- **Loading over a version that has responses** is a question, not a refusal:
  the page says how many there are and how many were submitted, and offers
  *Discard N responses and load* beside the ordinary Load. A published version
  is not offered it at all.

The command line does the same two things: `--discard-responses` on
`load_definition`, and `publish_version <slug>`.

### 2.3 Activate and archive — admin actions  *(not built)*

Register `SurveyVersion` as a **read-only** ModelAdmin — list only, no add, no change — carrying two actions:

- **Activate** — with a confirmation naming what it costs: which version this archives, whether the non-default languages are reviewed, whether the instrument is inside its effective window. Unreviewed machine translations stay refused unless the deployment opted in (`PROLOG_MACHINE_LANGUAGES`), and then the confirmation says respondents will see the disclosure.
- **Archive** — kept and readable, no longer offered.

Actions rather than an editable `status` field: the transitions have rules (one active version per survey, an archived version cannot be re-activated, a serialising lock) that live in `activate_version`. A dropdown on a form would let somebody set a status the engine would never have set.

### 2.4 Delete — already safe, and it should say why  *(not built)*

`SurveyVersion.survey` and `SurveyResponse.survey_version` are both `PROTECT`: a survey with versions, or a version with responses, cannot be deleted. The database refuses before any code does, which is the right default.

What Django gives by default is a protected-objects error page listing rows. Better: `has_delete_permission` returns False once responses exist, so the button is absent rather than present-and-failing, and the change page says why — *"3,412 responses are bound to this survey. Export them first; deleting it would destroy what people told you."*

No force flag. A deployment that genuinely wants the data gone has an export, `purge_abandoned_responses` and a database; none of those is a button beside a list.

### 2.5 Exports — actions that download  *(not built)*

`Export responses`, `Export contacts` and `Export translations` as actions returning the CSV the management commands already produce. The two response exports stay separate, as they are on the command line: the response export never contains an address, and the contact export never contains an answer.

## 3. The rule that matters more than the screens

**Nothing that a respondent's answers are interpreted against may become editable here.** A version's `definition`, a question's text or type, an option's key: all reachable through a badly-configured ModelAdmin, and all of them would let somebody produce an instrument the validator never saw and the engines disagree about.

The current admin gets this right, and the additions must not undo it. It is worth a test — a check that `SurveyVersion` has no add or change permission and that `SurveyAdmin.get_readonly_fields` covers the loader-owned set — because it is the kind of thing a later convenience change breaks without anyone noticing.

## 4. Who is an administrator

Django's own: `is_staff`, plus the per-model permissions. Nothing new in this repository.

That is the same answer in both profiles, and it is the reason the admin route is a better fit than a bespoke console: the standalone deployment has a staff user already, and an integrated host — where roles, organisations and trust are the host's business — is the one deciding who reaches `/admin/` at all. PROlog does not have to model any of it.

**A host that wants finer control than "staff"** — say, an org admin who may administer only their own instruments — filters in its own `AdminSite`, or does not use this and drives the same commands from its own UI. That is a host decision and stays out of here.

## 5. What this is not

- **Not a survey builder.** Definitions are authored as files and reviewed like code: diffable, revertible, testable before anyone answers them. Every screen above treats a definition as a document to verify and load, never as a form to fill in.
- **Not audience management.** Who a survey is for is the host's question.
- **Not branded.** This looks like Django admin, because it is. If a customer's own staff ever administer their own instruments, that is when a themed console earns its cost — and this design is what it would replace, not something it would have to undo.

## 6. Decisions to settle before building

1. ~~**Does the console show response *data*?**~~ **Settled: no.** The question and response admins are gone. Questions come from the definition; answers come from the API and the exports, and an admin page showing patient-entered free text has a different audience from an export somebody deliberately ran.
2. **Should a draft be deletable?** Its questions and options are `CASCADE`, so it works. The question is whether the UI should say so before doing it.
3. **Invitations and repeat administrations** exist in the engine and are only listed today. Whether the console ever drives them — "invite these people on this date" — is open.
