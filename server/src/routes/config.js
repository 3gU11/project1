const router = require('express').Router();
const db = require('../db');
const { authMiddleware, adminOnly } = require('../middleware/auth');
const { normalizeModelFamily } = require('../engine/predictor');

router.use(authMiddleware);

// GET /api/capacity-ratio
router.get('/capacity-ratio', async (req, res) => {
  const [rows] = await db.query(
    `SELECT config_value, updated_at, updated_by FROM system_config WHERE config_key = 'capacity_ratio'`
  );
  if (!rows.length) {
    return res.json({
      ratio: {
        level1: { G: 24, XS: 76, AUTO: 0 },
        level2: {
          G: { '300': 11, '400': 67, '500': 14, '600': 8 },
          XS: { '400': 51, '500': 24, '600': 17, 'BIG': 8 },
          AUTO: { '400': 51, '500': 24, '600': 17, 'BIG': 8 }
        }
      }
    });
  }
  const parsed = JSON.parse(rows[0].config_value);
  const ratio = parsed?.level1 ? parsed : { level1: parsed, level2: {} };
  res.json({ ratio, updated_at: rows[0].updated_at, updated_by: rows[0].updated_by });
});

// PATCH /api/capacity-ratio — update ratio
router.patch('/capacity-ratio', adminOnly, async (req, res) => {
  const ratio = req.body;
  if (!ratio || typeof ratio !== 'object') return res.status(400).json({ error: 'JSON ratio object required' });

  const isNested = ratio.level1 && typeof ratio.level1 === 'object';
  if (isNested) {
    const l1 = ratio.level1;
    const level1Total = Number(l1.G || 0) + Number(l1.XS || 0) + Number(l1.AUTO || 0);
    if (Math.abs(level1Total - 100) > 1) {
      return res.status(400).json({ error: `level1 ratio should sum to ~100, got ${level1Total}` });
    }
  } else {
    const total = Object.values(ratio).reduce((s, v) => s + Number(v), 0);
    if (Math.abs(total - 100) > 1) {
      return res.status(400).json({ error: `Ratio should sum to ~100, got ${total}` });
    }
  }

  await db.query(
    `UPDATE system_config SET config_value = ?, updated_by = ?, updated_at = NOW() WHERE config_key = 'capacity_ratio'`,
    [JSON.stringify(ratio), req.user.username]
  );

  const io = req.app.get('io');
  if (io) io.emit('config:updated', { key: 'capacity_ratio', value: ratio });

  res.json({ success: true, ratio });
});

// GET /api/system-config — get all config
router.get('/system-config', adminOnly, async (req, res) => {
  const [rows] = await db.query(`SELECT config_key, config_value, description, updated_at FROM system_config`);
  res.json({ configs: rows });
});

// GET /api/model-types
router.get('/model-types', async (req, res) => {
  const [rows] = await db.query(
    `SELECT model_name, enabled, sort_order
     FROM model_dictionary
     WHERE enabled = 1
       AND UPPER(TRIM(model_name)) NOT IN ('G', 'XS', 'AUTO')
     ORDER BY sort_order ASC, model_name ASC`
  );
  res.json({
    model_types: rows.map((r) => ({
      model_type: r.model_name,
      model_family: normalizeModelFamily(r.model_name)
    }))
  });
});

module.exports = router;
