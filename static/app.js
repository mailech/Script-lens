// ═══════════════════════════════════════════════════════════
//  ScriptLens — Frontend JS
// ═══════════════════════════════════════════════════════════

const API_BASE = '';  // Same origin (FastAPI serves this)

let selectedFile = null;
let analysisData = null;
let allScenes = [];
const sceneImageCache = {}; // scene_number -> 'loading' | 'done' | 'error'

// ─────────────────────────────────────────
//  INIT
// ─────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    refreshAgentStatus();
});


// ─────────────────────────────────────────
//  TOAST NOTIFICATIONS
// ─────────────────────────────────────────

function showToast(message, type = 'info', duration = 4000) {
    const container = document.getElementById('toast-container');
    const icons = { success: '✅', error: '❌', info: 'ℹ️' };
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `<span>${icons[type] || 'ℹ️'}</span><span>${message}</span>`;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.animation = 'toastIn 0.3s ease reverse';
        setTimeout(() => toast.remove(), 300);
    }, duration);
}


// ─────────────────────────────────────────
//  API KEY TESTING
// ─────────────────────────────────────────

async function testKey(provider, inputId, statusId) {
    const input = document.getElementById(inputId);
    const statusEl = document.getElementById(statusId);
    const btn = document.getElementById(`test-${provider === 'google' ? 'gemini' : provider}`);

    const key = input.value.trim();
    if (!key) {
        setStatus(statusEl, 'error', '⚠ Please enter an API key first');
        return;
    }

    // Loading state
    btn.disabled = true;
    btn.textContent = '...';
    setStatus(statusEl, 'testing', '⏳ Testing connection...');

    try {
        const res = await fetch(`${API_BASE}/api/test-key`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ provider, api_key: key })
        });
        const data = await res.json();

        if (data.success) {
            setStatus(statusEl, 'success', `✓ ${data.message}`);
            showToast(`${getProviderName(provider)} key is valid!`, 'success');
        } else {
            setStatus(statusEl, 'error', `✗ ${data.message}`);
            showToast(`${getProviderName(provider)} key failed: ${data.message}`, 'error');
        }
    } catch (e) {
        setStatus(statusEl, 'error', `✗ Request failed: ${e.message}`);
    } finally {
        btn.disabled = false;
        btn.textContent = 'Test';
    }
}

function setStatus(el, type, msg) {
    el.className = `key-status ${type}`;
    el.textContent = msg;
}

function getProviderName(p) {
    return { google: 'Gemini', groq: 'Groq', openai: 'OpenAI', anthropic: 'Claude', replicate: 'Replicate', sarvam: 'Sarvam AI' }[p] || p;
}


// ─────────────────────────────────────────
//  SAVE KEYS
// ─────────────────────────────────────────

async function saveKeys() {
    const keys = {
        gemini: document.getElementById('gemini-key').value.trim() || undefined,
        groq: document.getElementById('groq-key').value.trim() || undefined,
        openai: document.getElementById('openai-key').value.trim() || undefined,
        anthropic: document.getElementById('claude-key').value.trim() || undefined,
        replicate: document.getElementById('replicate-key').value.trim() || undefined,
        sarvam: document.getElementById('sarvam-key').value.trim() || undefined,
    };

    if (!keys.gemini && !keys.groq && !keys.openai && !keys.anthropic && !keys.replicate && !keys.sarvam) {
        showToast('Please enter at least one API key before saving.', 'error');
        return;
    }

    try {
        const res = await fetch(`${API_BASE}/api/save-keys`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(keys)
        });
        const data = await res.json();
        if (data.success) {
            showToast('API keys saved successfully! ✨', 'success');
            await refreshAgentStatus();
        } else {
            showToast('Failed to save keys.', 'error');
        }
    } catch (e) {
        showToast(`Error saving keys: ${e.message}`, 'error');
    }
}


// ─────────────────────────────────────────
//  AGENT STATUS
// ─────────────────────────────────────────

async function refreshAgentStatus() {
    const btn = document.getElementById('refresh-agents-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Refreshing...'; }

    try {
        const res = await fetch(`${API_BASE}/api/agent-status`);
        const data = await res.json();
        updateAgentDots(data.agents);
        updateHeaderStatus(data.agents);
    } catch (e) {
        // Server might not be running yet or key not saved
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = '🔄 Refresh Status'; }
    }
}

function updateAgentDots(agents) {
    const dotMap = { google: 'dot-gemini', groq: 'dot-groq', openai: 'dot-openai', anthropic: 'dot-claude', replicate: 'dot-replicate', sarvam: 'dot-sarvam' };
    agents.forEach(agent => {
        const dot = document.getElementById(dotMap[agent.provider]);
        if (dot) {
            dot.className = `agent-dot ${agent.configured ? 'active' : 'inactive'}`;
        }
    });
}

function updateHeaderStatus(agents) {
    const configured = agents.filter(a => a.configured).length;
    const dot = document.getElementById('api-status-dot');
    const text = document.getElementById('api-status-text');

    if (configured === 0) {
        dot.style.background = 'var(--accent-red)';
        dot.style.boxShadow = '0 0 6px var(--accent-red)';
        text.textContent = 'No agents configured';
    } else if (configured === 1) {
        dot.style.background = 'var(--accent-orange)';
        dot.style.boxShadow = '0 0 6px var(--accent-orange)';
        text.textContent = `${configured} agent active`;
    } else {
        dot.style.background = 'var(--accent-green)';
        dot.style.boxShadow = '0 0 6px var(--accent-green)';
        text.textContent = `${configured} agents active`;
    }
}


// ─────────────────────────────────────────
//  FILE UPLOAD HANDLING
// ─────────────────────────────────────────

function handleDragOver(event) {
    event.preventDefault();
    document.getElementById('upload-zone').classList.add('drag-over');
}

function handleDragLeave(event) {
    document.getElementById('upload-zone').classList.remove('drag-over');
}

function handleDrop(event) {
    event.preventDefault();
    document.getElementById('upload-zone').classList.remove('drag-over');
    const files = event.dataTransfer.files;
    if (files.length > 0) processFile(files[0]);
}

function handleFileSelect(event) {
    const file = event.target.files[0];
    if (file) processFile(file);
}

function processFile(file) {
    if (!file.name.toLowerCase().endsWith('.pdf')) {
        showToast('Please upload a PDF file!', 'error');
        return;
    }
    if (file.size > 50 * 1024 * 1024) {
        showToast('File too large! Maximum 50MB allowed.', 'error');
        return;
    }

    selectedFile = file;
    const sizeStr = file.size > 1024 * 1024
        ? `${(file.size / (1024 * 1024)).toFixed(2)} MB`
        : `${(file.size / 1024).toFixed(1)} KB`;

    document.getElementById('file-name-text').textContent = file.name;
    document.getElementById('file-size-text').textContent = sizeStr;
    document.getElementById('file-info').classList.add('visible');
    document.getElementById('analyze-btn').disabled = false;
    showToast(`"${file.name}" selected`, 'success', 2500);
}

function removeFile() {
    selectedFile = null;
    document.getElementById('file-input').value = '';
    document.getElementById('file-info').classList.remove('visible');
    document.getElementById('analyze-btn').disabled = true;
}


// ─────────────────────────────────────────
//  ANALYZE SCREENPLAY
// ─────────────────────────────────────────

async function analyzeScript() {
    if (!selectedFile) { showToast('Please select a PDF file first!', 'error'); return; }

    // Check at least one key is saved
    const btn = document.getElementById('analyze-btn');
    // UI: loading state
    btn.disabled = true;
    document.getElementById('analyze-btn-icon').textContent = '';
    document.getElementById('analyze-btn-text').textContent = 'Analyzing...';
    const spinner = document.createElement('div');
    spinner.className = 'spinner';
    spinner.id = 'analyze-spinner';
    btn.prepend(spinner);

    const progressSection = document.getElementById('progress-section');
    const pctText = document.getElementById('progress-pct');
    const stepperSteps = ['step-1', 'step-2', 'step-3', 'step-4', 'step-5', 'step-6', 'step-7', 'step-8', 'step-9', 'step-10'];

    // Reset steps
    stepperSteps.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.className = 'step-item';
    });
    progressSection.classList.add('visible');

    const updateProgress = (stepIdx) => {
        if (stepIdx >= stepperSteps.length) return;
        for (let i = 0; i < stepIdx; i++) {
            const prev = document.getElementById(stepperSteps[i]);
            if (prev) prev.className = 'step-item completed';
        }
        const curr = document.getElementById(stepperSteps[stepIdx]);
        if (curr) curr.className = 'step-item active';
        pctText.textContent = `${Math.round(((stepIdx + 1) / stepperSteps.length) * 100)}%`;
    };

    let simulatedIdx = 0;
    const progressInterval = setInterval(() => {
        if (simulatedIdx < 9) updateProgress(simulatedIdx++);
    }, 2800);

    const formData = new FormData();
    formData.append('file', selectedFile);

    try {
        const res = await fetch(`${API_BASE}/api/analyze-script`, {
            method: 'POST',
            body: formData
        });

        clearInterval(progressInterval);
        updateProgress(9);

        if (!res.ok) {
            const errData = await res.json().catch(() => ({ detail: res.statusText }));
            throw new Error(errData.detail || `HTTP ${res.status}`);
        }

        const data = await res.json();
        analysisData = data;
        allScenes = data.scenes || [];

        // 1. Render Dashboard Metrics
        const stats = data.stats || {};
        document.getElementById('stat-scenes').textContent = stats.total_scenes || allScenes.length;
        document.getElementById('stat-cast').textContent = stats.total_characters || 0;
        document.getElementById('stat-locations').textContent = stats.locations || 0;
        document.getElementById('stat-props').textContent = stats.props_count || 0;
        document.getElementById('stat-vehicles').textContent = stats.vehicles || 0;
        document.getElementById('stat-stunts').textContent = stats.stunt_scenes || 0;
        document.getElementById('stat-vfx').textContent = stats.vfx_scenes || 0;
        document.getElementById('stat-extras').textContent = stats.extras_required_total || 0;

        // 2. Clear and Render Results
        document.getElementById('results-content').style.display = 'block';
        document.getElementById('placeholder-state').style.display = 'none';
        document.getElementById('agent-used-name').textContent = data.agent_used || 'Hybrid Parser';

        renderResults(data);

        // 3. Initialize Dept Hub
        switchDept('PROPS');

        showToast(`✨ Analysis complete! ${allScenes.length} scenes found.`, 'success', 5000);

        setTimeout(() => {
            progressSection.classList.remove('visible');
            document.getElementById('results-dashboard')?.scrollIntoView({ behavior: 'smooth' });
        }, 2000);

    } catch (err) {
        clearInterval(progressInterval);
        showToast(`Analysis failed: ${err.message}`, 'error', 6000);
        console.error('Analysis failed:', err);
    } finally {
        btn.disabled = false;
        document.getElementById('analyze-btn-icon').textContent = '🎬';
        document.getElementById('analyze-btn-text').textContent = 'Analyze Screenplay';
        const sp = document.getElementById('analyze-spinner');
        if (sp) sp.remove();
    }
}


// ─────────────────────────────────────────
//  RENDER RESULTS
// ─────────────────────────────────────────

function renderResults(data) {
    document.getElementById('placeholder-state').style.display = 'none';
    document.getElementById('results-content').style.display = 'block';

    // Agent used badge
    document.getElementById('agent-used-name').textContent = data.agent_used || 'Unknown';

    // Stats
    const stats = data.stats || {};
    renderStats(stats);

    // Scenes
    renderSceneList(allScenes);
}

function renderStats(stats) {
    const ids = {
        'stat-scenes': stats.total_scenes || allScenes.length || 0,
        'stat-cast': stats.total_characters || 0,
        'stat-locations': stats.locations || stats.unique_locations || 0,
        'stat-props': stats.props_count || 0,
        'stat-vehicles': stats.vehicles || 0,
        'stat-stunts': stats.stunt_scenes || 0,
        'stat-vfx': stats.vfx_scenes || 0,
        'stat-extras': stats.extras_required_total || 0
    };

    for (const [id, val] of Object.entries(ids)) {
        const el = document.getElementById(id);
        if (el) {
            el.textContent = val;
            // Add pulse effect on update
            el.classList.add('pulse');
            setTimeout(() => el.classList.remove('pulse'), 500);
        }
    }
}

function renderSceneList(scenes) {
    const list = document.getElementById('scenes-list');
    const countEl = document.getElementById('scene-count-shown');
    countEl.textContent = scenes.length;

    if (scenes.length === 0) {
        list.innerHTML = `<div style="text-align:center; padding:40px; color: var(--text-muted);">No scenes match your filters.</div>`;
        return;
    }

    list.innerHTML = scenes.map(scene => buildSceneCard(scene)).join('');
}

function buildSceneCard(scene) {
    const s = scene;
    const tod = (s.time_of_day || '').toUpperCase();
    const intExt = (s.int_ext || '').replace('-', '/');
    const todTag = getTimeTag(tod);
    const chars = s.characters || [];
    const location = s.location_detail || s.location || '—';
    const bts = s.bts_requirements || {};

    // Client-side garbled text detector
    function isGarbled(str) {
        if (!str) return false;
        const alpha = [...str].filter(c => /[a-zA-Z\u00C0-\u024F]/.test(c));
        if (!alpha.length) return false;
        return alpha.filter(c => c.charCodeAt(0) >= 0x00C0 && c.charCodeAt(0) <= 0x024F).length / alpha.length > 0.35;
    }

    const cleanChars = chars.filter(c => {
        if (!c || !c.trim() || c.length < 2) return false;
        const trimmed = c.trim().toUpperCase();
        if (/^[\d\s.:,\-]+$/.test(trimmed)) return false;
        const boilerplate = new Set(['N/A', 'NA', 'NONE', 'NULL', 'SCENE', 'CUT', 'FADE', 'INT', 'EXT', 'DAY', 'NIGHT', 'CAMERA', 'COLLEGE']);
        if (boilerplate.has(trimmed)) return false;
        return !isGarbled(c);
    });

    const charDisplay = cleanChars.map(name => {
        const isNonLatin = /[^\x00-\x7F]/.test(name);
        const style = isNonLatin ? 'font-family:"Noto Sans",sans-serif;font-size:12px;' : '';
        return `<span class="char-chip" style="${style}">${escapeHtml(name)}</span>`;
    }).join('');

    const summary = isGarbled(s.summary || '')
        ? (s.summary || '').replace(/[^\x00-\x7F\s.,!?'"()\-:]/g, '')
        : (s.summary || '');

    // Hollywood Breakdown Mapping
    const hb = s.hollywood_breakdown || {};
    const DEPT_MAP = {
        "Cast": hb.cast, "Extras": hb.extras, "Stunts": hb.stunts,
        "Props": hb.props, "Wardrobe": hb.wardrobe, "Makeup": hb.makeup,
        "Vehicles": hb.vehicles, "Animals": hb.animals, "SFX": hb.special_effects_sfx,
        "VFX": hb.visual_effects_vfx, "Permits": hb.permits_legal, "Safety": hb.safety_requirements
    };

    const renderDepts = Object.entries(DEPT_MAP)
        .filter(([_, val]) => val && (Array.isArray(val) ? val.length > 0 : !!val))
        .map(([key, val]) => `
            <div class="prod-field mt-1" style="display:flex; gap:8px;">
                <span class="field-label" style="font-size:10px; min-width:65px; color:var(--accent-gold); opacity:0.8;">${key}:</span>
                <span class="field-val" style="font-size:10px; line-height:1.3;">${Array.isArray(val) ? val.join(', ') : val}</span>
            </div>
        `).join('');

    return `
    <div class="scene-card" id="scene-card-${s.scene_number}" onclick="toggleScene(${s.scene_number})">
      <!-- Cinematic Scene Image -->
      <div class="scene-img-panel" id="scene-img-${s.scene_number}" style="display:none;"></div>
      <div class="scene-header">
        <div class="scene-num">${escapeHtml(s.script_scene_number || s.scene_number)}</div>
        <div class="scene-main">
          <div class="scene-heading-text">${escapeHtml(s.heading)}</div>
          <div class="scene-meta">
            <span class="scene-tag ${todTag}">${getTimeIcon(tod)} ${tod || '—'}</span>
            <span class="scene-tag ${intExt.startsWith('INT') ? 'tag-int' : 'tag-ext'}">📍 ${escapeHtml(location)}</span>
            ${s.location_permit ? `<span class="scene-tag" style="background:rgba(239,68,68,0.1); color:#ef4444; border:1px solid rgba(239,68,68,0.2);">🚨 PERMIT</span>` : ''}
          </div>
        </div>
        <div class="scene-chevron">▾</div>
      </div>
      <div class="scene-body">
        <div class="scene-body-grid">
          <div class="scene-body-section main-info">
            <div class="scene-body-label">Director's Analysis</div>
            <div class="summary-text">${escapeHtml(summary || 'Analyzing scene context...')}</div>
            <div class="mt-3">
                <div class="scene-body-label">On-Set Cast</div>
                <div class="char-chips">${charDisplay || 'Main cast required.'}</div>
            </div>
          </div>
          <div class="scene-body-section production-info">
            <div class="scene-body-label">Hollywood Breakdown</div>
            <div class="prod-breakdown-card">
                ${renderDepts || '<div class="none">Standard departmental requirements.</div>'}
                <div class="mt-2 pt-2 border-top" style="border-color:rgba(255,255,255,0.05) !important;">
                    <div class="prod-logistics-grid">
                        <div class="log-item">
                            <span class="field-label" style="font-size:9px;">CAM:</span>
                            <div class="field-val" style="font-size:9px;">${escapeHtml(bts.camera_suggestions || 'Static')}</div>
                        </div>
                        <div class="log-item">
                            <span class="field-label" style="font-size:9px;">LIGHT:</span>
                            <div class="field-val" style="font-size:9px;">${escapeHtml(bts.lighting_requirements || 'Standard')}</div>
                        </div>
                    </div>
                </div>
            </div>
          </div>
        </div>
        
        <!-- Crafts Explorer -->
        <div class="crafts-explorer mt-3">
            <div class="scene-body-label" style="text-align:center; font-size:14px; margin-bottom:15px; color:var(--accent-gold);">
                <i class="fas fa-clapperboard"></i> Full 24-Crafts Analysis
            </div>
            ${renderCraftsSection(s, 'pre_production', 'Pre-Production', 'fa-pencil-ruler')}
            ${renderCraftsSection(s, 'production_on_set', 'Production', 'fa-video')}
            ${renderCraftsSection(s, 'post_production', 'Post-Production', 'fa-layer-group')}
        </div>
      </div>
    </div>`;
}

function renderCraftsSection(scene, phaseKey, title, phaseIcon) {
    const crafts = (scene.production_crafts && scene.production_crafts[phaseKey]) || {};

    // Mapping internal keys to display names and icons
    const craftMap = {
        // Pre-Production
        direction: { name: "1. Direction", icon: "fa-film" },
        script_writing: { name: "2. Script Writing", icon: "fa-pen-nib" },
        casting: { name: "3. Casting", icon: "fa-user-check" },

        // Production
        acting_junior_artists: { name: "4. Acting/Junior Artists", icon: "fa-people-group" },
        cinematography: { name: "5. Cinematography", icon: "fa-camera-movie" },
        technical_unit: { name: "6. Technical Unit", icon: "fa-tools" },
        outdoor_lightmen: { name: "7. Outdoor Lightmen", icon: "fa-lightbulb" },
        stunt_direction: { name: "8. Stunt Direction", icon: "fa-hand-fist" },
        choreography: { name: "9. Choreography", icon: "fa-child-reaching" },
        art_direction: { name: "10. Art Direction", icon: "fa-paint-roller" },
        makeup: { name: "11. Makeup", icon: "fa-magic" },
        costume_designing: { name: "12. Costume Designing", icon: "fa-shirt" },
        production_assistance: { name: "13. Production Assistance", icon: "fa-list-check" },
        production_executive: { name: "14. Production Executive", icon: "fa-briefcase" },
        studio_workers: { name: "15. Studio Workers", icon: "fa-hammer" },
        production_women: { name: "16. Production Women", icon: "fa-person-dress" },
        still_photography: { name: "17. Still Photography", icon: "fa-camera" },
        junior_artist_agent: { name: "18. Junior Artist Agent", icon: "fa-address-book" },
        cinema_drivers: { name: "19. Cinema Drivers", icon: "fa-bus" },

        // Post
        editing: { name: "20. Editing", icon: "fa-scissors" },
        audiography_sound: { name: "21. Audiography/Sound", icon: "fa-microphone-lines" },
        music: { name: "22. Music", icon: "fa-music" },
        dubbing_artist: { name: "23. Dubbing Artist", icon: "fa-comment-dots" },
        publicity_designing: { name: "24. Publicity Designing", icon: "fa-bullhorn" }
    };

    const cards = Object.keys(crafts).map(key => {
        const info = craftMap[key] || { name: key.replace(/_/g, ' '), icon: "fa-cube" };
        const content = crafts[key];
        return `
            <div class="craft-card">
                <div class="craft-header">
                    <div class="craft-icon"><i class="fas ${info.icon}"></i></div>
                    <div class="craft-name">${info.name}</div>
                </div>
                <div class="craft-content">
                    ${content ? escapeHtml(content) : '<span class="craft-empty">No specific requirements mentioned in text.</span>'}
                </div>
            </div>
        `;
    }).join('');

    if (!cards) return '';

    return `
        <div class="craft-phase-section">
            <div class="craft-phase-title">
                <i class="fas ${phaseIcon}"></i> ${title}
            </div>
            <div class="craft-grid">
                ${cards}
            </div>
        </div>
    `;
}

function toggleScene(sceneNum) {
    const card = document.getElementById(`scene-card-${sceneNum}`);
    if (!card) return;
    const wasExpanded = card.classList.contains('expanded');
    card.classList.toggle('expanded');
    // Lazy-generate the scene image on first expand
    if (!wasExpanded && !sceneImageCache[sceneNum]) {
        const scene = allScenes.find(s => s.scene_number === sceneNum);
        if (scene) generateSceneImage(scene);
    }
}

async function generateSceneImage(scene) {
    const sceneNum = scene.scene_number;
    if (sceneImageCache[sceneNum]) return; // already loading or done
    sceneImageCache[sceneNum] = 'loading';

    const imgContainer = document.getElementById(`scene-img-${sceneNum}`);
    if (!imgContainer) return;

    // Show skeleton loader
    imgContainer.innerHTML = `
        <div class="scene-img-loader">
            <div class="scene-img-spinner"></div>
            <span>Generating cinematic image...</span>
        </div>`;
    imgContainer.style.display = 'block';

    try {
        const res = await fetch(`${API_BASE}/api/generate-scene-image`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                scene_number: sceneNum,
                heading: scene.heading || '',
                time_of_day: scene.time_of_day || 'DAY',
                int_ext: scene.int_ext || 'EXT',
                location: scene.location_detail || scene.location || '',
                tone: scene.tone || 'Neutral',
                genre: scene.genre || 'Drama',
                characters: (scene.characters || []).slice(0, 4),
                summary: scene.summary || ''
            })
        });

        const data = await res.json();
        if (data.success && data.image_data) {
            sceneImageCache[sceneNum] = 'done';
            imgContainer.innerHTML = `
                <div class="scene-img-wrapper">
                    <div class="scene-img-badge">🎬 AI Scene Visual · ${data.provider || 'AI'}</div>
                    <img
                        src="${data.image_data}"
                        alt="Scene ${sceneNum} visual"
                        class="scene-generated-img"
                        loading="lazy"
                        onclick="openImageLightbox('${data.image_data}', 'Scene ${sceneNum} — ${escapeHtml(scene.heading || '')}')"
                    />
                    <div class="scene-img-caption">${escapeHtml(scene.heading || '')} · ${scene.time_of_day || 'DAY'}</div>
                </div>`;
        } else {
            throw new Error(data.error || 'Image generation failed');
        }
    } catch (err) {
        sceneImageCache[sceneNum] = 'error';
        imgContainer.innerHTML = `
            <div class="scene-img-error">
                <span>🎞️</span>
                <p>Could not generate image</p>
                <small>${err.message}</small>
                <button onclick="delete sceneImageCache[${sceneNum}]; generateSceneImage(allScenes.find(s=>s.scene_number===${sceneNum}))">Retry</button>
            </div>`;
    }
}

async function generateAllImages() {
    if (!allScenes.length) { showToast('Analyze a script first!', 'error'); return; }

    const btn = document.getElementById('gen-all-images-btn');
    const originalText = btn.textContent;
    btn.disabled = true;

    const scenesToGen = allScenes.filter(s => !sceneImageCache[s.scene_number]);
    if (scenesToGen.length === 0) {
        showToast('All scene visuals are already generated! ✨', 'info');
        btn.disabled = false;
        return;
    }

    showToast(`Starting batch generation for ${scenesToGen.length} scenes...`, 'info');

    // Simple concurrency limiter (max 3 at a time)
    const limit = 3;
    let running = 0;
    let index = 0;
    let completed = 0;

    const processNext = async () => {
        if (index >= scenesToGen.length) return;

        const scene = scenesToGen[index++];
        running++;

        btn.textContent = `⏳ Generating (${Math.round((completed / scenesToGen.length) * 100)}%)`;

        try {
            await generateSceneImage(scene);
        } catch (e) {
            console.error(`Batch gen failed for scene ${scene.scene_number}`, e);
        } finally {
            running--;
            completed++;
            btn.textContent = `⏳ Generating (${Math.round((completed / scenesToGen.length) * 100)}%)`;
            await processNext();
        }
    };

    const starters = [];
    for (let i = 0; i < Math.min(limit, scenesToGen.length); i++) {
        starters.push(processNext());
    }

    await Promise.all(starters);

    btn.disabled = false;
    btn.textContent = originalText;
    showToast('Batch generation complete! 🎬', 'success');
}

function openImageLightbox(src, caption) {
    const lb = document.createElement('div');
    lb.id = 'img-lightbox';
    lb.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.92);z-index:9999;display:flex;flex-direction:column;align-items:center;justify-content:center;cursor:zoom-out;';
    lb.innerHTML = `
        <div style="position:absolute;top:20px;right:24px;font-size:28px;color:white;cursor:pointer;" onclick="this.parentElement.remove()">✕</div>
        <img src="${src}" style="max-width:90vw;max-height:80vh;border-radius:12px;box-shadow:0 0 60px rgba(0,0,0,0.8);" />
        <div style="color:rgba(255,255,255,0.7);margin-top:16px;font-size:13px;font-family:inherit;">${caption}</div>`;
    lb.addEventListener('click', e => { if (e.target === lb) lb.remove(); });
    document.body.appendChild(lb);
}

function getTimeTag(tod) {
    if (tod.includes('NIGHT') || tod.includes('MIDNIGHT')) return 'tag-night';
    if (tod.includes('DAWN') || tod.includes('SUNRISE')) return 'tag-dawn';
    if (tod.includes('DUSK') || tod.includes('SUNSET') || tod.includes('MAGIC HOUR')) return 'tag-dusk';
    if (tod.includes('DAY') || tod.includes('MORNING') || tod.includes('AFTERNOON') || tod.includes('NOON')) return 'tag-day';
    return 'tag-other';
}

function getTimeIcon(tod) {
    if (tod.includes('NIGHT') || tod.includes('MIDNIGHT')) return '🌙';
    if (tod.includes('DAWN') || tod.includes('SUNRISE')) return '🌅';
    if (tod.includes('DUSK') || tod.includes('SUNSET')) return '🌆';
    if (tod.includes('MORNING')) return '🌄';
    if (tod.includes('AFTERNOON')) return '☀️';
    if (tod.includes('EVENING')) return '🌇';
    if (tod.includes('DAY')) return '☀️';
    if (tod.includes('CONTINUOUS')) return '↩️';
    return '🕐';
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}


// ─────────────────────────────────────────
//  FILTERING
// ─────────────────────────────────────────

function filterScenes() {
    if (!allScenes.length) return;

    const search = document.getElementById('search-input').value.toLowerCase().trim();
    const timeFilter = document.getElementById('time-filter').value;
    const intExtFilter = document.getElementById('intext-filter').value;

    let filtered = allScenes.filter(scene => {
        // Time filter
        if (timeFilter !== 'all') {
            const tod = (scene.time_of_day || '').toUpperCase();
            if (!tod.includes(timeFilter)) return false;
        }

        // INT/EXT filter
        if (intExtFilter !== 'all') {
            const ie = (scene.int_ext || '').toUpperCase();
            if (!ie.includes(intExtFilter)) return false;
        }

        // Search filter
        if (search) {
            const heading = (scene.heading || '').toLowerCase();
            const location = (scene.location_detail || scene.location || '').toLowerCase();
            const chars = (scene.characters || []).join(' ').toLowerCase();
            const summary = (scene.summary || '').toLowerCase();
            if (!heading.includes(search) && !location.includes(search) &&
                !chars.includes(search) && !summary.includes(search)) {
                return false;
            }
        }

        return true;
    });

    renderSceneList(filtered);
}


// ─────────────────────────────────────────
//  EXPORT
// ─────────────────────────────────────────

function exportJSON() {
    if (!analysisData) { showToast('No data to export yet!', 'error'); return; }
    const blob = new Blob([JSON.stringify(analysisData, null, 2)], { type: 'application/json' });
    downloadBlob(blob, 'screenplay_analysis.json');
    showToast('JSON exported!', 'success');
}

function exportCSV() {
    if (!allScenes.length) { showToast('No data to export yet!', 'error'); return; }
    const headers = ['Scene #', 'Heading', 'INT/EXT', 'Location', 'Time of Day', 'Character Count', 'Characters', 'Summary'];
    const rows = allScenes.map(s => [
        s.scene_number,
        `"${(s.heading || '').replace(/"/g, '""')}"`,
        s.int_ext || '',
        `"${(s.location_detail || s.location || '').replace(/"/g, '""')}"`,
        s.time_of_day || '',
        s.character_count || (s.characters || []).length,
        `"${(s.characters || []).join('; ').replace(/"/g, '""')}"`,
        `"${(s.summary || '').replace(/"/g, '""')}"`
    ]);
    const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    downloadBlob(blob, 'screenplay_analysis.csv');
    showToast('CSV exported!', 'success');
}

function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
}

/**
 * Department Sheet Logic
 */
function switchDept(dept) {
    // UI: Active tab state
    document.querySelectorAll('.dept-tab').forEach(btn => {
        const btnText = btn.textContent.trim().toUpperCase();
        btn.classList.toggle('active', btnText === dept.toUpperCase());
    });

    const container = document.getElementById('dept-sheet-content');
    if (!container) return;

    const sheets = analysisData?.department_sheets || {};
    const items = sheets[dept.toUpperCase()] || [];

    if (items.length === 0) {
        container.innerHTML = `<div style="text-align:center; padding: 40px; color: var(--text-muted);">No requirements found for ${dept} in this script.</div>`;
        return;
    }

    container.innerHTML = items.map(sheet => `
        <div class="dept-sheet-item">
            <div class="dept-sheet-header">${sheet.header}</div>
            <div class="dept-sheet-vals">
                ${Array.isArray(sheet.items) ? sheet.items.map(i => `• ${i}`).join('<br>') : (sheet.details || sheet.reqs || 'Requested')}
            </div>
        </div>
    `).join('');
}

// Initializing App
document.addEventListener('DOMContentLoaded', () => {
    refreshAgentStatus();
});
