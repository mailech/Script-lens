import React, { useState, useEffect, useRef } from 'react';
import {
    Upload, Film, Search, Download, FileText,
    Copy, Check, Loader2, Clapperboard, Eye
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

/* ── Types ──────────────────────────────────────────────── */
interface Annotation {
    image_id: string;
    page_number: number;
    image_index: number;
    filename: string;

    // Cinematic fields
    scene_heading?: string;
    scene_description?: string;
    action_lines?: string;
    visual_elements?: string[];
    mood_and_tone?: string;
    lighting_notes?: string;
    color_palette?: string;
    characters_or_subjects?: string;
    text_in_scene?: string[];
    director_notes?: string;
    scene_type?: string;

    status: 'pending' | 'processing' | 'completed' | 'error';
    error_message?: string;
}

/* ── Filmstrip decoration ───────────────────────────────── */
const Filmstrip = () => (
    <>
        <div className="filmstrip-top">
            {Array.from({ length: 40 }).map((_, i) => (
                <div key={i} className="filmstrip-hole" />
            ))}
        </div>
        <div className="filmstrip-bottom">
            {Array.from({ length: 40 }).map((_, i) => (
                <div key={i} className="filmstrip-hole" />
            ))}
        </div>
    </>
);

/* ── Copy button ────────────────────────────────────────── */
function CopyButton({ text }: { text: string }) {
    const [copied, setCopied] = useState(false);
    const handle = () => {
        navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };
    return (
        <button className="copy-btn" onClick={handle} title="Copy to clipboard">
            {copied
                ? <Check size={13} style={{ color: '#f5c842' }} />
                : <Copy size={13} />}
        </button>
    );
}

/* ── Single Scene Card ──────────────────────────────────── */
function SceneCard({ ann, index, selectedLang }: { ann: Annotation; index: number; selectedLang: string }) {
    const isProcessing = ann.status === 'processing' || ann.status === 'pending';
    const isError = ann.status === 'error';

    // Per-card translation state
    const [translatedAnn, setTranslatedAnn] = useState<Annotation | null>(null);
    const [isTranslating, setIsTranslating] = useState(false);

    useEffect(() => {
        if (!ann || isProcessing || isError) return;
        if (selectedLang === 'English') {
            setTranslatedAnn(null);
            return;
        }

        // Let's translate this specific scene card!
        const translate = async () => {
            setIsTranslating(true);
            try {
                // Strip unnecessary metadata for the translator engine
                const { image_id, page_number, image_index, filename, status, error_message, ...sceneData } = ann;

                const res = await fetch('/api/translate_scene', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        language: selectedLang,
                        scene_data: sceneData
                    })
                });

                if (res.ok) {
                    const translatedData = await res.json();
                    setTranslatedAnn({ ...ann, ...translatedData });
                }
            } catch (err) {
                console.error("Translation error", err);
            } finally {
                setIsTranslating(false);
            }
        };

        translate();
    }, [selectedLang, ann, isProcessing, isError]);

    // Choose which annotation to render (Original vs Translated)
    const displayAnn = translatedAnn || ann;

    const fullSceneText = [
        displayAnn.scene_heading,
        '',
        displayAnn.scene_description,
        '',
        displayAnn.action_lines,
    ].filter(Boolean).join('\n');

    return (
        <motion.div
            className="scene-card fade-up"
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.06, duration: 0.4 }}
        >
            {/* Scene number header bar */}
            <div className="scene-number-bar">
                <span>SCENE {String(index + 1).padStart(3, '0')}  —  PAGE {displayAnn.page_number}</span>
                {displayAnn.scene_type && (
                    <span className="scene-type-badge">{displayAnn.scene_type}</span>
                )}
            </div>

            <div className="scene-body">
                {/* Left: Image */}
                <div className="scene-image-col">
                    {isProcessing ? (
                        <div className="scene-image-loading">
                            <div className="spinner" />
                            <span>DEVELOPING FRAME...</span>
                        </div>
                    ) : (
                        <img
                            className="scene-image"
                            src={`/images/${displayAnn.filename}`}
                            alt={`Scene ${index + 1}`}
                            loading="lazy"
                        />
                    )}
                </div>

                {/* Right: Screenplay content */}
                <div className="scene-content-col">
                    {isProcessing && (
                        <div className="processing-overlay">
                            <div className="spinner" />
                            <span>A.I. IS WRITING THE SCENE...</span>
                        </div>
                    )}

                    {isTranslating && (
                        <div className="processing-overlay" style={{ background: 'rgba(20,20,20,0.85)' }}>
                            <div className="spinner" />
                            <span>Translating to {selectedLang}...</span>
                        </div>
                    )}

                    {isError && (
                        <div className="processing-overlay" style={{ color: '#c0392b' }}>
                            <span>⚠ ERROR PROCESSING THIS SCENE — {displayAnn.error_message || 'Unknown error'}</span>
                        </div>
                    )}

                    {displayAnn.status === 'completed' && !isTranslating && (
                        <>
                            {/* INT./EXT. heading */}
                            {displayAnn.scene_heading && (
                                <div className="screenplay-heading">
                                    <span>{displayAnn.scene_heading}</span>
                                    <CopyButton text={fullSceneText} />
                                </div>
                            )}

                            {/* Scene description */}
                            {displayAnn.scene_description && (
                                <p className="scene-description-block">{displayAnn.scene_description}</p>
                            )}

                            {/* Action lines */}
                            {displayAnn.action_lines && (
                                <blockquote className="action-block">{displayAnn.action_lines}</blockquote>
                            )}

                            {/* Mood + Lighting */}
                            <div className="meta-grid">
                                {displayAnn.mood_and_tone && (
                                    <div className="meta-item">
                                        <div className="meta-label">🎭 Mood & Tone</div>
                                        <div className="meta-value">{displayAnn.mood_and_tone}</div>
                                    </div>
                                )}
                                {displayAnn.lighting_notes && (
                                    <div className="meta-item">
                                        <div className="meta-label">💡 Lighting (DOP)</div>
                                        <div className="meta-value">{displayAnn.lighting_notes}</div>
                                    </div>
                                )}
                                {displayAnn.color_palette && (
                                    <div className="meta-item">
                                        <div className="meta-label">🎨 Color Palette</div>
                                        <div className="meta-value">{displayAnn.color_palette}</div>
                                    </div>
                                )}
                                {displayAnn.characters_or_subjects && (
                                    <div className="meta-item">
                                        <div className="meta-label">🎬 Subjects</div>
                                        <div className="meta-value">{displayAnn.characters_or_subjects}</div>
                                    </div>
                                )}
                            </div>

                            {/* Visual elements */}
                            {displayAnn.visual_elements && displayAnn.visual_elements.length > 0 && (
                                <div className="tag-row">
                                    {displayAnn.visual_elements.map((el, i) => (
                                        <span key={i} className="tag">{el}</span>
                                    ))}
                                </div>
                            )}

                            {/* Text in scene */}
                            {displayAnn.text_in_scene && displayAnn.text_in_scene.length > 0 && displayAnn.text_in_scene[0] !== '' && (
                                <div className="detected-text-block">
                                    📜 &nbsp;{displayAnn.text_in_scene.join(' · ')}
                                </div>
                            )}

                            {/* Director's note */}
                            {displayAnn.director_notes && (
                                <div className="directors-note">
                                    <div className="directors-note-label">🎬 Director's Note</div>
                                    <p className="directors-note-text">{displayAnn.director_notes}</p>
                                </div>
                            )}
                        </>
                    )}
                </div>
            </div>
        </motion.div>
    );
}

/* ── Main App ───────────────────────────────────────────── */
const LANGUAGES = [
    "English", "Hindi", "Bengali", "Telugu", "Marathi", "Tamil",
    "Urdu", "Gujarati", "Kannada", "Odia", "Malayalam", "Punjabi", "Assamese"
];

export default function App() {
    const [selectedLang, setSelectedLang] = useState("English");
    const [file, setFile] = useState<File | null>(null);
    const [taskId, setTaskId] = useState<string | null>(null);
    const [status, setStatus] = useState<string | null>(null);
    const [progress, setProgress] = useState({ current: 0, total: 0 });
    const [annotations, setAnnotations] = useState<Annotation[]>([]);
    const [loading, setLoading] = useState(false);
    const [searchQuery, setSearchQuery] = useState('');
    const [isDragging, setIsDragging] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);

    /* ── File handling ─────────── */
    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files?.[0]) setFile(e.target.files[0]);
    };

    const handleDrop = (e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(false);
        const dropped = e.dataTransfer.files[0];
        if (dropped?.type === 'application/pdf') setFile(dropped);
    };

    /* ── Upload & start ─────────── */
    const startProcessing = async () => {
        if (!file) return;
        setLoading(true);
        setTaskId(null);
        setAnnotations([]);
        setStatus(null);

        const formData = new FormData();
        formData.append('file', file);

        try {
            const res = await fetch('/api/upload_pdf', { method: 'POST', body: formData });
            const data = await res.json();
            setTaskId(data.task_id);
        } catch (err) {
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    /* ── Polling ──────────────── */
    useEffect(() => {
        if (!taskId) return;
        const interval = setInterval(async () => {
            try {
                const statusRes = await fetch(`/api/processing_status/${taskId}`);
                const statusData = await statusRes.json();
                setStatus(statusData.status);
                setProgress({ current: statusData.completed, total: statusData.total });

                if (statusData.completed > 0 || statusData.status === 'completed') {
                    const annRes = await fetch(`/api/annotations/${taskId}`);
                    const annData = await annRes.json();
                    setAnnotations(annData);
                }

                if (statusData.status === 'completed' || statusData.status === 'error') {
                    clearInterval(interval);
                }
            } catch (err) {
                console.error(err);
                clearInterval(interval);
            }
        }, 2000);
        return () => clearInterval(interval);
    }, [taskId]);

    /* ── Search filter ──────────── */
    const filtered = annotations.filter(ann => {
        if (!searchQuery) return true;
        const q = searchQuery.toLowerCase();
        return (
            ann.scene_heading?.toLowerCase().includes(q) ||
            ann.scene_description?.toLowerCase().includes(q) ||
            ann.action_lines?.toLowerCase().includes(q) ||
            ann.mood_and_tone?.toLowerCase().includes(q) ||
            ann.director_notes?.toLowerCase().includes(q) ||
            ann.visual_elements?.some(e => e.toLowerCase().includes(q)) ||
            ann.text_in_scene?.some(t => t.toLowerCase().includes(q))
        );
    });

    /* ── Download ──────────────── */
    const download = (format: 'json' | 'screenplay') => {
        let content = '';
        const name = `screenplay_${taskId}.${format === 'json' ? 'json' : 'txt'}`;

        if (format === 'json') {
            content = JSON.stringify(annotations, null, 2);
        } else {
            content = annotations.map((ann, i) => {
                return [
                    '='.repeat(60),
                    `SCENE ${String(i + 1).padStart(3, '0')}  —  PAGE ${ann.page_number}`,
                    '='.repeat(60),
                    '',
                    ann.scene_heading || '',
                    '',
                    ann.scene_description || '',
                    '',
                    ann.action_lines || '',
                    '',
                    `MOOD: ${ann.mood_and_tone || ''}`,
                    `LIGHTING: ${ann.lighting_notes || ''}`,
                    `PALETTE: ${ann.color_palette || ''}`,
                    `SUBJECTS: ${ann.characters_or_subjects || ''}`,
                    `ELEMENTS: ${ann.visual_elements?.join(', ') || ''}`,
                    `TEXT: ${ann.text_in_scene?.join(' | ') || ''}`,
                    '',
                    `DIRECTOR'S NOTE: ${ann.director_notes || ''}`,
                    '',
                ].join('\n');
            }).join('\n\n');
        }

        const blob = new Blob([content], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = name; a.click();
        URL.revokeObjectURL(url);
    };

    const isRunning = taskId && status !== 'completed' && status !== 'error';
    const pct = progress.total > 0 ? (progress.current / progress.total) * 100 : 0;

    /* ── Render ─────────────────── */
    return (
        <>
            <Filmstrip />

            <div style={{ paddingTop: '28px', paddingBottom: '28px' }}>
                {/* Header */}
                <header className="app-header">
                    <span className="logo-eyebrow">A.I. Cinematic Vision Engine</span>
                    <h1 className="app-title">
                        Script<span>Lens</span>
                    </h1>
                    <p className="app-subtitle">
                        Upload a PDF · Every image becomes a movie scene
                    </p>
                </header>

                {/* Upload */}
                <section className="upload-section">
                    <div className="upload-card">
                        <div
                            className="dropzone"
                            style={isDragging ? { borderColor: '#f5c842', background: 'rgba(245,200,66,0.05)' } : {}}
                            onDragOver={e => { e.preventDefault(); setIsDragging(true); }}
                            onDragLeave={() => setIsDragging(false)}
                            onDrop={handleDrop}
                            onClick={() => fileInputRef.current?.click()}
                        >
                            <input
                                ref={fileInputRef}
                                type="file"
                                accept="application/pdf"
                                onChange={handleFileChange}
                                style={{ display: 'none' }}
                            />
                            <Film className="dropzone-icon" size={40} />
                            <span className="dropzone-label">
                                {isDragging ? 'DROP THE FILM REEL...' : 'LOAD YOUR PDF — DRAG OR CLICK'}
                            </span>
                            <span className="dropzone-hint">Supports multi-page PDFs · Max 50MB</span>
                        </div>

                        {file && (
                            <div className="file-selected">
                                <Clapperboard size={16} />
                                <span>{file.name}</span>
                                <span style={{ marginLeft: 'auto', fontSize: '0.75rem', opacity: 0.6 }}>
                                    {(file.size / 1024 / 1024).toFixed(2)} MB
                                </span>
                            </div>
                        )}

                        <div className="action-row">
                            <button
                                className="btn btn-primary"
                                onClick={startProcessing}
                                disabled={!file || loading || !!isRunning}
                            >
                                {loading
                                    ? <><Loader2 size={16} className="animate-spin" /> UPLOADING...</>
                                    : <><Eye size={16} /> ANNOTATE AS MOVIE SCENES</>}
                            </button>
                        </div>

                        {/* Progress */}
                        {taskId && (
                            <div className="progress-section">
                                <div className="progress-meta">
                                    <span className="progress-status">{status ?? 'waiting'}...</span>
                                    <span className="progress-count">{progress.current} / {progress.total} scenes</span>
                                </div>
                                <div className="progress-bar">
                                    <motion.div
                                        className="progress-fill"
                                        initial={{ width: 0 }}
                                        animate={{ width: `${pct}%` }}
                                        transition={{ duration: 0.5 }}
                                    />
                                </div>
                            </div>
                        )}
                    </div>
                </section>

                {/* Results */}
                <AnimatePresence>
                    {annotations.length > 0 && (
                        <motion.section
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                        >
                            <div className="results-toolbar">
                                <h2 className="results-count">
                                    <span>{filtered.length}</span> SCENES
                                </h2>

                                <div className="search-wrap">
                                    <Search className="search-icon" size={15} />
                                    <input
                                        className="search-input"
                                        type="text"
                                        placeholder="Search scenes..."
                                        value={searchQuery}
                                        onChange={e => setSearchQuery(e.target.value)}
                                    />
                                </div>

                                <div className="toolbar-actions">
                                    <select
                                        className="btn btn-ghost btn-sm"
                                        value={selectedLang}
                                        onChange={e => setSelectedLang(e.target.value)}
                                        style={{ marginRight: '8px', background: 'rgba(255,255,255,0.05)', color: '#fff', border: '1px solid rgba(255,255,255,0.1)', outline: 'none' }}
                                    >
                                        {LANGUAGES.map(lang => <option key={lang} value={lang} style={{ color: '#000' }}>{lang}</option>)}
                                    </select>
                                    <button
                                        className="btn btn-ghost btn-sm"
                                        onClick={() => download('screenplay')}
                                    >
                                        <FileText size={14} /> Screenplay
                                    </button>
                                    <button
                                        className="btn btn-ghost btn-sm"
                                        onClick={() => download('json')}
                                    >
                                        <Download size={14} /> JSON
                                    </button>
                                </div>
                            </div>

                            <div className="scenes-list">
                                {filtered.map((ann, i) => (
                                    <SceneCard key={ann.image_id} ann={ann} index={i} selectedLang={selectedLang} />
                                ))}
                            </div>
                        </motion.section>
                    )}
                </AnimatePresence>

                {/* Empty state */}
                {annotations.length === 0 && !loading && !taskId && (
                    <div className="empty-state">
                        <Clapperboard className="empty-icon" size={80} />
                        <p className="empty-title">NO FOOTAGE LOADED</p>
                        <p className="empty-sub">Upload a PDF above to begin scene annotation</p>
                    </div>
                )}
            </div>
        </>
    );
}
