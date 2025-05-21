import logging
from typing import Dict, List
import os
import aiohttp
import asyncio
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class LatencyProber:
    def __init__(self):
        # Load CDN POP URLs from environment
        self.cdn_pops = {
            "us-east": os.getenv("CDN_POP_US_EAST"),
            "eu-west": os.getenv("CDN_POP_EU_WEST"),
            "ap-southeast": os.getenv("CDN_POP_AP_SOUTHEAST")
        }
        
        # Validate configuration
        missing_pops = [pop for pop, url in self.cdn_pops.items() if not url]
        if missing_pops:
            raise ValueError(f"Missing CDN POP URLs for: {', '.join(missing_pops)}")
            
        self.latency_slo_ms = float(os.getenv("LATENCY_SLO_MS", "80.0"))
        self.probe_timeout = float(os.getenv("PROBE_TIMEOUT_MS", "1000.0"))
        self.max_retries = int(os.getenv("PROBE_MAX_RETRIES", "3"))
        
        logger.info("Initialized LatencyProber with real CDN endpoints")

    async def _probe_pop(self, pop: str, url: str) -> float:
        """Probe a single CDN POP with retries."""
        for attempt in range(self.max_retries):
            try:
                start_time = datetime.now(timezone.utc)
                
                async with aiohttp.ClientSession() as session:
                    async with session.head(
                        url,
                        timeout=self.probe_timeout / 1000.0,  # Convert to seconds
                        allow_redirects=True
                    ) as response:
                        if response.status == 200:
                            end_time = datetime.now(timezone.utc)
                            latency = (end_time - start_time).total_seconds() * 1000.0  # Convert to ms
                            return latency
                        else:
                            logger.warning(f"Probe failed for {pop}: HTTP {response.status}")
                            
            except asyncio.TimeoutError:
                logger.warning(f"Probe timeout for {pop} (attempt {attempt + 1}/{self.max_retries})")
            except Exception as e:
                logger.warning(f"Probe error for {pop}: {str(e)} (attempt {attempt + 1}/{self.max_retries})")
                
            if attempt < self.max_retries - 1:
                await asyncio.sleep(0.1 * (attempt + 1))  # Exponential backoff
                
        logger.error(f"All probe attempts failed for {pop}")
        return -1.0  # Use -1.0 as fallback value for failed probes

    async def probe_all_pops(self) -> Dict[str, float]:
        """Probe all CDN POPs concurrently."""
        tasks = []
        for pop, url in self.cdn_pops.items():
            tasks.append(self._probe_pop(pop, url))
            
        latencies = await asyncio.gather(*tasks)
        return dict(zip(self.cdn_pops.keys(), latencies))

    async def get_acceptable_pops(self) -> List[str]:
        """Get list of POPs that meet the latency SLO."""
        latencies = await self.probe_all_pops()
        return [
            pop for pop, latency in latencies.items()
            if latency <= self.latency_slo_ms
        ]

# Initialize the prober
latency_prober = LatencyProber() 