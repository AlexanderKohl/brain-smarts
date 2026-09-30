#!/usr/bin/env node
'use strict';
// Moves whole methods of one class, unedited, into a new module in the same folder: a class of the
// same methods, whose descriptors the original class takes back onto its prototype. Callers, tests
// and instanceof see the same class; each method keeps its text, name, length and non-enumerable
// descriptor. The new module gets the imports its methods use, copied from the source.
//
// Refuses constructors, static, computed, private, getter and setter members, methods using super,
// names defined twice, methods using module, exports or __filename, and methods that need a name
// staying in the source as something other than an import (a cycle).
//
// Part of the split-file skill (canonical copy: /shared/skills/split-file/).

const fs = require('fs');
const path = require('path');
const A = require('./lib/ast');
const { parseArgs, fail, run, movedFrom } = require('./lib/args');

const USAGE = 'usage: node move-methods.js <source.js> --class <ClassName> --to <newModule> --methods m1,m2 [--header TEXT] [--ref TEXT]';
const LOOP_START = 'for (const Methods of [';

function main() {
  const { positional, options } = parseArgs(process.argv.slice(2), { usage: USAGE });
  const [sourceFile] = positional;
  const className = options.class;
  if (!sourceFile || !className || !options.to || !options.methods) fail('source, --class, --to and --methods are required', USAGE);
  const moduleName = options.to.replace(/\.js$/, '');
  if (!/^[A-Za-z_$][\w$.-]*$/.test(moduleName)) throw new Error(`${moduleName} is not a plain module name`);
  const names = options.methods.split(',').map((n) => n.trim()).filter(Boolean);
  const target = path.join(path.dirname(sourceFile), `${moduleName}.js`);
  if (fs.existsSync(target)) throw new Error(`${target} exists`);

  const { eol, text, lines } = A.readSource(sourceFile);
  const ast = A.parse(text);
  const stmts = A.statements(ast, text);
  const strict = (ast.program.directives || []).some((d) => d.value.value === 'use strict');
  const clsStmt = stmts.find((s) => s.node.type === 'ClassDeclaration' && s.node.id && s.node.id.name === className);
  if (!clsStmt) throw new Error(`class ${className} is not declared at top level`);
  const cls = clsStmt.node;
  const memberName = (m) => (m.key && !m.computed && m.key.type !== 'PrivateName' ? (m.key.name || m.key.value) : null);
  const counts = new Map();
  for (const m of cls.body.body) counts.set(memberName(m), (counts.get(memberName(m)) || 0) + 1);

  const problems = [];
  const moving = [];
  for (const name of names) {
    const m = cls.body.body.find((x) => memberName(x) === name);
    if (!m) { problems.push(`method ${name} not found in ${className}`); continue; }
    if (m.type !== 'ClassMethod' || m.kind !== 'method' || m.static || m.computed) { problems.push(`${name} is not a plain method`); continue; }
    if (counts.get(name) > 1) { problems.push(`${name} is defined more than once`); continue; }
    const u = A.uses(m);
    if (u.usesSuper) problems.push(`${name} uses super`);
    for (const n of A.fileBound(m)) if (n !== 'this') problems.push(`${name} uses ${n}, which means something else in another file`);
    if (A.usesPrivate(m)) problems.push(`${name} uses a private member`);
    const from = m.leadingComments && m.leadingComments.length ? m.leadingComments[0].loc.start.line : m.loc.start.line;
    moving.push({ name, node: m, from, end: m.loc.end.line, read: u.read });
  }
  moving.sort((a, b) => a.from - b.from);

  const needed = new Set();
  for (const m of moving) for (const n of m.read) needed.add(n);
  needed.delete(className); // the class itself: `this.constructor` would be the holder, so refuse below
  const { lines: importLines, behind } = A.importsFor(needed, stmts, []);
  for (const b of behind) problems.push(`${b.name} (line ${b.line}) stays in the source; a method using it cannot move`);
  for (const m of moving) if (m.read.has(className)) problems.push(`${m.name} refers to ${className} by name, which stays in the source`);
  if (problems.length) throw new Error(`\n  ${problems.join('\n  ')}`);

  const holder = moduleName.charAt(0).toUpperCase() + moduleName.slice(1).replace(/[^\w$]/g, '_');
  const body = [];
  for (const m of moving) {
    if (body.length) body.push('');
    body.push(...lines.slice(m.from - 1, m.end));
  }
  const base = path.basename(sourceFile);
  const moduleText = [
    ...(strict ? ["'use strict';"] : []),
    `// ${options.header || `Methods of ${className}, split out of ${base}.`}`,
    `// ${movedFrom(base, options.ref)} ${className} takes these methods back onto its prototype with`,
    '// their descriptors, so callers see the same class.',
    ...importLines,
    '',
    `class ${holder} {`,
    ...body,
    '}',
    '',
    `module.exports = ${holder};`,
    '',
  ].join('\n');

  const drop = new Set();
  for (const m of moving) {
    for (let l = m.from; l <= m.end; l += 1) drop.add(l);
    if (lines[m.end] !== undefined && lines[m.end].trim() === '') drop.add(m.end + 1);
  }
  const requireLine = `  require('./${moduleName}'),`;
  // A loop from an earlier move: the new module joins its list.
  const loopAt = lines.findIndex((l, i) => i >= cls.loc.end.line && l === LOOP_START);
  const listEnd = loopAt >= 0 ? lines.findIndex((l, i) => i > loopAt && l === ']) {') : -1;
  const out = [];
  lines.forEach((line, i) => {
    if (i === listEnd) out.push(requireLine);
    if (!drop.has(i + 1)) out.push(line);
    if (i + 1 === cls.loc.end.line && loopAt < 0) {
      out.push(
        '',
        `// Methods moved unchanged into the modules below. Each module is a class whose methods are copied`,
        `// onto ${className}.prototype with their descriptors, so callers, tests and instanceof see the same class.`,
        LOOP_START,
        requireLine,
        ']) {',
        '  for (const [name, descriptor] of Object.entries(Object.getOwnPropertyDescriptors(Methods.prototype))) {',
        `    if (name !== 'constructor') Object.defineProperty(${className}.prototype, name, descriptor);`,
        '  }',
        '}',
      );
    }
  });
  if (loopAt >= 0 && listEnd < 0) throw new Error('the method loop from an earlier move has no closing "]) {" line');
  const result = out.join('\n');

  A.writeText(target, moduleText, eol);
  A.writeText(sourceFile, result, eol);
  console.log(`${moduleName}.js: ${moduleText.split('\n').length - 1} lines, ${moving.length} methods, ${importLines.length} imports`);
  console.log(`${base}: now ${result.split('\n').length} lines`);
}

run(main);
