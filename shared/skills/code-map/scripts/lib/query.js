'use strict';
// `show`: everything the map knows about a name – a file, function, class, route, UI route, HTTP
// call, table, column, model, environment variable, settings key or variable – with every link in
// and out and where it is. Output is plain text, capped per list so an agent can afford to read it.
// Part of the code-map skill (canonical copy: /shared/skills/code-map/).

const { natural } = require('./graph');
const { pathMatches } = require('./adapters/http');

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
  if (!hits.length) return `Nothing in the map is called "${term}". Unresolved items are listed by \`code-map report\`.`;
  const out = [];
  const byFrom = new Map(); const byTo = new Map();
  for (const e of map.graph.edges) {
    if (!byFrom.has(e.from)) byFrom.set(e.from, []);
    byFrom.get(e.from).push(e);
    if (!byTo.has(e.to)) byTo.set(e.to, []);
    byTo.get(e.to).push(e);
  }
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

module.exports = { show, find, label };
