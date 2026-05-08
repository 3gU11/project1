const router = require('express').Router();
const db = require('../db');
const { authMiddleware, adminOnly } = require('../middleware/auth');
const { pullFromQueue } = require('../engine/predictor');

router.use(authMiddleware);

// GET /api/production-queue — view waiting queue status
router.get('/', async (req, res) => {
  const [items] = await db.query(`
    SELECT model_type, COUNT(*) as contract_count, SUM(quantity_remaining) as total_units,
           MIN(due_date) as earliest_due, MAX(due_date) as latest_due
    FROM production_queue
    WHERE status = 'Waiting'
    GROUP BY model_type
    ORDER BY model_type
  `);

  const [details] = await db.query(`
    SELECT * FROM production_queue
    WHERE status = 'Waiting'
    ORDER BY model_type, due_date ASC, id ASC
  `);

  res.json({ summary: items, details });
});

// POST /api/production-queue/pull — manually pull from queue
router.post('/pull', adminOnly, async (req, res) => {
  const { model_type } = req.body;
  try {
    const result = await pullFromQueue(model_type || null);
    const io = req.app.get('io');
    if (io) io.emit('queue:updated', {});
    res.json(result);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

module.exports = router;
