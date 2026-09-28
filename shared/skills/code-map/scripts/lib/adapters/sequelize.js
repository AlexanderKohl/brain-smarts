'use strict';
// Sequelize: models (sequelize.define and Model.init), their attributes and database column names,
// associations, the schema the migrations build in order, and the model calls in code
// (where, attributes, order, include, create/update data). Part of the code-map skill
// (canonical copy: /shared/skills/code-map/).

const path = require('path');
const A = require('../js/ast');
const { lookup } = require('../js/extract');
const { analyse } = require('../sql');

const READ_OPS = new Set(['findAll', 'findOne', 'findByPk', 'findAndCountAll', 'findOrCreate', 'findCreateFind', 'count', 'max', 'min', 'sum', 'aggregate']);
const WRITE_OPS = new Set(['create', 'bulkCreate', 'update', 'destroy', 'upsert', 'increment', 'decrement', 'restore', 'truncate']);
const ASSOCIATIONS = new Set(['hasMany', 'belongsTo', 'hasOne', 'belongsToMany']);
// Calls whose result is one record of the model.
const RECORD_OPS = new Set(['findOne', 'findByPk', 'create', 'build']);

const snake = (s) => s.replace(/([a-z0-9])([A-Z])/g, '$1_$2').replace(/([A-Z])([A-Z][a-z])/g, '$1_$2').toLowerCase();

function props(obj) {
  const out = new Map();
  obj = A.unwrap(obj);
  if (!obj || obj.type !== 'ObjectExpression') return out;
  for (const p of obj.properties) if (p.type === 'ObjectProperty' || p.type === 'ObjectMethod') out.set(A.keyName(p.key, p.computed), p.type === 'ObjectMethod' ? p : p.value);
  return out;
}

// Folders the project declares for sequelize-cli: `--models-path` / `--migrations-path` in its npm
// scripts, then .sequelizerc. A folder is taken only when it exists.
function declaredFolders(ctx) {
  const out = { models: [], migrations: [] };
  const { readText } = require('../files');
  const dirs = new Set(ctx.files.map((e) => path.posix.dirname(e.file)));
  const keep = (kind, p) => { p = p.replace(/^\.\//, '').replace(/\/$/, ''); if (dirs.has(p) && !out[kind].includes(p)) out[kind].push(p); };
  for (const e of ctx.files) {
    if (path.posix.basename(e.file) !== 'package.json') continue;
    let pkg;
    try { pkg = JSON.parse(readText(ctx.root, e) || '{}'); } catch { continue; }
    const base = path.posix.dirname(e.file) === '.' ? '' : path.posix.dirname(e.file);
    for (const script of Object.values(pkg.scripts || {})) {
      for (const [flag, kind] of [['--models-path', 'models'], ['--migrations-path', 'migrations']]) {
        const m = new RegExp(`${flag}[= ]+([^\\s]+)`).exec(script);
        if (m) keep(kind, path.posix.join(base, m[1]));
      }
    }
  }
  const rc = ctx.files.find((e) => /(^|\/)\.sequelizerc$/.test(e.file));
  const text = rc ? readText(ctx.root, rc) : null;
  if (!text) return out;
  let ast;
  try { ast = A.parse(text, `${rc.file}.js`); } catch { return out; }
  const dir = path.posix.dirname(rc.file) === '.' ? '' : path.posix.dirname(rc.file);
  A.walk(ast.program, (node) => {
    if (node.type !== 'ObjectProperty') return;
    const key = A.keyName(node.key, node.computed);
    if (key !== 'models-path' && key !== 'migrations-path') return;
    const v = A.unwrap(node.value);
    let p = A.staticString(v);
    if (p === null && A.isCall(v)) {
      const parts = v.arguments.filter((a) => !(a.type === 'Identifier' && a.name === '__dirname')).map((a) => A.staticString(a));
      if (parts.every((x) => x !== null)) p = path.posix.join(...parts);
    }
    if (p !== null) keep(key === 'models-path' ? 'models' : 'migrations', path.posix.join(dir, p));
  });
  return out;
}

function sequelizeAdapter(ctx) {
  const { project, db, graph, config } = ctx;
  const rc = declaredFolders(ctx);
  const modelDirs = (config.sequelize.models.length ? config.sequelize.models : rc.models).map((d) => d.replace(/\/$/, ''));
  const migrationDirs = (config.sequelize.migrations.length ? config.sequelize.migrations : rc.migrations).map((d) => d.replace(/\/$/, ''));
  const usesSequelize = [...project.facts.values()].some((f) => f.imports.some((i) => i.source === 'sequelize'));
  if (!usesSequelize && !modelDirs.length) { graph.cover('orm:sequelize', 'not used', {}); return; }
  if (!modelDirs.length) {
    for (const f of project.facts.values()) {
      if (/(^|\/)models\/index\.[cm]?js$/.test(f.file) && f.imports.some((i) => i.source === 'sequelize')) modelDirs.push(path.posix.dirname(f.file));
    }
  }
  if (!migrationDirs.length) for (const d of modelDirs) migrationDirs.push(path.posix.join(path.posix.dirname(d), 'migrations'));
  const indexFiles = new Set(config.sequelize.modelsIndex.length ? config.sequelize.modelsIndex
    : modelDirs.flatMap((d) => ['js', 'cjs', 'mjs', 'ts'].map((e) => `${d}/index.${e}`)));
  const inModels = (file) => modelDirs.some((d) => file.startsWith(`${d}/`)) && !indexFiles.has(file);

  // Models.
  const modelBindings = new Map(); // binding -> model name
  for (const facts of project.facts.values()) {
    if (!inModels(facts.file) && !facts.imports.some((i) => i.source === 'sequelize')) continue;
    for (const site of facts.callSites) {
      const method = site.path[site.path.length - 1];
      if (method === 'define' && site.args.length >= 2 && A.unwrap(site.args[1]).type === 'ObjectExpression') {
        const name = A.staticString(site.args[0]);
        if (name === null) continue;
        defineModel(ctx, facts, name, site.args[1], site.args[2], site.line);
        for (const b of facts.moduleScope.values()) if (b.init && A.unwrap(b.init) === site.node) modelBindings.set(b, name);
        for (const s of facts.callSites) if (s.binding && s.binding.init && A.unwrap(s.binding.init) === site.node) modelBindings.set(s.binding, name);
      } else if (method === 'init' && site.rootType === 'id' && site.path.length === 1 && site.args[0] && A.unwrap(site.args[0]).type === 'ObjectExpression') {
        // class X extends Model {} – at module level or inside the exported model function.
        const b = site.binding;
        const cls = b && b.kind === 'class' && b.init ? b.init : null;
        const sup = cls && cls.superClass ? A.memberChain(cls.superClass) : null;
        const supName = sup ? (sup.path.length ? sup.path[sup.path.length - 1] : sup.root && sup.root.name) : null;
        if (supName !== 'Model') continue;
        const opts = props(site.args[1]);
        const name = opts.get('modelName') ? A.staticString(opts.get('modelName')) || b.name : b.name;
        defineModel(ctx, facts, name, site.args[0], site.args[1], site.line);
        modelBindings.set(b, name);
      }
    }
  }

  // Associations, once every model is known.
  for (const facts of project.facts.values()) {
    if (!inModels(facts.file)) continue;
    for (const site of facts.callSites) {
      const kind = site.path[site.path.length - 1];
      if (!ASSOCIATIONS.has(kind) || !site.args[0]) continue;
      let source = null;
      if (site.rootType === 'id' && site.path.length === 1) source = modelBindings.get(site.binding) || (db.models.has(site.rootName) ? site.rootName : null);
      if (site.rootType === 'this' && site.className) source = db.models.has(site.className) ? site.className : null;
      const targetChain = A.memberChain(site.args[0]);
      const target = targetChain.path.length ? targetChain.path[targetChain.path.length - 1] : targetChain.root && targetChain.root.name;
      if (!source || !target || !db.models.has(target)) continue;
      graph.edge('relates', `model:${source}`, `model:${target}`, { kind, file: facts.file, line: site.line });
      const opts = props(site.args[1]);
      let fk = opts.get('foreignKey');
      fk = fk ? (A.staticString(fk) ?? (props(fk).get('name') ? A.staticString(props(fk).get('name')) : null)) : null;
      if (fk && kind !== 'belongsToMany') {
        const owner = db.models.get(kind === 'belongsTo' ? source : target);
        if (owner && !owner.attributes.has(fk)) db.attribute(owner, fk, owner.underscored ? snake(fk) : fk);
      }
    }
  }

  // Migrations, in file-name order.
  let migrations = 0;
  const migrationFiles = [...project.facts.values()].filter((f) => migrationDirs.some((d) => f.file.startsWith(`${d}/`))).sort((a, b) => (a.file < b.file ? -1 : 1));
  for (const facts of migrationFiles) {
    const up = facts.functions.find((f) => f.name === 'up');
    if (!up) continue;
    migrations++;
    const qi = up.node.params[0] && up.node.params[0].type === 'Identifier' ? up.node.params[0].name : null;
    const sites = facts.callSites.filter((s) => s.owner === up.id).sort((a, b) => a.node.start - b.node.start);
    for (const site of sites) {
      if (site.rootType !== 'id' || site.rootName !== qi) continue;
      const op = site.path.join('.');
      const tableArg = (n) => { const v = A.unwrap(n); if (!v) return null; if (v.type === 'ObjectExpression') { const t = props(v).get('tableName'); return t ? A.staticString(t) : null; } return project.valueOf(facts, v, site.scopes); };
      const where = { file: facts.file, line: site.line };
      const t = tableArg(site.args[0]);
      if (op === 'sequelize.query') {
        const sql = site.args[0] ? project.valueOf(facts, site.args[0], site.scopes) : null;
        if (sql === null) { graph.unresolvedItem('migration', facts.file, site.line, A.snippet(site.text, site.node), 'migration SQL is built at run time'); continue; }
        const r = analyse(sql, ctx.dialect);
        if (r.ddl) db.applyDdl(db.migrated, r.ddl, 'migration', facts.file, site.line);
        else if (r.error && !r.missing) graph.unresolvedItem('migration', facts.file, site.line, sql.slice(0, 80), r.error);
        continue;
      }
      const ops = {
        createTable: () => { db.table(db.migrated, t, 'migration', where.file, where.line); for (const c of props(site.args[1]).keys()) if (c) db.column(db.migrated, t, c, 'migration', where.file, where.line); },
        addColumn: () => { const c = A.staticString(site.args[1]); if (c) db.column(db.migrated, t, c, 'migration', where.file, where.line); },
        removeColumn: () => db.applyDdl(db.migrated, [{ op: 'drop-column', table: t, column: A.staticString(site.args[1]) }]),
        renameColumn: () => db.applyDdl(db.migrated, [{ op: 'rename-column', table: t, from: A.staticString(site.args[1]), to: A.staticString(site.args[2]) }], 'migration', where.file, where.line),
        dropTable: () => db.applyDdl(db.migrated, [{ op: 'drop-table', table: t }]),
        renameTable: () => db.applyDdl(db.migrated, [{ op: 'rename-table', from: t, to: tableArg(site.args[1]) }]),
      };
      if (!ops[op]) continue;
      if (!t) { graph.unresolvedItem('migration', facts.file, site.line, A.snippet(site.text, site.node), 'table name is not a literal'); continue; }
      ops[op]();
    }
  }

  // Model calls in code.
  let calls = 0;
  for (const facts of project.facts.values()) {
    for (const site of facts.callSites) {
      if (site.rootType !== 'id' || !site.binding) continue;
      let model = null;
      let rest = site.path;
      const b = site.binding;
      if (modelBindings.has(b)) model = modelBindings.get(b);
      else if (b.import) {
        const t = project.bindingTarget(facts, b);
        if (t && t.file && indexFiles.has(t.file)) {
          const imported = t.member || t.imported;
          if (imported === '*' || imported === 'default') { model = rest[0]; rest = rest.slice(1); } else model = imported;
        }
      } else if (b.init && A.isMember(A.unwrap(b.init))) {
        const chain = A.memberChain(b.init);
        const rb = chain.root && chain.root.type === 'Identifier' ? lookup(site.scopes, chain.root.name) : null;
        const t = rb && rb.import ? project.bindingTarget(facts, rb) : null;
        if (t && t.file && indexFiles.has(t.file) && chain.path.length === 1) model = chain.path[0];
      }
      if (!model || !db.models.has(model) || rest.length !== 1) continue;
      const op = rest[0];
      if (!READ_OPS.has(op) && !WRITE_OPS.has(op)) continue;
      if (RECORD_OPS.has(op)) { if (!db.recordCalls) db.recordCalls = new Map(); db.recordCalls.set(site.node, model); }
      calls++;
      modelCall(ctx, facts, site, model, op);
    }
  }
  graph.cover('orm:sequelize', db.models.size || migrations ? 'mapped' : 'not used', { models: [...db.models.values()].filter((m) => m.framework === 'sequelize').length, migrations, calls, modelDirs, migrationDirs });
}

function defineModel(ctx, facts, name, attrsNode, optsNode, line) {
  const { db } = ctx;
  const opts = props(optsNode);
  const str = (k) => (opts.get(k) ? A.staticString(opts.get(k)) : null);
  const bool = (k, d) => { const v = opts.get(k) && A.unwrap(opts.get(k)); return v && v.type === 'BooleanLiteral' ? v.value : d; };
  let table = str('tableName');
  if (!table && bool('freezeTableName', false)) table = name;
  if (!table) ctx.graph.unresolvedItem('model-table', facts.file, line, name, 'no tableName: Sequelize derives the table name at run time');
  const underscored = bool('underscored', false);
  const m = db.model(name, 'sequelize', table, facts.file, line);
  m.underscored = underscored;
  let hasPk = false;
  for (const [attr, value] of props(attrsNode)) {
    if (!attr) continue;
    const v = props(value);
    const field = v.get('field') ? A.staticString(v.get('field')) : null;
    const typeNode = A.unwrap(v.get('type') || value);
    const typeChain = A.memberChain(A.isCall(typeNode) ? typeNode.callee : typeNode);
    const virtual = typeChain.path[typeChain.path.length - 1] === 'VIRTUAL';
    if (v.get('primaryKey') && A.unwrap(v.get('primaryKey')).value === true) hasPk = true;
    db.attribute(m, attr, field || (underscored ? snake(attr) : attr), virtual);
  }
  if (!hasPk && !m.attributes.has('id')) db.attribute(m, 'id', 'id');
  if (bool('timestamps', true)) {
    for (const key of ['createdAt', 'updatedAt']) {
      const v = opts.get(key) ? A.unwrap(opts.get(key)) : null;
      if (v && v.type === 'BooleanLiteral' && !v.value) continue;
      const attr = v && v.type === 'StringLiteral' ? v.value : key;
      db.attribute(m, attr, underscored ? snake(attr) : attr);
    }
    if (bool('paranoid', false)) db.attribute(m, 'deletedAt', underscored ? 'deleted_at' : 'deletedAt');
  }
}

// Columns a model call names in its options and data.
function modelCall(ctx, facts, site, model, op) {
  const { db } = ctx;
  const add = (attr, access, m = model) => { if (attr && !attr.includes('$') && !attr.includes('.')) db.ref({ via: 'sequelize', model: m, attr, access, file: facts.file, line: site.line, owner: site.owner }); };
  const whereKeys = (node, m) => {
    node = A.unwrap(node);
    if (!node) return;
    if (node.type === 'ArrayExpression') { node.elements.forEach((e) => whereKeys(e, m)); return; }
    if (node.type !== 'ObjectExpression') return;
    for (const p of node.properties) {
      if (p.type !== 'ObjectProperty') continue;
      if (p.computed && A.keyName(p.key, true) === null) { whereKeys(p.value, m); continue; }
      add(A.keyName(p.key, p.computed), 'read', m);
    }
  };
  const options = (node, m) => {
    const o = props(node);
    whereKeys(o.get('where'), m);
    const attrs = o.get('attributes') && A.unwrap(o.get('attributes'));
    const list = attrs && attrs.type === 'ObjectExpression' ? [...['include', 'exclude'].map((k) => props(attrs).get(k))] : [attrs];
    for (const l of list) {
      const arr = l && A.unwrap(l);
      if (!arr || arr.type !== 'ArrayExpression') continue;
      for (const el of arr.elements) {
        const e = A.unwrap(el);
        if (!e) continue;
        if (e.type === 'StringLiteral') add(e.value, 'read', m);
        else if (e.type === 'ArrayExpression' && e.elements[0] && A.unwrap(e.elements[0]).type === 'StringLiteral') add(A.unwrap(e.elements[0]).value, 'read', m);
      }
    }
    for (const k of ['order', 'group']) {
      const v = o.get(k) && A.unwrap(o.get(k));
      if (!v) continue;
      if (v.type === 'StringLiteral') add(v.value, 'read', m);
      if (v.type === 'ArrayExpression') for (const el of v.elements) {
        const e = el && A.unwrap(el);
        if (e && e.type === 'StringLiteral') add(e.value, 'read', m);
        if (e && e.type === 'ArrayExpression' && e.elements[0] && A.unwrap(e.elements[0]).type === 'StringLiteral') add(A.unwrap(e.elements[0]).value, 'read', m);
      }
    }
    const include = o.get('include') && A.unwrap(o.get('include'));
    const includes = include ? (include.type === 'ArrayExpression' ? include.elements : [include]) : [];
    for (const inc of includes) {
      const i = inc && A.unwrap(inc);
      if (!i) continue;
      const modelNode = i.type === 'ObjectExpression' ? props(i).get('model') : i;
      const chain = modelNode ? A.memberChain(modelNode) : null;
      const target = chain ? (chain.path.length ? chain.path[chain.path.length - 1] : chain.root && chain.root.name) : null;
      if (target && ctx.db.models.has(target)) {
        ctx.graph.edge('reads-model', (site.owner ? `fn:${site.owner}` : `file:${facts.file}`), `model:${target}`, { file: facts.file, line: site.line, via: 'include' });
        if (i.type === 'ObjectExpression') options(i, target);
      }
    }
  };
  const dataKeys = (node, access) => {
    node = A.unwrap(node);
    if (!node) return;
    if (node.type === 'ArrayExpression') { node.elements.forEach((e) => dataKeys(e, access)); return; }
    if (node.type !== 'ObjectExpression') return;
    for (const p of node.properties) if (p.type === 'ObjectProperty') add(A.keyName(p.key, p.computed), access);
  };
  const [a0, a1] = site.args;
  if (READ_OPS.has(op)) {
    if (op === 'findByPk') { options(a1, model); return; }
    if (op === 'count' || op === 'max' || op === 'min' || op === 'sum') {
      const s = a0 && A.staticString(a0);
      if (s !== null && s !== undefined && op !== 'count') { add(s, 'read'); options(a1, model); } else options(a0, model);
      return;
    }
    options(a0, model);
    return;
  }
  if (op === 'create' || op === 'bulkCreate' || op === 'upsert') { dataKeys(a0, 'write'); options(a1, model); return; }
  if (op === 'update') { dataKeys(a0, 'write'); options(a1, model); return; }
  if (op === 'destroy' || op === 'restore') { options(a0, model); db.ref({ via: 'sequelize', model, access: op === 'destroy' ? 'delete' : 'write', file: facts.file, line: site.line, owner: site.owner }); return; }
  if (op === 'increment' || op === 'decrement') {
    const v = a0 && A.unwrap(a0);
    if (v && v.type === 'StringLiteral') add(v.value, 'write');
    else if (v && v.type === 'ArrayExpression') v.elements.forEach((e) => e && A.unwrap(e).type === 'StringLiteral' && add(A.unwrap(e).value, 'write'));
    else dataKeys(v, 'write');
    options(a1, model);
  }
}

module.exports = { sequelizeAdapter, snake };
