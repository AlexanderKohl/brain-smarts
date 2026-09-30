'use strict';
// Per-file facts for JavaScript, TypeScript, JSX, TSX and the script blocks of Vue and HTML files.
// Everything here is read from the syntax alone; nothing is guessed. Part of the code-map skill
// (canonical copy: /shared/skills/code-map/); in a project this is an installed copy.

const A = require('./ast');
// Code moved unchanged into the modules required below is loaded back here, so this file's
// exports stay the same.
const {
  originOf, binding, declarePattern, requireInfo, isRequireCall, declareVariable,
  declareStatements, lookup,
} = require('./scope');
const { jsxName, wholeImport, isEnvObject, isReference } = require('./nodes');

// Roots whose members are language or runtime APIs, not data: never recorded as fields.
const GLOBALS = new Set(['Math', 'JSON', 'Object', 'Array', 'Number', 'String', 'Boolean', 'Promise', 'Date',
  'console', 'window', 'document', 'globalThis', 'self', 'navigator', 'location', 'history', 'localStorage',
  'sessionStorage', 'Symbol', 'Reflect', 'Intl', 'Buffer', 'module', 'exports', 'require', 'process', 'Error',
  'RegExp', 'Map', 'Set', 'URL', 'crypto', 'performance']);
const LITERAL = new Set(['StringLiteral', 'NumericLiteral', 'BooleanLiteral']);

const MUTATORS = new Set(['push', 'pop', 'shift', 'unshift', 'splice', 'sort', 'reverse', 'fill',
  'copyWithin', 'set', 'delete', 'clear', 'add']);

function newFacts(file, language, lines) {
  return {
    file, language, lines, errors: [], functions: [], classes: [], variables: [], imports: [],
    exports: { named: new Map(), default: null, cjsDefault: null, starFrom: [] },
    callSites: [], newSites: [], tagged: [], varRefs: [], env: [], assignments: [], jsx: [], memberReads: [], fields: [],
    moduleScope: new Map(), programs: [], functionsByName: new Map(), callCount: 0,
    // For the unused report: what this file uses of the modules it imports ({ source, name }, name
    // '*' when the whole module is passed on), scripts it starts by file name, and parameters a
    // function uses as an environment variable name.
    importUses: [], scriptRefs: [], envParamReads: [],
  };
}

// Functions that start another script by its file name.
const SCRIPT_RUNNERS = new Set(['execFile', 'execFileSync', 'spawn', 'spawnSync', 'fork', 'exec', 'execSync', 'importScripts']);
const SCRIPT_FILE = /\.(c|m)?[jt]sx?$/;

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
        this.facts.importUses.push({ source: node.source.value, name: '*', line: A.lineOf(node) });
        return;
      case 'TSExportAssignment': this.facts.exports.cjsDefault = { node: node.expression, line: A.lineOf(node) }; return this.visitChildren(node, ctx);
      case 'TSImportEqualsDeclaration': {
        const ref = node.moduleReference;
        if (ref && ref.type === 'TSExternalModuleReference') this.addImport(ref.expression.value, [{ imported: '*', local: node.id.name }], ctx.fnDepth ? 'deferred' : 'startup', 'require', node, ctx, node.importKind === 'type');
        return;
      }
      case 'CallExpression':
      case 'OptionalCallExpression': this.call(node, ctx); return this.visitChildren(node, ctx);
      case 'NewExpression':
        if (A.unwrap(node.callee).type === 'Identifier' && A.unwrap(node.callee).name === 'Worker') this.scriptRefs(node.arguments.slice(0, 1), ctx, A.lineOf(node));
        this.record(this.facts.newSites, node, node.callee, ctx);
        return this.visitChildren(node, ctx);
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
        const objPath = name ? [...(ctx.objPath || []), name] : null;
        const value = A.unwrap(node.value);
        // An object literal sets its keys: { contactDetails: { entity_type: 'x' } } sets contactDetails.entity_type.
        if (objPath && parent && parent.type === 'ObjectExpression') {
          this.facts.fields.push({ path: objPath, root: null, line: A.lineOf(node), owner: ctx.owner && ctx.owner.id, write: true, literal: true,
            compared: value && LITERAL.has(value.type) ? [value.value] : null, fallback: null, origin: null, initNode: null });
        }
        return this.visit(node.value, node, 'value', { ...ctx, propName: name, objPath: value && value.type === 'ObjectExpression' ? objPath : undefined });
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
    // Default values of parameters are code too: `function f(env = process.env)`, `(x = LIMIT)`.
    const defaults = (p) => {
      if (!p) return;
      if (p.type === 'AssignmentPattern') { this.visit(p.right, p, 'right', inner); defaults(p.left); } else if (p.type === 'ObjectPattern') p.properties.forEach((q) => defaults(q.type === 'RestElement' ? q.argument : q.value));
      else if (p.type === 'ArrayPattern') p.elements.forEach(defaults);
      else if (p.type === 'TSParameterProperty') defaults(p.parameter);
    };
    node.params.forEach(defaults);
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
        this.facts.importUses.push({ source: node.source.value, name: imported, line: A.lineOf(spec) });
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
    // Destructured fields: const { a, b: { c } } = obj.x reads obj.x.a and obj.x.b.c.
    if (node.id.type === 'ObjectPattern' && init && !req && !isEnvObject(init)) {
      const chain = A.memberChain(init);
      if (chain.root && chain.root.type === 'Identifier' && !chain.path.includes(null)) {
        const b = lookup(ctx.scopes, chain.root.name);
        if (!(b && b.import) && !(!b && GLOBALS.has(chain.root.name))) {
          const walkPattern = (pat, prefix) => {
            for (const p of pat.properties) {
              if (p.type !== 'ObjectProperty') continue;
              const k = A.keyName(p.key, p.computed);
              if (!k) continue;
              const dflt = p.value.type === 'AssignmentPattern' ? A.unwrap(p.value.right) : null;
              this.facts.fields.push({ path: [...prefix, k], root: chain.root.name, line: A.lineOf(p), owner: ctx.owner && ctx.owner.id, write: false, compared: null,
                fallback: dflt && LITERAL.has(dflt.type) ? dflt.value : null,
                origin: originOf(b, this.text), initNode: b && b.init ? A.unwrap(b.init) : null });
              if (p.value.type === 'ObjectPattern') walkPattern(p.value, [...prefix, k]);
            }
          };
          walkPattern(node.id, chain.path);
        }
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
    if (b) {
      // Uses of a module-level declaration, for the unused report.
      if (b.module) {
        const write = this.isWrite(node, parent, key);
        if (write) b.writes = (b.writes || 0) + 1;
        // `row: next++` reads next as well as setting it; `next++;` on its own only sets it.
        const gp = this.stack[this.stack.length - 3];
        const updateUsed = parent.type === 'UpdateExpression' && gp && gp.type !== 'ExpressionStatement'
          && !(gp.type === 'ForStatement' && gp.update === parent) && gp.type !== 'SequenceExpression';
        if (!write || updateUsed) b.reads = (b.reads || 0) + 1;
      }
      if (wholeImport(b)) this.wholeImportUse(b, node, parent, key);
    }
    if (!b || !ctx.owner || !b.module) return;
    if (!['var', 'let', 'const'].includes(b.kind) || b.import) return;
    const init = A.unwrap(b.init);
    if (init && (A.isFunction(init) || init.type === 'ClassExpression')) return;
    this.facts.varRefs.push({ owner: ctx.owner.id, name: node.name, write: this.isWrite(node, parent, key), line: A.lineOf(node) });
  }

  // A reference to a whole imported module (`const m = require('./m')`, `import * as m`, a default
  // import): `m.name` uses one export (recorded in member()), `const { a } = m` uses a, and anything
  // else passes the module on, which uses all of it (or, for a default import, its default).
  wholeImportUse(b, node, parent, key) {
    if (A.isMember(parent) && key === 'object') return;
    const line = A.lineOf(node);
    if (parent.type === 'VariableDeclarator' && key === 'init' && parent.id.type === 'ObjectPattern') {
      for (const p of parent.id.properties) {
        const name = p.type === 'RestElement' ? '*' : A.keyName(p.key, p.computed) || '*';
        this.facts.importUses.push({ source: b.import.source, name, line });
      }
      return;
    }
    this.facts.importUses.push({ source: b.import.source, name: b.import.imported === 'default' ? 'default' : '*', line });
  }

  // process.env, a parameter that defaults to it, or a variable set to it.
  isEnvSource(obj, ctx) {
    if (!obj) return false;
    if (isEnvObject(obj)) return true;
    if (obj.type !== 'Identifier') return false;
    const b = lookup(ctx.scopes, obj.name);
    if (!b) return false;
    if (b.kind === 'param' && b.param) {
      const p = b.param.fn.params[b.param.index];
      return !!p && p.type === 'AssignmentPattern' && isEnvObject(A.unwrap(p.right));
    }
    return !!b.init && isEnvObject(A.unwrap(b.init));
  }

  // A path a script is started with: 'x.js', path.join(__dirname, 'x.js'), or a constant holding one.
  scriptPath(node, ctx, depth = 0) {
    node = A.unwrap(node);
    if (!node || depth > 3) return null;
    const s = A.staticString(node);
    if (s !== null) {
      const token = s.split(/\s+/).find((t) => SCRIPT_FILE.test(t));
      return token ? { base: 'plain', value: token.replace(/^["']|["']$/g, '') } : null;
    }
    if (A.isCall(node)) {
      const chain = A.memberChain(node.callee);
      if (chain.root && chain.root.type === 'Identifier' && chain.root.name === 'path' && /^(join|resolve)$/.test(chain.path[0])) {
        const [first, ...rest] = node.arguments;
        const parts = rest.map((a) => A.staticString(a));
        if (first && first.type === 'Identifier' && first.name === '__dirname' && parts.every((p) => p !== null)) {
          const value = parts.join('/');
          return SCRIPT_FILE.test(value) ? { base: 'dir', value } : null;
        }
      }
      return null;
    }
    if (node.type === 'Identifier') {
      const b = lookup(ctx.scopes, node.name);
      if (b && b.kind === 'const' && b.init) return this.scriptPath(b.init, ctx, depth + 1);
    }
    return null;
  }

  scriptRefs(args, ctx, line) {
    const each = (a) => {
      a = A.unwrap(a);
      if (!a) return;
      if (a.type === 'ArrayExpression') { a.elements.forEach(each); return; }
      if (a.type === 'ObjectExpression') {
        // chrome.scripting.executeScript({ files: ['x.js'] })
        for (const p of a.properties) if (p.type === 'ObjectProperty' && A.keyName(p.key, p.computed) === 'files') each(p.value);
        return;
      }
      const ref = this.scriptPath(a, ctx);
      if (ref) this.facts.scriptRefs.push({ ...ref, line });
    };
    args.forEach(each);
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
    // One export of a whole imported module: m.name, require('./m').name.
    const prop = A.keyName(node.property, node.computed);
    if (obj.type === 'Identifier') {
      const ob = lookup(ctx.scopes, obj.name);
      if (wholeImport(ob)) this.facts.importUses.push({ source: ob.import.source, name: prop === null ? '*' : prop, line: A.lineOf(node) });
    } else if (A.isCall(obj) && isRequireCall(obj) && !lookup(ctx.scopes, 'require')) {
      const src = obj.arguments[0] ? A.staticString(obj.arguments[0]) : null;
      if (src !== null) this.facts.importUses.push({ source: src, name: prop === null ? '*' : prop, line: A.lineOf(node) });
    }
    // A parameter used as an environment variable name: env[name], process.env[name].
    if (node.computed && ctx.owner && node.property.type === 'Identifier') {
      const pb = lookup(ctx.scopes, node.property.name);
      if (pb && pb.kind === 'param' && pb.param && pb.param.fn === ctx.owner.node && this.isEnvSource(obj, ctx)) {
        this.facts.envParamReads.push({ owner: ctx.owner.id, index: pb.param.index, line: A.lineOf(node) });
      }
    }
    if (isEnvObject(obj)) {
      const name = A.keyName(node.property, node.computed);
      this.facts.env.push({ name, line: A.lineOf(node), owner: ctx.owner && ctx.owner.id, dynamic: name === null, text: name === null ? A.snippet(this.text, node) : undefined });
    }
    if (!(A.isMember(parent) && parent.object === node)) this.field(node, parent, key, ctx);
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

  // A data field: the outermost property path read or written on a value that is not a module API,
  // with the literal it is compared with and the default it falls back to, when the syntax says so.
  field(node, parent, key, ctx) {
    const chain = A.memberChain(node);
    const root = chain.root;
    if (!root || root.type !== 'Identifier') return;
    const b = lookup(ctx.scopes, root.name);
    if ((!b && GLOBALS.has(root.name)) || (b && b.import) || isEnvObject(A.unwrap(node.object))) return;
    const path = [];
    for (const k of chain.path) { if (k === null || k.startsWith('#')) break; path.push(k); }
    if (A.isCall(parent) && parent.callee === node && path.length === chain.path.length) path.pop();
    if (!path.length) return;
    let base = [];
    let origin = b;
    if (b && b.pattern && b.initBinding && b.pattern.every((p) => p && !p.startsWith('[') && p !== '...')) { base = b.pattern; origin = b.initBinding; }
    const s = this.stack;
    const up = s[s.length - 2];
    let compared = null;
    let fallback = null;
    if (up && up.type === 'BinaryExpression' && /^[!=]==?$/.test(up.operator)) {
      const other = A.unwrap(up.left === node ? up.right : up.left);
      if (other && LITERAL.has(other.type)) compared = [other.value];
    } else if (up && up.type === 'LogicalExpression' && (up.operator === '||' || up.operator === '??') && up.left === node) {
      const r = A.unwrap(up.right);
      if (r && LITERAL.has(r.type)) fallback = r.value;
    } else if (up && up.type === 'SwitchStatement' && up.discriminant === node) {
      compared = up.cases.map((c) => c.test && A.unwrap(c.test)).filter((t) => t && LITERAL.has(t.type)).map((t) => t.value);
    } else if (up && A.isCall(up) && up.arguments[0] === node && A.isMember(up.callee) && A.keyName(up.callee.property, up.callee.computed) === 'includes') {
      const arr = A.unwrap(up.callee.object);
      if (arr && arr.type === 'ArrayExpression') compared = arr.elements.map((e) => e && A.unwrap(e)).filter((e) => e && LITERAL.has(e.type)).map((e) => e.value);
    }
    this.facts.fields.push({
      path: [...base, ...path], root: root.name, line: A.lineOf(node), owner: ctx.owner && ctx.owner.id,
      write: this.isWrite(node, parent, key), compared, fallback,
      origin: originOf(origin, this.text), initNode: origin && origin.init ? A.unwrap(origin.init) : null,
    });
  }

  call(node, ctx) {
    this.facts.callCount++;
    const callee = A.unwrap(node.callee);
    if (callee.type === 'Import') {
      const source = node.arguments[0] ? A.staticString(node.arguments[0]) : null;
      if (source !== null) {
        this.addImport(source, [], 'deferred', 'dynamic-import', node, ctx);
        this.facts.importUses.push({ source, name: '*', line: A.lineOf(node) });
      } else this.facts.imports.push({ source: null, names: [], load: 'deferred', kind: 'dynamic-import', unresolved: A.snippet(this.text, node), line: A.lineOf(node), owner: ctx.owner && ctx.owner.id });
      return;
    }
    if (callee.type === 'Identifier' && callee.name === 'require' && !lookup(ctx.scopes, 'require')) {
      if (node.__requireRecorded) return;
      const source = node.arguments[0] ? A.staticString(node.arguments[0]) : null;
      if (source !== null) {
        this.addImport(source, [], ctx.fnDepth ? 'deferred' : 'startup', 'require', node, ctx);
        // require('./m').name is recorded in member(); a bare require('./m') only runs the module;
        // anything else passes the whole module on.
        const parent = this.stack[this.stack.length - 2];
        const asObject = parent && A.isMember(parent) && A.unwrap(parent.object) === node;
        if (!asObject && !(parent && parent.type === 'ExpressionStatement')) this.facts.importUses.push({ source, name: '*', line: A.lineOf(node) });
      } else this.facts.imports.push({ source: null, names: [], load: ctx.fnDepth ? 'deferred' : 'startup', kind: 'require', unresolved: A.snippet(this.text, node), line: A.lineOf(node), owner: ctx.owner && ctx.owner.id });
      return;
    }
    const chain = A.memberChain(callee);
    const last = chain.path.length ? chain.path[chain.path.length - 1] : (chain.root && chain.root.type === 'Identifier' ? chain.root.name : null);
    if (last && (SCRIPT_RUNNERS.has(last) || last === 'executeScript')) this.scriptRefs(node.arguments, ctx, A.lineOf(node));
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
    // <Component /> and <ns.Component /> use the binding they name.
    let root = nameNode;
    while (root && root.type === 'JSXMemberExpression') root = root.object;
    if (root && root.type === 'JSXIdentifier' && (/^[A-Z]/.test(root.name) || root !== nameNode)) {
      const b = lookup(ctx.scopes, root.name);
      if (b && b.module) b.reads = (b.reads || 0) + 1;
      if (wholeImport(b)) {
        const prop = nameNode.type === 'JSXMemberExpression' && nameNode.object === root ? nameNode.property.name : null;
        this.facts.importUses.push({ source: b.import.source, name: prop || (b.import.imported === 'default' ? 'default' : '*'), line: A.lineOf(node) });
      }
    }
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

module.exports = { extractJs, lookup, requireInfo };
