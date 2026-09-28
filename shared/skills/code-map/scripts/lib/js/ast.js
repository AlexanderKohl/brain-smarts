'use strict';
// Parsing and small AST helpers for JavaScript, TypeScript, JSX and TSX.
// Part of the code-map skill (canonical copy: /shared/skills/code-map/). In a project this file is
// an installed copy: change the skill and reinstall, never edit the copy.

let babel = null;
function parser() {
  if (!babel) babel = require('@babel/parser');
  return babel;
}

const TS_EXT = /\.(ts|mts|cts)$/;
const TSX_EXT = /\.tsx$/;

// Parses one source text. `startLine` lets a Vue or HTML script block keep its real line numbers.
function parse(text, file, { startLine = 1, typescript = null } = {}) {
  const isTs = typescript === null ? TS_EXT.test(file) || TSX_EXT.test(file) : typescript;
  const plugins = isTs
    ? (TS_EXT.test(file) && typescript === null ? ['typescript'] : ['typescript', 'jsx'])
    : ['jsx'];
  plugins.push('decorators-legacy', 'importAttributes', 'explicitResourceManagement');
  return parser().parse(text, {
    sourceType: 'unambiguous',
    startLine,
    errorRecovery: true,
    allowReturnOutsideFunction: true,
    allowImportExportEverywhere: true,
    allowAwaitOutsideFunction: true,
    allowUndeclaredExports: true,
    allowSuperOutsideMethod: true,
    attachComment: false,
    plugins,
  });
}

const SKIP_KEYS = new Set(['loc', 'start', 'end', 'extra', 'leadingComments', 'trailingComments',
  'innerComments', 'range', 'errors', 'tokens', 'comments', 'type', 'typeAnnotation',
  'returnType', 'typeParameters', 'superTypeParameters', 'predicate']);

// Child nodes of a node in source order, with the key they sit under.
function children(node) {
  const out = [];
  for (const key of Object.keys(node)) {
    if (SKIP_KEYS.has(key)) continue;
    const value = node[key];
    if (Array.isArray(value)) {
      for (const item of value) if (item && typeof item.type === 'string') out.push([key, item]);
    } else if (value && typeof value.type === 'string') {
      out.push([key, value]);
    }
  }
  return out;
}

// Depth-first walk; `visit(node, parent, key)` returning false skips the node's children.
function walk(node, visit, parent = null, key = null) {
  if (!node || typeof node.type !== 'string') return;
  if (visit(node, parent, key) === false) return;
  for (const [childKey, child] of children(node)) walk(child, visit, node, childKey);
}

const WRAPPERS = new Set(['TSAsExpression', 'TSNonNullExpression', 'TSSatisfiesExpression',
  'TSTypeAssertion', 'ParenthesizedExpression', 'TSInstantiationExpression']);

// The expression under TypeScript casts and parentheses.
function unwrap(node) {
  while (node && WRAPPERS.has(node.type)) node = node.expression;
  return node;
}

function isFunction(node) {
  return !!node && /^(FunctionDeclaration|FunctionExpression|ArrowFunctionExpression|ObjectMethod|ClassMethod|ClassPrivateMethod)$/.test(node.type);
}

function isMember(node) {
  return !!node && (node.type === 'MemberExpression' || node.type === 'OptionalMemberExpression');
}

function isCall(node) {
  return !!node && (node.type === 'CallExpression' || node.type === 'OptionalCallExpression');
}

// The name of a property key when it is written literally: `a`, `'a'`, `[‘a’]`.
function keyName(node, computed) {
  if (!node) return null;
  if (!computed && node.type === 'Identifier') return node.name;
  if (node.type === 'StringLiteral') return node.value;
  if (node.type === 'NumericLiteral') return String(node.value);
  if (computed && node.type === 'TemplateLiteral' && node.expressions.length === 0) return node.quasis[0].value.cooked;
  if (!computed && node.type === 'PrivateName') return '#' + node.id.name;
  return null;
}

// `a.b['c'].d` -> { root: <a>, path: ['b', 'c', 'd'] }; a dynamic key ends the path with null.
function memberChain(node) {
  node = unwrap(node);
  const path = [];
  while (isMember(node)) {
    const name = keyName(node.property, node.computed);
    path.unshift(name);
    node = unwrap(node.object);
  }
  return { root: node, path };
}

// A string known without running the code: literals, templates and `+` of those. `valueOf` resolves
// an identifier (or member) to a constant string, or returns null.
function staticString(node, valueOf) {
  node = unwrap(node);
  if (!node) return null;
  if (node.type === 'StringLiteral') return node.value;
  if (node.type === 'TemplateLiteral') {
    let out = node.quasis[0].value.cooked ?? '';
    for (let i = 0; i < node.expressions.length; i++) {
      const part = staticString(node.expressions[i], valueOf);
      if (part === null) return null;
      out += part + (node.quasis[i + 1].value.cooked ?? '');
    }
    return out;
  }
  if (node.type === 'BinaryExpression' && node.operator === '+') {
    const a = staticString(node.left, valueOf);
    const b = a === null ? null : staticString(node.right, valueOf);
    return a === null || b === null ? null : a + b;
  }
  if ((node.type === 'Identifier' || isMember(node)) && valueOf) return valueOf(node);
  return null;
}

// Pieces of a string whose dynamic parts are marked: ['/api/', {dynamic: node}, '/x'].
function stringParts(node, valueOf) {
  node = unwrap(node);
  if (!node) return null;
  const known = staticString(node, valueOf);
  if (known !== null) return [known];
  if (node.type === 'TemplateLiteral') {
    const out = [node.quasis[0].value.cooked ?? ''];
    node.expressions.forEach((expr, i) => {
      const part = staticString(expr, valueOf);
      out.push(part !== null ? part : { dynamic: expr });
      out.push(node.quasis[i + 1].value.cooked ?? '');
    });
    return out;
  }
  if (node.type === 'BinaryExpression' && node.operator === '+') {
    const a = stringParts(node.left, valueOf) || [{ dynamic: node.left }];
    const b = stringParts(node.right, valueOf) || [{ dynamic: node.right }];
    return [...a, ...b];
  }
  return [{ dynamic: node }];
}

// Source text of a node, shortened for reports.
function snippet(text, node, max = 80) {
  if (!node || node.start == null) return '';
  const s = text.slice(node.start, node.end).replace(/\s+/g, ' ').trim();
  return s.length > max ? s.slice(0, max - 1) + '…' : s;
}

function lineOf(node) {
  return node && node.loc ? node.loc.start.line : null;
}

function endLineOf(node) {
  return node && node.loc ? node.loc.end.line : null;
}

module.exports = {
  parse, walk, children, unwrap, isFunction, isMember, isCall, keyName, memberChain,
  staticString, stringParts, snippet, lineOf, endLineOf,
};
