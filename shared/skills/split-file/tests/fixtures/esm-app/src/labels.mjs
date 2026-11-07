// Label text for a fictional garden club (fixture for the split-file ES module tests).

export const LABEL_WIDTH = 24;

export function tidyLabel(name) {
  return String(name).trim().replace(/\s+/g, ' ');
}

export function titleCase(word) {
  return word.charAt(0).toUpperCase() + word.slice(1);
}
