#!/usr/bin/env python3
"""
Carbon data refresh cron job.
Runs every 5 minutes to fetch fresh carbon intensity data from all providers.
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
import redis.asyncio as redis

# Add the api directory to the path so we can import the carbon providers
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'api'))

from carbon_v2 import (
    MultiProviderCarbonClient, 
    POP_ZONE_MAPPING,
    CarbonData,
    CarbonType
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/carbon_cron.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

async def refresh_carbon_data():
    """Refresh carbon data from all providers."""
    try:
        client = MultiProviderCarbonClient()
        
        # Get all zones that have provider mappings
        zones = list(POP_ZONE_MAPPING.keys())
        
        logger.info(f"Starting carbon data refresh for {len(zones)} zones")
        
        # Refresh data for each zone
        for zone in zones:
            try:
                result = await client.get_zone_intensity(zone)
                
                # Log the result
                logger.info(f"Zone {zone}: {result['carbon_intensity']:.1f} gCO₂/kWh "
                           f"from {result['source']} (fresh: {result['fresh_sec']}s)")
                
                # Store in Redis with timestamp for monitoring
                redis_key = f"carbon_refresh:{zone}:{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}"
                await client.redis.setex(redis_key, 3600, str(result['carbon_intensity']))
                
            except Exception as e:
                logger.error(f"Failed to refresh carbon data for zone {zone}: {str(e)}")
        
        logger.info("Carbon data refresh completed")
        
    except Exception as e:
        logger.error(f"Carbon data refresh failed: {str(e)}")
        raise

async def main():
    """Main function to run the carbon refresh."""
    # Ensure logs directory exists
    os.makedirs('logs', exist_ok=True)
    
    logger.info("Starting carbon data refresh cron job")
    
    try:
        await refresh_carbon_data()
        logger.info("Carbon data refresh completed successfully")
    except Exception as e:
        logger.error(f"Carbon data refresh failed: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main()) 