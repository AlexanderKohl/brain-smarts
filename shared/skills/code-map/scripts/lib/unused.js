'use strict';
// The unused report: code a repository no longer uses. It reports only and never fails a run,
// because every kind has blind spots (code loaded by a name built at run time, callers outside the
// repository). What it counts, and what it leaves out, is stated with each kind.
// Part of the code-map skill (canonical copy: /shared/skills/code-map/).

const path = require('path');
const { readText } = require('./files');
const { matchesAny, globToRegExp } = require('./config');
const { natural } = require('./graph');
const { interfaceOf } = require('./checks');

const P = path.posix;
const JS_CODE = /\.(c|m)?[jt]sx?$|\.vue$/;
const DECLARATION_FILE = /\.d\.(c|m)?ts$/;
// Configuration files a tool loads by its own name.
const TOOL_CONFIG = /(^|\/)([\w.-]+\.config|\.?(eslintrc|prettierrc|babelrc|stylelintrc|lintstagedrc))\.(c|m)?[jt]s$/;
// Migrations and seeders are run by their tool, not imported.
const MIGRATION = /(^|\/)(migrations?|seeders?)\//;
// Next.js loads these by their place in the folder tree.
const NEXT_SPECIAL = /^(src\/)?(app\/(.*\/)?(page|layout|loading|error|global-error|not-found|template|default|route|opengraph-image|twitter-image|icon|apple-icon|sitemap|robots|manifest)|pages\/.+|middleware|instrumentation)\.(c|m)?[jt]sx?$/;
const MACROS = new Set(['defineProps', 'defineEmits', 'defineModel', 'defineSlots', 'defineExpose', 'defineOptions', 'withDefaults']);

// The kinds, in the order the report lists them: whole files first, then what is inside files.
const KINDS = [
  { id: 'files', title: 'Files no entry point reaches' },
  { id: 'exports', title: 'Exports no file uses' },
  { id: 'declarations', title: 'Declarations never used in their own file' },
  { id: 'vue-state', title: 'Vue script-setup state the component never uses' },
  { id: 'env', title: 'Example env lines no code reads' },
];

const dirOf = (file) => { const d = P.dirname(file); return d === '.' ? '' : d; };

// The file a path names, with or without its extension, or as a folder with an index file.
function resolveFile(fileIndex, p) {
  p = P.normalize(p).replace(/^\.\//, '');
  if (p.startsWith('../')) return null;
  for (const c of [p, `${p}.js`, `${p}.mjs`, `${p}.cjs`, `${p}.ts`, `${p}.tsx`, `${p}.jsx`, `${p}/index.js`, `${p}/index.ts`]) if (fileIndex.has(c)) return c;
  return null;
}

// ---------- entry points ----------

// Files something outside the import graph starts: package scripts and fields, tests, tool
// configuration, migrations, HTML pages, browser-extension manifests, Next.js route files, and
// what the project declares in `unused.entries`. Returns Map file -> reason.
function entryPoints(map) {
  const { root, files, fileIndex, config } = map;
  const out = new Map();
  const add = (file, reason) => { if (file && fileIndex.has(file) && !out.has(file)) out.set(file, reason); };
  const code = files.filter((e) => JS_CODE.test(e.file));

  for (const e of files) {
    const base = P.basename(e.file);
    const dir = dirOf(e.file);
    if (base === 'package.json') {
      let pkg;
      try { pkg = JSON.parse(readText(root, e) || '{}'); } catch { continue; }
      const fields = [pkg.main, pkg.module, ...(typeof pkg.bin === 'string' ? [pkg.bin] : Object.values(pkg.bin || {})),
        ...(typeof pkg.exports === 'string' ? [pkg.exports] : Object.values(pkg.exports || {}).filter((v) => typeof v === 'string'))];
      for (const f of fields) if (typeof f === 'string') add(resolveFile(fileIndex, P.join(dir, f)), `${e.file} field`);
      for (const [name, script] of Object.entries(pkg.scripts || {})) {
        for (let token of String(script).split(/\s+|&&|\|\||;|\|/)) {
          token = token.replace(/^["']|["']$/g, '').replace(/^--?[\w-]+=/, '');
          if (!token || token.startsWith('-') || token.startsWith('$')) continue;
          const joined = P.normalize(P.join(dir, token)).replace(/^\.\//, '');
          if (/[*?]/.test(token)) {
            const re = globToRegExp(joined);
            for (const c of code) if (re.test(c.file)) add(c.file, `script ${name}`);
          } else if (/[/.]/.test(token)) {
            const f = resolveFile(fileIndex, joined);
            if (f) add(f, `script ${name}`);
            else for (const c of code) if (c.file.startsWith(`${joined}/`)) add(c.file, `script ${name} (folder)`);
          }
        }
      }
    }
    if (e.language === 'html') {
      const text = readText(root, e) || '';
      for (const m of text.matchAll(/<script\b[^>]*\bsrc\s*=\s*["']([^"']+)["']/gi)) {
        const src = m[1];
        if (/^(https?:)?\/\//.test(src)) continue;
        add(resolveFile(fileIndex, P.join(dir, src.replace(/^\//, ''))) || resolveFile(fileIndex, src.replace(/^\//, '')), `script in ${e.file}`);
      }
    }
    if (base === 'manifest.json') {
      let m;
      try { m = JSON.parse(readText(root, e) || '{}'); } catch { continue; }
      if (!m.manifest_version) continue;
      const bg = m.background || {};
      const scripts = [bg.service_worker, ...(bg.scripts || []), ...(m.content_scripts || []).flatMap((c) => c.js || [])];
      for (const s of scripts) if (typeof s === 'string') add(resolveFile(fileIndex, P.join(dir, s)), `${e.file}`);
    }
    if (/^next\.config\.(c|m)?[jt]s$/.test(base)) {
      for (const c of code) {
        if (dir && !c.file.startsWith(`${dir}/`)) continue;
        if (NEXT_SPECIAL.test(dir ? c.file.slice(dir.length + 1) : c.file)) add(c.file, 'Next.js route file');
      }
    }
  }
  for (const c of code) {
    if (c.test) add(c.file, 'test');
    else if (TOOL_CONFIG.test(c.file)) add(c.file, 'tool configuration');
    else if (MIGRATION.test(c.file)) add(c.file, 'migration or seeder');
  }
  const declared = (config.unused && config.unused.entries) || [];
  for (const c of code) if (matchesAny(c.file, declared)) add(c.file, 'declared in unused.entries');
  return out;
}

// ---------- reachability ----------

function reachability(map, entries) {
  const { root, fileIndex, graph, project } = map;
  const adj = new Map();
  const link = (from, to) => { if (!to || from === to) return; if (!adj.has(from)) adj.set(from, new Set()); adj.get(from).add(to); };
  for (const e of graph.edgesOf('imports')) if (e.to.startsWith('file:')) link(e.from.slice(5), e.to.slice(5));
  let unresolved = 0;
  for (const facts of project.facts.values()) {
    const dir = dirOf(facts.file);
    // Scripts started by file name: execFileSync(node, [path.join(__dirname, 'x.js')]).
    for (const ref of facts.scriptRefs || []) {
      link(facts.file, ref.base === 'dir' ? resolveFile(fileIndex, P.join(dir, ref.value))
        : resolveFile(fileIndex, P.join(dir, ref.value)) || resolveFile(fileIndex, ref.value));
    }
    // A loader that requires every file of its own folder by a computed name (Sequelize's models/index.js).
    const dynamic = facts.imports.filter((i) => i.source === null);
    if (!dynamic.length) continue;
    const text = readText(root, fileIndex.get(facts.file)) || '';
    if (/readdirSync\(\s*(__dirname|path\.(join|resolve)\(\s*__dirname\s*\))/.test(text)) {
      for (const f of fileIndex.keys()) if (dirOf(f) === dir && JS_CODE.test(f)) link(facts.file, f);
    } else unresolved += dynamic.length;
  }
  const seen = new Set(entries.keys());
  const queue = [...seen];
  while (queue.length) {
    const f = queue.pop();
    for (const t of adj.get(f) || []) if (!seen.has(t)) { seen.add(t); queue.push(t); }
  }
  return { reached: seen, unresolved };
}

// ---------- the kinds ----------

function unusedFiles(map, entries, reached) {
  const ignore = (map.config.unused && map.config.unused.ignore) || [];
  return map.files
    .filter((e) => JS_CODE.test(e.file) && !DECLARATION_FILE.test(e.file) && !e.test && map.project.facts.has(e.file))
    .filter((e) => !reached.has(e.file) && !matchesAny(e.file, ignore))
    .map((e) => ({ file: e.file, line: null, name: P.basename(e.file), message: 'no entry point reaches this file' }));
}

function exportLine(facts, name) {
  const named = facts.exports.named.get(name);
  if (named) return named.line;
  const cjs = facts.exports.cjsDefault && facts.exports.cjsDefault.node;
  if (cjs && cjs.type === 'ObjectExpression') {
    const prop = cjs.properties.find((p) => p.key && (p.key.name === name || p.key.value === name));
    if (prop && prop.loc) return prop.loc.start.line;
  }
  return facts.exports.cjsDefault ? facts.exports.cjsDefault.line : null;
}

function unusedExports(map, entries, reached) {
  const { project } = map;
  const ignore = (map.config.unused && map.config.unused.ignore) || [];
  const used = new Map();
  const use = (from, source, name) => {
    const r = project.target(from, source);
    if (!r.file) return;
    if (!used.has(r.file)) used.set(r.file, new Set());
    used.get(r.file).add(name);
  };
  for (const facts of project.facts.values()) {
    for (const imp of facts.imports) {
      if (!imp.source) continue;
      for (const n of imp.names) if (n.imported && n.imported !== '*') use(facts.file, imp.source, n.imported);
    }
    for (const u of facts.importUses || []) use(facts.file, u.source, u.name);
  }
  const out = [];
  for (const [file, v] of Object.entries(interfaceOf(map))) {
    const entry = map.fileIndex.get(file);
    if (!v.exports || !entry || entry.test || entries.has(file) || !reached.has(file) || /\.vue$/.test(file) || matchesAny(file, ignore)) continue;
    const u = used.get(file) || new Set();
    const facts = project.facts.get(file);
    if (u.has('*') || (u.has('default') && facts.exports.cjsDefault)) continue;
    for (const name of v.exports) {
      if (['default', 'module.exports', '...'].includes(name) || u.has(name)) continue;
      out.push({ file, line: exportLine(facts, name), name, message: `export ${name} is used by no file` });
    }
  }
  return out;
}

function initCallee(b) {
  let init = b.init;
  if (init && init.type === 'AwaitExpression') init = init.argument;
  return init && (init.type === 'CallExpression') && init.callee.type === 'Identifier' ? init.callee.name : null;
}

// Module-level declarations nothing in their file reads. Exported names, imports, names starting
// with _, and scripts with no import or export (their names are globals other scripts may use) are
// left out. Vue components are checked only in their <script setup>, against script and template.
function unusedDeclarations(map, entries) {
  const decl = [];
  const vue = [];
  const ignore = (map.config.unused && map.config.unused.ignore) || [];
  let classic = 0;
  for (const facts of map.project.facts.values()) {
    const entry = map.fileIndex.get(facts.file);
    if (!entry || entry.test || facts.language === 'html' || matchesAny(facts.file, ignore)) continue;
    const isVue = facts.language === 'vue';
    const isModule = facts.imports.length || facts.exports.named.size || facts.exports.default || facts.exports.cjsDefault
      || facts.exports.starFrom.length || (facts.assignments || []).some((a) => a.rootName === 'module' || a.rootName === 'exports');
    if (!isVue && !isModule) { classic++; continue; }
    if (isVue && !facts.vueSetup) continue;
    const exported = new Set([...facts.exports.named.values()].map((n) => n.local).filter(Boolean));
    const dflt = facts.exports.default && facts.exports.default.node;
    if (dflt && dflt.id) exported.add(dflt.id.name);
    for (const b of facts.moduleScope.values()) {
      if (b.import || !['function', 'class', 'var', 'let', 'const'].includes(b.kind)) continue;
      if (b.init && /^TSDeclare/.test(b.init.type)) continue;
      if (b.name.startsWith('_') || exported.has(b.name)) continue;
      if (isVue && (b.line < facts.vueSetup.start || b.line > facts.vueSetup.end || MACROS.has(initCallee(b)))) continue;
      const inTemplate = isVue && facts.templateNames.has(b.name);
      const reads = (b.reads || 0) + (inTemplate ? 1 : 0);
      const writes = b.writes || 0;
      if (reads) continue;
      const item = {
        file: facts.file, line: b.line, name: b.name,
        message: writes && !['function', 'class'].includes(b.kind) ? `${b.name} is set but never read` : `${b.name} is declared and never used`,
      };
      (isVue ? vue : decl).push(item);
    }
  }
  return { decl, vue, classic };
}

const ENV_FILES = /(^|\/)(\.env\.example|env\.example|\.env\.sample|\.env\.template|example\.env|\.env\.dist)$/;

// Lines of the example env files that name a variable no code reads – not through process.env,
// import.meta.env or a helper such as readEnv('X') – and no other file of the repository mentions
// (a deployment file or a script may read it).
function unusedEnv(map) {
  const { root, ctx, project } = map;
  if (!ctx.envDeclared || !ctx.envDeclared.size) return [];
  const read = new Set();
  for (const facts of project.facts.values()) for (const e of facts.env) if (e.name) read.add(e.name);
  for (const py of ctx.python.values()) for (const e of py.env || []) if (e.name) read.add(e.name);
  const candidates = [...ctx.envDeclared.keys()].filter((n) => !read.has(n));
  if (!candidates.length) return [];
  const mentioned = new Set();
  for (const e of map.files) {
    if (ENV_FILES.test(e.file) || e.language === 'markdown' || ctx.envFiles.includes(e.file)) continue;
    const text = readText(root, e);
    if (!text) continue;
    for (const n of candidates) if (!mentioned.has(n) && new RegExp(`(^|[^A-Za-z0-9_])${n}([^A-Za-z0-9_]|$)`).test(text)) mentioned.add(n);
  }
  const out = [];
  for (const n of candidates) {
    if (mentioned.has(n)) continue;
    for (const file of ctx.envDeclared.get(n)) {
      const lines = (readText(root, map.fileIndex.get(file)) || '').split('\n');
      const line = lines.findIndex((l) => new RegExp(`^\\s*#?\\s*(export\\s+)?${n}\\s*=`).test(l)) + 1 || null;
      out.push({ file, line, name: n, message: `${n} is listed but no code reads it` });
    }
  }
  return out;
}

function unusedReport(map) {
  const entries = entryPoints(map);
  const { reached, unresolved } = reachability(map, entries);
  const { decl, vue, classic } = unusedDeclarations(map, entries);
  const items = {
    files: unusedFiles(map, entries, reached),
    exports: unusedExports(map, entries, reached),
    declarations: decl,
    'vue-state': vue,
    env: unusedEnv(map),
  };
  const sort = (a, b) => natural(a.file, b.file) || (a.line || 0) - (b.line || 0) || natural(a.name, b.name);
  const kinds = KINDS.map((k) => ({ ...k, items: items[k.id].sort(sort) }));
  const notes = [];
  notes.push(`${entries.size} entry point(s): package scripts and fields, tests, tool configuration, migrations, HTML pages, extension manifests, Next.js route files, unused.entries.`);
  if (unresolved) notes.push(`${unresolved} import(s) name their module only at run time; files loaded that way may be listed as unreached.`);
  if (classic) notes.push(`${classic} script(s) with no import or export were not checked for unused declarations: their names are globals other scripts may use.`);
  notes.push('Imports never used, TypeScript types, Vue options-API state, packages and Python are not covered.');
  return { kinds, notes, entries };
}

function formatUnused(result, { limit = 30, only = null } = {}) {
  const lines = ['Unused code (report only; nothing here fails a run)', ''];
  for (const k of result.kinds) {
    if (only && !only.includes(k.id)) continue;
    lines.push(`${k.id.padEnd(12)} ${k.title}: ${k.items.length}`);
    for (const it of k.items.slice(0, limit)) lines.push(`       ${it.file}${it.line ? `:${it.line}` : ''}  ${it.message}`);
    if (k.items.length > limit) lines.push(`       … ${k.items.length - limit} more (--limit N to see more)`);
  }
  lines.push('');
  for (const n of result.notes) lines.push(`Note: ${n}`);
  return lines.join('\n');
}

module.exports = { unusedReport, formatUnused, entryPoints, KINDS };
