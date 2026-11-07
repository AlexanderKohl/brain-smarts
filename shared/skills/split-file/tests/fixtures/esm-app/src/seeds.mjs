// Seed packets of a fictional garden club, as an ES module: the file the split-file ES module tests
// split.
import { tidyLabel as cleanLabel, LABEL_WIDTH, titleCase } from './labels.mjs';
import * as units from './units.mjs';
import catalogue from './catalogue.json' with { type: 'json' };

export const SEASONS = Object.freeze(['spring', 'summer', 'autumn', 'winter']);

// Grams in a packet of one kind, from the catalogue.
function packetGrams(kind) {
  return (catalogue.packets[kind] || catalogue.packets.default) * units.GRAMS_PER_SCOOP;
}

// One line for a seed label; the name is cut to the label's width.
export function seedLabel(name, kind) {
  return `${cleanLabel(name).slice(0, LABEL_WIDTH)} – ${packetGrams(kind)} g`;
}

export function sowingMonths(season) {
  return { spring: [9, 10, 11], summer: [12, 1, 2] }[season] || [];
}

export function packetTotal(kinds) {
  return kinds.reduce((sum, kind) => sum + packetGrams(kind), 0);
}

export function seasonTitle(season) {
  return titleCase(season);
}

let swaps = 0;

export function recordSwap() {
  swaps += 1;
  return swaps;
}

// Where the club's seed list lives, next to this file.
export function listFolder() {
  return new URL('.', import.meta.url).pathname;
}

const SWAP_DAY = 'first Saturday';
export { SWAP_DAY };

export default function seasonCount() {
  return SEASONS.length;
}
