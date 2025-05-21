from fastapi import FastAPI
import uvicorn
import asyncio
import random
from datetime import datetime, timezone

app = FastAPI()

@app.get("/")
async def root():
    return {
        "status": "ok",
        "pop": "mock-cdn",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.head("/")
async def head():
    # Simulate some network latency
    await asyncio.sleep(random.uniform(0.05, 0.15))
    return {"status": "ok"}

@app.get("/video/{video_id}")
async def get_video(video_id: str):
    # Simulate network latency (50-150ms)
    await asyncio.sleep(random.uniform(0.05, 0.15))
    
    return {
        "status": "ok",
        "video_id": video_id,
        "content": f"dummy_content_{video_id}",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8001
    uvicorn.run(app, host="0.0.0.0", port=port) 