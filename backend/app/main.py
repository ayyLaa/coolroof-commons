from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import router as api_router
from app.core.config import CORS_ORIGINS, PHOTO_DIR, PHOTO_URL_PREFIX
from app.core.exceptions import register_exception_handlers

app = FastAPI(title="CoolRoof Commons API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)
app.include_router(api_router)

# Coverage overlays are written next to the uploaded photos; the frontend loads them
# through mask_preview_url, which points here.
PHOTO_DIR.mkdir(parents=True, exist_ok=True)
app.mount(PHOTO_URL_PREFIX, StaticFiles(directory=PHOTO_DIR), name="photos")
