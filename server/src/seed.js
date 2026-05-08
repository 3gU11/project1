/**
 * Seed script — populate system with demo data for development.
 *
 * Run: node src/seed.js
 */
require('dotenv').config();
const db = require('./db');

async function seed() {
  console.log('Seeding demo data...');

  // Create demo admin user
  await db.query(`
    INSERT INTO users (username, password, role, name, status, region, register_time)
    VALUES ('admin', 'admin123', 'boss', '管理员', 'active', 'guangdong', NOW())
    ON DUPLICATE KEY UPDATE username=username
  `);

  // Create demo sales user
  await db.query(`
    INSERT INTO users (username, password, role, name, status, region, register_time)
    VALUES ('sales1', 'sales123', 'sales', '销售张三', 'active', 'guangdong', NOW())
    ON DUPLICATE KEY UPDATE username=username
  `);

  // Ensure model_dictionary has entries
  const models = [
    ['G', 1, 1, ''],
    ['XS', 2, 1, ''],
    ['AUTO', 3, 1, ''],
  ];
  for (const [name, order, enabled, remark] of models) {
    await db.query(`
      INSERT INTO model_dictionary (model_name, sort_order, enabled, remark)
      VALUES (?, ?, ?, ?)
      ON DUPLICATE KEY UPDATE enabled=1
    `, [name, order, enabled, remark]);
  }

  console.log('Seeding complete.');
  process.exit(0);
}

seed().catch(err => { console.error(err); process.exit(1); });
