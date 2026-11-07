#!/usr/bin/env node
'use strict';
// Moves whole top-level declarations out of a CommonJS file into a new module in the same folder,
// without editing them. The new module gets the imports its code uses, copied from the source; the
// source loads the moved names it still uses back from it, so it exports exactly what it did.
//
// An ES module (.mjs, or a .js file with import or export) is moved the same way, with ES module
// wiring: the new module (.mjs beside a .mjs) gets the source's import declarations, narrowed to the
// names its code uses; a moved `export function f` keeps its `export`, and a moved name the source
// still uses is exported with `export { … }`; the source imports the names it still uses back
// (`import { … } from './new.mjs'`) and re-exports the moved names it exported
// (`export { … } from './new.mjs'`), after its own imports.
//
// Refuses when the move could change behaviour:
// - the moved code needs a name that stays behind as something other than an import (the new
//   module would have to load the source: a cycle) – move that name too, or first;
// - the moved code uses module, exports, __filename, a top-level `this` or import.meta, which mean
//   something else in another file;
// - a name is an ES module's default export (`export default function f`), which stays;
// - a moved binding is assigned after it is declared, or moved code assigns a name that stays (the
//   loaded-back copy would not follow the assignment);
// - a moved variable's initial value runs code (it would now run when the new module is loaded),
//   unless --allow-load-order says that order does not matter;
// - a statement also declares names not asked for, or a name is not found.
//
// Part of the split-file skill (canonical copy: /shared/skills/split-file/).

const fs = require('fs');
const path = require('path');
const A = require('./lib/ast');
const { parseArgs, fail, run, movedFrom } = require('./lib/args');

const USAGE = 'usage: node move.js <source.js|source.mjs> --to <newModule> --names a,b,c [--header TEXT] [--ref TEXT] [--allow-load-order]';
const MARKER = '// Code moved unchanged into the modules required below is loaded back here, so this file\'s';
const ESM_MARKER = '// Code moved unchanged into the modules imported below is imported back here, so this file\'s';

function main() {
  const { positional, options } = parseArgs(process.argv.slice(2), { flags: ['allow-load-order'], usage: USAGE });
  const [sourceFile] = positional;
  if (!sourceFile || !options.to || !options.names) fail('source, --to and --names are required', USAGE);
  const moduleName = options.to.replace(/\.m?js$/, '');
  if (!/^[A-Za-z_$][\w$.-]*$/.test(moduleName)) throw new Error(`${moduleName} is not a plain module name`);
  const names = options.names.split(',').map((n) => n.trim()).filter(Boolean);
  const moduleFile = `${moduleName}${/\.mjs$/i.test(sourceFile) ? '.mjs' : '.js'}`;
  const target = path.join(path.dirname(sourceFile), moduleFile);
  if (fs.existsSync(target)) throw new Error(`${target} exists`);

  const { eol, text, lines } = A.readSource(sourceFile);
  const ast = A.parse(text, { file: sourceFile });
  const esm = ast.program.sourceType === 'module';
  const stmts = A.statements(ast, text);
  const strict = (ast.program.directives || []).some((d) => d.value.value === 'use strict');

  for (const s of stmts) if (names.includes(s.defaultName)) throw new Error(`${s.defaultName} (line ${s.start}) is the default export; it stays in the source`);
  const moving = stmts.filter((s) => s.declares.some((n) => names.includes(n)));
  for (const s of moving) {
    const extra = s.declares.filter((n) => !names.includes(n));
    if (extra.length) throw new Error(`the statement at line ${s.start} also declares ${extra.join(', ')}; name them too`);
  }
  const movedNames = new Set(moving.flatMap((s) => s.declares));
  const missing = names.filter((n) => !movedNames.has(n));
  if (missing.length) throw new Error(`not found at top level: ${missing.join(', ')}`);
  const staying = stmts.filter((s) => !moving.includes(s));
  const stayingNames = new Set(staying.flatMap((s) => s.declares));

  const problems = [];
  const needed = new Set();
  for (const s of moving) {
    const u = A.refs(s.node);
    for (const n of u.read) if (!movedNames.has(n)) needed.add(n);
    for (const n of A.fileBound(s.node)) problems.push(`line ${s.start} uses ${n}, which means something else in another file`);
    for (const n of u.assigned) if (stayingNames.has(n)) problems.push(`line ${s.start} assigns ${n}, which stays in the source`);
  }
  const { lines: importLines, behind } = A.importsFor(needed, stmts, moving);
  for (const b of behind) problems.push(`${b.name} (line ${b.line}) stays in the source; move it too, or first`);

  const stillUsed = new Set();
  const assignedAnywhere = new Set();
  for (const s of stmts) for (const n of A.refs(s.node).assigned) assignedAnywhere.add(n);
  for (const s of staying) for (const n of A.refs(s.node).read) if (movedNames.has(n)) stillUsed.add(n);
  for (const s of moving) {
    for (const n of s.declares) if (stillUsed.has(n) && assignedAnywhere.has(n)) problems.push(`${n} (line ${s.start}) is assigned after it is declared; a loaded-back copy would not follow`);
    const decl = A.unwrap(s.node);
    if (decl.type === 'VariableDeclaration' && !options['allow-load-order']) {
      const effects = decl.declarations.filter((d) => !A.isPure(d.init));
      if (effects.length) problems.push(`line ${s.start} runs code when loaded (${effects.map((d) => text.slice(d.init.start, d.init.end).split('\n')[0].slice(0, 60)).join('; ')}); it would run when the new module loads – check the order does not matter, then pass --allow-load-order`);
    }
  }
  // The moved names the source still uses (loaded or imported back), and, in an ES module, those it
  // exported itself (`export function f`), which it re-exports.
  const exportsList = moving.flatMap((s) => s.declares).filter((n) => stillUsed.has(n));
  const reexports = esm ? moving.filter((s) => s.exported).flatMap((s) => s.declares) : [];
  if (!exportsList.length && !reexports.length) problems.push(`nothing left in the source uses${esm ? ' or exports' : ''} the moved names; delete unused code rather than moving it`);
  if (problems.length) throw new Error(`\n  ${problems.join('\n  ')}`);

  const base = path.basename(sourceFile);
  const body = [];
  for (const s of moving) {
    if (body.length) body.push('');
    body.push(...lines.slice(s.from - 1, s.end));
  }
  // A moved `export function f` exports itself; the other names the source uses are exported here.
  const ownExports = exportsList.filter((n) => !reexports.includes(n));
  const moduleText = [
    ...(strict ? ["'use strict';"] : []),
    ...A.commentLines(options.header || `Split out of ${base}.`),
    ...A.commentLines(`${movedFrom(base, options.ref)} ${base} loads these names back, so its callers see the same names.`),
    ...importLines,
    '',
    ...body,
    '',
    ...(!esm ? [`module.exports = ${A.braceList(exportsList, 17)};`, ''] : ownExports.length ? [`export ${A.braceList(ownExports, 8)};`, ''] : []),
  ].join('\n');

  // Remove the moved statements, with their leading comments.
  const drop = A.dropRanges(lines, moving.map((s) => [s.from, s.end]));
  const after = A.backRequireLine(staying, movedNames);
  const insert = [];
  if (esm) {
    if (!text.includes(ESM_MARKER)) insert.push(ESM_MARKER, '// exports stay the same.');
    if (exportsList.length) insert.push(`import ${A.braceList(exportsList, 30)} from './${moduleFile}';`);
    if (reexports.length) insert.push(`export ${A.braceList(reexports, 30)} from './${moduleFile}';`);
  } else {
    if (!text.includes(MARKER)) insert.push(MARKER, '// exports stay the same.');
    insert.push(`const ${A.braceList(exportsList, 6)} = require('./${moduleName}');`);
  }
  const out = after === 0 ? [...insert] : [];
  lines.forEach((line, i) => {
    if (!drop.has(i + 1)) out.push(line);
    if (i + 1 === after) out.push(...insert);
  });
  const result = out.join('\n');

  A.writeText(target, moduleText, eol);
  A.writeText(sourceFile, result, eol);
  console.log(`${moduleFile}: ${A.countLines(moduleText)} lines, ${moving.length} statements, exports ${[...new Set([...exportsList, ...reexports])].join(', ')}; ${importLines.length} imports`);
  console.log(`${base}: now ${A.countLines(result)} lines`);
}

run(main);
