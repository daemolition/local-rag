function parseMarkdown(text) {
    let html = text
        .replace(/^### (.*$)/gim, '<h3>$1</h3>')
        .replace(/^## (.*$)/gim, '<h2>$1</h2>')
        .replace(/^# (.*$)/gim, '<h1>$1</h1>')
        .replace(/\*\*(.*)\*\*/gim, '<strong>$1</strong>')
        .replace(/\*(.*)\*/gim, '<em>$1</em>')
        .replace(/```([\s\S]*?)```/gim, '<pre><code>$1</code></pre>')
        .replace(/`([^`]+)`/gim, '<code>$1</code>')
        .replace(/^\s*[-*+]\s+(.*)/gim, '<li>$1</li>')
        .replace(/^\s*>\s*(.*)/gim, '<blockquote>$1</blockquote>');
    
    html = html.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$1</ul>');
    html = html.replace(/\n/g, '<br>');
    
    return html;
}

function updatePreview() {
    const content = document.getElementById('content').value;
    document.getElementById('preview-content').innerHTML = parseMarkdown(content);
}

function switchTab(tab) {
    document.querySelectorAll('[id^="tab-"]').forEach(t => {
        t.classList.remove('text-slate-700', 'dark:text-slate-400', 'bg-white', 'dark:bg-gray-800', 'border-slate-600', 'dark:border-slate-400');
    });
    
    const activeTab = document.getElementById('tab-' + tab);
    activeTab.classList.remove('text-gray-600', 'dark:text-gray-400', 'border-transparent');
    activeTab.classList.add('text-slate-700', 'dark:text-slate-400', 'bg-white', 'dark:bg-gray-800', 'border-slate-600', 'dark:border-slate-400');
    
    document.getElementById('pane-edit').classList.toggle('hidden', tab !== 'edit');
    document.getElementById('pane-preview').classList.toggle('hidden', tab !== 'preview');
    
    if (tab === 'preview') {
        updatePreview();
    }
}

async function saveSummary() {
    const content = document.getElementById('content').value;
    const btn = document.querySelector('button[onclick="saveSummary()"]');
    btn.disabled = true;
    btn.classList.add('opacity-50', 'cursor-not-allowed');
    
    try {
        const response = await fetch(saveEndpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content })
        });
        
        const result = await response.json();
        if (result.success) {
            showToast('Gespeichert', 'success');
        } else {
            showToast('Fehler: ' + result.error, 'error');
        }
    } catch (e) {
        showToast('Fehler: ' + e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.classList.remove('opacity-50', 'cursor-not-allowed');
    }
}

let debounceTimer;
document.getElementById('content').addEventListener('input', () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(updatePreview, 300);
});

updatePreview();