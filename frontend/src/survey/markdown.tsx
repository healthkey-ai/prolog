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
 * links, bold and italic. Anything else renders as the text it is written as,
 * which for a notice is a readable failure rather than a broken one.
 */

const INLINE = /(\[[^\]]+\]\([^)\s]+\))|(\*\*[^*]+\*\*)|(\*[^*]+\*)/g;

/** Only http(s) links become links; anything else stays as text (javascript:, data:). */
function safeHref(href: string): string | null {
  try {
    const url = new URL(href, "https://example.invalid");
    return url.protocol === "http:" || url.protocol === "https:" ? href : null;
  } catch {
    return null;
  }
}

export function renderInline(text: string, keyPrefix = ""): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  let match: RegExpExecArray | null;
  INLINE.lastIndex = 0;
  while ((match = INLINE.exec(text)) !== null) {
    if (match.index > last) out.push(text.slice(last, match.index));
    const token = match[0];
    const key = `${keyPrefix}-${match.index}`;
    if (token.startsWith("[")) {
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

export function renderMarkdown(source: string): ReactNode[] {
  const blocks: ReactNode[] = [];
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  let paragraph: string[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;

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

    if (!line.trim()) {
      flushParagraph();
      flushList();
      continue;
    }
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
    flushList();
    paragraph.push(line.trim());
  }
  flushParagraph();
  flushList();
  return blocks;
}
