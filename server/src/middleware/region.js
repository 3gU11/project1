/**
 * Region guard — PRD principle P5: backend must enforce region,
 * never rely on frontend hiding.
 */
function regionGuard(req, res, next) {
  const userRegion = (req.user?.region || '').toLowerCase();
  if (!userRegion) {
    return res.status(403).json({ error: 'No region assigned. Contact admin.' });
  }
  req.userRegion = userRegion;
  next();
}

module.exports = { regionGuard };
