// Pitching reports: narrow by date range, tick the games to build, generate every
// pitcher across the selection with a merged PDF alongside the individual ones.

const MIN_SPINNER_MS = 600;
const SLOW_SELECTION = 4;   // games, not pitchers -- each one carries a full staff

// Inline SVG rather than an <img> so the spinner picks up theme CSS variables
const SPINNER_SVG = `<svg viewBox="0 0 90 90" xmlns="http://www.w3.org/2000/svg" style="width: 48px; margin: 32px auto; display: block;" aria-label="Loading...">
  <rect x="20" y="20" width="50" height="50" fill="var(--bg-bubble)" transform="rotate(45 45 45)"/>
  <line x1="26" y1="47" x2="64" y2="47" stroke="#8B1A1A" stroke-width="1.8" stroke-linecap="round"/>
  <line x1="30" y1="53" x2="60" y2="53" stroke="#8B1A1A" stroke-width="1" stroke-linecap="round" opacity="0.5"/>
  <path d="M 45,90 L 90,45 L 45,0.5 L 0.5,45 L 45,90" fill="none" stroke="var(--text-primary)" stroke-width="2.2" stroke-linecap="butt" stroke-dasharray="0 253.44" stroke-dashoffset="253.44">
    <animate attributeName="stroke-dasharray" values="0 253.44; 126.72 126.72; 0 253.44" keyTimes="0;0.5;1" dur="5s" calcMode="spline" keySplines="0.5 0 0.5 1;0.5 0 0.5 1" repeatCount="indefinite"/>
    <animate attributeName="stroke-dashoffset" values="253.44;253.44;0" keyTimes="0;0.5;1" dur="5s" calcMode="spline" keySplines="0.5 0 0.5 1;0.5 0 0.5 1" repeatCount="indefinite"/>
  </path>
</svg>`;

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

        const result = await response.json();
        if (reportOutput) reportOutput.innerHTML = '';

        renderRunSummary(result);

        if (result.reports && result.reports.length > 0) {
            result.reports.forEach(report => renderPitcherCard(report));
        } else if (reportOutput) {
            reportOutput.innerHTML = '<p style="margin: 32px;">No reports generated.</p>';
        }

        if (result.merged_pdf_url) updateDownloadLink(true, result.merged_pdf_url);
        if (result.failed && result.failed.length) {
            toast(`${result.failed.length} pitcher(s) could not be generated.`, 'error');
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

    const count = (result.reports || []).length;
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
                📄 Download PDF
            </a>`;
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

function chartBlock(lightSrc, darkSrc, label, theme, alt, imgClass) {
    const wrapper = document.createElement('div');
    wrapper.className = 'graph-block';

    const title = document.createElement('p');
    title.className = 'graph-title';
    title.textContent = label;

    const img = document.createElement('img');
    img.dataset.lightSrc = lightSrc;
    img.dataset.darkSrc = darkSrc;
    img.src = theme === 'dark' ? darkSrc : lightSrc;
    img.alt = alt;
    img.className = `report-img ${imgClass}`;
    img.onerror = function () {
        this.parentElement.innerHTML =
            '<p style="color: var(--danger);">Chart not available. Update your subscription.</p>';
    };

    wrapper.appendChild(title);
    wrapper.appendChild(img);
    return wrapper;
}
