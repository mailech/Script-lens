"""
Movie Script PDF Parser
- Uses PyMuPDF to extract raw text
- Uses regex to detect scene headings (INT./EXT.)
- Uses Multi-Agent LLM to enrich scene data (characters, summaries)
"""

import re
import json
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────
#  PDF Text Extraction
# ─────────────────────────────────────────

def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract raw text from PDF bytes using PyMuPDF."""
    import fitz  # PyMuPDF
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    full_text = ""
    for idx, page in enumerate(doc):
        # Adding page markers helps the LLM recognize boundaries
        full_text += f"\n--- [PAGE {idx+1}] ---\n"
        full_text += page.get_text("text") + "\n"
    doc.close()
    return full_text


# ─────────────────────────────────────────
#  Scene Heading Regex Parser
# ─────────────────────────────────────────

# Super-robust scene heading detector
# Catches: 1. INT. ROOM, INT. ROOM - DAY, SCENE 1: EXT. FIELD, etc.
# Looks for INT, EXT, or I/E at the beginning of a stripped line
SCENE_LEADERS = ['INT', 'EXT', 'I/E', 'INT.', 'EXT.', 'I/E.', 'INT/', 'EXT/']

def is_scene_heading(line: str) -> bool:
    """Checks if a line is likely a scene heading."""
    s = line.strip().upper()
    if not s: return False
    
    # Common screenwriter prefixes like "1.", "SCENE 10", etc.
    words = s.split()
    if not words: return False
    
    # Case 1: Stars with INT/EXT (most common)
    if any(s.startswith(leader) for leader in SCENE_LEADERS):
        return len(s) < 120
        
    # Case 2: Starts with a number or "SCENE", then has INT/EXT
    if len(words) > 1:
        # Check if 2nd or 3rd word is INT/EXT
        for i in range(min(3, len(words))):
            if any(words[i].startswith(leader) for leader in SCENE_LEADERS):
                return len(s) < 120
    
    return False

# Time of day detection
TIME_OF_DAY_PATTERN = re.compile(
    r'\b(DAY|NIGHT|DAWN|DUSK|MORNING|AFTERNOON|EVENING|CONTINUOUS|LATER|MOMENTS LATER|'
    r'FLASHBACK|FLASH CUT|DREAM|INTERCUT|SAME TIME|SAME|PRE-DAWN|MAGIC HOUR|'
    r'GOLDEN HOUR|SUNRISE|SUNSET|MIDNIGHT|NOON|DUSK/DAWN|DAY/NIGHT|NIGHT/DAY)\b',
    re.IGNORECASE
)

CHARACTER_LINE_PATTERN = re.compile(
    r'^\s{10,}([A-Z][A-Z\s\'\-\.]+?)(?:\s*\(.*?\))?\s*$',
    re.MULTILINE
)


def split_into_scenes(full_text: str, router=None) -> List[Dict[str, Any]]:
    """
    Fast and robust scene splitting using high-speed text scanning.
    Processes entire documents in one pass.
    """
    lines = full_text.split('\n')
    scenes = []
    current_scene = None
    current_lines = []
    scene_number = 0

    for line in lines:
        if is_scene_heading(line):
            # Save previous scene
            if current_scene is not None:
                current_scene['raw_text'] = '\n'.join(current_lines).strip()
                current_scene['characters'] = extract_characters_regex(current_scene['raw_text'])
                scenes.append(current_scene)

            scene_number += 1
            heading = line.strip()
            
            # Extract basic data
            tod_match = TIME_OF_DAY_PATTERN.search(heading)
            time_of_day = tod_match.group(0).upper() if tod_match else "UNKNOWN"
            
            # Identify location
            loc_clean = heading
            # Remove digits at start
            loc_clean = re.sub(r'^[\d\s\.\-SCENE]+', '', loc_clean, flags=re.I)
            # Remove INT/EXT
            loc_clean = re.sub(r'^(INT|EXT|I/E|INT\.?/EXT\.?|EXT\.?/INT\.?|INT\.?|EXT\.?|I/E\.?)\s*', '', loc_clean, flags=re.I)
            # Remove Time of Day
            loc_clean = re.sub(TIME_OF_DAY_PATTERN.pattern, '', loc_clean, flags=re.I).strip(' .-_')

            current_scene = {
                "scene_number": scene_number,
                "heading": heading,
                "int_ext": "INT" if "INT" in heading.upper() else "EXT",
                "location": loc_clean or "UNKNOWN LOCATION",
                "time_of_day": time_of_day,
                "characters": [],
                "character_count": 0,
                "summary": "",
                "raw_text": ""
            }
            current_lines = []
            logger.info(f"Detected scene {scene_number}: {heading}")
        else:
            if current_scene is not None:
                current_lines.append(line)

    # Add the final scene
    if current_scene is not None:
        current_scene['raw_text'] = '\n'.join(current_lines).strip()
        current_scene['characters'] = extract_characters_regex(current_scene['raw_text'])
        scenes.append(current_scene)

    if not scenes and full_text.strip():
        logger.warning("No scene headers found with scanner. Using single-scene fallback.")
        scenes.append({
            "scene_number": 1,
            "heading": "SCENE 1 (No headers detected)",
            "int_ext": "UNKNOWN",
            "location": "UNKNOWN",
            "time_of_day": "UNKNOWN",
            "characters": extract_characters_regex(full_text),
            "character_count": 0,
            "summary": "Full script text provided. No scene headers found.",
            "raw_text": full_text
        })

    logger.info(f"Total scenes identified: {len(scenes)}")
    return scenes


def extract_characters_regex(scene_text: str) -> List[str]:
    """Extract character names from scene text using indentation heuristic."""
    lines = scene_text.split('\n')
    characters = set()
    
    # Common words to exclude (not character names)
    EXCLUDE_WORDS = {
        'CUT TO', 'FADE IN', 'FADE OUT', 'DISSOLVE TO', 'SMASH CUT',
        'INTERCUT', 'TITLE', 'SUPER', 'BACK TO', 'CONTINUED', 'MORE',
        'CONT\'D', 'END OF', 'THE END', 'MONTAGE', 'SERIES OF SHOTS',
        'BEGIN', 'END', 'NOTE', 'NARRATOR', 'VOICE OVER', 'V.O', 'O.S', 'O.C',
        'PRESENT DAY', 'DAY', 'NIGHT', 'SCENE', 'TITLE', 'ACT', 'PROLOGUE',
        'EPILOGUE', 'FLASHBACK', 'MORNING', 'EVENING', 'AFTERNOON', 'LOCATION'
    }

    for line in lines:
        stripped = line.strip()
        if not stripped: continue
        
        # Character names are typically centered or heavily indented (20-40 spaces)
        # But in PDF text extraction, this might be simplified to 8-15 spaces
        leading_spaces = len(line) - len(line.lstrip())
        
        if (
            stripped.isupper()
            and 1 <= len(stripped.split()) <= 4
            and (leading_spaces >= 6 or (len(line) > 20 and leading_spaces >= 2)) # Flexible for different PDF extractions
            and not any(excl in stripped for excl in EXCLUDE_WORDS)
            and not is_scene_heading(line)
            and not re.match(r'^\d+$', stripped) # Exclude page numbers
        ):
            # Clean up V.O., O.S., (CONT'D) etc.
            clean_name = re.sub(r'\s*\(.*?\)', '', stripped).strip()
            # Remove more variations of V.O., O.S., etc.
            clean_name = re.sub(r"\b(V\.O\.?|O\.S\.?|O\.C\.?|CONT'D|CONTINUED|V/O|O/S)\b", '', clean_name, flags=re.I).strip()
            
            # Further validation: No periods (unless in middle), no trailing punctuations, no common movie words
            if (
                clean_name 
                and len(clean_name) >= 2 
                and not clean_name.isdigit()
                and not any(word in clean_name.upper() for word in ['INT', 'EXT', 'SCENE', 'PAGE', 'TITLE', 'REVISION'])
            ):
                characters.add(clean_name)

    return sorted(list(characters))


# ─────────────────────────────────────────
#  LLM Enhancement
# ─────────────────────────────────────────

def build_enhancement_prompt(scenes_batch: List[Dict]) -> str:
    """Build JSON prompt for LLM to enhance scene data."""
    scenes_text = []
    for s in scenes_batch:
        # Highly optimized excerpt size to stay within Free Tier limits
        truncated_text = s['raw_text'][:300] if len(s['raw_text']) > 300 else s['raw_text']
        scenes_text.append(
            f"SCENE {s['scene_number']}: {s['heading']}\n"
            f"REGEX CHARACTERS FOUND: {', '.join(s['characters']) if s['characters'] else 'None detected'}\n"
            f"SCENE TEXT EXCERPT:\n{truncated_text}\n"
            f"{'─'*40}"
        )

    scenes_block = '\n\n'.join(scenes_text)

    prompt = f"""You are a professional screenplay analyst. Analyze the following movie script scenes.

For EACH scene, return a JSON array where each object has:
- "scene_number": (integer, must match the scene number)
- "characters": (array of ALL character names present, correcting any from regex)
- "character_count": (integer count of unique characters)
- "summary": (A DETAILED, DESCRIPTIVE 2-3 sentence summary explaining exactly what happens)
- "location_detail": (clean, human-readable location name)
- "time_of_day": (DAY, NIGHT, DAWN, DUSK, MORNING, AFTERNOON, EVENING, CONTINUOUS, or LATER)

IMPORTANT RULES:
- Characters include EVERYONE who speaks or is explicitly named in the scene
- Do NOT include V.O. (voice over) characters as physically present
- Keep summaries concise and objective
- Fix any regex extraction errors for character names
- Return ONLY valid JSON array, no other text, no markdown

SCENES TO ANALYZE:
{scenes_block}

Return format (JSON array only):
[
  {{
    "scene_number": 1,
    "characters": ["CHARACTER_A", "CHARACTER_B"],
    "character_count": 2,
    "summary": "...",
    "location_detail": "...",
    "time_of_day": "..."
  }},
  ...
]"""
    return prompt


def enhance_scenes_with_llm(scenes: List[Dict], router) -> List[Dict]:
    """
    Use multi-agent LLM to enhance scene data in sequential batches.
    Sequential is much more stable for Free Tier rate limits.
    """
    from concurrent.futures import ThreadPoolExecutor
    BATCH_SIZE = 30 # Large batches to minimize total API calls
    enhanced_scenes = []
    
    # We'll use a local list to collect results to ensure order doesn't break
    batches = [scenes[i:i + BATCH_SIZE] for i in range(0, len(scenes), BATCH_SIZE)]
    
    def process_batch(batch):
        try:
            logger.info(f"Processing batch of {len(batch)} scenes...")
            prompt = build_enhancement_prompt(batch)
            response_text, agent_used = router.generate(prompt)
            
            clean_response = response_text.replace('```json', '').replace('```', '').strip()
            json_match = re.search(r'\[\s*\{.*\}\s*\]', clean_response, re.DOTALL)
            
            if json_match:
                llm_data = json.loads(json_match.group())
                llm_map = {item['scene_number']: item for item in llm_data}
                for scene in batch:
                    info = llm_map.get(scene['scene_number'], {})
                    if info:
                        scene['characters'] = info.get('characters', scene['characters'])
                        scene['character_count'] = info.get('character_count', len(scene['characters']))
                        scene['summary'] = info.get('summary', '')
                        scene['location_detail'] = info.get('location_detail', scene['location'])
                        scene['time_of_day'] = info.get('time_of_day', scene['time_of_day'])
            return (batch, agent_used)
        except Exception as e:
            logger.error(f"Batch processing failed: {e}")
            # Fallback: Don't show an error, just use regex characters and mark summary
            for s in batch:
                s['character_count'] = len(s['characters'])
                s['summary'] = "Detailed summary unavailable due to API rate limits."
                s['location_detail'] = s['location']
            return (batch, "failed")

    # Use max_workers=1 to be very stable against 429 errors
    logger.info(f"Starting sequential enhancement for {len(batches)} batches...")
    with ThreadPoolExecutor(max_workers=1) as executor:
        results = list(executor.map(process_batch, batches))

    # Re-assemble
    final_scenes = []
    final_agent = "various"
    for batch_res, agent in results:
        final_scenes.extend(batch_res)
        final_agent = agent # Keep last one for reporting
        
    return final_scenes, final_agent


# ─────────────────────────────────────────
#  Main Entry Point
# ─────────────────────────────────────────

def analyze_script(file_bytes: bytes, router) -> Dict[str, Any]:
    """
    Full pipeline: PDF → Text → Scenes → LLM Enhancement → Results
    """
    logger.info("Step 1: Extracting text from PDF...")
    full_text = extract_text_from_pdf(file_bytes)

    logger.info("Step 2: Splitting into scenes...")
    scenes = split_into_scenes(full_text, router=router)

    if not scenes:
        return {
            "error": "No scenes detected. Make sure this is a properly formatted screenplay PDF.",
            "scenes": [],
            "stats": {}
        }

    logger.info(f"Step 3: Enhancing {len(scenes)} scenes with LLM...")
    enhanced_scenes, agent_used = enhance_scenes_with_llm(scenes, router)

    # Build stats
    all_characters = set()
    locations = set()
    day_count = 0
    night_count = 0

    for s in enhanced_scenes:
        all_characters.update(s.get('characters', []))
        locations.add(s.get('location_detail', s.get('location', '')))
        tod = s.get('time_of_day', '').upper()
        if 'NIGHT' in tod or 'MIDNIGHT' in tod:
            night_count += 1
        elif any(t in tod for t in ['DAY', 'MORNING', 'AFTERNOON', 'NOON', 'DAWN', 'DUSK', 'EVENING', 'SUNRISE', 'SUNSET']):
            day_count += 1

    # Remove raw_text to keep response slim
    for s in enhanced_scenes:
        s.pop('raw_text', None)

    return {
        "scenes": enhanced_scenes,
        "agent_used": agent_used or "regex-only",
        "stats": {
            "total_scenes": len(enhanced_scenes),
            "total_characters": len(all_characters),
            "unique_locations": len(locations),
            "day_scenes": day_count,
            "night_scenes": night_count,
            "all_characters": sorted(list(all_characters)),
            "all_locations": sorted(list(locations))
        }
    }
