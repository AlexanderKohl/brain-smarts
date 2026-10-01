'use strict';
// lib/scope.js: the names code uses that it does not declare, resolved through its own scopes.
// A move relies on it never missing a name; the cases below each hold one way of declaring or
// shadowing a name.

const test = require('node:test');
const assert = require('node:assert');
const { parse } = require('../../scripts/js/lib/ast');
const { freeNames } = require('../../scripts/js/lib/scope');

const free = (code) => {
  const { read, assigned } = freeNames(parse(code).program.body[0]);
  return { read: [...read].sort(), assigned: [...assigned].sort() };
};

test('a local declaration hides the top-level name it shares', () => {
  assert.deepEqual(free('function f() { const settings = 1; return settings; }').read, []);
  assert.deepEqual(free('function f(settings) { return settings; }').read, []);
  assert.deepEqual(free('function f() { try { g(); } catch (settings) { return settings; } }').read, ['g']);
  assert.deepEqual(free('function f() { for (const settings of list) use(settings); }').read, ['list', 'use']);
  assert.deepEqual(free('const f = function settings() { return settings; };').read, []);
  assert.deepEqual(free('function f() { class Settings {} return new Settings(); }').read, []);
  assert.deepEqual(free('router.get("/", (req, res) => { const settings = load(req); res.json(settings); });').read, ['load', 'router']);
});

test('var is the function\'s, let and const are the block\'s', () => {
  assert.deepEqual(free('function f() { if (a) { var y = 1; } return y; }').read, ['a']);
  assert.deepEqual(free('function f() { { let y = 1; } return y; }').read, ['y'], 'a let outside its block is the top-level one');
  assert.deepEqual(free('function f() { return y; let y = 1; }').read, [], 'read before its let: still the local one');
});

test('names used in patterns, defaults and computed keys', () => {
  assert.deepEqual(free('function f({ a = b, [c]: d }) { return a + d; }').read, ['b', 'c']);
  assert.deepEqual(free('function f() { const { x = fallback } = source; return x; }').read, ['fallback', 'source']);
});

test('assignments to a name no scope inside declares', () => {
  assert.deepEqual(free('function f() { settings = load(); count += 1; total++; }'), { read: ['count', 'load', 'settings', 'total'], assigned: ['count', 'settings', 'total'] });
  assert.deepEqual(free('function f() { let settings; settings = load(); }'), { read: ['load'], assigned: [] });
  assert.deepEqual(free('function f() { [a, b] = pair; }'), { read: ['a', 'b', 'pair'], assigned: ['a', 'b'] });
});

test('what is not a name: properties, keys, labels', () => {
  assert.deepEqual(free('function f() { out: for (;;) { x.settings = { settings: 1 }; break out; } }').read, ['x']);
  assert.deepEqual(free('function f() { return { settings }; }').read, ['settings'], 'a shorthand property reads the name');
  assert.deepEqual(free('function f() { return obj[settings]; }').read, ['obj', 'settings']);
});
