// Modal Functions
function openCreateModal() {
    document.getElementById('createModal').classList.remove('hidden');
    document.getElementById('createModal').classList.add('flex');
    document.getElementById('newUsername').focus();
}

function closeCreateModal() {
    document.getElementById('createModal').classList.add('hidden');
    document.getElementById('createModal').classList.remove('flex');
    document.getElementById('createUserForm').reset();
}

function openResetModal(userId, username) {
    document.getElementById('resetUserId').value = userId;
    document.getElementById('resetUsername').textContent = username;
    document.getElementById('resetModal').classList.remove('hidden');
    document.getElementById('resetModal').classList.add('flex');
    document.getElementById('resetPassword').focus();
}

function closeResetModal() {
    document.getElementById('resetModal').classList.add('hidden');
    document.getElementById('resetModal').classList.remove('flex');
    document.getElementById('resetPasswordForm').reset();
}

function togglePassword(inputId) {
    const input = document.getElementById(inputId);
    input.type = input.type === 'password' ? 'text' : 'password';
}

// API Functions
async function handleCreate(e) {
    e.preventDefault();
    
    const data = {
        username: document.getElementById('newUsername').value.trim(),
        password: document.getElementById('newPassword').value,
        is_admin: document.getElementById('newIsAdmin').checked
    };
    
    try {
        const response = await fetch('/admin/users', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        
        const result = await response.json();
        if (result.success) {
            showToast('User erfolgreich angelegt', 'success');
            closeCreateModal();
            setTimeout(() => location.reload(), 500);
        } else {
            showToast('Fehler: ' + result.error, 'error');
        }
    } catch (e) {
        showToast('Fehler: ' + e.message, 'error');
    }
}

async function handleReset(e) {
    e.preventDefault();
    
    const userId = document.getElementById('resetUserId').value;
    const password = document.getElementById('resetPassword').value;
    
    try {
        const response = await fetch(`/admin/users/${userId}/reset-password`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password })
        });
        
        const result = await response.json();
        if (result.success) {
            showToast('Passwort zurückgesetzt', 'success');
            closeResetModal();
        } else {
            showToast('Fehler: ' + result.error, 'error');
        }
    } catch (e) {
        showToast('Fehler: ' + e.message, 'error');
    }
}

async function toggleAdmin(userId, username) {
    if (!confirm(`Admin-Status für "${username}" ändern?`)) return;
    
    try {
        const response = await fetch(`/admin/users/${userId}/toggle-admin`, {
            method: 'POST'
        });
        
        const result = await response.json();
        if (result.success) {
            showToast('Admin-Status geändert', 'success');
            setTimeout(() => location.reload(), 500);
        } else {
            showToast('Fehler: ' + result.error, 'error');
        }
    } catch (e) {
        showToast('Fehler: ' + e.message, 'error');
    }
}

async function deleteUser(userId, username) {
    if (!confirm(`User "${username}" wirklich löschen? Alle Dokumente werden dem Admin übertragen.`)) return;
    
    try {
        const response = await fetch(`/admin/users/${userId}`, {
            method: 'DELETE'
        });
        
        const result = await response.json();
        if (result.success) {
            showToast('User gelöscht', 'success');
            setTimeout(() => location.reload(), 500);
        } else {
            showToast('Fehler: ' + result.error, 'error');
        }
    } catch (e) {
        showToast('Fehler: ' + e.message, 'error');
    }
}

function resetPassword(userId, username) {
    openResetModal(userId, username);
}

// Keyboard handlers for modals
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeCreateModal();
        closeResetModal();
    }
});