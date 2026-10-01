'use strict';
// The names a piece of code refers to that it does not declare itself: resolved through its own
// scopes (functions, blocks, loops, catch clauses, classes), the way JavaScript resolves them, so a
// local variable that shares a name with a top-level one is not taken for it. What is left refers to
// the file's top level (or a global).
//
// It errs on the side of free: a name it cannot place in an inner scope counts as free, so a move
// may be refused for a name it does not need, never allowed without one it does. Not handled, and
// so counted as free: names a sloppy-mode function declaration hoists out of its block, `with`, eval.
// Part of the split-file skill (canonical copy: /shared/skills/split-file/).

const SKIP_KEYS = new Set(['loc', 'start', 'end', 'leadingComments', 'trailingComments', 'innerComments', 'extra']);
const FUNCTIONS = new Set(['FunctionDeclaration', 'FunctionExpression', 'ArrowFunctionExpression', 'ObjectMethod', 'ClassMethod', 'ClassPrivateMethod']);

function eachChild(n, fn) {
  for (const k of Object.keys(n)) {
    if (SKIP_KEYS.has(k)) continue;
    const v = n[k];
    if (Array.isArray(v)) v.forEach((c) => { if (c && typeof c.type === 'string') fn(c, k); });
    else if (v && typeof v.type === 'string') fn(v, k);
  }
}

// The names a declaration pattern binds.
function bound(p, out) {
  if (!p) return out;
  if (p.type === 'Identifier') out.add(p.name);
  else if (p.type === 'ObjectPattern') p.properties.forEach((q) => bound(q.type === 'RestElement' ? q.argument : q.value, out));
  else if (p.type === 'ArrayPattern') p.elements.forEach((e) => bound(e, out));
  else if (p.type === 'AssignmentPattern') bound(p.left, out);
  else if (p.type === 'RestElement') bound(p.argument, out);
  return out;
}

// An identifier that names a binding here, rather than a property, a key or a label.
function isReference(parent, key) {
  if (!parent) return true;
  if (/MemberExpression$/.test(parent.type) && key === 'property' && !parent.computed) return false;
  if (['ObjectProperty', 'ObjectMethod', 'ClassMethod', 'ClassProperty', 'ClassPrivateProperty'].includes(parent.type) && key === 'key' && !parent.computed) return false;
  if (['LabeledStatement', 'BreakStatement', 'ContinueStatement'].includes(parent.type)) return false;
  if (parent.type === 'MetaProperty') return false;
  return true;
}

/** { read, assigned }: the names the node refers to, and assigns, that no scope inside it declares. */
function freeNames(root) {
  const read = new Set();
  const assigned = new Set();
  const scope = (parent) => ({ names: new Set(), parent });
  const declared = (s, name) => { for (let c = s; c; c = c.parent) if (c.names.has(name)) return true; return false; };
  const refer = (name, s, isAssign) => {
    if (declared(s, name)) return;
    read.add(name);
    if (isAssign) assigned.add(name);
  };

  // `var` declarations anywhere in a function body (not in nested functions) belong to the function.
  const hoistVars = (node, s) => {
    const visit = (n) => {
      if (FUNCTIONS.has(n.type)) return;
      if (n.type === 'VariableDeclaration' && n.kind === 'var') n.declarations.forEach((d) => bound(d.id, s.names));
      eachChild(n, visit);
    };
    visit(node);
  };
  // Block-scoped declarations directly in a list of statements.
  const blockDeclarations = (statements, s) => {
    for (const st of statements) {
      if (st.type === 'VariableDeclaration' && st.kind !== 'var') st.declarations.forEach((d) => bound(d.id, s.names));
      if ((st.type === 'FunctionDeclaration' || st.type === 'ClassDeclaration') && st.id) s.names.add(st.id.name);
    }
  };

  // A declaration pattern: its defaults and computed keys are references; its names are not.
  function pattern(p, s) {
    if (!p) return;
    if (p.type === 'AssignmentPattern') { pattern(p.left, s); walk(p.right, s, p, 'right'); return; }
    if (p.type === 'ObjectPattern') {
      for (const q of p.properties) {
        if (q.type === 'RestElement') { pattern(q.argument, s); continue; }
        if (q.computed) walk(q.key, s, q, 'key');
        pattern(q.value, s);
      }
      return;
    }
    if (p.type === 'ArrayPattern') { p.elements.forEach((e) => pattern(e, s)); return; }
    if (p.type === 'RestElement') { pattern(p.argument, s); return; }
    if (p.type !== 'Identifier') walk(p, s, null, null); // a member expression as an assignment target
  }

  // The target of an assignment or update: an identifier there is assigned; anything else is walked.
  function target(t, s) {
    if (t.type === 'Identifier') { refer(t.name, s, true); return; }
    if (['ObjectPattern', 'ArrayPattern', 'AssignmentPattern', 'RestElement'].includes(t.type)) {
      for (const name of bound(t, new Set())) refer(name, s, true);
      pattern(t, scope(null)); // defaults and computed keys, resolved from nowhere (counted as free)
      return;
    }
    walk(t, s, null, null);
  }

  function walk(n, s, parent, key) {
    if (!n || typeof n.type !== 'string') return;
    if (n.type === 'Identifier') { if (isReference(parent, key)) refer(n.name, s, false); return; }
    if (FUNCTIONS.has(n.type)) {
      if (n.computed && n.key) walk(n.key, s, n, 'key');
      const fs = scope(s);
      if (n.type === 'FunctionExpression' && n.id) fs.names.add(n.id.name);
      if (n.type !== 'ArrowFunctionExpression') fs.names.add('arguments');
      n.params.forEach((p) => bound(p, fs.names));
      hoistVars(n.body, fs);
      n.params.forEach((p) => pattern(p, fs));
      if (n.body.type === 'BlockStatement') {
        blockDeclarations(n.body.body, fs);
        n.body.body.forEach((st) => walk(st, fs, n.body, 'body'));
      } else walk(n.body, fs, n, 'body');
      return;
    }
    if (n.type === 'BlockStatement' || n.type === 'StaticBlock') {
      const bs = scope(s);
      blockDeclarations(n.body, bs);
      n.body.forEach((st) => walk(st, bs, n, 'body'));
      return;
    }
    if (n.type === 'SwitchStatement') {
      walk(n.discriminant, s, n, 'discriminant');
      const ss = scope(s);
      n.cases.forEach((c) => blockDeclarations(c.consequent, ss));
      n.cases.forEach((c) => { walk(c.test, ss, c, 'test'); c.consequent.forEach((st) => walk(st, ss, c, 'consequent')); });
      return;
    }
    if (['ForStatement', 'ForInStatement', 'ForOfStatement'].includes(n.type)) {
      const ls = scope(s);
      const head = n.init || n.left;
      if (head && head.type === 'VariableDeclaration' && head.kind !== 'var') head.declarations.forEach((d) => bound(d.id, ls.names));
      if (head && head.type !== 'VariableDeclaration' && n.type !== 'ForStatement') target(head, ls);
      eachChild(n, (c, k) => { if (!(c === head && head.type !== 'VariableDeclaration' && n.type !== 'ForStatement')) walk(c, ls, n, k); });
      return;
    }
    if (n.type === 'CatchClause') {
      const cs = scope(s);
      bound(n.param, cs.names);
      pattern(n.param, cs);
      walk(n.body, cs, n, 'body');
      return;
    }
    if (n.type === 'ClassDeclaration' || n.type === 'ClassExpression') {
      if (n.superClass) walk(n.superClass, s, n, 'superClass');
      const cs = scope(s);
      if (n.id) cs.names.add(n.id.name);
      walk(n.body, cs, n, 'body');
      return;
    }
    if (n.type === 'VariableDeclarator') { pattern(n.id, s); walk(n.init, s, n, 'init'); return; }
    if (n.type === 'AssignmentExpression') { target(n.left, s); walk(n.right, s, n, 'right'); return; }
    if (n.type === 'UpdateExpression') { target(n.argument, s); return; }
    eachChild(n, (c, k) => walk(c, s, n, k));
  }

  // At the top: the node's own declarations are the file's top-level names, not an inner scope.
  if (root.type === 'FunctionDeclaration' || root.type === 'ClassDeclaration') {
    walk({ ...root, id: null }, scope(null), null, null);
  } else if (root.type === 'VariableDeclaration') {
    root.declarations.forEach((d) => { pattern(d.id, scope(null)); walk(d.init, scope(null), d, 'init'); });
  } else {
    walk(root, scope(null), null, null);
  }
  return { read, assigned };
}

module.exports = { freeNames };
