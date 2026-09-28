'use strict';
// Builds the map of one repository: files, the facts of every file a reader supports, then each
// framework adapter in turn. Returns the graph and the collections the checks and reports use.
// Part of the code-map skill (canonical copy: /shared/skills/code-map/).

const path = require('path');
const { loadConfig } = require('./config');
const { listFiles, readText } = require('./files');
const { Graph } = require('./graph');
const { Resolver } = require('./resolve');
const { loadJs, tsconfigAliases, viteAliases } = require('./js/load');
const { JsProject } = require('./js/project');
const { extractPython, resolvePy } = require('./python');
const { expressAdapter } = require('./adapters/express');
const { nextAdapter, addRoute } = require('./adapters/next');
const { uiRoutesAdapter } = require('./adapters/ui-routes');
const { httpAdapter } = require('./adapters/http');
const { Database, rawSqlAdapter } = require('./adapters/database');
const { sequelizeAdapter } = require('./adapters/sequelize');
const { prismaAdapter } = require('./adapters/prisma');
const { dexieAdapter } = require('./adapters/dexie');
const { messagingAdapter } = require('./adapters/messaging');
const { envAdapter, settingsAdapter } = require('./adapters/config-reads');
const { analyse, placeholder } = require('./sql');

const JS_LANGS = new Set(['javascript', 'typescript', 'vue', 'html']);
const MAPPED_LANGS = new Set(['javascript', 'typescript', 'vue', 'html', 'python', 'sql', 'prisma']);

function collectAliases(config, files, root) {
  const out = [];
  for (const a of config.aliases || []) {
    const scope = a.dir ? `${a.dir.replace(/\/$/, '')}/` : '';
    const from = a.alias.endsWith('/') ? a.alias : `${a.alias}/`;
    const to = a.target.endsWith('/') ? a.target : `${a.target}/`;
    out.push({ scope, from, to, source: 'code-map.config.json' });
  }
  for (const e of files) {
    const base = path.posix.basename(e.file);
    if (/^(tsconfig|jsconfig)(\.[\w-]+)?\.json$/.test(base)) out.push(...tsconfigAliases(e.file, readText(root, e) || ''));
    if (/^vite\.config\.(js|mjs|cjs|ts|mts)$/.test(base)) out.push(...viteAliases(e.file, readText(root, e) || ''));
  }
  return out;
}

function detectDialect(config, files, root) {
  if (config.database.dialect) return config.database.dialect;
  const found = new Set();
  for (const e of files) {
    if (path.posix.basename(e.file) !== 'package.json') continue;
    let pkg;
    try { pkg = JSON.parse(readText(root, e) || '{}'); } catch { continue; }
    const deps = Object.keys({ ...pkg.dependencies, ...pkg.devDependencies });
    if (deps.some((d) => /^(mysql2?|mariadb)$/.test(d))) found.add('mysql');
    if (deps.some((d) => /^(pg|postgres|@electric-sql\/pglite|@neondatabase\/serverless|@vercel\/postgres)$/.test(d))) found.add('postgresql');
    if (deps.some((d) => /^(better-sqlite3|sqlite3|@libsql\/client)$/.test(d))) found.add('sqlite');
  }
  for (const d of ['mysql', 'postgresql', 'sqlite']) if (found.has(d)) return d;
  return null;
}

function buildMap(root) {
  root = path.resolve(root);
  const config = loadConfig(root);
  const files = listFiles(root, config);
  const fileIndex = new Map(files.map((e) => [e.file, e]));
  const graph = new Graph();
  const langStats = new Map();
  const stat = (lang) => { if (!langStats.has(lang)) langStats.set(lang, { files: 0, parsed: 0, failed: [], sizeOnly: 0 }); return langStats.get(lang); };

  for (const e of files) {
    if (!e.code && !MAPPED_LANGS.has(e.language)) continue;
    readText(root, e);
    graph.node(`file:${e.file}`, 'file', { path: e.file, language: e.language || e.ext, lines: e.lines, test: e.test, sizeExempt: e.sizeExempt, code: e.code });
    const s = stat(e.language || e.ext);
    s.files++;
    if (!MAPPED_LANGS.has(e.language)) s.sizeOnly++;
  }

  const resolver = new Resolver(new Set(files.map((e) => e.file)), collectAliases(config, files, root));
  const project = new JsProject(resolver);
  const hints = { roots: config.settings.names, loaders: config.settings.loaders };
  const missing = new Set();
  for (const e of files) {
    if (!JS_LANGS.has(e.language)) continue;
    const text = readText(root, e);
    if (text === null) continue;
    const { facts, missing: miss } = loadJs(e, text, hints);
    if (miss) { missing.add(miss); stat(e.language).sizeOnly++; continue; }
    project.add(facts);
    if (facts.errors.length) stat(e.language).failed.push(`${e.file}: ${facts.errors[0]}`);
    else stat(e.language).parsed++;
  }
  project.linkClasses();

  // Structure of every JavaScript-family file.
  for (const facts of project.facts.values()) {
    const fileId = `file:${facts.file}`;
    for (const fn of facts.functions) {
      graph.node(`fn:${fn.id}`, 'function', { file: facts.file, name: fn.name, qualified: fn.qualified, line: fn.line, endLine: fn.endLine, length: fn.length, kind: fn.kind, className: fn.className || null });
      graph.edge('contains', fileId, `fn:${fn.id}`);
    }
    for (const cls of facts.classes) {
      const id = `class:${facts.file}#${cls.name}`;
      graph.node(id, 'class', { file: facts.file, name: cls.name, line: cls.line, endLine: cls.endLine, superClass: cls.superClass, methods: cls.methods.map((m) => m.name).sort(), mixins: cls.mixins || [] });
      graph.edge('contains', fileId, id);
    }
    for (const v of facts.variables) {
      const id = `var:${facts.file}#${v.name}`;
      graph.node(id, 'variable', { file: facts.file, name: v.name, kind: v.kind, line: v.line, container: v.container });
      graph.edge('contains', fileId, id);
    }
    for (const ref of facts.varRefs) graph.edge(ref.write ? 'writes-var' : 'reads-var', `fn:${ref.owner}`, `var:${facts.file}#${ref.name}`, { line: ref.line });
    for (const imp of facts.imports) {
      if (imp.source === null) { graph.unresolvedItem('import', facts.file, imp.line, imp.unresolved, 'module name is only known at run time'); continue; }
      const r = resolver.resolve(facts.file, imp.source);
      const props = { line: imp.line, load: imp.load, kind: imp.kind, typeOnly: imp.typeOnly || undefined, names: imp.names.map((n) => n.imported).filter(Boolean) };
      if (r.file) graph.edge('imports', fileId, `file:${r.file}`, props);
      else if (r.package) { graph.node(`pkg:${r.package}`, 'package', { name: r.package, core: !!r.core }); graph.edge('imports', fileId, `pkg:${r.package}`, props); }
      else graph.unresolvedItem('import', facts.file, imp.line, imp.source, 'no file or package found for this import');
    }
    for (const site of facts.callSites) {
      const target = project.callTarget(facts, site);
      if (target) graph.edge('calls', site.owner ? `fn:${site.owner}` : fileId, `fn:${target}`, { line: site.line });
    }
  }

  const ctx = {
    root, config, files, fileIndex, project, graph, python: new Map(), routes: [], uiRoutes: [], httpCalls: [],
    events: [], envReads: [], settingsReads: [], db: new Database(graph), dialect: detectDialect(config, files, root),
    dialectDeclared: !!config.database.dialect, routerOrder: [],
  };

  // Python.
  const pyFiles = files.filter((e) => e.language === 'python').map((e) => e.file);
  const py = extractPython(root, pyFiles, config);
  if (py.error) { graph.cover('language:python', 'sizes only', { reason: py.error }); stat('python').sizeOnly += pyFiles.length; }
  const fileSet = new Set(files.map((e) => e.file));
  for (const [file, f] of py.results) {
    ctx.python.set(file, f);
    const fileId = `file:${file}`;
    if (f.error) { stat('python').failed.push(`${file}: ${f.error}`); continue; }
    stat('python').parsed++;
    for (const fn of f.functions) {
      graph.node(`fn:${file}#${fn.qualified}`, 'function', { file, name: fn.name, qualified: fn.qualified, line: fn.line, endLine: fn.endLine, length: fn.length, kind: fn.kind, className: fn.className });
      graph.edge('contains', fileId, `fn:${file}#${fn.qualified}`);
    }
    for (const cls of f.classes) {
      graph.node(`class:${file}#${cls.name}`, 'class', { file, name: cls.name, line: cls.line, endLine: cls.endLine, superClass: cls.bases.join(', ') || null, methods: cls.methods.map((m) => m.name).sort() });
      graph.edge('contains', fileId, `class:${file}#${cls.name}`);
    }
    for (const v of f.variables) { graph.node(`var:${file}#${v.name}`, 'variable', { file, name: v.name, line: v.line, container: v.container }); graph.edge('contains', fileId, `var:${file}#${v.name}`); }
    for (const r of f.varRefs) graph.edge(r.write ? 'writes-var' : 'reads-var', `fn:${file}#${r.owner}`, `var:${file}#${r.name}`, { line: r.line });
    for (const c of f.calls) graph.edge('calls', `fn:${file}#${c.owner}`, `fn:${file}#${c.target}`, { line: c.line });
    for (const imp of f.imports) {
      const r = resolvePy(file, imp, fileSet, config.python.roots || []);
      const props = { line: imp.line, load: imp.load, kind: 'import', names: imp.names };
      if (r.files) for (const target of r.files) graph.edge('imports', fileId, `file:${target}`, props);
      else if (r.package) { graph.node(`pkg:${r.package}`, 'package', { name: r.package, core: r.stdlib }); graph.edge('imports', fileId, `pkg:${r.package}`, props); }
      else graph.unresolvedItem('import', file, imp.line, `${'.'.repeat(imp.level)}${imp.module}`, 'relative import with no matching file');
    }
    for (const r of f.routes) {
      const p = r.prefix ? `${r.path.replace(/\/$/, '')}/*` : r.path;
      addRoute(ctx, r.method, p, file, r.line, f.functions.find((fn) => fn.name === `do_${r.method}`) ? `${file}#${r.className}.do_${r.method}` : null, 'python-http');
    }
  }

  expressAdapter(ctx);
  nextAdapter(ctx);
  uiRoutesAdapter(ctx);
  httpAdapter(ctx);
  sequelizeAdapter(ctx);
  prismaAdapter(ctx);
  dexieAdapter(ctx);

  // .sql files: migration folders build the migrated schema; any other file declares or queries.
  for (const e of files) {
    if (e.language !== 'sql' || e.migrationRead) continue;
    const text = readText(root, e);
    if (!text) continue;
    if (/(^|\/)migrations?\//.test(e.file)) {
      const r = analyse(text, ctx.dialect);
      if (r.ddl) ctx.db.applyDdl(ctx.db.migrated, r.ddl, 'migration', e.file, 1);
      else if (r.error && !r.missing) graph.unresolvedItem('sql', e.file, 1, e.file, r.error);
    } else {
      ctx.db.sql([text], ctx.dialect, { file: e.file, line: 1, owner: null });
    }
  }
  rawSqlAdapter(ctx);
  const pyDialect = config.python.dialect || 'sqlite';
  for (const [file, f] of ctx.python) {
    for (const s of f.sql || []) {
      let k = 0;
      const parts = s.parts.map((p) => (typeof p === 'string' ? p.replace(/%\(\w+\)s|%s/g, () => placeholder(pyDialect, ++k + 100)) : p));
      ctx.db.sql(parts, pyDialect, { file, line: s.line, owner: s.owner ? `${file}#${s.owner}` : null });
    }
  }
  ctx.db.finalize();
  if (ctx.db.sqlMissing) missing.add('node-sql-parser');
  graph.cover('database:raw-sql', ctx.db.sqlMissing ? 'not checked' : ctx.db.sqlCount ? 'mapped' : 'not used', { statements: ctx.db.sqlCount, unparsed: ctx.db.sqlErrors, dialect: ctx.dialect });

  messagingAdapter(ctx);
  envAdapter(ctx);
  settingsAdapter(ctx);

  for (const [lang, s] of langStats) {
    graph.cover(`language:${lang}`, s.parsed ? (s.failed.length ? 'mapped with parse errors' : 'mapped') : s.sizeOnly ? 'sizes only' : 'not used',
      { files: s.files, parsed: s.parsed, sizeOnly: s.sizeOnly, failed: s.failed.slice(0, 10), failedCount: s.failed.length });
  }
  for (const m of missing) graph.cover(`dependency:${m}`, 'missing', { install: `npm install --save-dev ${m}` });
  return { root, config, files, fileIndex, graph, project, ctx };
}

module.exports = { buildMap };
