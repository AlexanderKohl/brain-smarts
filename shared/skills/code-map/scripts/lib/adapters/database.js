'use strict';
// The database as the code declares it and uses it. Schema sources (Sequelize models, Prisma schema,
// Dexie stores, migrations, CREATE TABLE in .sql files or in code) and references (model calls,
// Prisma calls, raw SQL) are collected here and turned into table and column nodes.
// Part of the code-map skill (canonical copy: /shared/skills/code-map/).

const A = require('../js/ast');
const { analyse, looksLikeSql, placeholder } = require('../sql');

class Database {
  constructor(graph) {
    this.graph = graph;
    this.declared = new Map(); // table(lower) -> { name, columns: Map(lower -> {name, sources}), sources: Set }
    this.migrated = new Map(); // table(lower) -> { name, columns: Map }, by framework
    this.models = new Map(); // model name -> { framework, table, attributes: Map(attr -> column), file, line }
    this.refs = []; // { via, model?, table?, column?, attr?, access, file, line, owner }
    this.sqlErrors = 0;
    this.sqlCount = 0;
    this.sqlMissing = false;
  }

  table(store, name, source, file, line) {
    const key = String(name).toLowerCase();
    if (!store.has(key)) store.set(key, { name, columns: new Map(), sources: new Set(), files: new Set() });
    const t = store.get(key);
    t.sources.add(source);
    if (file) t.files.add(file);
    if (store === this.declared) {
      this.graph.node(`table:${t.name}`, 'table', { name: t.name });
      if (file) this.graph.edge('declares', `file:${file}`, `table:${t.name}`, { line });
    }
    return t;
  }

  column(store, tableName, column, source, file, line) {
    const t = this.table(store, tableName, source, file, line);
    const key = String(column).toLowerCase();
    if (!t.columns.has(key)) t.columns.set(key, { name: column, sources: new Set() });
    t.columns.get(key).sources.add(source);
    if (store === this.declared) {
      const id = `column:${t.name}.${column}`;
      this.graph.node(id, 'column', { table: t.name, name: column });
      this.graph.edge('has', `table:${t.name}`, id);
    }
  }

  // Applies CREATE / ALTER / DROP operations to a schema store, in order.
  applyDdl(store, ops, source, file, line) {
    for (const op of ops) {
      if (op.op === 'create') { this.table(store, op.table, source, file, line); for (const c of op.columns) this.column(store, op.table, c, source, file, line); }
      else if (op.op === 'add' && op.column) this.column(store, op.table, op.column, source, file, line);
      else if (op.op === 'drop-column' && op.column) { const t = store.get(op.table.toLowerCase()); if (t) t.columns.delete(op.column.toLowerCase()); }
      else if (op.op === 'rename-column' && op.from && op.to) {
        const t = store.get(op.table.toLowerCase());
        if (t && t.columns.delete(op.from.toLowerCase())) this.column(store, op.table, op.to, source, file, line);
      } else if (op.op === 'drop-table') store.delete(String(op.table).toLowerCase());
      else if (op.op === 'rename-table' && op.from && op.to) {
        const t = store.get(op.from.toLowerCase());
        if (t) { store.delete(op.from.toLowerCase()); t.name = op.to; store.set(op.to.toLowerCase(), t); }
      }
    }
  }

  model(name, framework, table, file, line) {
    const m = { name, framework, table, attributes: new Map(), file, line, associations: [] };
    this.models.set(name, m);
    this.graph.node(`model:${name}`, 'model', { name, framework, table, file, line });
    this.graph.edge('contains', `file:${file}`, `model:${name}`);
    if (table) {
      this.table(this.declared, table, framework, file, line);
      this.graph.edge('maps-to', `model:${name}`, `table:${table}`);
    }
    return m;
  }

  attribute(model, attr, column, virtual) {
    model.attributes.set(attr, { column, virtual: !!virtual });
    if (model.table && column && !virtual) this.column(this.declared, model.table, column, model.framework, model.file, model.line);
  }

  ref(r) {
    this.refs.push(r);
  }

  // Edges for every reference, once all schema sources have been read.
  finalize() {
    for (const r of this.refs) this.edgeFor(r);
  }

  edgeFor(r) {
    const from = r.owner ? `fn:${r.owner}` : `file:${r.file}`;
    if (r.model) {
      const m = this.models.get(r.model);
      const attr = r.attr ? m && m.attributes.get(r.attr) : null;
      if (attr && m.table && attr.column) this.graph.edge(r.access === 'read' ? 'reads-column' : 'writes-column', from, `column:${m.table}.${attr.column}`, { file: r.file, line: r.line });
      else this.graph.edge(r.access === 'read' ? 'reads-model' : 'writes-model', from, `model:${r.model}`, { file: r.file, line: r.line, attr: r.attr });
    } else if (r.table) {
      const t = this.declared.get(r.table.toLowerCase());
      const name = t ? t.name : r.table;
      if (r.column && t && t.columns.has(r.column.toLowerCase())) this.graph.edge(r.access === 'read' ? 'reads-column' : 'writes-column', from, `column:${name}.${t.columns.get(r.column.toLowerCase()).name}`, { file: r.file, line: r.line });
      else if (!r.column) this.graph.edge(r.access === 'read' ? 'reads-table' : 'writes-table', from, `table:${name}`, { file: r.file, line: r.line });
    }
  }

  // SQL text (with its dynamic parts marked) found in code -> refs and DDL.
  sql(parts, dialect, where) {
    let n = 0;
    let text = '';
    for (const part of parts) text += typeof part === 'string' ? part : placeholder(dialect, ++n);
    if (!looksLikeSql(text)) return false;
    this.sqlCount++;
    const result = analyse(text, dialect);
    if (result.missing) { this.sqlMissing = true; return true; }
    if (result.error) {
      this.sqlErrors++;
      this.graph.unresolvedItem('sql', where.file, where.line, text.replace(/\s+/g, ' ').slice(0, 100), n ? `SQL assembled at run time, or not parseable: ${result.error}` : `SQL not parseable as ${dialect}: ${result.error}`);
      return true;
    }
    if (result.ddl.length) this.applyDdl(this.declared, result.ddl, 'sql', where.file, where.line);
    for (const r of result.refs) this.ref({ via: 'sql', table: r.table, column: r.column, access: r.access, candidates: r.candidates, file: where.file, line: where.line, owner: where.owner });
    return true;
  }
}

// Dialect for one file, from the drivers it imports, then the project default.
function fileDialect(project, facts, fallback) {
  for (const imp of facts.imports) {
    const r = imp.source ? project.target(facts.file, imp.source) : null;
    const pkg = r && r.package;
    if (!pkg) continue;
    if (/^(mysql2?|mariadb)$/.test(pkg)) return 'mysql';
    if (/^(pg|postgres|@electric-sql\/pglite|@neondatabase\/serverless|@vercel\/postgres|pg-promise)$/.test(pkg)) return 'postgresql';
    if (/^(better-sqlite3|sqlite3|sqlite|@libsql\/client|bun:sqlite)$/.test(pkg)) return 'sqlite';
  }
  return fallback;
}

const SQL_METHODS = new Set(['query', 'execute', 'exec', 'prepare', 'raw', 'unsafe', '$queryRawUnsafe', '$executeRawUnsafe', 'run', 'all', 'get']);
const SQL_TAGS = new Set(['sql', 'SQL', '$queryRaw', '$executeRaw', 'raw']);

// Raw SQL in JavaScript-family code: method calls and tagged templates whose text is SQL.
function rawSqlAdapter(ctx) {
  const { project, db } = ctx;
  for (const facts of project.facts.values()) {
    const dialect = fileDialect(project, facts, ctx.dialect);
    for (const site of facts.callSites) {
      const method = site.path.length ? site.path[site.path.length - 1] : null;
      if (!method || !SQL_METHODS.has(method) || !site.args[0]) continue;
      let node = A.unwrap(site.args[0]);
      if (node.type === 'Identifier') {
        const d = project.declaration(facts, node.name, site.scopes);
        if (d && d.binding && d.binding.kind === 'const' && d.node && !d.binding.pattern) node = A.unwrap(d.node);
      }
      if (!/^(StringLiteral|TemplateLiteral|BinaryExpression)$/.test(node.type)) continue;
      const parts = A.stringParts(node, project.valueAt(facts, site.scopes));
      if (!parts || typeof parts[0] !== 'string') continue;
      db.sql(parts, dialect, { file: facts.file, line: site.line, owner: site.owner });
    }
    for (const t of facts.tagged) {
      const name = t.path.length ? t.path[t.path.length - 1] : t.rootName;
      if (!SQL_TAGS.has(name)) continue;
      const q = t.quasi;
      const parts = [];
      q.quasis.forEach((quasi, i) => { parts.push(quasi.value.cooked ?? ''); if (i < q.expressions.length) parts.push({ dynamic: q.expressions[i] }); });
      db.sql(parts, dialect, { file: facts.file, line: t.line, owner: t.owner });
    }
  }
}

module.exports = { Database, rawSqlAdapter, fileDialect };
