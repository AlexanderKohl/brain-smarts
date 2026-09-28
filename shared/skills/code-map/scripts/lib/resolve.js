'use strict';
// Resolves an import specifier to a repository file, a package or a Node built-in, by the same
// fixed rules the runtimes use: relative paths, extensions, index files, and the aliases the project
// declares (code-map config, tsconfig/jsconfig `paths`, a literal Vite `resolve.alias`).
// Part of the code-map skill (canonical copy: /shared/skills/code-map/).

const path = require('path');
const { builtinModules } = require('module');

const CORE = new Set(builtinModules.flatMap((m) => [m, `node:${m}`]));
const EXTENSIONS = ['.js', '.ts', '.tsx', '.jsx', '.mjs', '.cjs', '.mts', '.cts', '.vue', '.json'];

class Resolver {
  constructor(fileSet, aliases) {
    this.files = fileSet; // Set of repo-relative paths
    // [{ scope: 'frontend/', from: '@/', to: 'frontend/src/' }], most specific scope first.
    this.aliases = aliases.slice().sort((a, b) => b.scope.length - a.scope.length || b.from.length - a.from.length);
    this.cache = new Map();
  }

  tryFile(candidate) {
    candidate = path.posix.normalize(candidate).replace(/^\.\//, '');
    if (candidate.startsWith('../')) return null;
    if (this.files.has(candidate)) return candidate;
    for (const ext of EXTENSIONS) if (this.files.has(candidate + ext)) return candidate + ext;
    // TypeScript ESM imports name the compiled `.js` file of a `.ts` source.
    const m = /\.(m|c)?js$/.exec(candidate);
    if (m) {
      const base = candidate.slice(0, -m[0].length);
      for (const ext of ['.ts', '.tsx', '.mts', '.cts']) if (this.files.has(base + ext)) return base + ext;
    }
    for (const ext of EXTENSIONS) if (this.files.has(`${candidate}/index${ext}`)) return `${candidate}/index${ext}`;
    return null;
  }

  // -> { file } | { package, core } | { unresolved }
  resolve(fromFile, specifier) {
    if (typeof specifier !== 'string') return { unresolved: true };
    const key = `${fromFile}\0${specifier}`;
    if (this.cache.has(key)) return this.cache.get(key);
    const out = this.compute(fromFile, specifier);
    this.cache.set(key, out);
    return out;
  }

  compute(fromFile, spec) {
    if (spec.startsWith('.') || spec.startsWith('/')) {
      const base = spec.startsWith('/') ? spec.slice(1) : path.posix.join(path.posix.dirname(fromFile), spec);
      const file = this.tryFile(base);
      return file ? { file } : { unresolved: true, specifier: spec };
    }
    for (const alias of this.aliases) {
      if (!fromFile.startsWith(alias.scope)) continue;
      if (spec === alias.from.replace(/\/$/, '') || spec.startsWith(alias.from)) {
        const rest = spec === alias.from.replace(/\/$/, '') ? '' : spec.slice(alias.from.length);
        const file = this.tryFile(path.posix.join(alias.to, rest));
        if (file) return { file, alias: alias.from };
      }
    }
    if (CORE.has(spec) || CORE.has(spec.split('/')[0])) return { package: spec.replace(/^node:/, ''), core: true };
    const parts = spec.split('/');
    const name = spec.startsWith('@') ? parts.slice(0, 2).join('/') : parts[0];
    return { package: name, subpath: parts.slice(spec.startsWith('@') ? 2 : 1).join('/') || null };
  }
}

module.exports = { Resolver, EXTENSIONS };
