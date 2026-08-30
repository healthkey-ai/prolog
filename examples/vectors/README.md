# Engine test vectors

Shared fixtures run by both engines — `backend/prolog_surveys/engine` (Python)
and `frontend/src/survey` (TypeScript) — so the two never drift.

Each file names a definition in `examples/`, an optional `initial` expectation,
a list of `steps` (an answer to store, then what must hold afterwards) and a
`final` expectation. Expectations may include `visible` (ordered visible
question keys), `invalidated` (keys whose stored answers were deleted or
pruned by the cascade), `answers` (the surviving answer map), `missing`
(completion check) and `progress`.

`retained` entries start from `given` answers, store one `answer` and check
the same expectations — for rules about answers that outlive their question's
visibility (a recorded contact capture).

Validation-only sections run each entry against an empty response (or the
`given` answers) without storing anything:

- `reject: [{key, value, code, given?}]` — the engine must refuse `value` for
  question `key` with exactly the rejection `code` (the structured code both
  engines emit and the runner maps to a message); a `reject` entry without a
  `code` fails the suite.
- `accept: [{key, value, given?, canonical?}]` — the engine must accept
  `value`; when `canonical` is present the returned (stored) value must equal
  it, e.g. options re-ordered to definition order or text stripped.
