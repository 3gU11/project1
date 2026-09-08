const router = require('express').Router();
const db = require('../db');
const { authMiddleware, adminOnly } = require('../middleware/auth');
const { pullFromQueue, refillEmptySlots, normalizeModelFamily } = require('../engine/predictor');
const { acquireLock, releaseLock } = require('../redis');
const { getBatchAudit, appendChange } = require('../services/sandboxAudit');

router.use(authMiddleware);

// GET /api/batches 鈥?list batches with optional filters
router.get('/', async (req, res) => {
  const { status, model_type, unassigned } = req.query;
  let sql = `
    SELECT b.*,
      (SELECT COUNT(*) FROM units u WHERE u.batch_id = b.batch_id) as unit_count,
      (SELECT COUNT(*) FROM units u WHERE u.batch_id = b.batch_id AND u.contract_no IS NOT NULL) as contract_count,
      (SELECT COUNT(*) FROM units u WHERE u.batch_id = b.batch_id AND (u.contract_no IS NULL OR u.contract_no = '')) as stock_count,
      (SELECT MIN(u.due_date) FROM units u WHERE u.batch_id = b.batch_id AND u.contract_no IS NOT NULL) as earliest_due_date,
      EXISTS(SELECT 1 FROM sandbox_batch_baselines sb WHERE sb.batch_id = b.batch_id) as is_manually_adjusted,
      b.updated_at as last_recompute_at,
      'heuristic-edd-v1' as algorithm_version
    FROM batches b WHERE 1=1
  `;
  const params = [];

  if (status) {
    sql += ' AND b.status = ?';
    params.push(status);
  }
  if (model_type) {
    sql += ' AND b.model_type = ?';
    params.push(model_type);
  }
  if (unassigned === 'true') {
    sql += ' AND b.production_line_id IS NULL';
  }
  sql += ' ORDER BY b.model_type, b.batch_no';

  const [batches] = await db.query(sql, params);
  const batchIds = batches.map((b) => b.batch_id);
  let unitsByBatch = {};
  if (batchIds.length) {
    const [units] = await db.query(
      `SELECT
        u.*,
        COALESCE(md.model_name, NULLIF(fp.model_type_detail, ''), u.model_type) AS model_type_detail,
        COALESCE(NULLIF(u.dealer_id, ''), NULLIF(fp.dealer_name, '')) AS dealer_name,
        b.due_date_end AS promised_due_date
      FROM units u
      JOIN batches b ON b.batch_id = u.batch_id
      LEFT JOIN (
        SELECT
          contract_no,
          model_type_detail,
          MAX(dealer_name) AS dealer_name
        FROM (
          SELECT
            \`\u5408\u540c\u53f7\` AS contract_no,
            NULLIF(\`\u673a\u578b\`, '') AS model_type_detail,
            NULLIF(\`\u4ee3\u7406\u5546\`, '') AS dealer_name
          FROM factory_plan
          WHERE TRIM(COALESCE(\`状态\`, '')) = '待规划'
        ) x
        GROUP BY contract_no, model_type_detail
      ) fp ON fp.contract_no COLLATE utf8mb4_general_ci = u.contract_no COLLATE utf8mb4_general_ci
          AND fp.model_type_detail COLLATE utf8mb4_general_ci = u.model_type COLLATE utf8mb4_general_ci
      LEFT JOIN model_dictionary md
        ON md.enabled = 1
       AND UPPER(TRIM(md.model_name)) NOT IN ('G', 'XS', 'AUTO')
       AND md.model_name COLLATE utf8mb4_general_ci =
           COALESCE(NULLIF(fp.model_type_detail, ''), u.model_type) COLLATE utf8mb4_general_ci
      WHERE u.batch_id IN (?)
      ORDER BY u.batch_id, u.slot_index`,
      [batchIds]
    );
    unitsByBatch = units.reduce((acc, u) => {
      if (!acc[u.batch_id]) acc[u.batch_id] = [];
      acc[u.batch_id].push(u);
      return acc;
    }, {});
  }

  res.json({
    batches: batches.map((b) => {
      const units = unitsByBatch[b.batch_id] || [];
      const ordered_count = Number(b.contract_count || 0);
      const stock_count = Number(b.stock_count || 0);
      return {
        ...b,
        units,
        ordered_count,
        stock_count,
        empty_count: Math.max(0, Number(b.capacity || 0) - ordered_count - stock_count),
        ...(() => {
          const risks = [];
          const capacity = Number(b.capacity || 0);
          if (capacity > 0 && units.length > capacity) risks.push({ code: 'capacity_overflow', severity: 'error', blocking: true, message: `卡片数超出容量 ${units.length - capacity} 台`, unit_ids: units.slice(capacity).map((u) => String(u.unit_id)) });
          const batchFamily = normalizeModelFamily(b.model_type);
          const mismatched = units.filter((u) => batchFamily && normalizeModelFamily(u.model_type) && normalizeModelFamily(u.model_type) !== batchFamily);
          if (mismatched.length) risks.push({ code: 'model_family_mismatch', severity: 'error', blocking: true, message: `机型大类不匹配 ${mismatched.length} 台`, unit_ids: mismatched.map((u) => String(u.unit_id)) });
          const inbound = b.expected_inbound_date || b.due_date_end;
          const earliest = b.earliest_due_date;
          if (inbound && earliest) {
            const days = Math.ceil((new Date(inbound).getTime() - new Date(earliest).getTime()) / 86400000);
            if (days > 0) risks.push({ code: 'due_risk', severity: 'error', blocking: true, message: `预计入库晚于最早交期 ${days} 天`, unit_ids: units.filter((u) => String(u.due_date || '').slice(0, 10) === String(earliest).slice(0, 10)).map((u) => String(u.unit_id)) });
          }
          return { risk_count: risks.length, risks };
        })(),
      };
    })
  });
});

// GET /api/batches/:id 鈥?single batch with units
router.get('/:id', async (req, res) => {
  const [batches] = await db.query('SELECT * FROM batches WHERE batch_id = ?', [req.params.id]);
  if (!batches.length) return res.status(404).json({ error: 'Batch not found' });

  const [units] = await db.query(
    `SELECT * FROM units WHERE batch_id = ? ORDER BY slot_index`, [req.params.id]
  );

  res.json({ batch: batches[0], units });
});

// GET /api/batches/:id/audit - baseline and manual changes for the prediction-column drawer.
router.get('/:id/audit', async (req, res) => {
  try {
    const [batches] = await db.query('SELECT batch_id FROM batches WHERE batch_id = ?', [req.params.id]);
    if (!batches.length) return res.status(404).json({ error: 'Batch not found' });
    res.json(await getBatchAudit(req.params.id));
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// POST /api/batches/:id/confirm 鈥?approve batch, release slot, pull from queue
router.post('/:id/confirm', adminOnly, async (req, res) => {
  const batchCode = String(req.body?.batch_code || '').trim();
  const expectedInboundDate = String(req.body?.expected_inbound_date || '').trim();
  if (expectedInboundDate && !/^\d{4}-\d{2}-\d{2}$/.test(expectedInboundDate)) {
    return res.status(400).json({ error: 'expected_inbound_date format must be YYYY-MM-DD' });
  }
  let assignedBatchNo = null;
  if (batchCode) {
    const m = batchCode.match(/^(\d{2})-(\d{2})(?:[\u4e00-\u9fa5A-Za-z0-9_-]{0,20})$/);
    if (!m) return res.status(400).json({ error: 'batch_code format must start with MM-SS' });
    assignedBatchNo = Number(m[1]) * 100 + Number(m[2]);
  }

  const lockToken = await acquireLock('batch:slot', 30);
  if (!lockToken) return res.status(409).json({ error: 'Another operation in progress' });

  const conn = await db.getConnection();
  try {
    await conn.beginTransaction();

    const [batches] = await conn.query(
      'SELECT * FROM batches WHERE batch_id = ? FOR UPDATE', [req.params.id]
    );
    if (!batches.length) {
      await conn.rollback();
      return res.status(404).json({ error: 'Batch not found' });
    }
    const batch = batches[0];

    if (batch.status !== 'Predicted') {
      await conn.rollback();
      return res.status(400).json({ error: 'Only Predicted batches can be confirmed' });
    }

    const [unitCounts] = await conn.query(
      'SELECT COUNT(*) AS count FROM units WHERE batch_id = ?', [req.params.id]
    );
    if (Number(unitCounts[0]?.count || 0) > Number(batch.capacity || 0)) {
      await conn.rollback();
      return res.status(400).json({ error: 'Batch exceeds capacity and cannot be confirmed' });
    }

    if (assignedBatchNo !== null) {
      await conn.query(
        `UPDATE batches SET status = 'Confirmed', batch_no = ?, expected_inbound_date = COALESCE(?, expected_inbound_date), updated_at = NOW() WHERE batch_id = ?`,
        [assignedBatchNo, expectedInboundDate || null, req.params.id]
      );
    } else {
      await conn.query(
        `UPDATE batches SET status = 'Confirmed', expected_inbound_date = COALESCE(?, expected_inbound_date), updated_at = NOW() WHERE batch_id = ?`,
        [expectedInboundDate || null, req.params.id]
      );
    }
    await appendChange(conn, {
      batchId: batch.batch_id,
      action: 'confirm',
      before: { ...batch, status: 'Predicted' },
      after: { ...batch, status: 'Confirmed', expected_inbound_date: expectedInboundDate || batch.expected_inbound_date },
      username: req.user.username,
    });

    // Audit log
    await conn.query(
      `INSERT INTO sys_operation_log (user_id, username, operate_time, module, action_type, biz_type, content)
       VALUES (?, ?, NOW(), 'batch', 'confirm', 'batch', ?)`,
      [req.user.username, req.user.username, `Confirmed batch ${batch.batch_id}`]
    );

    await conn.commit();
    conn.release();

    // Release lock then trigger queue pull
    await releaseLock('batch:slot', lockToken);

    // Async: pull from queue (fire and forget, but log errors)
    pullFromQueue(batch.model_type).catch(err =>
      console.error('Queue pull failed:', err.message)
    );

    // Push WS
    const io = req.app.get('io');
    if (io) {
      io.emit('batch:confirmed', { batch_id: req.params.id, model_type: batch.model_type });
      io.emit('queue:updated', { model_type: batch.model_type });
    }

    res.json({ success: true, batch_id: req.params.id });
  } catch (err) {
    await conn.rollback();
    conn.release();
    await releaseLock('batch:slot', lockToken);
    res.status(500).json({ error: err.message });
  }
});

// POST /api/batches/:id/revoke - restore a confirmed batch after its plan sync is reversed.
// Queue refill triggered by the original confirmation is asynchronous and is deliberately
// not reversed here; a cross-service transaction is required for that broader guarantee.
router.post('/:id/revoke', adminOnly, async (req, res) => {
  const conn = await db.getConnection();
  try {
    await conn.beginTransaction();
    const [batches] = await conn.query(
      'SELECT batch_id, status FROM batches WHERE batch_id = ? FOR UPDATE', [req.params.id]
    );
    if (!batches.length) {
      await conn.rollback();
      return res.status(404).json({ error: 'Batch not found' });
    }
    if (batches[0].status !== 'Confirmed') {
      await conn.rollback();
      return res.status(400).json({ error: 'Only Confirmed batches can be revoked' });
    }
    await conn.query(
      "UPDATE batches SET status = 'Predicted', updated_at = NOW() WHERE batch_id = ?",
      [req.params.id]
    );
    await appendChange(conn, {
      batchId: batches[0].batch_id,
      action: 'revoke',
      before: { ...batches[0], status: 'Confirmed' },
      after: { ...batches[0], status: 'Predicted' },
      username: req.user.username,
    });
    await conn.query(
      `INSERT INTO sys_operation_log (user_id, username, operate_time, module, action_type, biz_type, content)
       VALUES (?, ?, NOW(), 'batch', 'revoke', 'batch', ?)`,
      [req.user.username, req.user.username, `Revoked batch ${batches[0].batch_id}`]
    );
    await conn.commit();
    res.json({ success: true, batch_id: req.params.id });
  } catch (err) {
    await conn.rollback();
    res.status(500).json({ error: err.message });
  } finally {
    conn.release();
  }
});

// POST /api/batches/batch-confirm 鈥?multi-batch approve
router.post('/batch-confirm', adminOnly, async (req, res) => {
  const { batch_ids } = req.body;
  if (!Array.isArray(batch_ids) || !batch_ids.length) {
    return res.status(400).json({ error: 'batch_ids array required' });
  }

  const lockToken = await acquireLock('batch:slot', 60);
  if (!lockToken) return res.status(409).json({ error: 'Another operation in progress' });

  const results = [];
  for (const id of batch_ids) {
    try {
      const conn = await db.getConnection();
      await conn.beginTransaction();
      const [batches] = await conn.query('SELECT * FROM batches WHERE batch_id = ? FOR UPDATE', [id]);
      if (batches.length && batches[0].status === 'Predicted') {
        await conn.query(`UPDATE batches SET status = 'Confirmed', updated_at = NOW() WHERE batch_id = ?`, [id]);
        await conn.query(
          `INSERT INTO sys_operation_log (user_id, username, operate_time, module, action_type, biz_type, content)
           VALUES (?, ?, NOW(), 'batch', 'confirm', 'batch', ?)`,
          [req.user.username, req.user.username, `Batch confirmed ${id}`]
        );
        results.push({ batch_id: id, confirmed: true });
      } else {
        results.push({ batch_id: id, confirmed: false, reason: 'Not in Predicted status' });
      }
      await conn.commit();
      conn.release();
    } catch (err) {
      results.push({ batch_id: id, confirmed: false, reason: err.message });
    }
  }

  await releaseLock('batch:slot', lockToken);

  // Pull from queue for any released slots
  pullFromQueue().catch(err => console.error('Queue pull failed:', err.message));

  res.json({ success: true, results });
});

// POST /api/batches/generate-next 鈥?manually generate next batch from queue
router.post('/generate-next', adminOnly, async (req, res) => {
  const { model_type } = req.body;
  if (!model_type) return res.status(400).json({ error: 'model_type required' });

  try {
    const result = await pullFromQueue(model_type);
    res.json(result);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

module.exports = router;

