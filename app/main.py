from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse
import os
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()


app.add_middleware(
    CORSMiddleware,
    # allow_origins=["http://localhost:5173"],
    allow_origins=["*"],  # or "*" for testing
    allow_methods=["*"],
    allow_headers=["*"],
)

MEDIA_ROOT = "media/movies"
WHITELISTED_IPS = ["127.0.0.1", "192.168.0.48", "172.17.46.123"]

# Build a movie list on startup
MOVIES = {}

@app.on_event("startup")
async def scan_movies():
    global MOVIES
    MOVIES = {}
    movie_id = 1
    for folder in os.listdir(MEDIA_ROOT):
        folder_path = os.path.join(MEDIA_ROOT, folder)
        if os.path.isdir(folder_path):
            for file in os.listdir(folder_path):
                if file.endswith((".mp4", ".mkv", ".avi")):
                    MOVIES[movie_id] = {
                        "id": movie_id,
                        "title": folder,
                        "file_path": os.path.join(folder_path, file)
                    }
                    movie_id += 1

@app.middleware("http")
async def ip_whitelist(request: Request, call_next):
    client_ip = request.client.host
    if client_ip not in WHITELISTED_IPS:
        raise HTTPException(status_code=403, detail="Forbidden")
    response = await call_next(request)
    return response

@app.get("/movies")
async def list_movies():
    return list(MOVIES.values())

@app.get("/media/{movie_id}")
async def get_media(movie_id: int):
    movie = MOVIES.get(movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")
    return FileResponse(movie["file_path"], media_type="video/mp4")
