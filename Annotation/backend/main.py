from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import shutil
import os
import uuid
import json
import time
import base64
import httpx
import traceback
from dotenv import load_dotenv

# Local imports
from utils import extract_images_from_pdf

load_dotenv(dotenv_path="../.env")

# Load API Key from environment (.env file)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

if not OPENROUTER_API_KEY:
    print("WARNING: OPENROUTER_API_KEY is not set. Please set it in your .env file.")

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
Analyze this image as a MOVIE SCENE. Return ONLY a JSON object with this structure:
{
  "scene_heading": "INT./EXT. SCENE NAME - DAY/NIGHT",
  "scene_description": "Vivid script-style paragraph describing the setting/mood.",
  "action_lines": "Visual action description.",
  "visual_elements": ["list of items"],
  "mood_and_tone": "One sentence on atmosphere.",
  "lighting_notes": "Lighting description.",
  "color_palette": "Dominant colors.",
  "characters_or_subjects": "Description of subjects.",
  "text_in_scene": ["any text found"],
  "director_notes": "Thematic intent.",
  "scene_type": "ESTABLISHING SHOT | CLOSE-UP | WIDE SHOT | etc."
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
        # We use openai/gpt-4o-mini via OpenRouter - it is extremely cheap, fast, and the model string is 100% stable
        resp = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "HTTP-Referer": "http://localhost:5173",
                "X-Title": "ScriptLens"
            },
            json={
                "model": "openai/gpt-4o-mini", 
                "messages": [{"role": "user", "content": [
                    {"type": "text", "text": CINEMATIC_PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{base64_image}"}}
                ]}],
                "response_format": {"type": "json_object"}
            },
            timeout=60.0
        )
        if resp.status_code != 200:
            raise Exception(f"OpenRouter returned {resp.status_code}: {resp.text}")
        
        data = resp.json()
        return clean_json(data["choices"][0]["message"]["content"])


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
                try:
                    result = await annotate_with_openrouter(img["filepath"], open(img["filepath"], "rb").read())
                    TASKS[task_id]["results"][img["image_id"]].update({**result, "status": "completed"})
                except Exception as e:
                    print(f"Error on {img['image_id']}: {e}")
                    TASKS[task_id]["results"][img["image_id"]].update({"status": "error", "error_message": str(e)})
                
                # Small delay to keep things stable
                if i < len(images) - 1:
                    time.sleep(1)

        loop.run_until_complete(run_all())
        TASKS[task_id]["status"] = "completed"
    except Exception as e:
        print(f"Background Process Error: {e}")
        traceback.print_exc()
        TASKS[task_id]["status"] = "error"
        TASKS[task_id]["error_message"] = str(e)

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
