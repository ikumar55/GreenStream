import logging
from typing import Dict, Optional, List
import os
import aiohttp
import redis.asyncio as redis
from datetime import datetime, timezone, timedelta
import json
import ssl
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class CarbonType(Enum):
    MARGINAL = "marginal"
    AVERAGE = "avg"

@dataclass
class CarbonData:
    gco2: float  # gCO₂/kWh
    ts: str      # timestamp
    type: CarbonType
    source: str  # "WattTime", "ESO", "GridStatus", "ENTSOE", "EM-stale"
    fresh_sec: int  # seconds since last update

# POP to Zone mapping for different providers
POP_ZONE_MAPPING = {
    # WattTime zones
    "sfo": "CAISO_NORTH",
    "lax": "CAISO_NORTH",
    "sea": "CAISO_NORTH",
    
    # GridStatus zones (US East)
    "iad": "NYISO",
    "nyc": "NYISO",
    "atl": "PJM",
    "chi": "PJM",
    
    # ESO zones (Great Britain)
    "lon": "GBR-13",
    "man": "GBR-13",
    
    # ENTSO-E zones (Europe)
    "ams": "ENTSOE_NL",
    "fra": "ENTSOE_FR",
    "ber": "ENTSOE_DE",
    "par": "ENTSOE_FR",
    
    # Legacy ElectricityMap zones (fallback)
    "us-east": "US-NY-NYIS",
    "eu-west": "EM-EU",
    "ap-southeast": "EM-AP"
}

# Fallback carbon intensities (gCO₂eq/kWh) for regions without live data
FALLBACK_INTENSITIES = {
    'eu-west': 300.0,        # Typical value for Western Europe
    'ap-southeast': 450.0,   # Typical value for Southeast Asia
    'us-west': 350.0,        # Typical value for US West
    'us-central': 400.0      # Typical value for US Central
}

class CarbonProvider:
    """Base class for carbon intensity providers"""
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.cache_ttl = 300  # 5 minutes default
    
    async def get_carbon_data(self, zone: str) -> Optional[CarbonData]:
        """Get carbon data for a zone. Override in subclasses."""
        raise NotImplementedError
    
    async def _get_from_cache(self, key: str) -> Optional[CarbonData]:
        """Get carbon data from Redis cache."""
        try:
            cached = await self.redis.get(key)
            if cached:
                data = json.loads(cached)
                return CarbonData(
                    gco2=data["gco2"],
                    ts=data["ts"],
                    type=CarbonType(data["type"]),
                    source=data["source"],
                    fresh_sec=data["fresh_sec"]
                )
        except Exception as e:
            logger.warning(f"Cache read failed for {key}: {str(e)}")
        return None
    
    async def _set_cache(self, key: str, data: CarbonData):
        """Set carbon data in Redis cache."""
        try:
            cache_data = {
                "gco2": data.gco2,
                "ts": data.ts,
                "type": data.type.value,
                "source": data.source,
                "fresh_sec": data.fresh_sec
            }
            await self.redis.setex(key, self.cache_ttl, json.dumps(cache_data))
        except Exception as e:
            logger.warning(f"Cache write failed for {key}: {str(e)}")

class WattTimeProvider(CarbonProvider):
    """WattTime MOER v3 provider for US West (CAISO_NORTH)"""
    
    def __init__(self, redis_client: redis.Redis):
        super().__init__(redis_client)
        self.username = os.getenv("WATTTIME_USERNAME")
        self.password = os.getenv("WATTTIME_PASSWORD")
        self.base_url = "https://api2.watttime.org/v3"
        self.token = None
        
    async def _login(self):
        """Login to WattTime and get token."""
        if not self.username or not self.password:
            logger.error("WattTime credentials not configured")
            return False
            
        try:
            async with aiohttp.ClientSession() as session:
                auth_data = {"username": self.username, "password": self.password}
                async with session.post(f"{self.base_url}/login", json=auth_data) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.token = data.get("token")
                        logger.info("WattTime login successful")
                        return True
                    else:
                        logger.error(f"WattTime login failed: {response.status}")
                        return False
        except Exception as e:
            logger.error(f"WattTime login error: {str(e)}")
            return False
    
    async def get_carbon_data(self, zone: str) -> Optional[CarbonData]:
        """Get marginal carbon intensity from WattTime."""
        if zone != "CAISO_NORTH":
            return None
            
        cache_key = f"WT:{zone}"
        
        # Try cache first
        cached = await self._get_from_cache(cache_key)
        if cached and cached.fresh_sec < 300:  # 5 minutes
            return cached
        
        # Login if needed
        if not self.token:
            if not await self._login():
                return None
        
        try:
            async with aiohttp.ClientSession() as session:
                headers = {"Authorization": f"Bearer {self.token}"}
                url = f"{self.base_url}/marginal?ba={zone}"
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        # Convert lbs/MWh to g/kWh: * 453.59 / 1000
                        gco2 = float(data.get("marginal_carbon_intensity", 0)) * 453.59 / 1000
                        
                        carbon_data = CarbonData(
                            gco2=gco2,
                            ts=datetime.now(timezone.utc).isoformat(),
                            type=CarbonType.MARGINAL,
                            source="WattTime",
                            fresh_sec=0
                        )
                        
                        await self._set_cache(cache_key, carbon_data)
                        return carbon_data
                    else:
                        logger.error(f"WattTime API error: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"WattTime fetch error: {str(e)}")
            return None

class ESOProvider(CarbonProvider):
    """National Grid ESO provider for Great Britain (GBR-13)"""
    
    def __init__(self, redis_client: redis.Redis):
        super().__init__(redis_client)
        self.base_url = "https://api.carbonintensity.org.uk"
    
    async def get_carbon_data(self, zone: str) -> Optional[CarbonData]:
        """Get carbon intensity from National Grid ESO."""
        if zone != "GBR-13":
            return None
            
        cache_key = f"ESO:{zone}"
        
        # Try cache first
        cached = await self._get_from_cache(cache_key)
        if cached and cached.fresh_sec < 300:  # 5 minutes
            return cached
        
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/regional/regionid/13"
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        intensity_data = data.get("data", [{}])[0]
                        
                        carbon_data = CarbonData(
                            gco2=float(intensity_data.get("intensity", {}).get("actual", 0)),
                            ts=intensity_data.get("from", datetime.now(timezone.utc).isoformat()),
                            type=CarbonType.AVERAGE,
                            source="ESO",
                            fresh_sec=0
                        )
                        
                        await self._set_cache(cache_key, carbon_data)
                        return carbon_data
                    else:
                        logger.error(f"ESO API error: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"ESO fetch error: {str(e)}")
            return None

class GridStatusProvider(CarbonProvider):
    """GridStatus provider for US East (NYISO, PJM) - requires Lambda wrapper"""
    
    def __init__(self, redis_client: redis.Redis):
        super().__init__(redis_client)
        self.lambda_url = os.getenv("GRIDSTATUS_LAMBDA_URL")
    
    async def get_carbon_data(self, zone: str) -> Optional[CarbonData]:
        """Get carbon intensity from GridStatus Lambda wrapper."""
        if zone not in ["NYISO", "PJM"]:
            return None
            
        if not self.lambda_url:
            logger.warning("GridStatus Lambda URL not configured")
            return None
            
        cache_key = f"GS:{zone}"
        
        # Try cache first
        cached = await self._get_from_cache(cache_key)
        if cached and cached.fresh_sec < 300:  # 5 minutes
            return cached
        
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.lambda_url}/intensity?iso={zone}"
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        carbon_data = CarbonData(
                            gco2=float(data.get("intensity", 0)),
                            ts=data.get("timestamp", datetime.now(timezone.utc).isoformat()),
                            type=CarbonType.AVERAGE,
                            source="GridStatus",
                            fresh_sec=0
                        )
                        
                        await self._set_cache(cache_key, carbon_data)
                        return carbon_data
                    else:
                        logger.error(f"GridStatus API error: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"GridStatus fetch error: {str(e)}")
            return None

class ENTSOEProvider(CarbonProvider):
    """ENTSO-E Transparency Platform provider for EU"""
    
    def __init__(self, redis_client: redis.Redis):
        super().__init__(redis_client)
        self.api_key = os.getenv("ENTSOE_API_KEY")
        self.base_url = "https://transparency.entsoe.eu/api"
    
    async def get_carbon_data(self, zone: str) -> Optional[CarbonData]:
        """Get carbon intensity from ENTSO-E."""
        if not zone.startswith("ENTSOE_"):
            return None
            
        if not self.api_key:
            logger.warning("ENTSO-E API key not configured")
            return None
            
        cache_key = f"ENTSOE:{zone}"
        
        # Try cache first
        cached = await self._get_from_cache(cache_key)
        if cached and cached.fresh_sec < 900:  # 15 minutes
            return cached
        
        try:
            # This is a simplified version - ENTSO-E requires complex XML parsing
            # For now, return a placeholder that indicates the need for implementation
            logger.info(f"ENTSO-E provider not fully implemented for {zone}")
            return None
        except Exception as e:
            logger.error(f"ENTSO-E fetch error: {str(e)}")
            return None

class ElectricityMapProvider(CarbonProvider):
    """Legacy ElectricityMap provider (fallback)"""
    
    def __init__(self, redis_client: redis.Redis):
        super().__init__(redis_client)
        self.api_key = os.getenv("ELECTRICITY_MAPS_API_KEY")
        self.base_url = "https://api.electricitymap.org/v3"
    
    async def get_carbon_data(self, zone: str) -> Optional[CarbonData]:
        """Get carbon intensity from ElectricityMap (legacy)."""
        if not self.api_key:
            return None
            
        cache_key = f"EM:{zone}"
        
        # Try cache first
        cached = await self._get_from_cache(cache_key)
        if cached and cached.fresh_sec < 3600:  # 1 hour
            return cached
        
        try:
            async with aiohttp.ClientSession() as session:
                headers = {"auth-token": self.api_key}
                url = f"{self.base_url}/carbon-intensity/latest?zone={zone}"
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        carbon_data = CarbonData(
                            gco2=float(data.get("carbonIntensity", 0)),
                            ts=datetime.now(timezone.utc).isoformat(),
                            type=CarbonType.AVERAGE,
                            source="EM-stale",
                            fresh_sec=0
                        )
                        
                        await self._set_cache(cache_key, carbon_data)
                        return carbon_data
                    else:
                        logger.error(f"ElectricityMap API error: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"ElectricityMap fetch error: {str(e)}")
            return None

class MultiProviderCarbonClient:
    """Multi-provider carbon intensity client with freshness penalties"""
    
    def __init__(self):
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
        
        # Initialize providers in priority order
        self.providers = [
            WattTimeProvider(self.redis),
            ESOProvider(self.redis),
            GridStatusProvider(self.redis),
            ENTSOEProvider(self.redis),
            ElectricityMapProvider(self.redis)
        ]
        
        logger.info("Initialized MultiProviderCarbonClient")
    
    def _apply_freshness_penalty(self, data: CarbonData) -> float:
        """Apply freshness penalty to carbon intensity."""
        # +1g for each extra minute stale beyond 10 minutes
        penalty = max(0, data.fresh_sec - 600) / 60
        return data.gco2 + penalty
    
    async def get_zone_intensity(self, zone: str) -> Dict:
        """Get carbon intensity for a zone with provider info."""
        pop_zone = POP_ZONE_MAPPING.get(zone, zone)
        
        # Try each provider in order
        for provider in self.providers:
            try:
                data = await provider.get_carbon_data(pop_zone)
                if data:
                    # Apply freshness penalty
                    adj_carbon = self._apply_freshness_penalty(data)
                    
                    return {
                        "zone": zone,
                        "carbon_intensity": adj_carbon,
                        "raw_carbon": data.gco2,
                        "source": data.source,
                        "type": data.type.value,
                        "fresh_sec": data.fresh_sec,
                        "timestamp": data.ts
                    }
            except Exception as e:
                logger.warning(f"Provider {provider.__class__.__name__} failed for {zone}: {str(e)}")
                continue
        
        # Fallback to static values
        fallback_intensity = FALLBACK_INTENSITIES.get(zone, 500.0)
        return {
            "zone": zone,
            "carbon_intensity": fallback_intensity,
            "raw_carbon": fallback_intensity,
            "source": "fallback",
            "type": "avg",
            "fresh_sec": 86400,  # 24 hours (very stale)
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    async def get_all_intensities(self) -> Dict[str, Dict]:
        """Get carbon intensities for all zones."""
        intensities = {}
        for zone in POP_ZONE_MAPPING.keys():
            try:
                intensities[zone] = await self.get_zone_intensity(zone)
            except Exception as e:
                logger.error(f"Failed to get intensity for {zone}: {str(e)}")
                intensities[zone] = {
                    "zone": zone,
                    "carbon_intensity": FALLBACK_INTENSITIES.get(zone, 500.0),
                    "raw_carbon": FALLBACK_INTENSITIES.get(zone, 500.0),
                    "source": "fallback",
                    "type": "avg",
                    "fresh_sec": 86400,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
        return intensities

# Initialize the client as None
multi_carbon_client = None

def get_multi_carbon_client():
    global multi_carbon_client
    if multi_carbon_client is None:
        multi_carbon_client = MultiProviderCarbonClient()
    return multi_carbon_client

# FastAPI app
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

app = FastAPI(title="Multi-Provider Carbon Intensity API")

@app.get("/carbon")
async def get_carbon(zone: str = Query(..., description="Zone name, e.g. 'sfo', 'lon', 'iad'")):
    client = get_multi_carbon_client()
    result = await client.get_zone_intensity(zone)
    return JSONResponse(content=result)

@app.get("/carbon/all")
async def get_all_carbon():
    client = get_multi_carbon_client()
    result = await client.get_all_intensities()
    return JSONResponse(content=result)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "providers": len(get_multi_carbon_client().providers)} 