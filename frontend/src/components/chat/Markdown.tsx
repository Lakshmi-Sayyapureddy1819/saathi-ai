import { Fragment, type ReactNode } from "react";

/** Minimal, safe markdown: paragraphs, headings, bullet/numbered lists, **bold**, *italic*, `code`. Builds React nodes only. */
export type Block =
  | { t: "p"; text: string }
  | { t: "h"; text: string }
  | { t: "ul"; items: string[] }
  | { t: "ol"; items: string[] };

export function parseBlocks(src: string): Block[] {
  const blocks: Block[] = [];
  let para: string[] = [];
  const flush = () => { if (para.length) { blocks.push({ t: "p", text: para.join("\n") }); para = []; } };
  for (const raw of src.replace(/\r\n/g, "\n").split("\n")) {
    const line = raw.trimEnd();
    const ul = /^\s*[-*•]\s+(.*)$/.exec(line);
    const ol = /^\s*\d+[.)]\s+(.*)$/.exec(line);
    const h = /^#{1,4}\s+(.*)$/.exec(line);
    if (!line.trim()) { flush(); continue; }
    if (h) { flush(); blocks.push({ t: "h", text: h[1]! }); continue; }
    if (ul || ol) {
      flush();
      const kind = ul ? "ul" : "ol";
      const last = blocks[blocks.length - 1];
      const text = (ul ?? ol)![1]!;
      if (last && last.t === kind) last.items.push(text); else blocks.push({ t: kind, items: [text] } as Block);
      continue;
    }
    para.push(line);
  }
  flush();
  return blocks;
}

const INLINE = /(\*\*[^*]+\*\*|\*[^*\s][^*]*\*|`[^`]+`)/g;
export function inline(text: string): ReactNode[] {
  return text.split(INLINE).filter((s) => s !== "").map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) return <strong key={i}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) return <code key={i}>{part.slice(1, -1)}</code>;
    if (part.startsWith("*") && part.endsWith("*") && part.length > 2) return <em key={i}>{part.slice(1, -1)}</em>;
    return <Fragment key={i}>{part.split("\n").map((l, j, a) => <Fragment key={j}>{l}{j < a.length - 1 && <br />}</Fragment>)}</Fragment>;
  });
}

export function Markdown({ text }: { text: string }) {
  return (
    <div className="md">
      {parseBlocks(text).map((b, i) =>
        b.t === "p" ? <p key={i}>{inline(b.text)}</p>
          : b.t === "h" ? <h4 key={i}>{inline(b.text)}</h4>
            : b.t === "ul" ? <ul key={i}>{b.items.map((x, j) => <li key={j}>{inline(x)}</li>)}</ul>
              : <ol key={i}>{b.items.map((x, j) => <li key={j}>{inline(x)}</li>)}</ol>)}
    </div>
  );
}
