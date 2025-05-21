import pytest
import os
import json
from unittest.mock import patch, AsyncMock
from datetime import datetime
from api.routing import Router

@pytest.fixture
def mock_env_vars():
    with patch.dict(os.environ, {
        "LATENCY_SLO_MS": "80.0"
    }):
        yield

@pytest.fixture
def mock_carbon_client():
    with patch("api.routing.carbon_client") as mock:
        mock.get_all_zone_intensities.return_value = AsyncMock(
            return_value={
                "us-east": 450.0,
                "eu-west": 120.0,
                "ap-southeast": 300.0
            }
        )
        yield mock

@pytest.fixture
def mock_latency_prober():
    with patch("api.routing.latency_prober") as mock:
        mock.probe_all_pops.return_value = AsyncMock(
            return_value={
                "us-east": 75.0,
                "eu-west": 55.0,
                "ap-southeast": 85.0
            }
        )
        mock.get_acceptable_pops.return_value = ["us-east", "eu-west"]
        yield mock

@pytest.mark.asyncio
async def test_select_pop_normal_case(mock_env_vars, mock_carbon_client, mock_latency_prober):
    """Test normal case where some POPs meet latency SLO."""
    router = Router()
    selected_pop, metadata = await router.select_pop("test_video")
    
    assert selected_pop == "eu-west"  # Lowest carbon among acceptable POPs
    assert metadata["video_id"] == "test_video"
    assert set(metadata["acceptable_pops"]) == {"us-east", "eu-west"}

@pytest.mark.asyncio
async def test_select_pop_no_acceptable_pops(mock_env_vars, mock_carbon_client, mock_latency_prober):
    """Test case where no POPs meet latency SLO."""
    mock_latency_prober.get_acceptable_pops.return_value = []
    
    router = Router()
    selected_pop, metadata = await router.select_pop("test_video")
    
    assert selected_pop == "eu-west"  # Lowest carbon overall
    assert metadata["acceptable_pops"] == []

@pytest.mark.asyncio
async def test_select_pop_logging(mock_env_vars, mock_carbon_client, mock_latency_prober, tmp_path):
    """Test that routing decisions are logged correctly."""
    router = Router()
    router.log_dir = str(tmp_path)
    
    selected_pop, metadata = await router.select_pop("test_video")
    
    # Check that log file was created
    log_files = list(tmp_path.glob("routing_*.jsonl"))
    assert len(log_files) == 1
    
    # Check log content
    with open(log_files[0]) as f:
        log_entry = json.loads(f.readline())
        assert log_entry["video_id"] == "test_video"
        assert log_entry["selected_pop"] == selected_pop
        assert "carbon_intensities" in log_entry
        assert "latencies" in log_entry
        assert "acceptable_pops" in log_entry 