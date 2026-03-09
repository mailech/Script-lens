"""
Movie Script PDF Parser
- Uses PyMuPDF to extract raw text
- Uses regex to detect scene headings
- Uses Multi-Agent LLM to enrich scene data
"""

import re
import json
import logging
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)

# #########################################
# PDF Text Extraction
# #########################################

def _ratio_garbled(text: str) -> float:
    """
    Returns ratio of Latin-Extended 'garbled' chars to total alpha chars.
    PDFs with custom font encodings produce Latin-Extended garbage (U+0080..U+024F)
    when decoded incorrectly. Legitimate Telugu is U+0C00..U+0C7F, Hindi U+0900..U+097F.
    """
    alpha = [c for c in text if c.isalpha()]
    if not alpha:
        return 0.0
    # Latin Extended A/B (U+00C0..U+024F) = common garbled PDF encoding range
    garbled = [c for c in alpha if 0x00C0 <= ord(c) <= 0x024F]
    return len(garbled) / len(alpha)


def sanitize_line(line: str) -> str:
    """
    Clean a single line from garbled PDF encoding.
    Lines with >40% garbled Latin-Extended chars are replaced with a placeholder
    so the LLM still knows content existed but ignores the garbage bytes.
    """
    if _ratio_garbled(line) > 0.4:
        # Keep any clean ASCII words from the line
        clean_words = [w for w in line.split() if _ratio_garbled(w) <= 0.2 and w.strip()]
        if clean_words:
            return ' '.join(clean_words)
        return ''  # Fully garbled line — drop it
    return line


def is_real_character_name(name: str) -> bool:
    """
    Validate that a string looks like a real character name.
    Rejects: numbers, timecodes, dialogue-like text, common non-name words, garbled artifacts.
    """
    if not name or not name.strip():
        return False
    name = name.strip()
    
    # Reject if it's purely numeric (e.g. "16", "17", timecodes)
    if re.match(r'^[\d\s\.:,\-]+$', name):
        return False

    # Reject timecodes like 00.34.09.16
    if re.match(r'^\d{2}[\.:]\ *\d{2}[\.:]\ *\d{2}', name):
        return False

    # Rejects if it contains dialogue punctuation
    if any(c in name for c in [':', '!', '?', ';', '[', ']', '{', '}']):
        return False
    
    # Reject known placeholders and boilerplate production words
    NON_NAME_WORDS = {
        'N/A', 'NA', 'NONE', '-', '—', 'NULL', 'UNKNOWN', 'TBD', 'CONTINUED',
        'LOOKING', 'GOING', 'COLLEGE', 'STUDENTS', 'PEOPLE', 'CROWD', 'CAMERA',
        'SCENE', 'CUT', 'FADE', 'EXT', 'INT', 'DAY', 'NIGHT', 'MORNING',
        'EVENING', 'LATER', 'CONTINUOUS', 'TRANSITION', 'SMASH', 'DISSOLVE',
    }
    if name.upper() in NON_NAME_WORDS:
        return False
        
    # Reject if >30% garbled Latin-Extended chars
    if _ratio_garbled(name) > 0.3:
        return False
        
    # Reject based on length
    if len(name) > 35 or len(name) < 2:
        return False

    # Reject pure numbers (even if embedded): names must have letters
    alpha = sum(1 for c in name if c.isalpha())
    if alpha < 2:
        return False
        
    # Reject if it starts with lowercase ASCII (names are usually capitalized)
    if name[0].islower() and name.isascii():
        return False
        
    # Reject if it has too many comma/periods (it's dialogue or a sentence)
    if name.count(',') > 1 or name.count('.') > 2:
        return False

    # Reject if word count > 5 (likely a sentence fragment, not a name)
    if len(name.split()) > 5:
        return False
        
    return True


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """
    Extract text from PDF using multiple strategies.
    Tries standard text, then rawdict (better for custom-encoded Indian fonts),
    then falls back to blocks mode. Returns the most readable result.
    """
    import fitz
    doc = fitz.open(stream=file_bytes, filetype="pdf")

    def try_standard():
        pages = []
        for page in doc:
            pages.append(page.get_text("text", sort=True))
        return "\n".join(pages)

    def try_blocks():
        pages = []
        for page in doc:
            blocks = page.get_text("blocks", sort=True)
            page_lines = []
            for b in blocks:
                if b[6] == 0:  # text block
                    page_lines.append(b[4])
            pages.append('\n'.join(page_lines))
        return "\n".join(pages)

    results = [try_standard(), try_blocks()]

    # Pick the result with the lowest garbled ratio (most readable)
    def score(text):
        lines = [l for l in text.split('\n') if l.strip()]
        if not lines:
            return 1.0
        ratios = [_ratio_garbled(l) for l in lines]
        return sum(ratios) / len(ratios)

    best = min(results, key=score)
    logger.info(f"PDF extraction: chose strategy with garbled ratio {score(best):.2f}")

    # Sanitize lines: filter/clean garbled encoding
    clean_lines = []
    for line in best.split('\n'):
        cleaned = sanitize_line(line)
        clean_lines.append(cleaned)
    return '\n'.join(clean_lines)



# #########################################
# Scene Heading Detection (Multi-Strategy)
# #########################################

def is_scene_heading(line: str) -> bool:
    """
    Detects if a line is a scene heading (slugline).
    Handles standard INT./EXT. and common Indian script formats.
    """
    l = line.strip().upper()
    if not l or len(l) < 4:
        return False
    
    # Reject common action/camera directions
    rejects = ["WITH CAMERA", "FADE IN", "FADE OUT", "CUT TO", "DISSOLVE", "SCENE CUTS", "CONTINUED", "TRANSITION", "THE SCENE CUTS"]
    if any(r in l for r in rejects):
        return False

    # Standard INT/EXT
    if l.startswith(("INT.", "EXT.", "INT/", "EXT/", "INT ", "EXT ", "I/E", "INT-", "EXT-")):
        return True
    
    # Multilingual scene keywords
    multilingual_markers = [
        "SCENE", "दृश्य", "సన్నివేశం", "కాட்சி", "స్థానం", "మొదలు", "ముగింపు",
        "SC No", "SC.NO", "S.NO", "SN.", "సీన్", "దృశ్యం", "దృశ్యము", "सीन", "ఘట్టం", "स्थान"
    ]
    for m in multilingual_markers:
        if l.startswith(m.upper()):
            return len(l.split()) >= 1

    # Numbered sluglines with location or TOD
    if re.match(r'^\d+[A-Z]?[\.\s-]', l):
        tod_markers = ["DAY", "NIGHT", "MORNING", "EVENING", "DUSK", "DAWN", "CONTINUOUS", "LATER", "RAAT", "DIN", "SUBAH"]
        place_words = [
            "HOUSE", "OFFICE", "ROAD", "STREET", "CAR", "COLLEGE", "SCHOOL", "PARK", "MARKET", "STATION", 
            "HOTEL", "RESTAURANT", "AIRPORT", "KITCHEN", "HALL", "TEMPLE", "CHURCH", "VILLAGE", "CITY",
            "MALL", "Market", "Bazaar", "Bazar", "Hospital", "Garden", "Beach", "Forest"
        ]
        has_tod = any(m in l for m in tod_markers)
        has_place = any(pw.upper() in l for pw in place_words)
        has_sep = any(s in l for s in [" - ", " — ", " / ", ".", ":"])
        if has_tod or has_place or has_sep:
            return True
            
    return False



def clean_scene_heading(line: str) -> str:
    """Clean heading: remove prefix numbers/labels and timecodes but keep the core info."""
    l = line.strip()
    # 1. Remove markers like "SCENE 2A:", "1.", "SC.NO 10:"
    cleaned = re.sub(r'^(SCENE|दृश्य|సన్నివేశం|காட்சி|SC|SC\.?NO|S\.?NO|SN\.?|ఘట్టం|#)\s*[\d\w.-]+[:\.\s-]*', '', l, flags=re.IGNORECASE)
    
    # If it was just a raw number like "2 COLLEGE", strip the number part
    if cleaned == l:
        cleaned = re.sub(r'^\d+[A-Z]?[\.\s-]*', '', cleaned)

    # 2. Remove timecode ranges like "00.34.09.16 to 00.35.41.03"
    cleaned = re.sub(r'\d{2}\.?\d{2}\.?\d{2}\.?\d{2}\s*(to|TO)\s*\d{2}\.?\d{2}\.?\d{2}\.?\d{2}', '', cleaned)
    # Individual timecodes
    cleaned = re.sub(r'\d{2}\.\d{2}\.\d{2}\.\d{2}', '', cleaned)
    
    # Final trim of any remaining noise like " - " at the start
    cleaned = re.sub(r'^[:\.\s-]*', '', cleaned)
    
    # If we cleaned too much and left it empty, return original
    return cleaned.strip() or l

def get_script_scene_number(line: str) -> str:
    """Extract specifically the scene number from the text if present (e.g. '2A')."""
    match = re.search(r'(?:SCENE|SC|SC\.?NO|S\.?NO|SN\.?|#)\s*([\d]+[A-Z]?)', line, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    # Also try start of line numbers
    match = re.match(r'^(\d+[A-Z]?)[\.\s-]', line.strip())
    if match:
        return match.group(1).upper()
    return ""
def _make_scene_skeleton(num: int, heading: str, raw_line: str) -> Dict[str, Any]:
    """Helper to create initial scene structure."""
    script_num = get_script_scene_number(raw_line)
    return {
        "scene_number": num,
        "script_scene_number": script_num or str(num),
        "heading": heading,
        "int_ext": "UNKNOWN",
        "location": "UNKNOWN",
        "location_detail": "UNKNOWN",
        "time_of_day": "DAY",
        "characters": [],
        "character_count": 0,
        "summary": "Analyzing scene...",
        "props": [],
        "vehicles": [],
        "animals": [],
        "extras": [],
        "tone": "Neutral",
        "wardrobe": "Standard",
        "stunts": False,
        "vfx": False,
        "environment": [],
        "raw_text": raw_line + "\n"
    }

def split_into_scenes(text: str, router=None) -> List[Dict]:
    """
    Split raw text into scene blocks using a reinforced multi-pass strategy.
    Optimized for Indian scripts where formatting (indentation) is often lost.
    """
    lines = text.split('\n')
    scenes = []
    current_scene = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if is_scene_heading(line):
            if current_scene:
                scenes.append(current_scene)
            heading = clean_scene_heading(line)
            current_scene = _make_scene_skeleton(len(scenes) + 1, heading, line)
        elif current_scene:
            current_scene["raw_text"] += line + "\n"
            
            # --- IMPROVED CHARACTER EXTRACTION (NO DIALOGUE) ---
            line_lstrip = line.lstrip()
            indent = len(line) - len(line_lstrip)
            content = line_lstrip.strip()
            
            is_potential_name = False
            name = ""

            # Check for "NAME: DIALOGUE" pattern
            speaker_match = re.match(r'^([A-Z\u0C00-\u0C7F\u0900-\u097F\u0B80-\u0BFF\s]{2,35})[:\-]', content)
            
            if speaker_match:
                name = speaker_match.group(1).strip()
                is_potential_name = True
            elif indent >= 10 and 1 <= len(content.split()) <= 3:
                # Normal center-indented character name
                name = content
                is_potential_name = True
            elif content.isupper() and 1 <= len(content.split()) <= 2 and len(content) > 2:
                # Bold/ALL-CAPS solo line character name
                name = content
                is_potential_name = True

            if is_potential_name and name:
                # CLEAN-UP: Remove trailing/leading garbage from name
                name = name.strip()
                # Reject if common production markers or it looks like dialogue
                rejects = ["EXT", "INT", "DAY", "NIGHT", "CUT TO", "FADE", "SCENE", "CONTINUED", "CONT.", "(V.O.)", "(O.S.)"]
                if not any(r in name.upper() for r in rejects):
                    # Check if name is actually dialogue (has too many common lowercase words)
                    common_words = ["the", "this", "that", "was", "for", "with", "have", "will", "you", "they", "them", "from"]
                    word_list = name.lower().split()
                    if not any(w in word_list for w in common_words):
                        if is_real_character_name(name) and name not in current_scene["characters"]:
                            current_scene["characters"].append(name)

    if current_scene:
        scenes.append(current_scene)
    
    # PASS 1.5: If No scenes found or very few, fallback to generic numbered split
    if len(scenes) < 2:
        logger.warning(f"Pass 1 found only {len(scenes)} scenes. Attempting generic numbered split.")
        scenes = []
        current_scene = None
        for line in lines:
            stripped = line.strip()
            if not stripped: continue
            if re.match(r'^\d+[\.\s]', stripped) and len(stripped) < 100:
                if current_scene: scenes.append(current_scene)
                current_scene = _make_scene_skeleton(len(scenes) + 1, stripped, line)
            elif current_scene:
                current_scene["raw_text"] += line + "\n"
        if current_scene: scenes.append(current_scene)

    # Post-process: initial character counting
    for s in scenes:
        s["character_count"] = len(s["characters"])

    logger.info(f"Detected {len(scenes)} scenes in total.")

    # ── PASS 2: Blank-line + ALL-CAPS heading detection (Indian script fallback) ──
    if len(scenes) <= 1:
        logger.warning("Initial pass found <=1 scene. Running Pass 2: blank-line + ALL-CAPS detection...")
        scenes = []
        current_scene = None
        prev_blank = True  # start of file counts as "preceded by blank"

        for line in lines:
            stripped = line.strip()
            # A candidate heading: preceded by blank, short, mostly uppercase
            if prev_blank and stripped and len(stripped) <= 70:
                alpha = [c for c in stripped if c.isalpha()]
                uppers = [c for c in stripped if c.isupper()]
                is_cap_heavy = alpha and (len(uppers) / len(alpha) >= 0.75)
                words = stripped.split()
                is_short = 1 <= len(words) <= 8
                if is_cap_heavy and is_short and not stripped.startswith('('):
                    if current_scene:
                        scenes.append(current_scene)
                    heading = stripped.upper()
                    current_scene = _make_scene_skeleton(len(scenes) + 1, heading, stripped)
                    prev_blank = False
                    continue

            if current_scene:
                current_scene["raw_text"] += line + "\n"

            prev_blank = (stripped == "")

        if current_scene:
            scenes.append(current_scene)

        logger.info(f"Pass 2: {len(scenes)} scenes detected")

    # ── PASS 3: Auto-chunk fallback — guarantees output for ANY script ──
    if len(scenes) <= 1:
        logger.warning("Pass 2 found <=1 scene. Running Pass 3: auto-chunk fallback...")
        scenes = []
        CHUNK_SIZE = 80  # lines per scene
        meaningful_lines = [l for l in lines if l.strip()]

        for i in range(0, len(meaningful_lines), CHUNK_SIZE):
            chunk = meaningful_lines[i:i + CHUNK_SIZE]
            scene_num = (i // CHUNK_SIZE) + 1
            # Use first non-empty line as heading
            heading = chunk[0].strip()[:60] if chunk else f"SECTION {scene_num}"
            scene = _make_scene_skeleton(scene_num, heading, chunk[0] if chunk else "")
            scene["raw_text"] = "\n".join(chunk)
            scenes.append(scene)

        logger.info(f"Pass 3 (auto-chunk): {len(scenes)} sections created")

    return scenes



# #########################################
# LLM Enhancement
# #########################################

def build_enhancement_prompt(scenes_batch: List[Dict]) -> str:
    """Build production breakdown prompt — with extras estimation and char extraction guidance."""
    scenes_text = []
    for s in scenes_batch:
        truncated_text = s['raw_text'][:800] if len(s['raw_text']) > 800 else s['raw_text']
        scenes_text.append(
            f"=== SCENE {s['scene_number']}: {s['heading']} ==="
            f"\nTEXT:\n{truncated_text}\n"
        )

    scenes_block = '\n'.join(scenes_text)

    prompt = f"""You are a professional film production analyst. Analyze these screenplay scenes.
The script may be in English, Telugu, Hindi, Tamil, or code-mixed. Handle ALL languages.

CHARACTER EXTRACTION RULES:
- A character is any NAMED PERSON who speaks or is physically present in the scene.
- Find characters from: dialogue speaker labels (even if in Telugu/Hindi/Tamil), named mentions in action, and visible named people.
- **VERY IMPORTANT**: You MUST translate ALL non-English character names to English (e.g. "రాము" -> "Ramu", "పిలుపు" -> "Call/Name", "రవి" -> "Ravi").
- Look for standard script patterns where character names are placed before dialogue (often indented or bolded).
- Do NOT include dialogue or descriptions as character names. Only proper names.
- If a scene has dialogue, the person speaking IS a character. List them.
- Even if the text has some encoding artifacts, try to decipher the character names.

EXTRAS ESTIMATION RULES (VERY IMPORTANT — never return 0 unless the scene is completely isolated):
- Market / Bazaar / Mall scene → 30-80 extras
- Classroom / College / School scene → 20-40 extras
- Road / Traffic / Street scene → 10-50 extras
- Restaurant / Dhaba / Cafe scene → 10-30 extras
- Office / Workplace scene → 5-20 extras
- Temple / Church / Mosque scene → 20-60 extras
- Hospital scene → 10-20 extras
- Wedding / Party / Function scene → 50-200 extras
- Courtroom scene → 20-50 extras
- Private room / Home scene with only main cast → 0-2 extras
- any PUBLIC place = at least 10 extras

NAMED EXTRAS: List background roles with specific types like:
"Shopkeeper", "Traffic Police", "Street Vendor", "Waiter", "Student", "Nurse", "Security Guard"

Return ONLY a valid JSON array. No markdown, no explanations before/after.

[
  {{
    "scene_number": <integer matching input>,
    "location": "place name in English",
    "time_of_day": "DAY or NIGHT or MORNING or EVENING etc",
    "characters": ["Character Name 1", "Character Name 2"],
    "extras": ["Shopkeeper", "Street Vendor", "Police Officer"],
    "props": ["prop1", "prop2"],
    "vehicles": [],
    "animals": [],
    "wardrobe": "brief costume note per character",
    "stunts": false,
    "vfx": false,
    "tone": "emotional tone in English",
    "environment": ["Weather/conditions e.g. Sunny, Crowded, Noisy"],
    "bts_requirements": {{
      "actors_required": <int: number of named characters>,
      "extras_required": <int: estimate based on location type — DO NOT return 0 for public scenes>,
      "props_department": ["every prop needed on set"],
      "location_requirements": "specific logistical need e.g. 'Public road — obtain municipality permit'",
      "lighting_requirements": "lighting setup description",
      "sound_requirements": "sound recording approach",
      "camera_suggestions": "shot style and key shots",
      "safety_concerns": ["any risks or special requirements"]
    }},
    "shooting_type": "PUBLIC LOCATION or INTERIOR or EXTERIOR or STUDIO / PRIVATE",
    "location_permit": true or false,
    "summary": "2-3 clear sentences in English describing what happens in this scene, who is present, and what is notable from a production standpoint. Do NOT include garbled text."
  }}
]

SCENES TO ANALYZE:
{scenes_block}
"""
    return prompt


# Keywords that indicate a PUBLIC LOCATION requiring shoot permits
PUBLIC_LOCATION_KEYWORDS = [
    "road", "street", "highway", "junction", "signal", "traffic", "flyover", "bridge",
    "market", "bazaar", "bazar", "mall", "shopping", "shop", "store",
    "park", "garden", "beach", "river", "lake", "forest", "hill", "mountain",
    "temple", "church", "mosque", "masjid", "mandir",
    "station", "railway", "airport", "bus stand", "bus stop",
    "hospital", "school", "college", "university",
    "stadium", "ground", "court",
    "restaurant", "hotel", "dhaba", "cafe",
    "village", "town", "city", "downtown",
    "police", "court", "government",
    "ext", "exterior", "outside", "outdoor",
]

# Estimated extras by location type (for fallback)
_EXTRAS_BY_KEYWORD = {
    "market": 60, "bazaar": 60, "bazar": 60, "mall": 40, "shopping": 30,
    "road": 25, "street": 20, "highway": 15, "traffic": 30,
    "temple": 35, "church": 25, "mosque": 30, "masjid": 30,
    "station": 40, "railway": 35, "airport": 30, "bus stand": 25,
    "hospital": 20, "school": 30, "college": 30,
    "wedding": 100, "party": 50, "function": 60, "celebration": 50,
    "stadium": 80, "restaurant": 20, "hotel": 15, "cafe": 10,
    "park": 20, "garden": 15, "beach": 30, "village": 25,
    "classroom": 30, "office": 15, "court": 40,
}


def detect_shooting_type(heading: str, location: str) -> dict:
    """
    Detects whether a scene needs a PUBLIC location permit,
    and estimates extras required based on location type.
    Returns dict with shooting_type, location_permit, extras_estimate.
    """
    combined = (heading + " " + location).lower()
    is_public = any(kw in combined for kw in PUBLIC_LOCATION_KEYWORDS)

    # INT. = definitely interior/studio
    is_interior = heading.upper().startswith("INT")
    is_exterior = heading.upper().startswith("EXT") or (not is_interior and is_public)

    if is_interior:
        shooting_type = "INTERIOR"
        permit_needed = False
    elif is_public:
        shooting_type = "PUBLIC LOCATION"
        permit_needed = True
    elif is_exterior:
        shooting_type = "EXTERIOR"
        permit_needed = False
    else:
        shooting_type = "STUDIO / PRIVATE"
        permit_needed = False

    # Estimate extras
    extras_est = 0
    for kw, count in _EXTRAS_BY_KEYWORD.items():
        if kw in combined:
            extras_est = max(extras_est, count)
    if is_public and extras_est == 0:
        extras_est = 15  # default for generic public place

    return {
        "shooting_type": shooting_type,
        "location_permit": permit_needed,
        "extras_estimate": extras_est,
    }


def fallback_enrich_scene(scene: Dict) -> Dict:
    """
    Regex-based scene enrichment when LLM is unavailable.
    Generates clean summaries WITHOUT using garbled raw text.
    """
    heading = scene.get('heading', 'UNKNOWN SCENE')
    heading_up = heading.upper()
    raw = scene.get('raw_text', '')

    # ── Time of Day ──
    tod = "DAY"
    for marker in ["NIGHT", "MIDNIGHT", "DAWN", "DUSK", "EVENING",
                   "MORNING", "AFTERNOON", "SUNSET", "SUNRISE", "CONTINUOUS", "LATER"]:
        if marker in heading_up:
            tod = marker
            break
    scene['time_of_day'] = tod

    # ── Location from heading ──
    loc_match = re.search(
        r'(?:INT|EXT)[./\s-]+(.*?)(?:\s*[-\u2013\u2014]\s*(?:DAY|NIGHT|MORNING|EVENING|DUSK|DAWN|AFTERNOON|SUNSET|SUNRISE|CONTINUOUS))?$',
        heading_up)
    location_detail = loc_match.group(1).strip() if loc_match else heading
    scene['location_detail'] = location_detail or heading

    # ── INT / EXT ──
    if heading_up.startswith('INT'):
        scene['int_ext'] = 'INT'
    elif heading_up.startswith('EXT'):
        scene['int_ext'] = 'EXT'
    else:
        scene['int_ext'] = 'UNKNOWN'

    # ── Shooting type & permit detection ──
    shoot_info = detect_shooting_type(heading, location_detail)
    scene['shooting_type'] = shoot_info['shooting_type']
    scene['location_permit'] = shoot_info['location_permit']

    # ── Props — only from clean ASCII words in raw text ──
    prop_keywords = [
        "gun", "pistol", "knife", "phone", "mobile", "camera", "car", "bike", "motorcycle",
        "bottle", "glass", "table", "chair", "book", "bag", "suitcase", "rope", "torch",
        "fire", "sword", "weapon", "rifle", "photo", "picture", "letter", "document",
        "ring", "chain", "key", "computer", "laptop", "television", "tv"
    ]
    # Only scan clean ASCII parts of raw text for props
    clean_raw = ' '.join(w for w in raw.split() if _ratio_garbled(w) <= 0.2)
    raw_lower = clean_raw.lower()
    found_props = [kw.title() for kw in prop_keywords if kw in raw_lower]
    scene['props'] = list(set(found_props))[:8]

    # ── Clean summary — built from KNOWN facts, never from garbled raw text ──
    chars = scene.get('characters', [])
    n_chars = len(chars)
    char_list = ", ".join(chars[:3]) + (" and others" if n_chars > 3 else "")
    char_phrase = f"involving {char_list}" if chars else "with no named characters"
    
    permit_note = " This is a public shoot requiring local authority permits." if shoot_info['location_permit'] else ""
    atmos = "night-time" if 'NIGHT' in tod or 'MIDNIGHT' in tod else "daytime"
    
    # Professional production summary
    summary_parts = [
        f"This {scene['int_ext'].lower()} scene takes place at a {scene['location_detail']} location during {atmos}.",
        f"The sequence {char_phrase} will require {shoot_info['extras_estimate']} extras for background atmosphere.",
        f"Technical focus: Standard {scene['int_ext'].lower()} coverage.{permit_note}"
    ]
    scene['summary'] = " ".join(summary_parts)

    # ── BTS ──
    is_night = 'NIGHT' in tod or 'MIDNIGHT' in tod
    extras = shoot_info['extras_estimate']
    scene['bts_requirements'] = {
        "actors_required": max(n_chars, 1),
        "extras_required": extras,
        "props_department": scene['props'] if scene['props'] else ["Standard props"],
        "location_requirements": (
            "Public location — obtain shoot permit from local authority" if shoot_info['location_permit']
            else f"{'Indoor' if scene['int_ext'] == 'INT' else 'Outdoor'} location scout required"
        ),
        "lighting_requirements": "Night lighting rig + reflectors" if is_night else "Natural daylight + fill lights",
        "sound_requirements": "Sync sound recording with boom mic",
        "camera_suggestions": "Standard 3-point coverage with close-ups for dialogue",
        "safety_concerns": [
            "Night shoot safety protocols" if is_night else "Standard set safety",
            "Crowd control required" if shoot_info['location_permit'] else "Standard protocols",
        ]
    }
    scene['tone'] = "Dramatic"
    scene['wardrobe'] = "As per character profile"
    scene['stunts'] = False
    scene['vfx'] = False
    scene['environment'] = [
        "Public" if shoot_info['location_permit'] else ("Night ambience" if is_night else "Natural daylight")
    ]
    scene['character_count'] = n_chars
    scene.setdefault('extras', [])
    return scene



def enhance_scenes_with_llm(scenes: List[Dict], router) -> Tuple[List[Dict], str]:
    """Parallel LLM Enhancement Engine with fallback."""
    from concurrent.futures import ThreadPoolExecutor
    BATCH_SIZE = 5
    batches = [scenes[i:i + BATCH_SIZE] for i in range(0, len(scenes), BATCH_SIZE)]
    agent_used_tracker = []

    def sanitize_list(val):
        return [str(item) for item in val] if isinstance(val, list) else []

    def process_batch(batch):
        try:
            prompt = build_enhancement_prompt(batch)
            response_text, agent = router.generate(prompt)
            agent_used_tracker.append(agent)
            logger.info(f"LLM ({agent}) responded for batch of {len(batch)} scenes")

            clean_response = response_text.replace('```json', '').replace('```', '').strip()

            # Try to find JSON array; fall back to wrapping extracted objects
            json_match = re.search(r'\[.*\]', clean_response, re.DOTALL)
            if not json_match:
                obj_matches = re.findall(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', clean_response, re.DOTALL)
                if obj_matches:
                    clean_response = '[' + ','.join(obj_matches) + ']'
                    json_match = re.search(r'\[.*\]', clean_response, re.DOTALL)

            if json_match:
                try:
                    llm_data = json.loads(json_match.group())
                    llm_map = {item['scene_number']: item for item in llm_data if isinstance(item, dict)}

                    for scene in batch:
                        info = llm_map.get(scene['scene_number'], {})
                        if info:
                            scene['summary'] = str(info.get('summary', scene['summary']))
                            scene['location_detail'] = str(info.get('location', scene.get('location', '')))
                            scene['time_of_day'] = str(info.get('time_of_day', scene['time_of_day']))
                            scene['tone'] = str(info.get('tone', "Neutral"))
                            scene['characters'] = sanitize_list(info.get('characters') or scene['characters'])
                            scene['character_count'] = len(scene['characters'])
                            scene['extras'] = sanitize_list(info.get('extras', []))
                            scene['props'] = sanitize_list(info.get('props', []))
                            scene['vehicles'] = sanitize_list(info.get('vehicles', []))
                            scene['animals'] = sanitize_list(info.get('animals', []))
                            scene['wardrobe'] = str(info.get('wardrobe', 'Standard'))
                            scene['stunts'] = bool(info.get('stunts', False))
                            scene['vfx'] = bool(info.get('vfx', False))
                            scene['environment'] = sanitize_list(info.get('environment', []))

                            # shooting_type / location_permit — from LLM or auto-detected
                            shoot_info = detect_shooting_type(scene.get('heading', ''), scene['location_detail'])
                            llm_shoot = str(info.get('shooting_type', '')).upper()
                            scene['shooting_type'] = llm_shoot if llm_shoot else shoot_info['shooting_type']
                            llm_permit = info.get('location_permit')
                            scene['location_permit'] = bool(llm_permit) if llm_permit is not None else shoot_info['location_permit']

                            new_bts = info.get('bts_requirements', {})
                            if isinstance(new_bts, dict):
                                extras_count = new_bts.get('extras_required', 0)
                                if extras_count == 0 and scene['extras']:
                                    extras_count = len(scene['extras'])
                                if extras_count == 0:
                                    extras_count = shoot_info['extras_estimate']
                                scene['bts_requirements'] = {
                                    "actors_required": new_bts.get('actors_required', len(scene['characters'])),
                                    "extras_required": extras_count,
                                    "props_department": sanitize_list(new_bts.get('props_department', [])),
                                    "location_requirements": str(new_bts.get('location_requirements', "Standard")),
                                    "lighting_requirements": str(new_bts.get('lighting_requirements', "Standard")),
                                    "sound_requirements": str(new_bts.get('sound_requirements', "Sync")),
                                    "camera_suggestions": str(new_bts.get('camera_suggestions', "Standard setup")),
                                    "safety_concerns": sanitize_list(new_bts.get('safety_concerns', []))
                                }
                        else:
                            logger.warning(f"Scene {scene['scene_number']} missing from LLM response — using regex fallback")
                            fallback_enrich_scene(scene)

                except Exception as json_err:
                    logger.error(f"JSON Parse Error: {json_err}")
                    for scene in batch:
                        fallback_enrich_scene(scene)
            else:
                logger.warning("No valid JSON found in LLM response — using regex fallback for batch")
                for scene in batch:
                    fallback_enrich_scene(scene)

            return batch
        except Exception as e:
            logger.error(f"LLM Batch Error: {e} — falling back to regex enrichment")
            agent_used_tracker.append("regex-fallback")
            for scene in batch:
                fallback_enrich_scene(scene)
            return batch

    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(process_batch, batches))
    
    final_scenes = []
    for res in results: final_scenes.extend(res)
    agent = agent_used_tracker[-1] if agent_used_tracker else "regex-only"
    return final_scenes, agent


# #########################################
# Main Entry Point
# #########################################

def analyze_script(file_bytes: bytes, router) -> Dict[str, Any]:
    """Full pipeline: PDF to Results."""
    logger.info("Step 1: Extracting text from PDF...")
    full_text = extract_text_from_pdf(file_bytes)

    logger.info("Step 2: Splitting into scenes...")
    scenes = split_into_scenes(full_text, router=router)

    if not scenes:
        return {"error": "No scenes detected.", "scenes": [], "stats": {}}

    logger.info(f"Step 3: LLM enhancement for {len(scenes)} scenes...")
    enhanced_scenes, agent_used = enhance_scenes_with_llm(scenes, router)

    # Safety net: final cleanup pass before data reaches the frontend
    for s in enhanced_scenes:
        # If LLM never ran, apply regex fallback
        if s.get('summary', '').strip() in ('', 'Analyzing...'):
            logger.warning(f"Scene {s['scene_number']} still unprocessed — applying regex fallback")
            fallback_enrich_scene(s)

        # Clean characters: remove garbled encoding artifacts, numbers, dialogue, and placeholders
        raw_chars = s.get('characters', [])
        cleaned_chars = []
        for c in raw_chars:
            c = str(c).strip()
            # Strip common suffixes like (V.O.), (O.S.), (CONT'D)
            c = re.sub(r'\s*\(.*?\)', '', c).strip()
            if is_real_character_name(c):
                cleaned_chars.append(c)
        s['characters'] = cleaned_chars
        s['character_count'] = len(s['characters'])

        # Clean extras list too
        raw_extras = s.get('extras', [])
        s['extras'] = [e for e in raw_extras if is_real_character_name(str(e))]

        # Ensure all required fields exist
        s.setdefault('location_detail', s.get('location', 'Unknown'))
        s.setdefault('tone', 'Neutral')
        s.setdefault('wardrobe', 'Standard')
        s.setdefault('stunts', False)
        s.setdefault('vfx', False)
        s.setdefault('environment', [])
        s.setdefault('vehicles', [])
        s.setdefault('animals', [])
        s.setdefault('extras', [])

        # Clean summary: remove any garbled text leftover
        summary = s.get('summary', '')
        if _ratio_garbled(summary) > 0.3:
            # Keep only ASCII sentences
            good_sentences = [sent.strip() for sent in summary.split('.') if _ratio_garbled(sent) <= 0.2 and sent.strip()]
            s['summary'] = '. '.join(good_sentences) + ('.' if good_sentences else '')
            if not s['summary'].strip():
                s['summary'] = f"Scene at {s.get('location_detail', 'Unknown')} during {s.get('time_of_day', 'DAY')}."

        bts = s.get('bts_requirements', {})
        if not isinstance(bts, dict) or not bts.get('lighting_requirements'):
            s['bts_requirements'] = {
                "actors_required": len(s['characters']),
                "extras_required": len(s['extras']),
                "props_department": s.get('props', []),
                "location_requirements": "Standard location setup",
                "lighting_requirements": "Natural + fill lights",
                "sound_requirements": "Sync sound recording",
                "camera_suggestions": "Standard 3-point coverage",
                "safety_concerns": ["Standard set safety protocols"]
            }

    all_characters = set()
    locations = set()
    day_count, night_count = 0, 0
    total_props, total_vehicles, total_animals = 0, 0, 0
    stunt_scenes, vfx_scenes = 0, 0

    for s in enhanced_scenes:
        for c in s.get('characters', []): all_characters.add(str(c))
        locations.add(str(s.get('location_detail', s.get('location', 'Unknown'))))

        tod = str(s.get('time_of_day', '')).upper()
        if 'NIGHT' in tod or 'MIDNIGHT' in tod: night_count += 1
        else: day_count += 1

        total_props += len(s.get('props', []))
        total_vehicles += len(s.get('vehicles', []))
        total_animals += len(s.get('animals', []))
        if s.get('stunts'): stunt_scenes += 1
        if s.get('vfx'): vfx_scenes += 1
        s.pop('raw_text', None)

    return {
        "scenes": enhanced_scenes,
        "agent_used": agent_used,
        "stats": {
            "total_scenes": len(enhanced_scenes),
            "total_characters": len(all_characters),
            "locations": len(locations),
            "day_scenes": day_count,
            "night_scenes": night_count,
            "props_count": total_props,
            "vehicles": total_vehicles,
            "animals": total_animals,
            "stunts": stunt_scenes,
            "vfx_scenes": vfx_scenes
        }
    }
