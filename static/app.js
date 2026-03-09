// ═══════════════════════════════════════════════════════════
//  ScriptLens — Frontend JS
// ═══════════════════════════════════════════════════════════

const API_BASE = '';  // Same origin (FastAPI serves this)

let selectedFile = null;
let analysisData = null;
let allScenes = [];

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
    return { google: 'Gemini', groq: 'Groq', openai: 'OpenAI', anthropic: 'Claude' }[p] || p;
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
    };

    if (!keys.gemini && !keys.groq && !keys.openai && !keys.anthropic) {
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
    const dotMap = { google: 'dot-gemini', groq: 'dot-groq', openai: 'dot-openai', anthropic: 'dot-claude' };
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
    const progressSection = document.getElementById('progress-section');
    const progressLabel = document.getElementById('progress-label');

    // UI: loading state
    btn.disabled = true;
    document.getElementById('analyze-btn-icon').textContent = '';
    document.getElementById('analyze-btn-text').textContent = 'Analyzing...';
    const spinner = document.createElement('div');
    spinner.className = 'spinner';
    spinner.id = 'analyze-spinner';
    btn.prepend(spinner);
    progressSection.classList.add('visible');

    const steps = [
        'Extracting text from PDF...',
        'Detecting scene headings...',
        'Identifying locations...',
        'Mapping characters...',
        'Running multi-agent LLM enhancement...',
        'Generating scene summaries...',
        'Finalizing results...'
    ];

    let stepIdx = 0;
    const stepInterval = setInterval(() => {
        if (stepIdx < steps.length) {
            progressLabel.textContent = steps[stepIdx++];
        }
    }, 3000);

    const formData = new FormData();
    formData.append('file', selectedFile);

    try {
        const res = await fetch(`${API_BASE}/api/analyze-script`, {
            method: 'POST',
            body: formData
        });

        clearInterval(stepInterval);

        if (!res.ok) {
            const errData = await res.json().catch(() => ({ detail: res.statusText }));
            throw new Error(errData.detail || `HTTP ${res.status}`);
        }

        const data = await res.json();
        analysisData = data;
        allScenes = data.scenes || [];

        renderResults(data);
        showToast(`✨ Analysis complete! ${allScenes.length} scenes found.`, 'success', 5000);
        progressLabel.textContent = `✓ Analysis complete — ${allScenes.length} scenes detected`;

    } catch (err) {
        clearInterval(stepInterval);
        showToast(`Analysis failed: ${err.message}`, 'error', 6000);
        progressLabel.textContent = `✗ Failed: ${err.message}`;
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
    const grid = document.getElementById('stats-grid');
    grid.innerHTML = `
    <div class="stat-card gold">
      <div class="stat-value">${stats.total_scenes || 0}</div>
      <div class="stat-label">Total Scenes</div>
    </div>
    <div class="stat-card blue">
      <div class="stat-value">${stats.total_characters || 0}</div>
      <div class="stat-label">Characters</div>
    </div>
    <div class="stat-card green">
      <div class="stat-value">${stats.locations || stats.unique_locations || 0}</div>
      <div class="stat-label">Locations</div>
    </div>
    <div class="stat-card gold" style="border-bottom: 3px solid var(--accent);">
      <div class="stat-value">${stats.props_count || 0}</div>
      <div class="stat-label">Props</div>
    </div>
    <div class="stat-card" style="border-bottom: 3px solid #ffa500;">
      <div class="stat-value">${stats.vehicles || 0}</div>
      <div class="stat-label">Vehicles</div>
    </div>
    <div class="stat-card" style="border-bottom: 3px solid #22c55e;">
      <div class="stat-value">${stats.animals || 0}</div>
      <div class="stat-label">Animals</div>
    </div>
    <div class="stat-card" style="border-bottom: 3px solid #ef4444;">
      <div class="stat-value">${stats.stunts || 0}</div>
      <div class="stat-label">Stunt Scenes</div>
    </div>
    <div class="stat-card" style="border-bottom: 3px solid #3b82f6;">
      <div class="stat-value">${stats.vfx_scenes || 0}</div>
      <div class="stat-label">VFX Shots</div>
    </div>
  `;
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

    // Client-side garbled text detector (defense-in-depth)
    function isGarbled(str) {
        const alpha = [...str].filter(c => /[a-zA-Z\u00C0-\u024F]/.test(c));
        if (!alpha.length) return false;
        const garbled = alpha.filter(c => c.charCodeAt(0) >= 0x00C0 && c.charCodeAt(0) <= 0x024F);
        return garbled.length / alpha.length > 0.35;
    }

    // Non-name words that should NEVER appear as a character chip
    const NON_NAME_WORDS = new Set([
        'N/A', 'NA', 'NONE', 'NULL', '-', '—', 'SCENE', 'CUT', 'FADE', 'EXT', 'INT',
        'DAY', 'NIGHT', 'MORNING', 'EVENING', 'CAMERA', 'COLLEGE', 'STUDENTS', 'PEOPLE',
        'CROWD', 'CONTINUED', 'TRANSITION', 'LOOKING', 'GOING', 'DISSOLVE'
    ]);

    // Filter garbled, numeric, timecode, and non-name chars
    const cleanChars = chars.filter(c => {
        if (!c || !c.trim()) return false;
        const trimmed = c.trim();
        // Reject pure numbers or timecodes
        if (/^[\d\s.:,\-]+$/.test(trimmed)) return false;
        if (/^\d{2}[.:]\d{2}/.test(trimmed)) return false;
        // Reject very short strings (single char or number)
        if (trimmed.length < 2) return false;
        // Reject boilerplate words
        if (NON_NAME_WORDS.has(trimmed.toUpperCase())) return false;
        // Reject garbled text
        if (isGarbled(trimmed)) return false;
        return true;
    });

    // Smart chip renderer: handles non-Latin scripts via Noto fonts
    function makeCharChip(name) {
        const isNonLatin = /[^\x00-\x7F]/.test(name) && !isGarbled(name);
        const fontStyle = isNonLatin
            ? 'font-family:"Noto Sans Telugu","Noto Sans Devanagari","Noto Sans Tamil","Noto Sans",sans-serif;font-size:12px;'
            : '';
        return `<span class="char-chip" style="${fontStyle}" title="${escapeHtml(name)}">${escapeHtml(name)}</span>`;
    }

    const charChips = cleanChars.map(makeCharChip).join('');
    const charDisplay = cleanChars.length > 0 ? charChips : '<span style="color:var(--text-muted);font-size:13px;">Characters extracted by LLM</span>';

    // Clean summary text from garbled characters
    const rawSummary = s.summary || '';
    const summary = isGarbled(rawSummary)
        ? rawSummary.replace(/[^\x00-\x7F\u0C00-\u0C7F\u0900-\u097F\u0B80-\u0BFF\s.,!?'"()\-:]/g, '').trim() || `Scene at ${s.location_detail || s.location || 'unknown location'}.`
        : rawSummary;

    const location = s.location_detail || s.location || '—';

    // Professional Schematic Mapping
    const bts = s.bts_requirements || {};
    const formatVal = (v) => {
        if (Array.isArray(v)) return v.length > 0 ? v.join(', ') : 'None';
        if (typeof v === 'object' && v !== null) {
            try { return JSON.stringify(v); } catch (e) { return String(v); }
        }
        return v || 'None';
    };

    const props = Array.isArray(s.props) ? s.props : [];
    const vehicles = Array.isArray(s.vehicles) ? s.vehicles : [];
    const animals = Array.isArray(s.animals) ? s.animals : [];
    const env = Array.isArray(s.environment) ? s.environment : [];

    return `
    <div class="scene-card" id="scene-card-${s.scene_number}" onclick="toggleScene(${s.scene_number})">
      <div class="scene-header">
        <div class="scene-num">${escapeHtml(s.script_scene_number || s.scene_number)}</div>
        <div class="scene-main">
          <div class="scene-heading-text" title="${escapeHtml(s.heading || '')}">
            ${escapeHtml(s.heading)}
          </div>
          <div class="scene-meta">
            <span class="scene-tag ${todTag}">
              ${getTimeIcon(tod)} ${tod || '—'}
            </span>
            <span class="scene-tag ${intExt.startsWith('INT') ? 'tag-int' : 'tag-ext'}">
              📍 ${escapeHtml(location)}
            </span>
            <span class="scene-tag tag-chars">
              👥 ${s.character_count || chars.length || 0} chars
            </span>
            <span class="scene-tag" style="background:rgba(168,85,247,0.1); color:#a855f7;">
              🎭 ${escapeHtml(s.tone || 'Neutral Tone')}
            </span>
            ${s.location_permit ? `
            <span class="scene-tag" style="background:rgba(239,68,68,0.15); color:#ef4444; border:1px solid rgba(239,68,68,0.35); font-weight:600;">
              🚨 PUBLIC LOCATION — PERMIT NEEDED
            </span>` : (s.shooting_type && s.shooting_type !== 'INTERIOR' ? `
            <span class="scene-tag" style="background:rgba(16,185,129,0.1); color:#10b981;">
              🎬 ${escapeHtml(s.shooting_type)}
            </span>` : '')}
          </div>
        </div>
        <div class="scene-chevron">▾</div>
      </div>
      <div class="scene-body">
        <div class="scene-body-grid">
          <div class="scene-body-section main-info">
            <div class="scene-body-label">Director's Analysis</div>
            <div class="summary-text">${escapeHtml(summary)}</div>
            
            <div class="mt-3">
                <div class="scene-body-label">Characters & Environment</div>
                <div class="char-chips">${charDisplay}</div>
                <div class="mt-2">
                    <span class="field-label">🌍 Environment:</span>
                    <span class="field-val">${formatVal(env)}</span>
                </div>
            </div>

                <div class="mt-3">
                    <div class="scene-body-label">Wardrobe &amp; Extra Talent</div>
                    <div class="prod-field">
                        <span class="field-label"><i class="fas fa-tshirt"></i> Wardrobe:</span>
                        <div class="field-val" style="color:#a855f7; font-weight:500;">${escapeHtml(s.wardrobe || 'Standard')}</div>
                    </div>
                    <div class="prod-field mt-1">
                        <span class="field-label"><i class="fas fa-users"></i> Actors Needed:</span>
                        <div class="field-val">
                          <strong>${bts.actors_required || chars.length}</strong> named actors
                          &nbsp;|&nbsp;
                          <strong style="color:${(bts.extras_required || 0) > 0 ? '#f59e0b' : 'var(--text-muted)'}">
                            ${bts.extras_required || 0}
                          </strong> extras
                        </div>
                    </div>
                    ${(s.extras && s.extras.length > 0) ? `
                    <div class="prod-field mt-1">
                        <span class="field-label" style="margin-bottom:4px;">🎭 Background Roles:</span>
                        <div class="char-chips" style="margin-top:4px;">
                          ${s.extras.map(e => `<span class="char-chip" style="background:rgba(245,158,11,0.15);color:#f59e0b;border-color:rgba(245,158,11,0.3);">${escapeHtml(e)}</span>`).join('')}
                        </div>
                    </div>` : ''}
                </div>
          </div>
          
          <div class="scene-body-section production-info">
            <div class="scene-body-label">BTS & Department Logistics</div>
            <div class="prod-breakdown-card">
                <div class="prod-field">
                    <span class="field-label"><i class="fas fa-box"></i> Physical Props:</span>
                    <div class="prop-tags">
                        ${props.map(p => `<span class="prop-tag">${escapeHtml(p)}</span>`).join('') || '<span class="none">None</span>'}
                    </div>
                </div>
                ${vehicles.length > 0 || animals.length > 0 ? `
                <div class="prod-field mt-2">
                    <span class="field-label"><i class="fas fa-car-side"></i> Transport/Animals:</span>
                    <div class="prop-tags">
                        ${vehicles.map(v => `<span class="prop-tag" style="background:rgba(255,165,0,0.1); color:#ffa500;">${escapeHtml(v)}</span>`).join('')}
                        ${animals.map(a => `<span class="prop-tag" style="background:rgba(34,197,94,0.1); color:#22c55e;">🐾 ${escapeHtml(a)}</span>`).join('')}
                    </div>
                </div>` : ''}
                
                <div class="prod-field mt-3">
                    <div class="scene-body-label" style="font-size:10px; opacity:0.6; text-transform:uppercase; margin-bottom:5px;">Professional Logistics</div>
                    <div class="prod-logistics-grid">
                        <div class="log-item">
                            <span class="field-label">Location:</span>
                            <div class="field-val" style="font-size:10px;">${escapeHtml(bts.location_requirements || 'Standard')}</div>
                        </div>
                        <div class="log-item">
                            <span class="field-label">Lighting:</span>
                            <div class="field-val" style="font-size:10px;">${escapeHtml(bts.lighting_requirements || 'Standard')}</div>
                        </div>
                        <div class="log-item">
                            <span class="field-label">Sound:</span>
                            <div class="field-val" style="font-size:10px;">${escapeHtml(bts.sound_requirements || 'Sync')}</div>
                        </div>
                        <div class="log-item">
                            <span class="field-label">Camera:</span>
                            <div class="field-val" style="font-size:10px;">${escapeHtml(bts.camera_suggestions || 'Static')}</div>
                        </div>
                    </div>
                    <div class="prod-field mt-2">
                        <span class="field-label"><i class="fas fa-shield-alt"></i> Safety/Concerns:</span>
                        <div class="field-val" style="color:#ef4444; font-size:11px;">${formatVal(bts.safety_concerns)}</div>
                    </div>
                </div>

                <div class="mt-3 d-flex flex-wrap gap-1">
                    ${s.stunts ? `<span class="scene-tag" style="background:#ef4444; color:white; border:none; font-size:10px;">🔥 STUNTS: ${escapeHtml(bts.stunt_coordination || 'YES')}</span>` : ''}
                    ${s.vfx ? `<span class="scene-tag" style="background:#3b82f6; color:white; border:none; font-size:10px;">✨ VFX: ${escapeHtml(bts.vfx_requirements || 'YES')}</span>` : ''}
                </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  `;
}

function toggleScene(sceneNum) {
    const card = document.getElementById(`scene-card-${sceneNum}`);
    if (card) card.classList.toggle('expanded');
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
