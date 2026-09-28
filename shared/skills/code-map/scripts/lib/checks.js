'use strict';
// The checks: facts about the map that must hold. Each finding has a stable key, so problems that
// exist when a project adopts the code map are recorded once (known.json) and only new ones fail.
// Unresolved items never fail a check; they are listed so nobody mistakes them for a pass.
// Part of the code-map skill (canonical copy: /shared/skills/code-map/).

const A = require('./js/ast');
const { natural } = require('./graph');

// Every check, in the order the report lists them. `fails` says whether a new finding fails the run.
const CHECKS = [
  { id: 'size', title: 'Code files over the size limit may not grow', fails: true },
  { id: 'cycles', title: 'No import cycle among modules loaded at startup', fails: true },
  { id: 'interface', title: 'The public interface matches its committed record', fails: true },
  { id: 'http', title: 'Every UI call reaches a backend route', fails: true },
  { id: 'env', title: 'Every environment variable read is listed in an example env file', fails: true },
  { id: 'settings', title: 'Every settings key read has a default or is declared', fails: false },
  { id: 'columns', title: 'Code names only columns its models or tables define', fails: true },
];

function finding(check, key, file, line, message) {
  return { check, key: `${check}:${key}`, file: file || null, line: line || null, message };
}

// 1. Size ratchet. `sizes` holds the recorded size of each file that was over the limit.
function sizeCheck(map, records) {
  const limit = map.config.limits.fileLines;
  const out = [];
  for (const e of map.files) {
    if (!e.code || e.sizeExempt || !e.lines || e.lines <= limit) continue;
    const recorded = records.sizes[e.file];
    if (recorded === undefined) out.push(finding('size', e.file, e.file, null, `${e.lines} lines, over the ${limit}-line limit`));
    else if (e.lines > recorded) out.push(finding('size', e.file, e.file, null, `grew from its recorded ${recorded} lines to ${e.lines}`));
  }
  return out;
}

// 2. Cycles among files that import each other at startup (a require inside a function is not one).
function cycleCheck(map) {
  const adj = new Map();
  for (const e of map.graph.edgesOf('imports')) {
    if (e.load !== 'startup' || e.typeOnly || !e.to.startsWith('file:')) continue;
    if (!adj.has(e.from)) adj.set(e.from, new Set());
    adj.get(e.from).add(e.to);
  }
  // Tarjan's strongly connected components, iterative.
  let index = 0;
  const idx = new Map(); const low = new Map(); const onStack = new Set(); const stack = []; const sccs = [];
  for (const start of [...adj.keys()].sort(natural)) {
    if (idx.has(start)) continue;
    const work = [[start, [...(adj.get(start) || [])].sort(natural), 0]];
    idx.set(start, index); low.set(start, index); index++; stack.push(start); onStack.add(start);
    while (work.length) {
      const top = work[work.length - 1];
      const [v, next] = top;
      if (top[2] < next.length) {
        const w = next[top[2]++];
        if (!idx.has(w)) {
          idx.set(w, index); low.set(w, index); index++; stack.push(w); onStack.add(w);
          work.push([w, [...(adj.get(w) || [])].sort(natural), 0]);
        } else if (onStack.has(w)) low.set(v, Math.min(low.get(v), idx.get(w)));
      } else {
        work.pop();
        if (work.length) { const u = work[work.length - 1][0]; low.set(u, Math.min(low.get(u), low.get(v))); }
        if (low.get(v) === idx.get(v)) {
          const scc = [];
          let w;
          do { w = stack.pop(); onStack.delete(w); scc.push(w); } while (w !== v);
          const self = scc.length === 1 && (adj.get(v) || new Set()).has(v);
          if (scc.length > 1 || self) sccs.push(scc.map((id) => id.slice(5)).sort(natural));
        }
      }
    }
  }
  return sccs.map((files) => finding('cycles', files.join(' <> '), files[0], null, `${files.length} files load each other at startup: ${files.join(', ')}`));
}

// 3. The public interface: exports, class methods, and routes and middleware in registration order.
function interfaceOf(map) {
  const files = {};
  const add = (file, key, value) => { (files[file] = files[file] || {})[key] = value; };
  for (const facts of map.project.facts.values()) {
    if ((map.fileIndex.get(facts.file) || {}).test) continue;
    const names = new Set(facts.exports.named.keys());
    if (facts.exports.default) names.add('default');
    const cjs = facts.exports.cjsDefault && A.unwrap(facts.exports.cjsDefault.node);
    if (cjs && cjs.type === 'ObjectExpression') {
      for (const p of cjs.properties) { const k = p.type === 'SpreadElement' ? '...' : A.keyName(p.key, p.computed); if (k) names.add(k); }
    } else if (cjs) names.add('module.exports');
    if (names.size) add(facts.file, 'exports', [...names].sort(natural));
    const classes = {};
    for (const c of facts.classes) classes[c.name] = c.methods.map((m) => m.name).sort(natural);
    if (Object.keys(classes).length) add(facts.file, 'classes', classes);
  }
  for (const r of map.ctx.routerOrder || []) {
    if (!r.entries.length) continue;
    const entries = r.entries.map((e) => (e.kind === 'route' ? `${e.method} ${e.path}` : `${e.kind} ${e.prefix} ${e.label}`));
    add(r.file, `router ${r.name}`, entries);
  }
  const sorted = {};
  for (const f of Object.keys(files).sort(natural)) sorted[f] = files[f];
  return sorted;
}

function interfaceCheck(map, records) {
  if (!records.interface) return [];
  const now = interfaceOf(map);
  const was = records.interface;
  const out = [];
  for (const file of [...new Set([...Object.keys(now), ...Object.keys(was)])].sort(natural)) {
    const a = JSON.stringify(was[file] || null);
    const b = JSON.stringify(now[file] || null);
    if (a === b) continue;
    const parts = [];
    const keys = new Set([...Object.keys(was[file] || {}), ...Object.keys(now[file] || {})]);
    for (const k of [...keys].sort(natural)) {
      const before = (was[file] || {})[k];
      const after = (now[file] || {})[k];
      if (JSON.stringify(before) === JSON.stringify(after)) continue;
      const flat = (v) => (Array.isArray(v) ? v : v ? Object.entries(v).map(([c, m]) => `${c}(${m.join(', ')})`) : []);
      const added = flat(after).filter((x) => !flat(before).includes(x));
      const removed = flat(before).filter((x) => !flat(after).includes(x));
      const moved = !added.length && !removed.length ? ' (same entries, new order)' : '';
      parts.push(`${k}: ${added.length ? `+${added.join(', +')}` : ''}${added.length && removed.length ? ' ' : ''}${removed.length ? `-${removed.join(', -')}` : ''}${moved}`);
    }
    out.push(finding('interface', file, file, null, `changed without updating the record – ${parts.join('; ')}`));
  }
  return out;
}

// 4. UI calls that match no backend route. Calls from tests are not the product's own UI.
function httpCheck(map) {
  if (!map.ctx.routes.length) return [];
  return map.ctx.httpCalls.filter((c) => !c.test && c.url !== undefined && !c.matches.length)
    .map((c) => finding('http', `${c.method} ${c.url} @${c.file}`, c.file, c.line, `${c.method} ${c.url} matches no backend route`));
}

// 5. Environment variables read by the product that no example env file lists.
function envCheck(map) {
  if (!map.ctx.envFiles || !map.ctx.envFiles.length) return [];
  const seen = new Map();
  for (const r of map.ctx.envReads) {
    if (r.test || map.ctx.envDeclared.has(r.name) || seen.has(r.name)) continue;
    seen.set(r.name, r);
  }
  return [...seen.values()].map((r) => finding('env', r.name, r.file, r.line, `${r.name} is read but not listed in ${map.ctx.envFiles.join(', ')}`));
}

// 6. Settings keys read with no default and no declaration. Reports only, unless the project enforces it.
function settingsCheck(map) {
  const seen = new Map();
  for (const r of map.ctx.settingsReads) {
    if (r.test || seen.has(r.key)) continue;
    const node = map.graph.nodes.get(`setting:${r.key}`);
    if (node && !node.defined) seen.set(r.key, r);
  }
  return [...seen.values()].map((r) => finding('settings', r.key, r.file, r.line, `settings key ${r.key} has no default and is not declared`));
}

// 7. Columns named through a model or in SQL that the model or table does not define. A model may be
// named by attribute or by column (`createdAt` or `created_at` when underscored). Migrations are left
// out: they work on the schema's history, including columns the current models no longer have.
const MIGRATION = /(^|\/)(migrations?|seeders?)\//;
function columnCheck(map) {
  const db = map.ctx.db;
  const out = new Map();
  for (const r of db.refs) {
    if ((map.fileIndex.get(r.file) || {}).test || MIGRATION.test(r.file)) continue;
    if (r.model && r.attr) {
      const m = db.models.get(r.model);
      const columns = m && m.attributes ? new Set([...m.attributes.values()].map((a) => a.column).filter(Boolean)) : new Set();
      if (m && m.attributes && m.attributes.size && !m.attributes.has(r.attr) && !columns.has(r.attr)) {
        const k = `${r.model}.${r.attr} @${r.file}`;
        if (!out.has(k)) out.set(k, finding('columns', k, r.file, r.line, `${r.model} has no attribute ${r.attr}`));
      }
    } else if (r.table && r.column) {
      const t = db.declared.get(r.table.toLowerCase());
      if (t && t.columns.size && !t.columns.has(r.column.toLowerCase())) {
        const k = `${t.name}.${r.column} @${r.file}`;
        if (!out.has(k)) out.set(k, finding('columns', k, r.file, r.line, `table ${t.name} has no column ${r.column}`));
      }
    }
  }
  return [...out.values()];
}

// Runs every check. `records` = { sizes, interface, known }; returns findings split into new and known.
function runChecks(map, records, only = null) {
  const settingsFail = !!(map.config.settings && map.config.settings.enforce);
  const all = [
    ...sizeCheck(map, records), ...cycleCheck(map), ...interfaceCheck(map, records), ...httpCheck(map),
    ...envCheck(map), ...settingsCheck(map), ...columnCheck(map),
  ].filter((f) => !only || only.includes(f.check));
  const known = new Set(records.known || []);
  const byCheck = {};
  for (const c of CHECKS) {
    const list = all.filter((f) => f.check === c.id).sort((a, b) => natural(a.key, b.key));
    const fails = c.id === 'settings' ? settingsFail : c.fails;
    byCheck[c.id] = { title: c.title, fails, findings: list, new: list.filter((f) => !known.has(f.key)) };
  }
  const present = new Set(all.map((f) => f.key));
  const fixed = [...known].filter((k) => !present.has(k)).sort(natural);
  const failing = Object.values(byCheck).filter((c) => c.fails).flatMap((c) => c.new);
  return { byCheck, all, fixed, failing, ok: failing.length === 0 };
}

module.exports = { CHECKS, runChecks, interfaceOf };
