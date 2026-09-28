'use strict';
// `show`: everything the map knows about a name – a file, function, class, route, UI route, HTTP
// call, table, column, model, environment variable, settings key or variable – with every link in
// and out and where it is. Output is plain text, capped per list so an agent can afford to read it.
// Part of the code-map skill (canonical copy: /shared/skills/code-map/).

const { natural } = require('./graph');
const { pathMatches } = require('./adapters/http');
const { readText } = require('./files');

const LIMIT = 40;

function label(n) {
  if (!n) return '?';
  switch (n.type) {
    case 'file': return `file ${n.path} (${n.lines} lines${n.test ? ', test' : ''})`;
    case 'function': return `function ${n.qualified || n.name}  ${n.file}:${n.line}-${n.endLine}`;
    case 'class': return `class ${n.name}  ${n.file}:${n.line}`;
    case 'variable': return `variable ${n.name} (${n.kind || 'file-level'})  ${n.file}:${n.line}`;
    case 'route': return `route ${n.method} ${n.path || `${n.localPath} (not mounted)`}  ${n.file}:${n.line}`;
    case 'ui-route': return `UI route ${n.path}  ${n.file || ''}`;
    case 'http-call': return `HTTP call ${n.method || ''} ${n.url || n.external || `(unresolved: ${n.unresolved})`}  ${n.file}:${n.line}`;
    case 'router': return `router ${n.name}  ${n.file}:${n.line}${n.mountedAt && n.mountedAt.length ? ` at ${n.mountedAt.join(', ')}` : ''}`;
    case 'table': return `table ${n.name}`;
    case 'column': return `column ${n.table}.${n.name}`;
    case 'model': return `model ${n.name} → table ${n.table || '?'}  ${n.file}:${n.line}`;
    case 'env': return `environment variable ${n.name}${n.declared ? '' : ' (not in an example env file)'}`;
    case 'setting': return `settings key ${n.key}${n.defined ? '' : ' (no default, not declared)'}`;
    case 'package': return `package ${n.name}`;
    case 'message': return `message ${n.name}`;
    case 'field': return `field ${n.path}`;
    default: return `${n.type} ${n.id}`;
  }
}

function where(e, other) {
  const file = e.file || (other && (other.file || other.path));
  return e.line ? `  (${file ? `${file}:` : 'line '}${e.line})` : '';
}

// Nodes a term names. Exact matches win; a path-like term also matches routes by pattern.
function find(map, term) {
  const t = term.toLowerCase();
  const nodes = [...map.graph.nodes.values()];
  const keyOf = (n) => [n.path, n.name, n.qualified, n.key, n.url, n.table && n.name ? `${n.table}.${n.name}` : null,
    n.method && n.path ? `${n.method} ${n.path}` : null].filter(Boolean).map((s) => String(s).toLowerCase());
  let hits = nodes.filter((n) => keyOf(n).includes(t));
  if (!hits.length && term.startsWith('/')) hits = nodes.filter((n) => (n.type === 'route' || n.type === 'ui-route') && n.path && pathMatches(n.path, term));
  if (!hits.length) hits = nodes.filter((n) => n.type !== 'http-call' && keyOf(n).some((k) => k.endsWith(`/${t}`) || k.endsWith(`.${t}`) || k.endsWith(`#${t}`)));
  if (!hits.length) hits = nodes.filter((n) => n.type !== 'http-call' && keyOf(n).some((k) => k.includes(t)));
  return hits.sort((a, b) => natural(a.type, b.type) || natural(a.id, b.id));
}

function show(map, term, { limit = LIMIT } = {}) {
  const hits = find(map, term);
  if (!hits.length) return `Nothing in the map is called "${term}", so here is a word search instead.\n\n${findWords(map, term)}`;
  const out = [];
  const byFrom = new Map(); const byTo = new Map();
  for (const e of map.graph.edges) {
    if (!byFrom.has(e.from)) byFrom.set(e.from, []);
    byFrom.get(e.from).push(e);
    if (!byTo.has(e.to)) byTo.set(e.to, []);
    byTo.get(e.to).push(e);
  }
  const fields = hits.filter((n) => n.type === 'field');
  if (fields.length && fields.length === hits.length) return fieldSummary(map, fields, byFrom, byTo, limit);
  const shown = hits.slice(0, 12);
  if (hits.length > shown.length) out.push(`${hits.length} matches; the first ${shown.length} are shown. Use a fuller name to narrow.`);
  for (const n of shown) {
    out.push('', `== ${label(n)}`);
    const groups = new Map();
    for (const e of byFrom.get(n.id) || []) {
      if (n.type === 'file' && e.type === 'contains') continue;
      const k = `${e.type} →`;
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k).push(`${label(map.graph.nodes.get(e.to))}${where(e, n)}`);
    }
    for (const e of byTo.get(n.id) || []) {
      if (e.type === 'contains') continue;
      const k = `← ${e.type}`;
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k).push(`${label(map.graph.nodes.get(e.from))}${where(e)}`);
    }
    if (n.type === 'file') {
      const inner = (byFrom.get(n.id) || []).filter((e) => e.type === 'contains').map((e) => map.graph.nodes.get(e.to)).filter(Boolean);
      const fns = inner.filter((x) => x.type === 'function').sort((a, b) => a.line - b.line);
      if (fns.length) groups.set('functions', fns.map((f) => `${f.qualified || f.name}  ${f.line}-${f.endLine}`));
      const other = inner.filter((x) => !['function', 'http-call'].includes(x.type));
      if (other.length) groups.set('also contains', other.map(label));
    }
    for (const [k, list] of [...groups.entries()].sort((a, b) => natural(a[0], b[0]))) {
      const uniq = [...new Set(list)].sort(natural);
      out.push(`  ${k} (${uniq.length})`);
      for (const line of uniq.slice(0, limit)) out.push(`    ${line}`);
      if (uniq.length > limit) out.push(`    … ${uniq.length - limit} more`);
    }
    if (n.type === 'route' && !(byTo.get(n.id) || []).some((e) => e.type === 'requests')) out.push('  no UI call in the map reaches this route (calls through variables are listed as unresolved)');
  }
  return out.join('\n');
}

// A field: where it is read and set, the values it is compared with, its defaults, where the object
// it hangs off comes from, and whether anything in the repository sets it at all.
function fieldSummary(map, fields, byFrom, byTo, limit) {
  const out = [];
  const at = (e) => `${e.file}:${e.line}${e.template ? ` (${e.template} template)` : ''}${e.test ? ' (test)' : ''}`;
  for (const n of fields.slice(0, 8)) {
    const inEdges = byTo.get(n.id) || [];
    const reads = inEdges.filter((e) => e.type === 'reads-field');
    const writes = inEdges.filter((e) => e.type === 'writes-field');
    const declared = inEdges.filter((e) => e.type === 'declares-field');
    const values = new Map(); const defaults = new Map(); const origins = new Map();
    for (const e of [...reads, ...writes]) {
      for (const v of e.compared || []) values.set(JSON.stringify(v), (values.get(JSON.stringify(v)) || 0) + 1);
      if (e.fallback !== undefined) defaults.set(JSON.stringify(e.fallback), at(e));
      if (e.origin) origins.set(e.origin, at(e));
    }
    out.push('', `== field ${n.path}`);
    const list = (title, items) => {
      if (!items.length) return;
      const uniq = [...new Set(items)].sort(natural);
      out.push(`  ${title} (${uniq.length})`);
      for (const x of uniq.slice(0, limit)) out.push(`    ${x}`);
      if (uniq.length > limit) out.push(`    … ${uniq.length - limit} more`);
    };
    list('read at', reads.map(at));
    list('set at', writes.map((e) => `${at(e)}${e.literal ? ' (object literal)' : ''}${e.compared ? ` = ${e.compared.map((v) => JSON.stringify(v)).join(', ')}` : ''}`));
    if (values.size) out.push(`  compared with: ${[...values.entries()].map(([v, c]) => `${v} (${c})`).join(', ')}`);
    if (defaults.size) out.push(`  defaults to: ${[...defaults.entries()].map(([v, w]) => `${v} at ${w}`).join('; ')}`);
    list('the object it is read from', [...origins.entries()].map(([o, w]) => `${o}   (${w})`));
    list('declared in', declared.map((e) => e.file));
    if (!writes.some((e) => !e.test) && !declared.length) out.push('  NOT SET anywhere in this repository: its value comes from outside the code (stored data, a request, another system). Look where the object above is loaded.');
  }
  if (fields.length > 8) out.push('', `${fields.length - 8} more fields share this name; use a fuller path.`);
  return out.join('\n');
}

// Word search: functions (and template or data files) whose text holds the most of the words, by
// identifier parts (stcRebate is "stc" and "rebate"), strings and comments. Text matches, ranked by
// how many words meet in one function; never turned into links.
function words(text) {
  return text.replace(/([a-z0-9])([A-Z])/g, '$1 $2').replace(/([A-Z])([A-Z][a-z])/g, '$1 $2').toLowerCase().split(/[^a-z0-9]+/).filter(Boolean);
}

function findWords(map, query, { top = 10 } = {}) {
  const wanted = [...new Set(words(query))].filter((w) => w.length >= 2);
  if (!wanted.length) return 'Name at least one word to search for.';
  const units = [];
  const fnsByFile = new Map();
  for (const n of map.graph.ofType('function')) {
    if (!n.file || !n.line || !n.endLine) continue;
    if (!fnsByFile.has(n.file)) fnsByFile.set(n.file, []);
    fnsByFile.get(n.file).push(n);
  }
  for (const e of map.files) {
    if ((!e.code && !['ejs', 'hbs', 'handlebars', 'njk', 'jinja', 'j2', 'liquid', 'json', 'md'].includes(e.ext)) || e.lines > 20000) continue;
    const text = readText(map.root, e);
    if (!text) continue;
    const lines = text.split('\n');
    const fns = fnsByFile.get(e.file) || [];
    const spans = fns.length ? fns.map((f) => ({ name: f.qualified || f.name, from: f.line, to: f.endLine })) : [{ name: null, from: 1, to: lines.length }];
    for (const sp of spans) {
      const hits = new Map();
      for (let i = sp.from; i <= sp.to && i <= lines.length; i++) {
        const ws = words(lines[i - 1]);
        for (const w of wanted) if (!hits.has(w) && ws.some((x) => x === w || (w.length >= 3 && x.startsWith(w)))) hits.set(w, i);
      }
      if (hits.size) units.push({ file: e.file, test: e.test, ...sp, hits, lines });
    }
  }
  units.sort((a, b) => b.hits.size - a.hits.size || (a.test ? 1 : 0) - (b.test ? 1 : 0) || (a.to - a.from) - (b.to - b.from) || natural(a.file, b.file));
  const best = units.filter((u) => u.hits.size === units[0]?.hits.size).length;
  const out = [`Word search for ${wanted.join(', ')}: text matches, ranked by how many of the words meet in one function (smaller first). ${units.length} place(s) hold at least one word; ${best} hold the most.`];
  for (const u of units.slice(0, top)) {
    out.push('', `== ${u.hits.size}/${wanted.length}  ${u.file}:${u.from}-${u.to}${u.name ? `  ${u.name}` : ''}${u.test ? '  (test)' : ''}`);
    for (const [w, line] of [...u.hits.entries()].sort((a, b) => a[1] - b[1])) out.push(`    ${line}: ${u.lines[line - 1].trim().slice(0, 110)}   [${w}]`);
  }
  return out.join('\n');
}

module.exports = { show, find, label, findWords };
