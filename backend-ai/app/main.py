import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings, resolve_rules_ai_mode
from app.routes.rules_nl import router as rules_nl_router
from app.services.rules_config_store import ensure_rules_config_dir

app = FastAPI(title="Rallyday AI", version="0.2.0")

settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", settings.cors_origins).split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ensure_rules_config_dir(settings.rules_config_dir)

app.include_router(rules_nl_router)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "backend-ai",
        "environment": os.getenv("ENVIRONMENT", settings.environment),
        "rulesAiMode": resolve_rules_ai_mode(settings),
    }


@app.get("/api/ai/example")
def example() -> dict:
    return {"message": "AI service — use /api/ai/rules for natural-language rules"}
