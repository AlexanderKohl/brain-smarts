// Routes whose paths are computed: the map cannot know them, so a UI call under /api/jobs must be left
// unresolved rather than reported as broken.
const express = require('express');

function createJobsRouter() {
  const router = express.Router();
  for (const name of ['rebuild', 'cleanup']) {
    router.post(`/${name}`, (req, res) => res.json({ job: name }));
  }
  return router;
}

module.exports = { createJobsRouter };
