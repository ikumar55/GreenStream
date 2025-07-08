from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
import httpx
import logging
from typing import Dict, Optional
import os
from datetime import datetime, timezone

from .routing import router
from .carbon import get_carbon_client  # Import the getter function instead


# Ensure the logs directory exists
os.makedirs('logs', exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/server.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = FastAPI(title="GreenStream CDN Router")

# CDN POPs configuration (real or mock)
CDN_POPS = {
    "us-east": "http://localhost:8001",
    "eu-west": "http://localhost:8002",
    "ap-southeast": "http://localhost:8003"
}

# Initialize HTTP client
http_client = httpx.AsyncClient()

@app.get("/")
async def root():
    return {
        "status": "ok",
        "service": "GreenStream CDN Router",
        "version": "1.0.0"
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/video/{video_id}")
async def route_video(
    video_id: str,
    policy: str = Query("weighted", enum=["weighted", "latency", "carbon"]),
    log_suffix: str = Query(None)
):
    """
    Route a video request using the specified policy and log_suffix.
    """
    try:
        decision = await router.route_video(video_id, policy=policy, log_suffix=log_suffix)
        return {
            "video_id": video_id,
            "selected_pop": decision["selected_pop"],
            "baseline_pop": decision["baseline_pop"],
            "carbon_intensities": decision["carbon_intensities"],
            "latencies": decision["latencies"],
            "metadata": decision["metadata"],
            "policy_used": decision["policy_used"],
            "timestamp": decision["timestamp"]
        }
    except Exception as e:
        logger.error(f"Error routing video {video_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to route video request")

@app.on_event("shutdown")
async def shutdown_event():
    await http_client.aclose()
