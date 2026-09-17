import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { renderMarkdown } from "./markdown";

const html = (source: string) => renderToStaticMarkup(<>{renderMarkdown(source)}</>);

describe("renderMarkdown", () => {
  it("renders the subset a notice is written in", () => {
    const out = html("# Privacy\n\nWe keep **little**.\n\n- one\n- two\n");
    expect(out).toContain("<h1");
    expect(out).toContain("<strong>little</strong>");
    expect(out).toContain("<ul");
    expect(out).toContain("<li>one</li>");
  });

  it("joins wrapped lines into one paragraph", () => {
    expect(html("a line\nand its continuation\n")).toContain("a line and its continuation");
  });

  it("keeps ordered and unordered lists apart", () => {
    const out = html("1. first\n2. second\n");
    expect(out).toContain("<ol");
    expect(out).not.toContain("<ul");
  });

  it("makes http links, and leaves anything else as text", () => {
    expect(html("[site](https://example.org)")).toContain('href="https://example.org"');
    const dangerous = html("[click](javascript:alert(1))");
    expect(dangerous).not.toContain("javascript:");
    expect(dangerous).toContain("click");
  });

  it("never emits markup a page supplied", () => {
    // The whole reason this renders a subset rather than setting innerHTML.
    const out = html("<script>alert(1)</script> and <img src=x onerror=y>");
    expect(out).not.toContain("<script>");
    expect(out).not.toContain("<img");
    expect(out).toContain("&lt;script&gt;");
  });

  it("renders unsupported syntax as the text it is written as", () => {
    expect(html("> a quote\n")).toContain("&gt; a quote");
  });

  it("survives an empty page", () => {
    expect(renderMarkdown("")).toEqual([]);
  });

  it("renders a table, which a legal notice usually has one of", () => {
    const out = html("| What | Why |\n| --- | --- |\n| answers | research |\n");
    expect(out).toContain("<table");
    expect(out).toContain("<th");
    expect(out).toContain("research");
    // the |---| rule is structure, not a row
    expect(out).not.toContain("---");
  });

  it("keeps a wrapped list item in its item", () => {
    // Source files are hard-wrapped; a continuation is not a new paragraph.
    const out = html("- a long item that continues\n  on the next line\n- second\n");
    expect(out).toContain("<li>a long item that continues on the next line</li>");
    expect(out.match(/<li>/g)).toHaveLength(2);
    expect(out).not.toContain("<p");
  });

  it("joins a wrapped line before reading inline syntax", () => {
    // **bold across a line break** would otherwise render its own asterisks.
    const out = html("this is **bold\nacross lines** here\n");
    expect(out).toContain("<strong>bold across lines</strong>");
    expect(out).not.toContain("**");
  });

  it("scrolls a wide table instead of the page", () => {
    expect(html("| a | b |\n| --- | --- |\n| 1 | 2 |\n")).toContain("overflow-x-auto");
  });

  it("escapes a pipe inside a cell", () => {
    const out = html("| a | b |\n| --- | --- |\n| one \\| two | 2 |\n");
    expect(out).toContain("one | two");
  });

});

describe("footnotes", () => {
  it("links a citation to its note and the note back to the citation", () => {
    const out = html("Data minimisation[^1] applies.\n\n## Notes\n\n[^1]: Personal data should be limited to what is necessary.\n");
    expect(out).toContain('<sup class="ml-0.5 text-[0.75em] leading-none"><a href="#fn-1" id="fnref-1"');
    expect(out).toContain('>1</a></sup>');
    expect(out).toContain('<li id="fn-1"');
    expect(out).toContain("limited to what is necessary");
    expect(out).toContain('href="#fnref-1"');
    expect(out).toContain('aria-label="Back to note 1"');
  });

  it("cites a note twice without duplicating its id, and joins a wrapped note", () => {
    const out = html("First[^a] and again[^a].\n\n[^a]: A long note that\nwraps onto a second line.\n");
    expect(out.match(/data-testid="footnote-ref-a"/g)?.length).toBe(2);
    expect(out.match(/id="fnref-a"/g)?.length).toBe(1);
    expect(out).toContain("A long note that wraps onto a second line.");
  });

  it("leaves a lone caret bracket as text", () => {
    expect(html("Not a note [^] here.\n")).toContain("Not a note [^] here.");
  });
});
