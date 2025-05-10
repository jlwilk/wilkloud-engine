from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse
import os
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any

app = FastAPI(
    title="Wilkloud Media Server",
    description="API for streaming movies and TV shows from a network share",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)


app.add_middleware(
    CORSMiddleware,
    # allow_origins=["http://localhost:5173"],
    allow_origins=["*"],  # or "*" for testing
    allow_methods=["*"],
    allow_headers=["*"],
)

MEDIA_ROOT = "//Larry/d/"
MEDIA_FOLDERS = ["Movies", "TV and Video"]
WHITELISTED_IPS = ["127.0.0.1", "192.168.0.48", "172.17.46.123"]

# Build media lists on startup
MOVIES = {}
TV_SHOWS = {}

@app.on_event("startup")
async def scan_media():
    global MOVIES, TV_SHOWS
    MOVIES = {}
    TV_SHOWS = {}
    movie_id = 1
    tv_id = 1
    for media_folder in MEDIA_FOLDERS:
        folder_path = os.path.join(MEDIA_ROOT, media_folder)
        if os.path.isdir(folder_path):
            for folder in os.listdir(folder_path):
                subfolder_path = os.path.join(folder_path, folder)
                if os.path.isdir(subfolder_path):
                    if media_folder == "Movies":
                        # Handle movies directly
                        for file in os.listdir(subfolder_path):
                            if file.endswith((".mp4", ".mkv", ".avi")):
                                MOVIES[movie_id] = {
                                    "id": movie_id,
                                    "title": folder,
                                    "file_path": os.path.join(subfolder_path, file)
                                }
                                movie_id += 1
                    else:
                        # Handle TV shows with season folders
                        for season_folder in os.listdir(subfolder_path):
                            season_path = os.path.join(subfolder_path, season_folder)
                            if os.path.isdir(season_path) and season_folder.startswith("Season"):
                                for file in os.listdir(season_path):
                                    if file.endswith((".mp4", ".mkv", ".avi")):
                                        TV_SHOWS[tv_id] = {
                                            "id": tv_id,
                                            "title": folder,
                                            "season": season_folder,
                                            "file_path": os.path.join(season_path, file)
                                        }
                                        tv_id += 1

@app.middleware("http")
async def ip_whitelist(request: Request, call_next):
    client_ip = request.client.host
    if client_ip not in WHITELISTED_IPS:
        raise HTTPException(status_code=403, detail="Forbidden")
    response = await call_next(request)
    return response

@app.get("/movies", 
    response_model=List[Dict[str, Any]],
    summary="List all movies",
    description="Returns a list of all available movies with their details including ID, title, and file path.",
    tags=["Movies"])
async def list_movies():
    return list(MOVIES.values())

@app.get("/tv-shows",
    response_model=List[Dict[str, Any]],
    summary="List all TV shows",
    description="Returns a list of all available TV shows with their details including ID, title, season, and file path.",
    tags=["TV Shows"])
async def list_tv_shows():
    return list(TV_SHOWS.values())

@app.get("/media/movie/{movie_id}",
    summary="Stream a movie",
    description="Streams a specific movie by its ID. Returns the video file for playback.",
    responses={
        200: {
            "description": "Video file stream",
            "content": {
                "video/mp4": {
                    "example": "Binary video data"
                }
            }
        },
        404: {
            "description": "Movie not found",
            "content": {
                "application/json": {
                    "example": {"detail": "Movie not found"}
                }
            }
        }
    },
    tags=["Movies"])
async def get_movie(movie_id: int):
    movie = MOVIES.get(movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")
    return FileResponse(movie["file_path"], media_type="video/mp4")

@app.get("/media/tv/{show_id}",
    summary="Stream a TV show episode",
    description="Streams a specific TV show episode by its ID. Returns the video file for playback.",
    responses={
        200: {
            "description": "Video file stream",
            "content": {
                "video/mp4": {
                    "example": "Binary video data"
                }
            }
        },
        404: {
            "description": "TV show not found",
            "content": {
                "application/json": {
                    "example": {"detail": "TV Show not found"}
                }
            }
        }
    },
    tags=["TV Shows"])
async def get_tv_show(show_id: int):
    show = TV_SHOWS.get(show_id)
    if not show:
        raise HTTPException(status_code=404, detail="TV Show not found")
    return FileResponse(show["file_path"], media_type="video/mp4")
