# Survey definition manual

**Contract:** [`schema/survey-definition.schema.json`](../../schema/survey-definition.schema.json) (JSON Schema 2020-12, `schema_version` 1)  
**Example:** [`examples/sample-wellbeing.json`](../../examples/sample-wellbeing.json) exercises every feature below.  
**Requirements:** DEF-1…DEF-10, RUN-*, Q-*, CON-* in [requirements.md](../requirements.md).

A survey definition is one JSON file describing one **version** of one
survey: its identity, languages, participant-facing copy, participation and
presentation settings, and the ordered sections → questions → options with
their validation and branching rules. The backend stores the (normalised)
document verbatim as the immutable `SurveyVersion.definition`; the runner
renders it; exports and analytics read it. Survey content is data — it never
lives in code.

---

## 1. File anatomy

```jsonc
{
  "$schema": "../schema/survey-definition.schema.json",   // optional, editor support only
  "schema_version": 1,
  "slug": "wellbeing-check-in",                            // stable identity across versions
  "version": "1.0",                                        // content revision
  "status": "draft",                                       // advisory; activation is a CLI/API action
  "default_language": "en",
  "languages": ["en", "es"],
  "translation_status": { "es": "reviewed" },
  "title": { "en": "…", "es": "…" },
  "intro": { "en": "…" },                                  // intro page copy
  "completion": { "en": "…" },                             // completion page copy
  "estimated_minutes": 5,
  "theme": "default",                                      // theme code (see theme manual)
  "participation": { "anonymous": true, "resume": "browser_token" },
  "presentation": { "mode": "question", "skip_policy": "soft" },
  "consent": { "version": "2026-01", "text": { "en": "…" } },
  "notes": "internal, never shown",
  "sections": [ … ]
}
```

### Top-level fields

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `schema_version` | integer | no (=1) | Format version this file targets. The loader refuses unsupported versions. |
| `slug` | `^[a-z0-9][a-z0-9-]*$`, ≤ 120 chars | yes | Stable survey identity across versions; part of the runner URL `/s/<slug>`. |
| `version` | `^[0-9]+(\.[0-9]+)*$`, ≤ 32 chars | yes | Content revision (`0.6`, `1.0`, `1.1`). Any wording or structure change responses must be interpreted against is a **new version**. |
| `status` | `draft` · `active` · `archived` | yes | Advisory only. The loader always stores a file as a **draft**; activation is the explicit `--activate` step (see §9). |
| `default_language` | language code | yes | Fallback for every text; must be listed in `languages`. |
| `languages` | array of codes | yes | Languages offered on the intro page and in the header switch. Codes match `^[a-z]{2}(-[A-Za-z]{2,4})?$` (`en`, `pt-BR`). |
| `translation_status` | `{lang: machine\|reviewed}` | for non-default languages | `machine` = placeholder that must not go live; `reviewed` = approved. **A version cannot be activated while any offered language is `machine`.** |
| `title`, `intro`, `completion` | i18n text | `title` yes | Title (also `<title>`; ≤ 255 characters in the default language), intro-page paragraph, completion-page paragraph. |
| `estimated_minutes` | integer ≥ 1 | no | Shown as "About N minutes" on the intro page. |
| `theme` | theme code (≤ 64 chars) | no | Resolved by the deployment; unknown or missing → `default` (logged). |
| `participation` | object | no | Who may respond and how they resume — §5. |
| `presentation` | object | no | Wizard layout and skip policy — §6. |
| `consent` | object | no | Versioned consent attestation shown before the first question — §7. |
| `notes` | string | no | Internal notes; stripped from everything the runner receives. |
| `sections` | array (≥ 1) | yes | The instrument — §2. |

### i18n text

Every participant-facing string is an object keyed by language code:

```json
{ "en": "How old are you?", "es": "¿Cuántos años tiene?" }
```

The `default_language` key is **required** in every i18n object (validator
error otherwise). Missing languages fall back to the default at render time;
keys for languages not listed in `languages` produce a warning.

---

## 2. Sections

```jsonc
{
  "key": "wellbeing",                       // ^[a-z0-9][a-z0-9_]*$ (≤ 128 chars), unique among sections
  "title": { "en": "How you have been feeling" },
  "description": { "en": "Think about the last two weeks." },   // optional
  "visible_if": [ … ],                      // optional; may only reference questions in EARLIER sections
  "questions": [ … ]                        // ≥ 1, presentation order
}
```

Sections run in array order and questions within a section in array order —
that order is the **presentation order** used everywhere (numbering, the
overview panel, exports) and it is also the evaluation order of the
dependency graph (§4). A hidden section hides all of its questions.

The runner shows a data-free **interstitial** (section number, title,
description) when a participant enters a new section
(`presentation.section_interstitials`).

---

## 3. Questions

```jsonc
{
  "key": "symptoms",                        // globally unique; answers and exports reference it
  "type": "multi",
  "text": { "en": "Which symptoms? Select up to three." },
  "help": { "en": "…" },                    // optional help line (email: shown as a notice panel)
  "required": true,                         // default true (info: always false)
  "options": [ … ],                         // single / dropdown / multi / ranking
  "visible_if": [ … ],                      // optional; references EARLIER questions only
  "config": { … }                           // per type, below
}
```

### 3.1 Types at a glance

| `type` | Control in the runner | Stored answer value |
| --- | --- | --- |
| `info` | Read-only text block (no answer, not counted in progress) | — |
| `single` | Radio cards; an option with `free_text` reveals an inline text field | `{"option": "k", "other_text"?: "…"}` |
| `dropdown` | Searchable combobox; options from `options_source` plus inline options | `{"option": "k"}` |
| `multi` | Checkbox cards with counter, limits and exclusive options | `{"options": ["k1","k2"], "other_text"?: "…"}` |
| `scale` | Segmented buttons `min..max` with endpoint or per-point labels | `{"value": 4}` |
| `ranking` | Sortable list (drag **and** ▲▼ buttons); optional items in an "add" tray | `{"order": ["k1","k2",…], "other_text"?: "…"}` |
| `matrix` | One card per row, a segmented scale per row, legend once | `{"ratings": {"row": 3, …}}` |
| `text` | Input or textarea (`multiline`) with a remaining-characters counter | `{"text": "…"}` |
| `number` | Numeric input | `{"number": 42}` |
| `date` | Date input | `{"date": "YYYY-MM-DD"}` |
| `email` | Email input with the `help` notice, **Save** and **No thanks** | `{"provided": true\|false}` — the address itself is never an answer (§8) |
| any | Explicit skip (soft policy or optional question) | `{"skipped": true}` |

Option keys and `other_text` are stored exactly as canonicalised by the
server: option lists are re-ordered to the definition's option order,
free text is stripped of leading/trailing ASCII space, tab, CR and LF (other
Unicode whitespace is kept and counted), `other_text` is only kept when a `free_text` option is
selected/ranked, and it is limited to 500 characters.

### 3.2 Options

```jsonc
{ "key": "other", "label": { "en": "Other" }, "free_text": true }
{ "key": "none",  "label": { "en": "None of these" }, "exclusive": true }
```

| Field | Meaning |
| --- | --- |
| `key` | `^[a-z0-9][a-z0-9_]*$` (≤ 128 chars), unique within the question. Referenced by conditions, exports (`question.key` columns) and matrix rows. |
| `label` | i18n text. |
| `free_text` | Selecting (or ranking) this option reveals an inline text input stored as `other_text`. |
| `exclusive` | `multi` only: selecting it clears every other option, and selecting another option clears it (e.g. "I am not sure"). Warned on other types. |

### 3.3 `config` by type

| Type | Keys | Notes |
| --- | --- | --- |
| `multi` | `max_selections` (int ≥ 1), `min_selections` (int ≥ 1, default 1) | "Select up to N" counter; at the limit the remaining cards become inert. Fewer than `min_selections` picks are rejected (`min_selections`), except an `exclusive` option selected on its own, which is a complete answer. `max_selections` ≤ number of options; `min` ≤ `max`. |
| `dropdown` | `options_source` (`iso3166_countries`) | A built-in, localised list served by `GET /api/run/options/iso3166_countries/?lang=`; inline `options` are appended after it (e.g. "Prefer not to say"). A dropdown needs `options`, `options_source`, or both. |
| `scale` | `scale: {min, max, min_label?, max_label?, point_labels?}` | `min < max` and at most 101 points (`max − min ≤ 100`; the runner draws one control per point); `point_labels` (i18n each) must have exactly `max − min + 1` entries. |
| `matrix` | `scale` (required) plus **either** `rows_from` (key of an earlier `multi` question — its selected options become the rows; an `exclusive` option never does, so a selection of only exclusive options hides the matrix) **or** `rows: [{key, label}]` (fixed rows) | Dynamic rows are labelled with the source option label, or with the participant's own `other_text` for a `free_text` option. Every current row must be rated. |
| `ranking` | `optional_items: [keys]` | Items that may be left unranked; they sit in an "Add to ranking" tray. Everything else must be ranked exactly once, so at least one item must not be optional. |
| `text` | `max_length` (int ≥ 1), `multiline` (bool; default `max_length > 200`) | Counter shows remaining characters. The limit is measured on the stored value: leading/trailing ASCII whitespace (space, tab, CR, LF) is stripped by both engines; other Unicode whitespace (e.g. U+00A0, U+FEFF) is kept and counted. Every text answer is capped at **10,000 characters** by the engines regardless of `max_length` (a larger value is clamped and warned about). |
| `number` | `min_value`, `max_value` (numbers), `integer` (bool) | Non-finite values are rejected. |
| `date` | `min_date`, `max_date` (`YYYY-MM-DD`) | Inclusive bounds. Both must be real calendar dates (the schema only checks the digit pattern) with `min_date` ≤ `max_date`. |
| `email` | `store_separately: true` **or** `link_identity: true` | **Exactly one is required**: the schema rejects both together and the validator rejects neither (`email_capture` — without a capture mode no endpoint could accept an address, so the step could only ever record a decline). §8. |

Keys not used by the type are reported as warnings.

### 3.4 `required` and skipping

`required` defaults to `true` (for `info` it is ignored). What "required"
means depends on `presentation.skip_policy`:

| `skip_policy` | required question, no answer, Next pressed | `required: false` |
| --- | --- | --- |
| `soft` (default) | One-time prompt "You haven't answered. Skip this question?"; confirming stores `{"skipped": true}` | skips silently |
| `hard` | Next stays disabled until answered; the API rejects a skip | skips silently |
| `none` | skips silently | skips silently |

A skip is an explicit, revisitable answer row — distinct from "not reached" —
so completion (§10) and exports (`SKIPPED`) can tell the two apart. Optional
questions show an **Optional** tag under the question number.

---

## 4. Branching: `visible_if` and the DAG rule

A question or section is shown only when **all** its conditions hold (AND).

```jsonc
"visible_if": [
  { "question": "has_symptoms", "op": "eq", "value": "yes" },
  { "question": "symptoms", "op": "answered" }
]
```

| `op` | Applies to | True when |
| --- | --- | --- |
| `eq` / `neq` | `single`, `dropdown`, `scale` | the answer equals / does not equal `value` (scale values as strings: `"4"`) |
| `in` | `single`, `dropdown`, `scale` | the answer is one of `values` |
| `contains` | `multi`, `ranking` | `value` is among the selected / ranked keys |
| `answered` | any answerable type | an answer exists that is not a skip (and not empty) |

**Every operator is false while the referenced question is unanswered or
skipped.** `value`/`values` must be option keys of the referenced question
(or integers within the scale range); dropdowns with an `options_source`
accept any value.

### The DAG rule (DEF-10)

Questions are nodes; every `visible_if` condition and every `rows_from` is a
directed edge from the dependent question (or section) to the question it
depends on. **An edge may only point to a question that appears earlier in
presentation order** — never to itself, never forward — and a section may
only depend on questions in earlier sections. The graph is therefore acyclic
by construction and presentation order is its topological order, which is
what makes the engine simple:

- Visibility is one forward pass; conditions only ever see answers of
  questions that are themselves visible, so a hidden question's stale answer
  can never keep something downstream open.
- When an answer changes, the server recomputes visibility and **cascades**:
  answers of now-hidden questions are deleted, a dynamic matrix is pruned to
  its surviving rows (deleted if none remain), and the response returns
  `invalidated: [keys]` so the runner can sync.
- The validator rejects forward, self and unknown references and warns about
  questions that can never be shown (contradictory conditions, or
  dependants of unreachable questions).

Jumping *back* in the wizard is not an edge — participants may revisit any
reachable question; changing an answer re-runs the cascade forward.

---

## 5. `participation`

```jsonc
"participation": {
  "anonymous": true,            // default false
  "resume": "browser_token",    // browser_token | account | none
  "repeat": { "every": 4, "unit": "weeks", "start_date": "2026-09-01", "end_date": "2027-03-01", "use_current_version": false }
}
```

| Field | Meaning |
| --- | --- |
| `anonymous` | `true`: no account; the response id held by the browser is the only credential (treated as a secret). `false`: participants need an authenticated account with a resolvable participant (integrated profile) **or** a personal invitation link. |
| `resume` | `browser_token` (default for anonymous): the response id is kept in browser storage; the intro offers **Continue / Start again**. `account`: `POST /responses/` returns the participant's in-progress response. `none`: no resume on a later visit — the id is kept in `sessionStorage`, so a reload or a return to `/s/<slug>/q/…` **within the same tab** reopens the in-progress response, but the intro never offers **Continue / Start again** (Start always creates a new response) and the id is gone once the tab closes, so a later visitor on a shared device never sees it. |
| `repeat` | Repeat administration for invited participants: every `every` `weeks`/`months` from `start_date` (month-end dates clamp), until `end_date`; `use_current_version: true` lets each administration use the then-active version instead of the scheduled one. Off by default. `start_date`/`end_date` must be real calendar dates with `end_date` ≥ `start_date` (validator errors). On an `anonymous` survey a `repeat` block is inert — the scheduler never administers anonymous surveys — and the validator warns. Nothing is scheduled or sent while the survey is outside its effective window (`effective_from`/`effective_to` on the survey record). |

---

## 6. `presentation`

```jsonc
"presentation": {
  "mode": "question",            // question (one question per screen); "section" is planned and rejected by the validator for now
  "overview": true,              // "All questions" panel with jump-back
  "section_interstitials": true, // interstitial when entering a new section
  "skip_policy": "soft",         // soft | hard | none (see §3.4)
  "progress": "bar"              // bar | steps | none
}
```

Defaults reproduce the one-question-per-screen wizard. `progress: "bar"` draws a
completion bar in the header; `"steps"` shows a **Step n of m** counter over the
visible screens instead; `"none"` hides both.

---

## 7. `consent`

```jsonc
"consent": {
  "version": "2026-01",                   // ≤ 64 chars
  "text": { "en": "We store your answers to …" },
  "required": true,              // default true
  "privacy_url": "https://example.org/privacy"  // absolute http(s) URL only (validated)
}
```

The notice is shown on the intro page with a checkbox. Creating a response
requires `{"version": "2026-01", "agreed": true}` for the current version;
the attestation is stored separately from answers (version, text hash,
language, timestamp). Bumping `version` re-presents the notice on the next
administration and never alters an existing response's attestation.

---

## 8. The `email` question — contact vs identity capture

The address never travels through the answer endpoint; the answer row only
records `{"provided": true|false}`.

| Config | Behaviour | Profile |
| --- | --- | --- |
| `"store_separately": true` | **Contact capture.** `POST /responses/{id}/contact/` stores the address in a contact table with the survey version and the notice shown, and **no reference to the response**. Exported separately; never returned by the API; never logged. | standalone + integrated |
| `"link_identity": true` | **Identity capture.** The address goes only to the host platform's identity service, which creates/finds a participant; the response is linked to it. The address is never persisted by the runner. | integrated only (validator error otherwise) |

At most one `email` question per survey. Use the question's `help` for the
privacy notice (shown as a panel above the input). **No thanks** records the
decline and moves on; on the last question it submits.

---

## 9. Versioning and lifecycle

| Situation | What to do |
| --- | --- |
| First release | `version: "1.0"`, `translation_status` all `reviewed`, `load_definition file --activate`. |
| Fix a typo in a **draft** | Edit the file and load again — drafts are upserted in place (idempotent; same checksum = "unchanged"). The checksum is taken over the file as written, so a newer runner filling in more defaults never makes an untouched file look edited. |
| Change wording/options/branching of a **published** version | New file (or new `version` value): `1.0` → `1.1`. The loader refuses to modify an active or archived version ("bump the version to change it"). |
| Activate the new version | `load_definition file --activate` archives the previous active version; in-progress responses keep the version they started on (the runner asks for the definition bound to the response). |
| Review machine-translated content locally | `--activate --allow-unreviewed` (logs loudly; never for launch). |

Survey-level fields shown to participants (title, theme, anonymity) mirror
the **active** version; loading a draft cannot retarget a live survey.

---

## 10. What the server enforces

- **Structure** (JSON Schema): types, patterns, required keys, enums,
  identifier lengths (`slug` ≤ 120, `version` ≤ 32, `theme` ≤ 64, keys ≤ 128,
  `consent.version` ≤ 64 — the database columns behind them).
- **Semantics** (`validate_definition`): unique keys; the DAG rule; condition
  operators/values fit the referenced question type; `rows_from` targets a
  `multi`; `max_selections` ≤ options; `min` ≤ `max`; `optional_items` are
  options; scale `min < max` and label counts; one `email` question, and
  it declares exactly one capture mode (`store_separately` or
  `link_identity`); `link_identity` only in the integrated profile; `min_date`/`max_date` and
  `repeat.start_date`/`end_date` are real calendar dates in order; `title`
  in the default language ≤ 255 characters; every non-default language has
  a `translation_status`; every i18n object has the default language;
  warnings for unreachable questions and for `repeat` on an anonymous
  survey.
- **Answers** (per PUT): value shape per type, option keys, limits,
  exclusives, `other_text` rules, scale bounds, ranking completeness, matrix
  rows equal to the current row set, text/number/date bounds, the skip
  policy, and visibility (an answer to a hidden question is rejected). A
  rejection is `400 {"value": [{"code", "params", "message"}]}`: the
  `code` (e.g. `rows_incomplete`, `value_out_of_range`) and typed `params`
  are what the runner turns into text in the participant's language; the
  English `message` is for logs and tooling only. Both engines share the
  code list (`engine/answers.py` `MESSAGES`, `survey/answers.ts`).
- **Presentation**: `presentation.mode` must be `question`; `section` is
  reserved for a later phase and rejected until the runner implements it.
- **Completion** (`POST …/submit/`): every visible answerable question has an
  answer row (value or skip); otherwise `400 {"missing": [keys]}` and the
  runner jumps to the first.

---

## 11. Command-line reference

```sh
manage.py validate_definition surveys/            # schema + semantic rules, no writes
manage.py load_definition surveys/x.json          # upsert as draft (idempotent)
manage.py load_definition surveys/x.json --activate [--allow-unreviewed]
manage.py load_definitions                        # every file in PROLOG_DEFINITION_DIRS, as drafts (runs at container start)
manage.py export_responses <slug> [--survey-version 1.0] [--out file.csv] [--include-in-progress]
manage.py export_contacts  <slug> [--survey-version 1.0] [--out file.csv]
```

Without a database: `python -m jsonschema -i surveys/x.json schema/survey-definition.schema.json`
checks structure only.

---

## 12. Worked example (excerpt)

A gate, a limited multi-select with an exclusive and a free-text option, and a
dynamic matrix whose rows follow the selection — all from the shipped example:

```json
{
  "key": "has_symptoms", "type": "single",
  "text": { "en": "Have you had any symptoms that bothered you?" },
  "options": [
    { "key": "yes", "label": { "en": "Yes" } },
    { "key": "no", "label": { "en": "No" } },
    { "key": "not_sure", "label": { "en": "Not sure" } }
  ]
},
{
  "key": "symptoms", "type": "multi",
  "text": { "en": "Which symptoms? Select up to three." },
  "visible_if": [{ "question": "has_symptoms", "op": "eq", "value": "yes" }],
  "config": { "max_selections": 3 },
  "options": [
    { "key": "fatigue", "label": { "en": "Tiredness" } },
    { "key": "pain", "label": { "en": "Pain" } },
    { "key": "other", "label": { "en": "Other" }, "free_text": true },
    { "key": "none", "label": { "en": "None of these" }, "exclusive": true }
  ]
},
{
  "key": "symptom_impact", "type": "matrix",
  "text": { "en": "How much did each symptom interfere with your daily life?" },
  "visible_if": [
    { "question": "has_symptoms", "op": "eq", "value": "yes" },
    { "question": "symptoms", "op": "answered" }
  ],
  "config": {
    "rows_from": "symptoms",
    "scale": { "min": 1, "max": 5, "point_labels": [{ "en": "Not at all" }, { "en": "A little" }, { "en": "Moderately" }, { "en": "Quite a lot" }, { "en": "Extremely" }] }
  }
}
```

Answering `has_symptoms = no` later removes both downstream answers
(`invalidated: ["symptoms", "symptom_impact"]`); deselecting `pain` prunes
the matrix to the remaining rows.

---

## 13. Export columns

`export_responses` writes one row per submitted response with one column per
question in presentation order: `single`/`dropdown`/`scale`/`text`/`number`/
`date` as a single column; `multi` as one `key.option` column per option
(`1`/`0`) plus `key.other_text`; `ranking` as one column per item holding the
position; `matrix` as one `key.row` column per row; `email` as `1`/`0`
(provided). Skipped questions read `SKIPPED`, hidden questions are blank.
Free text is neutralised against spreadsheet formula injection. Contacts are
a separate export and are never joined.
