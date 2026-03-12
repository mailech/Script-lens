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
    replicate: Optional[str] = None
    sarvam: Optional[str] = None


# In-memory key store (persisted to .env on save)
_runtime_keys: dict = {
    "gemini": os.getenv("GEMINI_API_KEY", ""),
    "groq": os.getenv("GROQ_API_KEY", ""),
    "openai": os.getenv("OPENAI_API_KEY", ""),
    "anthropic": os.getenv("ANTHROPIC_API_KEY", ""),
    "replicate": os.getenv("REPLICATE_API_TOKEN", ""),
    "sarvam": os.getenv("SARVAM_API_KEY", ""),
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
        "replicate": "REPLICATE_API_TOKEN",
        "sarvam": "SARVAM_API_KEY",
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
    if request.replicate:
        _runtime_keys["replicate"] = request.replicate
    if request.sarvam:
        _runtime_keys["sarvam"] = request.sarvam

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
    """Universal script analyzer for professional pre-production."""
    ext = file.filename.lower().split('.')[-1]
    SUPPORTED = ('pdf', 'fdx', 'docx', 'fountain', 'txt')
    if ext not in SUPPORTED:
        raise HTTPException(status_code=400, detail=f"Unsupported format. Supported: {', '.join(SUPPORTED)}")

    file_bytes = await file.read()
    if len(file_bytes) > 60 * 1024 * 1024:  # 60MB limit
        raise HTTPException(status_code=400, detail="File too large. Max 60MB.")

    router = MultiAgentRouter(api_keys=_runtime_keys)
    try:
        # Pass filename to parser for format detection
        result = analyze_script(file_bytes, router, filename=file.filename)
        if "error" in result:
            raise HTTPException(status_code=422, detail=result["error"])
        return JSONResponse(content=result)
    except HTTPException: raise
    except Exception as e:
        logger.error(f"Analysis failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────
#  Scene Image Generation
# ─────────────────────────────────────────

class SceneImageRequest(BaseModel):
    scene_number: int
    heading: str
    time_of_day: Optional[str] = "DAY"
    int_ext: Optional[str] = "EXT"
    location: Optional[str] = ""
    tone: Optional[str] = "Neutral"
    genre: Optional[str] = "Drama"
    characters: Optional[list] = []
    summary: Optional[str] = ""


def _build_image_prompt(req: SceneImageRequest) -> str:
    """Build a rich cinematic prompt from scene metadata."""
    time_map = {
        "NIGHT": "night time, dark shadows, moonlit, artificial lights",
        "MIDNIGHT": "deep night, very dark, isolated pools of light",
        "DAWN": "pre-dawn golden light, misty atmosphere",
        "SUNRISE": "golden hour sunrise, warm orange glow, long shadows",
        "MORNING": "bright morning light, fresh atmosphere",
        "AFTERNOON": "harsh midday sun, strong shadows",
        "DUSK": "dusk, orange and purple sunset sky",
        "SUNSET": "dramatic sunset, golden hour, silhouettes",
        "EVENING": "early evening, warm street lights, blue hour",
        "DAY": "daylight, natural lighting, clear atmosphere",
        "CONTINUOUS": "continuous from previous scene, same lighting",
    }
    tod_key = (req.time_of_day or "DAY").upper()
    lighting = time_map.get(tod_key, "natural daylight")

    loc = req.location or req.heading or "film location"
    ie = "interior" if "INT" in (req.int_ext or "").upper() else "exterior"
    chars = req.characters or []
    char_text = f"Characters present: {', '.join(chars[:4])}. " if chars else ""
    tone_map = {
        "Dramatic": "dramatic lighting, high contrast, moody cinematic shadows",
        "Comedic": "bright high-key lighting, vibrant cheerful colors, wide lens",
        "Romantic": "soft dreamlike lighting, warm glow, shallow depth of field, pastel tones",
        "Action": "dynamic motion blur, low angle shot, gritty texture, high energy",
        "Thriller": "low-key lighting, suspenseful atmosphere, cold blue tones, sharp shadows",
        "Emotional": "melancholic atmosphere, soft natural light, close-up focused",
        "Horror": "eerie atmosphere, harsh shadows, desaturated colors, misty",
        "Sci-Fi": "futuristic lighting, neon accents, clean sharp lines, high tech look",
        "Neutral": "cinematic film look, professional lighting",
    }
    tone_style = tone_map.get(req.tone or "Neutral", "cinematic film look")
    
    genre_style = f"Genre: {req.genre}. " if req.genre else ""

    summary_snippet = ""
    if req.summary and len(req.summary) > 10:
        first_sent = req.summary.split('.')[0][:150]
        summary_snippet = f"Scene context: {first_sent}. "

    prompt = (
        f"Professional cinematic film production still, {ie} shot at {loc}. "
        f"{genre_style}{summary_snippet}"
        f"{char_text}"
        f"Lighting: {lighting}. "
        f"Visual Tone: {tone_style}. "
        f"Shot on 35mm film, ARRI Alexa, anamorphic lens, realistic textures, "
        f"movie quality lighting and composition. Masterpiece, high detail. No text."
    )
    return prompt


@app.post("/api/generate-scene-image")
async def generate_scene_image(req: SceneImageRequest):
    """Generate a cinematic image for a script scene using AI image generation."""
    prompt = _build_image_prompt(req)
    logger.info(f"Generating image for Scene {req.scene_number}: {prompt[:80]}...")

    # 1. Try OpenAI DALL-E 3
    openai_key = _runtime_keys.get("openai", "")
    if openai_key and openai_key not in ("", "your_openai_api_key_here"):
        try:
            from openai import OpenAI
            import base64
            client = OpenAI(api_key=openai_key)
            response = client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size="1792x1024",
                quality="standard",
                response_format="b64_json",
                n=1,
            )
            b64 = response.data[0].b64_json
            return JSONResponse(content={
                "success": True,
                "image_data": f"data:image/png;base64,{b64}",
                "provider": "dall-e-3",
                "prompt_used": prompt
            })
        except Exception as e:
            logger.warning(f"DALL-E 3 failed for scene {req.scene_number}: {e}")

    # 2. Try Gemini Imagen
    gemini_key = _runtime_keys.get("gemini", "")
    if gemini_key and gemini_key not in ("", "your_gemini_api_key_here"):
        try:
            import httpx
            import json
            
            # Using stable Imagen version
            url = f"https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-001:predict?key={gemini_key}"
            payload = {
                "instances": [{"prompt": prompt}],
                "parameters": {
                    "sampleCount": 1,
                    "aspectRatio": "16:9",
                    "personGeneration": "ALLOW_ADULT"
                }
            }
            async with httpx.AsyncClient() as client:
                res = await client.post(url, json=payload, timeout=30.0)
                if res.status_code == 200:
                    data = res.json()
                    predictions = data.get("predictions", [])
                    if predictions and "bytesBase64Encoded" in predictions[0]:
                        b64 = predictions[0]["bytesBase64Encoded"]
                        return JSONResponse(content={
                            "success": True,
                            "image_data": f"data:image/jpeg;base64,{b64}",
                            "provider": "gemini-imagen",
                            "prompt_used": prompt
                        })
                else:
                    logger.warning(f"Gemini Imagen returned {res.status_code}: {res.text}")

        except Exception as e:
            logger.warning(f"Gemini Imagen failed for scene {req.scene_number}: {e}")

    # 3. Try Replicate (Flux Schnell)
    replicate_token = _runtime_keys.get("replicate", "")
    if replicate_token and replicate_token not in ("", "your_replicate_token_here"):
        try:
            import replicate
            import httpx
            import base64
            
            # Using Flux Schnell for high quality cinematic stills
            output = replicate.run(
                "black-forest-labs/flux-schnell",
                input={
                    "prompt": prompt,
                    "aspect_ratio": "16:9",
                    "output_format": "webp",
                    "output_quality": 80,
                    "num_inference_steps": 4
                }
            )
            
            if output and len(output) > 0:
                image_url = output[0]
                # Download and convert to base64 to keep it local/consistent
                async with httpx.AsyncClient() as client:
                    img_res = await client.get(image_url)
                    if img_res.status_code == 200:
                        b64 = base64.b64encode(img_res.content).decode("utf-8")
                        return JSONResponse(content={
                            "success": True,
                            "image_data": f"data:image/webp;base64,{b64}",
                            "provider": "replicate-flux",
                            "prompt_used": prompt
                        })
        except Exception as e:
            err_msg = str(e)
            logger.warning(f"Replicate failed for scene {req.scene_number}: {err_msg}")
            # We don't return here anymore, we let it fall through to the free tier!

    # 4. Try Ultimate Free Fallback (Pollinations AI - No key required)
    logger.info(f"Using Free Tier Image Generation for Scene {req.scene_number}")
    try:
        import urllib.parse
        import httpx
        import base64
        
        # Pollinations generates images via direct URL request
        encoded_prompt = urllib.parse.quote(prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=576&nologo=true&seed={req.scene_number}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        }
        
        async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
            img_res = await client.get(url)
            if img_res.status_code == 200:
                b64 = base64.b64encode(img_res.content).decode("utf-8")
                return JSONResponse(content={
                    "success": True,
                    "image_data": f"data:image/jpeg;base64,{b64}",
                    "provider": "pollinations (free fallback)",
                    "prompt_used": prompt
                })
    except Exception as e:
        logger.warning(f"Pollinations fallback failed for scene {req.scene_number}: {e}")

    # 5. All providers failed
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": "No image generation provider available. Please configure an OpenAI, Gemini, or Replicate API key.",
        }
    )


# ─────────────────────────────────────────
#  Health Check
# ─────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok", "message": "Script Analyzer API is running"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
