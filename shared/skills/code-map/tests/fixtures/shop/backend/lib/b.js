const a = require('./a');

function twice(value) {
  return [value, value];
}

// A require inside a function loads later, so c.js is not part of a startup cycle.
function late() {
  return require('./c').name;
}

module.exports = { twice, late, a };
