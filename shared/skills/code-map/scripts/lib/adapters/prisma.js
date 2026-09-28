'use strict';
// Prisma: models and fields from schema.prisma (with @map / @@map column and table names), the
// datasource's dialect, the schema the migration.sql files build in order, and prisma client calls
// (where, select, include, orderBy, data). Part of the code-map skill
// (canonical copy: /shared/skills/code-map/).

const A = require('../js/ast');
const { readText } = require('../files');
const { analyse } = require('../sql');

const OPS = new Set(['findUnique', 'findUniqueOrThrow', 'findFirst', 'findFirstOrThrow', 'findMany', 'count', 'aggregate', 'groupBy',
  'create', 'createMany', 'createManyAndReturn', 'update', 'updateMany', 'updateManyAndReturn', 'upsert', 'delete', 'deleteMany']);
const READS = new Set(['findUnique', 'findUniqueOrThrow', 'findFirst', 'findFirstOrThrow', 'findMany', 'count', 'aggregate', 'groupBy']);
const FILTER_KEYS = new Set(['AND', 'OR', 'NOT', 'some', 'every', 'none', 'is', 'isNot']);

function parseSchema(text) {
  const clean = text.replace(/\/\/[^\n]*/g, '');
  const out = { provider: null, models: [] };
  const block = /^\s*(model|view|datasource|enum|type)\s+(\w+)\s*\{([\s\S]*?)^\s*\}/gm;
  let m;
  const raw = [];
  while ((m = block.exec(clean))) raw.push({ kind: m[1], name: m[2], body: m[3], line: clean.slice(0, m.index).split('\n').length + 1 });
  const modelNames = new Set(raw.filter((b) => b.kind === 'model' || b.kind === 'view').map((b) => b.name));
  for (const b of raw) {
    if (b.kind === 'datasource') {
      const p = /provider\s*=\s*"([^"]+)"/.exec(b.body);
      if (p) out.provider = p[1];
      continue;
    }
    if (b.kind !== 'model' && b.kind !== 'view') continue;
    const map = /@@map\(\s*(?:name:\s*)?"([^"]+)"/.exec(b.body);
    const model = { name: b.name, table: map ? map[1] : b.name, line: b.line, fields: [] };
    b.body.split('\n').forEach((lineText, i) => {
      const f = /^\s*(\w+)\s+(\w+)(\[\])?(\?)?(.*)$/.exec(lineText);
      if (!f || lineText.trim().startsWith('@@')) return;
      const attrs = f[5] || '';
      if (/@ignore\b/.test(attrs)) return;
      const colMap = /@map\(\s*(?:name:\s*)?"([^"]+)"/.exec(attrs);
      const relation = modelNames.has(f[2]);
      model.fields.push({ name: f[1], type: f[2], list: !!f[3], relation, column: relation ? null : (colMap ? colMap[1] : f[1]), line: b.line + i });
    });
    out.models.push(model);
  }
  return out;
}

const PROVIDER_DIALECT = { postgresql: 'postgresql', postgres: 'postgresql', cockroachdb: 'postgresql', mysql: 'mysql', sqlite: 'sqlite', sqlserver: 'mssql' };

function prismaAdapter(ctx) {
  const { project, db, graph, config } = ctx;
  const schemas = ctx.files.filter((e) => e.ext === 'prisma');
  if (!schemas.length) { graph.cover('orm:prisma', 'not used', {}); return; }
  const models = new Map(); // accessor (lowerFirst) -> model
  let dialect = null;
  for (const entry of schemas) {
    const text = readText(ctx.root, entry);
    if (!text) continue;
    const parsed = parseSchema(text);
    if (parsed.provider) dialect = PROVIDER_DIALECT[parsed.provider] || dialect;
    for (const pm of parsed.models) {
      const m = db.model(pm.name, 'prisma', pm.table, entry.file, pm.line);
      m.fields = new Map(pm.fields.map((f) => [f.name, f]));
      for (const f of pm.fields) {
        if (f.relation) { graph.edge('relates', `model:${pm.name}`, `model:${f.type}`, { kind: f.list ? 'hasMany' : 'relation', file: entry.file, line: f.line }); m.attributes.set(f.name, { column: null, relation: f.type }); } else db.attribute(m, f.name, f.column);
      }
      models.set(pm.name[0].toLowerCase() + pm.name.slice(1), m);
    }
  }
  if (dialect && !ctx.dialectDeclared) ctx.dialect = ctx.dialect || dialect;

  // migration.sql files, in folder order.
  const migrations = ctx.files.filter((e) => /(^|\/)migrations\/[^/]+\/migration\.sql$/.test(e.file)).sort((a, b) => (a.file < b.file ? -1 : 1));
  for (const entry of migrations) {
    const text = readText(ctx.root, entry);
    if (!text) continue;
    const r = analyse(text, dialect || ctx.dialect);
    if (r.ddl) db.applyDdl(db.migrated, r.ddl, 'migration', entry.file, 1);
    if (r.error && !r.missing) graph.unresolvedItem('migration', entry.file, 1, 'migration.sql', r.error);
    entry.migrationRead = true;
  }

  // Client calls: prisma.<model>.<op>({ ... }).
  const clients = new Set(config.prisma.clients || []);
  let calls = 0;
  for (const facts of project.facts.values()) {
    for (const site of facts.callSites) {
      if (site.rootType !== 'id' || !clients.has(site.rootName) || site.path.length !== 2) continue;
      const m = models.get(site.path[0]);
      const op = site.path[1];
      if (!m || !OPS.has(op)) continue;
      calls++;
      const add = (model, field, access) => { if (field) db.ref({ via: 'prisma', model: model.name, attr: field, access, file: facts.file, line: site.line, owner: site.owner }); };
      const walkKeys = (node, model, access, depth = 0) => {
        node = A.unwrap(node);
        if (!node || depth > 6) return;
        if (node.type === 'ArrayExpression') { node.elements.forEach((e) => walkKeys(e, model, access, depth + 1)); return; }
        if (node.type !== 'ObjectExpression') return;
        for (const p of node.properties) {
          if (p.type !== 'ObjectProperty') continue;
          const key = A.keyName(p.key, p.computed);
          if (!key || key.startsWith('_')) continue;
          if (FILTER_KEYS.has(key)) { walkKeys(p.value, model, access, depth + 1); continue; }
          add(model, key, access);
          const f = model.fields && model.fields.get(key);
          if (f && f.relation) {
            const target = [...db.models.values()].find((x) => x.name === f.type);
            if (target) walkKeys(p.value, target, access, depth + 1);
          }
        }
      };
      const args = new Map();
      const a0 = site.args[0] && A.unwrap(site.args[0]);
      if (a0 && a0.type === 'ObjectExpression') for (const p of a0.properties) if (p.type === 'ObjectProperty') args.set(A.keyName(p.key, p.computed), p.value);
      for (const k of ['where', 'select', 'include', 'orderBy', 'cursor', 'having', 'omit']) if (args.get(k)) walkKeys(args.get(k), m, 'read');
      const by = args.get('by') && A.unwrap(args.get('by'));
      if (by && by.type === 'ArrayExpression') by.elements.forEach((e) => e && A.unwrap(e).type === 'StringLiteral' && add(m, A.unwrap(e).value, 'read'));
      const distinct = args.get('distinct') && A.unwrap(args.get('distinct'));
      if (distinct && distinct.type === 'ArrayExpression') distinct.elements.forEach((e) => e && A.unwrap(e).type === 'StringLiteral' && add(m, A.unwrap(e).value, 'read'));
      for (const k of ['data', 'create', 'update']) if (args.get(k)) walkKeys(args.get(k), m, 'write');
      if (READS.has(op) && !args.size) db.ref({ via: 'prisma', model: m.name, access: 'read', file: facts.file, line: site.line, owner: site.owner });
      if (op.startsWith('delete')) db.ref({ via: 'prisma', model: m.name, access: 'delete', file: facts.file, line: site.line, owner: site.owner });
    }
  }
  graph.cover('orm:prisma', 'mapped', { schemas: schemas.length, models: models.size, migrations: migrations.length, calls, dialect });
}

module.exports = { prismaAdapter, parseSchema };
