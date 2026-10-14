// The rest of a fictional garden club's program: it imports the seed module's names (fixture for
// the split-file ES module tests).
import seasonCount, {
  SEASONS, SWAP_DAY, packetTotal, recordSwap, seasonTitle, seedLabel, sowingMonths,
} from './seeds.mjs';

console.log(JSON.stringify([
  seasonCount(),
  SEASONS,
  SWAP_DAY,
  packetTotal(['bean', 'herb', 'radish']),
  recordSwap(),
  recordSwap(),
  seasonTitle('autumn'),
  seedLabel('  Purple   climbing bean of the old orchard ', 'bean'),
  sowingMonths('spring'),
]));
