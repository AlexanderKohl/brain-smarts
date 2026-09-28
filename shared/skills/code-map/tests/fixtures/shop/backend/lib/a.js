// a.js and b.js load each other at startup: a cycle the check must report.
const b = require('./b');

function helper(value) {
  return b.twice(value);
}

module.exports = { helper };
