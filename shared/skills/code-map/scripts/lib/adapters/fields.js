'use strict';
// Data fields: every property path the code reads or sets (`contactDetails.entity_type`), with the
// literal values it is compared with, the default it falls back to, and where the object it hangs off
// came from, as the code states it. Fields in templates (Vue <template>, EJS, Handlebars, Jinja) are
// read from their expressions. A record loaded through a model links its fields to the columns.
// Keys in the repository's JSON files that match a field path are listed as declaring it. Fields with
// the same path on different objects share one node: that is matching text, never a claim they are
// the same object. Part of the code-map skill (canonical copy: /shared/skills/code-map/).

const A = require('../js/ast');
const { readText } = require('../files');

// Template files by extension, and the delimiters their expressions sit in.
const TEMPLATE_EXT = {
  ejs: [/<%(?!#)[=\-_]?([\s\S]*?)[-_]?%>/g],
  hbs: [/\{\{\{?([\s\S]*?)\}?\}\}/g], handlebars: [/\{\{\{?([\s\S]*?)\}?\}\}/g], mustache: [/\{\{\{?([\s\S]*?)\}?\}\}/g],
  njk: [/\{\{([\s\S]*?)\}\}/g, /\{%([\s\S]*?)%\}/g], jinja: [/\{\{([\s\S]*?)\}\}/g, /\{%([\s\S]*?)%\}/g],
  jinja2: [/\{\{([\s\S]*?)\}\}/g, /\{%([\s\S]*?)%\}/g], j2: [/\{\{([\s\S]*?)\}\}/g, /\{%([\s\S]*?)%\}/g],
  liquid: [/\{\{([\s\S]*?)\}\}/g, /\{%([\s\S]*?)%\}/g],
};
const TEMPLATE_GLOBALS = new Set(['Math', 'JSON', 'Object', 'Array', 'Number', 'String', 'Date', 'console',
  'window', 'document', 'this', 'loop', 'forloop']);
const JSON_MAX_BYTES = 500000;

// Blank out string literals so paths inside them are not read, keeping every index in place.
function maskStrings(text) {
  return text.replace(/(['"`])(?:\\.|(?!\1)[^\\])*\1/g, (m) => m[0] + ' '.repeat(Math.max(0, m.length - 2)) + m[m.length - 1]);
}

// Fields in one template expression, by fixed rules on its text.
function templateFields(expr, line) {
  const out = [];
  const masked = maskStrings(expr);
  const re = /(?<![\w$.])([A-Za-z_$][\w$]*)((?:\s*\??\.\s*[A-Za-z_$][\w$]*)+)(\s*\()?/g;
  let m;
  while ((m = re.exec(masked))) {
    if (TEMPLATE_GLOBALS.has(m[1])) continue;
    const path = m[2].split(/\??\./).map((x) => x.trim()).filter(Boolean);
    if (m[3]) path.pop();
    if (!path.length) continue;
    const end = m.index + m[0].length - (m[3] ? m[3].length : 0);
    const after = expr.slice(end);
    const before = expr.slice(0, m.index);
    const cmp = /^\s*(?:===?|!==?)\s*(['"])(.*?)\1/.exec(after) || /(['"])([^'"]*?)\1\s*(?:===?|!==?)\s*$/.exec(before);
    const dflt = /^\s*(?:\|\||\?\?|or)\s*(['"])(.*?)\1/.exec(after) || /^\s*\|\s*default\(\s*(['"])(.*?)\1/.exec(after);
    out.push({ path, root: m[1], line: line + (expr.slice(0, m.index).match(/\n/g) || []).length, compared: cmp ? [cmp[2]] : null, fallback: dflt ? dflt[2] : null });
  }
  return out;
}

function flattenKeys(value, prefix, out, depth) {
  if (depth > 4 || !value || typeof value !== 'object') return;
  if (Array.isArray(value)) { for (const v of value.slice(0, 20)) flattenKeys(v, prefix, out, depth + 1); return; }
  for (const [k, v] of Object.entries(value)) {
    const key = prefix ? `${prefix}.${k}` : k;
    out.add(key);
    flattenKeys(v, key, out, depth + 1);
  }
}

function originText(o) {
  if (!o) return undefined;
  if (o.kind === 'parameter') return `parameter ${o.name}`;
  if (o.kind === 'value') return `${o.name} = ${o.text}`;
  return `${o.kind} ${o.name}`;
}

function fieldsAdapter(ctx) {
  const { graph, project, db } = ctx;
  const fieldId = (path) => {
    const id = `field:${path.join('.')}`;
    if (!graph.nodes.has(id)) graph.node(id, 'field', { path: path.join('.'), name: path[path.length - 1] });
    return id;
  };
  const isTest = (file) => !!(ctx.fileIndex.get(file) || {}).test;
  let reads = 0; let writes = 0; let templates = 0; let columns = 0;

  for (const facts of project.facts.values()) {
    const test = isTest(facts.file) || undefined;
    for (const f of facts.fields) {
      const id = fieldId(f.path);
      const from = f.owner ? `fn:${f.owner}` : `file:${facts.file}`;
      graph.edge(f.write ? 'writes-field' : 'reads-field', from, id, {
        file: facts.file, line: f.line, compared: f.compared && f.compared.length ? f.compared : undefined,
        fallback: f.fallback === null ? undefined : f.fallback, origin: originText(f.origin), literal: f.literal || undefined, test,
      });
      if (f.write) writes++; else reads++;
      // A field of a record loaded through a model is that model's column.
      let init = f.initNode;
      if (init && init.type === 'AwaitExpression') init = A.unwrap(init.argument);
      const model = init && db.recordCalls ? db.recordCalls.get(init) : null;
      const m = model ? db.models.get(model) : null;
      if (m && m.table) {
        const attr = m.attributes.get(f.path[0]);
        const column = attr && !attr.virtual ? attr.column : [...m.attributes.values()].some((a) => a.column === f.path[0]) ? f.path[0] : null;
        if (column) { graph.edge(f.write ? 'writes-column' : 'reads-column', from, `column:${m.table}.${column}`, { file: facts.file, line: f.line, via: 'record' }); columns++; }
      }
    }
    for (const t of facts.templateExprs || []) {
      for (const f of templateFields(t.text, t.line)) {
        graph.edge('reads-field', `file:${facts.file}`, fieldId(f.path), { file: facts.file, line: f.line, compared: f.compared || undefined, fallback: f.fallback === null ? undefined : f.fallback, template: 'vue', test });
        templates++;
      }
    }
  }

  const templateFiles = [];
  for (const e of ctx.files) {
    const patterns = TEMPLATE_EXT[e.ext];
    if (!patterns) continue;
    const text = readText(ctx.root, e);
    if (!text) continue;
    templateFiles.push(e.file);
    for (const re of patterns) {
      re.lastIndex = 0;
      let m;
      while ((m = re.exec(text))) {
        const line = text.slice(0, m.index).split('\n').length;
        for (const f of templateFields(m[1], line)) {
          graph.edge('reads-field', `file:${e.file}`, fieldId(f.path), { file: e.file, line: f.line, compared: f.compared || undefined, fallback: f.fallback === null ? undefined : f.fallback, template: e.ext, test: isTest(e.file) || undefined });
          templates++;
        }
      }
    }
  }

  // JSON files that hold a key with the same path as a field declare it (schemas, examples, defaults).
  let declared = 0;
  for (const e of ctx.files) {
    if (e.ext !== 'json' || /(^|\/)(package(-lock)?|tsconfig|jsconfig|composer)\.json$/.test(e.file) || (e.size && e.size > JSON_MAX_BYTES)) continue;
    const text = readText(ctx.root, e);
    if (!text || text.length > JSON_MAX_BYTES) continue;
    let value;
    try { value = JSON.parse(text); } catch { continue; }
    const keys = new Set();
    flattenKeys(value, '', keys, 0);
    for (const k of keys) {
      const id = `field:${k}`;
      if (!graph.nodes.has(id)) continue;
      graph.edge('declares-field', `file:${e.file}`, id, { file: e.file });
      declared++;
    }
  }
  graph.cover('data:fields', reads + writes + templates ? 'mapped' : 'not used',
    { reads, writes, templateReads: templates, templateFiles: templateFiles.length, recordColumns: columns, declaredInJson: declared });
}

module.exports = { fieldsAdapter, templateFields, TEMPLATE_EXT };
