// ── Change Password ──────────────────────────────────────────────────────────

function showPasswordForm() {
    document.getElementById('change-password-btn-wrap').style.display = 'none';
    document.getElementById('change-password-form').classList.add('open');
    document.getElementById('current-password').focus();
}

function hidePasswordForm() {
    document.getElementById('change-password-btn-wrap').style.display = 'block';
    document.getElementById('change-password-form').classList.remove('open');
    document.getElementById('current-password').value = '';
    document.getElementById('new-password').value = '';
}

async function updatePassword() {
    const currentPassword = document.getElementById('current-password').value;
    const newPassword = document.getElementById('new-password').value;

    if (!currentPassword || !newPassword) {
        alert('Please fill in both fields.');
        return;
    }
    if (newPassword.length < 8) {
        alert('New password must be at least 8 characters.');
        return;
    }

    try {
        const response = await fetch('/api/account/password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ current_password: currentPassword, new_password: newPassword })
        });
        const data = await response.json();
        if (response.ok) {
            alert('Password updated successfully.');
            hidePasswordForm();
        } else {
            alert(data.error || 'Failed to update password.');
        }
    } catch {
        alert('An error occurred. Please try again.');
    }
}

// ── Delete Account ───────────────────────────────────────────────────────────

function showDeleteForm() {
    document.getElementById('delete-account-btn-wrap').style.display = 'none';
    document.getElementById('delete-account-form').classList.add('open');
    document.getElementById('confirm-delete').focus();
}

function hideDeleteForm() {
    document.getElementById('delete-account-btn-wrap').style.display = 'block';
    document.getElementById('delete-account-form').classList.remove('open');
    document.getElementById('confirm-delete').value = '';
}

async function deleteAccount() {
    const confirmation = document.getElementById('confirm-delete').value.trim();
    if (confirmation !== 'DELETE') {
        alert('Please type DELETE to confirm account deletion.');
        return;
    }
    try {
        const response = await fetch('/api/account/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ confirm: confirmation })
        });
        const data = await response.json();
        if (response.ok) {
            alert('Account deleted successfully.');
            window.location.href = '/';
        } else {
            alert(data.error || 'Failed to delete account.');
        }
    } catch {
        alert('An error occurred. Please try again.');
    }
}

// ── Personal Information ─────────────────────────────────────────────────────

async function updateInformation() {
    const name = document.getElementById('update-name-input').value.trim();
    const email = document.getElementById('update-email-input').value.trim();

    try {
        const response = await fetch('/api/account/information', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, email })
        });
        const data = await response.json();
        if (response.ok) {
            alert('Information updated successfully.');
        } else {
            alert(data.error || 'Failed to update information.');
        }
    } catch {
        alert('An error occurred. Please try again.');
    }
}
