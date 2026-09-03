# Running surveys: an administrator's manual

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

## Languages

A definition carries its own translations, and each non-default language is
marked `machine` or `reviewed`.

**A version whose languages are still `machine` will not activate.** That gate
is deliberate: machine-translated clinical wording is where translation goes
most wrong, and "watch and wait" is not a phrase to guess at.

Two ways past it, and they are not the same:

- `--allow-unreviewed` on activation — **for review only**. It logs loudly. Use
  it to look at a staging deployment, never for a live one.
- Getting the translations reviewed, and changing `translation_status` to
  `reviewed`. This is the one that ships.

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
