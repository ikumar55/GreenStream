import logging
import os
import asyncio
import time
from typing import Dict, Optional
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
import aiohttp
import redis.asyncio as redis

logger = logging.getLogger(__name__)

# List of POPs to probe
POPS = {
    'us-east': 'https://www.google.com'
    # Add more POPs and their ping endpoints here
}

REDIS_KEY_PREFIX = "latency:"
CACHE_TTL = 60  # seconds
PROBE_INTERVAL = 30  # seconds

# Redis config (same as carbon.py)
redis_host = os.getenv("REDIS_HOST", "localhost")
redis_port = int(os.getenv("REDIS_PORT", "6379"))
redis_db = int(os.getenv("REDIS_DB", "0"))
redis_client = redis.Redis(
    host=redis_host,
    port=redis_port,
    db=redis_db,
    decode_responses=True
)

app = FastAPI()

async def probe_pop_latency(pop: str, url: str) -> Optional[float]:
    """Probe the POP and return latency in ms, or None if failed."""
    try:
        async with aiohttp.ClientSession() as session:
            start = time.perf_counter()
            async with session.get(url, timeout=5) as resp:
                await resp.text()
            latency = (time.perf_counter() - start) * 1000  # ms
            return latency
    except Exception as e:
        logger.warning(f"Latency probe failed for {pop}: {e}")
        return None

async def store_latency(pop: str, latency: float):
    try:
        await redis_client.setex(f"{REDIS_KEY_PREFIX}{pop}", CACHE_TTL, str(latency))
    except Exception as e:
        logger.warning(f"Failed to store latency for {pop}: {e}")

async def get_latency(pop: str) -> Optional[float]:
    try:
        val = await redis_client.get(f"{REDIS_KEY_PREFIX}{pop}")
        if val:
            return float(val)
    except Exception as e:
        logger.warning(f"Failed to get latency for {pop}: {e}")
    return None

async def probe_all_pops():
    while True:
        for pop, url in POPS.items():
            latency = await probe_pop_latency(pop, url)
            if latency is not None:
                await store_latency(pop, latency)
            else:
                # Fallback: keep last known good (do nothing), or implement rolling average here
                pass
        await asyncio.sleep(PROBE_INTERVAL)

@app.on_event("startup")
async def startup_event():
    # Start background task for periodic probing
    asyncio.create_task(probe_all_pops())

@app.get("/latency")
async def get_pop_latency(pop: str = Query(..., description="POP name, e.g. 'us-east'")):
    latency = await get_latency(pop)
    if latency is not None:
        return JSONResponse(content={"pop": pop, "latency_ms": latency, "source": "cache"})
    else:
        # Fallback: return a default or error
        return JSONResponse(content={"pop": pop, "latency_ms": None, "source": "fallback"}, status_code=404)

# Extension points:
# - Add Cloudflare Ping API integration
# - Add rolling average fallback
# - Add more POPs and endpoints 