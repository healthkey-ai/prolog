import { describe, expect, it } from "vitest";
import { type AnswerError, MAX_OTHER_TEXT, defaultOrder, implicitAnswer, validateAnswer, orderedSourceOptions, priorityCount, sourceKeys } from "./answers";
import type { Question } from "./types";

const ranking: Question = {
  key: "r",
  type: "ranking",
  text: { en: "r" },
  options: [
    { key: "a", label: { en: "a" } },
    { key: "b", label: { en: "b" } },
    { key: "c", label: { en: "c" } },
  ],
  config: { optional_items: ["c"] },
};

describe("defaultOrder", () => {
  it("is the options in definition order minus the optional items", () => {
    expect(defaultOrder(ranking)).toEqual(["a", "b"]);
    expect(defaultOrder({ ...ranking, config: {} })).toEqual(["a", "b", "c"]);
  });
});

describe("implicitAnswer", () => {
  it("is a required ranking's displayed order, optional items excluded", () => {
    expect(implicitAnswer(ranking)).toEqual({ order: ["a", "b"] });
    expect(implicitAnswer(ranking)).toEqual({ order: defaultOrder(ranking) });
  });
  it("is nothing for an optional ranking or any other type", () => {
    expect(implicitAnswer({ ...ranking, required: false })).toBeUndefined();
    expect(implicitAnswer({ key: "t", type: "text", text: { en: "t" } })).toBeUndefined();
  });
});

describe("matrix ratings", () => {
  it("come back in rows order whatever order they were rated in", () => {
    const q: Question = {
      key: "m",
      type: "matrix",
      text: { en: "m" },
      config: {
        scale: { min: 1, max: 5 },
        rows: [
          { key: "x", label: { en: "x" } },
          { key: "y", label: { en: "y" } },
          { key: "z", label: { en: "z" } },
        ],
      },
    };
    const value = validateAnswer(q, { ratings: { z: 3, x: 1, y: 2 } }, {});
    expect(Object.keys((value as { ratings: Record<string, number> }).ratings)).toEqual(["x", "y", "z"]);
    expect(JSON.stringify(value)).toBe(JSON.stringify({ ratings: { x: 1, y: 2, z: 3 } }));
  });
});

describe("text length", () => {
  it("counts code points like the server, not UTF-16 units", () => {
    const q: Question = { key: "t", type: "text", text: { en: "t" }, config: { max_length: 6 } };
    expect(validateAnswer(q, { text: "😀😀😀😀😀😀" }, {})).toEqual({ text: "😀😀😀😀😀😀" });
    let issues: unknown;
    try {
      validateAnswer(q, { text: "😀😀😀😀😀😀😀" }, {});
    } catch (e) {
      issues = (e as AnswerError).issues;
    }
    expect(issues).toEqual([{ code: "text_too_long", params: { max: 6 } }]);
  });
});

describe("text length (stripped value)", () => {
  it("applies the limit to what is stored, not to surrounding whitespace", () => {
    const q: Question = { key: "t", type: "text", text: { en: "t" }, config: { max_length: 3 } };
    expect(validateAnswer(q, { text: "  abc  " }, {})).toEqual({ text: "abc" });
    expect(() => validateAnswer(q, { text: "abcd" }, {})).toThrow();
  });
});

describe("multi exclusive option", () => {
  const q: Question = {
    key: "m",
    type: "multi",
    text: { en: "m" },
    config: { min_selections: 2 },
    options: [
      { key: "a", label: { en: "a" } },
      { key: "b", label: { en: "b" } },
      { key: "none", label: { en: "none" }, exclusive: true },
    ],
  };
  it("on its own satisfies min_selections", () => {
    expect(validateAnswer(q, { options: ["none"] }, {})).toEqual({ options: ["none"] });
  });
  it("still cannot be combined, and an ordinary short pick is still short", () => {
    let codes: string[] = [];
    try {
      validateAnswer(q, { options: ["none", "a"] }, {});
    } catch (e) {
      codes = (e as AnswerError).issues.map((i) => i.code);
    }
    expect(codes).toEqual(["exclusive_combined"]);
    codes = [];
    try {
      validateAnswer(q, { options: ["a"] }, {});
    } catch (e) {
      codes = (e as AnswerError).issues.map((i) => i.code);
    }
    expect(codes).toEqual(["min_selections"]);
  });
});

describe("dynamic matrix rows", () => {
  it("refuses to validate a rows_from matrix without the questions map", () => {
    const q: Question = {
      key: "m",
      type: "matrix",
      text: { en: "m" },
      config: { rows_from: "src", scale: { min: 1, max: 3 } },
    };
    const answers = { src: { options: ["none"] } };
    expect(() => validateAnswer(q, { ratings: { none: 1 } }, answers)).toThrow(/questions map/);
  });
});

describe("whitespace stripping (shared set)", () => {
  // Both engines strip exactly space, tab, CR and LF. String.prototype.trim()
  // and str.strip() disagree on U+FEFF and U+0085, so with max_length 3
  // "\uFEFFabc" and "\x85abc" must be text_too_long in both, never one each.
  const codesOf = (fn: () => unknown): string[] => {
    try {
      fn();
    } catch (e) {
      return (e as AnswerError).issues.map((i) => i.code);
    }
    return [];
  };
  it("text: strips the ASCII set and keeps other Unicode whitespace", () => {
    const q: Question = { key: "t", type: "text", text: { en: "t" }, config: { max_length: 3 } };
    expect(validateAnswer(q, { text: " \t\r\nabc\n\r\t " }, {})).toEqual({ text: "abc" });
    for (const raw of ["\uFEFFabc", "\x85abc"]) {
      expect(codesOf(() => validateAnswer(q, { text: raw }, {})), JSON.stringify(raw)).toEqual(["text_too_long"]);
    }
    expect(codesOf(() => validateAnswer(q, { text: " \t\r\n" }, {}))).toEqual(["text_required"]);
  });
  it("other_text: same set", () => {
    const q: Question = {
      key: "s",
      type: "single",
      text: { en: "s" },
      options: [{ key: "other", label: { en: "other" }, free_text: true }],
    };
    expect(validateAnswer(q, { option: "other", other_text: " \t\r\nx\n\r\t " }, {})).toEqual({
      option: "other",
      other_text: "x",
    });
    for (const lead of ["\uFEFF", "\x85"]) {
      const value = { option: "other", other_text: lead + "x".repeat(MAX_OTHER_TEXT) };
      expect(codesOf(() => validateAnswer(q, value, {})), JSON.stringify(lead)).toEqual(["other_text_too_long"]);
    }
  });
});

describe("dynamic matrix rows (questions map contents)", () => {
  const q: Question = {
    key: "m",
    type: "matrix",
    text: { en: "m" },
    config: { rows_from: "src", scale: { min: 1, max: 3 } },
  };
  const answers = { src: { options: ["none"] } };
  it("refuses an empty questions map", () => {
    expect(() => validateAnswer(q, { ratings: { none: 1 } }, answers, { questions: {} })).toThrow(/questions map/);
  });
  it("refuses a questions map that lacks the source question", () => {
    const questions = { other: { key: "other", type: "text", text: { en: "o" } } as Question };
    expect(() => validateAnswer(q, { ratings: { none: 1 } }, answers, { questions })).toThrow(/questions map/);
  });
});

describe("options_source_include", () => {
  const source = new Set(["DE", "FR", "US", "GB"]);
  const dropdown = {
    key: "country",
    type: "dropdown",
    text: "Country",
    options: [{ key: "prefer_not", label: "Prefer not to say" }],
    config: { options_source: "iso3166_countries", options_source_include: ["DE", "FR"] },
  } as unknown as Question;

  it("accepts an included key and refuses an excluded one (mirrors answers.py)", () => {
    expect(validateAnswer(dropdown, { option: "DE" }, {}, { sourceOptions: source })).toEqual({ option: "DE" });
    expect(() => validateAnswer(dropdown, { option: "US" }, {}, { sourceOptions: source })).toThrow();
  });

  it("leaves inline options and an unrestricted source alone", () => {
    expect(validateAnswer(dropdown, { option: "prefer_not" }, {}, { sourceOptions: source })).toEqual({ option: "prefer_not" });
    const open = { ...dropdown, config: { options_source: "iso3166_countries" } } as unknown as Question;
    expect(validateAnswer(open, { option: "US" }, {}, { sourceOptions: source })).toEqual({ option: "US" });
  });
});

describe("options_source_priority", () => {
  const opts = [
    { key: "AR", label: "Argentina" },
    { key: "DE", label: "Germany" },
    { key: "GB", label: "United Kingdom" },
    { key: "US", label: "United States" },
    { key: "ZW", label: "Zimbabwe" },
  ];

  it("puts the pinned keys first, in the order given", () => {
    const cfg = { options_source: "iso3166_countries", options_source_priority: ["GB", "US", "DE"] };
    expect(orderedSourceOptions(cfg, opts).map((o) => o.key)).toEqual(["GB", "US", "DE", "AR", "ZW"]);
  });

  it("leaves the rest in the source's own order", () => {
    const cfg = { options_source: "iso3166_countries", options_source_priority: ["US"] };
    expect(orderedSourceOptions(cfg, opts).map((o) => o.key)).toEqual(["US", "AR", "DE", "GB", "ZW"]);
  });

  it("changes nothing without the key", () => {
    const cfg = { options_source: "iso3166_countries" };
    expect(orderedSourceOptions(cfg, opts)).toBe(opts);
    expect(priorityCount(cfg, opts)).toBe(0);
  });

  it("ignores a pinned key the source does not have", () => {
    // The definition validator refuses these at load; the renderer must not
    // leave a gap in the list because one slipped through.
    const cfg = { options_source: "iso3166_countries", options_source_priority: ["XX", "GB"] };
    expect(orderedSourceOptions(cfg, opts).map((o) => o.key)).toEqual(["GB", "AR", "DE", "US", "ZW"]);
    expect(priorityCount(cfg, opts)).toBe(1);
  });

  it("counts the pinned group so a renderer can separate it", () => {
    const cfg = { options_source: "iso3166_countries", options_source_priority: ["GB", "US"] };
    expect(priorityCount(cfg, opts)).toBe(2);
  });

  it("orders but does not restrict: every key stays answerable", () => {
    const cfg = { options_source: "iso3166_countries", options_source_priority: ["GB"] };
    const source = new Set(opts.map((o) => o.key));
    expect(sourceKeys(cfg, source)).toEqual(source);
  });
});
