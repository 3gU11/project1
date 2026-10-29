import asyncio
import logging
from .client import configured, list_contracts, prepare_preview

logger = logging.getLogger(__name__)


def sync_once():
    # Snapshot pending IDs before uploads change the queue. No local database or planning writes.
    ids = []
    for page in range(1, 10001):
        rows = list_contracts(page, 'submitted')
        ids.extend(row['id'] for row in rows)
        if len(rows) < 100:
            break
    ok = failed = 0
    for revision_id in dict.fromkeys(ids):
        try:
            prepare_preview(revision_id)
            ok += 1
        except Exception:
            failed += 1
            logger.warning('Contract preview retry pending: %s', revision_id)
    return {'prepared': ok, 'failed': failed}


async def worker_loop():
    if not configured():
        return
    while True:
        try:
            result = await asyncio.to_thread(sync_once)
            if result['prepared'] or result['failed']:
                logger.info('Contract previews prepared=%d retry_pending=%d', result['prepared'], result['failed'])
        except Exception:
            logger.warning('Contract cloud unavailable; will retry')
        await asyncio.sleep(60)
