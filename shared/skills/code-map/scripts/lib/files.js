'use strict';
// Lists and classifies the repository's files. Uses Git when the folder is a Git checkout, so
// ignored files stay out; otherwise walks the folder. Part of the code-map skill
// (canonical copy: /shared/skills/code-map/).

const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const { matchesAny } = require('./config');

const LANGUAGE = {
  js: 'javascript', mjs: 'javascript', cjs: 'javascript', jsx: 'javascript',
  ts: 'typescript', mts: 'typescript', cts: 'typescript', tsx: 'typescript',
  vue: 'vue', html: 'html', htm: 'html', py: 'python', sql: 'sql', prisma: 'prisma', json: 'json',
  ps1: 'powershell', psm1: 'powershell', sh: 'shell', bash: 'shell', php: 'php', ejs: 'ejs',
  css: 'css', scss: 'css', md: 'markdown', svelte: 'svelte', go: 'go', rb: 'ruby', cs: 'csharp',
  java: 'java', kt: 'kotlin', swift: 'swift', rs: 'rust', yml: 'yaml', yaml: 'yaml',
};

function extOf(file) {
  const m = /\.([A-Za-z0-9]+)$/.exec(file);
  return m ? m[1].toLowerCase() : '';
}

// Git's own list of files, honouring .gitignore – but only when the folder is the top of its own
// work tree. A folder inside another repository (a copy, a scratch folder, an ignored path) is walked
// instead: asking the outer repository would list nothing and map nothing, silently.
function gitFiles(root) {
  try {
    const top = execFileSync('git', ['-C', root, 'rev-parse', '--show-toplevel'], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim();
    if (path.resolve(top).toLowerCase() !== path.resolve(root).toLowerCase()) return null;
    const out = execFileSync('git', ['-C', root, 'ls-files', '-z', '--cached', '--others', '--exclude-standard'],
      { encoding: 'utf8', maxBuffer: 256 << 20, stdio: ['ignore', 'pipe', 'ignore'] });
    const list = out.split('\0').filter(Boolean);
    return list.length ? list : null;
  } catch {
    return null;
  }
}

function walkFiles(root) {
  const out = [];
  const visit = (dir, rel) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (entry.name === '.git' || entry.name === 'node_modules') continue;
      const r = rel ? `${rel}/${entry.name}` : entry.name;
      if (entry.isDirectory()) visit(path.join(dir, entry.name), r);
      else if (entry.isFile()) out.push(r);
    }
  };
  visit(root, '');
  return out;
}

function countLines(text) {
  if (!text) return 0;
  let n = 1;
  for (let i = 0; i < text.length; i++) if (text.charCodeAt(i) === 10) n++;
  if (text.endsWith('\n')) n--;
  return n;
}

// Every mapped file: { file, ext, language, lines, test, sizeExempt, code }.
function listFiles(root, config) {
  const all = (gitFiles(root) || walkFiles(root)).map((f) => f.replace(/\\/g, '/'));
  const files = [];
  for (const file of all) {
    if (matchesAny(file, config.ignore)) continue;
    const full = path.join(root, file);
    let stat;
    try { stat = fs.statSync(full); } catch { continue; }
    if (!stat.isFile()) continue;
    const ext = extOf(file);
    const language = LANGUAGE[ext] || null;
    const entry = {
      file, ext, language, bytes: stat.size,
      test: matchesAny(file, config.tests),
      sizeExempt: matchesAny(file, config.sizeExempt),
      code: config.codeExtensions.includes(ext),
      lines: null,
    };
    files.push(entry);
  }
  files.sort((a, b) => (a.file < b.file ? -1 : a.file > b.file ? 1 : 0));
  return files;
}

// Reads a file's text once; binary or huge files return null.
function readText(root, entry) {
  if (entry.text !== undefined) return entry.text;
  if (entry.bytes > 8 * 1024 * 1024) { entry.text = null; return null; }
  try {
    const buf = fs.readFileSync(path.join(root, entry.file));
    if (buf.includes(0)) { entry.text = null; return null; }
    entry.text = buf.toString('utf8');
  } catch {
    entry.text = null;
  }
  if (entry.text !== null) entry.lines = countLines(entry.text);
  return entry.text;
}

module.exports = { listFiles, readText, countLines, extOf, LANGUAGE };
