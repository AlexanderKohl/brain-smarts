'use strict';
// Routes and helpers of a fictional garden club: the file the split-file tests split.

const { Router } = require('./router');
const store = require('./store');
const { plants } = store;

const router = Router();
const MAX_NAME = 40;

// Trims a plant name and checks its length.
function cleanName(name) {
  const trimmed = String(name || '').trim();
  if (!trimmed || trimmed.length > MAX_NAME) throw new Error('bad name');
  return trimmed;
}

function describePlant(plant) {
  return `${plant.name} (${plant.kind})`;
}

function wateringDays(kind) {
  return { herb: 2, tree: 7 }[kind] || 3;
}

let visits = 0;
const started = Date.now();

class Greenhouse {
  constructor(name) {
    this.name = name;
    this.beds = [];
  }

  addBed(bed) {
    this.beds.push(bed);
    return this;
  }

  // Counts the plants across all beds.
  countPlants() {
    return this.beds.reduce((sum, bed) => sum + bed.length, 0);
  }

  describe() {
    return `${this.name}: ${this.countPlants()} plants`;
  }

  static make(name) {
    return new Greenhouse(name);
  }

  get size() {
    return this.beds.length;
  }

  label() {
    return `${this.name.slice(0, MAX_NAME)}`;
  }
}

class Shed extends Greenhouse {
  describe() {
    return `shed ${super.describe()}`;
  }
}

router.use(function countVisit(req, res, next) {
  visits += 1;
  next();
});

// Plant routes.
router.get('/plants', function listPlants(req, res) {
  res.json([...plants.values()].map(describePlant));
});

router.post('/plants', function addPlant(req, res) {
  const name = cleanName(req.body.name);
  plants.set(name, { name, kind: req.body.kind });
  res.json({ ok: true });
});

router.get('/plants/:kind/water', function water(req, res) {
  res.json({ days: wateringDays(req.params.kind) });
});

// Visit routes.
router.get('/visits', function countVisits(req, res) {
  res.json({ visits, since: started });
});

router.get('/self', function self(req, res) {
  res.json({ keys: Object.keys(module.exports) });
});

router.get('/late', function late(req, res) {
  res.json({ late: LATE });
});

const LATE = 'after';

module.exports = router;
module.exports.cleanName = cleanName;
module.exports.describePlant = describePlant;
module.exports.wateringDays = wateringDays;
module.exports.Greenhouse = Greenhouse;
module.exports.Shed = Shed;
