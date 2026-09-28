#!/usr/bin/env node
'use strict';
// code-map: a deterministic map of a code repository, its checks, and a query for agents.
// Canonical copy: /shared/skills/code-map/ in the brain. Read SKILL.md beside this folder first.
//
//   code-map build   [repo] [--out FILE]              write the whole map as JSON
//   code-map check   [repo] [--records DIR] [--json]  run the checks; exit 1 when a new finding fails
//   code-map record  [repo] [--records DIR] [--adopt] write the committed records
//   code-map show    <name> [--repo DIR]              everything the map knows about a name or field
//   code-map find    <words…> [--repo DIR]            functions whose text holds the most of the words
//   code-map report  [repo] [--out FILE]              the generated inventory, as Markdown
//   code-map --version [--verbose]
// Common options: --config FILE (instead of <repo>/code-map.config.json).

const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const SKILL = path.resolve(__dirname, '..');
const pkg = JSON.parse(fs.readFileSync(path.join(SKILL, 'package.json'), 'utf8'));

function identity() {
  const id = { version: pkg.version, commit: null, dirty: false, branch: null };
  try {
    id.commit = execFileSync('git', ['-C', SKILL, 'log', '-1', '--format=%h', '--', '.'], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim() || null;
    id.dirty = execFileSync('git', ['-C', SKILL, 'status', '--porcelain', '--', '.'], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim().length > 0;
    id.branch = execFileSync('git', ['-C', SKILL, 'rev-parse', '--abbrev-ref', 'HEAD'], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim();
  } catch { /* not in a Git checkout: the version alone identifies the build */ }
  return id;
}

function parseArgs(argv) {
  const out = { _: [], flags: {} };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith('--')) {
      const [k, v] = a.slice(2).split('=');
      if (v !== undefined) out.flags[k] = v;
      else if (['out', 'records', 'config', 'repo', 'only', 'limit'].includes(k)) out.flags[k] = argv[++i];
      else out.flags[k] = true;
    } else out._.push(a);
  }
  return out;
}

function usage() {
  const text = fs.readFileSync(__filename, 'utf8').split('\n').filter((l) => l.startsWith('//   ') || l.startsWith('// Common')).map((l) => l.slice(3));
  return `code-map ${pkg.version}\n${text.join('\n')}`;
}

function load(repo, flags) {
  const { buildMap } = require('./lib/build');
  return buildMap(repo, { configFile: flags.config || null });
}

function main(argv) {
  const { _: args, flags } = parseArgs(argv);
  const cmd = args[0];
  if (flags.version || cmd === 'version') {
    const id = identity();
    console.log(flags.verbose ? `code-map ${id.version} (commit ${id.commit || 'unknown'}${id.dirty ? ', uncommitted changes' : ''}${id.branch && id.branch !== 'main' ? `, branch ${id.branch}` : ''})` : `code-map ${id.version}`);
    return 0;
  }
  if (!cmd || flags.help || cmd === 'help') { console.log(usage()); return cmd ? 0 : 2; }

  const { runChecks } = require('./lib/checks');
  const { loadRecords, writeRecords, recordDir } = require('./lib/records');
  const repoArg = cmd === 'show' || cmd === 'find' ? (flags.repo || '.') : (args[1] || '.');
  const repo = path.resolve(repoArg);
  if (!fs.existsSync(repo)) { console.error(`code-map: no such folder ${repo}`); return 2; }
  const map = load(repo, flags);
  const id = identity();

  if (cmd === 'build') {
    const json = JSON.stringify({ tool: { name: 'code-map', ...id }, root: path.basename(repo), ...map.graph.toJSON() }, null, 1);
    if (flags.out) { fs.mkdirSync(path.dirname(path.resolve(flags.out)), { recursive: true }); fs.writeFileSync(flags.out, json); console.log(`wrote ${flags.out}`); } else process.stdout.write(json);
    return 0;
  }
  const dir = recordDir(map, flags.records);
  const records = loadRecords(dir);
  const only = flags.only ? String(flags.only).split(',') : null;
  const result = runChecks(map, records, only);

  if (cmd === 'check') {
    if (flags.json) { console.log(JSON.stringify({ ok: result.ok, fixed: result.fixed, checks: result.byCheck }, null, 1)); return result.ok ? 0 : 1; }
    if (!records.present) console.log(`No records in ${dir} yet: every finding counts as new. Run \`code-map record --adopt\` once to accept what exists today.`);
    for (const [cid, c] of Object.entries(result.byCheck)) {
      const mark = !c.new.length ? 'ok  ' : c.fails ? 'FAIL' : 'note';
      console.log(`${mark} ${cid.padEnd(9)} ${c.title} – ${c.findings.length} finding(s), ${c.new.length} new`);
      for (const f of c.new.slice(0, 20)) console.log(`       ${f.file ? `${f.file}${f.line ? `:${f.line}` : ''}  ` : ''}${f.message}`);
      if (c.new.length > 20) console.log(`       … ${c.new.length - 20} more`);
    }
    if (result.fixed.length) console.log(`Fixed since the record (run \`code-map record\` to drop them): ${result.fixed.length}`);
    const cov = map.graph.coverage.filter((c) => !['mapped', 'not used'].includes(c.status));
    if (cov.length) console.log(`Not fully covered: ${cov.map((c) => `${c.area} (${c.status})`).join(', ')}`);
    console.log(result.ok ? 'code-map check: passed' : `code-map check: failed – ${result.failing.length} new finding(s)`);
    return result.ok ? 0 : 1;
  }
  if (cmd === 'record') {
    const r = writeRecords(map, dir, result, { adopt: !!flags.adopt });
    console.log(`wrote ${path.relative(process.cwd(), r.dir) || '.'}: ${r.sizes} oversized file(s) recorded, ${r.known} known finding(s)`);
    return 0;
  }
  if (cmd === 'show') {
    const { show } = require('./lib/query');
    if (!args[1]) { console.error('code-map show: name what to show'); return 2; }
    console.log(show(map, args.slice(1).join(' '), { limit: flags.limit ? Number(flags.limit) : undefined }));
    return 0;
  }
  if (cmd === 'find') {
    const { findWords } = require('./lib/query');
    if (!args[1]) { console.error('code-map find: name the words to look for'); return 2; }
    console.log(findWords(map, args.slice(1).join(' '), { top: flags.limit ? Number(flags.limit) : undefined }));
    return 0;
  }
  if (cmd === 'report') {
    const { report } = require('./lib/report');
    const text = report(map, result, { name: path.basename(repo), version: id.version, commit: id.commit });
    if (flags.out) { fs.writeFileSync(flags.out, `${text}\n`); console.log(`wrote ${flags.out}`); } else console.log(text);
    return 0;
  }
  console.error(`code-map: unknown command ${cmd}\n${usage()}`);
  return 2;
}

try {
  process.exitCode = main(process.argv.slice(2));
} catch (err) {
  console.error(`code-map: ${err.message}`);
  process.exitCode = 2;
}
