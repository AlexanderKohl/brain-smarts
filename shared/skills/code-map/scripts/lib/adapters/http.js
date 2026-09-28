'use strict';
// HTTP calls made by the code (fetch, axios and its instances, and the wrappers and URL builders a
// project declares), turned into URL patterns and matched to the routes the backends define.
// A URL assembled at run time is listed as unresolved, never guessed. Part of the code-map skill
// (canonical copy: /shared/skills/code-map/).

const A = require('../js/ast');
const { lookup } = require('../js/extract');

const AXIOS_VERBS = { get: 'GET', delete: 'DELETE', head: 'HEAD', options: 'OPTIONS', post: 'POST', put: 'PUT', patch: 'PATCH' };

function propOf(obj, name) {
  obj = A.unwrap(obj);
  if (!obj || obj.type !== 'ObjectExpression') return null;
  const p = obj.properties.find((x) => x.type === 'ObjectProperty' && A.keyName(x.key, x.computed) === name);
  return p ? p.value : null;
}

// Segments of a route or call path; params and wildcards normalised.
function segments(p) {
  return p.split('/').filter(Boolean);
}

function segKind(seg) {
  if (seg === '*' || /^:[^/]*\*\??$/.test(seg) || seg === '(.*)') return 'rest';
  if (/^:[A-Za-z0-9_]+\?$/.test(seg)) return 'optional';
  if (seg.startsWith(':')) return 'param';
  if (seg.includes('*')) return 'glob';
  return 'literal';
}

// Does a call path (with :param for unknown parts) fit a route path?
function pathMatches(route, call) {
  const r = segments(route);
  const c = segments(call);
  const go = (i, j) => {
    if (i === r.length) return j === c.length;
    const k = segKind(r[i]);
    if (k === 'rest') return true;
    if (k === 'optional') return go(i + 1, j) || (j < c.length && go(i + 1, j + 1));
    if (j === c.length) return false;
    if (k === 'param' || k === 'glob') return go(i + 1, j + 1);
    return (c[j] === r[i] || c[j] === ':param') && go(i + 1, j + 1);
  };
  return go(0, 0);
}

function methodMatches(routeMethod, callMethod) {
  return routeMethod === 'ALL' || callMethod === '*' || routeMethod === callMethod || (routeMethod === 'GET' && callMethod === 'HEAD');
}

function httpAdapter(ctx) {
  const { project, graph, config } = ctx;
  const builders = new Map((config.http.urlBuilders || []).map((b) => [b.name, b]));
  const wrappers = new Map((config.http.wrappers || []).map((w) => [w.name, w]));
  const envPrefixes = config.http.env || {};
  const calls = [];

  for (const facts of project.facts.values()) {
    const valueAt = (scopes) => (n) => {
      const v = project.valueOf(facts, n, scopes);
      if (v !== null) return v;
      const chain = A.memberChain(n);
      const envName = envRead(chain);
      return envName && Object.prototype.hasOwnProperty.call(envPrefixes, envName) ? envPrefixes[envName] : null;
    };

    // URL pattern for a node: { url } | { external } | { unresolved: reason }
    const urlOf = (node, scopes, depth = 0) => {
      node = A.unwrap(node);
      if (!node) return { unresolved: 'no URL argument' };
      if (depth > 4) return { unresolved: 'URL built too indirectly' };
      if (node.type === 'NewExpression' && node.callee.type === 'Identifier' && node.callee.name === 'URL') return urlOf(node.arguments[0], scopes, depth + 1);
      if (A.isCall(node) && A.unwrap(node.callee).type === 'Identifier' && builders.has(A.unwrap(node.callee).name)) {
        const b = builders.get(A.unwrap(node.callee).name);
        const inner = urlOf(node.arguments[b.arg || 0], scopes, depth + 1);
        return inner.url !== undefined ? { url: (b.prefix || '') + inner.url } : inner;
      }
      if (node.type === 'Identifier') {
        const b = lookup(scopes, node.name);
        if (b && b.kind === 'const' && b.init && !b.pattern && !b.import) return urlOf(b.init, scopes, depth + 1);
      }
      const parts = A.stringParts(node, valueAt(scopes));
      if (!parts) return { unresolved: 'URL is not a string' };
      let url = '';
      for (let i = 0; i < parts.length; i++) {
        const part = parts[i];
        if (typeof part === 'string') { url += part; continue; }
        const d = A.unwrap(part.dynamic);
        if (A.isCall(d) && d.callee.type === 'Identifier' && builders.has(d.callee.name)) {
          const inner = urlOf(d, scopes, depth + 1);
          if (inner.url === undefined) return inner;
          url += inner.url;
          continue;
        }
        if (i === 0 && url === '') return { unresolved: 'the start of the URL is only known at run time' };
        url += ':param';
      }
      const cut = url.search(/[?#]/);
      if (cut >= 0) url = url.slice(0, cut);
      if (/^[a-z][a-z0-9+.-]*:\/\//i.test(url)) return { external: url.replace(/:param/g, '…') };
      if (url.startsWith('//')) return { external: url };
      if (!url.startsWith('/')) return { unresolved: 'relative URL: resolved by the browser against the page it runs on' };
      return { url: url.replace(/\/{2,}/g, '/') };
    };

    const methodOf = (init, fallback) => {
      const m = init ? propOf(init, 'method') : null;
      if (!m) return init && A.unwrap(init).type !== 'ObjectExpression' ? '*' : fallback;
      const v = A.staticString(m);
      return v === null ? '*' : v.toUpperCase();
    };

    const instanceBase = (b, scopes) => {
      if (!b) return undefined;
      let d = { facts, node: b.init, scopes };
      if (b.import) {
        const dd = project.declaration(facts, b.name, scopes);
        if (!dd) return undefined;
        d = { facts: dd.facts, node: dd.node, scopes: [dd.facts.moduleScope] };
      }
      const init = d.node && A.unwrap(d.node);
      if (!init || !A.isCall(init)) return undefined;
      const chain = A.memberChain(init.callee);
      if (!chain.root || chain.root.type !== 'Identifier' || chain.path.length !== 1 || chain.path[0] !== 'create') return undefined;
      const ab = lookup(d.scopes, chain.root.name);
      const t = ab && ab.import ? project.bindingTarget(d.facts, ab) : null;
      if (!t || t.package !== 'axios') return undefined;
      const baseNode = propOf(init.arguments[0], 'baseURL');
      if (!baseNode) return '';
      const v = project.valueOf(d.facts, baseNode, d.scopes);
      if (v !== null) return v.replace(/\/$/, '');
      const envName = envRead(A.memberChain(baseNode));
      if (envName && Object.prototype.hasOwnProperty.call(envPrefixes, envName)) return envPrefixes[envName];
      return null;
    };

    const isAxios = (b) => {
      const t = b && b.import ? project.bindingTarget(facts, b) : null;
      return !!(t && t.package === 'axios' && !t.member && (t.imported === 'default' || t.imported === '*'));
    };

    for (const site of facts.callSites) {
      let client = null;
      let urlNode = null;
      let method = 'GET';
      let prefix = '';
      if (site.rootType === 'id' && site.rootName === 'fetch' && site.path.length === 0 && !site.binding) {
        client = 'fetch'; urlNode = site.args[0]; method = methodOf(site.args[1], 'GET');
      } else if (site.rootType === 'id' && /^(window|globalThis|self)$/.test(site.rootName) && !site.binding && site.path.length === 1 && site.path[0] === 'fetch') {
        client = 'fetch'; urlNode = site.args[0]; method = methodOf(site.args[1], 'GET');
      } else if (site.rootType === 'id' && site.binding && isAxios(site.binding)) {
        client = 'axios';
        if (site.path.length === 0) {
          const first = A.unwrap(site.args[0]);
          if (first && first.type === 'ObjectExpression') { urlNode = propOf(first, 'url'); method = methodOf(first, 'GET'); } else { urlNode = site.args[0]; method = methodOf(site.args[1], 'GET'); }
        } else if (site.path.length === 1 && AXIOS_VERBS[site.path[0]]) {
          urlNode = site.args[0]; method = AXIOS_VERBS[site.path[0]];
        } else if (site.path.length === 1 && site.path[0] === 'request') {
          urlNode = propOf(site.args[0], 'url'); method = methodOf(site.args[0], 'GET');
        } else continue;
      } else if (site.rootType === 'id' && site.binding && site.path.length === 1 && (AXIOS_VERBS[site.path[0]] || site.path[0] === 'request')) {
        const base = instanceBase(site.binding, site.scopes);
        if (base === undefined) continue;
        client = 'axios-instance';
        if (base === null) { calls.push({ facts, site, client, unresolved: 'the instance baseURL is only known at run time' }); continue; }
        prefix = base;
        if (site.path[0] === 'request') { urlNode = propOf(site.args[0], 'url'); method = methodOf(site.args[0], 'GET'); } else { urlNode = site.args[0]; method = AXIOS_VERBS[site.path[0]]; }
      } else if (site.rootType === 'id' && site.path.length === 0 && wrappers.has(site.rootName)) {
        const w = wrappers.get(site.rootName);
        client = site.rootName; urlNode = site.args[w.url || 0]; prefix = w.prefix || '';
        method = w.init !== undefined && w.init !== null ? methodOf(site.args[w.init], w.method || 'GET') : (w.method || 'GET');
      } else continue;
      const u = urlOf(urlNode, site.scopes);
      calls.push({ facts, site, client, method, ...u, url: u.url !== undefined ? (prefix + u.url).replace(/\/{2,}/g, '/') : undefined });
    }
  }

  let matched = 0;
  calls.forEach((c, i) => {
    const id = `call:${c.facts.file}:${c.site.line}:${i}`;
    const props = { file: c.facts.file, line: c.site.line, client: c.client, method: c.method, owner: c.site.owner };
    if (c.unresolved) {
      graph.node(id, 'http-call', { ...props, unresolved: c.unresolved, text: A.snippet(c.site.text, c.site.node, 100) });
      graph.unresolvedItem('http-call', c.facts.file, c.site.line, A.snippet(c.site.text, c.site.node, 100), c.unresolved);
    } else if (c.external) {
      graph.node(id, 'http-call', { ...props, external: c.external });
    } else {
      const hits = ctx.routes.filter((r) => methodMatches(r.method, c.method) && pathMatches(r.path, c.url));
      graph.node(id, 'http-call', { ...props, url: c.url, matches: hits.map((h) => h.id) });
      for (const h of hits) graph.edge('requests', id, h.id);
      if (hits.length) matched++;
      ctx.httpCalls.push({ id, file: c.facts.file, line: c.site.line, method: c.method, url: c.url, matches: hits.map((h) => h.id), test: !!(ctx.fileIndex.get(c.facts.file) || {}).test });
    }
    graph.edge('contains', `file:${c.facts.file}`, id);
    if (c.site.owner) graph.edge('makes', `fn:${c.site.owner}`, id);
  });
  graph.cover('boundary:http-calls', calls.length ? 'mapped' : 'not used', { calls: calls.length, matched });
}

function envRead(chain) {
  if (!chain.root) return null;
  if (chain.root.type === 'Identifier' && chain.root.name === 'process' && chain.path[0] === 'env') return chain.path[1] || null;
  if (chain.root.type === 'MetaProperty' && chain.path[0] === 'env') return chain.path[1] || null;
  return null;
}

module.exports = { httpAdapter, pathMatches, methodMatches };
