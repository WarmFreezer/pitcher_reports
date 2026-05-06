// ── Color picker ─────────────────────────────────────────────────────────────

const COLOR_TOKENS = ['primary', 'secondary', 'tertiary', 'dark', 'light', 'accent'];
const HEX_RE = /^#[0-9a-fA-F]{6}$/;

function syncColor(token, value) {
    document.getElementById('color-' + token + '-text').value = value;
    document.documentElement.style.setProperty('--' + token, value);
    document.getElementById('color-card-' + token).style.backgroundColor = value;
}

function syncColorText(token, value) {
    if (HEX_RE.test(value)) {
        document.getElementById('color-' + token).value = value;
        document.documentElement.style.setProperty('--' + token, value);
        document.getElementById('color-card-' + token).style.backgroundColor = value;
    }
}

// ── Save ─────────────────────────────────────────────────────────────────────

async function saveSubscription() {
    const colors = {};
    for (const token of COLOR_TOKENS) {
        const el = document.getElementById('color-' + token + '-text');
        if (!el) continue;
        const value = el.value.trim();
        if (!HEX_RE.test(value)) {
            alert(`Invalid hex color for ${token}: "${value}"`);
            return;
        }
        colors[token] = value;
    }

    // Fire all saves in parallel — each resolves to { ok, data, label } so errors can be reported by name
    const saves = [];

    if (Object.keys(colors).length === COLOR_TOKENS.length) {
        saves.push(
            fetch('/api/subscription/rebrand', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ colors })
            }).then(r => r.json().then(d => ({ ok: r.ok, data: d, label: 'Branding' })))
        );
    }

    const adminEmail = document.getElementById('admin-email');
    if (adminEmail) {
        saves.push(
            fetch('/api/subscription/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ admin_email: adminEmail.value.trim() })
            }).then(r => r.json().then(d => ({ ok: r.ok, data: d, label: 'Settings' })))
        );
    }

    const rosterPayload = collectRoster();
    if (rosterPayload) {
        saves.push(
            fetch('/api/subscription/roster', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(rosterPayload)
            }).then(r => r.json().then(d => ({ ok: r.ok, data: d, label: 'Roster' })))
        );
    }

    try {
        const results = await Promise.all(saves);
        const failed = results.filter(r => !r.ok);
        if (failed.length) {
            alert(failed.map(r => `${r.label}: ${r.data.error}`).join('\n'));
        } else {
            alert('Saved successfully.');
        }
    } catch {
        alert('An error occurred. Please try again.');
    }
}

// ── Logo upload ───────────────────────────────────────────────────────────────

async function handleLogoUpload(event) {
    const file = event.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch('/api/subscription/logo', {
            method: 'POST',
            body: formData
        });
        const data = await response.json();
        if (response.ok) {
            const url = data.logo_url + '?t=' + Date.now();
            const preview = document.getElementById('logo-preview');
            if (preview) preview.src = url;
            const headerLogo = document.querySelector('.header-right img');
            if (headerLogo) headerLogo.src = url;
        } else {
            alert(data.error || 'Failed to upload logo.');
        }
    } catch {
        alert('An error occurred. Please try again.');
    }

    event.target.value = '';
}

// ── Roster table ──────────────────────────────────────────────────────────────

let _rosterColumns = [];

async function loadRoster() {
    const container = document.getElementById('roster-table-container');
    if (!container) return;
    try {
        const response = await fetch('/api/subscription/roster');
        const data = await response.json();
        if (response.ok) {
            _rosterColumns = data.columns;
            renderRosterTable(data.roster, data.columns);
        }
    } catch {
        container.innerHTML = '<p style="color:red;">Failed to load roster.</p>';
    }
}

function renderRosterTable(roster, columns) {
    const container = document.getElementById('roster-table-container');
    if (!container) return;

    if (!columns || columns.length === 0) {
        container.innerHTML = '<p style="color: var(--dark); margin-bottom: 8px;">No roster uploaded yet.</p>';
        return;
    }

    const headerCells = ['Photo', ...columns, ''].map(c => `<th>${c}</th>`).join('');
    const rows = roster.map(row => buildRosterRow(row, columns)).join('');

    container.innerHTML = `
        <div class="roster-scroll">
            <table class="roster-table">
                <thead><tr>${headerCells}</tr></thead>
                <tbody id="roster-body">${rows}</tbody>
            </table>
        </div>`;
}

// Sanitise values before inserting into HTML attribute strings built with template literals
function escapeAttr(v) {
    return String(v ?? '').replace(/&/g, '&amp;').replace(/"/g, '&quot;');
}

function buildRosterRow(row, columns) {
    const trackmanId = row[columns[0]] ?? '';
    // Cache-busting timestamp prevents the browser from serving a stale 404 after a new pfp is uploaded
    const pfpUrl = `/storage/schools/${window._schoolSlug}/assets/players/${trackmanId}/pfp.png?t=${Date.now()}`;

    const pfpCell = `
        <td class="pfp-cell">
            <img class="player-pfp" src="${pfpUrl}" onerror="this.src='/static/resources/HomePlate.png'">
            <input type="file" accept=".png,.jpg,.jpeg" style="display:none"
                   onchange="uploadPlayerPfp('${trackmanId}', this)">
            <span class="pfp-edit" onclick="this.previousElementSibling.click()">✎</span>
        </td>`;

    const dataCells = columns.map(col =>
        `<td><input class="roster-input" value="${escapeAttr(row[col])}" data-col="${escapeAttr(col)}"></td>`
    ).join('');

    const deleteCell = `<td><button class="roster-delete-btn" onclick="deleteRosterRow(this)">×</button></td>`;

    return `<tr>${pfpCell}${dataCells}${deleteCell}</tr>`;
}

function addRosterRow() {
    const tbody = document.getElementById('roster-body');
    if (!tbody || _rosterColumns.length === 0) return;
    const emptyRow = Object.fromEntries(_rosterColumns.map(c => [c, '']));
    tbody.insertAdjacentHTML('beforeend', buildRosterRow(emptyRow, _rosterColumns));
}

function deleteRosterRow(btn) {
    btn.closest('tr').remove();
}

function collectRoster() {
    const tbody = document.getElementById('roster-body');
    if (!tbody || _rosterColumns.length === 0) return null;
    const rows = Array.from(tbody.querySelectorAll('tr')).map(tr => {
        const inputs = tr.querySelectorAll('.roster-input');
        const row = {};
        inputs.forEach(input => { row[input.dataset.col] = input.value; });
        return row;
    });
    return { columns: _rosterColumns, rows };
}

async function uploadPlayerPfp(playerId, fileInput) {
    if (!playerId || !fileInput.files[0]) return;
    const formData = new FormData();
    formData.append('file', fileInput.files[0]);
    try {
        const response = await fetch(`/api/subscription/roster/pfp/${playerId}`, {
            method: 'POST',
            body: formData
        });
        const data = await response.json();
        if (response.ok) {
            const img = fileInput.closest('td').querySelector('.player-pfp');
            if (img) img.src = data.pfp_url + '?t=' + Date.now();
        } else {
            alert(data.error || 'Failed to upload profile picture.');
        }
    } catch {
        alert('An error occurred. Please try again.');
    }
    fileInput.value = '';
}

async function handleFolderUpload(event) {
    const files = Array.from(event.target.files).filter(f =>
        /\.(png|jpe?g)$/i.test(f.name)
    );
    if (!files.length) {
        alert('No PNG or JPG images found in the selected folder.');
        event.target.value = '';
        return;
    }

    const formData = new FormData();
    files.forEach(f => formData.append('files', f));

    try {
        const response = await fetch('/api/subscription/roster/pfp/bulk', {
            method: 'POST',
            body: formData
        });
        const data = await response.json();
        if (response.ok) {
            let msg = data.message;
            if (data.unmatched && data.unmatched.length) {
                msg += `\n\nUnmatched files:\n${data.unmatched.join('\n')}`;
            }
            alert(msg);
            loadRoster();
        } else {
            alert(data.error || 'Failed to upload photos.');
        }
    } catch {
        alert('An error occurred. Please try again.');
    }

    event.target.value = '';
}

async function uploadRoster() {
    const fileInput = document.getElementById('roster-upload');
    if (!fileInput) return;

    const file = fileInput.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);
    try {
        const response = await fetch('/api/subscription/roster', {
            method: 'POST',
            body: formData
        });
        const data = await response.json();
        if (response.ok) {
            alert('Roster uploaded successfully.');
        } else {
            alert(data.error || 'Failed to upload roster.');
        }
    } catch {
        alert('An error occurred. Please try again.');
    }

    fileInput.value = '';
}

// ── Section toggle ────────────────────────────────────────────────────────────

function toggleSection(id, heading) {
    const el = document.getElementById(id);
    el.classList.toggle('open');
    heading.classList.toggle('open');
}

// ── Subscription management ───────────────────────────────────────────────────

async function startSubscription() {
    try {
        const response = await fetch('/api/subscription/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await response.json();
        if (response.ok) {
            if (data.reactivated) {
                // Subscription was still alive (cancel_at_period_end) — just undo the cancellation
                alert(data.message);
                window.location.reload();
            } else {
                window.location.href = `/checkout?client_secret=${data.client_secret}`;
            }
        } else {
            alert(data.error || 'Failed to start subscription.');
        }
    } catch {
        alert('An error occurred. Please try again.');
    }
}

function showCancelForm() {
    document.getElementById('cancel-subscription-btn-wrap').style.display = 'none';
    document.getElementById('cancel-subscription-form').classList.add('open');
    document.getElementById('cancel-confirm-input').focus();
}

function hideCancelForm() {
    document.getElementById('cancel-subscription-btn-wrap').style.display = 'block';
    document.getElementById('cancel-subscription-form').classList.remove('open');
    document.getElementById('cancel-confirm-input').value = '';
}

async function cancelSubscription() {
    const confirmation = document.getElementById('cancel-confirm-input').value.trim();
    if (confirmation !== 'CANCEL') {
        alert('Please type CANCEL to confirm.');
        return;
    }
    try {
        const response = await fetch('/api/subscription/cancel', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await response.json();
        if (response.ok) {
            alert(data.message);
            if (!data.permanent) window.location.href = '/dashboard';
        } else {
            alert(data.error || 'Failed to cancel subscription.');
        }
    } catch {
        alert('An error occurred. Please try again.');
    }
}

// ── Init ──────────────────────────────────────────────────────────────────────

// Roster auto-load — reads school slug from the body data attribute set by the template
(function () {
    if (document.getElementById('roster-table-container')) {
        window._schoolSlug = document.body.dataset.schoolSlug || '';
        loadRoster();
    }
})();

// FAB — stop following scroll once footer is visible
(function () {
    const fab = document.querySelector('.save-fab');
    if (!fab) return;

    function updateFab() {
        const footer = document.getElementById('footer-placeholder');
        if (!footer) return;
        const footerTop = footer.getBoundingClientRect().top;
        const margin = 32;
        // When the footer scrolls into the bottom margin zone, push the FAB up by the overlap amount
        fab.style.bottom = Math.max(margin, window.innerHeight - footerTop + margin) + 'px';
    }

    window.addEventListener('scroll', updateFab, { passive: true });
    updateFab();
})();
