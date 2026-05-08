const router = require('express').Router();
const db = require('../db');
const { authMiddleware, adminOnly } = require('../middleware/auth');
const { fullRecompute, loadContractsByModel, getPredictedAchievement, normalizeModelFamily } = require('../engine/predictor');

router.use(authMiddleware);

// POST /api/forecast/recompute — manual full recompute (admin debug)
router.post('/recompute', adminOnly, async (req, res) => {
  try {
    const result = await fullRecompute();
    const achievement = await getPredictedAchievement(20);
    res.json({ success: true, ...result, achievement });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
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
