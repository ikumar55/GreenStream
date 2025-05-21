import pytest
import os
from unittest.mock import patch, AsyncMock
import json
from api.carbon import CarbonIntensityClient

@pytest.fixture
def mock_env_vars():
    with patch.dict(os.environ, {
        "ELECTRICITY_MAPS_API_KEY": "test_key",
        "REDIS_HOST": "localhost",
        "REDIS_PORT": "6379"
    }):
        yield

@pytest.fixture
def mock_redis():
    with patch("redis.Redis") as mock:
        mock_instance = mock.return_value
        mock_instance.get.return_value = None
        mock_instance.setex = AsyncMock()
        yield mock_instance

@pytest.mark.asyncio
async def test_get_carbon_intensity_api_success(mock_env_vars, mock_redis):
    """Test successful API call for carbon intensity."""
    mock_response = {"carbonIntensity": 120.5}
    
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = AsyncMock(
            status_code=200,
            json=lambda: mock_response
        )
        
        client = CarbonIntensityClient()
        result = await client.get_carbon_intensity("FR")
        
        assert result == 120.5
        mock_redis.setex.assert_called_once()

@pytest.mark.asyncio
async def test_get_carbon_intensity_cache_hit(mock_env_vars, mock_redis):
    """Test cache hit for carbon intensity."""
    mock_redis.get.return_value = b"150.0"
    
    client = CarbonIntensityClient()
    result = await client.get_carbon_intensity("FR")
    
    assert result == 150.0
    mock_redis.setex.assert_not_called()

@pytest.mark.asyncio
async def test_get_carbon_intensity_api_failure(mock_env_vars, mock_redis):
    """Test API failure fallback for carbon intensity."""
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.side_effect = Exception("API Error")
        
        client = CarbonIntensityClient()
        result = await client.get_carbon_intensity("FR")
        
        assert result == 500.0  # Fallback value
        mock_redis.setex.assert_not_called()

@pytest.mark.asyncio
async def test_get_all_zone_intensities(mock_env_vars, mock_redis):
    """Test getting carbon intensities for all zones."""
    mock_response = {"carbonIntensity": 100.0}
    
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = AsyncMock(
            status_code=200,
            json=lambda: mock_response
        )
        
        client = CarbonIntensityClient()
        results = await client.get_all_zone_intensities()
        
        assert set(results.keys()) == {"us-east", "eu-west", "ap-southeast"}
        assert all(isinstance(v, float) for v in results.values()) 