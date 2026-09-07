from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.config.settings import get_settings

from app.auth.auth_routes import (
    router as google_auth_router,
)

from app.gmail.gmail_routes import (
    router as gmail_router,
)

from app.api.agent_routes import (
    router as agent_router,
)

from app.api.voice_routes import (
    router as voice_router,
)


# =============================================================
# Settings
# =============================================================

settings = get_settings()


# =============================================================
# FastAPI Application
# =============================================================

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Dynamic multilingual AI Gmail assistant",
)


# =============================================================
# CORS
# =============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================
# Session Middleware
# =============================================================

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.jwt_secret_key,
    session_cookie="zigma_session",
    max_age=60 * 60 * 24 * 7,
    same_site="lax",
    https_only=False,
)


# =============================================================
# Routers
# =============================================================

app.include_router(
    google_auth_router
)

app.include_router(
    gmail_router
)

app.include_router(
    agent_router
)

app.include_router(
    voice_router
)


# =============================================================
# Root
# =============================================================

@app.get("/")
async def root():
    return {
        "status": "ok",
        "message": settings.app_name,
        "version": settings.app_version,
    }


# =============================================================
# Health
# =============================================================

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "environment": settings.app_environment,
    }


# =============================================================
# Configuration
# =============================================================

@app.get("/config")
async def configuration():
    return {
        "application": {
            "name": settings.app_name,
            "version": settings.app_version,
            "environment": settings.app_environment,
        },

        "ai": {
            "provider": settings.llm_provider,
            "model": settings.llm_model,
            "region": settings.aws_region,
            "max_tokens": settings.llm_max_tokens,
            "temperature": settings.llm_temperature,
            "top_p": settings.llm_top_p,
        },

        "speech": {
            "stt_provider": settings.stt_provider,
            "tts_provider": settings.tts_provider,
            "languages": settings.supported_language_list,
        },

        "gmail": {
            "oauth_enabled": bool(
                settings.google_client_id
                and settings.google_client_secret
                and settings.google_redirect_uri
            ),
            "credential_store": "aws_secrets_manager",
            "aws_region": settings.aws_region,
            "secret_prefix": settings.aws_secret_prefix,
        },

        "voice": {
            "websocket_enabled": settings.websocket_enabled,
        },
    }