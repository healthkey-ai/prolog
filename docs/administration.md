# Running surveys: an administrator's manual

> **Two ways to do all of this:** the commands below, or Django admin. What the
> admin covers, and deliberately does not, is [From the admin](#from-the-admin);
> the rest of the plan is [`administration-console.md`](administration-console.md).
>
> **Artifacts this describes:** [`definitions/survey-definition.md`](definitions/survey-definition.md) — every field of a definition · [`definitions/theme-definition.md`](definitions/theme-definition.md) — every field of a theme · [`deployment.md`](deployment.md) — the deployment itself · [`integration.md`](integration.md) — installing PROlog in a host platform

This is for the person who puts a survey in front of respondents: what the
pieces are, what happens when, and which steps are deliberate because they
cannot be undone. It assumes a PROlog deployment already exists — building one
is [`deployment.md`](deployment.md).

If you read nothing else, read [Publishing a survey](#publishing-a-survey) and
[Versions are immutable](#versions-are-immutable). Everything else is detail
around those two.

---

## What a survey is here

Three separate things, deliberately:

A deployment running several surveys keeps **one folder per survey** — its
definition, its theme and the theme's assets together — and points
`PROLOG_DEFINITION_DIRS` at the tree above them. See
[`deployment.md`](deployment.md).

| | What it is | Who owns it |
| --- | --- | --- |
| **Definition** | A JSON file: the questions, their order, their branching rules. One file is one *version*. | You |
| **Theme** | A directory: colours, fonts, logo, decorative shapes. One theme can dress many surveys. | You |
| **Runner** | The application that asks the questions and records the answers. | PROlog |

The runner contains no survey content and no branding. Everything a respondent
reads comes from a definition; everything they see comes from a theme. That is
why adding a question is an edit to a file rather than a code change, and why
two customers can run entirely different-looking surveys on one deployment.

A definition is *data*, but it is not free text: it is validated against a
schema, and a deployment refuses to load one that does not fit. That refusal is
the point — a typo in a branching rule becomes an error at load time rather than
a respondent seeing the wrong question.

---

## The lifecycle

```
   author            load             review            activate           close
  a JSON  ──────▶  as a draft ─────▶ in the runner ───▶  live  ──────▶  effective_to
   file            (validated)       (not public)      (public)          passes
```

**Draft.** Loading a definition never publishes it. A draft is in the database,
validated, and invisible to respondents. You can load the same file as many
times as you like.

**Active.** Exactly one version of a survey is active at a time. Activating is a
separate, explicit command, and it archives whatever was active before.

**Archived.** Still there, still readable, no longer offered. Responses stay
attached to the version they were answered against — that is the whole reason
versions exist.

### Publishing a survey

Two ways, doing the same thing: the commands below, or **Django admin** — see
[From the admin](#from-the-admin). The admin is the same validator and the same
loader, for someone without a shell on the host.

```sh
# 1. Does it hold together? Nothing is written.
manage.py validate_definition surveys/my-survey.json

# 2. Load it as a draft. Safe to repeat.
manage.py load_definition surveys/my-survey.json

# 3. Look at it in the runner, as a respondent would.
#    Drafts are reachable only if your deployment exposes them; otherwise
#    review on a staging deployment before activating anywhere real.

# 4. Publish. This is the deliberate step.
manage.py load_definition surveys/my-survey.json --activate
```

Step 1 is worth running every time. It reports two kinds of thing: **errors**,
which refuse the file, and **warnings**, which do not — a warning usually means
"this is legal but probably not what you meant", such as an option nothing can
ever select.

---

## Versions are immutable

Once a version is active, **its content cannot change**. Editing the file and
re-loading it is refused:

```
ERROR immutable at $.version: version 1.0 is active; bump the version to change it
```

This is not bureaucracy. A response records *which version it answered*, and
"what did question 7 say?" must have one answer forever. If you edit an active
version in place, every response already given quietly comes to mean something
else.

So: **any change a respondent's answers must be interpreted against is a new
version.** Change `version` in the file, load it, activate it. The old version
is archived, its responses keep pointing at it, and new respondents get the new
one.

Reloading an *unchanged* file is always safe and reports `unchanged`.

### What is not a version change

Changing the theme, the effective dates, or the deployment's own settings. Those
do not alter what was asked.

---

## Who answers, and what is recorded

**Every response belongs to a participant record.** Where somebody is signed in,
it is theirs. Where nobody is, the deployment creates a record carrying nothing
that could name them.

That is what "anonymous" means here, and it is worth being precise with
respondents about it: *a record nobody can put a name to*, not *no record*. The
runner will not describe an instrument as anonymous on your behalf — the intro
and consent text are yours, and it is your responsibility that they are true.

**An email question is not a footnote.** Two modes, and they differ completely:

| Mode | What happens | When to use it |
| --- | --- | --- |
| `link_identity` | The address creates an account for the person who answered. They can come back, see their own data, and be asked less next time. | The default. |
| `store_separately` | The address goes to a separate list with **no link to the answers**. You get a mailing list and nothing else. | When you genuinely want only a mailing list, and can say why. |

With `link_identity`, an instrument is **not anonymous for the people who give
an address**, and its copy has to say so. With `store_separately`, nobody —
including you — can join an address back to a set of answers, which also means
you cannot honour a later "delete my answers" request from that address.

Skipping the email question always submits the response exactly as it stands.
An account is never a condition of answering.

---

## From the admin

`/admin/prolog_surveys/` in any deployment that has Django admin. It manages an
instrument's **inputs** — which definition and which theme a survey is built
from, whether they are valid, and loading them.

The survey list opens with **where this deployment reads from**: each configured
`PROLOG_DEFINITION_DIRS` and `PROLOG_THEME_DIRS` root, how many definitions or
themes were found under it, and — the useful part — whether the directory is
there at all. An empty list and a mistyped mount look identical until something
says which one it is.

**Add survey** goes to the same picker, because a survey is loaded from a
definition rather than typed into a form: the fields a form would offer are the
loader's, and it rewrites them from the definition on every load.

**Add another version**, on a survey's own page, is the same picker with one
thing already decided — which survey the version belongs to. The theme is
pre-set to the one that survey uses and can be changed, because sometimes
changing it is the point of the new version. A definition slugged for a
different survey is refused there: loading it would create a second survey
rather than a version of this one, which is not what the button said.

Loading — whether it works, does nothing, or is refused — leaves you on the
survey's own page, where its versions are, rather than on a list of every
survey.

**Surveys → Verify and load a definition** does what steps 1 and 2 above do:

1. Choose a definition **this deployment already mounts** (`PROLOG_DEFINITION_DIRS`),
   or upload one. A deployment that ships definitions in its image should choose
   rather than upload — two copies drift.
2. Optionally point at a **theme** — pick one the deployment mounts, or type the
   path to its folder or its `theme.json`; the assets are read from that folder
   either way. It is verified beside the definition, because both are what an
   instrument is made of. A path outside every mounted directory is refused, and
   says so.

   This is what makes one folder per survey work: a survey's theme travels with
   the survey, rather than every theme in the deployment sharing one directory
   and one namespace of codes.
3. **Verify.** Nothing is written. The page shows the validator's own output —
   level, code, path, message — for every issue, not the first, and names the
   schema it was checked against. A definition that is refused says so and stops
   there.
4. **Load as draft** appears only when there are no errors. It never activates:
   publishing stays the deliberate step it is on the command line.

### What the admin deliberately does not do

- **Questions are not listed.** They are the definition's, and a second view of
  them would be one nobody validated.
- **Responses are not browsable.** They belong to the API and the exports, whose
  audience is not an administrator's.
- **Nothing a respondent's answers are interpreted against is editable** — a
  version's definition, a question's text, an option's key. A survey's effective
  window is; the loader owns the rest and rewrites it on every load.
- **A survey with responses cannot be deleted.** The database refuses before any
  code does, and that is the right answer: export them first.

## Languages

A definition carries its own translations, and each non-default language is
marked `machine` or `reviewed`.

**A version whose languages are still `machine` will not activate.** That gate
is deliberate: machine-translated clinical wording is where translation goes
most wrong, and "watch and wait" is not a phrase to guess at.

Three ways past it, and they are not the same:

- `--allow-unreviewed` on activation — **for review only**. It logs loudly and
  the respondent is told nothing. Use it to look at a staging deployment, never
  for a live one.
- **`PROLOG_MACHINE_LANGUAGES`** — the deployment states that respondents will
  read a machine translation of those languages and that this is intended. The
  runner then **discloses it on the intro**: the language was translated by a
  machine, nobody has checked it, and here is the language it was written in.
  For a short, plain-language instrument that is usually better for a
  respondent than no translation at all — but only because they are told.
- Getting the translations reviewed, and changing `translation_status` to
  `reviewed`. This is the one that ships, and it removes the disclosure with
  nothing else to change.

The middle one is a deliberate position, not a shortcut: naming a language
there is a decision about what respondents read, so it belongs in the
deployment's settings next to its other decisions, not in the command somebody
happens to type.

### Giving a reviewer something they can read

A definition is not a review document. Export the two languages side by side:

```sh
manage.py export_translations <slug> --language es [--against en] [--format csv|md] [--out file.csv]
```

One row per translatable string, in the order a respondent meets them, with the
source and the target in adjacent columns and the language's
`translation_status` on every row. CSV opens in a spreadsheet, which is what a
reviewer will ask for; `--format md` renders in a document or a pull request.

**A string nobody has translated is an empty cell, not a missing row** — the
gaps are the most useful thing in the file. Corrections come back keyed by the
`path` column, which is stable, so you can apply them to the definition without
guessing which string was meant.

The respondent's chosen language is recorded on the response, and option keys
stay the same in every language, so answers stay comparable across them.

---

## Effective dates

A survey can carry `effective_from` and `effective_to`. Outside that window the
runner will not start a new response, and in-progress ones are told the survey
has closed.

These are calendar dates in the deployment's time zone, not timestamps. "Closes
on the 31st" means the end of the 31st where the deployment is, which may not be
where your respondents are.

---

## The privacy notice

A survey that asks for anything needs one, and the respondent should not have
to leave the survey to read it. Put Markdown files where the deployment points
`PROLOG_LEGAL_DIRS`:

```
/data/legal/privacy.md        the default language
/data/legal/privacy.es.md     a language that has its own
```

The runner serves it at `/s/<slug>/privacy`, in the survey's own theme, and
links to it **from the intro and from any question that asks for an email
address** — the two places somebody decides whether to trust the survey. The
link does not depend on the instrument having a consent gate: an anonymous
survey has no consent block and its respondents still have a notice to read. A
language with no file of its own falls back to `privacy.md` — the same rule
survey content follows — so a respondent always gets the notice rather than
nothing.

Configure nothing and there is no page and no link. PROlog ships no policy
text, no template and no placeholder wording: what the notice says is yours,
and so is keeping the translations current.

Only a Markdown subset is rendered — headings, paragraphs, lists, tables,
links, bold and italic. Anything else appears as the characters you typed,
which for a notice is a readable failure rather than a broken one. Hard-wrapped
source is fine: wrapped lines are joined before anything is read, so a bold span
or a link broken across two lines still works.

## Getting the answers out

```sh
manage.py export_responses <slug> [--survey-version 1.0] [--out file.csv] [--include-in-progress]
manage.py export_contacts  <slug> [--out contacts.csv]
```

Two exports, deliberately separate. **The response export never contains an
email address, and the contact export never contains an answer.** If you can
join them, something has gone wrong.

By default only submitted responses are exported; `--include-in-progress`
includes unfinished ones, which is usually what you want for a "how far did
people get" question and not what you want for analysis.

Multi-selects and matrix rows are exploded into columns, so a row is one
response.

---

## Housekeeping

**Abandoned responses.** People start surveys and wander off. Nothing deletes
those on its own:

```sh
manage.py purge_abandoned_responses --days 90 [--dry-run]
```

Schedule it. Without it, in-progress responses accumulate forever — and where
the deployment creates a participant record per respondent, so do those.

**Health.** `GET /api/health/` reports the database, whether migrations are
applied, how many surveys are active, and which themes loaded. A deployment
serving no active survey reports `degraded` — correct, and worth checking after
an activation you expected to work.

---

## When something looks wrong

| What you see | What it usually is |
| --- | --- |
| `version 1.0 is active; bump the version to change it` | You edited a published version. Change `version` in the file. |
| `active_surveys: 0` after activating | The activation did not happen, or it was refused for unreviewed translations. Read the load output. |
| The survey 404s for respondents | No active version, or today is outside `effective_from`/`effective_to`. |
| The theme is missing and everything is grey | The theme directory did not load. `register_theme <dir>` reports why; check the deployment's theme path. |
| A question never appears | Its `visible_if` never becomes true. Conditions may only reference *earlier* questions, so check the order as well as the rule. |
| Respondents report the wrong wording in Spanish | Almost always a `machine` translation activated with `--allow-unreviewed`. Check the load log. |

For anything else, the load and activation commands are safe to re-run and print
what they did.

---

## The habits worth having

1. **Validate before loading, load before activating, review before publishing.**
   The three steps exist so that a mistake stops at the cheapest point.
2. **Never edit a published version.** Bump it.
3. **Say what actually happens to the data.** The runner renders the anonymity
   statement you supply; it does not check that it is true.
4. **Keep definitions and themes in version control** where they can be reviewed
   and diffed like anything else you ship.
5. **Schedule the purge.** Nothing else cleans up abandoned responses.
