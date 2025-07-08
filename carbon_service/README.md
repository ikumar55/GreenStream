# Carbon Data Fetcher Microservice

This service provides real-time carbon intensity data for CDN POPs, with fallback and caching.

## Features
- Fetches live carbon data from ElectricityMap API (primary) and WattTime (fallback)
- Caches results in Redis for 30–60s
- Fallbacks to 1h average or continent defaults if all APIs fail
- Exposes a REST API for use by edge Workers or other services

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Start Redis (if not already running):
   ```bash
   redis-server
   ```
3. Run the FastAPI app:
   ```bash
   uvicorn main:app --reload
   ```

## API
- `GET /carbon` — Returns latest carbon intensities for all POPs

## TODO
- Implement real API calls and fallback logic in `fetcher.py`
- Add error handling and logging 