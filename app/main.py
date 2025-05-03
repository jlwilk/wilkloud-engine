from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse
import os

app = FastAPI()

# Example config (you could later move this to config.py)
MEDIA_FILE = os.getenv("MEDIA_FILE", "/path/to/your/media.mp4")
WHITELISTED_IPS = os.getenv("WHITELISTED_IPS", "127.0.0.1,192.168.1.10").split(",")

@app.middleware("http")
async def ip_whitelist(request: Request, call_next):
    client_ip = request.client.host
    if client_ip not in WHITELISTED_IPS:
        raise HTTPException(status_code=403, detail="Forbidden")
    response = await call_next(request)
    return response

@app.get("/media")
async def get_media():
    return FileResponse(MEDIA_FILE, media_type="video/mp4")
