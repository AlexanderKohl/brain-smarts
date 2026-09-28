'use strict';
// Environment variables read through helper functions: a function that reads `env[name]` or
// `process.env[name]` with one of its parameters is a helper, and so is a function that passes its
// own parameter on to a helper (or loops over an array parameter and passes each item). Every call
// to a helper with a string literal in that position reads that variable:
//   readEnv('BASE_URL'), readEnvWithDeprecated('KEY', ['OLD_KEY']).
// Part of the code-map skill (canonical copy: /shared/skills/code-map/).

const A = require('./ast');
const { lookup } = require('./extract');

function envHelperReads(project) {
  const helpers = new Map(); // function id -> Set of positions: 0, 1 … or 'each:1' for an array of names
  const add = (id, pos) => {
    if (!helpers.has(id)) helpers.set(id, new Set());
    if (helpers.get(id).has(pos)) return false;
    helpers.get(id).add(pos);
    return true;
  };
  for (const facts of project.facts.values()) for (const r of facts.envParamReads || []) add(r.owner, r.index);
  if (!helpers.size) return [];

  // Calls whose target is known, with the facts they are in.
  const calls = [];
  for (const facts of project.facts.values()) {
    const fnNode = new Map(facts.functions.map((f) => [f.id, f.node]));
    for (const site of facts.callSites) {
      const target = project.callTarget(facts, site);
      if (target) calls.push({ facts, site, target, ownerNode: site.owner ? fnNode.get(site.owner) : null });
    }
  }
  // Parameters passed on: f(name) inside g(name), or for (const n of names) f(n).
  const forwards = [];
  for (const c of calls) {
    if (!c.ownerNode) continue;
    c.site.args.forEach((arg, i) => {
      const a = A.unwrap(arg);
      if (!a || a.type !== 'Identifier') return;
      const b = lookup(c.site.scopes, a.name);
      if (!b) return;
      if (b.kind === 'param' && b.param && b.param.fn === c.ownerNode) forwards.push({ from: c.target, i, to: c.site.owner, pos: b.param.index });
      else if (b.forOf && A.unwrap(b.forOf).type === 'Identifier') {
        const pb = lookup(c.site.scopes, A.unwrap(b.forOf).name);
        if (pb && pb.kind === 'param' && pb.param && pb.param.fn === c.ownerNode) forwards.push({ from: c.target, i, to: c.site.owner, pos: `each:${pb.param.index}` });
      }
    });
  }
  let changed = true;
  while (changed) {
    changed = false;
    for (const f of forwards) if (helpers.has(f.from) && helpers.get(f.from).has(f.i) && add(f.to, f.pos)) changed = true;
  }

  const reads = [];
  for (const c of calls) {
    const positions = helpers.get(c.target);
    if (!positions) continue;
    for (const pos of positions) {
      const each = typeof pos === 'string';
      const arg = A.unwrap(c.site.args[each ? Number(pos.slice(5)) : pos]);
      if (!arg) continue;
      const values = each ? (arg.type === 'ArrayExpression' ? arg.elements : []) : [arg];
      for (const v of values) {
        const name = v ? A.staticString(v) : null;
        // A name from a list is a retired fallback (readEnvWithDeprecated('KEY', ['OLD_KEY'])): it
        // counts as read for the unused report, but the env check does not require it in the example file.
        if (name && /^[A-Za-z_][A-Za-z0-9_]*$/.test(name)) reads.push({ file: c.facts.file, name, line: A.lineOf(v), owner: c.site.owner, via: each ? 'helper-list' : 'helper' });
      }
    }
  }
  return reads;
}

module.exports = { envHelperReads };
