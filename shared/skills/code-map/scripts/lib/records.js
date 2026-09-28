'use strict';
// The committed records a project keeps beside its code: the recorded size of each file already
// over the limit (sizes only go down), the public interface, and the findings that existed when the
// project adopted the code map. Part of the code-map skill (canonical copy: /shared/skills/code-map/).

const fs = require('fs');
const path = require('path');
const { natural } = require('./graph');
const { interfaceOf } = require('./checks');

const FILES = { sizes: 'sizes.json', interface: 'interface.json', known: 'known-findings.json' };

function recordDir(map, override) {
  return override ? path.resolve(override) : path.join(map.root, map.config.recordDir);
}

function readJson(file, fallback) {
  if (!fs.existsSync(file)) return fallback;
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}

function loadRecords(dir) {
  return {
    present: fs.existsSync(path.join(dir, FILES.sizes)),
    sizes: readJson(path.join(dir, FILES.sizes), {}),
    interface: readJson(path.join(dir, FILES.interface), null),
    known: readJson(path.join(dir, FILES.known), []),
  };
}

function sortedObject(obj) {
  const out = {};
  for (const k of Object.keys(obj).sort(natural)) out[k] = obj[k];
  return out;
}

function write(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
}

// `adopt`: the first record of a project – every oversized file and every current finding is
// accepted as it stands. Otherwise: the interface is re-recorded, recorded sizes only go down, and
// known findings that have been fixed are removed; nothing new is ever accepted silently.
function writeRecords(map, dir, result, { adopt = false } = {}) {
  const old = loadRecords(dir);
  const limit = map.config.limits.fileLines;
  const sizes = {};
  for (const e of map.files) {
    if (!e.code || e.sizeExempt || !e.lines || e.lines <= limit) continue;
    const was = old.sizes[e.file];
    if (adopt) sizes[e.file] = e.lines;
    else if (was !== undefined) sizes[e.file] = Math.min(was, e.lines);
  }
  const present = new Set(result.all.map((f) => f.key));
  const known = adopt
    ? result.all.filter((f) => f.check !== 'interface' && f.check !== 'size').map((f) => f.key)
    : old.known.filter((k) => present.has(k));
  write(path.join(dir, FILES.sizes), sortedObject(sizes));
  write(path.join(dir, FILES.interface), interfaceOf(map));
  write(path.join(dir, FILES.known), [...new Set(known)].sort(natural));
  return { dir, sizes: Object.keys(sizes).length, known: known.length };
}

module.exports = { loadRecords, writeRecords, recordDir, FILES };
