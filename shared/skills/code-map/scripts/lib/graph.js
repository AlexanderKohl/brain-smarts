'use strict';
// The map itself: typed nodes, typed edges, what could not be resolved, and what was covered.
// Every list is sorted before it is written, so two runs on the same code give the same output.
// Part of the code-map skill (canonical copy: /shared/skills/code-map/).

const cmp = (a, b) => (a < b ? -1 : a > b ? 1 : 0);

// Alphabetical with numbers compared as numbers (`a2` before `a10`).
function natural(a, b) {
  return String(a).localeCompare(String(b), 'en', { numeric: true, sensitivity: 'variant' });
}

class Graph {
  constructor() {
    this.nodes = new Map();
    this.edges = [];
    this.edgeKeys = new Set();
    this.unresolved = [];
    this.coverage = [];
  }

  node(id, type, props = {}) {
    const existing = this.nodes.get(id);
    if (existing) { Object.assign(existing, props); return existing; }
    const node = { id, type, ...props };
    this.nodes.set(id, node);
    return node;
  }

  edge(type, from, to, props = {}) {
    if (!from || !to) return;
    const key = `${type}\0${from}\0${to}\0${props.line || ''}\0${props.file || ''}`;
    if (this.edgeKeys.has(key)) return;
    this.edgeKeys.add(key);
    this.edges.push({ type, from, to, ...props });
  }

  unresolvedItem(kind, file, line, text, reason) {
    this.unresolved.push({ kind, file, line, text, reason });
  }

  cover(area, status, detail) {
    this.coverage.push({ area, status, ...detail });
  }

  ofType(type) {
    return [...this.nodes.values()].filter((n) => n.type === type);
  }

  edgesOf(type) {
    return this.edges.filter((e) => e.type === type);
  }

  toJSON() {
    const nodes = [...this.nodes.values()].sort((a, b) => cmp(a.type, b.type) || natural(a.id, b.id));
    const edges = this.edges.slice().sort((a, b) => cmp(a.type, b.type) || natural(a.from, b.from) || natural(a.to, b.to) || (a.line || 0) - (b.line || 0));
    const unresolved = this.unresolved.slice().sort((a, b) => cmp(a.kind, b.kind) || natural(a.file || '', b.file || '') || (a.line || 0) - (b.line || 0));
    const coverage = this.coverage.slice().sort((a, b) => natural(a.area, b.area));
    return { nodes, edges, unresolved, coverage };
  }
}

module.exports = { Graph, natural, cmp };
