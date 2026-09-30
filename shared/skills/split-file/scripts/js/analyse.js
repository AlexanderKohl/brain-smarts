#!/usr/bin/env node
'use strict';
// The structure of a CommonJS file, for drawing up a destination table before a split.
//
//   node analyse.js <file>                   each top-level statement: lines, names declared, and
//                                            the other top-level names it refers to
//   node analyse.js <file> --class Name      each member of one class: lines, kind, the top-level
//                                            names it refers to, and the this.x members it touches
//   node analyse.js <file> --graph [--flag RE]
//                                            the helpers (declarations that are not imports) in an
//                                            order where each comes after what it needs, with how
//                                            many others use each; names matching RE are marked *
//   node analyse.js <file> --range "start text" "end text"
//                                            the line range from the statement whose first line
//                                            starts with one text (with its leading comments) to
//                                            the end of the one starting with the other
// Add --json for machine-readable output. References are over-counted on purpose.
//
// Part of the split-file skill (canonical copy: /shared/skills/split-file/).

const A = require('./lib/ast');
const { parseArgs, fail, run } = require('./lib/args');

const USAGE = 'usage: node analyse.js <file> [--class Name | --graph [--flag RE] | --range START END] [--json]';

function topLevel(file) {
  const { text, lines } = A.readSource(file);
  const ast = A.parse(text, { recover: true });
  const stmts = A.statements(ast, text);
  const topNames = new Set(stmts.flatMap((s) => s.declares));
  return {
    ast,
    lines,
    stmts: stmts.map((s) => ({
      type: s.node.type,
      from: s.from,
      start: s.start,
      end: s.end,
      declares: s.declares,
      import: Boolean(s.req),
      refs: [...A.uses(s.node).read].filter((n) => topNames.has(n) && !s.declares.includes(n)).sort(),
      head: lines[s.start - 1].trim().slice(0, 90),
    })),
    topNames,
  };
}

function classMembers(ast, topNames, className) {
  const cls = ast.program.body.find((s) => s.type === 'ClassDeclaration' && s.id && s.id.name === className);
  if (!cls) throw new Error(`class ${className} is not declared at top level`);
  return cls.body.body.map((m) => {
    const u = A.uses(m);
    const from = m.leadingComments && m.leadingComments.length ? m.leadingComments[0].loc.start.line : m.loc.start.line;
    return {
      name: m.key && (m.key.name || m.key.value || (m.key.id && `#${m.key.id.name}`)),
      type: m.type,
      kind: m.kind || null,
      static: Boolean(m.static),
      from,
      end: m.loc.end.line,
      lines: m.loc.end.line - from + 1,
      refs: [...u.read].filter((n) => topNames.has(n)).sort(),
      thisMembers: [...u.thisMembers].sort(),
      usesSuper: u.usesSuper,
    };
  });
}

function graph(stmts, flag) {
  const helpers = stmts.filter((s) => s.declares.length && !s.import);
  const byName = new Map();
  for (const h of helpers) for (const n of h.declares) byName.set(n, h);
  const usedBy = new Map();
  for (const s of stmts) {
    for (const r of s.refs) {
      if (!byName.has(r) || byName.get(r) === s) continue;
      if (!usedBy.has(r)) usedBy.set(r, new Set());
      usedBy.get(r).add(s.declares[0] || `line ${s.start}`);
    }
  }
  const done = new Set();
  const order = [];
  const visit = (h, stack = new Set()) => {
    if (done.has(h) || stack.has(h)) return;
    stack.add(h);
    for (const r of h.refs) if (byName.has(r)) visit(byName.get(r), stack);
    done.add(h);
    order.push(h);
  };
  helpers.forEach((h) => visit(h));
  return order.map((h) => ({
    start: h.start,
    lines: h.end - h.start + 1,
    names: h.declares,
    flagged: Boolean(flag && flag.test(h.declares.join(','))),
    needs: h.refs.filter((r) => byName.has(r)),
    usedBy: [...(usedBy.get(h.declares[0]) || [])].sort(),
  }));
}

function range(stmts, lines, startText, endText) {
  const find = (t) => {
    const hits = stmts.filter((s) => lines[s.start - 1].trim().startsWith(t));
    if (hits.length !== 1) throw new Error(`${hits.length} statements start with ${JSON.stringify(t)}`);
    return hits[0];
  };
  const a = find(startText);
  const b = find(endText);
  if (b.end < a.from) throw new Error('the end statement comes before the start');
  return { from: a.from, to: b.end };
}

function main() {
  const { positional, options } = parseArgs(process.argv.slice(2), { flags: ['json', 'graph'], usage: USAGE });
  const [file] = positional;
  if (!file) fail('a file is required', USAGE);
  const { ast, lines, stmts, topNames } = topLevel(file);
  const print = (value, text) => console.log(options.json ? JSON.stringify(value, null, 1) : text(value));

  if (options.range !== undefined) {
    const r = range(stmts, lines, options.range, positional[1]);
    print(r, (v) => `${v.from}-${v.to}`);
  } else if (options.class) {
    print(classMembers(ast, topNames, options.class), (ms) => ms.map((m) => `${String(m.from).padStart(5)}-${String(m.end).padEnd(5)} ${String(m.lines).padStart(4)} ${m.type === 'ClassMethod' ? '' : `${m.type} `}${m.static ? 'static ' : ''}${m.kind && m.kind !== 'method' ? `${m.kind} ` : ''}${m.name}  <- ${m.refs.join(', ')}${m.thisMembers.length ? `  this.${m.thisMembers.join(', this.')}` : ''}`).join('\n'));
  } else if (options.graph) {
    const flag = options.flag ? new RegExp(options.flag, 'i') : null;
    print(graph(stmts, flag), (hs) => hs.map((h) => `${String(h.start).padStart(5)} ${String(h.lines).padStart(4)} ${h.flagged ? '*' : ' '} ${h.names.join(',')}  <- ${h.needs.join(', ')}  | used by ${h.usedBy.length}`).join('\n'));
  } else {
    print(stmts, (ss) => ss.map((s) => `${String(s.from).padStart(5)}-${String(s.end).padEnd(5)} ${s.type.padEnd(20)} ${s.declares.join(',') || '-'}  <- ${s.refs.join(', ')}`).join('\n'));
  }
}

run(main);
