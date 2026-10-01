'use strict';
// A file whose top-level `let` is reassigned while the app runs, and routes that shadow it
// (fixture for the split-file tests).
const { Router } = require('./router');

const router = Router();
let settings = { theme: 'light' };

router.use(function reload(req, res, next) {
  settings = { theme: (req.query && req.query.theme) || 'light' };
  next();
});

// Reads its own settings, not the file's.
router.get('/local', function local(req, res) {
  const settings = { theme: 'own' };
  res.json({ theme: settings.theme });
});

router.get('/param', function param(req, res) {
  const show = (settings) => settings.theme;
  res.json({ theme: show({ theme: 'given' }) });
});

// Reads the file's settings.
router.get('/shared', function shared(req, res) {
  res.json({ theme: settings.theme });
});

module.exports = router;
