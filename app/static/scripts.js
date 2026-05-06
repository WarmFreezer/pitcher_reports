// Display uploaded data preview
function displayUploadData(data) {
    const contentArea = document.getElementById('uploadDataDisplay');
    if (!contentArea) return;

    const downloadButton = data.merged_pdf_url
        ? `<a href="${data.merged_pdf_url}" download="all_pitcher_reports.pdf" class="download-btn" style="text-decoration: none;">Download Full PDF</a>`
        : '';

    contentArea.innerHTML = `
        <div class="bubble">
            <h2>File Upload Summary</h2>
            <p>${data.message}</p>
            ${downloadButton}
        </div>
    `;
}

// Display game data preview
function displayGameData(data) {
    const contentArea = document.getElementById('gameDataDisplay');
    if (!contentArea) return;

    const teamsTitle = `${data.game_data.away_team} @ ${data.game_data.home_team}`;
    document.title = teamsTitle;

    contentArea.innerHTML = `
        <div style="padding: 30px; background-color: var(--secondary);">
            <h2>Game Data</h2>
            <p>Date: ${data.game_data.date}</p>
            <p>Home Team: ${data.game_data.home_team}</p>
            <p>Away Team: ${data.game_data.away_team}</p>
        </div>
    `;
}

// Load navbar
function loadNavbar() {
    const navbarHTML = `
        <nav class="main-nav">
            <ul class="nav-list">
                <li><a href="/" class="nav-link">Home</a></li>
                <li class="dropdown">
                    <a href="javascript:void(0)" class="nav-link">File ▼</a>
                    <div class="dropdown-content">
                        <a href="/upload" onclick="uploadFile(); return false;">📤 Upload</a>
                        <a href="#" id="nav-download-link" onclick="downloadPDFs(); return false;">📥 Download</a>
                    </div>
                </li>
                <li class="dropdown">
                    <a href="javascript:void(0)" class="nav-link">View ▼</a>
                    <div class="dropdown-content">
                        <a href="/report">📋 Season Report</a>
                    </div>
                </li>
                <li class="dropdown">
                    <a href="javascript:void(0)" class="nav-link">Settings ▼</a>
                    <div class="dropdown-content">
                        <a href="/account">👤 Account</a>
                        <a href="/subscription">💳 Subscription</a>
                    </div>
                </li>
                <li><a href="/about" class="nav-link">About</a></li>
                <li style="margin-left: auto;">
                    <a href="/logout" class="nav-link">
                        <button style="background: none; border: none; color: white; cursor: pointer; font-size: inherit; font-family: 'Cambria', serif; padding-right: 16px;">Logout</button>
                    </a>
                </li>
            </ul>
        </nav>
    `;
    document.getElementById('navbar-placeholder').innerHTML = navbarHTML;

    updateDownloadLink(false);
}

// Enable or disable download link
function updateDownloadLink(hasReports, downloadUrl = null)
{
    const downloadLink = document.getElementById('nav-download-link');
    if (!downloadLink) return;

    if (hasReports && downloadUrl) {
        downloadLink.style.opacity = '1.0';
        downloadLink.style.pointerEvents = 'auto';
        downloadLink.setAttribute('data-download-url', downloadUrl);
    } else {
        downloadLink.style.opacity = '0.5';
        downloadLink.style.pointerEvents = 'none';
        downloadLink.removeAttribute('data-download-url');
    }
}

// Download all PDFs
function downloadPDFs() {
    const downloadLink = document.getElementById('nav-download-link');
    const downloadUrl = downloadLink.getAttribute('data-download-url');

    if (!downloadUrl) {
        alert('No reports available for download.');
        return false;
    }

    const a = document.createElement('a');
    a.href = downloadUrl;
    a.download = '';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);

    return false;
}

// Trigger file upload
function uploadFile() {
    document.getElementById('fileUpload').click();
}

// Handle file upload
async function handleFileSelect(event) {
    const file = event.target.files[0];
    if (!file) return;

    // Show loading indicator
    const reportOutput = document.querySelector('#report-output');
    if (reportOutput) {
        reportOutput.innerHTML = '<p style="margin: 32px;">Processing file and generating reports...</p>';
    }

    const formData = new FormData();
    formData.append('file', file);
    
    try {
        const response = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            throw new Error('HTTP Error: ' + response.status);
        }

        const result = await response.json();
        
        // Enable Download link if merged PDF URL is provided
        if (result.merged_pdf_url) {
            updateDownloadLink(true, result.merged_pdf_url);
        }

        // Display upload summary
        displayUploadData({
            message: result.message,
            num_reports: result.num_reports,
            merged_pdf_url: result.merged_pdf_url
        });

        displayGameData({
            game_data: result.game_data
        });

        // Clear existing reports
        if (reportOutput) {
            reportOutput.innerHTML = '';
        }

        // Build all reports from the returned data
        if (result.reports && result.reports.length > 0) {
            buildAllReports(result.reports);
        } else {
            if (reportOutput) {
                reportOutput.innerHTML = '<p style="margin: 32px;">No reports generated.</p>';
            }
        }
    } catch (error) {
        console.error('Error uploading file:', error);
        alert('Error uploading file: ' + error.message);
        if (reportOutput) {
            reportOutput.innerHTML = `<p style="color: red; margin: 32px;">Error: ${error.message}</p>`;
        }
    }

    event.target.value = '';
}

// Build all reports from array of report data
function buildAllReports(reports) {
    reports.forEach(reportData => {
        generateReport(reportData);
    });
}

// Load header
async function loadHeader(title = "Pitcher Report", pfp = "/static/resources/HomePlate.png", logo = "/static/resources/HomePlate.png") {
    if (!await fileExists(pfp)) {
        console.warn('Profile picture not found at:', pfp);
        pfp = "/static/resources/HomePlate.png";
    }
    if (!await fileExists(logo)) {
        console.warn('Logo not found at:', logo);
        logo = "/static/resources/HomePlate.png";
    }

    const headerHTML = `
        <header class="site-header">
            <div class="header-container">
                <div class="header-left">
                    <img src=${pfp} height="128" alt="MSU Logo">
                </div>
                <div class="header-center">
                    <h1>${title}</h1>
                </div>
                <div class="header-right">
                    <img src=${logo} height="128" alt="App Icon">
                </div>
            </div>
        </header>
    `;
    document.getElementById('header-placeholder').innerHTML = headerHTML;
    // Trigger fade-in animation after content is added
    setTimeout(() => {
        const header = document.querySelector('.site-header');
        if (header) {
            header.classList.add('loaded');
        }
    }, 10);
}

// Load footer
function loadFooter() {
    const footerHTML = `
        <footer class="site-footer">
            <p style="color: white; font-family: 'Cambria', serif;">&copy; 2026 Thomas Eubank</p>
            <a href=/about style="color: white; font-family: 'Cambria', serif;">About</a>
            <a href=/terms style="color: white; margin-left: 16px; font-family: 'Cambria', serif;">Terms</a>
        </footer>
    `;
    document.getElementById('footer-placeholder').innerHTML = footerHTML;
}

// Generate a single report from template
function generateReport(data) {
    const template = document.querySelector('#pitcher-report-template');
    if (!template) {
        console.error('Template #pitcher-report-template not found');
        return;
    }

    const clone = template.content.cloneNode(true);

    // Update pitcher name
    const nameElement = clone.querySelector('.user-name');
    if (nameElement) {
        nameElement.textContent = data.pitcher_name;
    }

    // Add download pdf button for each report
    const downloadContainer = clone.querySelector('.download-container');
    if (downloadContainer) {
        if (data.pdf_url) {
            downloadContainer.innerHTML = `
                <a href="${data.pdf_url}" download="pitcher_${data.pitcher_id}_report.pdf" class="download-btn-small">
                    📄 Download PDF
                </a>
            `;
            console.log('Added download button for:', data.pitcher_name, data.pdf_url);
        } else {
            console.warn('No PDF URL provided for:', data.pitcher_name);
        }
    } else {
        console.error('Download container not found for:', data.pitcher_name);
    }

    // Add heatmap image
    const heatmapContainer = clone.querySelector('.pitcher-heatmap');
    if (heatmapContainer) {
        const img = document.createElement('img');
        img.src = data.heatmap_url;
        img.alt = `${data.pitcher_name} Heat Map`;
        img.width = 800;
        img.onerror = function() {
            console.error('Failed to load image:', this.src);
            this.alt = 'Image not available';
            this.parentElement.innerHTML = '<p style="color: red;">Heatmap image not available. Update your subscription.</p>';
        };
        heatmapContainer.appendChild(img);
    }

    // Add breakmap image
    const breakmapContainer = clone.querySelector('.pitcher-breakmap');
    if (breakmapContainer) {
        const img = document.createElement('img');
        img.src = data.breakmap_url;
        img.alt = `${data.pitcher_name} Break Map`;
        img.width = 400;
        img.onerror = function() {
            console.error('Failed to load image:', this.src);
            this.alt = 'Image not available';
            this.parentElement.innerHTML = '<p style="color: red;">Breakmap image not available. Update your subscription.</p>';
        };
        breakmapContainer.appendChild(img);
    }

    // Add pitcher table
    const tableContainer = clone.querySelector('.pitcher-table');
    if (tableContainer && data.pitcher_table) {
        tableContainer.innerHTML = data.pitcher_table;
        tableContainer.style.fontSize = '12px';
    }

    // Add pitch usage table
    const leftUsageContainer = clone.querySelector('.left-usage');
    if (leftUsageContainer && data.left_usage_table) {
        leftUsageContainer.innerHTML = data.left_usage_table;
        leftUsageContainer.style.fontSize = '12px';
        leftUsageContainer.style.borderCollapse = 'collapse';
    }

    const rightUsageContainer = clone.querySelector('.right-usage');
    if (rightUsageContainer && data.right_usage_table) {
        rightUsageContainer.innerHTML = data.right_usage_table;
        rightUsageContainer.style.fontSize = '12px';
        rightUsageContainer.style.borderCollapse = 'collapse';
    }

    const newLine = document.createElement('br');
    clone.appendChild(newLine);
    
    const reportOutputElement = document.querySelector('#report-output');
    if (reportOutputElement) {
        reportOutputElement.appendChild(clone);
    }
}

// Manage open/close dropdown
function dropdownInit() {
    const picker = document.querySelector('.school-picker');
    const trigger = document.getElementById('school-trigger');
    const hidden = document.getElementById('school-value');
    const options = document.querySelectorAll('.school-option');

    if (!picker || !trigger || !hidden || options.length === 0) return;

    trigger.addEventListener('click', () => picker.classList.toggle('open'));

    options.forEach(btn => {
        btn.addEventListener('click', () => {
        const name = btn.dataset.school;
        hidden.value = name;
        trigger.textContent = `${name} ▼`;
        picker.classList.remove('open');
        });
    });

    document.addEventListener('click', (e) => {
        if (!picker.contains(e.target)) picker.classList.remove('open');
    });
}

// Change Password form toggle
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

async function startSubscription() {
    try {
        const response = await fetch('/api/subscription/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await response.json();
        if (response.ok) {
            if (data.reactivated) {
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

// ── Roster table ────────────────────────────────────────────────────────────

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

function escapeAttr(v) {
    return String(v ?? '').replace(/&/g, '&amp;').replace(/"/g, '&quot;');
}

function buildRosterRow(row, columns) {
    const trackmanId = row[columns[0]] ?? '';
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

function toggleSection(id, heading) {
    const el = document.getElementById(id);
    el.classList.toggle('open');
    heading.classList.toggle('open');
}

(function () {
    if (document.getElementById('roster-table-container')) {
        window._schoolSlug = document.body.dataset.schoolSlug || '';
        loadRoster();
    }
})();

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

// api/subscription/roster
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

async function updateInformation() {
    const name = document.getElementById('update-name-input').value.trim();
    const email = document.getElementById('update-email-input').value.trim();

    try {
        const response = await fetch('/api/account/information', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name, email: email })
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

// FAB — stop following scroll once footer is visible
(function () {
    const fab = document.querySelector('.save-fab');
    if (!fab) return;

    function updateFab() {
        const footer = document.getElementById('footer-placeholder');
        if (!footer) return;
        const footerTop = footer.getBoundingClientRect().top;
        const margin = 32;
        fab.style.bottom = Math.max(margin, window.innerHeight - footerTop + margin) + 'px';
    }

    window.addEventListener('scroll', updateFab, { passive: true });
    updateFab();
})();

// File Exists
async function fileExists(url) {
    try {
        const response = await fetch(url, { method: 'HEAD' });
        return response.ok; // true if 200-299
    } catch {
        return false;
    }
}
