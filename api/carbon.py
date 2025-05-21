import logging
from typing import Dict, Optional
import os
import aiohttp
import redis.asyncio as redis
from datetime import datetime, timezone, timedelta
import json
import ssl

logger = logging.getLogger(__name__)

# Zone mapping from our POPs to Electricity Maps zones
# Only US-NY-NYIS is available in our free tier
ZONE_MAPPING = {
    'us-east': 'US-NY-NYIS',  # New York ISO (only zone we have access to)
    'eu-west': None,          # Will use fallback value
    'ap-southeast': None      # Will use fallback value
}

# Fallback carbon intensities (gCO₂eq/kWh) for regions we don't have access to
FALLBACK_INTENSITIES = {
    'eu-west': 300.0,        # Typical value for Western Europe
    'ap-southeast': 450.0    # Typical value for Southeast Asia
}

class CarbonIntensityClient:
    def __init__(self):
        self.api_key = os.getenv("ELECTRICITY_MAPS_API_KEY")
        if not self.api_key:
            raise ValueError("ELECTRICITY_MAPS_API_KEY environment variable not set")
            
        self.base_url = "https://api.electricitymap.org/v3"
        self.cache_ttl = 300  # 5 minutes in seconds
        
        # Initialize Redis connection
        redis_host = os.getenv("REDIS_HOST", "localhost")
        redis_port = int(os.getenv("REDIS_PORT", "6379"))
        redis_db = int(os.getenv("REDIS_DB", "0"))
        self.redis = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            decode_responses=True
        )
        
        logger.info("Initialized CarbonIntensityClient with Electricity Maps API")

    async def _get_from_cache(self, zone: str) -> Optional[float]:
        """Get carbon intensity from Redis cache."""
        try:
            cached = await self.redis.get(f"carbon:{zone}")
            if cached:
                return float(cached)
        except Exception as e:
            logger.warning(f"Cache read failed for {zone}: {str(e)}")
        return None

    async def _set_cache(self, zone: str, intensity: float):
        """Set carbon intensity in Redis cache."""
        try:
            await self.redis.setex(
                f"carbon:{zone}",
                self.cache_ttl,
                str(intensity)
            )
        except Exception as e:
            logger.warning(f"Cache write failed for {zone}: {str(e)}")

    async def _fetch_intensity(self, zone: str) -> float:
        """Fetch carbon intensity from Electricity Maps API."""
        em_zone = ZONE_MAPPING.get(zone)
        
        # If no zone mapping or it's None, use fallback value
        if not em_zone:
            return FALLBACK_INTENSITIES.get(zone, 500.0)

        headers = {
            "auth-token": self.api_key
        }

        # Disable SSL verification for aiohttp
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        async with aiohttp.ClientSession(connector=connector) as session:
            try:
                url = f"{self.base_url}/carbon-intensity/latest?zone={em_zone}"
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        return float(data.get("carbonIntensity", 0))
                    else:
                        error_text = await response.text()
                        logger.error(f"API error for {zone}: {error_text}")
                        return FALLBACK_INTENSITIES.get(zone, 500.0)
            except Exception as e:
                logger.error(f"Failed to fetch intensity for {zone}: {str(e)}")
                return FALLBACK_INTENSITIES.get(zone, 500.0)

    async def get_zone_intensity(self, zone: str) -> float:
        """Get carbon intensity for a specific zone with caching."""
        # Try cache first
        cached = await self._get_from_cache(zone)
        if cached is not None:
            return cached

        # Fetch from API if not in cache
        intensity = await self._fetch_intensity(zone)
        await self._set_cache(zone, intensity)
        return intensity

    async def get_all_intensities(self) -> Dict[str, float]:
        """Get carbon intensities for all zones."""
        intensities = {}
        for zone in ZONE_MAPPING.keys():
            try:
                intensities[zone] = await self.get_zone_intensity(zone)
            except Exception as e:
                logger.error(f"Failed to get intensity for {zone}: {str(e)}")
                intensities[zone] = FALLBACK_INTENSITIES.get(zone, 500.0)
        return intensities

# Initialize the client as None
carbon_client = None

def get_carbon_client():
    global carbon_client
    if carbon_client is None:
        carbon_client = CarbonIntensityClient()
    return carbon_client 