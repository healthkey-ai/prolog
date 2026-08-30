import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { firstOpenKey, overview, position } from "./navigation";
import type { Definition } from "./types";

const def = JSON.parse(readFileSync(join(__dirname, "..", "..", "..", "examples", "sample-wellbeing.json"), "utf-8")) as Definition;

describe("navigation", () => {
  it("starts a fresh response at the first visible question, info included", () => {
    expect(firstOpenKey(def, {}, "")).toBe("welcome");
  });

  it("resumes at the first open question", () => {
    const answers = { country: { option: "GB" }, age_band: { skipped: true as const } };
    expect(firstOpenKey(def, answers, "age_band")).toBe("birth_year");
  });

  it("computes position, numbering and neighbours", () => {
    const p = position(def, { has_symptoms: { option: "yes" } }, "symptoms");
    expect(p.previousKey).toBe("has_symptoms");
    expect(p.nextKey).toBe("daily_activities");
    expect(p.questionNumber).toBe(7); // welcome is info, not counted
    expect(p.sectionNumber).toBe(2);
    expect(p.sectionTotal).toBe(5); // follow-up section revealed by has_symptoms=yes
    expect(p.isLast).toBe(false);
  });

  it("marks overview rows and reachability", () => {
    const answers = { country: { option: "GB" }, age_band: { skipped: true as const } };
    const rows = overview(def, answers, "birth_year", "birth_year").flatMap((s) => s.rows);
    const byKey = Object.fromEntries(rows.map((r) => [r.key, r]));
    expect(byKey.country.status).toBe("answered");
    expect(byKey.age_band.status).toBe("skipped");
    expect(byKey.birth_year.status).toBe("current");
    expect(byKey.last_visit.status).toBe("unreachable");
    expect(byKey.last_visit.navigable).toBe(false);
    expect(byKey.welcome.navigable).toBe(true);
  });
});
