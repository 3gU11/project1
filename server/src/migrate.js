/**
 * Database migration script — creates new tables and alters existing ones
 * per PRD V2.2 data model.
 *
 * Run: node src/migrate.js
 */
require('dotenv').config();
const db = require('./db');

const migrations = [
  // 3.2.1 batches table
  `CREATE TABLE IF NOT EXISTS batches (
    batch_id            VARCHAR(64)  NOT NULL COMMENT 'BATCH-YYYYMM-NNN',
    batch_no            INT          NOT NULL,
    batch_code          VARCHAR(64)  NULL COMMENT 'Business batch code',
    model_type          VARCHAR(100) NOT NULL COMMENT 'Single model per batch',
    capacity            INT          NOT NULL COMMENT 'G/XS=30, AUTO=27',
    status              VARCHAR(32)  NOT NULL DEFAULT 'Predicted'
      COMMENT 'Predicted / Confirmed / In_Production / Completed',
    due_date_start      DATE         NULL,
    due_date_end        DATE         NULL,
    capacity_snapshot   JSON         NULL COMMENT 'Capacity ratio snapshot at generation',
    source              VARCHAR(32)  NOT NULL DEFAULT 'algorithm'
      COMMENT 'algorithm / manual',
    production_line_id  VARCHAR(64)  NULL,
    created_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
      ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (batch_id),
    INDEX idx_batches_status (status),
    INDEX idx_batches_model (model_type),
    INDEX idx_batches_line (production_line_id)
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4`,

  // 3.2.2 units table
  `CREATE TABLE IF NOT EXISTS units (
    unit_id             VARCHAR(64)  NOT NULL,
    serial_no           VARCHAR(100) NULL COMMENT 'Serial from finished_goods_data',
    forecast_serial_no  VARCHAR(64)  NULL COMMENT 'Forecast serial generated on batch confirm',
    batch_id            VARCHAR(64)  NOT NULL,
    slot_index          INT          NOT NULL COMMENT '1~30 position within batch',
    model_type          VARCHAR(100) NOT NULL COMMENT 'Must match batch.model_type',
    production_line_id  VARCHAR(64)  NULL,
    status              VARCHAR(32)  NOT NULL DEFAULT 'Pending'
      COMMENT 'Pending / In_Production / In_Warehouse / Spot_Inventory / Sold',
    contract_no         VARCHAR(100) NULL,
    customer            VARCHAR(255) NULL,
    dealer_id           VARCHAR(64)  NULL,
    sales_id            VARCHAR(64)  NULL,
    order_remark        VARCHAR(500) NULL,
    is_locked           TINYINT(1)   NOT NULL DEFAULT 0,
    locked_by           VARCHAR(100) NULL,
    locked_at           DATETIME     NULL,
    is_contract_pinned  TINYINT(1)   NOT NULL DEFAULT 0,
    created_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
      ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (unit_id),
    UNIQUE KEY uq_units_batch_slot (batch_id, slot_index),
    INDEX idx_units_batch (batch_id),
    INDEX idx_units_line_status (production_line_id, status),
    INDEX idx_units_locked (is_locked),
    INDEX idx_units_empty_container (status, contract_no, model_type, is_locked),
    CONSTRAINT fk_units_batch FOREIGN KEY (batch_id) REFERENCES batches(batch_id)
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4`,

  // 3.2.3 production_lines table
  `CREATE TABLE IF NOT EXISTS production_lines (
    line_id             VARCHAR(64)  NOT NULL,
    line_name           VARCHAR(100) NOT NULL,
    current_batch_id    VARCHAR(64)  NULL,
    status              VARCHAR(32)  NOT NULL DEFAULT 'Idle'
      COMMENT 'Idle / Busy / Maintenance',
    display_order       INT          NOT NULL DEFAULT 0,
    updated_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
      ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (line_id)
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4`,

  // 3.2.4 system_config table
  `CREATE TABLE IF NOT EXISTS system_config (
    config_key   VARCHAR(100) NOT NULL,
    config_value TEXT         NULL,
    description  VARCHAR(255) NULL,
    updated_by   VARCHAR(100) NULL,
    updated_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
      ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (config_key)
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4`,

  // 3.2.5 production_queue table
  `CREATE TABLE IF NOT EXISTS production_queue (
    id                 BIGINT       NOT NULL AUTO_INCREMENT,
    model_type         VARCHAR(100) NOT NULL,
    contract_no        VARCHAR(255) NOT NULL,
    customer           VARCHAR(255) NULL,
    dealer             VARCHAR(255) NULL,
    due_date           DATE         NOT NULL,
    quantity_remaining INT          NOT NULL COMMENT 'Remaining units not yet batched',
    status             VARCHAR(32)  DEFAULT 'Waiting'
      COMMENT 'Waiting / Pulled',
    created_at         DATETIME     DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_queue_model_due (model_type, due_date)
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4`,

  // ALTER users table
  `ALTER TABLE users
    ADD COLUMN IF NOT EXISTS region VARCHAR(50) NULL DEFAULT NULL
      COMMENT 'guangdong / non_guangdong' AFTER name`,

  `ALTER TABLE users
    ADD COLUMN IF NOT EXISTS wechat_openid VARCHAR(100) NULL DEFAULT NULL
      COMMENT 'WeChat mini-program login' AFTER region`,

  // Indexes for users
  `CREATE INDEX IF NOT EXISTS idx_users_region ON users(region)`,
  `CREATE INDEX IF NOT EXISTS idx_users_openid ON users(wechat_openid)`,
];

// Seed default config
const seedConfig = `
  INSERT IGNORE INTO system_config (config_key, config_value, description, updated_by) VALUES
    ('capacity_ratio',   '{"G":40,"XS":35,"AUTO":25}', 'Model batch count ratio', 'system'),
    ('model_capacity',   '{"G":30,"XS":30,"AUTO":27}', 'Per-batch capacity per model', 'system'),
    ('max_batch_slots',  '20',                          'Max predicted/confirmed batches', 'system'),
    ('batch_break_days', '30',                          'Gap threshold in days', 'system'),
    ('mes_webhook_secret','CHANGE_ME',                  'MES webhook HMAC secret', 'system')
`;

// Seed 20 production lines
const seedLines = [];
for (let i = 1; i <= 20; i++) {
  seedLines.push(`('line-${String(i).padStart(2, '0')}', '产线 ${i}', 'Idle', ${i})`);
}
const seedLinesSQL = `INSERT IGNORE INTO production_lines (line_id, line_name, status, display_order) VALUES ${seedLines.join(', ')}`;

async function run() {
  console.log('Running migrations...');
  for (const sql of migrations) {
    try {
      await db.query(sql);
      console.log('  OK:', sql.slice(0, 60).replace(/\n/g, ' '), '...');
    } catch (err) {
      if (err.code === 'ER_DUP_FIELDNAME' || err.code === 'ER_DUP_KEYNAME' || err.errno === 1060) {
        console.log('  SKIP (already exists):', sql.slice(0, 60).replace(/\n/g, ' '), '...');
      } else {
        console.error('  FAIL:', sql.slice(0, 60).replace(/\n/g, ' '), '...', err.message);
      }
    }
  }

  console.log('Seeding config...');
  await db.query(seedConfig);

  console.log('Seeding production lines...');
  await db.query(seedLinesSQL);

  console.log('Migration complete.');
  process.exit(0);
}

run().catch(err => { console.error(err); process.exit(1); });
