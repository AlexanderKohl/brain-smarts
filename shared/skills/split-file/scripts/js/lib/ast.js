'use strict';
// Shared parsing for the JavaScript split tools: the top-level statements of a CommonJS file, with
// their line ranges, the names each declares, reads and assigns, and the import each one is.
// Names read are over-counted on purpose (shadowing is ignored), so a move never loses a name it
// needs; the cost is an occasional refusal that a person resolves by moving more.
// Part of the split-file skill (canonical copy: /shared/skills/split-file/).

const fs = require('fs');
const parser = require('@babel/parser');

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

function parse(text, { recover = false } = {}) {
  return parser.parse(text, {
    sourceType: 'script',
    allowReturnOutsideFunction: true,
    errorRecovery: recover,
    plugins: ['optionalChaining', 'nullishCoalescingOperator', 'classProperties'],
  });
}

// Names a top-level statement declares.
function declared(stmt) {
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
// and `this` at the top level (module.exports in CommonJS). __dirname is the same in a module in
// the same folder, so it is allowed.
function fileBound(node) {
  const found = new Set();
  const visit = (n, parent, key, inFunction) => {
    if (n.type === 'Identifier' && ['module', 'exports', '__filename'].includes(n.name)
      && !(parent && /MemberExpression$/.test(parent.type) && key === 'property' && !parent.computed)
      && !(parent && ['ObjectProperty', 'ObjectMethod'].includes(parent.type) && key === 'key' && !parent.computed)) found.add(n.name);
    if (n.type === 'ThisExpression' && !inFunction) found.add('this');
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
  if (['ArrowFunctionExpression', 'FunctionExpression', 'StringLiteral', 'NumericLiteral', 'BooleanLiteral', 'NullLiteral', 'RegExpLiteral'].includes(n.type)) return true;
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

const KIND = { FunctionDeclaration: 'function', ClassDeclaration: 'class' };

// Every top-level statement: its node, first line with its leading comments (`from`), first and
// last line, the names it declares, its kind, and its import form.
function statements(ast, text) {
  const stmts = ast.program.body.map((s) => ({
    node: s,
    from: s.leadingComments && s.leadingComments.length ? s.leadingComments[0].loc.start.line : s.loc.start.line,
    start: s.loc.start.line,
    end: s.loc.end.line,
    declares: declared(s),
    kind: s.type === 'VariableDeclaration' ? s.kind : KIND[s.type] || null,
    req: requireOf(s, text),
  }));
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
  const lines = [...bySource.entries()].sort((a, b) => a[0] - b[0]).map(([, info]) => (info.whole
    ? `${info.req.kind} ${info.req.whole} = require(${info.req.source});`
    : `${info.req.kind} { ${info.req.names.filter((x) => info.names.has(x)).join(', ')} } = require(${info.req.source});`));
  return { lines, behind };
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
// comes before the first remaining statement using a moved name, so every use sees it loaded.
function backRequireLine(staying, movedNames) {
  const firstUse = staying.find((s) => [...uses(s.node).read].some((n) => movedNames.has(n)));
  const limit = firstUse ? firstUse.start : Infinity;
  let after = 0;
  for (const s of staying) if (s.req && s.end < limit) after = Math.max(after, s.end);
  if (!after && firstUse) after = firstUse.from - 1;
  return after;
}

module.exports = {
  readSource, writeText, parse, declared, uses, usesPrivate, fileBound, isPure, requireOf, statements, importsFor,
  braceList, backRequireLine,
};
