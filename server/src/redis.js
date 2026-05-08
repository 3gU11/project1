const Redis = require('ioredis');

let redis = null;
const memoryLocks = new Map();

function isRedisEnabled() {
  return String(process.env.REDIS_ENABLED || 'true').toLowerCase() === 'true';
}

async function initRedis() {
  if (!isRedisEnabled()) {
    return null;
  }

  redis = new Redis({
    host: process.env.REDIS_HOST || '127.0.0.1',
    port: parseInt(process.env.REDIS_PORT || '6379'),
    maxRetriesPerRequest: 3,
    retryStrategy(times) {
      if (times > 3) return null;
      return Math.min(times * 200, 1000);
    }
  });

  redis.on('error', (err) => {
    console.error('[redis] connection error:', err.message);
  });

  return redis;
}

function getRedis() {
  return redis;
}

/**
 * Acquire distributed lock
 * @returns {string|null} lock token if acquired, null otherwise
 */
async function acquireLock(key, ttl = 30) {
  if (!isRedisEnabled() || !redis) {
    const now = Date.now();
    const lockKey = `lock:${key}`;
    const existing = memoryLocks.get(lockKey);
    if (existing && existing.expiresAt > now) return null;
    const token = Date.now().toString(36) + Math.random().toString(36).slice(2);
    memoryLocks.set(lockKey, { token, expiresAt: now + ttl * 1000 });
    return token;
  }

  const token = Date.now().toString(36) + Math.random().toString(36).slice(2);
  const ok = await redis.set(`lock:${key}`, token, 'EX', ttl, 'NX');
  return ok === 'OK' ? token : null;
}

/**
 * Release lock with token safety
 */
async function releaseLock(key, token) {
  if (!isRedisEnabled() || !redis) {
    const lockKey = `lock:${key}`;
    const existing = memoryLocks.get(lockKey);
    if (existing && existing.token === token) {
      memoryLocks.delete(lockKey);
      return 1;
    }
    return 0;
  }

  const script = `
    if redis.call("get", KEYS[1]) == ARGV[1] then
      return redis.call("del", KEYS[1])
    else
      return 0
    end
  `;
  return redis.eval(script, 1, `lock:${key}`, token);
}

module.exports = { initRedis, getRedis, acquireLock, releaseLock };
