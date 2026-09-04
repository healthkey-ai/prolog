import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { firstOpenKey, hasStoredAnswer, overview, position, progressFraction } from "./navigation";
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
    expect(p.visible[p.index + 1].key).toBe("daily_activities");
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

  it("counts any stored row that is not a skip as an answer, as the server does", () => {
    expect(hasStoredAnswer(undefined)).toBe(false);
    expect(hasStoredAnswer({ skipped: true })).toBe(false);
    expect(hasStoredAnswer({ option: "a" })).toBe(true);
    expect(hasStoredAnswer({ provided: false })).toBe(true); // a declined capture is an answer row
    expect(hasStoredAnswer({ order: [] })).toBe(true); // an all-optional ranking with nothing ranked
  });

  it("ticks a declined capture in the overview", () => {
    const tiny = {
      ...def,
      sections: [{ key: "s", title: { en: "S" }, questions: [{ key: "contact", type: "email", text: { en: "Email?" } }, { key: "note", type: "text", text: { en: "Note" } }] }],
    } as unknown as Definition;
    const rows = overview(tiny, { contact: { provided: false } }, "note", "note").flatMap((s) => s.rows);
    expect(rows.find((r) => r.key === "contact")?.status).toBe("answered");
  });

  it("never reports negative progress on an info block", () => {
    const p = position(def, {}, "welcome"); // info: questionNumber is 0
    expect(progressFraction(p, false)).toBe(0);
    const q = position(def, {}, "country");
    expect(progressFraction(q, false)).toBe(0);
    expect(progressFraction(q, true)).toBeCloseTo(1 / q.questionTotal);
  });
});
