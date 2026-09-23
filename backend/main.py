from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from backend.api.routes import admin, players, reference, scouting
from gfs_core.config import get_settings
from gfs_core.db import get_engine

app = FastAPI(
    title="Global Football Scout API",
    version="0.1.0",
    description=(
        "Statistical player similarity and scouting analytics. Rankings come from data and models; "
        "an LLM is used only to translate natural-language requests into filters."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(players.router)
app.include_router(scouting.router)
app.include_router(reference.router)
app.include_router(admin.router)


@app.get("/health", tags=["ops"])
def health() -> dict:
    with get_engine().connect() as conn:
        conn.execute(text("select 1"))
    return {"status": "ok"}


@app.get("/features", tags=["ops"])
def features() -> dict:
    """Optional features this deployment has switched on, so the UI can hide the rest."""
    return {"natural_language": bool(get_settings().anthropic_api_key)}
