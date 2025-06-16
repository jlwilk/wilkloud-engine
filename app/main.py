from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse
import os
from fastapi.middleware.cors import CORSMiddleware
import httpx
from dotenv import load_dotenv
from os import getenv
from starlette.responses import StreamingResponse
import aiofiles
import json
from redis.asyncio import Redis
from datetime import timedelta

load_dotenv()

app = FastAPI(
    title="Wilkloud Media Server API",
    description="API to interface with Sonarr for listing shows, episodes, and streaming media files.",
    version="1.0.0"
)

# Redis configuration
REDIS_URL = getenv("REDIS_URL", "redis://localhost:6379")
redis = Redis.from_url(REDIS_URL, decode_responses=True)

# Cache configuration
CACHE_TTL = timedelta(minutes=30)  # Cache for 30 minutes
CACHE_KEY = "sonarr_series"
EPISODE_CACHE_KEY = "sonarr_episodes_{}"  # Format with series_id
EPISODE_FILE_CACHE_KEY = "sonarr_episode_files_{}"  # Format with series_id

app.add_middleware(
    CORSMiddleware,
    # allow_origins=["http://localhost:5173"],
    allow_origins=["*"],  # or "*" for testing
    allow_methods=["*"],
    allow_headers=["*"],
)

SONARR_URL = getenv("SONARR_URL", "http://localhost:8989")
SONARR_API_KEY = getenv("SONARR_API_KEY")
if not SONARR_API_KEY:
    raise RuntimeError("SONARR_API_KEY is not set in environment variables.")

headers = {
    "X-Api-Key": SONARR_API_KEY
}

async def fetch_sonarr_series():
    # Try to get from cache first
    cached_data = await redis.get(CACHE_KEY)
    if cached_data:
        print("Cache hit for shows")
        return json.loads(cached_data)

    # If not in cache, fetch from Sonarr
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{SONARR_URL}/api/v3/series", headers=headers)
        response.raise_for_status()
        data = response.json()
        
        # Cache the response
        await redis.setex(
            CACHE_KEY,
            CACHE_TTL,
            json.dumps(data)
        )
        
        return data

async def fetch_show_details(series_id: int):
    # Try to get from cache first
    cached_data = await redis.get(f"sonarr_show_{series_id}")
    if cached_data:
        print("Cache hit for individual show")
        return json.loads(cached_data)

    # If not in cache, fetch from Sonarr
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{SONARR_URL}/api/v3/series/{series_id}", headers=headers)
        response.raise_for_status()
        data = response.json()
        
        # Cache the response
        await redis.setex(
            f"sonarr_show_{series_id}",
            CACHE_TTL,
            json.dumps(data)
        )
        
        return data

WHITELISTED_IPS = ["127.0.0.1", "192.168.0.48", "172.17.46.123"]

@app.middleware("http")
async def ip_whitelist(request: Request, call_next):
    client_ip = request.client.host
    if client_ip not in WHITELISTED_IPS:
        raise HTTPException(status_code=403, detail="Forbidden")
    response = await call_next(request)
    return response

@app.get("/shows", summary="List all shows", description="Fetches all shows from the configured Sonarr instance with pagination support.")
async def list_shows(page: int = 1, page_size: int = 20):
    all_shows = await fetch_sonarr_series()

    total = len(all_shows)
    start = (page - 1) * page_size
    end = start + page_size
    paginated_shows = all_shows[start:end]

    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": (total + page_size - 1) // page_size,
        "results": paginated_shows
    }

@app.get("/show/{series_id}", summary="Get show details", description="Fetches detailed information for a specific show.")
async def get_show_details(series_id: int):
    try:
        return await fetch_show_details(series_id)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail="Show not found")
        raise HTTPException(status_code=500, detail="Error fetching show details")

@app.get("/show/{series_id}/episodes", summary="Get all episodes for a series", description="Fetches all episodes for a given series ID.")
async def get_combined_episode_data(series_id: int):
    async with httpx.AsyncClient() as client:
        ep_response = await client.get(f"{SONARR_URL}/api/v3/episode?seriesId={series_id}", headers=headers)
        file_response = await client.get(f"{SONARR_URL}/api/v3/episodeFile?seriesId={series_id}", headers=headers)

        if ep_response.status_code == 404 or file_response.status_code == 404:
            raise HTTPException(status_code=404, detail="Episode or file data not found")
        ep_response.raise_for_status()
        file_response.raise_for_status()

        episodes = ep_response.json()
        episode_files = {f["id"]: f for f in file_response.json()}

    combined = []
    for ep in episodes:
        has_file = ep.get("hasFile", False)
        
        if not has_file:
            continue
            
        file_data = episode_files.get(ep.get("episodeFileId"))
        if not file_data:
            print(f"  No file data found for episodeFileId: {ep.get('episodeFileId')}")
            continue

        episode_data = {
            "season": ep.get("seasonNumber", 0),
            "episode": ep.get("episodeNumber", 0),
            "title": ep.get("title", "Unknown"),
            "airDate": ep.get("airDate", None),
            "overview": ep.get("overview", ""),
            "filePath": file_data.get("path"),
            "relativePath": file_data.get("relativePath"),
            "size": file_data.get("size"),
            "quality": file_data.get("quality", {}).get("quality", {}).get("name"),
            "videoCodec": file_data.get("mediaInfo", {}).get("videoCodec"),
            "audioCodec": file_data.get("mediaInfo", {}).get("audioCodec"),
            "audioChannels": file_data.get("mediaInfo", {}).get("audioChannels"),
            "resolution": file_data.get("mediaInfo", {}).get("resolution"),
            "runtime": file_data.get("mediaInfo", {}).get("runTime"),
            "subtitles": file_data.get("mediaInfo", {}).get("subtitles"),
        }

        combined.append(episode_data)

    return sorted(combined, key=lambda x: (x["season"], x["episode"]))

@app.get("/stream/{series_id}/{season}/{episode}", summary="Stream media file", description="Streams a media file using HTTP byte-range support.")
async def stream_file(series_id: int, season: int, episode: int, request: Request):

    # Get the episode details
    episode_details = await get_combined_episode_data(series_id)
    episode_details = [ep for ep in episode_details if ep["season"] == season and ep["episode"] == episode]
    if not episode_details:
        raise HTTPException(status_code=404, detail="Episode not found")
    file_path = episode_details[0]["filePath"]

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    file_size = os.path.getsize(file_path)
    range_header = request.headers.get("range")

    def parse_range(range_header: str):
        units, _, range_spec = range_header.partition("=")
        start_str, _, end_str = range_spec.partition("-")
        start = int(start_str)
        end = int(end_str) if end_str else file_size - 1
        return start, end

    if range_header:
        start, end = parse_range(range_header)
        length = end - start + 1

        async def content():
            async with aiofiles.open(file_path, 'rb') as f:
                await f.seek(start)
                yield await f.read(length)

        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(length),
            "Content-Type": "video/mp4"
        }

        return StreamingResponse(content(), status_code=206, headers=headers)

    else:
        async def content():
            async with aiofiles.open(file_path, 'rb') as f:
                yield await f.read()

        headers = {
            "Content-Length": str(file_size),
            "Content-Type": "video/mp4"
        }

        return StreamingResponse(content(), headers=headers)

@app.get("/cache/clear", summary="Clear all cache", description="Clears all cached data from Redis.")
async def clear_cache():
    try:
        await redis.flushall()
        return {"message": "Cache cleared successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error clearing cache: {str(e)}")

@app.get("/health", summary="Health check for Redis and Sonarr", description="Checks if Redis and Sonarr are running and reachable.")
async def health_check():
    redis_status = "unknown"
    sonarr_status = "unknown"
    try:
        pong = await redis.ping()
        redis_status = "ok" if pong else "unreachable"
    except Exception as e:
        redis_status = f"error: {str(e)}"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{SONARR_URL}/api/v3/system/status", headers=headers, timeout=5)
            if response.status_code == 200:
                sonarr_status = "ok"
            else:
                sonarr_status = f"error: status {response.status_code}"
    except Exception as e:
        sonarr_status = f"error: {str(e)}"
    return {"redis": redis_status, "sonarr": sonarr_status}

@app.on_event("startup")
async def check_services_on_startup():
    redis_status = "unknown"
    sonarr_status = "unknown"
    try:
        pong = await redis.ping()
        redis_status = "ok" if pong else "unreachable"
    except Exception as e:
        redis_status = f"error: {str(e)}"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{SONARR_URL}/api/v3/system/status", headers=headers, timeout=5)
            if response.status_code == 200:
                sonarr_status = "ok"
            else:
                sonarr_status = f"error: status {response.status_code}"
    except Exception as e:
        sonarr_status = f"error: {str(e)}"
    print(f"[Startup Health Check] Redis: {redis_status}, Sonarr: {sonarr_status}")