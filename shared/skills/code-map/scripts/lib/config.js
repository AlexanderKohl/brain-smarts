'use strict';
// Project configuration: `code-map.config.json` at the repository root. Everything in it is a
// declaration the project makes about itself; the code map never guesses what it leaves out.
// Part of the code-map skill (canonical copy: /shared/skills/code-map/).

const fs = require('fs');
const path = require('path');

const CONFIG_FILE = 'code-map.config.json';

const DEFAULTS = {
  // Where the committed records live, relative to the repository root.
  recordDir: 'code-map',
  limits: { fileLines: 800, functionLines: 150 },
  // Files never mapped at all.
  ignore: ['**/node_modules/**', '**/dist/**', '**/build/**', '**/.next/**', '**/out/**', '**/coverage/**',
    '**/vendor/**', '**/*.min.js', '**/*.map', '**/.git/**', '**/__pycache__/**'],
  // Files mapped but exempt from the size limit (generated, data, migrations, fixtures, vendored).
  sizeExempt: ['**/migrations/**', '**/seeders/**', '**/fixtures/**', '**/__fixtures__/**', '**/*.generated.*',
    '**/generated/**', '**/*.d.ts', '**/package-lock.json', '**/*.lock'],
  // Code files the size rule counts, by extension.
  codeExtensions: ['js', 'mjs', 'cjs', 'jsx', 'ts', 'mts', 'cts', 'tsx', 'vue', 'svelte', 'py', 'ps1', 'psm1', 'sh',
    'bash', 'php', 'go', 'rb', 'cs', 'java', 'kt', 'swift', 'rs', 'ejs', 'sql'],
  tests: ['**/tests/**', '**/test/**', '**/__tests__/**', '**/*.test.*', '**/*.spec.*', '**/e2e/**'],
  aliases: [],
  next: [],
  http: { urlBuilders: [], wrappers: [], env: {} },
  database: { dialect: null },
  sequelize: { models: [], migrations: [], modelsIndex: [] },
  prisma: { clients: ['prisma', 'tx'] },
  env: { files: null, ignore: ['NODE_ENV', 'CI', 'HOME', 'PATH', 'TEMP', 'TMP', 'USERPROFILE', 'APPDATA',
    'LOCALAPPDATA', 'npm_*', 'MODE', 'DEV', 'PROD', 'SSR', 'BASE_URL', 'NEXT_RUNTIME'] },
  settings: { loaders: [], names: [], files: [], open: [], enforce: false },
  notes: ['brain/**/*.md'],
  python: { command: null, roots: [] },
  checks: {},
};

function merge(base, extra) {
  if (Array.isArray(base) || Array.isArray(extra)) return extra === undefined ? base : extra;
  if (base && typeof base === 'object' && extra && typeof extra === 'object') {
    const out = { ...base };
    for (const key of Object.keys(extra)) out[key] = merge(base[key], extra[key]);
    return out;
  }
  return extra === undefined ? base : extra;
}

// `configFile` overrides the repository's own file (for running on a copy that has none).
function loadConfig(root, configFile = null) {
  const file = configFile ? path.resolve(configFile) : path.join(root, CONFIG_FILE);
  let own = {};
  if (fs.existsSync(file)) {
    try { own = JSON.parse(fs.readFileSync(file, 'utf8')); } catch (err) {
      throw new Error(`${path.basename(file)} is not valid JSON: ${err.message}`);
    }
  }
  const config = merge(DEFAULTS, own);
  config.present = fs.existsSync(file);
  // Extra ignore and exempt patterns add to the defaults rather than replace them.
  if (own.ignoreMore) config.ignore = [...DEFAULTS.ignore, ...own.ignoreMore];
  if (own.sizeExemptMore) config.sizeExempt = [...DEFAULTS.sizeExempt, ...own.sizeExemptMore];
  if (own.env && own.env.ignoreMore) config.env.ignore = [...DEFAULTS.env.ignore, ...own.env.ignoreMore];
  return config;
}

// Minimal glob: `**` any path, `*` within one segment, `?` one character.
const globCache = new Map();
function globToRegExp(glob) {
  if (globCache.has(glob)) return globCache.get(glob);
  let re = '';
  for (let i = 0; i < glob.length; i++) {
    const c = glob[i];
    if (c === '*' && glob[i + 1] === '*') {
      if (glob[i + 2] === '/') { re += '(?:.*/)?'; i += 2; } else { re += '.*'; i += 1; }
    } else if (c === '*') re += '[^/]*';
    else if (c === '?') re += '[^/]';
    else re += c.replace(/[.+^${}()|[\]\\]/g, '\\$&');
  }
  const out = new RegExp(`^${re}$`);
  globCache.set(glob, out);
  return out;
}

function matchesAny(file, globs) {
  return (globs || []).some((g) => globToRegExp(g).test(file));
}

module.exports = { loadConfig, matchesAny, globToRegExp, CONFIG_FILE, DEFAULTS };
