let currentDocId = null;
let currentFilename = null;

function confirmDelete(docId, filename) {
    currentDocId = docId;
    document.getElementById('deleteModalText').textContent =
        `Möchtest du das Dokument "${filename}" wirklich löschen?`;
    document.getElementById('deleteModal').classList.remove('hidden');
    document.getElementById('deleteModal').classList.add('flex');
}

function closeModal() {
    document.getElementById('deleteModal').classList.add('hidden');
    document.getElementById('deleteModal').classList.remove('flex');
    currentDocId = null;
}

function deleteDocument() {
    if (!currentDocId) return;

    fetch(`/user/vectordb/${currentDocId}/delete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            showToast('Dokument gelöscht', 'success');
            setTimeout(() => location.reload(), 500);
        } else {
            showToast('Fehler: ' + (data.error || 'Unbekannter Fehler'), 'error');
            closeModal();
        }
    })
    .catch(err => {
        showToast('Fehler: ' + err.message, 'error');
        closeModal();
    });
}

function confirmBatchDelete(filename) {
    currentFilename = filename;
    document.getElementById('batchDeleteModalText').textContent =
        `Möchtest du wirklich alle Dokumente von "${filename}" löschen?`;
    document.getElementById('batchDeleteModal').classList.remove('hidden');
    document.getElementById('batchDeleteModal').classList.add('flex');
}

function closeBatchModal() {
    document.getElementById('batchDeleteModal').classList.add('hidden');
    document.getElementById('batchDeleteModal').classList.remove('flex');
    currentFilename = null;
}

function batchDeleteDocument() {
    if (!currentFilename) return;

    fetch('/user/vectordb/batch-delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: currentFilename })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            showToast('Dokumente gelöscht', 'success');
            setTimeout(() => location.reload(), 500);
        } else {
            showToast('Fehler: ' + (data.error || 'Unbekannter Fehler'), 'error');
            closeBatchModal();
        }
    })
    .catch(err => {
        showToast('Fehler: ' + err.message, 'error');
        closeBatchModal();
    });
}

// Keyboard handler
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeModal();
        closeBatchModal();
    }
});
