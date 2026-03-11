from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import shutil
import os
import uuid
import json
from typing import List, Optional
import google.generativeai as genai
from dotenv import load_dotenv

# Local imports
from utils import extract_images_from_pdf

load_dotenv(dotenv_path="../.env")

# Config Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

app = FastAPI()

# Enable CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploads"
IMAGES_DIR = "uploads/images"
os.makedirs(IMAGES_DIR, exist_ok=True)

# In-memory store for processing status and results
# In production, this would be a database/Redis
TASKS = {}

class AnnotationResult(BaseModel):
    image_id: str
    page_number: int
    image_index: int
    filename: str
    description: Optional[str] = None
    objects: List[str] = []
    text_detected: List[str] = []
    scene_context: Optional[str] = None
    important_details: Optional[str] = None
    status: str = "pending" # pending, processing, completed, error

async def process_image_with_gemini(image_path: str, task_id: str, img_info: dict):
    model = genai.GenerativeModel("gemini-1.5-flash")
    
    prompt = """
    Analyze this image carefully and generate a structured annotation.
    Provide the following information:
    1. Detailed description of the image
    2. List of objects visible
    3. Any text detected in the image
    4. Scene context and activity
    5. Important visual details
    
    Return the output ONLY in structured JSON format with this structure:
    {
      "description": "string",
      "objects": ["string"],
      "text_detected": ["string"],
      "scene_context": "string",
      "important_details": "string"
    }
    """
    
    try:
        # Load image
        img = genai.upload_file(path=image_path)
        
        # Generate content
        response = model.generate_content([prompt, img])
        
        # Parse JSON from response
        text = response.text.strip()
        # Handle cases where markdown block is returned
        if text.startswith("```json"):
            text = text[len("```json"):].strip()
        if text.endswith("```"):
            text = text[:-3].strip()
            
        result_data = json.loads(text)
        
        # Update TASKS
        TASKS[task_id]["results"][img_info["image_id"]].update({
            **result_data,
            "status": "completed"
        })
    except Exception as e:
        print(f"Error processing image {img_info['image_id']}: {e}")
        TASKS[task_id]["results"][img_info["image_id"]]["status"] = "error"

def background_process_pdf(pdf_path: str, task_id: str):
    try:
        images = extract_images_from_pdf(pdf_path, IMAGES_DIR)
        
        TASKS[task_id]["images_total"] = len(images)
        TASKS[task_id]["status"] = "processing"
        
        for img in images:
            # Seed results entry
            TASKS[task_id]["results"][img["image_id"]] = {
                "image_id": img["image_id"],
                "page_number": img["page_number"],
                "image_index": img["image_index"],
                "filename": img["filename"],
                "status": "processing"
            }
            
        # Process each image (could be parallelized)
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def run_all():
            tasks = []
            for img in images:
                tasks.append(process_image_with_gemini(img["filepath"], task_id, img))
            await asyncio.gather(*tasks)
            
        loop.run_until_complete(run_all())
        TASKS[task_id]["status"] = "completed"
        
    except Exception as e:
        print(f"Task {task_id} failed: {e}")
        TASKS[task_id]["status"] = "error"

@app.post("/upload_pdf")
async def upload_pdf(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Invalid file format. Only PDFs allowed.")
        
    task_id = str(uuid.uuid4())
    pdf_path = os.path.join(UPLOAD_DIR, f"{task_id}_{file.filename}")
    
    with open(pdf_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    TASKS[task_id] = {
        "id": task_id,
        "filename": file.filename,
        "status": "extracting",
        "images_total": 0,
        "results": {}
    }
    
    background_tasks.add_task(background_process_pdf, pdf_path, task_id)
    
    return {"task_id": task_id}

@app.get("/processing_status/{task_id}")
async def get_status(task_id: str):
    if task_id not in TASKS:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = TASKS[task_id]
    completed_count = sum(1 for r in task["results"].values() if r["status"] == "completed")
    
    return {
        "status": task["status"],
        "total": task["images_total"],
        "completed": completed_count
    }

@app.get("/annotations/{task_id}")
async def get_annotations(task_id: str):
    if task_id not in TASKS:
        raise HTTPException(status_code=404, detail="Task not found")
        
    return list(TASKS[task_id]["results"].values())

from fastapi.staticfiles import StaticFiles
app.mount("/images", StaticFiles(directory=IMAGES_DIR), name="images")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
