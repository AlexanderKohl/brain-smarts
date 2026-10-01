'use strict';
// Scope helpers for the JavaScript extractor: which names a statement declares, and where each comes from.
// Moved unchanged from extract.js. extract.js loads these names back, so its callers see the same names.
const A = require('./ast');

// ---------- declarations and scopes ----------

// Where the value a field hangs off comes from, as the code states it: a parameter, or the text of
// the expression that initialised it. Never a guess at its type.
function originOf(b, text) {
  if (!b) return null;
  if (b.kind === 'param') return { kind: 'parameter', name: b.name };
  if (b.import) return { kind: 'import', name: b.name };
  if (b.init) return { kind: 'value', name: b.name, text: A.snippet(text, b.init, 70), line: b.line };
  return { kind: b.kind, name: b.name };
}

function binding(name, kind, node, extra = {}) {
  return { name, kind, line: A.lineOf(node), init: null, import: null, pattern: null, assignments: [], ...extra };
}

function declarePattern(pattern, scope, make, path = []) {
  if (!pattern) return;
  switch (pattern.type) {
    case 'Identifier': scope.set(pattern.name, make(pattern.name, pattern, path)); break;
    case 'ObjectPattern':
      for (const prop of pattern.properties) {
        if (prop.type === 'RestElement') declarePattern(prop.argument, scope, make, [...path, '...']);
        else declarePattern(prop.value, scope, make, [...path, A.keyName(prop.key, prop.computed)]);
      }
      break;
    case 'ArrayPattern':
      pattern.elements.forEach((el, i) => declarePattern(el, scope, make, [...path, `[${i}]`]));
      break;
    case 'AssignmentPattern': declarePattern(pattern.left, scope, make, path); break;
    case 'RestElement': declarePattern(pattern.argument, scope, make, [...path, '...']); break;
    case 'TSParameterProperty': declarePattern(pattern.parameter, scope, make, path); break;
    default: break;
  }
}

// `require('x')`, `require('x').y`, `await import('x')` -> { source, member, deferred }.
function requireInfo(init) {
  let node = A.unwrap(init);
  let member = null;
  if (A.isMember(node)) {
    const name = A.keyName(node.property, node.computed);
    const obj = A.unwrap(node.object);
    if (A.isCall(obj) && isRequireCall(obj)) { member = name; node = obj; }
  }
  if (node && node.type === 'AwaitExpression') node = A.unwrap(node.argument);
  if (!A.isCall(node)) return null;
  const callee = A.unwrap(node.callee);
  const arg = node.arguments[0];
  const source = arg ? A.staticString(arg) : null;
  if (source === null) return null;
  if (callee.type === 'Identifier' && callee.name === 'require') return { source, member, dynamic: false };
  if (callee.type === 'Import') return { source, member, dynamic: true };
  return null;
}

function isRequireCall(node) {
  const callee = A.unwrap(node.callee);
  return callee && callee.type === 'Identifier' && callee.name === 'require';
}

function declareVariable(decl, scope, isModule) {
  for (const d of decl.declarations) {
    const req = requireInfo(d.init);
    declarePattern(d.id, scope, (name, node, path) => {
      const b = binding(name, decl.kind, node, { init: d.init, declarator: d, module: isModule, pattern: path.length ? path : null });
      if (req) {
        const imported = path.length ? path[0] : (req.member || '*');
        b.import = { source: req.source, imported: path.length && req.member ? req.member : imported, deferred: req.dynamic, kind: req.dynamic ? 'dynamic-import' : 'require' };
        if (path.length && req.member) b.import.member = path[0];
      }
      return b;
    });
  }
}

function declareStatements(stmts, scope, isModule, hoistVars) {
  for (const stmt of stmts) declareStatement(stmt, scope, isModule);
  if (hoistVars) for (const stmt of stmts) collectNestedVars(stmt, scope, isModule, true);
}

function declareStatement(stmt, scope, isModule) {
  if (!stmt) return;
  switch (stmt.type) {
    case 'VariableDeclaration': declareVariable(stmt, scope, isModule); break;
    case 'FunctionDeclaration':
    case 'TSDeclareFunction':
      if (stmt.id) scope.set(stmt.id.name, binding(stmt.id.name, 'function', stmt, { init: stmt, module: isModule }));
      break;
    case 'ClassDeclaration':
      if (stmt.id) scope.set(stmt.id.name, binding(stmt.id.name, 'class', stmt, { init: stmt, module: isModule }));
      break;
    case 'TSEnumDeclaration':
      scope.set(stmt.id.name, binding(stmt.id.name, 'const', stmt, { init: stmt, module: isModule }));
      break;
    case 'ImportDeclaration':
      for (const spec of stmt.specifiers) {
        const imported = spec.type === 'ImportDefaultSpecifier' ? 'default'
          : spec.type === 'ImportNamespaceSpecifier' ? '*' : A.keyName(spec.imported, false) || spec.imported.value;
        scope.set(spec.local.name, binding(spec.local.name, 'import', spec, {
          module: isModule,
          import: { source: stmt.source.value, imported, deferred: false, kind: 'import', typeOnly: stmt.importKind === 'type' || spec.importKind === 'type' },
        }));
      }
      break;
    case 'TSImportEqualsDeclaration': {
      const ref = stmt.moduleReference;
      if (ref && ref.type === 'TSExternalModuleReference') {
        scope.set(stmt.id.name, binding(stmt.id.name, 'import', stmt, { module: isModule, import: { source: ref.expression.value, imported: '*', deferred: false, kind: 'require' } }));
      }
      break;
    }
    case 'ExportNamedDeclaration':
    case 'ExportDefaultDeclaration':
      if (stmt.declaration && stmt.declaration.type !== 'Identifier' && /Declaration$/.test(stmt.declaration.type)) declareStatement(stmt.declaration, scope, isModule);
      break;
    default: break;
  }
}

// `var` declared inside blocks belongs to the enclosing function (or module).
function collectNestedVars(node, scope, isModule, top) {
  if (!node || A.isFunction(node) || /^Class/.test(node.type) || /Expression$/.test(node.type)) return;
  if (node.type === 'VariableDeclaration') {
    if (!top && node.kind === 'var') declareVariable(node, scope, isModule);
    return;
  }
  for (const [, child] of A.children(node)) collectNestedVars(child, scope, isModule, false);
}

function lookup(scopes, name) {
  for (let i = scopes.length - 1; i >= 0; i--) {
    const b = scopes[i].get(name);
    if (b) return b;
  }
  return null;
}

module.exports = {
  originOf, binding, declarePattern, requireInfo, isRequireCall, declareVariable,
  declareStatements, lookup,
};
