const router = require('express').Router();
const db = require('../db');
const { authMiddleware, adminOnly } = require('../middleware/auth');
const { refillEmptySlots } = require('../engine/predictor');

router.use(authMiddleware);

function normalizeModelFamily(modelType) {
  const upper = String(modelType || '').toUpperCase().trim();
  if (!upper) return '';
  if (upper.includes('AUTO')) return 'AUTO';
  if (upper.includes('XS')) return 'XS';
  if (upper === 'G' || upper.endsWith('G')) return 'G';
  return upper;
}

async function renumberBatchSlots(conn, batchId, orderedUnitIds) {
  if (!orderedUnitIds.length) return;

  // Phase 1: move to temporary non-conflicting indices to avoid unique-key collisions.
  for (let i = 0; i < orderedUnitIds.length; i++) {
    await conn.query(
      `UPDATE units SET slot_index = ?, updated_at = NOW() WHERE unit_id = ?`,
      [1000 + i + 1, orderedUnitIds[i]]
    );
  }

  // Phase 2: write final 1..N indices.
  for (let i = 0; i < orderedUnitIds.length; i++) {
    await conn.query(
      `UPDATE units SET slot_index = ?, updated_at = NOW() WHERE unit_id = ?`,
      [i + 1, orderedUnitIds[i]]
    );
  }
}

// PATCH /api/units/:id 鈥?info overwrite (triggers is_locked=true)
router.patch('/:id', adminOnly, async (req, res) => {
  const { contract_no, customer, dealer_id, sales_id, order_remark, model_type } = req.body;
  const conn = await db.getConnection();

  try {
    await conn.beginTransaction();

    const [units] = await conn.query(
      'SELECT * FROM units WHERE unit_id = ? FOR UPDATE', [req.params.id]
    );
    if (!units.length) {
      await conn.rollback();
      return res.status(404).json({ error: 'Unit not found' });
    }
    const unit = units[0];

    // Guard: keep unit model family consistent with its batch family.
    if (model_type !== undefined) {
      const [batchRows] = await conn.query(
        'SELECT model_type FROM batches WHERE batch_id = ?',
        [unit.batch_id]
      );
      const batchModel = batchRows?.[0]?.model_type || '';
      const nextFamily = normalizeModelFamily(model_type);
      const batchFamily = normalizeModelFamily(batchModel);
      if (nextFamily && batchFamily && nextFamily !== batchFamily) {
        await conn.rollback();
        return res.status(400).json({ error: `机型族不匹配：${model_type} 不可写入 ${batchModel} 批次` });
      }
    }

    // Update order content + set lock
    const updates = [];
    const values = [];
    if (contract_no !== undefined) { updates.push('contract_no = ?'); values.push(contract_no); }
    if (customer !== undefined) { updates.push('customer = ?'); values.push(customer); }
    if (dealer_id !== undefined) { updates.push('dealer_id = ?'); values.push(dealer_id); }
    if (sales_id !== undefined) { updates.push('sales_id = ?'); values.push(sales_id); }
    if (order_remark !== undefined) { updates.push('order_remark = ?'); values.push(order_remark); }
    if (model_type !== undefined) { updates.push('model_type = ?'); values.push(model_type); }

    // Set lock
    updates.push('is_locked = 1');
    updates.push('locked_by = ?'); values.push(req.user.username);
    updates.push('locked_at = NOW()');

    values.push(req.params.id);
    await conn.query(
      `UPDATE units SET ${updates.join(', ')}, updated_at = NOW() WHERE unit_id = ?`,
      values
    );

    // Audit log
    await conn.query(
      `INSERT INTO sys_operation_log (user_id, username, operate_time, module, action_type, biz_type, content, serial_no)
       VALUES (?, ?, NOW(), 'unit', 'overwrite', 'unit', ?, ?)`,
      [req.user.username, req.user.username, `Force edit unit ${req.params.id}`, req.params.id]
    );

    await conn.commit();
    conn.release();

    // Note: batch empty slot count does NOT change for info overwrite (PRD: 鍚屾壒绌烘Ы鏁颁笉鍙樹笉閲嶇畻)

    const io = req.app.get('io');
    if (io) io.emit('unit:updated', { unit_id: req.params.id });

    res.json({ success: true, unit_id: req.params.id });
  } catch (err) {
    await conn.rollback();
    conn.release();
    res.status(500).json({ error: err.message });
  }
});

// PATCH /api/units/:id/unlock 鈥?admin unlock
router.patch('/:id/unlock', adminOnly, async (req, res) => {
  const [result] = await db.query(
    `UPDATE units SET is_locked = 0, locked_by = NULL, locked_at = NULL, updated_at = NOW()
     WHERE unit_id = ? AND is_locked = 1`,
    [req.params.id]
  );

  await db.query(
    `INSERT INTO sys_operation_log (user_id, username, operate_time, module, action_type, biz_type, content, serial_no)
     VALUES (?, ?, NOW(), 'unit', 'unlock', 'unit', ?, ?)`,
    [req.user.username, req.user.username, `Unlocked unit ${req.params.id}`, req.params.id]
  );

  const io = req.app.get('io');
  if (io) io.emit('unit:updated', { unit_id: req.params.id, unlocked: true });

  res.json({ success: true, unlocked: result.affectedRows > 0 });
});

// POST /api/units/:id/move-batch 鈥?drag unit to another (same-model) batch
router.post('/:id/move-batch', adminOnly, async (req, res) => {
  const { target_batch_id, target_slot, insert_before_slot_index } = req.body;
  if (!target_batch_id) return res.status(400).json({ error: 'target_batch_id required' });

  const conn = await db.getConnection();
  try {
    await conn.beginTransaction();

    // Lock source unit with batch
    const [sourceUnits] = await conn.query(
      'SELECT u.*, b.model_type as batch_model FROM units u JOIN batches b ON u.batch_id = b.batch_id WHERE u.unit_id = ? FOR UPDATE',
      [req.params.id]
    );
    if (!sourceUnits.length) { await conn.rollback(); return res.status(404).json({ error: 'Unit not found' }); }
    const unit = sourceUnits[0];

    const [targetBatch] = await conn.query(
      'SELECT * FROM batches WHERE batch_id = ? FOR UPDATE', [target_batch_id]
    );
    if (!targetBatch.length) { await conn.rollback(); return res.status(404).json({ error: 'Target batch not found' }); }

    // Must be same model family (G/XS/AUTO), detailed model can differ in same family
    if (normalizeModelFamily(unit.model_type) !== normalizeModelFamily(targetBatch[0].model_type)) {
      await conn.rollback();
      return res.status(400).json({ error: 'Cannot move to batch of different model family' });
    }

    const sourceBatchId = unit.batch_id;
    const movingAcrossBatch = sourceBatchId !== target_batch_id;

    // Capacity check only when crossing batches
    if (movingAcrossBatch) {
      const [targetUnits] = await conn.query(
        'SELECT COUNT(*) as cnt FROM units WHERE batch_id = ?', [target_batch_id]
      );
      if (targetUnits[0].cnt >= targetBatch[0].capacity) {
        await conn.rollback();
        return res.status(400).json({ error: 'Target batch is full' });
      }
    }

    // Compute desired position in target batch
    const [targetRowsRaw] = await conn.query(
      'SELECT unit_id, slot_index FROM units WHERE batch_id = ? ORDER BY slot_index ASC FOR UPDATE',
      [target_batch_id]
    );
    let targetRows = targetRowsRaw.filter((r) => r.unit_id !== req.params.id);

    const requestedSlotRaw = target_slot ?? insert_before_slot_index;
    const requestedSlot = Number(requestedSlotRaw);
    let insertPos = targetRows.length; // append by default
    if (Number.isFinite(requestedSlot) && requestedSlot > 0) {
      const idx = targetRows.findIndex((r) => Number(r.slot_index) >= requestedSlot);
      insertPos = idx >= 0 ? idx : targetRows.length;
    }
    if (insertPos < 0) insertPos = 0;
    if (insertPos > targetRows.length) insertPos = targetRows.length;

    // Place unit into target batch first
    await conn.query(
      `UPDATE units SET batch_id = ?, updated_at = NOW() WHERE unit_id = ?`,
      [target_batch_id, req.params.id]
    );

    // Rebuild target ordering with moved unit inserted at target position
    targetRows.splice(insertPos, 0, { unit_id: req.params.id });
    await renumberBatchSlots(conn, target_batch_id, targetRows.map((r) => r.unit_id));

    // Rebuild source ordering if moved across batches
    if (movingAcrossBatch) {
      const [sourceRows] = await conn.query(
        'SELECT unit_id FROM units WHERE batch_id = ? ORDER BY slot_index ASC FOR UPDATE',
        [sourceBatchId]
      );
      await renumberBatchSlots(conn, sourceBatchId, sourceRows.map((r) => r.unit_id));
    }

    // Audit
    await conn.query(
      `INSERT INTO sys_operation_log (user_id, username, operate_time, module, action_type, biz_type, content, serial_no)
       VALUES (?, ?, NOW(), 'unit', 'move_batch', 'unit', ?, ?)`,
      [req.user.username, req.user.username, `Move unit ${req.params.id} from ${sourceBatchId} to ${target_batch_id} at slot ${insertPos + 1}`, req.params.id]
    );

    await conn.commit();
    conn.release();

    // Re-calc empty slots only when crossing batches
    if (movingAcrossBatch) {
      refillEmptySlots(sourceBatchId).catch(err => console.error('Refill source failed:', err));
      refillEmptySlots(target_batch_id).catch(err => console.error('Refill target failed:', err));
    }

    const io = req.app.get('io');
    if (io) {
      io.emit('batch:updated', { batch_id: sourceBatchId });
      io.emit('batch:updated', { batch_id: target_batch_id });
    }

    res.json({ success: true, source_batch_id: sourceBatchId, target_batch_id });
  } catch (err) {
    await conn.rollback();
    conn.release();
    res.status(500).json({ error: err.message });
  }
});

// GET /api/units/empty-containers 鈥?find empty containers for drag fallback
router.get('/empty-containers', async (req, res) => {
  const { model_type } = req.query;
  if (!model_type) return res.status(400).json({ error: 'model_type required' });

  const [units] = await db.query(`
    SELECT u.*, b.batch_no, pl.line_name
    FROM units u
    JOIN batches b ON u.batch_id = b.batch_id
    LEFT JOIN production_lines pl ON u.production_line_id = pl.line_id
    WHERE u.contract_no IS NULL
      AND u.model_type = ?
      AND u.is_locked = 0
    ORDER BY u.production_line_id, u.batch_id, u.slot_index
    LIMIT 200
  `, [model_type]);

  res.json({ containers: units });
});

// POST /api/units/swap-content 鈥?horizontal drag-and-drop order modification
router.post('/swap-content', adminOnly, async (req, res) => {
  const { source_unit_id, target_unit_id, fallback_unit_id, operator, reason } = req.body;

  if (!source_unit_id || !target_unit_id || !fallback_unit_id) {
    return res.status(400).json({ error: 'source_unit_id, target_unit_id, and fallback_unit_id are all required' });
  }

  const conn = await db.getConnection();
  try {
    await conn.beginTransaction();

    // Lock all three rows
    const [rows] = await conn.query(
      `SELECT * FROM units WHERE unit_id IN (?, ?, ?) FOR UPDATE`,
      [source_unit_id, target_unit_id, fallback_unit_id]
    );
    if (rows.length !== 3) {
      await conn.rollback();
      return res.status(404).json({ error: 'One or more units not found' });
    }

    const source = rows.find(r => r.unit_id === source_unit_id);
    const target = rows.find(r => r.unit_id === target_unit_id);
    const fallback = rows.find(r => r.unit_id === fallback_unit_id);

    // Validations
    if (target.is_locked) {
      await conn.rollback();
      return res.status(400).json({ error: 'Target unit is locked. Unlock first.' });
    }
    if (fallback.contract_no !== null) {
      await conn.rollback();
      return res.status(400).json({ error: 'Fallback container is no longer empty.' });
    }
    if (fallback.model_type !== target.model_type) {
      await conn.rollback();
      return res.status(400).json({ error: 'Fallback container model type mismatch.' });
    }

    // Extract order content fields
    const orderFields = ['contract_no', 'customer', 'dealer_id', 'sales_id', 'order_remark'];

    // Save target's original content
    const targetOriginal = {};
    for (const f of orderFields) targetOriginal[f] = target[f];

    // Save source content
    const sourceContent = {};
    for (const f of orderFields) sourceContent[f] = source[f];

    // Step 1: Write source content to target
    await conn.query(
      `UPDATE units SET contract_no=?, customer=?, dealer_id=?, sales_id=?, order_remark=?, updated_at=NOW()
       WHERE unit_id=?`,
      [...orderFields.map(f => source[f]), target_unit_id]
    );

    // Step 2: Write target's original content to fallback
    await conn.query(
      `UPDATE units SET contract_no=?, customer=?, dealer_id=?, sales_id=?, order_remark=?, updated_at=NOW()
       WHERE unit_id=?`,
      [...orderFields.map(f => targetOriginal[f]), fallback_unit_id]
    );

    // Step 3: Clear source (if it was a real unit, not a temp order card)
    // If source has a production_line_id, it's a real unit and we clear it
    if (source.production_line_id) {
      await conn.query(
        `UPDATE units SET contract_no=NULL, customer=NULL, dealer_id=NULL, sales_id=NULL, order_remark=NULL, updated_at=NOW()
         WHERE unit_id=?`,
        [source_unit_id]
      );
    }

    // Audit log
    await conn.query(
      `INSERT INTO sys_operation_log (user_id, username, operate_time, module, action_type, biz_type, content)
       VALUES (?, ?, NOW(), 'unit', 'swap_content', 'unit', ?)`,
      [req.user.username || operator, req.user.username || operator,
       `Swap: ${source_unit_id}鈫?{target_unit_id}, ${target_unit_id} content鈫?{fallback_unit_id}, reason: ${reason || 'rush order'}`]
    );

    await conn.commit();
    conn.release();

    // Re-fetch affected units for response
    const [affected] = await db.query(
      `SELECT unit_id, contract_no, customer FROM units WHERE unit_id IN (?, ?, ?)`,
      [source_unit_id, target_unit_id, fallback_unit_id]
    );

    // WS push
    const io = req.app.get('io');
    if (io) {
      io.emit('unit:updated', { units: affected.map(u => u.unit_id) });
    }

    res.json({
      success: true,
      affected_units: affected,
      ws_pushed: true
    });
  } catch (err) {
    await conn.rollback();
    conn.release();
    res.status(500).json({ error: err.message });
  }
});

// POST /api/units/:id/mark-spot 鈥?mark unit as spot inventory
router.post('/:id/mark-spot', adminOnly, async (req, res) => {
  await db.query(
    `UPDATE units SET status = 'Spot_Inventory', updated_at = NOW() WHERE unit_id = ?`,
    [req.params.id]
  );

  await db.query(
    `INSERT INTO sys_operation_log (user_id, username, operate_time, module, action_type, biz_type, content, serial_no)
     VALUES (?, ?, NOW(), 'unit', 'mark_spot', 'unit', ?, ?)`,
    [req.user.username, req.user.username, `Marked unit ${req.params.id} as spot`, req.params.id]
  );

  const io = req.app.get('io');
  if (io) io.emit('unit:updated', { unit_id: req.params.id, status: 'Spot_Inventory' });

  res.json({ success: true });
});

// POST /api/units/rush-insert - insert rush order into target slot
router.post('/rush-insert', adminOnly, async (req, res) => {
  const { target_unit_id, fallback_unit_id, rush_order } = req.body || {};
  if (!target_unit_id || !fallback_unit_id || !rush_order?.contract_no || !rush_order?.model_type) {
    return res.status(400).json({ error: 'target_unit_id, fallback_unit_id and rush_order(contract_no, model_type) are required' });
  }

  const conn = await db.getConnection();
  try {
    await conn.beginTransaction();
    const sameUnitFallback = target_unit_id === fallback_unit_id;
    const [rows] = sameUnitFallback
      ? await conn.query(
          `SELECT * FROM units WHERE unit_id = ? FOR UPDATE`,
          [target_unit_id]
        )
      : await conn.query(
          `SELECT * FROM units WHERE unit_id IN (?, ?) FOR UPDATE`,
          [target_unit_id, fallback_unit_id]
        );

    if ((!sameUnitFallback && rows.length !== 2) || (sameUnitFallback && rows.length !== 1)) {
      await conn.rollback();
      return res.status(404).json({ error: 'Target or fallback unit not found' });
    }

    const target = rows.find((r) => r.unit_id === target_unit_id);
    const fallback = sameUnitFallback ? target : rows.find((r) => r.unit_id === fallback_unit_id);
    if (!target || !fallback) {
      await conn.rollback();
      return res.status(404).json({ error: 'Target or fallback unit not found' });
    }
    if (target.is_locked) {
      await conn.rollback();
      return res.status(400).json({ error: 'Target unit is locked' });
    }
    if (!sameUnitFallback && fallback.contract_no !== null) {
      await conn.rollback();
      return res.status(400).json({ error: 'Fallback unit is not empty' });
    }
    if (!sameUnitFallback && fallback.model_type !== target.model_type) {
      await conn.rollback();
      return res.status(400).json({ error: 'Fallback model type mismatch' });
    }
    if (normalizeModelFamily(rush_order.model_type) !== normalizeModelFamily(target.model_type)) {
      await conn.rollback();
      return res.status(400).json({ error: 'Rush order model type mismatch with target unit' });
    }

    // Hard guard: if target already belongs to a production line, line family must stay consistent.
    if (target.production_line_id) {
      const [lineRows] = await conn.query(
        `SELECT b.model_type
         FROM production_lines pl
         LEFT JOIN batches b ON b.batch_id = pl.current_batch_id
         WHERE pl.line_id = ?`,
        [target.production_line_id]
      );
      const lineModel = lineRows?.[0]?.model_type || target.model_type;
      if (normalizeModelFamily(rush_order.model_type) !== normalizeModelFamily(lineModel)) {
        await conn.rollback();
        return res.status(400).json({ error: `Line family mismatch: ${normalizeModelFamily(rush_order.model_type)} vs ${normalizeModelFamily(lineModel)}` });
      }
    }

    if (!sameUnitFallback && target.contract_no) {
      await conn.query(
        `UPDATE units SET contract_no=?, customer=?, dealer_id=?, sales_id=?, order_remark=?, updated_at=NOW()
         WHERE unit_id=?`,
        [target.contract_no, target.customer, target.dealer_id, target.sales_id, target.order_remark, fallback_unit_id]
      );
    }

    await conn.query(
      `UPDATE units
       SET contract_no=?, customer=?, model_type=?, order_remark=?, is_locked=1, locked_by=?, locked_at=NOW(), updated_at=NOW()
       WHERE unit_id=?`,
      [rush_order.contract_no, rush_order.customer || null, rush_order.model_type, 'rush_insert', req.user.username, target_unit_id]
    );

    await conn.commit();
    conn.release();

    const io = req.app.get('io');
    if (io) io.emit('unit:updated', { units: [target_unit_id, fallback_unit_id] });
    res.json({ success: true, target_unit_id, fallback_unit_id });
  } catch (err) {
    await conn.rollback();
    conn.release();
    res.status(500).json({ error: err.message });
  }
});

function familySqlWhere(familyAlias = 'b.model_type') {
  if (familyAlias.includes(';')) throw new Error('invalid alias');
  return {
    AUTO: `UPPER(${familyAlias}) LIKE '%AUTO%'`,
    XS: `UPPER(${familyAlias}) LIKE '%XS%'`,
    G: `(UPPER(${familyAlias}) = 'G' OR UPPER(${familyAlias}) LIKE '%G')`
  };
}

// POST /api/units/repair-family-mismatches - auto-fix misplaced units by swapping with empty containers in correct-family batches
router.post('/repair-family-mismatches', adminOnly, async (req, res) => {
  const [rows] = await db.query(
    `SELECT
       u.unit_id,
       u.batch_id,
       u.slot_index,
       u.model_type,
       u.contract_no,
       b.model_type AS batch_model_type
     FROM units u
     JOIN batches b ON b.batch_id = u.batch_id
     WHERE b.status IN ('Predicted', 'Confirmed', 'In_Production')
       AND u.contract_no IS NOT NULL`
  );

  const mismatches = rows.filter((r) => {
    const uf = normalizeModelFamily(r.model_type);
    const bf = normalizeModelFamily(r.batch_model_type);
    return uf && bf && uf !== bf;
  });

  const fixed = [];
  const failed = [];

  for (const item of mismatches) {
    const conn = await db.getConnection();
    try {
      await conn.beginTransaction();

      const [srcRows] = await conn.query(
        `SELECT u.*, b.model_type AS batch_model_type
         FROM units u
         JOIN batches b ON b.batch_id = u.batch_id
         WHERE u.unit_id = ?
         FOR UPDATE`,
        [item.unit_id]
      );
      if (!srcRows.length) throw new Error('source unit not found');
      const src = srcRows[0];
      const srcFamily = normalizeModelFamily(src.batch_model_type);
      const unitFamily = normalizeModelFamily(src.model_type);
      if (!srcFamily || !unitFamily || srcFamily === unitFamily) {
        await conn.rollback();
        conn.release();
        continue;
      }

      const whereMap = familySqlWhere('b2.model_type');
      const familyWhere = whereMap[unitFamily];
      if (!familyWhere) throw new Error(`unsupported family ${unitFamily}`);

      const [fallbackRows] = await conn.query(
        `SELECT
           u2.unit_id,
           u2.batch_id,
           u2.slot_index,
           u2.model_type,
           b2.model_type AS batch_model_type
         FROM units u2
         JOIN batches b2 ON b2.batch_id = u2.batch_id
         WHERE b2.status IN ('Predicted', 'Confirmed', 'In_Production')
           AND ${familyWhere}
           AND u2.contract_no IS NULL
           AND u2.is_locked = 0
         ORDER BY b2.due_date_start ASC, u2.slot_index ASC
         LIMIT 1
         FOR UPDATE`
      );
      if (!fallbackRows.length) {
        throw new Error('no empty slot found in target family batches');
      }
      const fb = fallbackRows[0];

      // Swap positions between source unit and fallback empty slot.
      await conn.query(
        `UPDATE units SET batch_id = ?, slot_index = 900001, updated_at = NOW() WHERE unit_id = ?`,
        [fb.batch_id, src.unit_id]
      );
      await conn.query(
        `UPDATE units SET batch_id = ?, slot_index = 900002, model_type = ?, updated_at = NOW() WHERE unit_id = ?`,
        [src.batch_id, src.batch_model_type, fb.unit_id]
      );
      await conn.query(
        `UPDATE units SET slot_index = ?, updated_at = NOW() WHERE unit_id = ?`,
        [fb.slot_index, src.unit_id]
      );
      await conn.query(
        `UPDATE units SET slot_index = ?, updated_at = NOW() WHERE unit_id = ?`,
        [src.slot_index, fb.unit_id]
      );

      await conn.query(
        `INSERT INTO sys_operation_log (user_id, username, operate_time, module, action_type, biz_type, content, serial_no)
         VALUES (?, ?, NOW(), 'unit', 'repair_family_mismatch', 'unit', ?, ?)`,
        [
          req.user.username,
          req.user.username,
          `Repair mismatch: move ${src.unit_id}(${src.model_type}) ${src.batch_id} -> ${fb.batch_id} swap with ${fb.unit_id}`,
          src.unit_id
        ]
      );

      await conn.commit();
      conn.release();

      fixed.push({
        unit_id: src.unit_id,
        from_batch_id: src.batch_id,
        to_batch_id: fb.batch_id,
        swapped_with: fb.unit_id
      });
    } catch (err) {
      await conn.rollback();
      conn.release();
      failed.push({ unit_id: item.unit_id, error: err.message });
    }
  }

  const io = req.app.get('io');
  if (io && (fixed.length || failed.length)) io.emit('unit:updated', { repaired: fixed.length, failed: failed.length });

  res.json({ success: true, mismatch_count: mismatches.length, fixed_count: fixed.length, fixed, failed });
});
module.exports = router;

