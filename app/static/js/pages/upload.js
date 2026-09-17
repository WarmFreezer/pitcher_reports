// Upload page: validate a TrackMan file, confirm what it contains, save it to the
// archive, and manage what has already been saved. Report generation lives on
// /pitching and /batting, which read from that archive.

const MIN_SPINNER_MS = 600;

document.addEventListener('DOMContentLoaded', loadSavedGames);

// Trigger file upload
function uploadFile() {
    document.getElementById('fileUpload').click();
}

async function handleFileSelect(event) {
    const file = event.target.files[0];
    if (!file) return;

    const summary = document.getElementById('uploadSummary');
    const spinnerStart = Date.now();
    if (summary) summary.innerHTML = SPINNER_SVG;

    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch('/api/upload', { method: 'POST', body: formData });

        const elapsed = Date.now() - spinnerStart;
        if (elapsed < MIN_SPINNER_MS) await new Promise(r => setTimeout(r, MIN_SPINNER_MS - elapsed));

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            toast(err.error || 'An error occurred while processing the file.', 'error');
            if (summary) summary.innerHTML = '';
            return;
        }

        renderUploadSummary(await response.json());
    } catch (error) {
        console.error('Error uploading file:', error);
        toast('Error uploading file: ' + error.message, 'error');
        if (summary) summary.innerHTML = '';
    } finally {
        // Clearing lets the same file be re-picked, which would otherwise no-op
        event.target.value = '';
    }
}

// Shows what the file contains so the user can confirm before committing it
function renderUploadSummary(data) {
    const area = document.getElementById('uploadSummary');
    if (!area) return;

    const g = data.game_data;
    document.title = `${g.away_team} @ ${g.home_team}`;

    const warning = data.already_saved
        ? '<p style="color: var(--warn);">This game is already in your archive. Saving again will not duplicate it.</p>'
        : '';

    area.innerHTML = `
        <div class="bubble" style="display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap;">
            <div>
                <h2>${g.away_team} @ ${g.home_team}</h2>
                <p>${g.date}</p>
                <p class="filter-note">${g.pitches} pitches · ${g.pitchers} pitchers · ${g.batters} batters</p>
                ${warning}
            </div>
            <div style="display: flex; gap: 12px; flex-wrap: wrap; align-items: center;">
                <button id="save-game-btn" class="upload-btn" onclick="saveGame()">Save Game</button>
            </div>
        </div>`;
}

async function saveGame() {
    const btn = document.getElementById('save-game-btn');
    const practice = document.getElementById('practiceToggle')?.checked === true;

    if (btn) {
        btn.disabled = true;
        btn.textContent = 'Saving…';
    }

    try {
        const res = await fetch('/api/save-game', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ practice }),
        });
        const data = await res.json();

        if (!res.ok) {
            toast(data.error || 'Failed to save game.', 'error');
            if (btn) {
                btn.disabled = false;
                btn.textContent = 'Save Game';
            }
            return;
        }

        toast(data.message, data.duplicate ? 'info' : 'success');
        if (btn) btn.textContent = data.duplicate ? 'Already Saved' : 'Saved';
        loadSavedGames();
    } catch (e) {
        toast('Error saving game: ' + e.message, 'error');
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Save Game';
        }
    }
}

// ---------------------------------------------------------------- manager

async function loadSavedGames() {
    const area = document.getElementById('savedGames');
    const count = document.getElementById('savedCount');
    if (!area) return;

    try {
        const res = await fetch('/api/games');
        if (!res.ok) throw new Error('Could not load saved games');
        const games = (await res.json()).games || [];

        if (count) {
            count.textContent = games.length
                ? `${games.length} game${games.length === 1 ? '' : 's'}`
                : '';
        }

        if (games.length === 0) {
            area.innerHTML = '<p class="filter-note">No games saved yet. Upload a file to get started.</p>';
            return;
        }

        // Newest first -- the archive returns ascending, which is right for the
        // report pickers but backwards for a management list.
        const rows = [...games].reverse().map(g => `
            <tr>
                <td>${formatDate(g.date)}</td>
                <td>${g.label}${g.practice ? ' <span class="row-badge">Practice</span>' : ''}</td>
                <td>${g.pitcher_count}</td>
                <td>${g.batter_count}</td>
                <td style="text-align: right;">
                    <button class="download-btn-small btn-danger"
                            onclick="deleteGame('${g.content_hash}', '${formatDate(g.date)}')">Delete</button>
                </td>
            </tr>`).join('');

        area.innerHTML = `
            <table class="pitcher-data-table table-compact">
                <thead>
                    <tr><th>Date</th><th>Game</th><th>Pitchers</th><th>Batters</th><th></th></tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>`;
    } catch (error) {
        console.error('Error loading saved games:', error);
        area.innerHTML = '<p class="filter-note">Could not load saved games.</p>';
    }
}

function formatDate(iso) {
    const [y, m, d] = (iso || '').split('-');
    return y ? `${m}/${d}/${y}` : iso;
}

async function deleteGame(contentHash, label) {
    // Deleting drops the archived file and the season stats together, so confirm
    if (!confirm(`Delete the game from ${label}?\n\nThis removes its reports and its season stats.`)) {
        return;
    }

    try {
        const res = await fetch(`/api/games/${contentHash}`, { method: 'DELETE' });
        const data = await res.json();

        if (!res.ok) {
            toast(data.error || 'Could not delete the game.', 'error');
            return;
        }

        toast(data.message || 'Game deleted.', 'success');
        loadSavedGames();
    } catch (error) {
        toast('Error deleting game: ' + error.message, 'error');
    }
}
