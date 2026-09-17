// Pitching reports: narrow by date range, tick the games to build, generate every
// pitcher across the selection with a merged PDF alongside the individual ones.

const MIN_SPINNER_MS = 600;
const SLOW_SELECTION = 4;   // games, not pitchers -- each one carries a full staff

let archiveBounds = { first: null, last: null };
let reloadTimer = null;

document.addEventListener('DOMContentLoaded', async () => {
    // First call carries no dates, purely to learn the archive's bounds so the
    // pickers can be seeded before the real, range-filtered fetch.
    await loadGames({ seedDates: true });

    for (const id of ['startDate', 'endDate']) {
        document.getElementById(id)?.addEventListener('change', () => {
            clearTimeout(reloadTimer);
            reloadTimer = setTimeout(() => loadGames(), 150);
        });
    }
});

function currentFilters() {
    return {
        target: document.getElementById('targetToggle')?.checked ? 'opponent' : 'own',
        start_date: document.getElementById('startDate')?.value || '',
        end_date: document.getElementById('endDate')?.value || '',
    };
}

async function loadGames({ seedDates = false } = {}) {
    const list = document.getElementById('gameList');
    const info = document.getElementById('archiveInfo');
    const filters = currentFilters();

    if (list) list.innerHTML = '<p class="filter-note">Loading…</p>';

    const params = new URLSearchParams();
    if (!seedDates) {
        if (filters.start_date) params.set('start_date', filters.start_date);
        if (filters.end_date) params.set('end_date', filters.end_date);
    }

    try {
        const response = await fetch(`/api/pitching/games?${params.toString()}`);
        if (!response.ok) throw new Error('Could not load games');
        const data = await response.json();

        if (seedDates) {
            archiveBounds = { first: data.first_date, last: data.last_date };
            seedDateInputs();
            if (info) {
                info.textContent = data.game_count
                    ? `${data.game_count} game${data.game_count === 1 ? '' : 's'} saved, ${data.first_date} through ${data.last_date}.`
                    : 'No games saved yet. Upload a game file and save it to build your archive.';
            }
            if (data.game_count) return loadGames();
        }

        renderGameList(data.games || []);
    } catch (error) {
        console.error('Error loading games:', error);
        toast('Could not load games.', 'error');
        if (list) list.innerHTML = '<p class="filter-note">Unavailable.</p>';
        updateSelectionCount();
    }
}

function seedDateInputs() {
    const start = document.getElementById('startDate');
    const end = document.getElementById('endDate');
    if (!archiveBounds.first || !archiveBounds.last) return;

    // Bound the pickers to what the archive actually holds
    for (const input of [start, end]) {
        if (!input) continue;
        input.min = archiveBounds.first;
        input.max = archiveBounds.last;
    }
    if (start && !start.value) start.value = archiveBounds.first;
    if (end && !end.value) end.value = archiveBounds.last;
}

function renderGameList(games) {
    const list = document.getElementById('gameList');
    if (!list) return;

    if (games.length === 0) {
        list.innerHTML = '<p class="filter-note">No games in this range.</p>';
        updateSelectionCount();
        return;
    }

    // All checked by default -- generating the selected window is the common case
    list.innerHTML = games.map(g => `
        <label class="checkbox-row">
            <input type="checkbox" class="game-check" value="${g.content_hash}" checked
                   onchange="updateSelectionCount()">
            <span class="row-label">${formatDate(g.date)} &nbsp; ${g.label}</span>
            ${g.practice ? '<span class="row-badge">Practice</span>' : ''}
            <span class="row-meta">${g.pitcher_count} P · ${g.batter_count} B</span>
        </label>`).join('');

    updateSelectionCount();
}

function formatDate(iso) {
    const [y, m, d] = (iso || '').split('-');
    return y ? `${m}/${d}/${y}` : iso;
}

function setAllGames(checked) {
    document.querySelectorAll('.game-check').forEach(box => { box.checked = checked; });
    updateSelectionCount();
}

function selectedGameHashes() {
    return Array.from(document.querySelectorAll('.game-check:checked')).map(box => box.value);
}

function updateSelectionCount() {
    const label = document.getElementById('selectionCount');
    if (!label) return;
    const n = selectedGameHashes().length;
    label.textContent = n ? `${n} game${n === 1 ? '' : 's'} selected` : 'No games selected';
}

async function generatePitchingReports() {
    const hashes = selectedGameHashes();
    if (hashes.length === 0) {
        toast('Select at least one game.', 'error');
        return;
    }

    if (hashes.length > SLOW_SELECTION) {
        toast('This might take a minute…', 'info');
    }

    const payload = { content_hashes: hashes, target: currentFilters().target };

    const reportOutput = document.querySelector('#report-output');
    const summaryArea = document.getElementById('pitchingSummary');
    const button = document.getElementById('generateBtn');
    const spinnerStart = Date.now();

    if (reportOutput) reportOutput.innerHTML = SPINNER_SVG;
    if (summaryArea) summaryArea.innerHTML = '';
    if (button) button.disabled = true;

    let reportCount = 0;

    try {
        const response = await fetch('/api/pitching/report', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });

        const elapsed = Date.now() - spinnerStart;
        if (elapsed < MIN_SPINNER_MS) await new Promise(r => setTimeout(r, MIN_SPINNER_MS - elapsed));

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            toast(err.error || 'Could not generate reports.', 'error');
            if (reportOutput) reportOutput.innerHTML = '';
            return;
        }

        if (reportOutput) reportOutput.innerHTML = '';

        // Server streams one NDJSON line per pitcher as their report finishes
        // (built in parallel), plus a final 'done' line -- render each card as
        // its line arrives instead of waiting for the whole staff.
        for await (const msg of readNdjson(response)) {
            if (msg.type === 'report') {
                renderPitcherCard(msg);
                reportCount++;
            } else if (msg.type === 'done') {
                renderRunSummary({ ...msg, count: reportCount });
                if (msg.merged_pdf_url) updateDownloadLink(true, msg.merged_pdf_url);
                if (msg.failed && msg.failed.length) {
                    toast(`${msg.failed.length} pitcher(s) could not be generated.`, 'error');
                }
            }
        }

        if (reportCount === 0 && reportOutput) {
            reportOutput.innerHTML = '<p style="margin: 32px;">No reports generated.</p>';
        }
    } catch (error) {
        console.error('Error generating pitching reports:', error);
        toast('Error generating reports: ' + error.message, 'error');
        if (reportOutput) reportOutput.innerHTML = '';
    } finally {
        if (button) button.disabled = false;
    }
}

function renderRunSummary(result) {
    const area = document.getElementById('pitchingSummary');
    if (!area) return;

    const count = result.count ?? 0;
    const mergedButton = result.merged_pdf_url
        ? `<a href="${result.merged_pdf_url}" class="download-btn" download style="text-decoration: none;">Download All (${count})</a>`
        : '';

    area.innerHTML = `
        <div class="bubble" style="display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap;">
            <div>
                <h2>${count} Pitcher Report${count === 1 ? '' : 's'}</h2>
                <p>${result.date_range} · ${result.games} game${result.games === 1 ? '' : 's'} · ${result.opponent}</p>
            </div>
            <div style="display: flex; gap: 12px; flex-wrap: wrap; align-items: center;">${mergedButton}</div>
        </div>`;
}

// Stamps one pitcher's data into the hidden <template> and appends the clone
function renderPitcherCard(data) {
    const template = document.querySelector('#pitcher-report-template');
    if (!template) {
        console.error('Template #pitcher-report-template not found');
        return;
    }

    const clone = template.content.cloneNode(true);
    clone.querySelector('.user-name').textContent = data.pitcher_name;

    const downloadContainer = clone.querySelector('.download-container');
    if (downloadContainer && data.pdf_url) {
        downloadContainer.innerHTML = `
            <a href="${data.pdf_url}" download class="download-btn-small">
                ${_fileIcon()} Download PDF
            </a>`;
        if (data.pitch_by_pitch_url) {
            downloadContainer.innerHTML += `
                <a href="${data.pitch_by_pitch_url}" download class="download-btn-small">
                    ${_listIcon()} Pitch-by-Pitch
                </a>`;
        }
    }

    // data-light-src / data-dark-src let core.js _swapChartImages() react to the theme toggle
    const currentTheme = document.documentElement.getAttribute('data-theme') ?? 'light';

    const heatmapContainer = clone.querySelector('.pitcher-heatmap');
    if (heatmapContainer) {
        for (const [lightSrc, darkSrc, label] of [
            [data.heatmap_left_url, data.heatmap_left_dark_url, 'vs Left-Handed Batters'],
            [data.heatmap_right_url, data.heatmap_right_dark_url, 'vs Right-Handed Batters'],
        ]) {
            heatmapContainer.appendChild(
                chartBlock(lightSrc, darkSrc, label, currentTheme,
                           `${data.pitcher_name} Heat Map ${label}`, 'report-img-heatmap'));
        }
    }

    const breakmapContainer = clone.querySelector('.pitcher-breakmap');
    if (breakmapContainer) {
        const title = data.arm_angle ? `Pitch Break — Arm Angle: ${data.arm_angle}` : 'Pitch Break';
        breakmapContainer.appendChild(
            chartBlock(data.breakmap_url, data.breakmap_dark_url, title, currentTheme,
                       `${data.pitcher_name} Break Map`, 'report-img-breakmap'));
    }

    clone.querySelector('.pitcher-table').innerHTML = data.pitcher_table || '';
    clone.querySelector('.left-usage').innerHTML = data.left_usage_table || '';
    clone.querySelector('.right-usage').innerHTML = data.right_usage_table || '';

    // Custom stats from the school's own uploaded report script, if any --
    // most schools have none, so the section stays hidden.
    const hasCustom = data.custom_stats || (data.custom_pitch_type_stats_tables && data.custom_pitch_type_stats_tables.length);
    if (hasCustom) {
        const customSection = clone.querySelector('.custom-stats-section');
        if (customSection) customSection.hidden = false;
        renderStatTiles(clone.querySelector('.custom-stats'), data.custom_stats);

        const pitchTypeContainer = clone.querySelector('.custom-pitch-type-stats');
        if (pitchTypeContainer && data.custom_pitch_type_stats_tables) {
            for (const { title, html } of data.custom_pitch_type_stats_tables) {
                const section = document.createElement('div');
                section.className = 'table-section';
                section.style.cssText = 'max-width:1200px; margin: 8px auto;';
                section.innerHTML = `<p class="graph-title">${title}</p><div class="table-scroll">${html}</div>`;
                pitchTypeContainer.appendChild(section);
            }
        }
    }

    const header = clone.querySelector('.report-card-header');
    const body = clone.querySelector('.report-card-body');
    header.addEventListener('click', (event) => {
        // The download link lives inside the header; don't toggle when it's clicked
        if (event.target.closest('a')) return;
        const isOpen = body.classList.toggle('open');
        header.classList.toggle('open', isOpen);
    });

    document.querySelector('#report-output')?.appendChild(clone);
}
