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
        toast('Please fill in both fields.', 'error');
        return;
    }
    if (newPassword.length < 8) {
        toast('New password must be at least 8 characters.', 'error');
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
            toast('Password updated successfully.', 'success');
            hidePasswordForm();
        } else {
            toast(data.error || 'Failed to update password.', 'error');
        }
    } catch {
        toast('An error occurred. Please try again.', 'error');
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
        toast('Please type DELETE to confirm account deletion.', 'error');
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
            toast('Account deleted successfully.', 'success');
            setTimeout(() => window.location.href = '/', 1500);
        } else {
            toast(data.error || 'Failed to delete account.', 'error');
        }
    } catch {
        toast('An error occurred. Please try again.', 'error');
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
            toast('Information updated successfully.', 'success');
        } else {
            toast(data.error || 'Failed to update information.', 'error');
        }
    } catch {
        toast('An error occurred. Please try again.', 'error');
    }
}
