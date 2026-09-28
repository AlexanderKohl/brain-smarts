'use strict';
// The project-wide view over every JavaScript-family file: where an import points, what a module
// exports (following re-exports), the value of a constant across files, which function a call
// reaches when that is certain, and the methods of a class including mixins.
// Part of the code-map skill (canonical copy: /shared/skills/code-map/).

const A = require('./ast');
const { lookup } = require('./extract');

class JsProject {
  constructor(resolver) {
    this.resolver = resolver;
    this.facts = new Map(); // file -> facts
  }

  add(facts) { this.facts.set(facts.file, facts); }

  target(fromFile, source) { return this.resolver.resolve(fromFile, source); }

  // The module a binding was imported from: { file, imported, member } or { package } or null.
  bindingTarget(facts, b) {
    if (!b || !b.import) return null;
    const r = this.target(facts.file, b.import.source);
    if (r.file) return { file: r.file, imported: b.import.imported, member: b.import.member || null };
    if (r.package) return { package: r.package, core: !!r.core, imported: b.import.imported, member: b.import.member || null };
    return null;
  }

  // What `import x from` / `require()` returns: the CommonJS module.exports value, or the default export.
  defaultOf(file) {
    const f = this.facts.get(file);
    if (!f) return null;
    const d = f.exports.cjsDefault || f.exports.default;
    if (!d) return null;
    const node = A.unwrap(d.node);
    const local = node && node.type === 'Identifier' ? node.name
      : node && (node.type === 'FunctionDeclaration' || node.type === 'ClassDeclaration' || node.type === 'ClassExpression') && node.id ? node.id.name : null;
    return { file, node, local, facts: f };
  }

  // One export by name, following re-exports. `*` means the module object itself.
  exportOf(file, name, seen = new Set()) {
    const f = this.facts.get(file);
    if (!f || seen.has(`${file}#${name}`)) return null;
    seen.add(`${file}#${name}`);
    if (name === 'default' || name === '*') {
      if (name === '*' && !f.exports.cjsDefault) return { file, facts: f, namespace: true };
      return this.defaultOf(file);
    }
    const named = f.exports.named.get(name);
    if (named) {
      if (named.fromSource) {
        const r = this.target(file, named.fromSource);
        return r.file ? this.exportOf(r.file, named.imported, seen) : null;
      }
      const node = named.value ? A.unwrap(named.value) : null;
      return this.followLocal({ file, facts: f, node, local: named.local || (node && node.type === 'Identifier' ? node.name : null) }, seen);
    }
    const cjs = f.exports.cjsDefault && A.unwrap(f.exports.cjsDefault.node);
    if (cjs && cjs.type === 'ObjectExpression') {
      for (const prop of cjs.properties) {
        if (prop.type === 'SpreadElement') continue;
        if (A.keyName(prop.key, prop.computed) !== name) continue;
        const node = prop.type === 'ObjectMethod' ? prop : A.unwrap(prop.value);
        return this.followLocal({ file, facts: f, node, local: node.type === 'Identifier' ? node.name : null }, seen);
      }
    }
    if (cjs && cjs.type === 'Identifier') {
      // module.exports = someObject: look inside a module-level object literal.
      const b = f.moduleScope.get(cjs.name);
      const init = b && A.unwrap(b.init);
      if (init && init.type === 'ObjectExpression') {
        for (const prop of init.properties) {
          if (prop.type !== 'SpreadElement' && A.keyName(prop.key, prop.computed) === name) {
            const node = prop.type === 'ObjectMethod' ? prop : A.unwrap(prop.value);
            return this.followLocal({ file, facts: f, node, local: node.type === 'Identifier' ? node.name : null }, seen);
          }
        }
      }
    }
    for (const star of f.exports.starFrom) {
      if (star.as) { if (star.as === name) { const r = this.target(file, star.source); return r.file ? { file: r.file, facts: this.facts.get(r.file), namespace: true } : null; } continue; }
      const r = this.target(file, star.source);
      if (!r.file) continue;
      const found = this.exportOf(r.file, name, seen);
      if (found) return found;
    }
    return null;
  }

  // An export that names a local import is the imported thing.
  followLocal(exp, seen) {
    if (!exp.local) return exp;
    const b = exp.facts.moduleScope.get(exp.local);
    if (b && b.import) {
      const t = this.bindingTarget(exp.facts, b);
      if (t && t.file) {
        const inner = this.exportOf(t.file, t.imported, seen);
        if (inner) return t.member ? this.exportOf(inner.file, t.member, seen) || inner : inner;
      }
    }
    return { ...exp, binding: b || null };
  }

  // The declaration an identifier refers to, across files: { facts, binding, node }.
  declaration(facts, name, scopes) {
    const b = lookup(scopes || [facts.moduleScope], name);
    if (!b) return null;
    if (b.import) {
      const t = this.bindingTarget(facts, b);
      if (!t || !t.file) return { facts, binding: b, external: t };
      let exp = this.exportOf(t.file, t.imported);
      if (exp && t.member) exp = this.exportOf(exp.file, t.member) || exp;
      if (!exp) return { facts, binding: b, unresolvedImport: t };
      const tb = exp.local ? exp.facts.moduleScope.get(exp.local) : null;
      return { facts: exp.facts, binding: tb, node: exp.node || (tb && tb.init), namespace: exp.namespace, file: exp.file };
    }
    return { facts, binding: b, node: b.init };
  }

  // A constant string, following consts and imports; null when it is only known at run time.
  valueOf(facts, node, scopes, depth = 0) {
    if (depth > 8) return null;
    node = A.unwrap(node);
    if (!node) return null;
    const recur = (f, s) => (n) => this.valueOf(f, n, s, depth + 1);
    if (node.type === 'Identifier') {
      const d = this.declaration(facts, node.name, scopes);
      if (!d || !d.binding) return null;
      if (d.binding.kind !== 'const' || d.binding.pattern || !d.binding.init) return null;
      return A.staticString(d.binding.init, recur(d.facts, null));
    }
    if (A.isMember(node)) {
      const chain = A.memberChain(node);
      if (!chain.root || chain.root.type !== 'Identifier' || chain.path.length !== 1 || chain.path[0] === null) return null;
      const d = this.declaration(facts, chain.root.name, scopes);
      if (!d) return null;
      if (d.file) {
        // A module (namespace import or CommonJS module object): look the name up among its exports.
        const exp = this.exportOf(d.file, chain.path[0]);
        if (exp && exp.local) {
          const b = exp.facts.moduleScope.get(exp.local);
          if (b && b.kind === 'const' && b.init && !b.pattern) return A.staticString(b.init, recur(exp.facts, null));
        }
        if (exp && exp.node) return A.staticString(exp.node, recur(exp.facts, null));
        return null;
      }
      if (d.binding && d.binding.import) return null;
      const init = d.node && A.unwrap(d.node);
      if (init && init.type === 'ObjectExpression' && d.binding && d.binding.kind === 'const') {
        for (const prop of init.properties) {
          if (prop.type === 'ObjectProperty' && A.keyName(prop.key, prop.computed) === chain.path[0]) {
            return A.staticString(prop.value, recur(d.facts, null));
          }
        }
      }
      return null;
    }
    return A.staticString(node, recur(facts, scopes));
  }

  // A resolver closure for A.staticString / A.stringParts at one place in one file.
  valueAt(facts, scopes) {
    return (n) => this.valueOf(facts, n, scopes);
  }

  // The function a call certainly reaches, as a function id, or null.
  callTarget(facts, site) {
    if (site.rootType === 'id' && site.path.length === 0) {
      const b = site.binding;
      if (!b) return null;
      if (b.module && (b.kind === 'function' || (b.kind === 'const' && b.init && A.isFunction(A.unwrap(b.init))))) {
        const fn = facts.functionsByName.get(site.rootName);
        return fn ? fn.id : null;
      }
      if (b.import) return this.functionOfDeclaration(this.declaration(facts, site.rootName, site.scopes));
      return null;
    }
    if (site.rootType === 'id' && site.path.length === 1 && site.path[0]) {
      const b = site.binding;
      if (!b) return null;
      if (b.import) {
        const t = this.bindingTarget(facts, b);
        if (!t || !t.file) return null;
        if (t.imported === '*' || t.imported === 'default') {
          const exp = this.exportOf(t.file, site.path[0]);
          if (exp) return this.functionOfDeclaration({ facts: exp.facts, node: exp.node, binding: exp.local ? exp.facts.moduleScope.get(exp.local) : null });
        }
        const d = this.declaration(facts, site.rootName, site.scopes);
        if (d && d.binding && d.binding.kind === 'class') return this.methodId(d.facts, d.binding.name, site.path[0]);
        return null;
      }
      if (b.module && b.kind === 'class') return this.methodId(facts, site.rootName, site.path[0]);
      return null;
    }
    if (site.rootType === 'this' && site.path.length === 1 && site.className) {
      return this.methodId(facts, site.className, site.path[0]);
    }
    return null;
  }

  functionOfDeclaration(d) {
    if (!d || !d.facts) return null;
    const node = d.node ? A.unwrap(d.node) : null;
    if (node) {
      const hit = d.facts.functions.find((f) => f.node === node);
      if (hit) return hit.id;
    }
    if (d.binding && (d.binding.kind === 'function' || d.binding.kind === 'const')) {
      const fn = d.facts.functionsByName.get(d.binding.name);
      if (fn) return fn.id;
    }
    return null;
  }

  methodId(facts, className, method) {
    const own = facts.functions.find((f) => f.className === className && f.name === method);
    if (own) return own.id;
    const cls = facts.classes.find((c) => c.name === className);
    const mixed = cls && cls.mixinMethods ? cls.mixinMethods.get(method) : null;
    return mixed || null;
  }

  // Adds prototype assignments and Object.assign(X.prototype, ...) mixins to each class.
  linkClasses() {
    for (const facts of this.facts.values()) {
      for (const cls of facts.classes) {
        cls.mixinMethods = new Map();
        cls.mixins = [];
        for (const a of facts.assignments) {
          if (a.rootName === cls.name && a.path[0] === 'prototype' && a.path.length === 2 && a.path[1]) {
            if (!cls.methods.some((m) => m.name === a.path[1])) cls.methods.push({ name: a.path[1], static: false, kind: 'method', line: a.line, prototype: true });
          }
        }
        for (const site of facts.callSites) {
          if (site.fnDepth !== 0 || site.rootName !== 'Object' || site.path[0] !== 'assign' || !site.args.length) continue;
          const first = A.memberChain(site.args[0]);
          if (!first.root || first.root.type !== 'Identifier' || first.root.name !== cls.name || first.path[0] !== 'prototype') continue;
          for (const arg of site.args.slice(1)) this.addMixin(facts, cls, arg.type === 'SpreadElement' ? arg.argument : arg, site);
        }
      }
    }
  }

  addMixin(facts, cls, node, site) {
    node = A.unwrap(node);
    let file = null;
    let obj = null;
    if (node.type === 'ObjectExpression') obj = { facts, node };
    else if (A.isCall(node) && node.callee.type === 'Identifier' && node.callee.name === 'require') {
      const r = this.target(facts.file, A.staticString(node.arguments[0]));
      file = r.file || null;
    } else if (node.type === 'Identifier') {
      const d = this.declaration(facts, node.name, site.scopes);
      if (d && d.namespace) file = d.file;
      else if (d && d.facts !== facts && d.node && A.unwrap(d.node).type === 'ObjectExpression') obj = { facts: d.facts, node: A.unwrap(d.node) };
      else if (d && d.binding && d.binding.import) {
        const t = this.bindingTarget(facts, d.binding);
        if (t && t.file) file = t.file;
      } else if (d && d.node && A.unwrap(d.node).type === 'ObjectExpression') obj = { facts: d.facts, node: A.unwrap(d.node) };
    }
    if (file) {
      const def = this.defaultOf(file);
      const target = def && def.node && def.node.type === 'ObjectExpression' ? { facts: def.facts, node: def.node } : null;
      const names = target ? null : [...(this.facts.get(file) ? this.facts.get(file).exports.named.keys() : [])];
      cls.mixins.push(file);
      if (target) obj = target;
      else if (names) for (const n of names) this.addMixinMethod(cls, n, this.functionOfDeclaration(this.declarationOfExport(file, n)), file);
    }
    if (obj) {
      for (const prop of obj.node.properties) {
        if (prop.type === 'SpreadElement') continue;
        const name = A.keyName(prop.key, prop.computed);
        if (!name) continue;
        const valueNode = prop.type === 'ObjectMethod' ? prop : A.unwrap(prop.value);
        let fnId = null;
        const hit = obj.facts.functions.find((f) => f.node === valueNode);
        if (hit) fnId = hit.id;
        else if (valueNode.type === 'Identifier') fnId = this.functionOfDeclaration(this.declaration(obj.facts, valueNode.name));
        this.addMixinMethod(cls, name, fnId, obj.facts.file);
      }
    }
  }

  declarationOfExport(file, name) {
    const exp = this.exportOf(file, name);
    if (!exp) return null;
    return { facts: exp.facts, node: exp.node, binding: exp.local ? exp.facts.moduleScope.get(exp.local) : null };
  }

  addMixinMethod(cls, name, fnId, file) {
    if (!cls.methods.some((m) => m.name === name)) cls.methods.push({ name, static: false, kind: 'method', mixin: file });
    if (fnId) cls.mixinMethods.set(name, fnId);
  }
}

module.exports = { JsProject };
