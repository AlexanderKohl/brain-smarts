'use strict';
// Turns a JavaScript-family file into facts: plain JS/TS/JSX/TSX, the script blocks of a Vue
// single-file component, and the inline scripts of an HTML page. Also reads the aliases a project
// declares for imports. Part of the code-map skill (canonical copy: /shared/skills/code-map/).

const path = require('path');
const A = require('./ast');
const { extractJs } = require('./extract');

let sfc = null;
function vueCompiler() {
  if (sfc === null) {
    try { sfc = require('@vue/compiler-sfc'); } catch {
      try { sfc = require('vue/compiler-sfc'); } catch { sfc = false; }
    }
  }
  return sfc;
}

function segmentsFor(entry, text) {
  if (entry.language === 'vue') {
    const compiler = vueCompiler();
    if (!compiler) return { segments: [], missing: '@vue/compiler-sfc' };
    const { descriptor } = compiler.parse(text, { filename: entry.file, sourceMap: false });
    const segments = [];
    for (const block of [descriptor.script, descriptor.scriptSetup]) {
      if (!block) continue;
      const ts = /^tsx?$/.test(block.lang || '');
      segments.push({ text: block.content, startLine: block.loc.start.line, typescript: ts });
    }
    return { segments };
  }
  if (entry.language === 'html') {
    const segments = [];
    const re = /<script\b([^>]*)>([\s\S]*?)<\/script>/gi;
    let m;
    while ((m = re.exec(text))) {
      const attrs = m[1];
      if (/\bsrc\s*=/.test(attrs)) continue;
      const type = /\btype\s*=\s*["']?([^"'\s>]+)/i.exec(attrs);
      if (type && !/^(module|text\/javascript|application\/javascript)$/i.test(type[1])) continue;
      const startLine = text.slice(0, m.index + m[0].indexOf('>') + 1).split('\n').length;
      segments.push({ text: m[2], startLine, typescript: false });
    }
    return { segments };
  }
  return { segments: [{ text, startLine: 1, typescript: null }] };
}

function loadJs(entry, text, hints) {
  const { segments, missing } = segmentsFor(entry, text);
  if (missing) return { facts: null, missing };
  return { facts: extractJs(entry.file, entry.language, entry.lines, segments, hints) };
}

// ---------- aliases ----------

function stripJsonComments(text) {
  let out = '';
  let inString = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inString) {
      out += c;
      if (c === '\\') { out += text[++i] || ''; continue; }
      if (c === '"') inString = false;
      continue;
    }
    if (c === '"') { inString = true; out += c; continue; }
    if (c === '/' && text[i + 1] === '/') { while (i < text.length && text[i] !== '\n') i++; out += '\n'; continue; }
    if (c === '/' && text[i + 1] === '*') { i += 2; while (i < text.length && !(text[i] === '*' && text[i + 1] === '/')) i++; i++; continue; }
    out += c;
  }
  return out.replace(/,(\s*[}\]])/g, '$1');
}

// tsconfig.json / jsconfig.json `compilerOptions.paths`.
function tsconfigAliases(file, text) {
  let json;
  try { json = JSON.parse(stripJsonComments(text)); } catch { return []; }
  const opts = json.compilerOptions || {};
  const dir = path.posix.dirname(file) === '.' ? '' : path.posix.dirname(file);
  const baseUrl = path.posix.join(dir, opts.baseUrl || '.');
  const out = [];
  for (const [pattern, targets] of Object.entries(opts.paths || {})) {
    if (!Array.isArray(targets) || !targets.length) continue;
    const from = pattern.replace(/\*$/, '');
    const to = path.posix.join(baseUrl, String(targets[0]).replace(/\*$/, ''));
    out.push({ scope: dir ? `${dir}/` : '', from, to: from.endsWith('/') ? `${to}/` : to, source: file });
  }
  return out;
}

// A literal `resolve: { alias: { '@': path.resolve(__dirname, './src') } }` in a Vite config.
function viteAliases(file, text) {
  let ast;
  try { ast = A.parse(text, file); } catch { return []; }
  const dir = path.posix.dirname(file) === '.' ? '' : path.posix.dirname(file);
  const out = [];
  A.walk(ast.program, (node) => {
    if (node.type !== 'ObjectProperty' || A.keyName(node.key, node.computed) !== 'alias') return;
    const value = A.unwrap(node.value);
    if (value.type !== 'ObjectExpression') return;
    for (const prop of value.properties) {
      if (prop.type !== 'ObjectProperty') continue;
      const from = A.keyName(prop.key, prop.computed);
      const target = aliasTarget(A.unwrap(prop.value));
      if (from && target !== null) {
        const to = path.posix.join(dir, target);
        out.push({ scope: dir ? `${dir}/` : '', from: `${from}/`, to: `${to}/`, source: file });
      }
    }
    return false;
  });
  return out;
}

function aliasTarget(node) {
  if (!node) return null;
  const literal = A.staticString(node);
  if (literal !== null) return literal.replace(/^\.\//, '');
  // path.resolve(__dirname, './src') / path.join(__dirname, 'src')
  if (A.isCall(node)) {
    const chain = A.memberChain(node.callee);
    if (chain.root && chain.root.type === 'Identifier' && chain.root.name === 'path' && /^(resolve|join)$/.test(chain.path[0])) {
      const parts = node.arguments.slice(1).map((a) => A.staticString(a));
      if (node.arguments[0] && node.arguments[0].type === 'Identifier' && node.arguments[0].name === '__dirname' && parts.every((p) => p !== null)) {
        return path.posix.join(...parts).replace(/^\.\//, '');
      }
    }
    // fileURLToPath(new URL('./src', import.meta.url))
    const arg = node.arguments[0] && A.unwrap(node.arguments[0]);
    if (arg && arg.type === 'NewExpression' && arg.callee.name === 'URL') {
      const s = A.staticString(arg.arguments[0]);
      if (s !== null) return s.replace(/^\.\//, '').replace(/\/$/, '');
    }
  }
  return null;
}

module.exports = { loadJs, tsconfigAliases, viteAliases, stripJsonComments, vueCompiler };
