/**
 * Clean raw Markdown passages for search-result display while preserving
 * character-level highlight offsets from the search index.
 *
 * The scanner walks the source once; every emitted character records the
 * original index it came from (or -1 for inserted placeholders), so
 * highlight ranges from the backend can be re-projected onto the cleaned
 * text without a re-index.
 */

export interface CleanedPassage {
  text: string;
  highlights: [number, number][];
}

// Matches, in order: images, links, html tags, emphasis runs, line-leading
// block markers (heading / blockquote / list), and finally unterminated
// images/links left behind when a passage window cuts syntax in half.
const TOKEN_RE = /!\[[^\]]*\]\([^)\n]*\)|\[([^\]\n]*)\]\([^)\n]*\)|<[^>\n]+>|[*_`~]{1,3}|^[ \t]*(?:#{1,6}[ \t]+|>[ \t]?|[-*+][ \t]+|\d+\.[ \t]+)|!\[[^\]]*\]\([^)\n]*$|\[([^\]\n]*)\]\([^)\n]*$/gm;

// Template metadata lines injected into captured articles; noise in snippets.
const METADATA_LINE_RE = /^[ \t]*(?:URL|Source|Platform|Author|Published|Captured|Type)\s*[:：]/i;

// Horizontal-rule-only lines.
const HR_LINE_RE = /^[ \t]*[-*_]{3,}[ \t]*$/;

export function cleanPassage(source: string, highlights: [number, number][], imagePlaceholder = "[图片]"): CleanedPassage {
  let out = "";
  const map: number[] = [];
  let lineStart = 0;
  let lastIndex = 0;

  const emitInserted = (text: string) => {
    for (let i = 0; i < text.length; i += 1) {
      out += text[i];
      map.push(-1);
    }
  };

  // Drop whole metadata lines before token scanning so "Platform: …" blocks
  // from the article header never reach the snippet.
  let filtered = "";
  const filteredMap: number[] = [];
  for (const line of source.split(/(?<=\n)/)) {
    lineStart = source.indexOf(line, lineStart);
    if (!METADATA_LINE_RE.test(line.replace(/^[ \t]*>[ \t]?/, "")) && !HR_LINE_RE.test(line.trimEnd())) {
      for (let i = 0; i < line.length; i += 1) {
        filtered += line[i];
        filteredMap.push(lineStart + i);
      }
    }
    lineStart += line.length;
  }

  const emitFilteredSlice = (start: number, end = filtered.length) => {
    for (let i = start; i < end; i += 1) {
      out += filtered[i];
      map.push(filteredMap[i]);
    }
  };

  for (const match of filtered.matchAll(TOKEN_RE)) {
    const start = match.index;
    emitFilteredSlice(lastIndex, start);
    const token = match[0];
    if (token.startsWith("![")) {
      emitInserted(imagePlaceholder);
    } else if ((match[1] !== undefined || match[2] !== undefined) && token.startsWith("[")) {
      // Inline link (terminated or truncated): keep the anchor text.
      const anchor = match[1] ?? match[2] ?? "";
      const labelOffset = token.indexOf("[") + 1;
      for (let i = 0; i < anchor.length; i += 1) {
        out += anchor[i];
        map.push(filteredMap[start + labelOffset + i]);
      }
    }
    // Emphasis runs, html tags and line-leading block markers are dropped.
    lastIndex = start + token.length;
  }
  emitFilteredSlice(lastIndex);

  // Re-project highlight ranges: an output char is highlighted when its
  // original index falls inside any source highlight range.
  const cleaned: [number, number][] = [];
  let runStart = -1;
  for (let i = 0; i <= map.length; i += 1) {
    const original = i < map.length ? map[i] : -1;
    const hit = original >= 0 && highlights.some(([s, e]) => original >= s && original < e);
    if (hit && runStart < 0) runStart = i;
    if (!hit && runStart >= 0) {
      cleaned.push([runStart, i]);
      runStart = -1;
    }
  }

  return { text: out, highlights: cleaned };
}
