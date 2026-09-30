'use strict';
// The JavaScript split tools on a fictional app (tests/fixtures/js-app): each move keeps the app's
// shape and behaviour and moves text unchanged; each refusal fires; planted faults are caught.

const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

const TOOLS = path.join(__dirname, '..', '..', 'scripts', 'js');
const FIXTURE = path.join(__dirname, '..', 'fixtures', 'js-app');

// A copy of the fixture app with LF line endings, whatever the checkout wrote.
function copyApp() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'split-js-'));
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

function shape(dir, extra = []) {
  return tool('shape.js', ['--root', dir, '--modules', 'src/garden.js', ...extra], dir);
}

const read = (dir, file) => fs.readFileSync(path.join(dir, file), 'utf8');

// Every line of the original's named range appears, unchanged and in order, in the new file.
function assertMovedVerbatim(original, from, to, moved) {
  const block = original.split('\n').slice(from - 1, to).join('\n');
  assert.ok(moved.includes(block), `lines ${from}-${to} were not moved unchanged`);
}

// The app's observable behaviour: routes in order and what each answers.
function behaviour(dir) {
  const script = `
    const g = require('./src/garden');
    const out = [];
    const res = { json: (v) => out.push(v) };
    for (const layer of g.stack) {
      if (!layer.route) continue;
      const req = { body: { name: ' Sage ', kind: 'herb' }, params: { kind: 'tree' } };
      for (const step of layer.route.stack) step.handle(req, res, () => {});
      out.push(layer.route.path);
    }
    const gh = new g.Greenhouse('North').addBed([1, 2]).addBed([3]);
    out.push(gh.describe(), gh.size, new g.Shed('Tool').describe(), g.cleanName(' Fern '));
    console.log(JSON.stringify(out.map((v) => (v && v.since ? { ...v, since: 0 } : v))));`;
  const r = spawnSync(process.execPath, ['-e', script], { cwd: dir, encoding: 'utf8' });
  assert.strictEqual(r.status, 0, r.stderr);
  return r.stdout;
}

function snapshotBefore(dir) {
  const file = path.join(dir, 'before.json');
  assert.strictEqual(shape(dir, ['--out', file]).code, 0);
  return file;
}

test('move.js moves declarations unchanged, and the shape and behaviour stay the same', () => {
  const dir = copyApp();
  const before = snapshotBefore(dir);
  const was = behaviour(dir);
  const original = read(dir, 'src/garden.js');
  const r = tool('move.js', ['src/garden.js', '--to', 'plantText', '--names', 'describePlant,wateringDays', '--ref', 'TASK-0000-0001'], dir);
  assert.strictEqual(r.code, 0, r.err);
  const moved = read(dir, 'src/plantText.js');
  assertMovedVerbatim(original, 18, 24, moved);
  assert.match(moved, /^'use strict';/);
  assert.match(moved, /Moved unchanged from garden\.js \(TASK-0000-0001\)/);
  assert.match(read(dir, 'src/garden.js'), /const \{ describePlant, wateringDays \} = require\('\.\/plantText'\);/);
  assert.strictEqual(behaviour(dir), was);
  const cmp = shape(dir, ['--compare', before]);
  assert.strictEqual(cmp.code, 0, cmp.out);
});

test('move.js copies the imports the moved code uses', () => {
  const dir = copyApp();
  const r = tool('move.js', ['src/garden.js', '--to', 'names', '--names', 'MAX_NAME,cleanName'], dir);
  assert.strictEqual(r.code, 0, r.err);
  const moved = read(dir, 'src/names.js');
  assert.doesNotMatch(moved, /require/); // cleanName uses only MAX_NAME, which moved with it
  assert.match(read(dir, 'src/garden.js'), /const \{ MAX_NAME, cleanName \} = require\('\.\/names'\);/);
});

test('move.js refuses what would change behaviour', () => {
  const cases = [
    [['cleanName'], /MAX_NAME \(line 9\) stays in the source/],
    [['visits'], /visits \(line \d+\) is assigned after it is declared/],
    [['started'], /runs code when loaded \(Date\.now\(\)\)/],
    [['nothing'], /not found at top level: nothing/],
  ];
  for (const [names, message] of cases) {
    const dir = copyApp();
    const original = read(dir, 'src/garden.js');
    const r = tool('move.js', ['src/garden.js', '--to', 'moved', '--names', names.join(',')], dir);
    assert.strictEqual(r.code, 1, `${names} was not refused`);
    assert.match(r.err, message);
    assert.strictEqual(read(dir, 'src/garden.js'), original, 'a refused move changed the source');
    assert.ok(!fs.existsSync(path.join(dir, 'src/moved.js')));
  }
  const dir = copyApp();
  assert.strictEqual(tool('move.js', ['src/garden.js', '--to', 'moved', '--names', 'started', '--allow-load-order'], dir).code, 0);
  // It sat directly under another statement: the blank line after it stays.
  assert.match(read(dir, 'src/garden.js'), /let visits = 0;\n\nclass Greenhouse/);
});

test('move-methods.js moves methods onto a holder class the original takes back', () => {
  const dir = copyApp();
  const before = snapshotBefore(dir);
  const was = behaviour(dir);
  const original = read(dir, 'src/garden.js');
  let r = tool('move-methods.js', ['src/garden.js', '--class', 'Greenhouse', '--to', 'greenhouseCount', '--methods', 'countPlants'], dir);
  assert.strictEqual(r.code, 0, r.err);
  r = tool('move-methods.js', ['src/garden.js', '--class', 'Greenhouse', '--to', 'greenhouseText', '--methods', 'describe'], dir);
  assert.strictEqual(r.code, 0, r.err);
  assertMovedVerbatim(original, 40, 43, read(dir, 'src/greenhouseCount.js'));
  const source = read(dir, 'src/garden.js');
  assert.match(source, /for \(const Methods of \[\n {2}require\('\.\/greenhouseCount'\),\n {2}require\('\.\/greenhouseText'\),\n\]\) \{/);
  assert.strictEqual(behaviour(dir), was);
  const cmp = shape(dir, ['--compare', before]);
  assert.strictEqual(cmp.code, 0, cmp.out);
});

test('move-methods.js refuses members that cannot move', () => {
  const cases = [
    ['Greenhouse', 'make', /make is not a plain method/],
    ['Greenhouse', 'size', /size is not a plain method/],
    ['Greenhouse', 'constructor', /constructor is not a plain method/],
    ['Greenhouse', 'label', /MAX_NAME \(line 9\) stays in the source/],
    ['Shed', 'describe', /describe uses super/],
  ];
  for (const [cls, method, message] of cases) {
    const dir = copyApp();
    const r = tool('move-methods.js', ['src/garden.js', '--class', cls, '--to', 'moved', '--methods', method], dir);
    assert.strictEqual(r.code, 1, `${cls}.${method} was not refused`);
    assert.match(r.err, message);
  }
});

test('move-block.js moves routes into a register function called where they were', () => {
  const dir = copyApp();
  const before = snapshotBefore(dir);
  const was = behaviour(dir);
  const range = tool('analyse.js', ['src/garden.js', '--range', "router.get('/plants',", "router.get('/plants/:kind/water'"], dir);
  assert.strictEqual(range.code, 0, range.err);
  assert.strictEqual(range.out.trim(), '73-86');
  const r = tool('move-block.js', ['src/garden.js', '--to', 'plantRoutes', '--register', 'registerPlantRoutes', '--lines', '73-86', '--ref', 'TASK-0000-0002'], dir);
  assert.strictEqual(r.code, 0, r.err);
  const source = read(dir, 'src/garden.js');
  assert.match(source, /registerPlantRoutes\(router, \{ plants, cleanName, describePlant, wateringDays \}\);/);
  assert.match(read(dir, 'src/plantRoutes.js'), /function registerPlantRoutes\(router, \{ plants, cleanName, describePlant, wateringDays \}\) \{/);
  assert.strictEqual(behaviour(dir), was);
  const cmp = shape(dir, ['--compare', before]);
  assert.strictEqual(cmp.code, 0, cmp.out);
});

test('move-block.js refuses what would change behaviour', () => {
  const at = (dir, text) => read(dir, 'src/garden.js').split('\n').findIndex((l) => l.startsWith(text)) + 1;
  const cases = [
    [(d) => `${at(d, "router.get('/plants',") + 1}-${at(d, "router.get('/plants/:kind") + 2}`, /the range cuts statements/],
    [(d) => `${at(d, "router.get('/visits'")}-${at(d, "router.get('/visits'") + 2}`, /visits \(line \d+\) is reassigned/],
    [(d) => `${at(d, "router.get('/self'")}-${at(d, "router.get('/self'") + 2}`, /uses module, which means something else/],
    [(d) => `${at(d, "router.get('/late'")}-${at(d, "router.get('/late'") + 2}`, /LATE is declared at line \d+, after the call/],
  ];
  for (const [range, message] of cases) {
    const dir = copyApp();
    const r = tool('move-block.js', ['src/garden.js', '--to', 'moved', '--register', 'registerMoved', '--lines', range(dir)], dir);
    assert.strictEqual(r.code, 1, `${range(dir)} was not refused`);
    assert.match(r.err, message);
  }
});

test('the shape check catches planted faults', () => {
  const faults = [
    ['a changed function body', (s) => s.replace("return { herb: 2, tree: 7 }[kind] || 3;", "return { herb: 2, tree: 8 }[kind] || 3;"), /wateringDays/],
    ['two routes in another order', (s) => {
      const a = "router.get('/visits', function countVisits(req, res) {\n  res.json({ visits, since: started });\n});\n";
      const b = "router.get('/self', function self(req, res) {\n  res.json({ keys: Object.keys(module.exports) });\n});\n";
      return s.replace(`${a}\n${b}`, `${b}\n${a}`);
    }, /route GET \/(visits|self)/],
    ['a lost export', (s) => s.replace('module.exports.Shed = Shed;\n', ''), /Shed/],
    ['a method that became enumerable', (s) => s.replace("module.exports = router;", "Greenhouse.prototype.extra = function extra() {};\nmodule.exports = router;"), /extra/],
  ];
  for (const [label, plant, expected] of faults) {
    const dir = copyApp();
    const before = snapshotBefore(dir);
    const file = path.join(dir, 'src/garden.js');
    const text = fs.readFileSync(file, 'utf8');
    const changed = plant(text);
    assert.notStrictEqual(changed, text, `${label}: the fault was not planted`);
    fs.writeFileSync(file, changed);
    const cmp = shape(dir, ['--compare', before]);
    assert.strictEqual(cmp.code, 1, `${label} was not caught`);
    assert.match(cmp.out, expected, label);
  }
});

test('the shape check against a git ref loads every changed file alone', { skip: spawnSync('git', ['--version']).status !== 0 }, () => {
  const dir = copyApp();
  const git = (...args) => spawnSync('git', ['-c', 'user.name=Example', '-c', 'user.email=split@example.com', ...args], { cwd: dir, encoding: 'utf8' });
  git('init', '-q');
  git('add', '.');
  git('commit', '-q', '-m', 'fixture');
  assert.strictEqual(tool('move.js', ['src/garden.js', '--to', 'plantText', '--names', 'describePlant,wateringDays'], dir).code, 0);
  let cmp = shape(dir, ['--compare-ref', 'HEAD']);
  assert.strictEqual(cmp.code, 0, cmp.out);
  fs.appendFileSync(path.join(dir, 'src/plantText.js'), "\nrequire('./missing');\n");
  cmp = shape(dir, ['--compare-ref', 'HEAD']);
  assert.strictEqual(cmp.code, 1);
  assert.match(cmp.out, /PROBLEM loading alone failed: src\/plantText\.js/);
});

test('move-block.js tells a route\'s own variable from a reassigned top-level one of the same name', () => {
  const dir = copyApp();
  const at = (text) => read(dir, 'src/shadow.js').split('\n').findIndex((l) => l.startsWith(text)) + 1;
  const behaviour = () => {
    const script = `
      const r = require('./src/shadow');
      const out = [];
      for (const theme of ['dark', 'light']) {
        for (const layer of r.stack) {
          const req = { query: { theme } };
          const res = { json: (v) => out.push(v) };
          if (layer.route) layer.route.stack.forEach((s) => s.handle(req, res, () => {}));
          else layer.handle(req, res, () => {});
        }
      }
      console.log(JSON.stringify(out));`;
    const r = spawnSync(process.execPath, ['-e', script], { cwd: dir, encoding: 'utf8' });
    assert.strictEqual(r.status, 0, r.stderr);
    return r.stdout;
  };
  const was = behaviour();
  // The route reading the file's settings cannot move: its value would be frozen at the call.
  const shared = tool('move-block.js', ['src/shadow.js', '--to', 'sharedRoutes', '--register', 'registerShared', '--lines', `${at('// Reads the file')}-${at("router.get('/shared'") + 2}`], dir);
  assert.strictEqual(shared.code, 1);
  assert.match(shared.err, /settings \(line 7\) is reassigned/);
  // The two that only use their own settings can.
  const r = tool('move-block.js', ['src/shadow.js', '--to', 'ownRoutes', '--register', 'registerOwn', '--lines', `${at('// Reads its own')}-${at("router.get('/param'") + 3}`], dir);
  assert.strictEqual(r.code, 0, r.err);
  assert.match(read(dir, 'src/shadow.js'), /registerOwn\(router, \{\s*\}\);|registerOwn\(router, \{ {2}\}\);|registerOwn\(router, \{ \}\);/);
  assert.strictEqual(behaviour(), was);
});
