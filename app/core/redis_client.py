import redis as redis_lib
import redis.asyncio as aioredis

from app.config import settings

# Sync client — distributed locking in evaluate_alerts (Celery worker context)
redis_client = redis_lib.from_url(settings.redis_url, decode_responses=True)

# Async client — health check (FastAPI async context)
# Shared instance so no new connection pool is created per request.
async_redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
