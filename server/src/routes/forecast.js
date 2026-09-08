const router = require('express').Router();
const db = require('../db');
const { authMiddleware, adminOnly } = require('../middleware/auth');
const { fullRecompute, loadContractsByModel, getPredictedAchievement, normalizeModelFamily } = require('../engine/predictor');
const crypto = require('crypto');

router.use(authMiddleware);

// POST /api/forecast/recompute — manual full recompute (admin debug)
router.post('/recompute', adminOnly, async (req, res) => {
  const jobId = `recompute-${Date.now()}-${crypto.randomBytes(4).toString('hex')}`;
  const parameters = { target_slot_no: req.body?.target_slot_no ?? 1, is_clicked: !!req.body?.is_clicked };
  await db.query(`INSERT INTO sandbox_recompute_jobs (job_id, status, requested_by, parameters_json) VALUES (?, 'queued', ?, ?)`, [jobId, req.user.username, JSON.stringify(parameters)]);
  res.status(202).json({ success: true, job_id: jobId, status: 'queued' });
  setImmediate(async () => {
    try {
      await db.query(`UPDATE sandbox_recompute_jobs SET status='running', started_at=NOW() WHERE job_id=?`, [jobId]);
      const result = await fullRecompute();
      const achievement = await getPredictedAchievement(20);
      await db.query(`UPDATE sandbox_recompute_jobs SET status='succeeded', result_json=?, completed_at=NOW() WHERE job_id=?`, [JSON.stringify({ ...result, achievement }), jobId]);
    } catch (err) {
      await db.query(`UPDATE sandbox_recompute_jobs SET status='failed', error_message=?, completed_at=NOW() WHERE job_id=?`, [String(err.message || err).slice(0, 2000), jobId]).catch(() => {});
    }
  });
});

router.get('/recompute/:job_id', adminOnly, async (req, res) => {
  const [rows] = await db.query(`SELECT job_id, status, requested_by, parameters_json, result_json, error_message, started_at, completed_at, created_at, updated_at FROM sandbox_recompute_jobs WHERE job_id=?`, [req.params.job_id]);
  if (!rows.length) return res.status(404).json({ error: 'Recompute job not found' });
  const row = rows[0];
  const parse = (value) => { try { return value ? JSON.parse(value) : null; } catch (_) { return null; } };
  res.json({ ...row, parameters: parse(row.parameters_json), result: parse(row.result_json) });
});

// GET /api/forecast/achievement - target vs actual in latest predicted batches
router.get('/achievement', adminOnly, async (req, res) => {
  try {
    const achievement = await getPredictedAchievement(20);
    res.json({ achievement });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// GET /api/forecast/preview — preview batch generation without saving
router.get('/preview', adminOnly, async (req, res) => {
  try {
    const modelQueues = await loadContractsByModel();
    const summary = {};
    const getCap = (m) => ({ G: 30, XS: 30, AUTO: 27 }[normalizeModelFamily(m)] || 30);

    for (const [model, units] of Object.entries(modelQueues)) {
      const cap = getCap(model);
      const batchesNeeded = Math.ceil(units.length / cap);
      summary[model] = {
        totalUnits: units.length,
        capacityPerBatch: cap,
        estimatedBatches: batchesNeeded,
        earliestDue: units[0]?.due_date || null,
        latestDue: units[units.length - 1]?.due_date || null
      };
    }

    res.json({ preview: summary });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

module.exports = router;
