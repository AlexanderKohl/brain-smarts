'use strict';
// Shared parsing for the JavaScript split tools: the top-level statements of a CommonJS file or an
// ES module, with their line ranges, the names each declares, reads and assigns, and the import each
// one is (a `require` or an `import` declaration).
// `refs` gives the top-level names a statement uses, resolved through its own scopes (lib/scope.js),
// so a local variable is not taken for a top-level one of the same name; `uses` over-counts (every
// identifier) and is kept for what needs no scopes: `this.x` members and `super`.
// Part of the split-file skill (canonical copy: /shared/skills/split-file/).

const fs = require('fs');
const parser = require('@babel/parser');
const { freeNames } = require('./scope');

/** { read, assigned }: the names a node uses that it does not declare itself (see lib/scope.js). */
const refs = (node) => freeNames(node);

const SKIP_KEYS = new Set(['loc', 'start', 'end', 'leadingComments', 'trailingComments', 'innerComments', 'extra']);

// The file's text with LF line endings, and the line ending to write back.
function readSource(file) {
  const raw = fs.readFileSync(file, 'utf8');
  const eol = raw.includes('\r\n') ? '\r\n' : '\n';
  const text = raw.replace(/\r\n/g, '\n');
  return { eol, text, lines: text.split('\n') };
}

function writeText(file, text, eol) {
  fs.writeFileSync(file, text.replace(/\n/g, eol));
}

// An ES module when the file is .mjs, CommonJS when it is .cjs; otherwise a module only when the
// text holds import or export (a .js file in a package of type "module").
function parse(text, { recover = false, file = '' } = {}) {
  return parser.parse(text, {
    sourceType: /\.mjs$/i.test(file) ? 'module' : /\.cjs$/i.test(file) ? 'script' : 'unambiguous',
    allowReturnOutsideFunction: true,
    errorRecovery: recover,
    plugins: ['optionalChaining', 'nullishCoalescingOperator', 'classProperties'],
  });
}

// The declaration inside `export function f`, `export const x = …` or `export class C`; any other
// statement as it is.
const unwrap = (stmt) => (stmt.type === 'ExportNamedDeclaration' && stmt.declaration ? stmt.declaration : stmt);

// The tools that write CommonJS wiring (move-block.js, move-methods.js) refuse an ES module.
function commonJsOnly(ast, file, tool) {
  if (ast.program.sourceType === 'module') throw new Error(`${file} is an ES module; ${tool} moves CommonJS code only (move.js moves an ES module's declarations)`);
}

// Names a top-level statement declares: its declarations, exported or not, and an import's names.
function declared(statement) {
  const stmt = unwrap(statement);
  const out = [];
  const pat = (p) => {
    if (!p) return;
    if (p.type === 'Identifier') out.push(p.name);
    else if (p.type === 'ObjectPattern') p.properties.forEach((q) => pat(q.type === 'RestElement' ? q.argument : q.value));
    else if (p.type === 'ArrayPattern') p.elements.forEach(pat);
    else if (p.type === 'AssignmentPattern') pat(p.left);
    else if (p.type === 'RestElement') pat(p.argument);
  };
  if ((stmt.type === 'FunctionDeclaration' || stmt.type === 'ClassDeclaration') && stmt.id) out.push(stmt.id.name);
  if (stmt.type === 'VariableDeclaration') stmt.declarations.forEach((d) => pat(d.id));
  if (stmt.type === 'ImportDeclaration') stmt.specifiers.forEach((sp) => out.push(sp.local.name));
  return out;
}

function eachChild(n, fn) {
  for (const k of Object.keys(n)) {
    if (SKIP_KEYS.has(k)) continue;
    const v = n[k];
    if (Array.isArray(v)) v.forEach((c) => { if (c && typeof c.type === 'string') fn(c, k); });
    else if (v && typeof v.type === 'string') fn(v, k);
  }
}

// Identifiers read, and identifiers assigned (x = …, x++), anywhere in a node; whether it uses
// `super`; and the `this.x` members it touches.
function uses(node) {
  const read = new Set();
  const assigned = new Set();
  const thisMembers = new Set();
  let usesSuper = false;
  const visit = (n, parent, key) => {
    if (n.type === 'Super') { usesSuper = true; return; }
    if (n.type === 'Identifier') {
      const skip = (parent && /MemberExpression$/.test(parent.type) && key === 'property' && !parent.computed)
        || (parent && ['ObjectProperty', 'ObjectMethod', 'ClassMethod', 'ClassProperty'].includes(parent.type) && key === 'key' && !parent.computed)
        || (parent && ['LabeledStatement', 'BreakStatement', 'ContinueStatement'].includes(parent.type));
      if (!skip) read.add(n.name);
      if (parent && ((parent.type === 'AssignmentExpression' && key === 'left') || parent.type === 'UpdateExpression')) assigned.add(n.name);
      return;
    }
    if (/MemberExpression$/.test(n.type) && n.object.type === 'ThisExpression' && !n.computed && n.property.type === 'Identifier') thisMembers.add(n.property.name);
    eachChild(n, (c, k) => visit(c, n, k));
  };
  visit(node, null, null);
  return { read, assigned, thisMembers, usesSuper };
}

// Whether a node uses a private class member (#name), which only its own class can reach.
function usesPrivate(node) {
  let found = false;
  const visit = (n) => {
    if (found) return;
    if (n.type === 'PrivateName') { found = true; return; }
    eachChild(n, visit);
  };
  visit(node);
  return found;
}

// Names that mean something else in another file: the module object, its exports, its file name,
// `this` at the top level (module.exports in CommonJS) and an ES module's `import.meta`. __dirname is
// the same in a module in the same folder, so it is allowed.
function fileBound(node) {
  const found = new Set();
  const visit = (n, parent, key, inFunction) => {
    if (n.type === 'Identifier' && ['module', 'exports', '__filename'].includes(n.name)
      && !(parent && /MemberExpression$/.test(parent.type) && key === 'property' && !parent.computed)
      && !(parent && ['ObjectProperty', 'ObjectMethod'].includes(parent.type) && key === 'key' && !parent.computed)) found.add(n.name);
    if (n.type === 'ThisExpression' && !inFunction) found.add('this');
    if (n.type === 'MetaProperty' && n.meta.name === 'import') found.add('import.meta');
    const fn = ['FunctionDeclaration', 'FunctionExpression', 'ObjectMethod', 'ClassMethod', 'ClassPrivateMethod'].includes(n.type);
    eachChild(n, (c, k) => visit(c, n, k, inFunction || fn));
  };
  visit(node, null, null, false);
  return found;
}

// A value whose evaluation has no effects: a function, a literal, an empty Map or Set, and arrays,
// objects and Object.freeze of those.
function isPure(n) {
  if (!n) return true;
  if (['ArrowFunctionExpression', 'FunctionExpression', 'StringLiteral', 'NumericLiteral', 'BooleanLiteral', 'NullLiteral', 'RegExpLiteral', 'Identifier', 'ThisExpression'].includes(n.type)) return true;
  // Reading a property (a getter aside) and combining values run nothing.
  if (n.type === 'MemberExpression') return isPure(n.object) && (!n.computed || isPure(n.property));
  if (n.type === 'ConditionalExpression') return isPure(n.test) && isPure(n.consequent) && isPure(n.alternate);
  if (n.type === 'BinaryExpression' || n.type === 'LogicalExpression') return isPure(n.left) && isPure(n.right);
  if (n.type === 'TemplateLiteral') return n.expressions.length === 0;
  if (n.type === 'UnaryExpression' && ['-', '+', '!'].includes(n.operator)) return isPure(n.argument);
  if (n.type === 'NewExpression') return n.callee.type === 'Identifier' && /^(Map|Set|WeakMap|WeakSet)$/.test(n.callee.name) && n.arguments.length === 0;
  if (n.type === 'ArrayExpression') return n.elements.every(isPure);
  if (n.type === 'ObjectExpression') return n.properties.every((q) => q.type === 'ObjectProperty' && !q.computed && isPure(q.value));
  if (n.type === 'CallExpression') {
    return n.callee.type === 'MemberExpression' && n.callee.object.name === 'Object' && n.callee.property.name === 'freeze' && n.arguments.every(isPure);
  }
  return false;
}

// A top-level `const x = require('…')` or `const { a, b } = require('…')`. The argument is kept as
// written: a module in the same folder resolves the same text the same way, including
// require(__dirname + '/…').
function requireOf(stmt, text) {
  if (stmt.type !== 'VariableDeclaration' || stmt.declarations.length !== 1) return null;
  const d = stmt.declarations[0];
  const init = d.init;
  if (!init || init.type !== 'CallExpression' || init.callee.name !== 'require' || !init.arguments[0]) return null;
  const source = text.slice(init.arguments[0].start, init.arguments[0].end);
  if (d.id.type === 'Identifier') return { source, whole: d.id.name, kind: stmt.kind };
  if (d.id.type === 'ObjectPattern' && d.id.properties.every((p) => p.type === 'ObjectProperty' && p.key.type === 'Identifier' && p.value.type === 'Identifier' && p.key.name === p.value.name)) {
    return { source, names: d.id.properties.map((p) => p.key.name), kind: stmt.kind };
  }
  return null;
}

// A top-level `import … from '…'` with the names it binds. Each specifier keeps its text (`a`,
// `a as b`, `* as ns`, a default name), and `from` the rest of the statement as written: the source
// and any import attributes (`with { type: 'json' }`). A module in the same folder resolves the same
// source the same way. A bare `import './x.mjs'` binds nothing and is not one.
function importOf(stmt, text) {
  if (stmt.type !== 'ImportDeclaration' || !stmt.specifiers.length) return null;
  return {
    esm: true,
    specifiers: stmt.specifiers.map((sp) => ({ local: sp.local.name, text: text.slice(sp.start, sp.end), type: sp.type })),
    from: text.slice(stmt.source.start, stmt.end),
  };
}

// The import declaration for the specifiers of `req` whose names are in `names`, in the source's
// order: a default and a namespace import first, then the named ones in braces.
function importLine(req, names) {
  const kept = req.specifiers.filter((sp) => names.has(sp.local));
  const lead = kept.filter((sp) => sp.type !== 'ImportSpecifier').map((sp) => sp.text);
  const named = kept.filter((sp) => sp.type === 'ImportSpecifier').map((sp) => sp.text);
  const head = [...lead, ...(named.length ? [braceList(named, 14 + lead.join(', ').length + req.from.length)] : [])].join(', ');
  return `import ${head} from ${req.from}${req.from.endsWith(';') ? '' : ';'}`;
}

const KIND = { FunctionDeclaration: 'function', ClassDeclaration: 'class' };

// The first line of a node with its leading comments. Babel attaches a comment that trails the
// previous node on its last line (`const a = 1; // note`) as a leading comment of the next node;
// such a comment stays with the line it is on, so only a comment that begins after `prevEnd` (the
// previous node's last line; 0 when there is none) counts towards the start.
function firstLine(node, prevEnd = 0) {
  const own = (node.leadingComments || []).find((c) => c.loc.start.line > prevEnd);
  return own ? own.loc.start.line : node.loc.start.line;
}

// Every top-level statement: its node, first line with its leading comments (`from`), first and
// last line, the names it declares, its kind, its import form, whether it exports what it declares
// (`export function f`), and the name a default export declares (`export default function f`).
function statements(ast, text) {
  const stmts = ast.program.body.map((s, i, all) => {
    const inner = unwrap(s);
    return {
      node: s,
      from: firstLine(s, i ? all[i - 1].loc.end.line : 0),
      start: s.loc.start.line,
      end: s.loc.end.line,
      declares: declared(s),
      kind: inner.type === 'VariableDeclaration' ? inner.kind : KIND[inner.type] || null,
      req: requireOf(inner, text) || importOf(s, text),
      exported: inner !== s,
      defaultName: s.type === 'ExportDefaultDeclaration' && s.declaration.id ? s.declaration.id.name : null,
    };
  });
  // `const { a, b } = logging` where `logging = require('./logging')`: the same names come straight
  // from require('./logging') in a new module.
  const wholeBy = new Map(stmts.filter((x) => x.req && x.req.whole).map((x) => [x.req.whole, x.req]));
  for (const x of stmts) {
    if (x.req || x.node.type !== 'VariableDeclaration' || x.node.declarations.length !== 1) continue;
    const d = x.node.declarations[0];
    if (!d.init || d.init.type !== 'Identifier' || !wholeBy.has(d.init.name) || d.id.type !== 'ObjectPattern') continue;
    if (!d.id.properties.every((p) => p.type === 'ObjectProperty' && p.key.type === 'Identifier' && p.value.type === 'Identifier' && p.key.name === p.value.name)) continue;
    x.req = { source: wholeBy.get(d.init.name).source, names: d.id.properties.map((p) => p.key.name), kind: x.node.kind };
  }
  return stmts;
}

// Import lines for a new module: for each needed name that an import of the source provides, the
// same import, narrowed to the names needed, in the source's order. Returns the lines and the names
// that stay behind in the source as something other than an import.
function importsFor(needed, stmts, exclude) {
  const provider = new Map();
  for (const s of stmts) if (!exclude.includes(s)) for (const n of s.declares) provider.set(n, s);
  const bySource = new Map();
  const behind = [];
  for (const n of [...needed].sort()) {
    const s = provider.get(n);
    if (!s) continue; // a global such as console, process or Buffer
    if (!s.req) { behind.push({ name: n, line: s.start }); continue; }
    if (!bySource.has(s.start)) bySource.set(s.start, { req: s.req, names: new Set(), whole: false });
    if (s.req.whole) bySource.get(s.start).whole = true; else bySource.get(s.start).names.add(n);
  }
  const lines = [...bySource.entries()].sort((a, b) => a[0] - b[0]).map(([, info]) => {
    if (info.req.esm) return importLine(info.req, info.names);
    return info.whole
      ? `${info.req.kind} ${info.req.whole} = require(${info.req.source});`
      : `${info.req.kind} ${braceList(info.req.names.filter((x) => info.names.has(x)), info.req.kind.length + info.req.source.length + 16)} = require(${info.req.source});`;
  });
  return { lines, behind };
}

// A comment as `// ` lines of at most `width` characters.
function commentLines(text, width = 100) {
  const out = [];
  let line = '//';
  for (const word of String(text).split(/\s+/).filter(Boolean)) {
    if (line.length + 1 + word.length > width && line !== '//') { out.push(line); line = '//'; }
    line += ` ${word}`;
  }
  out.push(line);
  return out;
}

// `{ a, b, c }`, over several lines when it would pass 100 characters.
function braceList(names, indent = 0) {
  const one = `{ ${names.join(', ')} }`;
  if (one.length + indent <= 100) return one;
  const out = ['{'];
  let line = '  ';
  for (const n of names) {
    const piece = `${n}, `;
    if (line.length + piece.length > 98) { out.push(line.trimEnd()); line = '  '; }
    line += piece;
  }
  out.push(line.trimEnd());
  out.push('}');
  return out.join('\n');
}

// The line after which a new `require` of moved code goes: after the last top-level require that
// comes before the first remaining statement using a moved name, so every use sees it loaded. In an
// ES module, whose imports load before any of its statements run, after its last import.
function backRequireLine(staying, movedNames) {
  const imports = staying.filter((s) => s.node.type === 'ImportDeclaration');
  if (imports.length) return Math.max(...imports.map((s) => s.end));
  const firstUse = staying.find((s) => [...refs(s.node).read].some((n) => movedNames.has(n)));
  const limit = firstUse ? firstUse.start : Infinity;
  let after = 0;
  for (const s of staying) if (s.req && s.end < limit) after = Math.max(after, s.end);
  if (!after && firstUse) after = firstUse.from - 1;
  return after;
}

// The lines to drop for moved ranges [from, to]. Ranges with only blank lines between them are one
// run; of the blank lines around a run, the wider side stays, so the code on either side keeps the
// spacing it had.
function dropRanges(lines, ranges) {
  const blank = (n) => lines[n - 1] !== undefined && lines[n - 1].trim() === '';
  const runs = [];
  for (const [from, to] of [...ranges].sort((a, b) => a[0] - b[0])) {
    const last = runs[runs.length - 1];
    let between = true;
    if (last) for (let l = last[1] + 1; l < from; l += 1) if (!blank(l)) between = false;
    if (last && between) last[1] = to; else runs.push([from, to]);
  }
  const drop = new Set();
  for (const [from, to] of runs) {
    for (let l = from; l <= to; l += 1) drop.add(l);
    const before = [];
    for (let k = from - 1; k >= 1 && !drop.has(k) && blank(k); k -= 1) before.push(k);
    const after = [];
    let n = to + 1;
    for (; n <= lines.length && blank(n); n += 1) after.push(n);
    const atEnd = n > lines.length;
    for (const l of (atEnd || after.length > before.length ? before : after)) drop.add(l);
  }
  return drop;
}

// Lines as the code map counts them: a final line ending does not start another line.
function countLines(text) {
  if (!text) return 0;
  const n = text.split('\n').length;
  return text.endsWith('\n') ? n - 1 : n;
}

module.exports = {
  readSource, writeText, parse, commonJsOnly, unwrap, declared, uses, refs, usesPrivate, fileBound, isPure, requireOf, importOf, firstLine, statements,
  importsFor, braceList, commentLines, backRequireLine, countLines, dropRanges,
};
