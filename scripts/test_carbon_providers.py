#!/usr/bin/env python3
"""
Test script for the multi-provider carbon system.
Tests each provider and verifies data quality.
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone

# Add the api directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'api'))

from carbon_v2 import MultiProviderCarbonClient, POP_ZONE_MAPPING

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_provider(client, zone, expected_source=None):
    """Test a specific zone and provider."""
    try:
        result = await client.get_zone_intensity(zone)
        
        print(f"\n=== Testing Zone: {zone} ===")
        print(f"Carbon Intensity: {result['carbon_intensity']:.1f} gCO₂/kWh")
        print(f"Raw Carbon: {result['raw_carbon']:.1f} gCO₂/kWh")
        print(f"Source: {result['source']}")
        print(f"Type: {result['type']}")
        print(f"Freshness: {result['fresh_sec']} seconds")
        print(f"Timestamp: {result['timestamp']}")
        
        # Validate the result
        if result['carbon_intensity'] <= 0:
            print("❌ ERROR: Carbon intensity is zero or negative")
            return False
        
        if result['carbon_intensity'] > 1000:
            print("⚠️  WARNING: Carbon intensity seems high (>1000 gCO₂/kWh)")
        
        if result['fresh_sec'] > 3600:
            print("⚠️  WARNING: Data is stale (>1 hour)")
        
        if expected_source and result['source'] != expected_source:
            print(f"⚠️  WARNING: Expected source {expected_source}, got {result['source']}")
        
        print("✅ Test passed")
        return True
        
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        return False

async def test_all_providers():
    """Test all providers and zones."""
    print("🧪 Testing Multi-Provider Carbon System")
    print("=" * 50)
    
    # Initialize the client
    client = MultiProviderCarbonClient()
    
    # Test specific zones for each provider
    test_cases = [
        # WattTime zones
        ("sfo", "WattTime"),
        ("lax", "WattTime"),
        
        # ESO zones
        ("lon", "ESO"),
        
        # GridStatus zones (will fallback if Lambda not deployed)
        ("iad", "GridStatus"),
        ("nyc", "GridStatus"),
        
        # Legacy zones
        ("us-east", "EM-stale"),
        ("eu-west", "fallback"),
    ]
    
    passed = 0
    total = len(test_cases)
    
    for zone, expected_source in test_cases:
        if await test_provider(client, zone, expected_source):
            passed += 1
    
    print(f"\n📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed!")
    else:
        print("⚠️  Some tests failed. Check the logs above.")
    
    return passed == total

async def test_freshness_penalty():
    """Test the freshness penalty logic."""
    print("\n🧪 Testing Freshness Penalty Logic")
    print("=" * 50)
    
    client = MultiProviderCarbonClient()
    
    # Test with fresh data (should have no penalty)
    result = await client.get_zone_intensity("sfo")
    fresh_penalty = result['carbon_intensity'] - result['raw_carbon']
    
    print(f"Fresh data penalty: {fresh_penalty:.2f} gCO₂/kWh")
    
    if fresh_penalty <= 0:
        print("✅ Freshness penalty working correctly")
    else:
        print("⚠️  Unexpected penalty on fresh data")

async def main():
    """Main test function."""
    try:
        # Test all providers
        success = await test_all_providers()
        
        # Test freshness penalty
        await test_freshness_penalty()
        
        if success:
            print("\n🎉 All tests completed successfully!")
            return 0
        else:
            print("\n❌ Some tests failed!")
            return 1
            
    except Exception as e:
        logger.error(f"Test failed: {str(e)}")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code) 