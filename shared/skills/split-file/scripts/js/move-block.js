#!/usr/bin/env node
'use strict';
// Moves a contiguous run of whole top-level statements (route registrations, and the helpers only
// they use) out of a CommonJS file, unedited, into the body of a `register…(router, deps)` function
// in a new module in the same folder. The source calls it where the run was, so routes and
// middleware register on the same router in the same order.
//
// The new module imports nothing: every top-level name of the source the moved code uses is passed
// in `deps` at the call, so the moved code sees the very bindings it saw before (a test that reloads
// the source with different stand-ins gets them too).
//
// Declarations in the run that code outside it uses stay where they are, and the call goes after
// the last of them, so each is set before it is passed in. A declaration kept this way must have an
// initial value with no effects, so running it before the moved code changes nothing.
//
// Refuses when: the range cuts a statement; a kept declaration's value runs code; a dependency is a
// `let`/`var` that is assigned anywhere (its value would be frozen at the call); a dependency is a
// `const`/`let`/class declared after the call (read before it is set); the moved code uses module,
// exports, __filename or a top-level `this`.
//
// Part of the split-file skill (canonical copy: /shared/skills/split-file/).

const fs = require('fs');
const path = require('path');
const A = require('./lib/ast');
const { parseArgs, fail, run, movedFrom } = require('./lib/args');

const USAGE = 'usage: node move-block.js <source.js> --to <newModule> --register <functionName> --lines FROM-TO [--receiver router] [--header TEXT] [--ref TEXT]';

function main() {
  const { positional, options } = parseArgs(process.argv.slice(2), { usage: USAGE });
  const [sourceFile] = positional;
  const registerName = options.register;
  const receiver = options.receiver || 'router';
  const m = /^(\d+)-(\d+)$/.exec(options.lines || '');
  if (!sourceFile || !options.to || !registerName || !m) fail('source, --to, --register and --lines FROM-TO are required', USAGE);
  const from = Number(m[1]);
  const to = Number(m[2]);
  const moduleName = options.to.replace(/\.js$/, '');
  if (!/^[A-Za-z_$][\w$.-]*$/.test(moduleName)) throw new Error(`${moduleName} is not a plain module name`);
  const target = path.join(path.dirname(sourceFile), `${moduleName}.js`);
  if (fs.existsSync(target)) throw new Error(`${target} exists`);

  const { eol, text, lines } = A.readSource(sourceFile);
  const ast = A.parse(text);
  const stmts = A.statements(ast, text);
  const strict = (ast.program.directives || []).some((d) => d.value.value === 'use strict');

  const inRange = (s) => s.start >= from && s.end <= to;
  const moving = stmts.filter(inRange);
  if (!moving.length) throw new Error('no whole statement in the range');
  const partial = stmts.filter((s) => !inRange(s) && s.end >= from && s.start <= to);
  if (partial.length) throw new Error(`the range cuts statements at lines ${partial.map((s) => `${s.start}-${s.end}`).join(', ')}`);

  // Keep declarations that code outside the run uses; repeated, since a kept declaration may use
  // another in the run.
  for (let changed = true; changed;) {
    changed = false;
    const outsideReads = new Set();
    for (const s of stmts) if (!moving.includes(s)) for (const n of A.uses(s.node).read) outsideReads.add(n);
    for (const s of [...moving]) {
      if (s.kind && s.declares.some((n) => outsideReads.has(n))) { moving.splice(moving.indexOf(s), 1); changed = true; }
    }
  }
  const kept = stmts.filter((s) => !moving.includes(s) && inRange(s));
  const problems = [];
  for (const s of kept) {
    if (s.node.type === 'VariableDeclaration' && !s.node.declarations.every((d) => A.isPure(d.init))) {
      problems.push(`line ${s.start} is used outside the run but its value runs code; it cannot stay behind`);
    }
  }
  if (!moving.length) throw new Error('nothing left to move: everything in the run is used outside it');
  const staying = stmts.filter((s) => !moving.includes(s));
  const firstMoved = moving[0];
  const lastKept = kept.reduce((a, s) => Math.max(a, s.end), 0);
  const callAfter = lastKept > firstMoved.from ? lastKept : firstMoved.from - 1; // the call goes after this line

  const movedNames = new Set(moving.flatMap((s) => s.declares));
  for (const s of moving) for (const n of A.fileBound(s.node)) if (!movedNames.has(n)) problems.push(`line ${s.start} uses ${n}, which means something else in another file`);
  const declaredAt = new Map();
  for (const s of staying) for (const n of s.declares) declaredAt.set(n, s);
  const assignedAnywhere = new Set();
  for (const s of stmts) for (const n of A.uses(s.node).assigned) assignedAnywhere.add(n);
  const deps = new Set();
  for (const s of moving) for (const n of A.uses(s.node).read) if (declaredAt.has(n) && !movedNames.has(n)) deps.add(n);
  if (!declaredAt.has(receiver)) problems.push(`${receiver} is not declared at the top level of the source`);
  for (const n of deps) {
    const s = declaredAt.get(n);
    if ((s.kind === 'let' || s.kind === 'var') && assignedAnywhere.has(n)) problems.push(`${n} (line ${s.start}) is reassigned; passing it would freeze its value`);
    if ((s.kind === 'const' || s.kind === 'let' || s.kind === 'class') && s.start > callAfter) problems.push(`${n} is declared at line ${s.start}, after the call`);
  }
  deps.delete(receiver); // passed as the first argument
  if (problems.length) throw new Error(`\n  ${problems.join('\n  ')}`);

  const depList = [...deps].sort((a, b) => declaredAt.get(a).start - declaredAt.get(b).start || a.localeCompare(b));
  // The moved statements in order; where none was kept between two, the text between them
  // (blank lines, comments) comes too.
  const keptBetween = (a, b) => kept.some((k) => k.start > a.end && k.end < b.start);
  const body = [];
  moving.forEach((s, i) => {
    if (i > 0) {
      const prev = moving[i - 1];
      if (keptBetween(prev, s)) body.push(''); else body.push(...lines.slice(prev.end, s.from - 1));
    }
    body.push(...lines.slice(s.from - 1, s.end));
  });
  const base = path.basename(sourceFile);
  const moduleText = [
    ...(strict ? ["'use strict';"] : []),
    `// ${options.header || `Routes split out of ${base}.`}`,
    `// ${movedFrom(base, options.ref)} ${base} calls ${registerName} where this code was, on the same`,
    `// ${receiver}, so everything registers in the same order; every name the code uses from ${base} is`,
    '// passed in, so it sees the same values as before.',
    '',
    `function ${registerName}(${receiver}, ${A.braceList(depList, 12 + registerName.length + receiver.length)}) {`,
    ...body,
    '}',
    '',
    `module.exports = { ${registerName} };`,
    '',
  ].join('\n');

  const call = `${registerName}(${receiver}, ${A.braceList(depList, registerName.length + receiver.length + 4)});`.split('\n');
  const requireLine = `const { ${registerName} } = require('./${moduleName}');`;
  const drop = new Set();
  moving.forEach((s, i) => {
    for (let l = s.from; l <= s.end; l += 1) drop.add(l);
    const next = moving[i + 1];
    if (next && !keptBetween(s, next)) for (let l = s.end + 1; l < next.from; l += 1) drop.add(l);
    else if (lines[s.end] !== undefined && lines[s.end].trim() === '') drop.add(s.end + 1);
  });
  // The module is required with the source's other imports: after the last top-level require
  // before the run.
  let lastRequire = 0;
  for (const s of staying) if (s.req && s.end < firstMoved.from) lastRequire = Math.max(lastRequire, s.end);
  const out = lastRequire === 0 ? [requireLine] : [];
  lines.forEach((line, i) => {
    const n = i + 1;
    if (n === callAfter + 1 && callAfter === firstMoved.from - 1) out.push(...call);
    if (!drop.has(n)) out.push(line);
    if (n === lastRequire) out.push(requireLine);
    if (n === callAfter && callAfter !== firstMoved.from - 1) out.push('', ...call);
  });
  const result = out.join('\n');

  A.writeText(target, moduleText, eol);
  A.writeText(sourceFile, result, eol);
  console.log(`${moduleName}.js: ${A.countLines(moduleText)} lines, ${moving.length} statements (${firstMoved.from}-${moving[moving.length - 1].end}), ${depList.length} deps; kept in place: ${kept.map((k) => k.declares[0]).join(', ') || 'none'}`);
  console.log(`${base}: now ${A.countLines(result)} lines`);
}

run(main);
