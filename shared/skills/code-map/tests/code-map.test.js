'use strict';
// Behaviour of the code map on a small fictional shop: what it maps, and every check failing once on
// purpose before it is trusted to pass. Run: npm test (from the skill folder).

const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');
const { buildMap } = require('../scripts/lib/build');
const { runChecks } = require('../scripts/lib/checks');
const { loadRecords, writeRecords } = require('../scripts/lib/records');
const { show, findWords } = require('../scripts/lib/query');

const FIXTURE = path.join(__dirname, 'fixtures', 'shop');
const CLI = path.join(__dirname, '..', 'scripts', 'code-map.js');

function copyFixture() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'code-map-'));
  fs.cpSync(FIXTURE, dir, { recursive: true });
  return dir;
}

const noRecords = { sizes: {}, interface: null, known: [] };
const map = buildMap(FIXTURE);
const result = runChecks(map, noRecords);
const keys = (check) => result.byCheck[check].findings.map((f) => f.key);

test('routes get their full path through the mount prefix', () => {
  const routes = map.ctx.routes.map((r) => `${r.method} ${r.path}`).sort();
  assert.deepStrictEqual(routes, ['GET /api/orders', 'GET /api/orders/:id', 'POST /api/orders']);
});

test('a UI call is linked to the route it reaches, and one that reaches none fails the http check', () => {
  const get = map.ctx.httpCalls.find((c) => c.url === '/api/orders/:param');
  assert.ok(get && get.matches.length === 1, 'the template URL matches GET /api/orders/:id');
  assert.deepStrictEqual(keys('http'), ['http:GET /api/invoices/:param @frontend/api.js']);
});

test('an environment variable missing from env.example fails; one listed there passes', () => {
  assert.deepStrictEqual(keys('env'), ['env:SHOP_SECRET']);
});

test('a startup cycle fails, and a require inside a function is not part of one', () => {
  assert.deepStrictEqual(keys('cycles'), ['cycles:backend/lib/a.js <> backend/lib/b.js']);
});

test('a column the model does not define fails; implicit and defined ones pass', () => {
  assert.deepStrictEqual(keys('columns'), ['columns:Order.customer_ref @backend/routes/orders.js']);
});

test('a field of a record loaded through a model is linked to its column', () => {
  const reads = map.graph.edgesOf('reads-column').filter((e) => e.to === 'column:orders.total_cents' && e.via === 'record');
  assert.ok(reads.length >= 1);
});

test('a field is found in code, a Vue template and an EJS template, with its values and default', () => {
  const text = show(map, 'kind');
  assert.match(text, /field contact\.kind/);
  assert.match(text, /backend\/routes\/orders\.js:\d+/);
  assert.match(text, /frontend\/Receipt\.vue:3 \(vue template\)/);
  assert.match(text, /templates\/receipt\.ejs:3 \(ejs template\)/);
  assert.match(text, /compared with: "business"/);
  assert.match(text, /defaults to: "person"/);
  assert.match(text, /NOT SET anywhere in this repository/);
});

test('a field some code sets is not reported as set elsewhere', () => {
  const text = show(map, 'status');
  assert.match(text, /set at/);
  assert.doesNotMatch(text, /NOT SET anywhere/);
});

test('word search ranks the function where the most words meet', () => {
  const text = findWords(map, 'invoice total tax');
  const first = text.split('\n== ')[1];
  assert.match(first, /^3\/3 {2}frontend\/api\.js:\d+-\d+ {2}invoiceTotalWithTax/);
});

test('a name the map does not know falls back to word search', () => {
  assert.match(show(map, 'included'), /Word search for included/);
});

test('size ratchet: a new oversized file fails, adoption records it, growth fails, shrinking lowers the record', () => {
  const dir = copyFixture();
  const big = path.join(dir, 'backend', 'big.js');
  fs.writeFileSync(big, Array.from({ length: 900 }, (_, i) => `const v${i} = ${i};`).join('\n'));
  let m = buildMap(dir);
  let recDir = path.join(dir, 'code-map');
  assert.deepStrictEqual(runChecks(m, loadRecords(recDir)).byCheck.size.new.map((f) => f.key), ['size:backend/big.js']);
  writeRecords(m, recDir, runChecks(m, loadRecords(recDir)), { adopt: true });
  assert.ok(runChecks(buildMap(dir), loadRecords(recDir)).ok, 'passes once adopted');
  fs.appendFileSync(big, '\nconst more = 1;');
  m = buildMap(dir);
  assert.match(runChecks(m, loadRecords(recDir)).byCheck.size.new[0].message, /grew from its recorded 900 lines to 901/);
  fs.writeFileSync(big, Array.from({ length: 850 }, (_, i) => `const v${i} = ${i};`).join('\n'));
  m = buildMap(dir);
  writeRecords(m, recDir, runChecks(m, loadRecords(recDir)));
  assert.strictEqual(loadRecords(recDir).sizes['backend/big.js'], 850);
  fs.rmSync(dir, { recursive: true, force: true });
  recDir = null;
});

test('interface record: an export change fails until it is recorded', () => {
  const dir = copyFixture();
  const recDir = path.join(dir, 'code-map');
  let m = buildMap(dir);
  writeRecords(m, recDir, runChecks(m, loadRecords(recDir)), { adopt: true });
  fs.appendFileSync(path.join(dir, 'frontend', 'api.js'), '\nexport function cancelOrder(id) { return id; }\n');
  m = buildMap(dir);
  const r = runChecks(m, loadRecords(recDir));
  assert.deepStrictEqual(r.byCheck.interface.new.map((f) => f.key), ['interface:frontend/api.js']);
  assert.match(r.byCheck.interface.new[0].message, /\+cancelOrder/);
  writeRecords(m, recDir, r);
  assert.ok(runChecks(buildMap(dir), loadRecords(recDir)).ok);
  fs.rmSync(dir, { recursive: true, force: true });
});

test('the command line fails on new findings and passes after adoption', () => {
  const dir = copyFixture();
  const run = (...args) => { try { execFileSync(process.execPath, [CLI, ...args], { stdio: 'pipe' }); return 0; } catch (e) { return e.status; } };
  assert.strictEqual(run('check', dir), 1);
  assert.strictEqual(run('record', dir, '--adopt'), 0);
  assert.strictEqual(run('check', dir), 0);
  assert.match(execFileSync(process.execPath, [CLI, '--version']).toString(), /^code-map \d+\.\d+\.\d+/);
  fs.rmSync(dir, { recursive: true, force: true });
});

test('a folder inside another repository is still mapped, not silently emptied', () => {
  // The fixture itself sits inside the brain's repository, below a folder that repository tracks;
  // a copy under an ignored folder must be walked directly rather than asked of the outer Git.
  const dir = copyFixture();
  const inner = path.join(dir, 'ignored', 'copy');
  fs.mkdirSync(inner, { recursive: true });
  fs.cpSync(FIXTURE, inner, { recursive: true });
  execFileSync('git', ['init', '-q', dir]);
  fs.writeFileSync(path.join(dir, '.gitignore'), 'ignored/\n');
  const m = buildMap(inner);
  assert.ok(m.ctx.routes.length === 3, `expected the three routes, got ${m.ctx.routes.length}`);
  fs.rmSync(dir, { recursive: true, force: true });
});

test('a field set only under another path is not reported as coming from outside the code', () => {
  const m = buildMap(FIXTURE);
  const text = show(m, 'user.role');
  assert.doesNotMatch(text, /NOT SET anywhere/);
  assert.match(text, /set as role at backend\/lib\/staff\.js:\d+/);
});
