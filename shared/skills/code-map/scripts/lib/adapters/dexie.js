'use strict';
// Dexie (IndexedDB in the browser): the tables and indexes declared with version(n).stores({...}),
// and the table calls in code. where() and orderBy() need an index, so a field used there that no
// store declares is a real error. Part of the code-map skill (canonical copy: /shared/skills/code-map/).

const A = require('../js/ast');

const OPS = { where: 'read', get: 'read', bulkGet: 'read', toArray: 'read', orderBy: 'read', filter: 'read', count: 'read',
  each: 'read', toCollection: 'read', limit: 'read', offset: 'read', reverse: 'read', first: 'read', last: 'read',
  put: 'write', add: 'write', bulkPut: 'write', bulkAdd: 'write', update: 'write', bulkUpdate: 'write', delete: 'delete',
  bulkDelete: 'delete', clear: 'delete' };

function fieldsOf(spec) {
  return spec.split(',').map((s) => s.trim().replace(/^(\+\+|&|\*)/, '')).filter(Boolean)
    .flatMap((s) => (s.startsWith('[') ? s.slice(1, -1).split('+') : [s]));
}

function dexieAdapter(ctx) {
  const { project, db, graph } = ctx;
  const tables = new Map(); // table -> Set(fields)
  let usesDexie = false;
  for (const facts of project.facts.values()) {
    if (!facts.imports.some((i) => i.source === 'dexie')) continue;
    usesDexie = true;
    for (const site of facts.callSites) {
      if (site.path[site.path.length - 1] !== 'stores' || !site.args[0]) continue;
      const obj = A.unwrap(site.args[0]);
      if (obj.type !== 'ObjectExpression') continue;
      for (const p of obj.properties) {
        if (p.type !== 'ObjectProperty') continue;
        const table = A.keyName(p.key, p.computed);
        const spec = A.staticString(p.value);
        if (!table) continue;
        if (!tables.has(table)) tables.set(table, new Set());
        const t = db.table(db.declared, table, 'dexie', facts.file, site.line);
        t.dexie = true;
        if (spec === null) { t.dropped = true; continue; }
        for (const f of fieldsOf(spec)) { tables.get(table).add(f); db.column(db.declared, table, f, 'dexie', facts.file, site.line); }
      }
    }
  }
  if (!usesDexie) { graph.cover('database:dexie', 'not used', {}); return; }
  let calls = 0;
  for (const facts of project.facts.values()) {
    for (const site of facts.callSites) {
      // <db>.<table>.<op>(...) or this.<table>.<op>(...)
      const i = site.path.findIndex((p) => tables.has(p));
      if (i < 0 || i + 1 >= site.path.length) continue;
      const table = site.path[i];
      const op = site.path[i + 1];
      if (!OPS[op]) continue;
      calls++;
      db.ref({ via: 'dexie', table, access: OPS[op], file: facts.file, line: site.line, owner: site.owner });
      if ((op === 'where' || op === 'orderBy') && site.args[0]) {
        const a = A.unwrap(site.args[0]);
        const fields = a.type === 'StringLiteral' ? [a.value] : a.type === 'ObjectExpression' ? a.properties.map((p) => A.keyName(p.key, p.computed)).filter(Boolean) : [];
        for (const f of fields.flatMap((x) => (x.startsWith('[') ? x.slice(1, -1).split('+') : [x]))) db.ref({ via: 'dexie', table, column: f, access: 'read', index: true, file: facts.file, line: site.line, owner: site.owner });
      }
    }
  }
  graph.cover('database:dexie', 'mapped', { tables: tables.size, calls });
}

module.exports = { dexieAdapter };
