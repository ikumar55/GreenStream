from fastapi import FastAPI
from fetcher import get_carbon_intensities

app = FastAPI()

@app.get("/carbon")
async def carbon():
    return await get_carbon_intensities() 