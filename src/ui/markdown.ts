/**
 * Just enough Markdown for INFO.md: headings, paragraphs, bullet and numbered lists, horizontal
 * rules, and the inline marks (`code`, **bold**, *italic*, [links](url)). Inline HTML such as
 * <kbd> passes through untouched: the file is part of the site, trusted like index.html.
 */

export interface RenderedMarkdown {
  /** The first level-1 heading, if any; it is left out of `html` so a dialog can use it as its title. */
  title: string | null;
  html: string;
}

const HEADING = /^(#{1,6})\s+(.+?)\s*#*\s*$/;
const BULLET = /^\s*[-*+]\s+(.*)$/;
const NUMBERED = /^\s*\d+[.)]\s+(.*)$/;
const RULE = /^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/;

export function inline(text: string): string {
  const codes: string[] = [];
  let out = text.replace(/`([^`]+)`/g, (_, code: string) => {
    codes.push(`<code>${code.replace(/&/g, '&amp;').replace(/</g, '&lt;')}</code>`);
    return `\u0000${codes.length - 1}\u0000`;
  });
  out = out
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, '<a href="$2">$1</a>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^\w*])\*([^*\s][^*]*?)\*(?!\w)/g, '$1<em>$2</em>')
    .replace(/(^|[^\w_])_([^_\s][^_]*?)_(?!\w)/g, '$1<em>$2</em>');
  return out.replace(/\u0000(\d+)\u0000/g, (_, i: string) => codes[Number(i)]);
}

/**
 * Headings below the title are shifted one level down (`##` → `<h3>`) so the dialog's own
 * `<h2>` title stays the top of the outline.
 */
export function renderMarkdown(source: string): RenderedMarkdown {
  let title: string | null = null;
  const html: string[] = [];
  let list: 'ul' | 'ol' | null = null;
  let paragraph: string[] = [];

  const closeList = () => {
    if (list) html.push(`</${list}>`);
    list = null;
  };
  const closeParagraph = () => {
    if (paragraph.length) html.push(`<p>${inline(paragraph.join(' '))}</p>`);
    paragraph = [];
  };
  const openList = (kind: 'ul' | 'ol') => {
    if (list !== kind) {
      closeList();
      html.push(`<${kind}>`);
      list = kind;
    }
  };

  for (const raw of source.split(/\r?\n/)) {
    const line = raw.trimEnd();
    if (!line.trim()) {
      closeParagraph();
      closeList();
      continue;
    }
    const heading = HEADING.exec(line);
    if (heading) {
      closeParagraph();
      closeList();
      const level = heading[1].length;
      if (level === 1 && title === null) {
        title = heading[2];
      } else {
        const tag = `h${Math.min(level + 1, 6)}`;
        html.push(`<${tag}>${inline(heading[2])}</${tag}>`);
      }
      continue;
    }
    if (RULE.test(line)) {
      closeParagraph();
      closeList();
      html.push('<hr>');
      continue;
    }
    const bullet = BULLET.exec(line);
    const numbered = bullet ? null : NUMBERED.exec(line);
    if (bullet || numbered) {
      closeParagraph();
      openList(bullet ? 'ul' : 'ol');
      html.push(`<li>${inline((bullet ?? numbered)![1])}</li>`);
      continue;
    }
    if (list) {
      // a wrapped list item continues the previous <li>
      const last = html.pop()!;
      html.push(last.replace(/<\/li>$/, ` ${inline(line.trim())}</li>`));
      continue;
    }
    paragraph.push(line.trim());
  }
  closeParagraph();
  closeList();
  return { title, html: html.join('\n') };
}
