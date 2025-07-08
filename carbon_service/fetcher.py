import os
import httpx
from cache import get_cached, set_cached
from dotenv import load_dotenv
import time
import logging

load_dotenv()

# POP to region mapping (for demo)
POPS = {
    "us-east": "US-NEISO",      # Example region code for ElectricityMap
    "eu-west": "GB",             # UK
    "ap-southeast": "SG"         # Singapore
}

CONTINENT_DEFAULTS = {
    "us-east": 400,
    "eu-west": 300,
    "ap-southeast": 500
}

CACHE_KEY = "carbon_intensities"
CACHE_TTL = 60  # seconds

ELECTRICITYMAP_API_KEY = os.getenv("ELECTRICITYMAP_API_KEY")
WATTTIME_USERNAME = os.getenv("WATTTIME_USERNAME")
WATTTIME_PASSWORD = os.getenv("WATTTIME_PASSWORD")

async def fetch_electricitymap():
    if not ELECTRICITYMAP_API_KEY:
        raise Exception("Missing ElectricityMap API key")
    headers = {"auth-token": ELECTRICITYMAP_API_KEY}
    async with httpx.AsyncClient(timeout=10) as client:
        results = {}
        for pop, region in POPS.items():
            try:
                url = f"https://api.electricitymap.org/v3/carbon-intensity/regions/{region}"
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                results[pop] = data.get("carbonIntensity", CONTINENT_DEFAULTS[pop])
            except Exception as e:
                logging.warning(f"ElectricityMap fetch failed for {pop}: {e}")
                results[pop] = None
        if all(v is not None for v in results.values()):
            return results
        raise Exception("Partial or total ElectricityMap failure")

async def fetch_watttime():
    if not (WATTTIME_USERNAME and WATTTIME_PASSWORD):
        raise Exception("Missing WattTime credentials")
    async with httpx.AsyncClient(timeout=10) as client:
        # Authenticate
        try:
            resp = await client.get(
                "https://api.watttime.org/v2/login",
                auth=(WATTTIME_USERNAME, WATTTIME_PASSWORD)
            )
            resp.raise_for_status()
            token = resp.json()["token"]
        except Exception as e:
            logging.warning(f"WattTime login failed: {e}")
            raise
        headers = {"Authorization": f"Bearer {token}"}
        results = {}
        for pop, region in POPS.items():
            try:
                # This is a placeholder endpoint; real endpoint may differ
                url = f"https://api.watttime.org/v2/index?region={region}"
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                results[pop] = data.get("carbonIntensity", CONTINENT_DEFAULTS[pop])
            except Exception as e:
                logging.warning(f"WattTime fetch failed for {pop}: {e}")
                results[pop] = None
        if all(v is not None for v in results.values()):
            return results
        raise Exception("Partial or total WattTime failure")

async def get_carbon_intensities():
    # Try cache first
    cached = await get_cached(CACHE_KEY)
    if cached:
        import json
        return json.loads(cached)
    # Try live fetches
    try:
        results = await fetch_electricitymap()
        await set_cached(CACHE_KEY, str(results), CACHE_TTL)
        return results
    except Exception as e:
        logging.warning(f"ElectricityMap failed: {e}")
    try:
        results = await fetch_watttime()
        await set_cached(CACHE_KEY, str(results), CACHE_TTL)
        return results
    except Exception as e:
        logging.warning(f"WattTime failed: {e}")
    # Try last 1h average from cache (not implemented, fallback to defaults)
    logging.warning("Falling back to continent defaults")
    return CONTINENT_DEFAULTS 