// Runs the nightly job as its own process and reads its settings from the environment.
const path = require('path');
const { execFileSync } = require('child_process');

const LEGACY_LIMIT = 5;
let lastRun = null;

function readSetting(name, env = process.env) {
  return env[name];
}

function readFirst(names) {
  for (const n of names) {
    const value = readSetting(n);
    if (value) return value;
  }
  return null;
}

function runNightly() {
  lastRun = Date.now();
  const region = readSetting('SHOP_REGION') || readFirst(['SHOP_ZONE_OLD']);
  execFileSync(process.execPath, [path.join(__dirname, '..', 'jobs', 'nightly.js'), region]);
}

function runWeekly() {
  return runNightly();
}

module.exports = { runNightly, runWeekly };
