import redis.asyncio as redis

r = redis.from_url("redis://localhost:6379", decode_responses=True)

async def get_cached(key):
    return await r.get(key)

async def set_cached(key, value, ttl=60):
    await r.set(key, value, ex=ttl) 