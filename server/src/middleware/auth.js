const jwt = require('jsonwebtoken');

const JWT_SECRET = process.env.JWT_SECRET || 'change-me-in-production';

function authMiddleware(req, res, next) {
  const header = req.headers.authorization;
  if (!header || !header.startsWith('Bearer ')) {
    return res.status(401).json({ error: 'Missing or invalid token' });
  }
  const token = header.slice(7);
  try {
    const payload = jwt.verify(token, JWT_SECRET);
    req.user = payload;
    next();
  } catch (err) {
    return res.status(401).json({ error: 'Token expired or invalid' });
  }
}

function adminOnly(req, res, next) {
  const role = String(req.user?.role || '').toLowerCase();
  if (role !== 'admin' && role !== 'boss') {
    return res.status(403).json({ error: 'Admin access required' });
  }
  next();
}

module.exports = { authMiddleware, adminOnly, JWT_SECRET };
