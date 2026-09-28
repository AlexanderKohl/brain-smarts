'use strict';
// Express: apps and routers, every route and middleware in registration order, error handlers, and
// where each router is mounted – directly, through a mount function's parameters, or through a
// router factory – so each route gets its full path. Part of the code-map skill
// (canonical copy: /shared/skills/code-map/).

const A = require('../js/ast');
const { lookup } = require('../js/extract');

const VERBS = new Set(['get', 'post', 'put', 'patch', 'delete', 'del', 'all', 'options', 'head']);

function joinPath(a, b) {
  const s = `${a || ''}/${b || ''}`.replace(/\/{2,}/g, '/');
  return s.length > 1 ? s.replace(/\/$/, '') : '/';
}

function expressAdapter(ctx) {
  const { project, graph } = ctx;
  const siteOfNode = new Map();
  for (const facts of project.facts.values()) for (const site of facts.callSites) siteOfNode.set(site.node, { facts, site });

  const routers = new Map(); // binding -> router
  const mounts = []; // { parent, child, prefix, start, line, file }

  const isExpress = (facts, b) => {
    if (!b || !b.import) return false;
    const t = project.bindingTarget(facts, b);
    return !!(t && t.package === 'express');
  };

  // 'app' | 'router' | null for the call that initialises a binding.
  const creates = (facts, node, scopes) => {
    node = A.unwrap(node);
    if (!A.isCall(node)) return null;
    const chain = A.memberChain(node.callee);
    const root = chain.root;
    if (root && root.type === 'Identifier') {
      const b = lookup(scopes, root.name);
      if (!isExpress(facts, b)) return null;
      const imported = b.import.member || b.import.imported;
      if (chain.path.length === 0) return imported === 'Router' ? 'router' : 'app';
      if (chain.path.length === 1 && chain.path[0] === 'Router') return 'router';
    }
    if (root && A.isCall(root) && root.callee.type === 'Identifier' && root.callee.name === 'require' && A.staticString(root.arguments[0]) === 'express') {
      if (chain.path.length === 1 && chain.path[0] === 'Router') return 'router';
    }
    return null;
  };

  const routerOf = (facts, b, scopes) => {
    if (!b) return null;
    if (routers.has(b)) return routers.get(b);
    if (!b.init) return null;
    const kind = creates(facts, b.init, scopes || [facts.moduleScope]);
    if (!kind) return null;
    const created = siteOfNode.get(A.unwrap(b.init));
    const r = {
      id: `router:${facts.file}#${b.name}${b.module ? '' : `@${b.line}`}`, facts, name: b.name, kind, line: b.line,
      owner: created ? created.site.owner : null, registrations: [],
    };
    routers.set(b, r);
    return r;
  };

  // The function a callee expression names, as a function id.
  const functionOf = (facts, callee, scopes) => {
    callee = A.unwrap(callee);
    if (callee.type === 'Identifier') return project.functionOfDeclaration(project.declaration(facts, callee.name, scopes));
    if (!A.isMember(callee)) return null;
    const chain = A.memberChain(callee);
    if (chain.path.length !== 1 || !chain.path[0]) return null;
    let file = null;
    if (chain.root.type === 'Identifier') {
      const d = project.declaration(facts, chain.root.name, scopes);
      file = d && d.file;
    } else if (A.isCall(chain.root) && chain.root.callee.type === 'Identifier' && chain.root.callee.name === 'require') {
      const r = project.target(facts.file, A.staticString(chain.root.arguments[0]));
      file = r.file || null;
    }
    if (!file) return null;
    return project.functionOfDeclaration(project.declarationOfExport(file, chain.path[0]));
  };

  // Routers an argument of use() refers to; 'static' for express.static; null for middleware.
  const mountTargets = (facts, node, scopes) => {
    node = A.unwrap(node);
    if (!node) return null;
    if (node.type === 'Identifier') {
      const b = lookup(scopes, node.name);
      const local = routerOf(facts, b, scopes);
      if (local) return [local];
      if (b && b.import) {
        const d = project.declaration(facts, node.name, scopes);
        if (d && d.binding) {
          const r = routerOf(d.facts, d.binding);
          if (r) return [r];
        }
        if (d && d.file) {
          const def = project.defaultOf(d.file);
          if (def && def.local) {
            const r = routerOf(def.facts, def.facts.moduleScope.get(def.local));
            if (r) return [r];
          }
        }
      }
      return null;
    }
    if (A.isCall(node)) {
      const chain = A.memberChain(node.callee);
      if (chain.root && chain.root.type === 'Identifier' && chain.path.length === 1 && chain.path[0] === 'static' && isExpress(facts, lookup(scopes, chain.root.name))) return 'static';
      const fnId = functionOf(facts, node.callee, scopes);
      if (fnId) {
        const made = [...routers.values()].filter((r) => r.owner === fnId);
        if (made.length) return made;
      }
    }
    return null;
  };

  // Pass 1: every router and app, so later passes can recognise them.
  for (const facts of project.facts.values()) {
    for (const site of facts.callSites) {
      if (site.rootType === 'id' && site.binding) routerOf(facts, site.binding, site.scopes);
    }
    for (const b of facts.moduleScope.values()) routerOf(facts, b);
  }

  // Pass 2: registrations.
  for (const facts of project.facts.values()) {
    for (const site of facts.callSites) {
      if (site.path.length !== 1) continue;
      const verb = site.path[0];
      if (!VERBS.has(verb) && verb !== 'use') continue;
      let router = null;
      let routePath;
      if (site.rootType === 'id') router = routerOf(facts, site.binding, site.scopes);
      else if (site.rootType === 'call' && VERBS.has(verb)) {
        let base = site.root;
        while (base && A.isCall(base)) {
          const c = A.memberChain(base.callee);
          if (c.path.length === 1 && c.path[0] === 'route' && c.root && c.root.type === 'Identifier') {
            router = routerOf(facts, lookup(site.scopes, c.root.name), site.scopes);
            routePath = base.arguments[0];
            break;
          }
          if (c.path.length === 1 && VERBS.has(c.path[0]) && A.isCall(c.root)) { base = c.root; continue; }
          break;
        }
      }
      if (!router) continue;
      router.registrations.push({ verb, site, facts, routePath, start: site.node.start, line: site.line });
    }
  }

  // Pass 3: mount functions – function (app, { a, b, list }) { app.use('/p', a); for (const x of list) app.use('/q', x) }.
  const mountFns = new Map();
  for (const facts of project.facts.values()) {
    for (const fn of facts.functions) {
      const p0 = fn.node.params[0];
      if (!p0 || p0.type !== 'Identifier') continue;
      const entries = [];
      for (const site of facts.callSites) {
        if (site.owner !== fn.id || site.rootType !== 'id' || site.path.length !== 1 || site.path[0] !== 'use') continue;
        const b = site.binding;
        if (!b || !b.param || b.param.fn !== fn.node || b.param.index !== 0) continue;
        const prefix = site.args[0] ? A.staticString(site.args[0]) : null;
        const rest = prefix !== null ? site.args.slice(1) : site.args;
        for (const arg of rest) {
          const a = A.unwrap(arg);
          if (a.type !== 'Identifier') { entries.push({ prefix, direct: a, site }); continue; }
          const ab = lookup(site.scopes, a.name);
          if (ab && ab.param && ab.param.fn === fn.node && ab.pattern) entries.push({ prefix, prop: ab.pattern[0], site });
          else if (ab && ab.forOf && A.unwrap(ab.forOf).type === 'Identifier') {
            const lb = lookup(site.scopes, A.unwrap(ab.forOf).name);
            if (lb && lb.param && lb.param.fn === fn.node && lb.pattern) entries.push({ prefix, prop: lb.pattern[0], array: true, site });
          } else entries.push({ prefix, direct: a, site });
        }
      }
      if (entries.some((e) => e.prop)) mountFns.set(fn.id, { fn, facts, entries });
    }
  }
  for (const facts of project.facts.values()) {
    for (const site of facts.callSites) {
      const target = project.callTarget(facts, site);
      const mf = target && mountFns.get(target);
      if (!mf || !site.args[0]) continue;
      const parentArg = A.unwrap(site.args[0]);
      const parent = parentArg.type === 'Identifier' ? routerOf(facts, lookup(site.scopes, parentArg.name), site.scopes) : null;
      if (!parent) continue;
      const obj = site.args[1] && A.unwrap(site.args[1]);
      const props = new Map();
      if (obj && obj.type === 'ObjectExpression') {
        for (const p of obj.properties) if (p.type === 'ObjectProperty') props.set(A.keyName(p.key, p.computed), A.unwrap(p.value));
      }
      mf.entries.forEach((entry, i) => {
        const nodes = [];
        if (entry.prop) {
          const v = props.get(entry.prop);
          if (!v) return;
          if (entry.array && v.type === 'ArrayExpression') nodes.push(...v.elements.filter(Boolean));
          else nodes.push(v);
          for (const n of nodes) {
            const targets = mountTargets(facts, n, site.scopes);
            if (Array.isArray(targets)) for (const child of targets) mounts.push({ parent, child, prefix: entry.prefix || '', start: site.node.start + i / 1000, line: entry.site.line, file: mf.facts.file, via: mf.fn.qualified });
            else graph.unresolvedItem('mount', facts.file, site.line, A.snippet(site.text, n), 'mounted value is not a router this map can follow');
          }
        } else if (entry.direct) {
          const targets = mountTargets(mf.facts, entry.direct, entry.site.scopes);
          if (Array.isArray(targets)) for (const child of targets) mounts.push({ parent, child, prefix: entry.prefix || '', start: site.node.start + i / 1000, line: entry.site.line, file: mf.facts.file, via: mf.fn.qualified });
        }
      });
    }
  }

  // Pass 4: routes, middleware and direct mounts, in registration order.
  const order = [];
  for (const router of routers.values()) {
    router.registrations.sort((a, b) => a.start - b.start);
    const entries = [];
    router.registrations.forEach((reg, index) => {
      const { site, facts } = reg;
      if (reg.verb === 'use') {
        const prefixNode = site.args[0];
        const prefix = prefixNode ? A.staticString(prefixNode, project.valueAt(facts, site.scopes)) : null;
        const args = prefix !== null ? site.args.slice(1) : site.args;
        for (const arg of args) {
          const inner = arg.type === 'SpreadElement' ? arg.argument : arg;
          const targets = arg.type === 'SpreadElement' ? null : mountTargets(facts, inner, site.scopes);
          if (Array.isArray(targets)) {
            for (const child of targets) {
              mounts.push({ parent: router, child, prefix: prefix || '', start: reg.start, line: reg.line, file: facts.file });
              entries.push({ kind: 'mount', prefix: prefix || '/', target: child.id, line: reg.line, order: index });
            }
          } else {
            const errorHandler = handlerParams(project, facts, inner, site.scopes) === 4;
            entries.push({ kind: targets === 'static' ? 'static' : errorHandler ? 'error-handler' : 'middleware', prefix: prefix || '/', label: A.snippet(site.text, inner, 60), line: reg.line, order: index });
          }
        }
        return;
      }
      const pathNode = reg.routePath || site.args[0];
      const localPath = pathNode ? A.staticString(pathNode, project.valueAt(facts, site.scopes)) : null;
      const handlers = reg.routePath ? site.args : site.args.slice(1);
      const last = handlers[handlers.length - 1];
      const handler = last ? handlerId(project, facts, last, site) : null;
      const method = reg.verb === 'del' ? 'DELETE' : reg.verb === 'all' ? 'ALL' : reg.verb.toUpperCase();
      if (localPath === null) {
        graph.unresolvedItem('route-path', facts.file, reg.line, A.snippet(site.text, site.node, 100), 'route path is not a literal');
        return;
      }
      entries.push({ kind: 'route', method, path: localPath, line: reg.line, order: index, handler,
        middleware: handlers.slice(0, -1).map((h) => A.snippet(site.text, h, 50)) });
    });
    router.entries = entries;
  }

  // Full paths: every chain of mounts from an app down to the router.
  const memo = new Map();
  const prefixesOf = (router, seen = new Set()) => {
    if (memo.has(router)) return memo.get(router);
    if (router.kind === 'app') { memo.set(router, ['']); return ['']; }
    if (seen.has(router)) return [];
    seen.add(router);
    const out = new Set();
    for (const m of mounts) if (m.child === router) for (const p of prefixesOf(m.parent, seen)) out.add(joinPath(p, m.prefix));
    const list = [...out];
    memo.set(router, list);
    return list;
  };

  for (const router of routers.values()) {
    const prefixes = prefixesOf(router);
    graph.node(router.id, 'router', { file: router.facts.file, name: router.name, kind: router.kind, line: router.line, mountedAt: prefixes.slice().sort(), mounted: router.kind === 'app' || prefixes.length > 0 });
    graph.edge('contains', `file:${router.facts.file}`, router.id);
    order.push({ id: router.id, file: router.facts.file, name: router.name, kind: router.kind, entries: router.entries || [], mounted: router.kind === 'app' || prefixes.length > 0 });
    for (const e of router.entries || []) {
      if (e.kind !== 'route') continue;
      const fulls = prefixes.length ? prefixes.map((p) => joinPath(p, e.path)) : [null];
      for (const full of fulls) {
        const id = `route:${e.method} ${full === null ? `(not mounted) ${router.facts.file} ${e.path}` : full}`;
        const node = graph.nodes.get(id) ? graph.node(`${id} @${router.facts.file}:${e.line}`, 'route', {}) : graph.node(id, 'route', {});
        Object.assign(node, { method: e.method, path: full, localPath: e.path, file: router.facts.file, line: e.line, framework: 'express', router: router.id, order: e.order, middleware: e.middleware });
        graph.edge('contains', `file:${router.facts.file}`, node.id);
        graph.edge('defines', router.id, node.id);
        if (e.handler) graph.edge('handles', node.id, `fn:${e.handler}`);
        if (full !== null) ctx.routes.push({ method: e.method, path: full, id: node.id, file: router.facts.file, line: e.line, framework: 'express' });
      }
    }
  }
  for (const m of mounts) graph.edge('mounts', m.parent.id, m.child.id, { prefix: m.prefix || '/', file: m.file, line: m.line, via: m.via });
  ctx.routerOrder = order;
  graph.cover('framework:express', routers.size ? 'mapped' : 'not used', { routers: routers.size, mounts: mounts.length });
}

function handlerId(project, facts, node, site) {
  node = A.unwrap(node);
  if (A.isFunction(node)) {
    const own = facts.functions.find((f) => f.node === node);
    return own ? own.id : site.owner;
  }
  if (node.type === 'Identifier') return project.functionOfDeclaration(project.declaration(facts, node.name, site.scopes));
  if (A.isMember(node)) {
    const chain = A.memberChain(node);
    if (chain.root.type === 'Identifier' && chain.path.length === 1 && chain.path[0]) {
      const d = project.declaration(facts, chain.root.name, site.scopes);
      if (d && d.file) return project.functionOfDeclaration(project.declarationOfExport(d.file, chain.path[0]));
    }
  }
  return null;
}

// Number of parameters of a middleware function, when known (4 means an error handler).
function handlerParams(project, facts, node, scopes) {
  node = A.unwrap(node);
  if (!node) return null;
  if (A.isFunction(node)) return node.params.length;
  if (node.type === 'Identifier') {
    const d = project.declaration(facts, node.name, scopes);
    const fn = d && d.node ? A.unwrap(d.node) : null;
    return fn && A.isFunction(fn) ? fn.params.length : null;
  }
  return null;
}

module.exports = { expressAdapter, joinPath };
