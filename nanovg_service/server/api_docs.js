// Parse nanovg-api.md into queryable sections.
// Doc is sourced from BaiSiYeShou (TapTap-flavor NanoVG Lua bindings).
import fs from 'node:fs';

let cache = null;

function load(docPath) {
  if (cache && cache.path === docPath) return cache;
  const text = fs.readFileSync(docPath, 'utf8');
  // Split on `## ` H2 headings (keep order).
  const lines = text.split('\n');
  const sections = [];
  let cur = { title: '__preamble__', body: [] };
  for (const ln of lines) {
    const m = ln.match(/^##\s+(.+?)\s*$/);
    if (m) {
      if (cur.body.length) sections.push({ ...cur, body: cur.body.join('\n').trim() });
      cur = { title: m[1], body: [] };
    } else {
      cur.body.push(ln);
    }
  }
  if (cur.body.length) sections.push({ ...cur, body: cur.body.join('\n').trim() });
  cache = { path: docPath, text, sections };
  return cache;
}

export function listSections(docPath) {
  const { sections } = load(docPath);
  return sections
    .filter(s => s.title !== '__preamble__' && s.title !== '目录')
    .map(s => s.title);
}

export function getSection(docPath, title) {
  const { sections } = load(docPath);
  // exact match first, then case-insensitive prefix.
  const lc = title.toLowerCase();
  let s = sections.find(x => x.title === title);
  if (!s) s = sections.find(x => x.title.toLowerCase() === lc);
  if (!s) s = sections.find(x => x.title.toLowerCase().includes(lc));
  if (!s) return null;
  return `## ${s.title}\n\n${s.body}`;
}

export function query(docPath, q, { maxLines = 8 } = {}) {
  const { sections } = load(docPath);
  const needle = q.toLowerCase();
  const hits = [];
  for (const s of sections) {
    if (s.title === '__preamble__' || s.title === '目录') continue;
    const body = s.body;
    const lines = body.split('\n');
    const matches = [];
    for (let i = 0; i < lines.length; i++) {
      if (lines[i].toLowerCase().includes(needle)) matches.push(i);
    }
    if (matches.length === 0) continue;
    // Coalesce nearby matches into a snippet.
    const shown = new Set();
    const snippet = [];
    for (const m of matches.slice(0, maxLines)) {
      const lo = Math.max(0, m - 1);
      const hi = Math.min(lines.length - 1, m + 1);
      for (let i = lo; i <= hi; i++) if (!shown.has(i)) {
        shown.add(i);
        snippet.push(lines[i]);
      }
    }
    hits.push({ section: s.title, hits: matches.length, snippet: snippet.join('\n') });
  }
  hits.sort((a, b) => b.hits - a.hits);
  return hits;
}
