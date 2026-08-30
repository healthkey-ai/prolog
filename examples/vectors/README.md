# Engine test vectors

Shared fixtures run by both engines — `backend/prolog_surveys/engine` (Python)
and `frontend/src/survey` (TypeScript) — so the two never drift.

Each file names a definition in `examples/`, an optional `initial` expectation,
a list of `steps` (an answer to store, then what must hold afterwards) and a
`final` expectation. Expectations may include `visible` (ordered visible
question keys), `invalidated` (keys whose stored answers were deleted or
pruned by the cascade), `answers` (the surviving answer map), `missing`
(completion check) and `progress`.
