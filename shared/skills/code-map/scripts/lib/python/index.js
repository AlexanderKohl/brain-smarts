'use strict';
// Runs the Python extractor (Python's own parser, standard library only) and resolves Python
// imports to repository files the way a script run from its own folder would find them.
// Part of the code-map skill (canonical copy: /shared/skills/code-map/).

const path = require('path');
const { spawnSync } = require('child_process');

const EXTRACTOR = path.join(__dirname, 'extract.py');

function findPython(configured) {
  const candidates = configured ? [configured] : process.platform === 'win32' ? ['python', 'py', 'python3'] : ['python3', 'python'];
  for (const cmd of candidates) {
    const r = spawnSync(cmd, ['-c', 'import sys; print(sys.version_info[0] * 100 + sys.version_info[1])'], { encoding: 'utf8' });
    if (r.status === 0 && Number(r.stdout.trim()) >= 308) return cmd;
  }
  return null;
}

// -> { results: Map(file -> facts), error }
function extractPython(root, files, config) {
  const results = new Map();
  if (!files.length) return { results };
  const cmd = findPython(config.python.command);
  if (!cmd) return { results, error: 'Python 3.8 or later was not found; Python files get sizes only' };
  const batch = 400;
  for (let i = 0; i < files.length; i += batch) {
    const chunk = files.slice(i, i + batch);
    const r = spawnSync(cmd, [EXTRACTOR, root], { input: JSON.stringify(chunk), encoding: 'utf8', maxBuffer: 512 << 20 });
    if (r.status !== 0) return { results, error: `Python extractor failed: ${(r.stderr || '').split('\n').filter(Boolean).pop() || r.status}` };
    for (const facts of JSON.parse(r.stdout)) results.set(facts.file, facts);
  }
  return { results };
}

function resolvePy(fromFile, imp, fileSet, roots) {
  const tryMod = (base, mod) => {
    const p = base ? `${base}/${mod}` : mod;
    if (fileSet.has(`${p}.py`)) return `${p}.py`;
    if (fileSet.has(`${p}/__init__.py`)) return `${p}/__init__.py`;
    return null;
  };
  const out = [];
  let dir = path.posix.dirname(fromFile);
  if (dir === '.') dir = '';
  if (imp.level > 0) {
    let base = dir;
    for (let i = 1; i < imp.level; i++) base = path.posix.dirname(base) === '.' ? '' : path.posix.dirname(base);
    const mod = imp.module ? imp.module.replace(/\./g, '/') : '';
    const hit = mod ? tryMod(base, mod) : null;
    if (hit) out.push(hit);
    for (const name of imp.names) { const sub = tryMod(base, mod ? `${mod}/${name}` : name); if (sub) out.push(sub); }
    return out.length ? { files: out } : { unresolved: true };
  }
  const mod = imp.module.replace(/\./g, '/');
  for (const base of [dir, '', ...roots]) {
    const hit = tryMod(base, mod);
    if (!hit) continue;
    out.push(hit);
    for (const name of imp.names) { const sub = tryMod(base, `${mod}/${name}`); if (sub) out.push(sub); }
    return { files: out };
  }
  return { package: imp.module.split('.')[0], stdlib: !!imp.stdlib };
}

module.exports = { extractPython, resolvePy, findPython };
