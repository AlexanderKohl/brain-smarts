'use strict';
// Next.js: pages become UI routes and route handlers become HTTP routes, by Next's own folder rules
// (route groups, dynamic and catch-all segments), under the app's basePath. Part of the code-map
// skill (canonical copy: /shared/skills/code-map/).

const path = require('path');
const A = require('../js/ast');
const { joinPath } = require('./express');

const METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'];
const PAGE = /^page\.(js|jsx|ts|tsx|mdx)$/;
const ROUTE = /^route\.(js|ts)$/;

// Folder segments -> URL path; null when the folder is not routable (private, intercepting).
function segmentsToPath(parts) {
  const out = [];
  for (const seg of parts) {
    if (!seg) continue;
    if (/^\(\.{1,3}\)/.test(seg) || seg.startsWith('_')) return null;
    if (/^\(.*\)$/.test(seg) || seg.startsWith('@')) continue;
    let m;
    if ((m = /^\[\[\.\.\.(.+)\]\]$/.exec(seg))) out.push(`:${m[1]}*?`);
    else if ((m = /^\[\.\.\.(.+)\]$/.exec(seg))) out.push(`:${m[1]}*`);
    else if ((m = /^\[(.+)\]$/.exec(seg))) out.push(`:${m[1]}`);
    else out.push(seg);
  }
  return `/${out.join('/')}`;
}

function nextApps(ctx) {
  const declared = (ctx.config.next || []).map((a) => ({ ...a, root: (a.root || '').replace(/\/$/, ''), declared: true }));
  const found = ctx.files.filter((e) => /(^|\/)next\.config\.(js|mjs|cjs|ts|mts)$/.test(e.file))
    .map((e) => ({ root: path.posix.dirname(e.file) === '.' ? '' : path.posix.dirname(e.file), configFile: e.file }));
  const apps = [...declared];
  for (const f of found) {
    const d = apps.find((a) => a.root === f.root);
    if (d) d.configFile = d.configFile || f.configFile; else apps.push(f);
  }
  return apps;
}

function basePathOf(ctx, app) {
  if (app.basePath !== undefined) return app.basePath;
  const facts = app.configFile && ctx.project.facts.get(app.configFile);
  if (!facts) return '';
  let value = '';
  for (const program of facts.programs) {
    A.walk(program, (node) => {
      if (node.type === 'ObjectProperty' && A.keyName(node.key, node.computed) === 'basePath') {
        const v = ctx.project.valueOf(facts, node.value, [facts.moduleScope]);
        if (v !== null) value = v;
        else ctx.graph.unresolvedItem('next-basepath', facts.file, A.lineOf(node), 'basePath', 'basePath is not a constant; declare it in code-map.config.json');
        return false;
      }
    });
  }
  return value;
}

function nextAdapter(ctx) {
  const { graph, project } = ctx;
  const apps = nextApps(ctx);
  let pages = 0;
  let handlers = 0;
  for (const app of apps) {
    const base = basePathOf(ctx, app);
    const prefix = app.root ? `${app.root}/` : '';
    const appDirs = [`${prefix}src/app/`, `${prefix}app/`];
    const pagesDirs = [`${prefix}src/pages/`, `${prefix}pages/`];
    for (const entry of ctx.files) {
      const appDir = appDirs.find((d) => entry.file.startsWith(d));
      const pagesDir = !appDir && pagesDirs.find((d) => entry.file.startsWith(d));
      if (!appDir && !pagesDir) continue;
      const rel = entry.file.slice((appDir || pagesDir).length);
      const parts = rel.split('/');
      const name = parts.pop();
      if (appDir) {
        if (PAGE.test(name)) {
          const p = segmentsToPath(parts);
          if (p === null) continue;
          addUiRoute(ctx, joinPath(base, p), entry.file, entry.file, 'next');
          pages++;
        } else if (ROUTE.test(name)) {
          const p = segmentsToPath(parts);
          if (p === null) continue;
          const facts = project.facts.get(entry.file);
          if (!facts) continue;
          for (const method of METHODS) {
            if (!facts.exports.named.has(method)) continue;
            const full = joinPath(base, p);
            const fn = facts.functionsByName.get(method);
            addRoute(ctx, method, full, entry.file, fn ? fn.line : null, fn ? fn.id : null, 'next');
            handlers++;
          }
        }
      } else if (/\.(js|jsx|ts|tsx)$/.test(name) && !/^_(app|document|error)\./.test(name)) {
        const stem = name.replace(/\.(js|jsx|ts|tsx)$/, '');
        const segs = stem === 'index' ? parts : [...parts, stem];
        const p = segmentsToPath(segs);
        if (p === null) continue;
        if (parts[0] === 'api') {
          const facts = project.facts.get(entry.file);
          const fn = facts && facts.functionsByName.get('default');
          addRoute(ctx, 'ALL', joinPath(base, p), entry.file, fn ? fn.line : null, fn ? fn.id : null, 'next');
          handlers++;
        } else {
          addUiRoute(ctx, joinPath(base, p), entry.file, entry.file, 'next');
          pages++;
        }
      }
    }
  }
  graph.cover('framework:next', apps.length ? 'mapped' : 'not used', { apps: apps.length, pages, handlers });
}

function addRoute(ctx, method, full, file, line, handler, framework) {
  const id = ctx.graph.nodes.has(`route:${method} ${full}`) ? `route:${method} ${full} @${file}` : `route:${method} ${full}`;
  ctx.graph.node(id, 'route', { method, path: full, localPath: full, file, line, framework });
  ctx.graph.edge('contains', `file:${file}`, id);
  if (handler) ctx.graph.edge('handles', id, handler.startsWith('fn:') ? handler : `fn:${handler}`);
  ctx.routes.push({ method, path: full, id, file, line, framework });
}

function addUiRoute(ctx, full, component, file, framework, line = null) {
  const id = ctx.graph.nodes.has(`ui:${full}`) ? `ui:${full} @${file}` : `ui:${full}`;
  ctx.graph.node(id, 'ui-route', { path: full, component, file, line, framework });
  ctx.graph.edge('contains', `file:${file}`, id);
  if (component) ctx.graph.edge('shows', id, `file:${component}`);
  ctx.uiRoutes.push({ path: full, component, file, framework, id });
}

module.exports = { nextAdapter, addRoute, addUiRoute, segmentsToPath };
