#!/usr/bin/env node
'use strict';
// Shape snapshot: what the rest of an app can see of some CommonJS modules, so a split that only
// moves code can be shown to leave it unchanged.
//
// It records:
// - each module's exports, and a class's prototype, with property descriptors; functions by name
//   and a hash of their source text;
// - each router (an Express-style function with a `stack`) layer by layer in registration order:
//   method, full path, handler name and source hash, and the options passed to the middleware
//   factories it knows (express.json/urlencoded/raw/text/static, cors, multer);
// - lines of other files that mount the routers, matched by pattern;
// - each module loaded first, alone, in a fresh process (load-order cycles);
// - every outbound network connection attempted while loading (there must be none).
//
// What it cannot see: options of middleware made by other factories, and which binding an
// unchanged function now refers to after a move. Those are reviewed by hand and covered by tests.
//
// Configuration: `split-file.config.json` at the repository root (or --config), key "js":
//   modules     files whose exports to describe
//   routers     [{ "mount": "/admin", "file": "…" }] routers to describe with their mount path
//   mountLines  [{ "file": "…", "pattern": "regular expression" }] lines that mount the routers
//   setup       files to load first (for example a test setup that swaps a store for memory)
//   env         environment values to set while loading
//   tempDirEnv  environment names to point at a fresh temporary folder
//   coldDirs    folders whose changed files are also loaded alone with --compare-ref
//   coldIgnore  path fragments to leave out of those
//
// Usage:
//   node shape.js [--root DIR] [--config FILE] [--modules a.js,b.js]   print the snapshot as JSON
//   node shape.js … --out FILE            write it to FILE
//   node shape.js … --compare FILE        compare with a saved snapshot
//   node shape.js … --compare-ref REF     take the snapshot of REF in a temporary git worktree and
//                                         compare; also loads every changed file alone
// Exit code 1 when a comparison finds a difference.
//
// Part of the split-file skill (canonical copy: /shared/skills/split-file/).

const crypto = require('crypto');
const fs = require('fs');
const net = require('net');
const os = require('os');
const path = require('path');
const { execFileSync, spawn } = require('child_process');
const { parseArgs } = require('./lib/args');

const USAGE = 'usage: node shape.js [--root DIR] [--config FILE] [--modules a,b] [--out FILE | --compare FILE | --compare-ref REF]';

// Line endings are ignored: a checkout or an editor may write CRLF or LF.
const hash = (text) => crypto.createHash('sha1').update(String(text).replace(/\r\n/g, '\n')).digest('hex').slice(0, 12);

function loadConfig(root, file, modulesOption) {
  const configFile = file ? path.resolve(file) : path.join(root, 'split-file.config.json');
  const all = fs.existsSync(configFile) ? JSON.parse(fs.readFileSync(configFile, 'utf8')) : {};
  const js = all.js || {};
  const config = {
    modules: js.modules || [],
    routers: js.routers || [],
    mountLines: (js.mountLines || []).map((m) => ({ file: m.file, pattern: new RegExp(m.pattern) })),
    setup: js.setup || [],
    env: js.env || {},
    tempDirEnv: js.tempDirEnv || [],
    coldDirs: js.coldDirs || ['.'],
    coldIgnore: js.coldIgnore || [],
  };
  if (modulesOption) config.modules = modulesOption.split(',').map((m) => m.trim()).filter(Boolean);
  if (!config.modules.length) throw new Error(`no modules: name them with --modules or in ${configFile}`);
  return config;
}

// ---- outbound connection trap -----------------------------------------------------------

const LOCAL_HOSTS = new Set(['localhost', '127.0.0.1', '::1', '']);

// Records every outbound connection attempt and refuses it. Throwing alone is not enough, since
// application code may catch the error: callers check the recorded list is empty.
function installOutboundTrap() {
  if (net.Socket.prototype.connect.shapeTrap) return net.Socket.prototype.connect.shapeTrap;
  const attempts = [];
  const original = net.Socket.prototype.connect;
  function trapped(...args) {
    const first = Array.isArray(args[0]) ? args[0][0] : args[0];
    let host = '';
    let port = '';
    if (first && typeof first === 'object') {
      if (first.path) return original.apply(this, args); // a local pipe or socket file
      host = first.host || first.hostname || 'localhost';
      port = first.port;
    } else if (typeof first === 'number' || /^\d+$/.test(String(first))) {
      port = first;
      host = typeof args[1] === 'string' ? args[1] : 'localhost';
    } else if (typeof first === 'string') {
      return original.apply(this, args); // a local pipe or socket file
    }
    if (LOCAL_HOSTS.has(String(host))) return original.apply(this, args);
    attempts.push(`${host}:${port}`);
    const socket = this;
    process.nextTick(() => socket.destroy(new Error(`outbound connection to ${host}:${port} blocked by the shape snapshot`)));
    return socket;
  }
  trapped.shapeTrap = attempts;
  net.Socket.prototype.connect = trapped;
  return attempts;
}

// ---- middleware factory tags ------------------------------------------------------------

const tags = new WeakMap();
// Replaces the repository's own path and temporary folders in recorded text; set when loading.
let normalise = (text) => String(text);

function normaliser(root, extra) {
  const roots = [[path.resolve(root), '<repo>'], ...extra.map((p) => [p, '<temp>']), [os.tmpdir(), '<tmp>']];
  return (text) => {
    let out = String(text);
    for (const [p, label] of roots) out = out.split(p).join(label).split(p.replace(/\\/g, '/')).join(label);
    return out.replace(/\\/g, '/');
  };
}

// A stable text form of factory arguments: sorted keys, functions as a source hash.
function canonical(value, normalise, depth = 0, seen = new Set()) {
  if (value === null || value === undefined) return String(value);
  if (typeof value === 'function') return `fn:${hash(value.toString())}`;
  if (typeof value === 'string') return JSON.stringify(normalise(value));
  if (typeof value !== 'object') return String(value);
  if (value instanceof RegExp) return String(value);
  if (seen.has(value)) return '[cycle]';
  if (depth > 4) return '[deep]';
  seen.add(value);
  const out = Array.isArray(value)
    ? `[${value.map((v) => canonical(v, normalise, depth + 1, seen)).join(',')}]`
    : `{${Object.keys(value).sort().map((k) => `${k}:${canonical(value[k], normalise, depth + 1, seen)}`).join(',')}}`;
  seen.delete(value);
  return out;
}

function tagFactory(label, factory, normalise) {
  const wrapped = function (...args) {
    const made = factory.apply(this, args);
    if (typeof made === 'function') tags.set(made, `${label}(${args.map((a) => canonical(a, normalise)).join(',')})`);
    return made;
  };
  Object.assign(wrapped, factory);
  return wrapped;
}

// Wraps the middleware factories in the copies of express, cors and multer the app under `root`
// will load, when it has them. Must run before any application module is loaded.
function installFactoryTags(root, normalise) {
  const resolve = (name) => { try { return require.resolve(name, { paths: [root] }); } catch { return null; } };
  const expressFile = resolve('express');
  if (expressFile) {
    const express = require(expressFile);
    if (!express.shapeTagged) {
      for (const name of ['json', 'urlencoded', 'raw', 'text', 'static']) {
        if (typeof express[name] === 'function') express[name] = tagFactory(`express.${name}`, express[name], normalise);
      }
      express.shapeTagged = true;
    }
  }
  const corsFile = resolve('cors');
  if (corsFile && !require(corsFile).shapeTagged) {
    const wrapped = tagFactory('cors', require(corsFile), normalise);
    wrapped.shapeTagged = true;
    require.cache[corsFile].exports = wrapped;
  }
  const multerFile = resolve('multer');
  if (multerFile && !require(multerFile).shapeTagged) {
    const multer = require(multerFile);
    const wrapped = function (options) {
      const instance = multer(options);
      const tagged = Object.create(instance);
      for (const method of ['single', 'array', 'fields', 'none', 'any']) {
        if (typeof instance[method] !== 'function') continue;
        tagged[method] = (...args) => {
          const made = instance[method](...args);
          tags.set(made, `multer.${method}(${[options, ...args].map((a) => canonical(a, normalise)).join(',')})`);
          return made;
        };
      }
      return tagged;
    };
    Object.assign(wrapped, multer);
    wrapped.shapeTagged = true;
    require.cache[multerFile].exports = wrapped;
  }
}

// ---- describing routers and modules -----------------------------------------------------

const isClass = (fn) => typeof fn === 'function' && /^class\b/.test(Function.prototype.toString.call(fn));

// A class's source text is its whole body, which changes whenever a method moves out; a class is
// named here, and its members are described one by one (describeClass).
function describeFn(fn) {
  if (typeof fn !== 'function') return String(typeof fn);
  if (isClass(fn)) return `class ${fn.name}`;
  const tag = tags.get(fn);
  return `${fn.name || '<anonymous>'} ${tag || `src:${hash(fn.toString())}`}`;
}

// Express 4 keeps a use() path only as a regular expression; turn it back into a path.
function layerPath(layer) {
  if (typeof layer.path === 'string' && !layer.regexp) return layer.path;
  if (!layer.regexp || layer.regexp.fast_slash) return '';
  let source = layer.regexp.source;
  const keys = [...(layer.keys || [])];
  source = source.replace(/^\^/, '').replace(/\\\/\?\(\?=\\\/\|\$\)$/, '').replace(/\/\?\$$/, '');
  source = source.replace(/\(\?:\(\[\^\\\/\]\+\?\)\)/g, () => `:${(keys.shift() || {}).name || 'param'}`);
  source = source.replace(/\\\//g, '/').replace(/\\\./g, '.').replace(/\\-/g, '-');
  return /[\\()[\]?*+^$|]/.test(source) ? `re:${layer.regexp.source}` : source;
}

const isRouter = (fn) => typeof fn === 'function' && Array.isArray(fn.stack);

function describeRouter(router, prefix, out = []) {
  out.push(`router ${prefix || '/'} options caseSensitive=${Boolean(router.caseSensitive)} mergeParams=${Boolean(router.mergeParams)} strict=${Boolean(router.strict)}`);
  for (const [name, handlers] of Object.entries(router.params || {}).sort(([a], [b]) => a.localeCompare(b))) {
    out.push(`param ${prefix} :${name} ${handlers.map(describeFn).join(' ')}`);
  }
  for (const layer of router.stack) {
    if (layer.route) {
      const routePath = Array.isArray(layer.route.path) ? layer.route.path.join('|') : String(layer.route.path);
      for (const step of layer.route.stack) out.push(`route ${(step.method || 'all').toUpperCase()} ${prefix}${routePath} ${describeFn(step.handle)}`);
    } else if (isRouter(layer.handle)) {
      describeRouter(layer.handle, `${prefix}${layerPath(layer)}`, out);
      out.push(`end ${`${prefix}${layerPath(layer)}` || '/'}`);
    } else {
      out.push(`use ${`${prefix}${layerPath(layer)}` || '/'} ${describeFn(layer.handle)}`);
    }
  }
  return out;
}

const ROUTER_OWN = new Set(['params', '_params', 'caseSensitive', 'mergeParams', 'strict', 'stack', 'length', 'name', 'prototype', 'arguments', 'caller']);
const FUNCTION_OWN = new Set(['length', 'name', 'prototype', 'arguments', 'caller']);

function describeProperty(descriptor) {
  const flags = `${descriptor.enumerable ? 'e' : '-'}${descriptor.writable ? 'w' : '-'}${descriptor.configurable ? 'c' : '-'}`;
  if (descriptor.get || descriptor.set) {
    return `accessor ${flags} get:${descriptor.get ? hash(descriptor.get.toString()) : '-'} set:${descriptor.set ? hash(descriptor.set.toString()) : '-'}`;
  }
  const { value } = descriptor;
  if (typeof value === 'function') return `function ${flags} ${describeFn(value)}`;
  if (value === null) return `null ${flags}`;
  if (typeof value === 'object') return `object ${flags} ${value.constructor ? value.constructor.name : 'Object'}`;
  return `${typeof value} ${flags} ${typeof value === 'string' ? hash(normalise(value)) : String(value)}`;
}

// A class: whether it has its own constructor, what it extends, its static members and its
// prototype, member by member.
function describeClass(cls) {
  const own = {};
  for (const name of Object.getOwnPropertyNames(cls).sort()) {
    if (!FUNCTION_OWN.has(name)) own[name] = describeProperty(Object.getOwnPropertyDescriptor(cls, name));
  }
  const proto = {};
  for (const name of Object.getOwnPropertyNames(cls.prototype).sort()) {
    if (name !== 'constructor') proto[name] = describeProperty(Object.getOwnPropertyDescriptor(cls.prototype, name));
  }
  const base = Object.getPrototypeOf(cls);
  const ctor = /\bconstructor\s*\(/.test(Function.prototype.toString.call(cls));
  return { extends: base && base.name ? base.name : null, constructor: ctor ? 'own' : 'inherited', static: own, prototype: proto };
}

function describeModule(exported) {
  const out = { type: isRouter(exported) ? 'router' : typeof exported };
  const skip = isRouter(exported) ? ROUTER_OWN : typeof exported === 'function' ? FUNCTION_OWN : new Set();
  if (typeof exported === 'function' && !isRouter(exported)) out.self = describeFn(exported);
  out.exports = {};
  out.classes = {};
  if (exported && (typeof exported === 'object' || typeof exported === 'function')) {
    for (const name of Object.getOwnPropertyNames(exported).sort()) {
      if (skip.has(name)) continue;
      const descriptor = Object.getOwnPropertyDescriptor(exported, name);
      out.exports[name] = describeProperty(descriptor);
      if (isClass(descriptor.value)) out.classes[name] = describeClass(descriptor.value);
    }
  }
  if (isClass(exported)) out.classes['(module)'] = describeClass(exported);
  else if (typeof exported === 'function' && exported.prototype && !isRouter(exported)) {
    const proto = {};
    for (const name of Object.getOwnPropertyNames(exported.prototype).sort()) {
      if (name !== 'constructor') proto[name] = describeProperty(Object.getOwnPropertyDescriptor(exported.prototype, name));
    }
    if (Object.keys(proto).length) out.prototype = proto;
  }
  return out;
}

function mountLines(root, config) {
  const out = {};
  for (const { file, pattern } of config.mountLines) {
    const full = path.join(root, file);
    out[file] = fs.existsSync(full) ? fs.readFileSync(full, 'utf8').split(/\r?\n/).map((l) => l.trim()).filter((l) => pattern.test(l)) : ['(missing)'];
  }
  return out;
}

// ---- snapshot ---------------------------------------------------------------------------

function prepareEnvironment(root, config) {
  const temps = [];
  for (const name of config.tempDirEnv) {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'shape-'));
    temps.push(dir);
    process.env[name] = dir;
  }
  process.on('exit', () => { for (const d of temps) { try { fs.rmSync(d, { recursive: true, force: true }); } catch { /* best effort */ } } });
  Object.assign(process.env, config.env);
  const attempts = installOutboundTrap();
  normalise = normaliser(root, temps);
  installFactoryTags(root, normalise);
  for (const file of config.setup) require(path.join(root, file));
  return attempts;
}

function runNode(args, cwd) {
  return new Promise((resolve) => {
    const child = spawn(process.execPath, args, { cwd, env: process.env, stdio: ['ignore', 'pipe', 'pipe'] });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (d) => { stdout += d; });
    child.stderr.on('data', (d) => { stderr += d; });
    child.on('close', (code) => resolve({ code, stdout, stderr }));
  });
}

// Loads one file first, alone, in a fresh process; reports its export names and any outbound
// connection attempted while loading.
async function coldLoad(root, configArgs, file) {
  const result = await runNode([__filename, '--cold', file, '--root', root, ...configArgs], root);
  const line = result.stdout.split(/\r?\n/).find((l) => l.startsWith('SHAPE-COLD '));
  if (result.code !== 0 || !line) {
    const errLines = result.stderr.trim().split(/\r?\n/).filter(Boolean);
    return { ok: false, error: (errLines.find((l) => /^\w*Error\b/.test(l)) || errLines.pop() || `exit ${result.code}`).slice(0, 300) };
  }
  return JSON.parse(line.slice('SHAPE-COLD '.length));
}

async function takeSnapshot(root, config, configArgs, coldFiles) {
  const attempts = prepareEnvironment(root, config);
  const snapshot = { modules: {}, routers: {}, mounts: mountLines(root, config), coldLoads: {}, outbound: [] };
  for (const file of config.modules) {
    const full = path.join(root, file);
    if (!fs.existsSync(full)) { snapshot.modules[file] = '(missing)'; continue; }
    let exported;
    try { exported = require(full); } catch (err) { snapshot.modules[file] = { loadError: String(err.message).split('\n')[0].slice(0, 300) }; continue; }
    snapshot.modules[file] = describeModule(exported);
    if (isRouter(exported) && !config.routers.some((r) => r.file === file)) snapshot.routers[`${file}`] = describeRouter(exported, '');
  }
  for (const { mount, file } of config.routers) {
    const full = path.join(root, file);
    let router = null;
    try { router = fs.existsSync(full) ? require(full) : null; } catch { /* reported with its module */ }
    snapshot.routers[`${mount} ${file}`] = router ? describeRouter(router, mount) : ['(missing or not loaded)'];
  }
  const cold = await Promise.all(coldFiles.map((file) => coldLoad(root, configArgs, file)));
  coldFiles.forEach((file, i) => { snapshot.coldLoads[file] = cold[i]; });
  snapshot.outbound = [...attempts];
  return snapshot;
}

// ---- comparison -------------------------------------------------------------------------

function flatten(value, prefix = '', out = []) {
  if (Array.isArray(value)) value.forEach((v) => (typeof v === 'object' && v !== null ? flatten(v, `${prefix}[]`, out) : out.push(`${prefix}: ${v}`)));
  else if (value && typeof value === 'object') for (const key of Object.keys(value)) flatten(value[key], prefix ? `${prefix} > ${key}` : key, out);
  else out.push(`${prefix}: ${value}`);
  return out;
}

// Ordered comparison: a moved line shows as removed in one place and added in another.
function diffLines(a, b) {
  const lcs = Array.from({ length: a.length + 1 }, () => new Uint32Array(b.length + 1));
  for (let i = a.length - 1; i >= 0; i -= 1) {
    for (let j = b.length - 1; j >= 0; j -= 1) lcs[i][j] = a[i] === b[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1]);
  }
  const out = [];
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) { i += 1; j += 1; } else if (lcs[i + 1][j] >= lcs[i][j + 1]) { out.push(`- ${a[i]}`); i += 1; } else { out.push(`+ ${b[j]}`); j += 1; }
  }
  while (i < a.length) { out.push(`- ${a[i]}`); i += 1; }
  while (j < b.length) { out.push(`+ ${b[j]}`); j += 1; }
  return out;
}

// Cold loads of files that exist on only one side are not a difference; everything else is.
function compareSnapshots(before, after, modules) {
  const pick = (s) => ({ ...s, coldLoads: Object.fromEntries(Object.entries(s.coldLoads || {}).filter(([f]) => modules.includes(f))) });
  const differences = diffLines(flatten(pick(before)), flatten(pick(after)));
  const problems = [];
  for (const [file, result] of Object.entries(after.coldLoads || {})) {
    if (!result.ok) problems.push(`loading alone failed: ${file}: ${result.error}`);
    else if (result.outbound && result.outbound.length) problems.push(`loading alone made outbound connections: ${file}: ${result.outbound.join(', ')}`);
  }
  for (const [file, result] of Object.entries(after.modules || {})) if (result && result.loadError) problems.push(`loading failed: ${file}: ${result.loadError}`);
  if ((after.outbound || []).length) problems.push(`outbound connections while loading: ${after.outbound.join(', ')}`);
  return { differences, problems };
}

// ---- command line -----------------------------------------------------------------------

// Files changed since the ref, including new files not yet added to git.
function changedFiles(root, ref, config) {
  const changed = execFileSync('git', ['diff', '--name-only', '--diff-filter=AMR', ref, '--', ...config.coldDirs], { cwd: root, encoding: 'utf8' });
  const added = execFileSync('git', ['ls-files', '--others', '--exclude-standard', '--', ...config.coldDirs], { cwd: root, encoding: 'utf8' });
  return [...new Set(`${changed}\n${added}`.split(/\r?\n/))].filter((f) => /\.c?js$/.test(f) && !config.coldIgnore.some((frag) => f.includes(frag)));
}

async function snapshotOfRef(root, ref, configArgs) {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'shape-ref-'));
  const tree = path.join(temp, 'tree');
  execFileSync('git', ['worktree', 'add', '--detach', tree, ref], { cwd: root, stdio: 'ignore' });
  try {
    if (fs.existsSync(path.join(root, 'node_modules'))) fs.symlinkSync(path.join(root, 'node_modules'), path.join(tree, 'node_modules'), 'junction');
    const outFile = path.join(temp, 'snapshot.json');
    const result = await runNode([__filename, '--root', tree, '--out', outFile, ...configArgs], tree);
    if (result.code !== 0) throw new Error(`snapshot of ${ref} failed: ${result.stderr.slice(-800)}`);
    return JSON.parse(fs.readFileSync(outFile, 'utf8'));
  } finally {
    try { fs.unlinkSync(path.join(tree, 'node_modules')); } catch { /* not made */ }
    execFileSync('git', ['worktree', 'remove', '--force', tree], { cwd: root, stdio: 'ignore' });
    fs.rmSync(temp, { recursive: true, force: true });
  }
}

function report({ differences, problems }, label) {
  for (const p of problems) console.log(`PROBLEM ${p}`);
  if (differences.length) {
    console.log(`${differences.length} difference(s) from ${label}:`);
    for (const line of differences.slice(0, 200)) console.log(`  ${line}`);
    if (differences.length > 200) console.log(`  … ${differences.length - 200} more`);
  }
  if (!differences.length && !problems.length) console.log(`Shape unchanged from ${label}.`);
  return differences.length || problems.length ? 1 : 0;
}

async function main(argv) {
  const { options } = parseArgs(argv, { usage: USAGE });
  const root = path.resolve(options.root || process.cwd());
  // A configuration outside the tree is passed on as an absolute path; one inside it is found again
  // in the other tree.
  const configArgs = [];
  if (options.config) configArgs.push('--config', path.resolve(options.config));
  if (options.modules) configArgs.push('--modules', options.modules);
  const config = loadConfig(root, options.config, options.modules);

  if (options.cold) {
    const attempts = prepareEnvironment(root, config);
    const exported = require(path.join(root, options.cold));
    const names = exported && (typeof exported === 'object' || typeof exported === 'function')
      ? Object.getOwnPropertyNames(exported).filter((n) => !(isRouter(exported) ? ROUTER_OWN : FUNCTION_OWN).has(n)).sort()
      : [];
    console.log(`SHAPE-COLD ${JSON.stringify({ ok: true, exports: names, outbound: [...attempts] })}`);
    process.exit(0);
  }

  const ref = options['compare-ref'];
  const coldFiles = ref ? [...new Set([...config.modules, ...changedFiles(root, ref, config)])] : config.modules;
  const snapshot = await takeSnapshot(root, config, configArgs, coldFiles);
  if (ref) process.exit(report(compareSnapshots(await snapshotOfRef(root, ref, configArgs), snapshot, config.modules), ref));
  if (options.compare) process.exit(report(compareSnapshots(JSON.parse(fs.readFileSync(options.compare, 'utf8')), snapshot, config.modules), options.compare));
  const text = `${JSON.stringify(snapshot, null, 1)}\n`;
  if (options.out) fs.writeFileSync(options.out, text); else process.stdout.write(text);
  process.exit(0);
}

if (require.main === module) {
  main(process.argv.slice(2)).catch((err) => {
    console.error(err && err.stack ? err.stack : err);
    process.exit(2);
  });
}

module.exports = { compareSnapshots, describeModule, describeRouter, diffLines, flatten, installOutboundTrap };
