import os

MEDIA_FILE = os.getenv("MEDIA_FILE", "/path/to/your/media.mp4")
WHITELISTED_IPS = os.getenv("WHITELISTED_IPS", "127.0.0.1,192.168.1.10").split(",")