from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import shutil
import os
import uuid
import json
import time
import base64
import httpx
import traceback
from typing import Dict, Any
from google import genai
from google.genai import types
from dotenv import load_dotenv

# Local imports
from utils import extract_images_from_pdf

# FORCE override any old terminal environment variables
load_dotenv(dotenv_path="../.env", override=True)

# API Keys
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploads"
IMAGES_DIR = "uploads/images"
os.makedirs(IMAGES_DIR, exist_ok=True)

TASKS = {}

CINEMATIC_PROMPT = """
Perform a deeply analytical and highly detailed cinematic breakdown of this image.
Pay EXTRAORDINARY ATTENTION to any humans in the frame: What exactly are they doing? What are their micro-expressions, body language, and clothing? Analyze their spatial relationship to other objects and overall intent.
Analyze the scene as a Master Director and Director of Photography would.

Return ONLY a JSON object with this exact structure (no markdown borders, just raw JSON):
{
  "scene_heading": "INT./EXT. SCENE NAME - DAY/NIGHT",
  "scene_description": "Extremely rich paragraph detailing the setting, atmosphere, and environmental context.",
  "action_lines": "Deep analysis of what the person is doing, step-by-step actions, interactions with props, micro-expressions, posture, and kinetic energy.",
  "visual_elements": ["list of 4-6 crucial background details, architectural elements, or props"],
  "mood_and_tone": "The psychological and emotional atmosphere of the frame.",
  "lighting_notes": "Cinematic lighting setup (e.g., Chiaroscuro, high-key, neon glow, practicals).",
  "color_palette": "Dominant colors, contrast, and aesthetic grading.",
  "characters_or_subjects": "Deep psychological and visual description of the people, their clothing style, emotional state, and physical details.",
  "text_in_scene": ["Any legible text, signs, or logos found"],
  "director_notes": "Thematic intent, camera angles (e.g., Low angle, Close-up, Dutch tilt), lens choices, and blocking.",
  "scene_type": "ESTABLISHING SHOT | CLOSE-UP | WIDE SHOT | MACRO | etc."
}
"""

def get_mime_type(filepath: str) -> str:
    ext = filepath.lower().rsplit(".", 1)[-1]
    return {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(ext, "image/png")

def clean_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```json"): text = text[7:]
    if text.startswith("```"): text = text[3:]
    if text.endswith("```"): text = text[:-3]
    return json.loads(text.strip())

async def annotate_with_openrouter(image_path: str, image_bytes: bytes):
    base64_image = base64.b64encode(image_bytes).decode('utf-8')
    mime = get_mime_type(image_path)
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "HTTP-Referer": "http://localhost:5173",
                "X-Title": "ScriptLens"
            },
            json={
                "model": "openai/gpt-4o-mini",
                "max_tokens": 1500,
                "messages": [{"role": "user", "content": [
                    {"type": "text", "text": CINEMATIC_PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{base64_image}"}}
                ]}],
                "response_format": {"type": "json_object"}
            },
            timeout=60.0
        )
        if resp.status_code != 200:
            raise Exception(f"OpenRouter Error {resp.status_code}: {resp.text}")
        data = resp.json()
        return clean_json(data["choices"][0]["message"]["content"])


async def annotate_with_gemini(image_path: str, mime: str, image_bytes: bytes):
    if not gemini_client:
        raise Exception("Gemini client not configured")
    
    response = gemini_client.models.generate_content(
        model="gemini-2.0-flash",
        contents=[
            CINEMATIC_PROMPT,
            types.Part.from_bytes(data=image_bytes, mime_type=mime),
        ],
    )
    return clean_json(response.text)

async def process_image(img_info: dict, task_id: str):
    image_path = img_info["filepath"]
    errors = []
    try:
        with open(image_path, "rb") as f:
            image_bytes = f.read()
        mime = get_mime_type(image_path)
        
        MAX_RETRIES = 3
        # 1. Primary: STRICTLY OpenRouter
        if OPENROUTER_API_KEY:
            for attempt in range(MAX_RETRIES):
                try:
                    print(f"  [OPENROUTER] Annotating {img_info['image_id']}...")
                    result = await annotate_with_openrouter(image_path, image_bytes)
                    if result:
                        TASKS[task_id]["results"][img_info["image_id"]].update({**result, "status": "completed"})
                        return
                except Exception as e:
                    err_str = str(e)
                    print(f"  [OPENROUTER FAILED] {err_str}")
                    if "insufficient_quota" in err_str or "credits" in err_str.lower():
                        raise Exception("OpenRouter Error: Insufficient Quota (No credits left).")
                    if "429" in err_str:
                        wait = 5 * (attempt + 1)
                        print(f"  -> Rate Limit Reached! Waiting {wait} seconds...")
                        time.sleep(wait)
                        continue
                    # Hard fail on any other OpenRouter error to prevent silent Gemini fallback
                    raise Exception(f"OpenRouter explicitly failed: {err_str}")

        # 2. Gemini (ONLY if OPENROUTER_API_KEY is completely missing)
        elif GEMINI_API_KEY:
            for attempt in range(MAX_RETRIES):
                try:
                    print(f"  [GEMINI] Annotating {img_info['image_id']}...")
                    result = await annotate_with_gemini(image_path, mime, image_bytes)
                    if result:
                        TASKS[task_id]["results"][img_info["image_id"]].update({**result, "status": "completed"})
                        return
                except Exception as e:
                    err_str = str(e)
                    print(f"  [GEMINI FAILED] {err_str}")
                    if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                        wait = 15
                        print(f"  -> Gemini Quota Exhausted! Waiting {wait} seconds...")
                        time.sleep(wait)
                        continue
                    raise Exception(f"Gemini explicitly failed: {e}")

        else:
            raise Exception("No API keys found. Please provide an OpenRouter key.")

    except Exception as e:
        print(f"  [FINAL FAILURE] {img_info['image_id']}: {e}")
        TASKS[task_id]["results"][img_info["image_id"]].update({"status": "error", "error_message": str(e)})


def background_process_pdf(pdf_path: str, task_id: str):
    try:
        images = extract_images_from_pdf(pdf_path, IMAGES_DIR)
        TASKS[task_id]["images_total"] = len(images)
        TASKS[task_id]["status"] = "processing"

        for img in images:
            TASKS[task_id]["results"][img["image_id"]] = {
                "image_id": img["image_id"], "page_number": img["page_number"],
                "image_index": img["image_index"], "filename": img["filename"], "status": "processing"
            }

        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def run_all():
            for i, img in enumerate(images):
                print(f"Processing scene {i+1}/{len(images)}...")
                await process_image(img, task_id)
                time.sleep(1)

        loop.run_until_complete(run_all())
        TASKS[task_id]["status"] = "completed"
    except Exception as e:
        print(f"Background Process Error: {e}")
        traceback.print_exc()
        TASKS[task_id]["status"] = "error"
        TASKS[task_id]["error_message"] = str(e)


# Translation Logic
class TranslateRequest(BaseModel):
    language: str
    scene_data: Dict[str, Any]

@app.post("/translate_scene")
async def translate_scene(req: TranslateRequest):
    tgt_lang = req.language
    data_str = json.dumps(req.scene_data, ensure_ascii=False)
    
    prompt = f"""
    You are an expert cinematic localization translator. 
    Translate the values of the following JSON scene object into {tgt_lang}.
    DO NOT translate the JSON keys. Keep the exact same JSON structure.
    Translate ONLY the strings inside the JSON values into highly cinematic and eloquent fluent {tgt_lang}.
    Return ONLY raw valid JSON (no markdown wrappers).
    
    JSON: {data_str}
    """
    
    try:
        if OPENROUTER_API_KEY:
            async with httpx.AsyncClient() as client:
                res = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "HTTP-Referer": "http://localhost:5173",
                        "X-Title": "ScriptLens"
                    },
                    json={
                        "model": "openai/gpt-4o-mini",
                        "max_tokens": 1500,
                        "messages": [{"role": "user", "content": prompt}],
                        "response_format": {"type": "json_object"}
                    },
                    timeout=30.0
                )
                if res.status_code == 200:
                    d = res.json()["choices"][0]["message"]["content"]
                    return clean_json(d)
                else:
                    raise Exception(f"OpenRouter Translation Error {res.status_code}: {res.text}")
                
        # Only fallback to Gemini for translation if OpenRouter key is fully missing
        elif GEMINI_API_KEY and gemini_client:
            resp = gemini_client.models.generate_content(
                model="gemini-2.0-flash",
                contents=[prompt],
            )
            return clean_json(resp.text)
            
        raise Exception("Translation failed: No valid API configured.")

    except Exception as e:
        print(f"Translate error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/upload_pdf")
async def upload_pdf(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"): raise HTTPException(status_code=400, detail="Invalid PDF")
    task_id = str(uuid.uuid4())
    pdf_path = os.path.join(UPLOAD_DIR, f"{task_id}_{file.filename}")
    with open(pdf_path, "wb") as buffer: shutil.copyfileobj(file.file, buffer)
    TASKS[task_id] = {"id": task_id, "filename": file.filename, "status": "extracting", "images_total": 0, "results": {}}
    background_tasks.add_task(background_process_pdf, pdf_path, task_id)
    return {"task_id": task_id}

@app.get("/processing_status/{task_id}")
async def get_status(task_id: str):
    if task_id not in TASKS: return {"status": "not_found", "total": 0, "completed": 0}
    task = TASKS[task_id]
    completed = sum(1 for r in task["results"].values() if r["status"] == "completed" or r["status"] == "error")
    return {"status": task["status"], "total": task["images_total"], "completed": completed}

@app.get("/annotations/{task_id}")
async def get_annotations(task_id: str):
    if task_id not in TASKS: return []
    results = list(TASKS[task_id]["results"].values())
    results.sort(key=lambda x: (x.get("page_number", 0), x.get("image_index", 0)))
    return results

from fastapi.staticfiles import StaticFiles
app.mount("/images", StaticFiles(directory=IMAGES_DIR), name="images")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
