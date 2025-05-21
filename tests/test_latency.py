import pytest
import os
from unittest.mock import patch, AsyncMock
from api.latency import LatencyProber

@pytest.fixture
def mock_env_vars():
    with patch.dict(os.environ, {
        "CDN_POP_US_EAST": "https://us-east.example.com",
        "CDN_POP_EU_WEST": "https://eu-west.example.com",
        "CDN_POP_AP_SOUTHEAST": "https://ap-southeast.example.com"
    }):
        yield

@pytest.mark.asyncio
async def test_probe_single_success(mock_env_vars):
    """Test successful single probe."""
    prober = LatencyProber()
    
    with patch("aiohttp.ClientSession.head") as mock_head:
        mock_head.return_value.__aenter__.return_value = AsyncMock(
            status=200
        )
        
        latency = await prober._probe_single("https://test.example.com")
        assert isinstance(latency, float)
        assert latency < float('inf')

@pytest.mark.asyncio
async def test_probe_single_failure(mock_env_vars):
    """Test failed single probe."""
    prober = LatencyProber()
    
    with patch("aiohttp.ClientSession.head") as mock_head:
        mock_head.side_effect = Exception("Connection failed")
        
        latency = await prober._probe_single("https://test.example.com")
        assert latency == float('inf')

@pytest.mark.asyncio
async def test_probe_pop(mock_env_vars):
    """Test probing a POP multiple times."""
    prober = LatencyProber()
    
    with patch("aiohttp.ClientSession.head") as mock_head:
        mock_head.return_value.__aenter__.return_value = AsyncMock(
            status=200
        )
        
        latency = await prober._probe_pop("us-east", "https://us-east.example.com")
        assert isinstance(latency, float)
        assert latency < float('inf')

@pytest.mark.asyncio
async def test_probe_all_pops(mock_env_vars):
    """Test probing all POPs."""
    prober = LatencyProber()
    
    with patch("aiohttp.ClientSession.head") as mock_head:
        mock_head.return_value.__aenter__.return_value = AsyncMock(
            status=200
        )
        
        latencies = await prober.probe_all_pops()
        assert set(latencies.keys()) == {"us-east", "eu-west", "ap-southeast"}
        assert all(isinstance(v, float) for v in latencies.values())

def test_get_acceptable_pops(mock_env_vars):
    """Test filtering POPs by latency threshold."""
    prober = LatencyProber()
    
    latencies = {
        "us-east": 75.0,
        "eu-west": 85.0,
        "ap-southeast": 55.0
    }
    
    acceptable = prober.get_acceptable_pops(latencies, max_latency=80.0)
    assert set(acceptable) == {"us-east", "ap-southeast"} 