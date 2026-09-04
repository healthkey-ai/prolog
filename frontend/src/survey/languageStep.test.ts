import { describe, expect, it } from "vitest";
import { baseTag, needsLanguageStep } from "./languageStep";

const three = ["en", "es", "pt"];

describe("needsLanguageStep", () => {
  it("does not ask when there is nothing to choose", () => {
    expect(needsLanguageStep({ languages: ["en"], mode: "first", preferred: ["fr"] })).toBe(false);
  });

  it("defaults to the inline picker, which is what deployments have today", () => {
    expect(needsLanguageStep({ languages: three, mode: undefined, preferred: ["fr"] })).toBe(false);
  });

  it("asks first when the definition says so", () => {
    expect(needsLanguageStep({ languages: three, mode: "first", preferred: ["en"] })).toBe(true);
  });

  it("auto asks only when the browser wants something the survey does not offer", () => {
    expect(needsLanguageStep({ languages: three, mode: "auto", preferred: ["fr", "de"] })).toBe(true);
    expect(needsLanguageStep({ languages: three, mode: "auto", preferred: ["es"] })).toBe(false);
  });

  it("auto matches on the base tag: es-419 is Spanish", () => {
    expect(needsLanguageStep({ languages: three, mode: "auto", preferred: ["es-419"] })).toBe(false);
    expect(needsLanguageStep({ languages: three, mode: "auto", preferred: ["pt-BR"] })).toBe(false);
  });

  it("a link that names an offered language has already asked", () => {
    expect(needsLanguageStep({ languages: three, mode: "first", preferred: ["fr"], requested: "es" })).toBe(false);
    // …but a link naming a language this survey does not have has not.
    expect(needsLanguageStep({ languages: three, mode: "first", preferred: ["fr"], requested: "de" })).toBe(true);
  });

  it("normalises a regional tag", () => {
    expect(baseTag("pt-BR")).toBe("pt");
    expect(baseTag("EN")).toBe("en");
  });
});
