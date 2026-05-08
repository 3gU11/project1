const router = require('express').Router();
const db = require('../db');
const { authMiddleware, adminOnly } = require('../middleware/auth');

router.use(authMiddleware);

function normalizeModelFamily(modelType) {
  const upper = String(modelType || '').toUpperCase().trim();
  if (!upper) return '';
  if (upper.includes('AUTO')) return 'AUTO';
  if (upper.includes('XS')) return 'XS';
  if (upper === 'G' || upper.endsWith('G')) return 'G';
  return upper;
}

// GET /api/production-lines 鈥?get all 20 lines with current batch info
router.get('/', async (req, res) => {
  const [lines] = await db.query(`
    SELECT pl.*, b.model_type, b.status as batch_status, b.production_line_id as batch_line_id,
      (SELECT COUNT(*) FROM units u WHERE u.production_line_id = pl.line_id) as unit_count
    FROM production_lines pl
    LEFT JOIN batches b ON pl.current_batch_id = b.batch_id
    ORDER BY pl.display_order
  `);

  // For busy lines, fetch their units
  const result = [];
  for (const line of lines) {
    const lineData = {
      ...line,
      production_line_id: line.line_id,
      line_model_family: normalizeModelFamily(line.model_type),
      units: []
    };
    // Data-healing guard: if line.current_batch_id points to a batch that belongs to another line,
    // do not render duplicated cards on this line.
    const batchBoundToOtherLine = line.current_batch_id && line.batch_line_id && line.batch_line_id !== line.line_id;
    if (line.current_batch_id && !batchBoundToOtherLine) {
      const [units] = await db.query(
        `SELECT
          u.*,
          COALESCE(md.model_name, NULLIF(fp.model_type_detail, ''), u.model_type) AS model_type_detail,
          COALESCE(NULLIF(u.dealer_id, ''), NULLIF(fp.dealer_name, '')) AS dealer_name
        FROM units u
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
            WHERE TRIM(COALESCE(状态, '')) IN ('未下单', '待规划')
          ) x
          GROUP BY contract_no, model_type_detail
        ) fp ON fp.contract_no COLLATE utf8mb4_general_ci = u.contract_no COLLATE utf8mb4_general_ci
            AND fp.model_type_detail COLLATE utf8mb4_general_ci = u.model_type COLLATE utf8mb4_general_ci
        LEFT JOIN model_dictionary md
          ON md.enabled = 1
         AND UPPER(TRIM(md.model_name)) NOT IN ('G', 'XS', 'AUTO')
         AND md.model_name COLLATE utf8mb4_general_ci =
             COALESCE(NULLIF(fp.model_type_detail, ''), u.model_type) COLLATE utf8mb4_general_ci
        WHERE u.production_line_id = ?
          AND u.batch_id = ?
          AND u.status = 'In_Production'
        ORDER BY u.slot_index`,
        [line.line_id, line.current_batch_id]
      );
      const seen = new Set();
      lineData.units = units.filter((u) => {
        if (!u?.unit_id || seen.has(u.unit_id)) return false;
        seen.add(u.unit_id);
        return true;
      });
    } else if (batchBoundToOtherLine) {
      lineData.data_warning = `Batch ${line.current_batch_id} belongs to line ${line.batch_line_id}`;
    }
    result.push(lineData);
  }

  res.json({ lines: result });
});

// GET /api/production-lines/consistency-check 鈥?detect mixed families in busy lines
router.get('/consistency-check', adminOnly, async (req, res) => {
  const [rows] = await db.query(`
    SELECT
      pl.line_id,
      pl.line_name,
      pl.status,
      COUNT(DISTINCT
        CASE
          WHEN UPPER(u.model_type) LIKE '%AUTO%' THEN 'AUTO'
          WHEN UPPER(u.model_type) LIKE '%XS%' THEN 'XS'
          WHEN UPPER(u.model_type) = 'G' OR UPPER(u.model_type) LIKE '%G' THEN 'G'
          ELSE UPPER(u.model_type)
        END
      ) AS family_count,
      GROUP_CONCAT(DISTINCT
        CASE
          WHEN UPPER(u.model_type) LIKE '%AUTO%' THEN 'AUTO'
          WHEN UPPER(u.model_type) LIKE '%XS%' THEN 'XS'
          WHEN UPPER(u.model_type) = 'G' OR UPPER(u.model_type) LIKE '%G' THEN 'G'
          ELSE UPPER(u.model_type)
        END
      ) AS families
    FROM production_lines pl
    LEFT JOIN units u ON u.production_line_id = pl.line_id
    WHERE pl.status = 'Busy'
    GROUP BY pl.line_id, pl.line_name, pl.status
    HAVING family_count > 1
    ORDER BY pl.display_order
  `);
  res.json({ mixed_lines: rows });
});

// POST /api/production-lines/:id/assign 鈥?assign whole batch to line
router.post('/:id/assign', adminOnly, async (req, res) => {
  const { batch_id } = req.body;
  if (!batch_id) return res.status(400).json({ error: 'batch_id required' });

  const conn = await db.getConnection();
  try {
    await conn.beginTransaction();

    // Lock line
    const [lines] = await conn.query(
      'SELECT * FROM production_lines WHERE line_id = ? FOR UPDATE', [req.params.id]
    );
    if (!lines.length) { await conn.rollback(); return res.status(404).json({ error: 'Line not found' }); }
    const line = lines[0];

    if (line.status !== 'Idle') {
      await conn.rollback();
      return res.status(400).json({ error: 'Line is not idle' });
    }

    // Lock batch
    const [batches] = await conn.query(
      'SELECT * FROM batches WHERE batch_id = ? FOR UPDATE', [batch_id]
    );
    if (!batches.length) { await conn.rollback(); return res.status(404).json({ error: 'Batch not found' }); }
    const batch = batches[0];

    if (batch.status !== 'Confirmed') {
      await conn.rollback();
      return res.status(400).json({ error: 'Only Confirmed batches can be assigned' });
    }
    if (batch.production_line_id) {
      await conn.rollback();
      return res.status(400).json({ error: 'Batch already assigned to a line' });
    }
    const [lineRefs] = await conn.query(
      'SELECT line_id FROM production_lines WHERE current_batch_id = ? FOR UPDATE',
      [batch_id]
    );
    const occupiedByOtherLine = lineRefs.find((r) => r.line_id !== req.params.id);
    if (occupiedByOtherLine) {
      await conn.rollback();
      return res.status(400).json({ error: `Batch is already occupied by line ${occupiedByOtherLine.line_id}` });
    }

    // Assign
    await conn.query(
      `UPDATE production_lines SET current_batch_id = ?, status = 'Busy', updated_at = NOW() WHERE line_id = ?`,
      [batch_id, req.params.id]
    );
    await conn.query(
      `UPDATE batches SET production_line_id = ?, status = 'In_Production', updated_at = NOW() WHERE batch_id = ?`,
      [req.params.id, batch_id]
    );
    await conn.query(
      `UPDATE units SET production_line_id = ?, status = 'In_Production', updated_at = NOW() WHERE batch_id = ?`,
      [req.params.id, batch_id]
    );

    // Audit
    await conn.query(
      `INSERT INTO sys_operation_log (user_id, username, operate_time, module, action_type, biz_type, content)
       VALUES (?, ?, NOW(), 'production_line', 'assign', 'batch', ?)`,
      [req.user.username, req.user.username, `Assign batch ${batch_id} to line ${req.params.id}`]
    );

    await conn.commit();
    conn.release();

    const io = req.app.get('io');
    if (io) {
      io.emit('line:updated', { line_id: req.params.id, batch_id });
      io.emit('batch:updated', { batch_id });
    }

    res.json({ success: true, line_id: req.params.id, batch_id });
  } catch (err) {
    await conn.rollback();
    conn.release();
    res.status(500).json({ error: err.message });
  }
});

// POST /api/production-lines/:id/manual-complete 鈥?manual finish override
router.post('/:id/manual-complete', adminOnly, async (req, res) => {
  const conn = await db.getConnection();
  try {
    await conn.beginTransaction();

    const [lines] = await conn.query(
      'SELECT * FROM production_lines WHERE line_id = ? FOR UPDATE', [req.params.id]
    );
    if (!lines.length) { await conn.rollback(); return res.status(404).json({ error: 'Line not found' }); }
    const line = lines[0];

    if (!line.current_batch_id) {
      await conn.rollback();
      return res.status(400).json({ error: 'No active batch on this line' });
    }

    // Complete batch
    await conn.query(
      `UPDATE batches SET status = 'Completed', updated_at = NOW() WHERE batch_id = ?`,
      [line.current_batch_id]
    );
    // Update units
    await conn.query(
      `UPDATE units
       SET status = 'In_Warehouse', production_line_id = NULL, updated_at = NOW()
       WHERE batch_id = ? AND production_line_id = ?`,
      [line.current_batch_id, req.params.id]
    );
    // Release line
    await conn.query(
      `UPDATE production_lines SET current_batch_id = NULL, status = 'Idle', updated_at = NOW() WHERE line_id = ?`,
      [req.params.id]
    );

    await conn.query(
      `INSERT INTO sys_operation_log (user_id, username, operate_time, module, action_type, biz_type, content)
       VALUES (?, ?, NOW(), 'production_line', 'manual_complete', 'batch', ?)`,
      [req.user.username, req.user.username, `Manual complete line ${req.params.id}, batch ${line.current_batch_id}`]
    );

    await conn.commit();
    conn.release();

    const io = req.app.get('io');
    if (io) {
      io.emit('line:updated', { line_id: req.params.id });
      io.emit('batch:updated', { batch_id: line.current_batch_id });
    }

    res.json({ success: true });
  } catch (err) {
    await conn.rollback();
    conn.release();
    res.status(500).json({ error: err.message });
  }
});

module.exports = router;

