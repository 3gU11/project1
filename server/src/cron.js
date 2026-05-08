/**
 * Cron job — hourly forecast recompute.
 *
 * Run standalone: node src/cron.js
 * Or via a process manager: pm2 start src/cron.js --cron "0 * * * *"
 */

require('dotenv').config();
const { fullRecompute } = require('./engine/predictor');

async function run() {
  console.log(`[${new Date().toISOString()}] Cron: Starting forecast recompute...`);
  try {
    const result = await fullRecompute();
    console.log(`[${new Date().toISOString()}] Cron: Complete`, result);
  } catch (err) {
    console.error(`[${new Date().toISOString()}] Cron: Failed —`, err.message);
  }
  process.exit(0);
}

run();
