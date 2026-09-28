'use strict';
// UI routers declared in code: vue-router's route tables and React Router's routes (JSX and object
// form). Each route links to the component file it shows. Part of the code-map skill
// (canonical copy: /shared/skills/code-map/).

const A = require('../js/ast');
const { lookup } = require('../js/extract');
const { joinPath } = require('./express');
const { addUiRoute } = require('./next');

const REACT_ROUTER = new Set(['react-router', 'react-router-dom']);
const ROUTER_FACTORIES = new Set(['createBrowserRouter', 'createHashRouter', 'createMemoryRouter', 'useRoutes']);

function packageOf(project, facts, b) {
  const t = b && b.import ? project.bindingTarget(facts, b) : null;
  return t && t.package ? t : null;
}

// The component file an expression names: an imported component, a lazy import(), a JSX element.
function componentFile(project, facts, node, scopes) {
  node = A.unwrap(node);
  if (!node) return null;
  if (node.type === 'JSXElement') {
    const n = node.openingElement.name;
    return n.type === 'JSXIdentifier' ? componentFile(project, facts, { type: 'Identifier', name: n.name }, scopes) : null;
  }
  if (node.type === 'Identifier') {
    const b = lookup(scopes || [facts.moduleScope], node.name);
    if (b && b.import) {
      const t = project.bindingTarget(facts, b);
      return t && t.file ? t.file : null;
    }
    if (b && b.init) return componentFile(project, facts, b.init, scopes);
    return null;
  }
  if (A.isFunction(node)) {
    let found = null;
    A.walk(node.body, (n) => {
      if (found) return false;
      if (A.isCall(n) && A.unwrap(n.callee).type === 'Import') {
        const spec = A.staticString(n.arguments[0]);
        const r = spec !== null ? project.target(facts.file, spec) : null;
        found = r && r.file ? r.file : null;
        return false;
      }
    });
    return found;
  }
  if (A.isCall(node) && node.arguments[0]) {
    // lazy(() => import('./X')), defineAsyncComponent(() => import('./X'))
    return componentFile(project, facts, node.arguments[0], scopes);
  }
  return null;
}

function routeArray(project, facts, node, scopes) {
  node = A.unwrap(node);
  if (!node) return null;
  if (node.type === 'ArrayExpression') return { facts, node };
  if (node.type === 'Identifier') {
    const d = project.declaration(facts, node.name, scopes);
    const init = d && d.node ? A.unwrap(d.node) : null;
    if (init && init.type === 'ArrayExpression') return { facts: d.facts, node: init };
  }
  return null;
}

function objectRoutes(ctx, facts, arrayNode, base, framework, file) {
  let count = 0;
  for (const el of arrayNode.elements) {
    const obj = A.unwrap(el);
    if (!obj || obj.type !== 'ObjectExpression') continue;
    const props = new Map();
    for (const p of obj.properties) if (p.type === 'ObjectProperty' || p.type === 'ObjectMethod') props.set(A.keyName(p.key, p.computed), p.type === 'ObjectMethod' ? p : p.value);
    const rawPath = props.has('path') ? ctx.project.valueOf(facts, props.get('path'), [facts.moduleScope]) : props.get('index') ? '' : null;
    const full = rawPath === null ? base : rawPath.startsWith('/') ? joinPath('', rawPath) : joinPath(base, rawPath);
    const compNode = props.get('component') || props.get('element') || props.get('Component') || props.get('lazy')
      || (props.get('components') && A.unwrap(props.get('components')).type === 'ObjectExpression'
        ? (A.unwrap(props.get('components')).properties.find((p) => A.keyName(p.key, p.computed) === 'default') || {}).value : null);
    if (rawPath !== null) {
      const component = compNode ? componentFile(ctx.project, facts, compNode) : null;
      addUiRoute(ctx, full, component, file, framework, A.lineOf(obj));
      if (compNode && !component && !props.has('redirect')) ctx.graph.unresolvedItem('ui-component', file, A.lineOf(obj), A.snippet('', compNode), 'component is not an import this map can follow');
      count++;
    }
    const kids = props.get('children') ? routeArray(ctx.project, facts, props.get('children')) : null;
    if (kids) count += objectRoutes(ctx, kids.facts, kids.node, full, framework, file);
  }
  return count;
}

function uiRoutesAdapter(ctx) {
  const { project } = ctx;
  let vue = 0;
  let react = 0;
  for (const facts of project.facts.values()) {
    for (const site of [...facts.callSites, ...facts.newSites]) {
      if (site.rootType !== 'id' || site.path.length !== 0) continue;
      const pkg = packageOf(project, facts, site.binding);
      if (!pkg) continue;
      const imported = pkg.member || pkg.imported;
      if (pkg.package === 'vue-router' && (imported === 'createRouter' || imported === 'default')) {
        const opts = site.args[0] && A.unwrap(site.args[0]);
        if (!opts || opts.type !== 'ObjectExpression') continue;
        const routesProp = opts.properties.find((p) => p.type === 'ObjectProperty' && A.keyName(p.key, p.computed) === 'routes');
        const arr = routesProp ? routeArray(project, facts, routesProp.value, site.scopes) : null;
        if (arr) vue += objectRoutes(ctx, arr.facts, arr.node, '', 'vue-router', facts.file);
      } else if (REACT_ROUTER.has(pkg.package) && ROUTER_FACTORIES.has(imported)) {
        const arr = site.args[0] ? routeArray(project, facts, site.args[0], site.scopes) : null;
        if (arr) react += objectRoutes(ctx, arr.facts, arr.node, '', 'react-router', facts.file);
      }
    }
    for (const jsx of facts.jsx) {
      if (jsx.name !== 'Route') continue;
      const b = lookup([facts.moduleScope], 'Route');
      const pkg = packageOf(project, facts, b);
      if (!pkg || !REACT_ROUTER.has(pkg.package)) continue;
      let full = '';
      const chain = [];
      for (let r = jsx; r; r = r.parent) chain.unshift(r);
      for (const r of chain) {
        const p = r.attrs.path ? project.valueOf(facts, r.attrs.path, [facts.moduleScope]) : '';
        if (p === null) { full = null; break; }
        full = p.startsWith('/') ? joinPath('', p) : joinPath(full, p);
      }
      if (full === null) { ctx.graph.unresolvedItem('ui-route', facts.file, jsx.line, 'Route', 'route path is not a literal'); continue; }
      if (!jsx.attrs.path && !jsx.attrs.index) continue;
      const compNode = jsx.attrs.element || jsx.attrs.Component || jsx.attrs.component;
      addUiRoute(ctx, full, compNode ? componentFile(project, facts, compNode) : null, facts.file, 'react-router', jsx.line);
      react++;
    }
  }
  ctx.graph.cover('framework:vue-router', vue ? 'mapped' : 'not used', { routes: vue });
  ctx.graph.cover('framework:react-router', react ? 'mapped' : 'not used', { routes: react });
}

module.exports = { uiRoutesAdapter };
