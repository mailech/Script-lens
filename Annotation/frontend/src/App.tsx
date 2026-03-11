import React, { useState, useEffect } from 'react';
import { Upload, FileText, Download, Play, Search, Copy, Check, Loader2, Image as ImageIcon } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

interface Annotation {
    image_id: string;
    page_number: number;
    image_index: number;
    filename: string;
    description?: string;
    objects: string[];
    text_detected: string[];
    scene_context?: string;
    important_details?: string;
    status: 'pending' | 'processing' | 'completed' | 'error';
}

function App() {
    const [file, setFile] = useState<File | null>(null);
    const [taskId, setTaskId] = useState<string | null>(null);
    const [status, setStatus] = useState<string | null>(null);
    const [progress, setProgress] = useState({ current: 0, total: 0 });
    const [annotations, setAnnotations] = useState<Annotation[]>([]);
    const [loading, setLoading] = useState(false);
    const [searchQuery, setSearchQuery] = useState('');
    const [copiedId, setCopiedId] = useState<string | null>(null);

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files && e.target.files[0]) {
            setFile(e.target.files[0]);
        }
    };

    const startProcessing = async () => {
        if (!file) return;

        setLoading(true);
        setTaskId(null);
        setAnnotations([]);

        const formData = new FormData();
        formData.append('file', file);

        try {
            const res = await fetch('/api/upload_pdf', {
                method: 'POST',
                body: formData,
            });
            const data = await res.json();
            setTaskId(data.task_id);
        } catch (err) {
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

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

    const copyToClipboard = (text: string, id: string) => {
        navigator.clipboard.writeText(text);
        setCopiedId(id);
        setTimeout(() => setCopiedId(null), 2000);
    };

    const filteredAnnotations = annotations.filter(ann =>
        ann.description?.toLowerCase().includes(searchQuery.toLowerCase()) ||
        ann.objects?.some(obj => obj.toLowerCase().includes(searchQuery.toLowerCase())) ||
        ann.text_detected?.some(txt => txt.toLowerCase().includes(searchQuery.toLowerCase()))
    );

    const downloadResults = (format: 'json' | 'txt') => {
        let content = '';
        let fileName = `annotations_${taskId}.${format}`;
        let mimeType = '';

        if (format === 'json') {
            content = JSON.stringify(annotations, null, 2);
            mimeType = 'application/json';
        } else {
            content = annotations.map(ann => {
                return `Page ${ann.page_number} - Image ${ann.image_index + 1}\n` +
                    `Description: ${ann.description}\n` +
                    `Objects: ${ann.objects.join(', ')}\n` +
                    `Text: ${ann.text_detected.join(', ')}\n` +
                    `---`.padEnd(50, '-') + '\n';
            }).join('\n');
            mimeType = 'text/plain';
        }

        const blob = new Blob([content], { type: mimeType });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = fileName;
        a.click();
        URL.revokeObjectURL(url);
    };

    return (
        <div className="min-h-screen">
            <header className="header">
                <h1 className="title">Script Lens: PDF Vision</h1>
                <p className="subtitle">Automatic Image Extraction and Intelligent Annotation</p>
            </header>

            <section className="upload-section">
                <div className="card">
                    <div className="dropzone">
                        <input
                            type="file"
                            accept="application/pdf"
                            onChange={handleFileChange}
                            id="fileInput"
                            className="sr-only"
                            style={{ display: 'none' }}
                        />
                        <label htmlFor="fileInput" className="cursor-pointer">
                            <Upload className="mx-auto mb-4 text-indigo-500" size={48} />
                            <p className="text-lg font-medium">
                                {file ? file.name : "Drag and drop or click to upload PDF"}
                            </p>
                            <p className="text-sm text-gray-400 mt-2">Maximum file size: 50MB</p>
                        </label>
                    </div>

                    <div className="mt-6 flex gap-4">
                        <button
                            className="btn flex-1"
                            onClick={startProcessing}
                            disabled={!file || loading || (taskId && status !== 'completed' && status !== 'error')}
                        >
                            {loading ? <Loader2 className="animate-spin inline mr-2" /> : <Play className="inline mr-2" size={18} />}
                            {taskId ? "Process New File" : "Start Extration & Analysis"}
                        </button>
                    </div>

                    {taskId && (
                        <div className="mt-8 pt-6 border-t border-gray-100">
                            <div className="flex justify-between items-center mb-2">
                                <span className="text-sm font-semibold capitalize text-indigo-600">{status}...</span>
                                <span className="text-sm text-gray-500">{progress.current} / {progress.total} images</span>
                            </div>
                            <div className="progress-bar">
                                <motion.div
                                    initial={{ width: 0 }}
                                    animate={{ width: `${progress.total > 0 ? (progress.current / progress.total) * 100 : 0}%` }}
                                    className="progress-fill"
                                />
                            </div>
                        </div>
                    )}
                </div>
            </section>

            {annotations.length > 0 && (
                <section className="results-section">
                    <div className="flex flex-col md:flex-row justify-between items-center gap-4 mb-8">
                        <div className="relative w-full md:w-96">
                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={18} />
                            <input
                                type="text"
                                placeholder="Search annotations, objects, or text..."
                                className="w-full pl-10 pr-4 py-2 border border-gray-200 rounded-lg focus:ring-2 focus:ring-indigo-500 outline-none"
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                            />
                        </div>

                        <div className="flex gap-2">
                            <button className="btn bg-gray-100 text-gray-700 hover:bg-gray-200" onClick={() => downloadResults('json')}>
                                <Download size={16} className="mr-2" /> JSON
                            </button>
                            <button className="btn bg-gray-100 text-gray-700 hover:bg-gray-200" onClick={() => downloadResults('txt')}>
                                <FileText size={16} className="mr-2" /> TXT
                            </button>
                        </div>
                    </div>

                    <div className="grid">
                        <AnimatePresence>
                            {filteredAnnotations.map((ann, idx) => (
                                <motion.div
                                    key={ann.image_id}
                                    initial={{ opacity: 0, y: 20 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    transition={{ delay: idx * 0.1 }}
                                    className="card"
                                >
                                    <img
                                        src={`/images/${ann.filename}`}
                                        alt={`Preview ${idx}`}
                                        className="image-preview"
                                    />

                                    <div className="flex justify-between items-start">
                                        <div>
                                            <h3 className="font-semibold text-lg">Image {idx + 1}</h3>
                                            <p className="text-xs text-gray-400">Page {ann.page_number} • {ann.filename}</p>
                                        </div>
                                        <button
                                            onClick={() => copyToClipboard(ann.description || '', ann.image_id)}
                                            className="p-2 hover:bg-gray-100 rounded-full transition-colors"
                                        >
                                            {copiedId === ann.image_id ? <Check size={16} className="text-green-500" /> : <Copy size={16} className="text-gray-400" />}
                                        </button>
                                    </div>

                                    <div className="mt-4">
                                        {ann.status === 'processing' ? (
                                            <div className="flex items-center gap-2 text-indigo-500 py-4">
                                                <Loader2 className="animate-spin" size={20} />
                                                <span className="text-sm font-medium">Analyzing with AI...</span>
                                            </div>
                                        ) : (
                                            <>
                                                <div className="annotation-label">Description</div>
                                                <p className="annotation-text">{ann.description || 'No description available.'}</p>

                                                <div className="annotation-label">Objects</div>
                                                <div className="tag-container">
                                                    {ann.objects?.map(obj => (
                                                        <span key={obj} className="tag">{obj}</span>
                                                    ))}
                                                </div>

                                                {ann.text_detected.length > 0 && (
                                                    <>
                                                        <div className="annotation-label">Detected Text</div>
                                                        <div className="annotation-text italic text-sm text-gray-600 bg-gray-50 p-2 rounded">
                                                            {ann.text_detected.join(' | ')}
                                                        </div>
                                                    </>
                                                )}

                                                <div className="annotation-label">Context</div>
                                                <p className="annotation-text text-sm">{ann.scene_context}</p>

                                                <div className="annotation-label">Key Details</div>
                                                <p className="annotation-text text-sm">{ann.important_details}</p>
                                            </>
                                        )}
                                    </div>
                                </motion.div>
                            ))}
                        </AnimatePresence>
                    </div>
                </section>
            )}

            {annotations.length === 0 && !loading && !taskId && (
                <div className="text-center py-20 opacity-30">
                    <ImageIcon className="mx-auto mb-4" size={64} />
                    <p className="text-xl">Your annotations will appear here</p>
                </div>
            )}
        </div>
    );
}

export default App;
