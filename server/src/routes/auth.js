const router = require('express').Router();
const jwt = require('jsonwebtoken');
const db = require('../db');
const { JWT_SECRET } = require('../middleware/auth');

router.post('/login', async (req, res) => {
  try {
    const { username, password } = req.body;
    if (!username || !password) {
      return res.status(400).json({ error: 'Username and password required' });
    }

    const [cols] = await db.query(
      `SELECT COLUMN_NAME
       FROM information_schema.COLUMNS
       WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users'`
    );
    const colSet = new Set(cols.map((c) => c.COLUMN_NAME));
    const safe = (name, fallback) => (colSet.has(name) ? name : `${fallback} AS ${name}`);
    const selectList = [
      safe('username', 'NULL'),
      safe('password', 'NULL'),
      safe('role', "'viewer'"),
      safe('name', 'username'),
      safe('region', "''")
    ].join(', ');

    const hasStatus = colSet.has('status');
    const sql = hasStatus
      ? `SELECT ${selectList} FROM users WHERE username = ? AND status = ? LIMIT 1`
      : `SELECT ${selectList} FROM users WHERE username = ? LIMIT 1`;
    const params = hasStatus ? [username, 'active'] : [username];
    const [rows] = await db.query(sql, params);

    if (!rows.length || rows[0].password !== password) {
      return res.status(401).json({ error: 'Invalid credentials' });
    }

    const user = rows[0];
    const token = jwt.sign(
      { username: user.username, role: user.role, name: user.name, region: user.region },
      JWT_SECRET,
      { expiresIn: '24h' }
    );

    res.json({
      token,
      user: {
        username: user.username,
        role: user.role,
        name: user.name,
        region: user.region
      }
    });
  } catch (err) {
    console.error('[auth/login] failed:', err);
    res.status(500).json({ error: err.message });
  }
});

router.get('/me', async (req, res) => {
  // Simple token verification without full middleware
  const header = req.headers.authorization;
  if (!header || !header.startsWith('Bearer ')) {
    return res.status(401).json({ error: 'Missing token' });
  }
  try {
    const payload = jwt.verify(header.slice(7), JWT_SECRET);
    res.json({ user: payload });
  } catch {
    res.status(401).json({ error: 'Invalid token' });
  }
});

module.exports = router;
