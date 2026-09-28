'use strict';
// Configuration the code reads: environment variables (JavaScript and Python) against the example
// env files, and settings keys read from the settings objects a project declares, against its
// settings files. Part of the code-map skill (canonical copy: /shared/skills/code-map/).

const path = require('path');
const A = require('../js/ast');
const { lookup } = require('../js/extract');
const { readText } = require('../files');
const { matchesAny, globToRegExp } = require('../config');

const ENV_FILES = /(^|\/)(\.env\.example|env\.example|\.env\.sample|\.env\.template|example\.env|\.env\.dist)$/;

function envAdapter(ctx) {
  const { graph, config } = ctx;
  const declared = new Map(); // name -> files
  const files = config.env.files ? ctx.files.filter((e) => config.env.files.includes(e.file)) : ctx.files.filter((e) => ENV_FILES.test(e.file));
  for (const entry of files) {
    const text = readText(ctx.root, entry) || '';
    for (const line of text.split('\n')) {
      const m = /^\s*#?\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=/.exec(line);
      if (m) { if (!declared.has(m[1])) declared.set(m[1], []); declared.get(m[1]).push(entry.file); }
    }
  }
  ctx.envDeclared = declared;
  ctx.envFiles = files.map((f) => f.file);
  const ignored = (name) => config.env.ignore.some((p) => globToRegExp(p).test(name));
  const reads = [];
  for (const facts of ctx.project.facts.values()) {
    for (const e of facts.env) reads.push({ ...e, file: facts.file });
  }
  for (const py of ctx.python.values()) for (const e of py.env || []) reads.push({ ...e, file: py.file, owner: e.owner ? `${py.file}#${e.owner}` : null });
  let count = 0;
  for (const r of reads) {
    if (r.name === null || r.name === undefined) { graph.unresolvedItem('env', r.file, r.line, r.text || 'process.env[…]', 'variable name is only known at run time'); continue; }
    if (ignored(r.name)) continue;
    graph.node(`env:${r.name}`, 'env', { name: r.name, declared: declared.has(r.name) });
    graph.edge('reads-env', (r.owner ? `fn:${r.owner}` : `file:${r.file}`), `env:${r.name}`, { file: r.file, line: r.line });
    // A retired fallback name read from a list (via 'helper-list') is not required in the example file.
    if (r.via !== 'helper-list') ctx.envReads.push({ name: r.name, file: r.file, line: r.line, test: !!(ctx.fileIndex.get(r.file) || {}).test });
    count++;
  }
  graph.cover('config:env', reads.length ? 'mapped' : 'not used', { reads: count, exampleFiles: ctx.envFiles });
}

// Flattened keys of a JSON value: a.b, a.list[], a.list[].c
function flatten(value, prefix, out) {
  if (Array.isArray(value)) {
    out.add(`${prefix}[]`);
    for (const v of value) if (v && typeof v === 'object') flatten(v, `${prefix}[]`, out);
  } else if (value && typeof value === 'object') {
    for (const [k, v] of Object.entries(value)) {
      const key = prefix ? `${prefix}.${k}` : k;
      out.add(key);
      flatten(v, key, out);
    }
  }
  return out;
}

function settingsAdapter(ctx) {
  const { graph, config, project } = ctx;
  const s = config.settings;
  if (!s.loaders.length && !s.names.length) { graph.cover('config:settings', 'not declared', {}); return; }
  const defined = new Set();
  const sources = ctx.files.filter((e) => matchesAny(e.file, s.files));
  for (const entry of sources) {
    try { flatten(JSON.parse(readText(ctx.root, entry) || 'null'), '', defined); } catch { graph.unresolvedItem('settings', entry.file, 1, entry.file, 'settings file is not valid JSON'); }
  }
  if (s.declared) {
    const entry = ctx.files.find((e) => e.file === s.declared);
    const text = entry ? readText(ctx.root, entry) : null;
    if (text) for (const line of text.split('\n')) { const k = line.replace(/#.*/, '').trim(); if (k) defined.add(k); }
  }
  ctx.settingsDefined = defined;
  const loaders = new Set(s.loaders);
  const names = new Set(s.names);
  let count = 0;

  const fromLoader = (n) => { n = A.unwrap(n); if (n && n.type === 'AwaitExpression') n = A.unwrap(n.argument); return !!n && A.isCall(n) && A.unwrap(n.callee).type === 'Identifier' && loaders.has(A.unwrap(n.callee).name); };
  // Is this binding a settings object? Returns the key path it stands for ([] for the root).
  const settingsPath = (b, rootName, depth = 0) => {
    if (depth > 3) return null;
    if (!b) return names.has(rootName) ? [] : null;
    if (b.pattern && b.initBinding) {
      const root = settingsPath(b.initBinding, b.initBinding.name, depth + 1);
      if (root && b.pattern.every((p) => p && !p.startsWith('[') && p !== '...')) return [...root, ...b.pattern];
      return null;
    }
    if (b.pattern && b.init && fromLoader(b.init)) return b.pattern.every((p) => p && !p.startsWith('[')) ? [...b.pattern] : null;
    if (!b.pattern && b.init && fromLoader(b.init)) return [];
    if (b.assignments.some(fromLoader)) return [];
    if (names.has(b.name) && !b.import) return [];
    return null;
  };

  for (const facts of project.facts.values()) {
    for (const r of facts.memberReads) {
      const base = settingsPath(r.binding, r.rootName);
      if (!base) continue;
      const keys = [];
      for (const k of r.path) { if (k === null) break; keys.push(k); }
      // Drop a trailing method name (settings.a.b.trim()).
      if (r.isCallee && keys.length === r.path.length && keys.length) keys.pop();
      const key = [...base, ...keys].join('.');
      if (!key) continue;
      if (r.path.includes(null) && !keys.length) { graph.unresolvedItem('settings', facts.file, r.line, `${r.rootName}[…]`, 'settings key is computed at run time'); continue; }
      graph.node(`setting:${key}`, 'setting', { key, defined: isDefined(key, defined, s.open) });
      graph.edge('reads-setting', (r.owner ? `fn:${r.owner}` : `file:${facts.file}`), `setting:${key}`, { file: facts.file, line: r.line });
      ctx.settingsReads.push({ key, file: facts.file, line: r.line, test: !!(ctx.fileIndex.get(facts.file) || {}).test });
      count++;
    }
  }
  graph.cover('config:settings', 'mapped', { reads: count, files: sources.map((e) => e.file), definedKeys: defined.size });
}

function isDefined(key, defined, open) {
  if (defined.has(key)) return true;
  const prefix = `${key}.`;
  for (const d of defined) if (d.startsWith(prefix) || d.startsWith(`${key}[]`)) return true;
  return (open || []).some((o) => key === o || key.startsWith(`${o}.`));
}

module.exports = { envAdapter, settingsAdapter, isDefined, flatten, ENV_FILES };
