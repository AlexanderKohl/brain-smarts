'use strict';
// The JavaScript split tools on a fictional ES module app (tests/fixtures/esm-app): a move out of a
// .mjs file keeps its imports as import declarations, narrowed, keeps the module's named exports by
// re-exporting moved names, and keeps the app's shape and behaviour; the refusals fire for what an ES
// module adds (import.meta, a default export). Up to 0.2.1 every tool refused a .mjs file at its
// first import with "'import' and 'export' may appear only with 'sourceType: "module"'" (run
// RUN-20261015-062856), which is the failure the first test guards against.

const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

const TOOLS = path.join(__dirname, '..', '..', 'scripts', 'js');
const FIXTURE = path.join(__dirname, '..', 'fixtures', 'esm-app');
const SOURCE_TYPE_REFUSAL = /'import' and 'export' may appear only with 'sourceType: "module"'/;

// A copy of the fixture app with LF line endings, whatever the checkout wrote.
function copyApp() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'split-esm-'));
  fs.cpSync(FIXTURE, dir, { recursive: true });
  for (const file of fs.readdirSync(path.join(dir, 'src'))) {
    const full = path.join(dir, 'src', file);
    fs.writeFileSync(full, fs.readFileSync(full, 'utf8').replace(/\r\n/g, '\n'));
  }
  return dir;
}

function tool(name, args, cwd) {
  const r = spawnSync(process.execPath, [path.join(TOOLS, name), ...args], { cwd, encoding: 'utf8' });
  return { code: r.status, out: r.stdout, err: r.stderr };
}

const shape = (dir, extra = []) => tool('shape.js', ['--root', dir, '--modules', 'src/seeds.mjs', ...extra], dir);
const read = (dir, file) => fs.readFileSync(path.join(dir, file), 'utf8');

// What the rest of the program sees: main.mjs imports the seed module's names and prints results.
function behaviour(dir) {
  const r = spawnSync(process.execPath, ['src/main.mjs'], { cwd: dir, encoding: 'utf8' });
  assert.strictEqual(r.status, 0, r.stderr);
  return r.stdout;
}

const MOVE = ['src/seeds.mjs', '--to', 'seedText', '--names', 'seedLabel,packetGrams,sowingMonths', '--ref', 'TASK-0000-0003'];

test('move.js reads an ES module instead of refusing it at the first import', () => {
  const dir = copyApp();
  const r = tool('move.js', MOVE, dir);
  assert.doesNotMatch(r.err, SOURCE_TYPE_REFUSAL);
  assert.strictEqual(r.code, 0, r.err);
});

test('move.js moves ES module declarations unchanged, and the shape and behaviour stay the same', () => {
  const dir = copyApp();
  const before = path.join(dir, 'before.json');
  assert.strictEqual(shape(dir, ['--out', before]).code, 0);
  const was = behaviour(dir);
  const original = read(dir, 'src/seeds.mjs');
  const r = tool('move.js', MOVE, dir);
  assert.strictEqual(r.code, 0, r.err);

  const moved = read(dir, 'src/seedText.mjs');
  // Lines 9-21: packetGrams with its comment, seedLabel with its comment, sowingMonths.
  assert.ok(moved.includes(original.split('\n').slice(8, 21).join('\n')), 'lines 9-21 were not moved unchanged');
  assert.doesNotMatch(moved, /use strict|require\(/);
  assert.match(moved, /Moved unchanged from seeds\.mjs \(TASK-0000-0003\)/);
  // Imports copied as import declarations, narrowed to the names used, alias and attributes kept.
  assert.match(moved, /^import \{ tidyLabel as cleanLabel, LABEL_WIDTH \} from '\.\/labels\.mjs';$/m);
  assert.match(moved, /^import \* as units from '\.\/units\.mjs';$/m);
  assert.match(moved, /^import catalogue from '\.\/catalogue\.json' with \{ type: 'json' \};$/m);
  assert.doesNotMatch(moved, /titleCase/);
  // packetGrams was not exported but stays in use; seedLabel and sowingMonths keep their own export.
  assert.match(moved, /^export \{ packetGrams \};$/m);

  const source = read(dir, 'src/seeds.mjs');
  assert.match(source, /^import \{ packetGrams \} from '\.\/seedText\.mjs';$/m);
  assert.match(source, /^export \{ seedLabel, sowingMonths \} from '\.\/seedText\.mjs';$/m);
  // The wiring goes after the source's own imports, which stay as they were.
  assert.match(source, /with \{ type: 'json' \};\n\/\/ Code moved unchanged into the modules imported below/);
  assert.match(source, /^import \{ tidyLabel as cleanLabel, LABEL_WIDTH, titleCase \} from '\.\/labels\.mjs';$/m);
  assert.doesNotMatch(source, /function packetGrams|function seedLabel|function sowingMonths/);
  assert.ok(!fs.existsSync(path.join(dir, 'src/seedText.js')));

  assert.strictEqual(behaviour(dir), was);
  const cmp = shape(dir, ['--compare', before]);
  assert.strictEqual(cmp.code, 0, cmp.out);
});

test('move.js refuses what would change an ES module\'s behaviour', () => {
  const cases = [
    [['seedLabel'], /packetGrams \(line 10\) stays in the source/],
    [['listFolder'], /line 39 uses import\.meta, which means something else in another file/],
    [['seasonCount'], /seasonCount \(line 46\) is the default export/],
    [['swaps'], /swaps \(line 31\) is assigned after it is declared/],
  ];
  for (const [names, message] of cases) {
    const dir = copyApp();
    const original = read(dir, 'src/seeds.mjs');
    const r = tool('move.js', ['src/seeds.mjs', '--to', 'moved', '--names', names.join(',')], dir);
    assert.strictEqual(r.code, 1, `${names} was not refused`);
    assert.match(r.err, message);
    assert.strictEqual(read(dir, 'src/seeds.mjs'), original, 'a refused move changed the source');
    assert.ok(!fs.existsSync(path.join(dir, 'src/moved.mjs')));
  }
});

test('analyse.js describes an ES module', () => {
  const dir = copyApp();
  const r = tool('analyse.js', ['src/seeds.mjs', '--json'], dir);
  assert.strictEqual(r.code, 0, r.err);
  const stmts = JSON.parse(r.out);
  const by = (name) => stmts.find((s) => s.declares.includes(name));
  assert.deepStrictEqual(by('cleanLabel').declares, ['cleanLabel', 'LABEL_WIDTH', 'titleCase']);
  assert.strictEqual(by('cleanLabel').import, true);
  assert.strictEqual(by('catalogue').import, true);
  assert.deepStrictEqual(by('seedLabel').refs, ['LABEL_WIDTH', 'cleanLabel', 'packetGrams']);
  assert.deepStrictEqual(by('packetGrams').refs, ['catalogue', 'units']);
  // `export { SWAP_DAY }` refers to SWAP_DAY; the imported name `tidyLabel` is not a reference.
  assert.deepStrictEqual(stmts.find((s) => s.head === 'export { SWAP_DAY };').refs, ['SWAP_DAY']);
  assert.ok(!stmts.some((s) => s.refs.includes('tidyLabel')));
  const graph = tool('analyse.js', ['src/seeds.mjs', '--graph'], dir);
  assert.strictEqual(graph.code, 0, graph.err);
  assert.match(graph.out, /packetGrams {2}<- +\| used by 2/);
});

test('move-methods.js and move-block.js refuse an ES module rather than write CommonJS wiring into it', () => {
  const cases = [
    ['move-methods.js', ['--class', 'Seeds', '--to', 'moved', '--methods', 'count']],
    ['move-block.js', ['--to', 'moved', '--register', 'registerMoved', '--lines', '19-21']],
  ];
  for (const [name, args] of cases) {
    const dir = copyApp();
    const original = read(dir, 'src/seeds.mjs');
    const r = tool(name, ['src/seeds.mjs', ...args], dir);
    assert.strictEqual(r.code, 1, `${name} did not refuse`);
    assert.match(r.err, new RegExp(`is an ES module; ${name.replace('.', '\\.')} moves CommonJS code only`));
    assert.doesNotMatch(r.err, SOURCE_TYPE_REFUSAL);
    assert.strictEqual(read(dir, 'src/seeds.mjs'), original);
  }
});

test('the shape check of an ES module catches a planted fault, and a git ref compare loads the new file alone', { skip: spawnSync('git', ['--version']).status !== 0 }, () => {
  const dir = copyApp();
  const before = path.join(dir, 'before.json');
  assert.strictEqual(shape(dir, ['--out', before]).code, 0);
  const file = path.join(dir, 'src/seeds.mjs');
  const text = fs.readFileSync(file, 'utf8');
  fs.writeFileSync(file, text.replace("export { SWAP_DAY };\n", ''));
  const lost = shape(dir, ['--compare', before]);
  assert.strictEqual(lost.code, 1, 'a lost export was not caught');
  assert.match(lost.out, /SWAP_DAY/);
  fs.writeFileSync(file, text);

  const git = (...args) => spawnSync('git', ['-c', 'user.name=Example', '-c', 'user.email=split@example.com', ...args], { cwd: dir, encoding: 'utf8' });
  git('init', '-q');
  git('add', '.');
  git('commit', '-q', '-m', 'fixture');
  assert.strictEqual(tool('move.js', MOVE, dir).code, 0);
  let cmp = shape(dir, ['--compare-ref', 'HEAD']);
  assert.strictEqual(cmp.code, 0, cmp.out);
  fs.appendFileSync(path.join(dir, 'src/seedText.mjs'), "\nimport './missing.mjs';\n");
  cmp = shape(dir, ['--compare-ref', 'HEAD']);
  assert.strictEqual(cmp.code, 1);
  assert.match(cmp.out, /PROBLEM loading alone failed: src\/seedText\.mjs/);
});
