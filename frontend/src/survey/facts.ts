import type { BranchCondition, Condition, Definition, FactCondition } from "./types";

/**
 * Facts about the participant, supplied by the host when a response starts
 * (DEF-14, RUN-23). The server resolves them into the definition it serves for
 * a response, so the runner only ever meets `{const: …}`; this resolver is the
 * same rule for tests and tooling. A fact not supplied, or supplied with an
 * undeclared value, is unknown, and every condition on it is false. Mirrors
 * engine/facts.py.
 */
export function knownFacts(def: Definition, facts: Record<string, unknown> | undefined): Record<string, string> {
  const declared = new Map((def.facts ?? []).map((f) => [f.key, new Set(f.values)]));
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(facts ?? {})) {
    if (typeof value === "string" && declared.get(key)?.has(value)) out[key] = value;
  }
  return out;
}

export function factHolds(c: FactCondition, known: Record<string, string>): boolean {
  const value = known[c.fact];
  if (value === undefined) return false;
  if (c.op === "eq") return value === c.value;
  if (c.op === "neq") return value !== c.value;
  if (c.op === "in") return (c.values ?? []).includes(value);
  return false;
}

function resolveBranch(c: BranchCondition, known: Record<string, string>): BranchCondition {
  return "fact" in c ? { const: factHolds(c, known) } : c;
}

function resolve(conditions: Condition[] | undefined, known: Record<string, string>): Condition[] | undefined {
  return conditions?.map((c) => ("any" in c ? { any: c.any.map((b) => resolveBranch(b, known)) } : resolveBranch(c, known)));
}

/** `def` with each fact condition replaced by its truth for `facts`; a definition declaring none is returned as it is. */
export function resolveFacts(def: Definition, facts: Record<string, unknown> | undefined): Definition {
  if (!def.facts?.length) return def;
  const known = knownFacts(def, facts);
  return {
    ...def,
    sections: def.sections.map((s) => ({
      ...s,
      visible_if: resolve(s.visible_if, known),
      questions: s.questions.map((q) => (q.visible_if ? { ...q, visible_if: resolve(q.visible_if, known) } : q)),
    })),
  };
}
