'use strict';
// Reads SQL text with node-sql-parser: which tables and columns a statement reads or writes, and
// what a CREATE / ALTER / DROP does to the schema. SQL that cannot be parsed, or whose table or
// column names are only known at run time, is reported, never guessed.
// Part of the code-map skill (canonical copy: /shared/skills/code-map/).

let parserState = null;
function sqlParser() {
  if (parserState === null) {
    try {
      const { Parser } = require('node-sql-parser');
      parserState = new Parser();
    } catch {
      parserState = false;
    }
  }
  return parserState;
}

const DIALECTS = { mysql: 'MySQL', mariadb: 'MariaDB', postgresql: 'PostgresQL', postgres: 'PostgresQL', sqlite: 'Sqlite', mssql: 'TransactSQL', sqlserver: 'TransactSQL', bigquery: 'BigQuery' };
const SQL_START = /^\s*(?:(?:--[^\n]*\n|\/\*[\s\S]*?\*\/)\s*)*(select|insert|update|delete|with|create|alter|drop|replace|merge|truncate|pragma|upsert|rename)\b/i;
const SYSTEM_TABLES = /^(information_schema|pg_catalog|pg_|sqlite_|mysql\.|sys\.|dual$)/i;

function looksLikeSql(text) {
  return typeof text === 'string' && SQL_START.test(text);
}

function placeholder(dialect, n) {
  return dialect === 'postgresql' || dialect === 'postgres' ? `$${n}` : '?';
}

function colName(c) {
  if (c == null) return null;
  if (typeof c === 'string') return c;
  if (c.expr && c.expr.value !== undefined) return String(c.expr.value);
  if (c.value !== undefined) return String(c.value);
  if (c.column !== undefined) return colName(c.column);
  return null;
}

function tableName(t) {
  if (!t) return null;
  if (typeof t === 'string') return t;
  return t.table ? colName(t.table) : null;
}

const ACCESS = { select: 'read', insert: 'write', update: 'write', replace: 'write', delete: 'delete', create: 'ddl', alter: 'ddl', drop: 'ddl' };

function firstLine(msg) {
  return String(msg || '').split('\n')[0].slice(0, 200);
}

// -> { refs: [{ table, column|null, access }], ddl: [...], error }
function analyse(text, dialect) {
  const p = sqlParser();
  if (!p) return { error: 'node-sql-parser is not installed', missing: true };
  const opt = { database: DIALECTS[String(dialect || 'mysql').toLowerCase()] || 'MySQL' };
  let ast;
  try { ast = p.astify(text, opt); } catch (err) { return { error: firstLine(err.message) }; }
  const statements = Array.isArray(ast) ? ast : [ast];
  const refs = [];
  const ddl = [];
  for (const stmt of statements) {
    if (!stmt || !stmt.type) continue;
    let sql;
    try { sql = statements.length > 1 ? p.sqlify(stmt, opt) : text; } catch { sql = text; }
    let tables = [];
    let columns = [];
    try {
      tables = p.tableList(sql, opt);
      columns = p.columnList(sql, opt);
    } catch (err) {
      return { error: firstLine(err.message) };
    }
    const touched = new Map();
    for (const t of tables) {
      const [kind, , name] = t.split('::');
      if (!name || name === 'null' || SYSTEM_TABLES.test(name)) continue;
      const access = ACCESS[kind] || 'read';
      touched.set(name, access === 'read' && touched.get(name) && touched.get(name) !== 'read' ? touched.get(name) : access);
    }
    const tableNames = [...touched.keys()];
    for (const [name, access] of touched) refs.push({ table: name, column: null, access });
    for (const c of columns) {
      const [kind, table, column] = c.split('::');
      if (!column || column === '(.*)' || column === '*') continue;
      const t = table && table !== 'null' ? table : tableNames.length === 1 ? tableNames[0] : null;
      if (t && SYSTEM_TABLES.test(t)) continue;
      refs.push({ table: t, column, access: ACCESS[kind] || 'read', candidates: t ? undefined : tableNames });
    }
    ddl.push(...ddlOf(stmt));
  }
  return { refs, ddl };
}

function ddlOf(stmt) {
  const out = [];
  const tables = (stmt.table || []).map(tableName).filter(Boolean);
  if (stmt.type === 'create' && stmt.keyword === 'table' && tables[0]) {
    const columns = (stmt.create_definitions || []).filter((d) => d.resource === 'column').map((d) => colName(d.column)).filter(Boolean);
    out.push({ op: 'create', table: tables[0], columns });
  } else if (stmt.type === 'alter' && tables[0]) {
    for (const e of stmt.expr || []) {
      if (e.resource === 'column' && e.action === 'add') out.push({ op: 'add', table: tables[0], column: colName(e.column) });
      else if (e.resource === 'column' && e.action === 'drop') out.push({ op: 'drop-column', table: tables[0], column: colName(e.column) });
      else if (e.resource === 'column' && e.action === 'rename') out.push({ op: 'rename-column', table: tables[0], from: colName(e.old_column), to: colName(e.column) });
      else if (e.resource === 'table' && e.action === 'rename') out.push({ op: 'rename-table', from: tables[0], to: tableName(e.table) || colName(e.table) });
    }
  } else if (stmt.type === 'drop' && (stmt.keyword === 'table' || !stmt.keyword)) {
    for (const t of (stmt.name || []).map(tableName).concat(tables).filter(Boolean)) out.push({ op: 'drop-table', table: t });
  } else if (stmt.type === 'rename') {
    for (const pair of stmt.table || []) if (Array.isArray(pair) && pair.length === 2) out.push({ op: 'rename-table', from: tableName(pair[0]), to: tableName(pair[1]) });
  }
  return out;
}

module.exports = { analyse, looksLikeSql, placeholder, sqlParser, SYSTEM_TABLES };
