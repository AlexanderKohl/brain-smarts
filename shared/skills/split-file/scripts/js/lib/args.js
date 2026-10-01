'use strict';
// Command-line options for the split tools: positional arguments, `--name value` options and
// `--flag` switches. Part of the split-file skill (canonical copy: /shared/skills/split-file/).

function parseArgs(argv, { flags = [], usage = '' } = {}) {
  const positional = [];
  const options = {};
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (!a.startsWith('--')) { positional.push(a); continue; }
    const name = a.slice(2);
    if (flags.includes(name)) { options[name] = true; continue; }
    if (i + 1 >= argv.length) fail(`--${name} needs a value`, usage);
    options[name] = argv[i + 1];
    i += 1;
  }
  return { positional, options };
}

function fail(message, usage = '') {
  process.stderr.write(`${message}\n${usage ? `${usage}\n` : ''}`);
  process.exit(2);
}

// Runs a command's main function; a refusal (an Error) prints its message and exits 1.
function run(main) {
  try {
    main();
  } catch (err) {
    process.stderr.write(`refused: ${err.message}\n`);
    process.exit(1);
  }
}

// The comment line naming where moved code came from, with the optional reference (a task id).
function movedFrom(base, ref) {
  return `Moved unchanged from ${base}${ref ? ` (${ref})` : ''}.`;
}

module.exports = { parseArgs, fail, run, movedFrom };
