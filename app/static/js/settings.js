function handleSelectChange(key, value) {
    for (const [parentKey, config] of Object.entries(dependentFields)) {
        if (parentKey === key) {
            for (const field of config.fields) {
                const group = document.getElementById('group-' + field);
                if (group) {
                    if (value === config.show_when) {
                        group.classList.remove('hidden');
                    } else {
                        group.classList.add('hidden');
                    }
                }
            }
        }
    }
}

document.addEventListener('DOMContentLoaded', function() {
});

function togglePassword(inputId) {
    const input = document.getElementById(inputId);
    input.type = input.type === 'password' ? 'text' : 'password';
}

async function saveCategory(category) {
    const form = document.querySelector(`form[data-category="${category}"]`);
    const inputs = form.querySelectorAll('input, select');
    const settings = {};

    inputs.forEach(input => {
        settings[input.name] = input.value;
    });

    try {
        const response = await fetch('/user/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ settings })
        });

        const result = await response.json();
        if (result.success) {
            showToast('Einstellungen gespeichert', 'success');
        } else {
            showToast('Fehler: ' + result.error, 'error');
        }
    } catch (e) {
        showToast('Fehler: ' + e.message, 'error');
    }
}

async function resetSetting(key) {
    if (!confirm(`"${key}" wirklich auf Default zurücksetzen?`)) return;

    try {
        const response = await fetch('/user/settings/reset', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ key })
        });

        const result = await response.json();
        if (result.success) {
            location.reload();
        } else {
            showToast('Fehler: ' + result.error, 'error');
        }
    } catch (e) {
        showToast('Fehler: ' + e.message, 'error');
    }
}

async function resetCategory(category) {
    if (!confirm(`Alle Einstellungen in dieser Kategorie wirklich auf Default zurücksetzen?`)) return;

    try {
        const response = await fetch('/user/settings/reset-category', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ category })
        });

        const result = await response.json();
        if (result.success) {
            showToast(`${result.reset_count} Einstellungen zurückgesetzt`, 'success');
            setTimeout(() => location.reload(), 1000);
        } else {
            showToast('Fehler: ' + result.error, 'error');
        }
    } catch (e) {
        showToast('Fehler: ' + e.message, 'error');
    }
}

async function changePassword() {
    const oldPassword = document.getElementById('oldPassword').value;
    const newPassword = document.getElementById('newPassword').value;

    if (!newPassword || newPassword.length < 4) {
        showToast('Neues Passwort muss mindestens 4 Zeichen haben', 'error');
        return;
    }

    try {
        const response = await fetch('/user/settings/change-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ old_password: oldPassword, new_password: newPassword })
        });

        const result = await response.json();
        if (result.success) {
            showToast('Passwort geändert', 'success');
            document.getElementById('oldPassword').value = '';
            document.getElementById('newPassword').value = '';
        } else {
            showToast('Fehler: ' + result.error, 'error');
        }
    } catch (e) {
        showToast('Fehler: ' + e.message, 'error');
    }
}
