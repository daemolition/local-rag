let status = initialStatus;

const uploadZone = document.getElementById('uploadZone');
const fileInput = document.getElementById('fileInput');
const pendingList = document.getElementById('pendingList');
const dataList = document.getElementById('dataList');
const pendingCount = document.getElementById('pendingCount');
const dataCount = document.getElementById('dataCount');
const ingestBtn = document.getElementById('ingestBtn');
const statusBox = document.getElementById('statusBox');
const statusTitle = document.getElementById('statusTitle');
const statusMessage = document.getElementById('statusMessage');
const progressArea = document.getElementById('progressArea');
const progressFile = document.getElementById('progressFile');
const progressStage = document.getElementById('progressStage');
const progressChunks = document.getElementById('progressChunks');

updateFileLists();

uploadZone.addEventListener('click', () => fileInput.click());

uploadZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadZone.classList.add('border-slate-500', 'bg-slate-50', 'dark:bg-slate-900/10');
});

uploadZone.addEventListener('dragleave', () => {
    uploadZone.classList.remove('border-slate-500', 'bg-slate-50', 'dark:bg-slate-900/10');
});

uploadZone.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadZone.classList.remove('border-slate-500', 'bg-slate-50', 'dark:bg-slate-900/10');
    handleFiles(e.dataTransfer.files);
});

fileInput.addEventListener('change', (e) => {
    handleFiles(e.target.files);
});

function handleFiles(files) {
    if (status.is_ingesting) {
        showToast('Ingestion läuft bereits. Bitte warten.', 'error');
        return;
    }

    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
        formData.append('files', files[i]);
    }

    fetch('/admin/upload', {
        method: 'POST',
        body: formData
    })
    .then(res => res.json())
    .then(data => {
        if (data.error) {
            showToast(data.error, 'error');
        } else {
            status.pending_files.push(...(data.files.pending || []));
            status.data_files.push(...(data.files.data || []));
            updateFileLists();
        }
    })
    .catch(err => showToast('Fehler beim Hochladen: ' + err, 'error'));
}

function updateFileLists() {
    pendingCount.textContent = status.pending_files.length;
    if (status.pending_files.length === 0) {
        pendingList.innerHTML = '<div class="p-4 text-center text-gray-400 dark:text-gray-500 text-sm">Keine Dateien</div>';
    } else {
        pendingList.innerHTML = status.pending_files.map(f => `
            <div class="flex justify-between items-center px-4 py-3 border-b border-gray-200 dark:border-gray-600 last:border-0">
                <span class="text-sm text-gray-800 dark:text-gray-200 truncate">${f}</span>
                <span class="text-xs text-gray-400">PDF/DOC</span>
            </div>
        `).join('');
    }

    dataCount.textContent = status.data_files.length;
    if (status.data_files.length === 0) {
        dataList.innerHTML = '<div class="p-4 text-center text-gray-400 dark:text-gray-500 text-sm">Keine Dateien</div>';
    } else {
        dataList.innerHTML = status.data_files.map(f => `
            <div class="flex justify-between items-center px-4 py-3 border-b border-gray-200 dark:border-gray-600 last:border-0">
                <span class="text-sm text-gray-800 dark:text-gray-200 truncate">${f}</span>
                <span class="text-xs text-gray-400">Excel/CSV</span>
            </div>
        `).join('');
    }

    ingestBtn.disabled = status.is_ingesting || status.pending_files.length === 0;
}

function updateProgressUI(event) {
    const stageLabels = {
        start: 'Startet...',
        parsing: 'Parse & OCR...',
        embedding: 'Embeddings...',
        done: 'Fertig'
    };

    progressFile.textContent = event.file || '-';
    progressStage.textContent = stageLabels[event.stage] || event.stage;
    progressChunks.textContent = event.chunks !== undefined ? `${event.chunks} Chunks` : '';

    if (event.stage === 'start' || event.stage === 'parsing' || event.stage === 'embedding') {
        progressArea.classList.remove('hidden');
    } else if (event.stage === 'done' && !event.file) {
        progressArea.classList.add('hidden');
    }
}

async function startIngestion() {
    if (status.is_ingesting) {
        showToast('Ingestion läuft bereits.', 'error');
        return;
    }

    if (status.pending_files.length === 0) {
        showToast('Keine Dateien zum Verarbeiten.', 'error');
        return;
    }

    ingestBtn.disabled = true;
    showStatus('processing', 'Ingestion läuft...', 'Die Dokumente werden verarbeitet...');
    progressArea.classList.remove('hidden');

    try {
        const response = await fetch('/admin/ingest/stream', { method: 'POST' });
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const data = line.slice(6).trim();
                    if (!data) continue;

                    try {
                        const event = JSON.parse(data);

                        if (event.error) {
                            showStatus('error', 'Fehler', event.error);
                            progressArea.classList.add('hidden');
                            break;
                        }

                        updateProgressUI(event);

                        if (event.stage === 'done' && !event.file) {
                            status.pending_files = [];
                            showStatus('success', 'Fertig!', 'Alle Dokumente wurden erfolgreich verarbeitet.');
                            progressArea.classList.add('hidden');
                        }
                    } catch (e) {
                        console.error('Parse error:', e, data);
                    }
                }
            }
        }
    } catch (err) {
        showStatus('error', 'Fehler', 'Verbindung fehlgeschlagen: ' + err);
        progressArea.classList.add('hidden');
    } finally {
        ingestBtn.disabled = false;
        updateFileLists();
    }
}

function clearFiles() {
    fetch('/admin/upload/clear', { method: 'POST' })
    .then(res => res.json())
    .then(data => {
        status.pending_files = [];
        status.data_files = [];
        updateFileLists();
    });
}

function showStatus(type, title, message) {
    statusBox.classList.remove('hidden', 'bg-amber-50', 'dark:bg-amber-900/20', 'bg-red-50', 'dark:bg-red-900/20', 'bg-slate-50', 'dark:bg-slate-900/20');

    if (type === 'processing') {
        statusBox.classList.add('bg-amber-50', 'dark:bg-amber-900/20');
    } else if (type === 'error') {
        statusBox.classList.add('bg-red-50', 'dark:bg-red-900/20');
    } else if (type === 'success') {
        statusBox.classList.add('bg-slate-50', 'dark:bg-slate-900/20');
    }

    statusTitle.textContent = title;
    statusMessage.textContent = message;
}
