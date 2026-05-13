/**
 * Prediction Engine V2.2 鈥?Model-type-based batch generation.
 *
 * Core rules:
 * - Batches are single-model (no mixing)
 * - G/XS capacity = 30, AUTO = 27 (configurable)
 * - Gap > 30 days 鈫?new batch
 * - Max 20 predicted/confirmed batches globally; overflow 鈫?production_queue
 * - Empty slots filled proportionally by capacity_ratio
 * - is_locked=true units are completely skipped
 */

const db = require('../db');
const { acquireLock, releaseLock } = require('../redis');

// ============================================================
// Configuration helpers
// ============================================================

async function getConfig(key, fallback) {
  const [rows] = await db.query(
    'SELECT config_value FROM system_config WHERE config_key = ?', [key]
  );
  if (rows.length) {
    try { return JSON.parse(rows[0].config_value); } catch { return rows[0].config_value; }
  }
  return fallback;
}

async function getModelCapacity() {
  const cap = await getConfig('model_capacity', { G: 30, XS: 30, AUTO: 27 });
  return (model) => {
    const family = normalizeModelFamily(model);
    return cap[model] || cap[family] || 30;
  };
}

async function getCapacityRatio() {
  return getConfig('capacity_ratio', {
    level1: { G: 24, XS: 76, AUTO: 0 },
    level2: {
      G: { '300': 11, '400': 67, '500': 14, '600': 8 },
      XS: { '400': 51, '500': 24, '600': 17, 'BIG': 8 },
      AUTO: { '400': 51, '500': 24, '600': 17, 'BIG': 8 }
    }
  });
}

async function getEnabledModelTypes() {
  const [rows] = await db.query(
    `SELECT model_name
     FROM model_dictionary
     WHERE enabled = 1
       AND UPPER(TRIM(model_name)) NOT IN ('G', 'XS', 'AUTO')
     ORDER BY sort_order ASC, model_name ASC`
  );
  return rows.map((r) => r.model_name).filter(Boolean);
}

function normalizeModelFamily(modelType) {
  const upper = String(modelType || '').toUpperCase().trim();
  if (!upper) return '';
  if (upper.includes('AUTO')) return 'AUTO';
  if (upper.includes('XS')) return 'XS';
  if (upper === 'G' || upper.endsWith('G')) return 'G';
  return upper;
}

function parseRatioConfig(rawRatio, models) {
  const defaultFamily = { G: 40, XS: 35, AUTO: 25 };
  const ratio = rawRatio && typeof rawRatio === 'object' ? rawRatio : defaultFamily;
  const level1 = ratio.level1 && typeof ratio.level1 === 'object' ? ratio.level1 : ratio;
  const level2 = ratio.level2 && typeof ratio.level2 === 'object' ? ratio.level2 : {};

  const familyRatio = {
    G: Number(level1.G || defaultFamily.G),
    XS: Number(level1.XS || defaultFamily.XS),
    AUTO: Number(level1.AUTO || defaultFamily.AUTO)
  };
  if (!Number.isFinite(familyRatio.AUTO)) {
    familyRatio.AUTO = Math.max(0, 100 - familyRatio.G - familyRatio.XS);
  }

  const modelsByFamily = { G: [], XS: [], AUTO: [] };
  for (const m of models) {
    const f = normalizeModelFamily(m);
    if (!modelsByFamily[f]) modelsByFamily[f] = [];
    modelsByFamily[f].push(m);
  }

  const modelTarget = {};
  for (const family of Object.keys(modelsByFamily)) {
    const familyModels = modelsByFamily[family];
    if (!familyModels.length) continue;
    const weights = level2[family] && typeof level2[family] === 'object' ? level2[family] : {};
    const perModelWeights = familyModels.map((m) => Number(weights[m] || 0));
    const sumWeight = perModelWeights.reduce((s, v) => s + (Number.isFinite(v) ? v : 0), 0);
    const familyShare = Number(familyRatio[family] || 0);

    if (sumWeight > 0) {
      familyModels.forEach((m, idx) => {
        modelTarget[m] = familyShare * (perModelWeights[idx] / sumWeight);
      });
    } else {
      const even = familyShare / familyModels.length;
      familyModels.forEach((m) => { modelTarget[m] = even; });
    }
  }

  const fallback = models.length ? (100 / models.length) : 0;
  for (const m of models) {
    if (!Number.isFinite(modelTarget[m])) modelTarget[m] = fallback;
  }
  return modelTarget;
}

function buildLevel2Weights(level2Config, family, candidates) {
  const familyCfg = level2Config?.[family] || {};
  const weights = {};
  const buckets = { '400': [], '500': [], '600': [], BIG: [] };

  for (const m of candidates) {
    const modelKey = String(m || '');
    const upper = modelKey.toUpperCase();
    const d3 = upper.match(/\d{3}/)?.[0] || '';
    let bucket = 'BIG';
    if (d3 === '400' || d3 === '500' || d3 === '600') bucket = d3;
    else if (/BIG|大/.test(upper)) bucket = 'BIG';
    buckets[bucket].push(m);
  }

  const bucketWeights = {
    '400': Number(familyCfg['400'] || 0),
    '500': Number(familyCfg['500'] || 0),
    '600': Number(familyCfg['600'] || 0),
    BIG: Number(familyCfg['BIG'] || 0)
  };

  let sum = 0;
  for (const [bucket, models] of Object.entries(buckets)) {
    if (!models.length) continue;
    const bw = Number.isFinite(bucketWeights[bucket]) ? bucketWeights[bucket] : 0;
    if (bw <= 0) continue;
    const perModel = bw / models.length;
    for (const m of models) {
      weights[m] = perModel;
      sum += perModel;
    }
  }

  if (sum <= 0) {
    const even = candidates.length ? (100 / candidates.length) : 0;
    for (const m of candidates) weights[m] = even;
  }
  return weights;
}

function getFamilyCandidates(family, allEnabledModels) {
  const candidates = allEnabledModels.filter((m) => normalizeModelFamily(m) === family);
  return candidates.length ? candidates : [family];
}

function pickModelByRatio(weights, cursor) {
  const entries = Object.entries(weights);
  const total = entries.reduce((s, [, v]) => s + Number(v), 0) || 1;
  const normalizedCursor = ((cursor % total) + total) % total;
  let acc = 0;
  for (const [k, v] of entries) {
    acc += Number(v) || 0;
    if (normalizedCursor <= acc) return k;
  }
  return entries[0]?.[0] || '';
}

function buildModelFillPlan(weights, slotCount) {
  const entries = Object.entries(weights || {}).filter(([, v]) => Number(v) > 0);
  if (!entries.length || slotCount <= 0) return [];

  const totalWeight = entries.reduce((s, [, v]) => s + Number(v), 0) || 1;
  const quotas = entries.map(([model, w]) => {
    const exact = (Number(w) / totalWeight) * slotCount;
    const base = Math.floor(exact);
    return { model, base, frac: exact - base };
  });

  let assigned = quotas.reduce((s, q) => s + q.base, 0);
  let remain = slotCount - assigned;
  quotas.sort((a, b) => b.frac - a.frac);
  for (let i = 0; i < remain; i++) quotas[i % quotas.length].base += 1;

  // Interleave by remaining count to avoid clustering same model in a chunk.
  const counters = quotas.map((q) => ({ model: q.model, remain: q.base }));
  const plan = [];
  for (let i = 0; i < slotCount; i++) {
    counters.sort((a, b) => b.remain - a.remain);
    const pick = counters.find((c) => c.remain > 0);
    if (!pick) break;
    plan.push(pick.model);
    pick.remain -= 1;
  }
  return plan;
}

async function getMaxBatchSlots() {
  const v = await getConfig('max_batch_slots', '20');
  return parseInt(v) || 20;
}

async function getGapThreshold() {
  const v = await getConfig('batch_break_days', '30');
  return parseInt(v) || 30;
}

// ============================================================
// Data loading 鈥?expand contracts into individual unit objects
// ============================================================

async function loadContractsByModel() {
  const [rows] = await db.query(`
    SELECT
      \`合同号\` AS contract_no,
      \`机型\` AS model_type,
      \`排产数量\` AS plan_qty,
      \`要求交期\` AS due_date_text,
      \`客户名\` AS customer,
      \`代理商\` AS dealer,
      \`状态\` AS plan_status,
      \`指定批次/来源\` AS source_tag
    FROM factory_plan
    WHERE \`机型\` COLLATE utf8mb4_general_ci IN (
      SELECT model_name COLLATE utf8mb4_general_ci
      FROM model_dictionary
      WHERE enabled = 1
    )
      AND TRIM(COALESCE(\`状态\`, '')) = '待规划'
      AND \`要求交期\` IS NOT NULL
      AND \`要求交期\` != ''
      AND NOT EXISTS (
        SELECT 1 FROM production_queue pq
        WHERE pq.contract_no COLLATE utf8mb4_general_ci = factory_plan.\`合同号\` COLLATE utf8mb4_general_ci
          AND pq.model_type COLLATE utf8mb4_general_ci = factory_plan.\`机型\` COLLATE utf8mb4_general_ci
          AND pq.status = 'Waiting'
      )
    ORDER BY \`要求交期\` ASC
  `);

  // Group by model type, expand each contract into individual unit entries
  const queues = {}; // { model_type: [unit, ...] }

  for (const row of rows) {
    const model = (row.model_type || '').trim();
    const qty = parseInt(row.plan_qty) || 0;
    const dueStr = String(row.due_date_text || '').trim();
    const dueDate = parseDueDate(dueStr);

    if (!model || qty <= 0 || !dueDate) continue;

    if (!queues[model]) queues[model] = [];

    for (let i = 0; i < qty; i++) {
      queues[model].push({
        contract_no: row.contract_no,
        model_type: model,
        customer: row.customer || '',
        dealer: row.dealer || '',
        due_date: dueDate,
        is_contract_pinned: 0
      });
    }
  }

  // Sort each queue by due_date
  for (const model of Object.keys(queues)) {
    queues[model].sort((a, b) => a.due_date - b.due_date);
  }

  return queues;
}

function parseDueDate(str) {
  if (!str || str === '0') return null;
  // Try common Chinese date formats
  const cleaned = str.replace(/[骞存湀]/g, '-').replace(/[鏃ュ彿]/g, '').trim();
  const d = new Date(cleaned);
  if (isNaN(d.getTime())) {
    // Try extracting YYYY-MM-DD
    const m = cleaned.match(/(\d{4})-(\d{1,2})-(\d{1,2})/);
    if (m) return new Date(+m[1], +m[2] - 1, +m[3]);
    return null;
  }
  return d;
}

// ============================================================
// Main batch generation algorithm
// ============================================================

async function generateBatches(modelQueues, options = {}) {
  const { forceModel } = options; // optional: generate only for specific model/family
  const maxSlots = await getMaxBatchSlots();
  const gapDays = await getGapThreshold();
  const getCap = await getModelCapacity();
  const ratio = await getCapacityRatio();
  const enabledModels = await getEnabledModelTypes();
  const level2 = ratio?.level2 && typeof ratio.level2 === 'object' ? ratio.level2 : {};

  const familyQueues = {};
  for (const [model, units] of Object.entries(modelQueues)) {
    const family = normalizeModelFamily(model);
    if (!familyQueues[family]) familyQueues[family] = [];
    for (const u of units) {
      familyQueues[family].push({
        ...u,
        model_type: u.model_type || model,
        model_family: family
      });
    }
  }
  for (const family of Object.keys(familyQueues)) {
    familyQueues[family].sort((a, b) => a.due_date - b.due_date);
  }

  // Count existing predicted/confirmed batches (non-completed)
  const [countRows] = await db.query(
    `SELECT model_type, COUNT(*) as cnt FROM batches
     WHERE status IN ('Predicted', 'Confirmed')
     GROUP BY model_type`
  );
  const existingByModel = {};
  let existingTotal = 0;
  for (const r of countRows) {
    existingByModel[r.model_type] = r.cnt;
    existingTotal += r.cnt;
  }

  const availableSlots = Math.max(0, maxSlots - existingTotal);

  if (availableSlots <= 0) {
    // All slots full 鈫?push everything to waiting queue
    if (forceModel && modelQueues[forceModel]) {
      await pushToQueue(forceModel, modelQueues[forceModel]);
    } else {
      for (const [model, units] of Object.entries(modelQueues)) {
        await pushToQueue(model, units);
      }
    }
    return { batches: [], queued: true };
  }

  const forceFamily = normalizeModelFamily(forceModel);
  const modelsToProcess = forceModel && (familyQueues[forceModel] || familyQueues[forceFamily])
    ? [familyQueues[forceModel] ? forceModel : forceFamily]
    : Object.keys(familyQueues);

  // Allocate available slots to models by capacity_ratio
  const allocation = allocateSlots(modelsToProcess, ratio, availableSlots, existingByModel);

  const allBatches = [];
  const allUnitInserts = [];

  for (const model of modelsToProcess) {
    const units = familyQueues[model] || [];
    const slotsForModel = allocation[model] || 0;
    if (slotsForModel <= 0) {
      if (units.length > 0) await pushToQueue(model, units);
      continue;
    }

    const capacity = getCap(model);
    const familyCandidates = getFamilyCandidates(model, enabledModels);
    const fillWeights = buildLevel2Weights(level2, model, familyCandidates);
    const { batches, usedUnits, remainingUnits } = splitIntoBatches(
      units, capacity, gapDays, slotsForModel, model, fillWeights
    );

    allBatches.push(...batches);

    // Build unit inserts
    const now = new Date();
    for (let bi = 0; bi < batches.length; bi++) {
      const batch = batches[bi];
      for (let si = 0; si < batch.units.length; si++) {
        const u = batch.units[si];
        allUnitInserts.push([
          generateUUID(),                                // unit_id
          null,                                           // serial_no (filled later by MES)
          batch.batch_id,                                 // batch_id
          si + 1,                                         // slot_index (1-based)
          u.model_type || model,                           // model_type
          null,                                           // production_line_id
          'Pending',                                      // status
          u.contract_no || null,                          // contract_no
          u.customer || null,                             // customer
          u.dealer || null,                               // dealer_id
          null,                                           // sales_id
          null,                                           // order_remark
          0,                                              // is_locked
          null,                                           // locked_by
          null,                                           // locked_at
          u.is_contract_pinned || 0,                      // is_contract_pinned
          now,                                            // created_at
          now                                             // updated_at
        ]);
      }
    }

    // Push remaining to queue
    if (remainingUnits.length > 0) {
      await pushToQueue(model, remainingUnits);
    }
  }

  return { batches: allBatches, unitInserts: allUnitInserts };
}

/**
 * Allocate available batch slots to models by capacity_ratio.
 * Returns { model: slotCount }
 */
function allocateSlots(models, ratio, totalSlots, existingByModel) {
  const allocation = {};
  if (!models.length || totalSlots <= 0) return allocation;

  const modelTargetRatio = parseRatioConfig(ratio, models);
  const totalTarget = Object.values(modelTargetRatio).reduce((s, v) => s + v, 0) || 100;
  const modelList = [...models];
  const existingTotal = Object.values(existingByModel).reduce((s, v) => s + v, 0) || 1;

  // Sort models by deviation from target (most under-represented first)
  const deviations = modelList.map(m => {
    const currentShare = ((existingByModel[m] || 0) / existingTotal) * 100;
    const targetShare = ((modelTargetRatio[m] || 0) / totalTarget) * 100;
    return { model: m, deviation: targetShare - currentShare };
  });
  deviations.sort((a, b) => b.deviation - a.deviation);

  // Distribute slots
  for (const { model } of deviations) {
    allocation[model] = 0;
  }

  let remaining = totalSlots;
  // First pass: proportional allocation
  let assignedTotal = 0;
  for (const { model } of deviations) {
    const share = (modelTargetRatio[model] || 0) / totalTarget;
    const slots = Math.floor(remaining * share);
    allocation[model] = slots;
    assignedTotal += slots;
  }

  remaining -= assignedTotal;
  // Second pass: give remainder to most under-represented
  const sorted = [...deviations].sort((a, b) => b.deviation - a.deviation);
  for (let i = 0; i < remaining; i++) {
    allocation[sorted[i % sorted.length].model]++;
  }

  return allocation;
}

/**
 * Split a model's units into batches respecting gap threshold and capacity.
 */
function splitIntoBatches(units, capacity, gapDays, maxBatches, modelType, fillWeights) {
  const batches = [];
  let currentBatch = [];
  const usedUnits = [];
  const remainingUnits = [];
  let batchNo = 0;

  for (const unit of units) {
    // Rule 1: gap threshold
    if (currentBatch.length > 0) {
      const lastDue = currentBatch[currentBatch.length - 1].due_date;
      const thisDue = unit.due_date;
      const diffDays = (thisDue - lastDue) / (1000 * 60 * 60 * 24);
      if (diffDays > gapDays) {
        if (batchNo < maxBatches && currentBatch.length > 0) {
          batches.push(finalizeBatch(batchNo, modelType, capacity, currentBatch, fillWeights));
          batchNo++;
        } else {
          remainingUnits.push(...currentBatch);
        }
        currentBatch = [];
      }
    }

    currentBatch.push(unit);

    // Rule 2: capacity reached
    if (currentBatch.length >= capacity) {
      if (batchNo < maxBatches) {
        batches.push(finalizeBatch(batchNo, modelType, capacity, [...currentBatch], fillWeights));
        batchNo++;
      } else {
        remainingUnits.push(...currentBatch);
      }
      currentBatch = [];
    }
  }

  // Finalize remaining
  if (currentBatch.length > 0) {
    if (batchNo < maxBatches) {
      batches.push(finalizeBatch(batchNo, modelType, capacity, [...currentBatch], fillWeights));
      batchNo++;
    } else {
      remainingUnits.push(...currentBatch);
    }
  }

  // Collect used
  for (const b of batches) {
    for (const u of b.units) usedUnits.push(u);
  }

  return { batches, usedUnits, remainingUnits };
}

/**
 * Fill a batch to its exact capacity with NULL-contract units.
 */
function finalizeBatch(batchNo, modelType, capacity, contractUnits, fillWeights) {
  const monthKey = new Date().toISOString().slice(0, 7).replace(/-/g, '');
  const familyKey = normalizeModelFamily(modelType) || 'MIX';
  const uniq = generateUUID().slice(0, 8).toUpperCase();
  const batchId = `BATCH-${monthKey}-${familyKey}-${String(batchNo + 1).padStart(3, '0')}-${uniq}`;

  const filledUnits = [...contractUnits];

  // Fill remaining slots with null-contract units
  const emptySlots = capacity - filledUnits.length;
  const fillPlan = buildModelFillPlan(fillWeights || { [modelType]: 1 }, emptySlots);
  for (let i = 0; i < emptySlots; i++) {
    const detailedModel = fillPlan[i] || pickModelByRatio(fillWeights || { [modelType]: 1 }, i);
    filledUnits.push({
      contract_no: null,
      model_type: detailedModel || modelType,
      customer: null,
      dealer: null,
      due_date: null,
      is_contract_pinned: 0
    });
  }

  const dueDates = contractUnits.map(u => u.due_date).filter(Boolean);
  dueDates.sort((a, b) => a - b);

  return {
    batch_id: batchId,
    batch_no: batchNo + 1,
    model_type: modelType,
    capacity,
    due_date_start: dueDates.length ? dueDates[0] : null,
    due_date_end: dueDates.length ? dueDates[dueDates.length - 1] : null,
    units: filledUnits
  };
}

// ============================================================
// Empty slot recalculation (after drag/move)
// ============================================================

async function refillEmptySlots(batchId) {
  const conn = await db.getConnection();
  try {
    await conn.beginTransaction();

    // Get batch info
    const [batches] = await conn.query('SELECT * FROM batches WHERE batch_id = ? FOR UPDATE', [batchId]);
    if (!batches.length) throw new Error('Batch not found');
    const batch = batches[0];

    const capacity = batch.capacity;
    const modelType = batch.model_type;
    const family = normalizeModelFamily(modelType);
    const ratio = await getCapacityRatio();
    const enabledModels = await getEnabledModelTypes();
    const familyCandidates = getFamilyCandidates(family, enabledModels);
    const fillWeights = buildLevel2Weights(ratio?.level2 || {}, family, familyCandidates);

    // Count locked + contract-pinned units (these are preserved)
    const [lockedUnits] = await conn.query(
      `SELECT COUNT(*) as cnt FROM units WHERE batch_id = ? AND is_locked = 1`, [batchId]
    );
    const [contractUnits] = await conn.query(
      `SELECT COUNT(*) as cnt FROM units WHERE batch_id = ? AND contract_no IS NOT NULL AND is_locked = 0`, [batchId]
    );

    const fixedCount = lockedUnits[0].cnt + contractUnits[0].cnt;
    const slotTotal = Math.max(0, capacity - fixedCount);

    // If no empty slots needed, we're done
    if (slotTotal <= 0) {
      // Remove excess null-contract, non-locked units
      await conn.query(
        `DELETE FROM units WHERE batch_id = ? AND contract_no IS NULL AND is_locked = 0
         ORDER BY slot_index DESC LIMIT ${Math.abs(slotTotal)}`,
        [batchId]
      );
      await conn.commit();
      return { refilled: 0 };
    }

    // Otherwise, ensure we have exactly slotTotal null-contract units
    const [nullUnits] = await conn.query(
      `SELECT unit_id FROM units WHERE batch_id = ? AND contract_no IS NULL AND is_locked = 0`, [batchId]
    );
    const currentNullCount = nullUnits.length;

    if (currentNullCount < slotTotal) {
      // Add more null units
      const toAdd = slotTotal - currentNullCount;
      const now = new Date();
      const maxSlot = await getMaxSlot(conn, batchId);
      for (let i = 0; i < toAdd; i++) {
        const detailedModel = pickModelByRatio(fillWeights, currentNullCount + i);
        await conn.query(
          `INSERT INTO units (unit_id, batch_id, slot_index, model_type, status, is_locked, created_at, updated_at)
           VALUES (?, ?, ?, ?, 'Pending', 0, ?, ?)`,
          [generateUUID(), batchId, maxSlot + i + 1, detailedModel || modelType, now, now]
        );
      }
    } else if (currentNullCount > slotTotal) {
      // Remove excess
      const toRemove = currentNullCount - slotTotal;
      const ids = nullUnits.slice(0, toRemove).map(u => u.unit_id);
      await conn.query(`DELETE FROM units WHERE unit_id IN (?)`, [ids]);
    }

    // Re-assign all remaining null-contract slots by configured level2 ratio.
    const [nullUnitsAfter] = await conn.query(
      `SELECT unit_id FROM units
       WHERE batch_id = ? AND contract_no IS NULL AND is_locked = 0
       ORDER BY slot_index ASC`,
      [batchId]
    );
    const fillPlan = buildModelFillPlan(fillWeights, nullUnitsAfter.length);
    for (let i = 0; i < nullUnitsAfter.length; i++) {
      const detailedModel = fillPlan[i] || pickModelByRatio(fillWeights, i);
      await conn.query(
        `UPDATE units SET model_type = ?, updated_at = NOW() WHERE unit_id = ?`,
        [detailedModel || modelType, nullUnitsAfter[i].unit_id]
      );
    }

    // Re-number slot_index
    const [allUnits] = await conn.query(
      `SELECT unit_id FROM units WHERE batch_id = ? ORDER BY is_locked DESC, contract_no IS NOT NULL DESC, slot_index ASC`,
      [batchId]
    );
    for (let i = 0; i < allUnits.length; i++) {
      await conn.query(`UPDATE units SET slot_index = ? WHERE unit_id = ?`, [i + 1, allUnits[i].unit_id]);
    }

    await conn.commit();
    return { refilled: slotTotal };
  } catch (err) {
    await conn.rollback();
    throw err;
  } finally {
    conn.release();
  }
}

async function getMaxSlot(conn, batchId) {
  const [rows] = await conn.query(
    'SELECT MAX(slot_index) as m FROM units WHERE batch_id = ?', [batchId]
  );
  return rows[0].m || 0;
}

// ============================================================
// Waiting queue management
// ============================================================

async function pushToQueue(modelType, units) {
  // Group by contract_no
  const byContract = {};
  for (const u of units) {
    const key = u.contract_no || '__null__';
    if (!byContract[key]) {
      byContract[key] = { ...u, count: 0 };
    }
    byContract[key].count++;
  }

  const now = new Date();
  for (const [key, item] of Object.entries(byContract)) {
    if (key === '__null__') continue; // skip null contracts
    // Upsert: update quantity if already in queue
    const [existing] = await db.query(
      `SELECT id, quantity_remaining FROM production_queue
       WHERE contract_no = ? AND model_type = ? AND status = 'Waiting'`,
      [item.contract_no, modelType]
    );
    if (existing.length) {
      await db.query(
        `UPDATE production_queue SET quantity_remaining = quantity_remaining + ? WHERE id = ?`,
        [item.count, existing[0].id]
      );
    } else {
      await db.query(
        `INSERT INTO production_queue (model_type, contract_no, customer, dealer, due_date, quantity_remaining, status)
         VALUES (?, ?, ?, ?, ?, ?, 'Waiting')`,
        [modelType, item.contract_no, item.customer, item.dealer, item.due_date, item.count]
      );
    }
  }
}

/**
 * Pull contracts from waiting queue and generate new batches.
 * Called when a batch is confirmed (slot released).
 */
async function pullFromQueue(modelType = null) {
  const maxSlots = await getMaxBatchSlots();
  const [countRows] = await db.query(
    `SELECT COUNT(*) as cnt FROM batches WHERE status IN ('Predicted', 'Confirmed')`
  );
  const currentCount = countRows[0].cnt;
  const available = maxSlots - currentCount;

  if (available <= 0) return { generated: 0, reason: 'No available slots' };

  const getCap = await getModelCapacity();
  const ratio = await getCapacityRatio();
  const gapDays = await getGapThreshold();

  // Determine which model to pull
  let targetModel = modelType;
  if (!targetModel) {
    // Pick model most under-represented by capacity_ratio
    const [modelCounts] = await db.query(
      `SELECT model_type, COUNT(*) as cnt FROM batches WHERE status IN ('Predicted', 'Confirmed') GROUP BY model_type`
    );
    const [queueModels] = await db.query(
      `SELECT DISTINCT model_type FROM production_queue WHERE status = 'Waiting'`
    );
    const existing = {};
    for (const r of modelCounts) existing[r.model_type] = r.cnt;
    const candidateModels = queueModels.map((r) => r.model_type).filter(Boolean);
    const total = Object.values(existing).reduce((s, v) => s + v, 0) || 1;

    let maxDeviation = -Infinity;
    const targetRatioByModel = parseRatioConfig(
      ratio,
      candidateModels.length ? candidateModels : Object.keys(existing)
    );
    for (const [model, target] of Object.entries(targetRatioByModel)) {
      const currentShare = ((existing[model] || 0) / total) * 100;
      const totalTarget = Object.values(targetRatioByModel).reduce((s, v) => s + v, 0) || 100;
      const targetShare = (target / totalTarget) * 100;
      const deviation = targetShare - currentShare;
      if (deviation > maxDeviation) {
        maxDeviation = deviation;
        targetModel = model;
      }
    }
    if (!targetModel && candidateModels.length) targetModel = candidateModels[0];
  }

  // Fetch from queue
  const [queueItems] = await db.query(
    `SELECT * FROM production_queue
     WHERE model_type = ? AND status = 'Waiting'
     ORDER BY due_date ASC, id ASC
     LIMIT 100`,
    [targetModel]
  );

  if (!queueItems.length) return { generated: 0, reason: 'Queue empty for model ' + targetModel };

  // Expand into unit objects
  const capacity = getCap(targetModel);
  const units = [];
  for (const item of queueItems) {
    const pullCount = Math.min(item.quantity_remaining, capacity - (units.length % capacity));
    for (let i = 0; i < pullCount; i++) {
      units.push({
        contract_no: item.contract_no,
        model_type: targetModel,
        customer: item.customer,
        dealer: item.dealer,
        due_date: item.due_date ? new Date(item.due_date) : null,
        is_contract_pinned: 0
      });
    }
  }

  // Generate batches (at most available slots)
  const { batches, unitInserts } = await (async () => {
    const { batches: b, unitInserts: u } = await generateBatchesForQueue(
      targetModel, units, capacity, gapDays, available
    );
    return { batches: b, unitInserts: u };
  })();

  // Insert into DB within a transaction
  const conn = await db.getConnection();
  try {
    await conn.beginTransaction();

    const now = new Date();
    for (const batch of batches) {
      await conn.query(
        `INSERT INTO batches (batch_id, batch_no, model_type, capacity, status,
         due_date_start, due_date_end, source, created_at, updated_at)
         VALUES (?, ?, ?, ?, 'Predicted', ?, ?, 'algorithm', ?, ?)`,
        [batch.batch_id, batch.batch_no, batch.model_type, batch.capacity,
         batch.due_date_start, batch.due_date_end, now, now]
      );
    }

    if (unitInserts.length > 0) {
      const placeholders = unitInserts.map(() => '(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)').join(',');
      const values = unitInserts.flat();
      await conn.query(
        `INSERT INTO units (unit_id, serial_no, batch_id, slot_index, model_type,
         production_line_id, status, contract_no, customer, dealer_id, sales_id,
         order_remark, is_locked, locked_by, locked_at, is_contract_pinned, created_at, updated_at)
         VALUES ${placeholders}`,
        values
      );
    }

    // Mark queue items as pulled (reduce quantity or mark pulled)
    for (const item of queueItems) {
      const usedCount = units.filter(u => u.contract_no === item.contract_no).length;
      const remaining = item.quantity_remaining - usedCount;
      if (remaining <= 0) {
        await conn.query(`UPDATE production_queue SET status = 'Pulled', quantity_remaining = 0 WHERE id = ?`, [item.id]);
      } else {
        await conn.query(`UPDATE production_queue SET quantity_remaining = ? WHERE id = ?`, [remaining, item.id]);
      }
    }

    await conn.commit();
    return { generated: batches.length };
  } catch (err) {
    await conn.rollback();
    throw err;
  } finally {
    conn.release();
  }
}

async function generateBatchesForQueue(modelType, units, capacity, gapDays, maxBatches) {
  const ratio = await getCapacityRatio();
  const enabledModels = await getEnabledModelTypes();
  const family = normalizeModelFamily(modelType);
  const fillWeights = buildLevel2Weights(ratio?.level2 || {}, family, getFamilyCandidates(family, enabledModels));
  const { batches, remainingUnits } = splitIntoBatches(units, capacity, gapDays, maxBatches, modelType, fillWeights);
  const unitInserts = [];
  const now = new Date();

  for (const batch of batches) {
    for (let si = 0; si < batch.units.length; si++) {
      const u = batch.units[si];
      unitInserts.push([
        generateUUID(), null, batch.batch_id, si + 1, u.model_type || modelType, null, 'Pending',
        u.contract_no || null, u.customer || null, u.dealer || null, null, null,
        0, null, null, u.is_contract_pinned || 0, now, now
      ]);
    }
  }

  // Push remaining back to queue
  if (remainingUnits.length > 0) {
    await pushToQueue(modelType, remainingUnits);
  }

  return { batches, unitInserts };
}

// ============================================================
// Full recompute (Cron trigger)
// ============================================================

async function fullRecompute() {
  const lockToken = await acquireLock('batch:slot', 60);
  if (!lockToken) throw new Error('Another recompute is in progress');

  try {
    // Load contracts, skip locked units
    const modelQueues = await loadContractsByModel();

    // Clear existing predicted batches that have no locked units
    // (Preserve batches with locked or confirmed units)
    const [batchesToKeep] = await db.query(`
      SELECT DISTINCT b.batch_id FROM batches b
      JOIN units u ON b.batch_id COLLATE utf8mb4_general_ci = u.batch_id COLLATE utf8mb4_general_ci
      WHERE u.is_locked = 1 OR b.status = 'Confirmed'
    `);
    const keepIds = batchesToKeep.map(r => r.batch_id);

    const conn = await db.getConnection();
    try {
      await conn.beginTransaction();

      if (keepIds.length > 0) {
        await conn.query(
          `DELETE FROM units
           WHERE batch_id IN (SELECT batch_id FROM batches WHERE status = 'Predicted' AND batch_id NOT IN (?))`,
          [keepIds]
        );
        await conn.query(
          `DELETE FROM batches
           WHERE status = 'Predicted' AND batch_id NOT IN (?)`,
          [keepIds]
        );
      } else {
        await conn.query(`DELETE FROM units WHERE batch_id IN (SELECT batch_id FROM batches WHERE status = 'Predicted')`);
        await conn.query(`DELETE FROM batches WHERE status = 'Predicted'`);
      }

      const result = await generateBatches(modelQueues);
      const batchesToInsert = Array.isArray(result?.batches) ? result.batches : [];
      const unitInserts = Array.isArray(result?.unitInserts) ? result.unitInserts : [];
      const now = new Date();
      for (const batch of batchesToInsert) {
        await conn.query(
          `INSERT INTO batches (batch_id, batch_no, model_type, capacity, status, due_date_start, due_date_end, source, created_at, updated_at)
           VALUES (?, ?, ?, ?, 'Predicted', ?, ?, 'algorithm', ?, ?)`,
          [batch.batch_id, batch.batch_no, batch.model_type, batch.capacity, batch.due_date_start, batch.due_date_end, now, now]
        );
      }

      if (unitInserts.length > 0) {
        const placeholders = unitInserts.map(() => '(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)').join(',');
        const values = unitInserts.flat();
        await conn.query(
          `INSERT INTO units (unit_id, serial_no, batch_id, slot_index, model_type,
            production_line_id, status, contract_no, customer, dealer_id, sales_id,
            order_remark, is_locked, locked_by, locked_at, is_contract_pinned, created_at, updated_at)
           VALUES ${placeholders}`,
          values
        );
      }

      await conn.commit();
      return {
        generated_batches: batchesToInsert.length,
        generated_units: unitInserts.length,
        preserved_batches: keepIds.length
      };
    } catch (err) {
      await conn.rollback();
      throw err;
    } finally {
      conn.release();
    }
  } finally {
    await releaseLock('batch:slot', lockToken);
  }
}

async function getPredictedAchievement(windowSize = 20) {
  const ratio = await getCapacityRatio();
  const enabledModels = await getEnabledModelTypes();
  const [recent] = await db.query(
    `SELECT batch_id FROM batches
     WHERE status = 'Predicted'
     ORDER BY updated_at DESC
     LIMIT ?`,
    [windowSize]
  );
  const batchIds = recent.map((r) => r.batch_id);
  if (!batchIds.length) {
    return { window_size: windowSize, actual: {}, target: {}, delta: {} };
  }
  const [rows] = await db.query(
    `SELECT model_type, COUNT(*) AS cnt
     FROM units
     WHERE batch_id IN (?) AND contract_no IS NULL
     GROUP BY model_type`,
    [batchIds]
  );
  const total = rows.reduce((s, r) => s + Number(r.cnt || 0), 0) || 1;
  const actual = {};
  for (const r of rows) actual[r.model_type] = Number((Number(r.cnt || 0) * 100 / total).toFixed(2));
  const target = parseRatioConfig(ratio, enabledModels);
  const delta = {};
  for (const m of enabledModels) {
    const t = Number((target[m] || 0).toFixed(2));
    const a = Number((actual[m] || 0).toFixed(2));
    delta[m] = Number((a - t).toFixed(2));
    target[m] = t;
    actual[m] = a;
  }
  return { window_size: windowSize, actual, target, delta };
}

// ============================================================
// Helpers
// ============================================================

function generateUUID() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
    const r = Math.random() * 16 | 0;
    const v = c === 'x' ? r : (r & 0x3 | 0x8);
    return v.toString(16);
  });
}

module.exports = {
  generateBatches,
  refillEmptySlots,
  fullRecompute,
  pullFromQueue,
  getModelCapacity,
  getCapacityRatio,
  getMaxBatchSlots,
  getGapThreshold,
  pushToQueue,
  loadContractsByModel,
  parseDueDate,
  getPredictedAchievement,
  normalizeModelFamily,
  getEnabledModelTypes
};
