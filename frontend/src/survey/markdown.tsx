import type { ReactNode } from "react";

/**
 * A deliberately small Markdown subset, rendered into elements.
 *
 * Legal pages are deployment-supplied, and they are opened from the screen
 * where somebody decides whether to give an email address — so the runner
 * renders a known subset into React nodes rather than setting HTML. Nothing a
 * page contains can inject markup into the survey around it, and no Markdown
 * library has to be trusted, shipped or kept patched.
 *
 * Supported: headings (# to ###), paragraphs, unordered and ordered lists,
 * tables, links, bold and italic, and footnotes — `[^3]` in the text, a
 * `[^3]: …` line where the note lives. Anything else renders as the text it
 * is written as, which for a notice is a readable failure rather than a broken
 * one.
 *
 * Footnotes are what a legal notice's drafter reaches for, and the runner
 * keeps them a page apart from the sentence: the marker is a superscript link
 * down to the note, and each note carries a link back to where it was cited,
 * so a reader on a phone is never stranded at the bottom of a long page.
 *
 * Source lines are hard-wrapped in the files these come from, so wrapped
 * continuations are joined back together before anything is parsed inline —
 * in paragraphs, in list items and in table cells. Without that, a bold span
 * or a link broken across two lines renders as its own asterisks.
 */

const INLINE = /(\[\^[A-Za-z0-9_-]+\])|(\[[^\]]+\]\([^)\s]+\))|(\*\*[^*]+\*\*)|(\*[^*]+\*)/g;

/** A footnote's definition line: `[^3]: the note`. */
const FOOTNOTE_DEF = /^\[\^([A-Za-z0-9_-]+)\]:\s+(.*)$/;

/** Element ids for a footnote and its (first) citation. Labels are limited to [A-Za-z0-9_-] by the regexes above. */
const noteId = (label: string) => `fn-${label}`;
const refId = (label: string) => `fnref-${label}`;

/** Only http(s) links become links; anything else stays as text (javascript:, data:). */
function safeHref(href: string): string | null {
  try {
    const url = new URL(href, "https://example.invalid");
    return url.protocol === "http:" || url.protocol === "https:" ? href : null;
  } catch {
    return null;
  }
}

/** Footnote labels already cited in the page being rendered (reset per renderMarkdown). */
let citedOnce = new Set<string>();

export function renderInline(text: string, keyPrefix = ""): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  let match: RegExpExecArray | null;
  INLINE.lastIndex = 0;
  while ((match = INLINE.exec(text)) !== null) {
    if (match.index > last) out.push(text.slice(last, match.index));
    const token = match[0];
    const key = `${keyPrefix}-${match.index}`;
    if (token.startsWith("[^")) {
      const label = token.slice(2, -1);
      // The first citation is where the note's back-link returns to; a note
      // cited twice keeps one id, so the page has no duplicate ids.
      const first = !citedOnce.has(label);
      citedOnce.add(label);
      out.push(
        <sup key={key} className="ml-0.5 text-[0.75em] leading-none">
          <a
            href={`#${noteId(label)}`}
            id={first ? refId(label) : undefined}
            className="scroll-mt-6 text-primary underline decoration-dotted underline-offset-2"
            aria-describedby={noteId(label)}
            data-testid={`footnote-ref-${label}`}
          >
            {label}
          </a>
        </sup>,
      );
    } else if (token.startsWith("[")) {
      const label = token.slice(1, token.indexOf("]"));
      const href = token.slice(token.indexOf("](") + 2, -1);
      const safe = safeHref(href);
      out.push(
        safe ? (
          <a key={key} href={safe} className="text-primary underline" target="_blank" rel="noreferrer noopener">
            {label}
          </a>
        ) : (
          label
        ),
      );
    } else if (token.startsWith("**")) {
      out.push(<strong key={key}>{token.slice(2, -2)}</strong>);
    } else {
      out.push(<em key={key}>{token.slice(1, -1)}</em>);
    }
    last = match.index + token.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export interface MarkdownLabels {
  /** Accessible name of a footnote's back-link, e.g. "Back to the text for note 3". */
  noteBack: (label: string) => string;
}

const DEFAULT_LABELS: MarkdownLabels = { noteBack: (label) => `Back to note ${label}` };

export function renderMarkdown(source: string, labels: MarkdownLabels = DEFAULT_LABELS): ReactNode[] {
  citedOnce = new Set();
  const blocks: ReactNode[] = [];
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  let paragraph: string[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;
  let table: string[][] | null = null;
  let notes: { label: string; text: string }[] | null = null;

  const flushParagraph = () => {
    if (!paragraph.length) return;
    const text = paragraph.join(" ");
    blocks.push(
      <p key={`p${blocks.length}`} className="mb-4 leading-relaxed">
        {renderInline(text, `p${blocks.length}`)}
      </p>,
    );
    paragraph = [];
  };
  const flushTable = () => {
    if (!table) return;
    const [header, ...body] = table;
    const key = `t${blocks.length}`;
    blocks.push(
      // Wide tables scroll rather than pushing the page sideways: a notice is
      // read on a phone as often as not.
      <div key={key} className="mb-4 overflow-x-auto">
        <table className="w-full border-collapse text-left text-[0.95rem]">
          <thead>
            <tr>
              {header.map((cell, i) => (
                <th key={i} className="border-b border-line px-2 py-2 align-top font-semibold">
                  {renderInline(cell, `${key}h${i}`)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {body.map((cells, r) => (
              <tr key={r}>
                {cells.map((cell, i) => (
                  <td key={i} className="border-b border-line px-2 py-2 align-top">
                    {renderInline(cell, `${key}r${r}c${i}`)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>,
    );
    table = null;
  };
  const flushNotes = () => {
    if (!notes) return;
    const key = `fn${blocks.length}`;
    blocks.push(
      // Rendered where the definitions sit, under whatever heading the notice
      // gives them: the runner adds no heading of its own.
      <ol key={key} className="mb-4 ml-6 list-outside list-decimal space-y-2 text-[0.95rem]" data-testid="footnotes">
        {notes.map(({ label, text }) => (
          <li key={label} id={noteId(label)} className="scroll-mt-4 target:bg-tint" data-testid={`footnote-${label}`}>
            {renderInline(text, `${key}-${label}`)}{" "}
            <a href={`#${refId(label)}`} className="text-primary underline decoration-dotted underline-offset-2" aria-label={labels.noteBack(label)} data-testid={`footnote-back-${label}`}>
              ↩
            </a>
          </li>
        ))}
      </ol>,
    );
    notes = null;
  };
  const flushList = () => {
    if (!list) return;
    const { ordered, items } = list;
    const className = `mb-4 ml-6 list-outside space-y-1 ${ordered ? "list-decimal" : "list-disc"}`;
    const children = items.map((item, i) => <li key={i}>{renderInline(item, `l${blocks.length}-${i}`)}</li>);
    blocks.push(
      ordered ? (
        <ol key={`l${blocks.length}`} className={className}>
          {children}
        </ol>
      ) : (
        <ul key={`l${blocks.length}`} className={className}>
          {children}
        </ul>
      ),
    );
    list = null;
  };

  for (const raw of lines) {
    const line = raw.trimEnd();
    const heading = /^(#{1,3})\s+(.*)$/.exec(line);
    const bullet = /^[-*]\s+(.*)$/.exec(line);
    const numbered = /^\d+\.\s+(.*)$/.exec(line);
    const row = /^\|(.*)\|\s*$/.exec(line);
    const note = FOOTNOTE_DEF.exec(line);

    if (!line.trim()) {
      flushParagraph();
      flushList();
      flushTable();
      flushNotes();
      continue;
    }
    if (note) {
      flushParagraph();
      flushList();
      flushTable();
      (notes ??= []).push({ label: note[1], text: note[2] });
      continue;
    }
    if (notes) {
      // A wrapped note: the continuation belongs to the note above.
      notes[notes.length - 1].text += ` ${line.trim()}`;
      continue;
    }
    if (row) {
      flushParagraph();
      flushList();
      const cells = row[1].split(/(?<!\\)\|/).map((c) => c.trim().replace(/\\\|/g, "|"));
      // The |---|---| rule under the header carries no content of its own.
      if (cells.every((c) => /^:?-{3,}:?$/.test(c))) continue;
      (table ??= []).push(cells);
      continue;
    }
    flushTable();
    if (heading) {
      flushParagraph();
      flushList();
      const level = heading[1].length;
      const size = level === 1 ? "text-2xl" : level === 2 ? "text-xl" : "text-lg";
      const Tag = (["h1", "h2", "h3"] as const)[level - 1];
      blocks.push(
        <Tag key={`h${blocks.length}`} className={`mb-3 mt-6 ${size}`}>
          {renderInline(heading[2], `h${blocks.length}`)}
        </Tag>,
      );
      continue;
    }
    if (bullet || numbered) {
      flushParagraph();
      const ordered = Boolean(numbered);
      if (!list || list.ordered !== ordered) {
        flushList();
        list = { ordered, items: [] };
      }
      list.items.push((bullet ?? numbered)![1]);
      continue;
    }
    if (list) {
      // A wrapped list item: the continuation belongs to the item above, not
      // to a paragraph of its own.
      list.items[list.items.length - 1] += ` ${line.trim()}`;
      continue;
    }
    paragraph.push(line.trim());
  }
  flushParagraph();
  flushList();
  flushTable();
  flushNotes();
  return blocks;
}
