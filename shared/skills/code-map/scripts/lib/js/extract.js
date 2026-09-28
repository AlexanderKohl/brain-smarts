'use strict';
// Per-file facts for JavaScript, TypeScript, JSX, TSX and the script blocks of Vue and HTML files.
// Everything here is read from the syntax alone; nothing is guessed. Part of the code-map skill
// (canonical copy: /shared/skills/code-map/); in a project this is an installed copy.

const A = require('./ast');

const MUTATORS = new Set(['push', 'pop', 'shift', 'unshift', 'splice', 'sort', 'reverse', 'fill',
  'copyWithin', 'set', 'delete', 'clear', 'add']);

function newFacts(file, language, lines) {
  return {
    file, language, lines, errors: [], functions: [], classes: [], variables: [], imports: [],
    exports: { named: new Map(), default: null, cjsDefault: null, starFrom: [] },
    callSites: [], newSites: [], tagged: [], varRefs: [], env: [], assignments: [], jsx: [], memberReads: [],
    moduleScope: new Map(), programs: [], functionsByName: new Map(), callCount: 0,
  };
}

// segments: [{ text, startLine, typescript }] – one for a plain file, one per script block otherwise.
// hints.roots: names whose member reads are recorded (settings objects); hints.loaders: functions
// whose result is such an object.
function extractJs(file, language, lines, segments, hints = {}) {
  const facts = newFacts(file, language, lines);
  facts.hints = { roots: new Set(hints.roots || []), loaders: new Set(hints.loaders || []) };
  const parsed = [];
  for (const seg of segments) {
    try {
      const ast = A.parse(seg.text, file, { startLine: seg.startLine || 1, typescript: seg.typescript ?? null });
      for (const err of ast.errors || []) facts.errors.push(`${err.reasonCode || 'SyntaxError'} at line ${err.loc ? err.loc.line : '?'}`);
      parsed.push({ ast, text: seg.text });
    } catch (err) {
      facts.errors.push(String(err.message || err).split('\n')[0]);
    }
  }
  const moduleScope = facts.moduleScope;
  for (const { ast } of parsed) declareStatements(ast.program.body, moduleScope, true, true);
  for (const { ast, text } of parsed) {
    facts.programs.push(ast.program);
    new Walker(facts, text).program(ast.program, moduleScope);
  }
  for (const binding of moduleScope.values()) {
    if (!['var', 'let', 'const'].includes(binding.kind) || binding.import) continue;
    const init = A.unwrap(binding.init);
    if (init && (A.isFunction(init) || init.type === 'ClassExpression')) continue;
    facts.variables.push({
      name: binding.name, kind: binding.kind, line: binding.line,
      container: !!init && (/^(ObjectExpression|ArrayExpression)$/.test(init.type) ||
        (init.type === 'NewExpression' && init.callee.type === 'Identifier' && /^(Map|Set|WeakMap|WeakSet|Array|Object)$/.test(init.callee.name))),
    });
  }
  facts.variables.sort((a, b) => a.line - b.line);
  return facts;
}

// ---------- declarations and scopes ----------

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

// ---------- the walk ----------

class Walker {
  constructor(facts, text) {
    this.facts = facts;
    this.text = text;
    this.stack = [];
  }

  program(program, moduleScope) {
    const ctx = { scopes: [moduleScope], owner: null, fnDepth: 0, className: null, objName: null, jsxRoute: null };
    for (const stmt of program.body) this.visit(stmt, program, 'body', ctx);
  }

  visit(node, parent, key, ctx) {
    if (!node || typeof node.type !== 'string') return;
    this.stack.push(node);
    try { this.dispatch(node, parent, key, ctx); } finally { this.stack.pop(); }
  }

  visitChildren(node, ctx, skip = null) {
    for (const [key, child] of A.children(node)) {
      if (skip && skip.has(key)) continue;
      this.visit(child, node, key, ctx);
    }
  }

  dispatch(node, parent, key, ctx) {
    if (A.isFunction(node)) return this.fn(node, parent, key, ctx);
    switch (node.type) {
      case 'BlockStatement':
      case 'StaticBlock': {
        const scope = new Map();
        declareStatements(node.body, scope, false, false);
        return this.visitChildren(node, { ...ctx, scopes: [...ctx.scopes, scope] });
      }
      case 'ForStatement':
      case 'ForInStatement':
      case 'ForOfStatement': {
        const scope = new Map();
        const decl = node.init || node.left;
        if (decl && decl.type === 'VariableDeclaration' && decl.kind !== 'var') declareVariable(decl, scope, false);
        if (node.type === 'ForOfStatement') for (const b of scope.values()) b.forOf = node.right;
        return this.visitChildren(node, { ...ctx, scopes: [...ctx.scopes, scope] });
      }
      case 'CatchClause': {
        const scope = new Map();
        declarePattern(node.param, scope, (name, n) => binding(name, 'catch', n));
        return this.visitChildren(node, { ...ctx, scopes: [...ctx.scopes, scope] });
      }
      case 'ClassDeclaration':
      case 'ClassExpression': return this.klass(node, parent, key, ctx);
      case 'VariableDeclarator': return this.declarator(node, ctx);
      case 'ImportDeclaration': return this.importDecl(node, ctx);
      case 'ExportNamedDeclaration': this.exportNamed(node, ctx); return this.visitChildren(node, ctx, new Set(['specifiers', 'source']));
      case 'ExportDefaultDeclaration': this.facts.exports.default = { node: node.declaration, line: A.lineOf(node) }; return this.visitChildren(node, { ...ctx, objName: 'default' });
      case 'ExportAllDeclaration':
        this.facts.exports.starFrom.push({ source: node.source.value, as: node.exported ? A.keyName(node.exported, false) || node.exported.value : null });
        this.addImport(node.source.value, [], 'startup', 're-export', node, ctx, node.exportKind === 'type');
        return;
      case 'TSExportAssignment': this.facts.exports.cjsDefault = { node: node.expression, line: A.lineOf(node) }; return this.visitChildren(node, ctx);
      case 'TSImportEqualsDeclaration': {
        const ref = node.moduleReference;
        if (ref && ref.type === 'TSExternalModuleReference') this.addImport(ref.expression.value, [{ imported: '*', local: node.id.name }], ctx.fnDepth ? 'deferred' : 'startup', 'require', node, ctx, node.importKind === 'type');
        return;
      }
      case 'CallExpression':
      case 'OptionalCallExpression': this.call(node, ctx); return this.visitChildren(node, ctx);
      case 'NewExpression': this.record(this.facts.newSites, node, node.callee, ctx); return this.visitChildren(node, ctx);
      case 'TaggedTemplateExpression': {
        const chain = A.memberChain(node.tag);
        this.facts.tagged.push({ node, quasi: node.quasi, root: chain.root, path: chain.path, rootName: chain.root && chain.root.type === 'Identifier' ? chain.root.name : null, line: A.lineOf(node), owner: ctx.owner && ctx.owner.id, scopes: ctx.scopes, text: this.text });
        return this.visitChildren(node, ctx);
      }
      case 'AssignmentExpression':
        if (this.assignment(node, parent, ctx) === 'handled') return;
        return this.visitChildren(node, ctx);
      case 'MemberExpression':
      case 'OptionalMemberExpression': this.member(node, parent, key, ctx); return this.visitChildren(node, ctx);
      case 'Identifier': return this.identifier(node, parent, key, ctx);
      case 'ObjectExpression': return this.visitChildren(node, ctx);
      case 'ObjectProperty': {
        if (node.computed) this.visit(node.key, node, 'key', ctx);
        const name = A.keyName(node.key, node.computed);
        return this.visit(node.value, node, 'value', { ...ctx, propName: name });
      }
      case 'JSXElement': return this.jsxElement(node, ctx);
      case 'LabeledStatement': return this.visit(node.body, node, 'body', ctx);
      case 'BreakStatement':
      case 'ContinueStatement': return;
      default: return this.visitChildren(node, ctx);
    }
  }

  // ----- functions and the functions that own code -----

  ownerName(node, parent, key, ctx) {
    const line = A.lineOf(node);
    if (node.type === 'FunctionDeclaration' && node.id) return { name: node.id.name, qualified: node.id.name, kind: 'function' };
    if (/^(ClassMethod|ClassPrivateMethod)$/.test(node.type)) {
      const k = A.keyName(node.key, node.computed) || `<computed>@${line}`;
      return { name: k, qualified: `${ctx.className || '<class>'}.${k}`, kind: 'method', className: ctx.className, static: !!node.static, methodKind: node.kind };
    }
    if (node.type === 'ObjectMethod' || (parent && parent.type === 'ObjectProperty' && key === 'value')) {
      const k = ctx.propName || A.keyName(node.key, node.computed) || `<computed>@${line}`;
      return { name: k, qualified: ctx.objName ? `${ctx.objName}.${k}` : k, kind: 'method' };
    }
    if (parent && parent.type === 'ClassProperty') {
      const k = A.keyName(parent.key, parent.computed) || `<computed>@${line}`;
      return { name: k, qualified: `${ctx.className || '<class>'}.${k}`, kind: 'method', className: ctx.className, static: !!parent.static };
    }
    if (parent && parent.type === 'VariableDeclarator' && parent.id.type === 'Identifier') return { name: parent.id.name, qualified: parent.id.name, kind: 'function' };
    if (parent && parent.type === 'AssignmentExpression') {
      const chain = A.memberChain(parent.left);
      const rootName = chain.root && chain.root.type === 'Identifier' ? chain.root.name : null;
      const qualified = [rootName, ...chain.path].filter(Boolean).join('.');
      return { name: chain.path.length ? chain.path[chain.path.length - 1] : rootName, qualified: qualified || `<assigned>@${line}`, kind: 'function' };
    }
    if (parent && parent.type === 'ExportDefaultDeclaration') return { name: 'default', qualified: 'default', kind: 'function' };
    if (parent && A.isCall(parent)) {
      const callee = A.snippet(this.text, parent.callee, 60);
      const first = parent.arguments[0];
      const lit = first && first !== node ? A.staticString(first) : null;
      const label = lit !== null ? `${callee}(${JSON.stringify(lit)})` : `${callee}()`;
      return { name: label, qualified: `${label}@${line}`, kind: 'callback' };
    }
    return { name: `<anonymous>@${line}`, qualified: `<anonymous>@${line}`, kind: 'function' };
  }

  fn(node, parent, key, ctx) {
    let owner = ctx.owner;
    if (!owner) {
      const info = this.ownerName(node, parent, key, ctx);
      let id = `${this.facts.file}#${info.qualified}`;
      if (this.facts.functions.some((f) => f.id === id)) id = `${id}@${A.lineOf(node)}`;
      owner = {
        id, ...info, line: A.lineOf(node), endLine: A.endLineOf(node),
        length: A.endLineOf(node) - A.lineOf(node) + 1, params: node.params.length,
        async: !!node.async, node,
      };
      this.facts.functions.push(owner);
      if (info.kind === 'function' && !this.facts.functionsByName.has(info.name) && ctx.fnDepth === 0) this.facts.functionsByName.set(info.name, owner);
    }
    const scope = new Map();
    const selfName = node.type === 'FunctionExpression' && node.id ? node.id.name : null;
    if (selfName) scope.set(selfName, binding(selfName, 'function', node, { init: node }));
    node.params.forEach((p, index) => declarePattern(p, scope, (name, n, path) => binding(name, 'param', n, { param: { fn: node, index }, pattern: path.length ? path : null })));
    const inner = { ...ctx, owner, fnDepth: ctx.fnDepth + 1, scopes: [...ctx.scopes, scope], objName: null, propName: null };
    if (node.body && node.body.type === 'BlockStatement') {
      declareStatements(node.body.body, scope, false, true);
      for (const stmt of node.body.body) this.visit(stmt, node.body, 'body', inner);
    } else if (node.body) {
      this.visit(node.body, node, 'body', inner);
    }
  }

  klass(node, parent, key, ctx) {
    const name = node.id ? node.id.name
      : parent && parent.type === 'VariableDeclarator' && parent.id.type === 'Identifier' ? parent.id.name
        : parent && parent.type === 'ExportDefaultDeclaration' ? 'default' : null;
    if (node.superClass) this.visit(node.superClass, node, 'superClass', ctx);
    const topLevel = ctx.fnDepth === 0;
    let record = null;
    if (topLevel && name) {
      record = {
        name, line: A.lineOf(node), endLine: A.endLineOf(node), node,
        superClass: node.superClass ? A.snippet(this.text, node.superClass, 60) : null, methods: [],
      };
      this.facts.classes.push(record);
    }
    const scope = new Map();
    if (node.id) scope.set(node.id.name, binding(node.id.name, 'class', node, { init: node }));
    const inner = { ...ctx, className: name || ctx.className, scopes: [...ctx.scopes, scope], objName: null };
    for (const member of node.body.body) {
      if (record) {
        const k = A.keyName(member.key, member.computed);
        const isFn = /^(ClassMethod|TSDeclareMethod)$/.test(member.type) ||
          (member.type === 'ClassProperty' && member.value && A.isFunction(A.unwrap(member.value)));
        if (k && isFn && member.kind !== 'constructor' && member.accessibility !== 'private') {
          record.methods.push({ name: k, static: !!member.static, kind: member.kind || 'method', line: A.lineOf(member) });
        }
      }
      if (member.type === 'ClassProperty' || member.type === 'ClassPrivateProperty') {
        if (member.computed) this.visit(member.key, member, 'key', inner);
        if (member.value) this.visit(member.value, member, 'value', inner);
      } else {
        this.visit(member, node.body, 'body', inner);
      }
    }
  }

  // ----- imports and exports -----

  addImport(source, names, load, kind, node, ctx, typeOnly = false) {
    this.facts.imports.push({ source, names, load, kind, typeOnly: !!typeOnly, line: A.lineOf(node), owner: ctx.owner && ctx.owner.id });
  }

  importDecl(node, ctx) {
    const names = node.specifiers.map((spec) => ({
      imported: spec.type === 'ImportDefaultSpecifier' ? 'default' : spec.type === 'ImportNamespaceSpecifier' ? '*' : (A.keyName(spec.imported, false) || spec.imported.value),
      local: spec.local.name,
    }));
    this.addImport(node.source.value, names, 'startup', 'import', node, ctx, node.importKind === 'type');
  }

  exportNamed(node) {
    const named = this.facts.exports.named;
    if (node.exportKind === 'type') return;
    const decl = node.declaration;
    if (decl) {
      if ((decl.type === 'FunctionDeclaration' || decl.type === 'ClassDeclaration' || decl.type === 'TSEnumDeclaration') && decl.id) {
        named.set(decl.id.name, { local: decl.id.name, line: A.lineOf(decl) });
      } else if (decl.type === 'VariableDeclaration') {
        for (const d of decl.declarations) declarePattern(d.id, new Map(), (name) => { named.set(name, { local: name, line: A.lineOf(d) }); return {}; });
      }
    }
    for (const spec of node.specifiers || []) {
      if (spec.exportKind === 'type') continue;
      const exported = A.keyName(spec.exported, false) || spec.exported.value;
      if (node.source) {
        const imported = spec.type === 'ExportNamespaceSpecifier' ? '*' : (spec.local ? (A.keyName(spec.local, false) || spec.local.value) : 'default');
        named.set(exported, { fromSource: node.source.value, imported, line: A.lineOf(spec) });
      } else {
        named.set(exported, { local: spec.local.name, line: A.lineOf(spec) });
      }
    }
    if (node.source) this.addImport(node.source.value, [], 'startup', 're-export', node, { owner: null }, node.exportKind === 'type');
  }

  // ----- declarations, assignments and references -----

  declarator(node, ctx) {
    const init = A.unwrap(node.init);
    const req = node.init ? requireInfo(node.init) : null;
    if (req) {
      const names = [];
      if (node.id.type === 'Identifier') names.push({ imported: req.member || '*', local: node.id.name });
      else if (node.id.type === 'ObjectPattern') {
        for (const p of node.id.properties) {
          if (p.type === 'ObjectProperty' && p.value.type === 'Identifier') names.push({ imported: A.keyName(p.key, p.computed), local: p.value.name });
        }
      }
      this.addImport(req.source, names, req.dynamic || ctx.fnDepth ? 'deferred' : 'startup', req.dynamic ? 'dynamic-import' : 'require', node, ctx);
      if (!req.dynamic) {
        // The require call itself is recorded; do not record it again as a plain call.
        const call = init && init.type === 'AwaitExpression' ? A.unwrap(init.argument) : init;
        const inner = A.isMember(call) ? A.unwrap(call.object) : call;
        if (inner) inner.__requireRecorded = true;
      }
    }
    // Env destructuring: const { A, B } = process.env
    if (node.id.type === 'ObjectPattern' && init && isEnvObject(init)) {
      for (const p of node.id.properties) {
        if (p.type !== 'ObjectProperty') continue;
        this.facts.env.push({ name: A.keyName(p.key, p.computed), line: A.lineOf(p), owner: ctx.owner && ctx.owner.id, via: 'destructure' });
      }
    }
    // Destructured from another binding: remember which one, resolved where it is written.
    if (init && init.type === 'Identifier' && node.id.type !== 'Identifier') {
      const source = lookup(ctx.scopes, init.name);
      declarePattern(node.id, new Map(), (name) => {
        const b = lookup(ctx.scopes, name);
        if (b && b.declarator === node) b.initBinding = source;
        return {};
      });
    }
    const objName = node.id.type === 'Identifier' ? node.id.name : null;
    if (node.init) this.visit(node.init, node, 'init', { ...ctx, objName: ctx.fnDepth === 0 ? objName : ctx.objName });
  }

  assignment(node, parent, ctx) {
    const left = A.unwrap(node.left);
    if (left.type === 'Identifier') {
      const b = lookup(ctx.scopes, left.name);
      if (b) b.assignments.push(node.right);
    }
    if (A.isMember(left)) {
      const chain = A.memberChain(left);
      const rootName = chain.root && chain.root.type === 'Identifier' ? chain.root.name : null;
      const isModuleExports = rootName === 'module' && chain.path[0] === 'exports' && !lookup(ctx.scopes, 'module');
      const isExports = rootName === 'exports' && !lookup(ctx.scopes, 'exports');
      if (isModuleExports && chain.path.length === 1) {
        this.facts.exports.cjsDefault = { node: node.right, line: A.lineOf(node) };
      } else if ((isModuleExports && chain.path.length === 2) || (isExports && chain.path.length === 1)) {
        const name = chain.path[chain.path.length - 1];
        if (name) this.facts.exports.named.set(name, { value: node.right, local: A.unwrap(node.right).type === 'Identifier' ? A.unwrap(node.right).name : null, line: A.lineOf(node), cjs: true });
      }
      if (ctx.fnDepth === 0) this.facts.assignments.push({ node, rootName, path: chain.path, value: node.right, line: A.lineOf(node), scopes: ctx.scopes, text: this.text });
      if (ctx.fnDepth === 0 && (isModuleExports || isExports)) {
        const nameCtx = { ...ctx, objName: isModuleExports && chain.path.length === 1 ? 'module.exports' : [rootName, ...chain.path].join('.') };
        this.visit(node.left, node, 'left', ctx);
        this.visit(node.right, node, 'right', nameCtx);
        return 'handled';
      }
    }
    return null;
  }

  identifier(node, parent, key, ctx) {
    if (!isReference(node, parent, key)) return;
    const b = lookup(ctx.scopes, node.name);
    if (!b || !ctx.owner || !b.module) return;
    if (!['var', 'let', 'const'].includes(b.kind) || b.import) return;
    const init = A.unwrap(b.init);
    if (init && (A.isFunction(init) || init.type === 'ClassExpression')) return;
    this.facts.varRefs.push({ owner: ctx.owner.id, name: node.name, write: this.isWrite(node, parent, key), line: A.lineOf(node) });
  }

  isWrite(node, parent, key) {
    if (parent.type === 'AssignmentExpression' && key === 'left') return true;
    if (parent.type === 'UpdateExpression') return true;
    // x.y = v, x.y++, delete x.y, x.push(v), Object.assign(x, ...)
    const s = this.stack;
    let i = s.length - 1;
    let cur = node;
    while (i > 0 && A.isMember(s[i - 1]) && s[i - 1].object === cur) { cur = s[i - 1]; i--; }
    const outer = s[i - 1];
    if (cur !== node && outer) {
      if (outer.type === 'AssignmentExpression' && outer.left === cur) return true;
      if (outer.type === 'UpdateExpression' || (outer.type === 'UnaryExpression' && outer.operator === 'delete')) return true;
      if (A.isCall(outer) && outer.callee === cur && A.isMember(cur) && MUTATORS.has(A.keyName(cur.property, cur.computed))) return true;
    }
    if (A.isCall(parent) && key === 'arguments' && parent.arguments[0] === node) {
      const c = A.memberChain(parent.callee);
      if (c.root && c.root.type === 'Identifier' && c.root.name === 'Object' && c.path[0] === 'assign') return true;
    }
    return false;
  }

  member(node, parent, key, ctx) {
    const obj = A.unwrap(node.object);
    if (isEnvObject(obj)) {
      const name = A.keyName(node.property, node.computed);
      this.facts.env.push({ name, line: A.lineOf(node), owner: ctx.owner && ctx.owner.id, dynamic: name === null, text: name === null ? A.snippet(this.text, node) : undefined });
    }
    // Outermost member chain rooted at a possible settings object.
    const hints = this.facts.hints;
    if ((!hints.roots.size && !hints.loaders.size) || (A.isMember(parent) && parent.object === node)) return;
    const chain = A.memberChain(node);
    if (!chain.root || chain.root.type !== 'Identifier') return;
    const b = lookup(ctx.scopes, chain.root.name);
    const isLoaderCall = (n) => {
      n = A.unwrap(n);
      if (n && n.type === 'AwaitExpression') n = A.unwrap(n.argument);
      return !!n && A.isCall(n) && A.unwrap(n.callee).type === 'Identifier' && hints.loaders.has(A.unwrap(n.callee).name);
    };
    const qualifies = (x, depth = 0) => !!x && depth < 4 && (hints.roots.has(x.name) || isLoaderCall(x.init) || x.assignments.some(isLoaderCall) || qualifies(x.initBinding, depth + 1));
    if (!hints.roots.has(chain.root.name) && !qualifies(b)) return;
    this.facts.memberReads.push({
      rootName: chain.root.name, binding: b, path: chain.path, line: A.lineOf(node), owner: ctx.owner && ctx.owner.id,
      isCallee: A.isCall(parent) && parent.callee === node,
    });
  }

  call(node, ctx) {
    this.facts.callCount++;
    const callee = A.unwrap(node.callee);
    if (callee.type === 'Import') {
      const source = node.arguments[0] ? A.staticString(node.arguments[0]) : null;
      if (source !== null) this.addImport(source, [], 'deferred', 'dynamic-import', node, ctx);
      else this.facts.imports.push({ source: null, names: [], load: 'deferred', kind: 'dynamic-import', unresolved: A.snippet(this.text, node), line: A.lineOf(node), owner: ctx.owner && ctx.owner.id });
      return;
    }
    if (callee.type === 'Identifier' && callee.name === 'require' && !lookup(ctx.scopes, 'require')) {
      if (node.__requireRecorded) return;
      const source = node.arguments[0] ? A.staticString(node.arguments[0]) : null;
      if (source !== null) this.addImport(source, [], ctx.fnDepth ? 'deferred' : 'startup', 'require', node, ctx);
      else this.facts.imports.push({ source: null, names: [], load: ctx.fnDepth ? 'deferred' : 'startup', kind: 'require', unresolved: A.snippet(this.text, node), line: A.lineOf(node), owner: ctx.owner && ctx.owner.id });
      return;
    }
    this.record(this.facts.callSites, node, callee, ctx);
  }

  record(list, node, callee, ctx) {
    const chain = A.memberChain(callee);
    const root = chain.root;
    const rootType = !root ? 'other' : root.type === 'Identifier' ? 'id' : root.type === 'ThisExpression' ? 'this'
      : A.isCall(root) || root.type === 'NewExpression' ? 'call' : root.type === 'MetaProperty' ? 'meta' : 'other';
    list.push({
      node, callee, root, rootType, rootName: rootType === 'id' ? root.name : null,
      binding: rootType === 'id' ? lookup(ctx.scopes, root.name) : null,
      path: chain.path, args: node.arguments || [], line: A.lineOf(node),
      owner: ctx.owner && ctx.owner.id, fnDepth: ctx.fnDepth, className: ctx.className,
      scopes: ctx.scopes, text: this.text,
    });
  }

  jsxElement(node, ctx) {
    const nameNode = node.openingElement.name;
    const name = jsxName(nameNode);
    if (name && /(^|\.)Route$/.test(name)) {
      const attrs = {};
      for (const attr of node.openingElement.attributes) {
        if (attr.type !== 'JSXAttribute') continue;
        const k = attr.name.type === 'JSXIdentifier' ? attr.name.name : null;
        if (!k) continue;
        attrs[k] = attr.value === null ? { type: 'BooleanLiteral', value: true }
          : attr.value.type === 'JSXExpressionContainer' ? attr.value.expression : attr.value;
      }
      const record = { name, attrs, line: A.lineOf(node), parent: ctx.jsxRoute, node, owner: ctx.owner && ctx.owner.id, scopes: ctx.scopes };
      this.facts.jsx.push(record);
      return this.visitChildren(node, { ...ctx, jsxRoute: record });
    }
    return this.visitChildren(node, ctx);
  }
}

function jsxName(node) {
  if (!node) return null;
  if (node.type === 'JSXIdentifier') return node.name;
  if (node.type === 'JSXMemberExpression') return `${jsxName(node.object)}.${node.property.name}`;
  return null;
}

function isEnvObject(node) {
  node = A.unwrap(node);
  if (!A.isMember(node)) return false;
  const obj = A.unwrap(node.object);
  const prop = A.keyName(node.property, node.computed);
  if (prop !== 'env') return false;
  if (obj.type === 'Identifier' && obj.name === 'process') return true;
  return obj.type === 'MetaProperty' && obj.meta.name === 'import' && obj.property.name === 'meta';
}

function isReference(node, parent, key) {
  if (!parent) return true;
  switch (parent.type) {
    case 'MemberExpression':
    case 'OptionalMemberExpression': return key !== 'property' || parent.computed;
    case 'ObjectProperty': return key === 'value' || parent.computed;
    case 'ObjectMethod':
    case 'ClassMethod':
    case 'ClassPrivateMethod':
    case 'ClassProperty': return key !== 'key' || parent.computed;
    case 'VariableDeclarator': return key === 'init';
    case 'FunctionDeclaration':
    case 'FunctionExpression':
    case 'ArrowFunctionExpression': return key === 'body';
    case 'ImportSpecifier':
    case 'ImportDefaultSpecifier':
    case 'ImportNamespaceSpecifier':
    case 'ExportSpecifier':
    case 'LabeledStatement':
    case 'BreakStatement':
    case 'ContinueStatement':
    case 'MetaProperty':
    case 'ClassDeclaration':
    case 'ClassExpression': return key === 'superClass';
    case 'CatchClause': return key !== 'param';
    default: return true;
  }
}

module.exports = { extractJs, lookup, requireInfo };
