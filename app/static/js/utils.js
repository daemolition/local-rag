// === Theme-Switch (Hell/Dunkel, OpenAI/OpenWebUI-Stil) ===
// Präferenz: localStorage 'ui_theme' = 'light' | 'dark' | 'system'.
// 'system' folgt prefers-color-scheme. base.html setzt die initiale Klasse
// vor dem ersten Paint; diese Funktion übernimmt nur Umschalten + Persistenz.
function applyTheme(pref) {
    localStorage.setItem('ui_theme', pref);
    var dark = pref === 'dark' ||
        (pref === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
    var root = document.documentElement;
    if (dark) root.classList.add('dark');
    else root.classList.remove('dark');
    updateThemeToggleIcons(dark);
    return dark;
}

// Cycle-Toggle für Header-Button: light -> dark -> system -> light ...
// Aktuell einfacher Binär-Toggle (light <-> dark), 'system' via Settings.
function toggleTheme() {
    var root = document.documentElement;
    var isDark = root.classList.contains('dark');
    return applyTheme(isDark ? 'light' : 'dark');
}

// Sonne/Mond-Icon-Sichtbarkeit aktualisieren. Die Icons nutzen die Tailwind
// 'hidden'-Klasse (display:none). Inline style.display='' wuerde die nicht
// überschreiben, daher explizit toggle('hidden', ...) statt style.display.
function updateThemeToggleIcons(isDark) {
    document.querySelectorAll('[data-theme-icon-sun]').forEach(function (el) {
        el.classList.toggle('hidden', !isDark);
    });
    document.querySelectorAll('[data-theme-icon-moon]').forEach(function (el) {
        el.classList.toggle('hidden', isDark);
    });
}

// Beim Laden die Icon-Sichtbarkeit mit dem initialen Theme synchronisieren.
(function initThemeIcons() {
    if (window.__themeDark !== undefined) updateThemeToggleIcons(window.__themeDark);
})();

// Auf OS-Theme-Wechsel reagieren, wenn Präferenz 'system' ist.
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function (e) {
    var pref = localStorage.getItem('ui_theme') || 'system';
    if (pref === 'system') {
        var root = document.documentElement;
        if (e.matches) root.classList.add('dark');
        else root.classList.remove('dark');
        updateThemeToggleIcons(e.matches);
    }
});

// Toast Notification
function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = `fixed bottom-6 right-6 px-6 py-3 rounded-lg shadow-material-3 z-50 transform translate-x-0 transition-transform duration-300 ${
        type === 'success'
            ? 'bg-primary text-primary-text'
            : 'bg-red-600 text-white'
    }`;
    toast.textContent = message;
    toast.style.animation = 'slideIn 0.3s ease';
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// CSS Animations for Toast
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from { transform: translateX(100%); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
    }
    @keyframes slideOut {
        from { transform: translateX(0); opacity: 1; }
        to { transform: translateX(100%); opacity: 0; }
    }
`;
document.head.appendChild(style);

// Escape HTML to prevent XSS
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Format Date in German locale
function formatLocalDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('de-DE', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

// Mobile Menu Toggle
function toggleMobileMenu() {
    const menu = document.getElementById('mobile-menu');
    if (menu) {
        menu.classList.toggle('hidden');
    }
}

// Close mobile menu when clicking outside
document.addEventListener('click', (e) => {
    const menu = document.getElementById('mobile-menu');
    const button = document.getElementById('mobile-menu-button');
    if (menu && button && !menu.contains(e.target) && !button.contains(e.target)) {
        menu.classList.add('hidden');
    }
});

// Ingestion-Indikator: pollt, ob gerade eine Ingestion laeuft, und
// zeigt/versteckt den blinkenden Indikator in der Navbar entsprechend.
(function pollIngestionStatus() {
    const indicator = document.getElementById('ingestionIndicator');
    if (!indicator) return;

    async function check() {
        try {
            const res = await fetch('/api/ingestion-status');
            if (!res.ok) {
                indicator.style.display = 'none';
                return;
            }
            const data = await res.json();
            indicator.style.display = data.is_ingesting ? 'flex' : 'none';
        } catch (e) {
            indicator.style.display = 'none';
        }
    }

    check();
    setInterval(check, 5000);
})();