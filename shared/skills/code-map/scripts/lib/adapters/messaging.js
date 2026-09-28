'use strict';
// Messages between parts of one system: socket.io events (emit / on) and browser-extension
// messages (chrome.runtime.sendMessage with a `type`, and the listener that compares that type).
// Names come from literals or constants; anything else is unresolved. Part of the code-map skill
// (canonical copy: /shared/skills/code-map/).

const A = require('../js/ast');
const { lookup } = require('../js/extract');

const RESERVED = new Set(['connect', 'connection', 'disconnect', 'disconnecting', 'error', 'connect_error', 'reconnect',
  'reconnect_attempt', 'reconnect_error', 'reconnect_failed', 'ping', 'pong', 'newListener', 'removeListener']);
const SENDERS = [['chrome', 'runtime', 'sendMessage'], ['chrome', 'tabs', 'sendMessage'], ['browser', 'runtime', 'sendMessage'], ['browser', 'tabs', 'sendMessage']];
const LISTENERS = [['chrome', 'runtime', 'onMessage', 'addListener'], ['browser', 'runtime', 'onMessage', 'addListener'], ['chrome', 'runtime', 'onMessageExternal', 'addListener']];

const same = (a, b) => a.length === b.length && a.every((x, i) => x === b[i]);

function messagingAdapter(ctx) {
  const { project, graph } = ctx;
  let events = 0;
  let messages = 0;
  for (const facts of project.facts.values()) {
    const valueOf = project.valueAt(facts, null);
    const socketFile = facts.imports.some((i) => /^socket\.io(-client)?$/.test(i.source || ''));
    for (const site of facts.callSites) {
      const full = [site.rootName, ...site.path];
      // socket.io
      if (socketFile && site.path.length >= 1 && /^(emit|on|once|off)$/.test(site.path[site.path.length - 1]) && site.args[0]) {
        const name = project.valueOf(facts, site.args[0], site.scopes);
        if (name === null) { graph.unresolvedItem('event', facts.file, site.line, A.snippet(site.text, site.node), 'event name is not a constant'); continue; }
        if (RESERVED.has(name)) continue;
        const kind = site.path[site.path.length - 1] === 'emit' ? 'emits' : 'listens';
        if (site.path[site.path.length - 1] === 'off') continue;
        graph.node(`event:${name}`, 'event', { name, transport: 'socket.io' });
        graph.edge(kind, (site.owner ? `fn:${site.owner}` : `file:${facts.file}`), `event:${name}`, { file: facts.file, line: site.line });
        ctx.events.push({ name, kind, file: facts.file, line: site.line, transport: 'socket.io' });
        events++;
        continue;
      }
      // browser extension: send
      if (site.rootType === 'id' && !site.binding && SENDERS.some((s) => same(s, full))) {
        const obj = A.unwrap(site.args[full[1] === 'tabs' ? 1 : 0]);
        const type = obj && obj.type === 'ObjectExpression' ? obj.properties.find((p) => p.type === 'ObjectProperty' && A.keyName(p.key, p.computed) === 'type') : null;
        const name = type ? project.valueOf(facts, type.value, site.scopes) : null;
        if (name === null) { graph.unresolvedItem('message', facts.file, site.line, A.snippet(site.text, site.node), 'message type is not a constant'); continue; }
        graph.node(`message:${name}`, 'message', { name, transport: 'extension' });
        graph.edge('sends', (site.owner ? `fn:${site.owner}` : `file:${facts.file}`), `message:${name}`, { file: facts.file, line: site.line });
        ctx.events.push({ name, kind: 'emits', file: facts.file, line: site.line, transport: 'extension' });
        messages++;
        continue;
      }
      // browser extension: listen – the types the listener compares.
      if (site.rootType === 'id' && !site.binding && LISTENERS.some((s) => same(s, full)) && site.args[0]) {
        let fn = A.unwrap(site.args[0]);
        if (fn.type === 'Identifier') {
          const d = project.declaration(facts, fn.name, site.scopes);
          fn = d && d.node ? A.unwrap(d.node) : null;
        }
        if (!fn || !A.isFunction(fn)) continue;
        const bodies = [fn];
        const param = fn.params[0] && fn.params[0].type === 'Identifier' ? fn.params[0].name : null;
        // One level of delegation: handle(message) called with the listener's first parameter.
        if (param) A.walk(fn.body, (n) => {
          if (A.isCall(n) && n.callee.type === 'Identifier' && n.arguments.some((a) => a.type === 'Identifier' && a.name === param)) {
            const d = project.declaration(facts, n.callee.name, [facts.moduleScope]);
            const target = d && d.node ? A.unwrap(d.node) : null;
            if (target && A.isFunction(target)) bodies.push(target);
          }
        });
        for (const body of bodies) {
          for (const name of comparedTypes(body, (n) => valueOf(n))) {
            graph.node(`message:${name}`, 'message', { name, transport: 'extension' });
            graph.edge('handles-message', (site.owner ? `fn:${site.owner}` : `file:${facts.file}`), `message:${name}`, { file: facts.file, line: site.line });
            ctx.events.push({ name, kind: 'listens', file: facts.file, line: site.line, transport: 'extension' });
            messages++;
          }
        }
      }
    }
  }
  graph.cover('boundary:events', events ? 'mapped' : 'not used', { events });
  graph.cover('boundary:extension-messages', messages ? 'mapped' : 'not used', { messages });
}

// Values compared with `<x>.type` / `<x>['type']` inside a function: ===, ==, switch cases.
function comparedTypes(fn, valueOf) {
  const out = new Set();
  const isType = (n) => {
    n = A.unwrap(n);
    return A.isMember(n) && A.keyName(n.property, n.computed) === 'type';
  };
  A.walk(fn.body || fn, (n) => {
    if (n.type === 'BinaryExpression' && /^(===|==)$/.test(n.operator)) {
      const other = isType(n.left) ? n.right : isType(n.right) ? n.left : null;
      const v = other ? (A.staticString(other) ?? valueOf(other)) : null;
      if (v !== null && v !== undefined) out.add(v);
    }
    if (n.type === 'SwitchStatement' && isType(n.discriminant)) {
      for (const c of n.cases) if (c.test) { const v = A.staticString(c.test) ?? valueOf(c.test); if (v !== null && v !== undefined) out.add(v); }
    }
  });
  return out;
}

module.exports = { messagingAdapter };
