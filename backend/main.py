"""
FastAPI Backend - Movie Script Analyzer
"""

import os
import logging
from typing import Optional
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from agents import MultiAgentRouter, test_single_agent
from script_parser import analyze_script

# Load .env
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Script Analyzer API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
STATIC_DIR = os.path.join(os.path.dirname(__file__), '..', 'static')
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ─────────────────────────────────────────
#  Serve Frontend
# ─────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    index_path = os.path.join(STATIC_DIR, "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


# ─────────────────────────────────────────
#  API Key Management
# ─────────────────────────────────────────

class ApiKeyConfig(BaseModel):
    provider: str   # "google" | "groq" | "openai"
    api_key: str


class SaveApiKeysRequest(BaseModel):
    gemini: Optional[str] = None
    groq: Optional[str] = None
    openai: Optional[str] = None
    anthropic: Optional[str] = None


# In-memory key store (persisted to .env on save)
_runtime_keys: dict = {
    "gemini": os.getenv("GEMINI_API_KEY", ""),
    "groq": os.getenv("GROQ_API_KEY", ""),
    "openai": os.getenv("OPENAI_API_KEY", ""),
    "anthropic": os.getenv("ANTHROPIC_API_KEY", ""),
}

ENV_PATH = os.path.join(os.path.dirname(__file__), '..', '.env')


def update_env_file(keys: dict):
    """Write updated keys back to .env file."""
    lines = []
    key_map = {
        "gemini": "GEMINI_API_KEY",
        "groq": "GROQ_API_KEY",
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
    }
    existing = {}
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r") as f:
            for line in f:
                stripped = line.strip()
                if '=' in stripped and not stripped.startswith('#'):
                    k, v = stripped.split('=', 1)
                    existing[k.strip()] = v.strip()
                else:
                    lines.append(line)

    for provider, env_name in key_map.items():
        if provider in keys and keys[provider]:
            existing[env_name] = keys[provider]

    with open(ENV_PATH, "w") as f:
        for line in lines:
            f.write(line)
        for env_name, val in existing.items():
            f.write(f"{env_name}={val}\n")


@app.post("/api/test-key")
async def test_key(config: ApiKeyConfig):
    """Test a single API key connection."""
    success, message = test_single_agent(config.provider, config.api_key)
    return {"success": success, "message": message, "provider": config.provider}


@app.post("/api/save-keys")
async def save_keys(request: SaveApiKeysRequest):
    """Save API keys to runtime store and .env file."""
    global _runtime_keys
    if request.gemini:
        _runtime_keys["gemini"] = request.gemini
    if request.groq:
        _runtime_keys["groq"] = request.groq
    if request.openai:
        _runtime_keys["openai"] = request.openai
    if request.anthropic:
        _runtime_keys["anthropic"] = request.anthropic

    try:
        update_env_file(_runtime_keys)
    except Exception as e:
        logger.warning(f"Could not write to .env file: {e}")

    return {"success": True, "message": "API keys saved successfully"}


@app.get("/api/agent-status")
async def agent_status():
    """Return configuration status of all agents."""
    router = MultiAgentRouter(api_keys=_runtime_keys)
    agents = router.get_configured_agents()
    return {"agents": agents}


@app.post("/api/test-all-keys")
async def test_all_keys():
    """Test all configured API keys in parallel."""
    router = MultiAgentRouter(api_keys=_runtime_keys)
    results = router.test_all()
    return {"results": results}


# ─────────────────────────────────────────
#  Script Analysis
# ─────────────────────────────────────────

@app.post("/api/analyze-script")
async def analyze_script_endpoint(file: UploadFile = File(...)):
    """
    Upload a screenplay PDF and extract scene-by-scene breakdown.
    Returns: scenes list with location, time of day, characters, summary.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    file_bytes = await file.read()
    if len(file_bytes) > 50 * 1024 * 1024:  # 50MB limit
        raise HTTPException(status_code=400, detail="File too large. Max 50MB.")

    router = MultiAgentRouter(api_keys=_runtime_keys)

    try:
        result = analyze_script(file_bytes, router)
        if "error" in result:
            raise HTTPException(status_code=422, detail=result["error"])
        return JSONResponse(content=result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Analysis failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────
#  Health Check
# ─────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok", "message": "Script Analyzer API is running"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
