/* EasyMDE Markdown-Editor */
let easyMDE;

function initEditor(markdownContent) {
    easyMDE = new EasyMDE({
        element: document.getElementById('editor'),
        initialValue: markdownContent,
        spellChecker: false,
        autofocus: true,
        status: ["lines", "words", "cursor"],
        renderingConfig: {
            singleLineBreaks: false,
            codeSyntaxHighlighting: true,
            sanitizerFunction: (renderedHTML) => DOMPurify.sanitize(renderedHTML),
        },
        insertTexts: {
            horizontalRule: ["", "\n\n-----\n\n"],
            image: ["!(http://", ")"],
            link: ["[", "](https://)"],
            table: ["", "\n\n| Spalte 1 | Spalte 2 | Spalte 3 |\n| -------- | -------- | -------- |\n| Text     | Text     | Text     |\n\n"],
        },
        toolbar: [
            "heading", "bold", "italic", "underline", "strikethrough", "|",
            "heading-1", "heading-2", "heading-3", "|",
            "code", "quote", "unordered-list", "ordered-list", "|",
            "link", "image", "table", "horizontal-rule", "|",
            "preview", "side-by-side", "fullscreen", "|",
            "guide"
        ],
        minHeight: "580px",
    });
}

/* Summary speichern — Source of Truth ist die Markdown-Textarea, kein HTML-Roundtrip */
async function saveSummary() {
    const markdownContent = easyMDE.value();

    const btn = document.querySelector('button[onclick="saveSummary()"]');
    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = `
        <svg class="animate-spin w-4 h-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
        </svg>
        Wird gespeichert...
    `;

    try {
        const response = await fetch(saveEndpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content: markdownContent })
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
        btn.innerHTML = originalText;
    }
}

/* Toast-Benachrichtigung (Fallback, falls utils.js nicht geladen) */
if (typeof showToast !== 'function') {
    function showToast(message, type = 'info') {
        const colors = {
            success: 'bg-emerald-500',
            error: 'bg-red-500',
            info: 'bg-blue-500',
            warning: 'bg-yellow-500'
        };
        const toast = document.createElement('div');
        toast.className = `fixed top-4 right-4 z-50 ${colors[type]} text-white px-4 py-3 rounded-lg shadow-lg text-sm font-medium transition-all`;
        toast.textContent = message;
        document.body.appendChild(toast);
        setTimeout(() => toast.remove(), 3000);
    }
}

/* Editor initialisieren */
document.addEventListener('DOMContentLoaded', () => {
    let markdownContent = '';
    const initialContentEl = document.getElementById('initial-content');
    if (initialContentEl) {
        try {
            markdownContent = JSON.parse(initialContentEl.textContent) || '';
        } catch (e) {
            markdownContent = initialContentEl.textContent || '';
        }
    }
    initEditor(markdownContent);
});