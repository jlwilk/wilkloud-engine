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
    # Try to get from cache first
    cached_data = await redis.get(CACHE_KEY)
    if cached_data:
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

@app.get("/shows/{series_id}/episodes", summary="Get all episodes for a series", description="Fetches all episodes for a given series ID.")
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
            if not ep.get("hasFile"):
                continue
            file_data = episode_files.get(ep["episodeFileId"])
            if not file_data:
                continue

            combined.append({
                "season": ep["seasonNumber"],
                "episode": ep["episodeNumber"],
                "title": ep["title"],
                "airDate": ep["airDate"],
                "overview": ep["overview"],
                "filePath": file_data["path"],
                "relativePath": file_data["relativePath"],
                "size": file_data["size"],
                "quality": file_data["quality"]["quality"]["name"],
                "videoCodec": file_data["mediaInfo"]["videoCodec"],
                "audioCodec": file_data["mediaInfo"]["audioCodec"],
                "audioChannels": file_data["mediaInfo"]["audioChannels"],
                "resolution": file_data["mediaInfo"]["resolution"],
                "runtime": file_data["mediaInfo"]["runTime"],
                "subtitles": file_data["mediaInfo"]["subtitles"],
            })

        return sorted(combined, key=lambda x: (x["season"], x["episode"]))

@app.get("/stream/{series_id}/{season}/{file_name}", summary="Stream media file", description="Streams a media file using HTTP byte-range support.")
async def stream_file(series_id: int, season: str, file_name: str, request: Request):
    media_root = "/Users/jason/Media/tv"
    file_path = os.path.join(media_root, str(series_id), season, file_name)

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