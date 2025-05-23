from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse
import os
from fastapi.middleware.cors import CORSMiddleware
import httpx
from dotenv import load_dotenv
from os import getenv

load_dotenv()

app = FastAPI()


app.add_middleware(
    CORSMiddleware,
    # allow_origins=["http://localhost:5173"],
    allow_origins=["*"],  # or "*" for testing
    allow_methods=["*"],
    allow_headers=["*"],
)

SONARR_URL = "http://localhost:8989"
SONARR_API_KEY = getenv("SONARR_API_KEY")
if not SONARR_API_KEY:
    raise RuntimeError("SONARR_API_KEY is not set in environment variables.")

headers = {
    "X-Api-Key": SONARR_API_KEY
}

async def fetch_sonarr_series():
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{SONARR_URL}/api/v3/series", headers=headers)
        response.raise_for_status()
        return response.json()

WHITELISTED_IPS = ["127.0.0.1", "192.168.0.48", "172.17.46.123"]

@app.middleware("http")
async def ip_whitelist(request: Request, call_next):
    client_ip = request.client.host
    if client_ip not in WHITELISTED_IPS:
        raise HTTPException(status_code=403, detail="Forbidden")
    response = await call_next(request)
    return response

@app.get("/shows")
async def list_shows():
    return await fetch_sonarr_series()

@app.get("/shows/{show_id}/episodes")
async def list_episodes(show_id: int):
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{SONARR_URL}/api/v3/episode?seriesId={show_id}", headers=headers)
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail="Show not found or no episodes available")
        response.raise_for_status()
        episodes = response.json()
        episodes_with_files = [ep for ep in episodes if ep.get("hasFile")]
        return episodes_with_files

@app.get("/episodes/{episode_id}")
async def get_episode(episode_id: int):
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{SONARR_URL}/api/episodefile/{episode_id}", headers=headers)
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail="Episode not found")
        response.raise_for_status()
        episode_file = response.json()
        file_path = episode_file.get("path")
        if not file_path or not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="File not found")
        return FileResponse(file_path, media_type="video/mp4")
