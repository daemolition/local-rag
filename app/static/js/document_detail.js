function confirmDelete() {
    document.getElementById('deleteModal').classList.remove('hidden');
    document.getElementById('deleteModal').classList.add('flex');
}

function closeModal() {
    document.getElementById('deleteModal').classList.add('hidden');
    document.getElementById('deleteModal').classList.remove('flex');
}

function deleteDocument() {
    fetch(`/admin/documents/${docId}/delete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            window.location.href = '/admin/documents';
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

function copyContent(elementId) {
    const content = document.getElementById(elementId).textContent;
    navigator.clipboard.writeText(content).then(() => {
        const btn = event.target;
        const originalText = btn.textContent;
        btn.textContent = 'Kopiert!';
        setTimeout(() => {
            btn.textContent = originalText;
        }, 2000);
    });
}