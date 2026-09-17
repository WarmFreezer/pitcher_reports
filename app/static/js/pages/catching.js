// Catching reports: pick a time frame, tick the catchers to build, generate
// them all at once with a merged PDF alongside the individual ones. Mirrors
// batting.js's shape (a date-range picker, not the pitching page's per-game
// checkbox list).

const MIN_SPINNER_MS = 600;
const SLOW_SELECTION = 10;   // past this many catchers, warn before the wait

let archiveBounds = { first: null, last: null };
let reloadTimer = null;

document.addEventListener('DOMContentLoaded', async () => {
    // First call has no dates, purely to learn the archive's bounds so the
    // pickers can be seeded before the real, range-filtered fetch.
    await loadCatchers({ seedDates: true });

    document.getElementById('targetToggle')?.addEventListener('change', () => loadCatchers());
    for (const id of ['startDate', 'endDate']) {
        document.getElementById(id)?.addEventListener('change', () => {
            clearTimeout(reloadTimer);
            reloadTimer = setTimeout(() => loadCatchers(), 150);
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

async function loadCatchers({ seedDates = false } = {}) {
    const list = document.getElementById('catcherList');
    const info = document.getElementById('archiveInfo');
    const filters = currentFilters();

    if (list) list.innerHTML = '<p class="filter-note">Loading…</p>';

    const params = new URLSearchParams({ target: filters.target });
    if (!seedDates) {
        if (filters.start_date) params.set('start_date', filters.start_date);
        if (filters.end_date) params.set('end_date', filters.end_date);
    }

    try {
        const response = await fetch(`/api/catching/catchers?${params.toString()}`);
        if (!response.ok) throw new Error('Could not load catchers');
        const data = await response.json();

        if (seedDates) {
            archiveBounds = { first: data.first_date, last: data.last_date };
            seedDateInputs();
            if (info) {
                info.textContent = data.game_count
                    ? `${data.game_count} game${data.game_count === 1 ? '' : 's'} saved, ${data.first_date} through ${data.last_date}.`
                    : 'No games saved yet. Upload a game file and choose Save Game to build your archive.';
            }
            // Re-fetch now that the pickers carry a real range
            if (data.game_count) return loadCatchers();
        }

        renderCatcherList(data.catchers || []);
    } catch (error) {
        console.error('Error loading catchers:', error);
        toast('Could not load catchers.', 'error');
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

function renderCatcherList(catchers) {
    const list = document.getElementById('catcherList');
    if (!list) return;

    if (catchers.length === 0) {
        list.innerHTML = '<p class="filter-note">No catchers in this range.</p>';
        updateSelectionCount();
        return;
    }

    // All checked by default -- generating the whole roster is the common case
    list.innerHTML = catchers.map(c => `
        <label class="checkbox-row">
            <input type="checkbox" class="catcher-check" value="${c.id}" checked
                   onchange="updateSelectionCount()">
            <span class="row-label">${c.name}</span>
            <span class="row-meta">${c.games}G</span>
        </label>`).join('');

    updateSelectionCount();
}

function setAllCatchers(checked) {
    document.querySelectorAll('.catcher-check').forEach(box => { box.checked = checked; });
    updateSelectionCount();
}

function selectedCatcherIds() {
    return Array.from(document.querySelectorAll('.catcher-check:checked')).map(box => box.value);
}

function updateSelectionCount() {
    const label = document.getElementById('selectionCount');
    if (!label) return;
    const n = selectedCatcherIds().length;
    label.textContent = n ? `${n} catcher${n === 1 ? '' : 's'} selected` : 'No catchers selected';
}

async function generateCatchingReports() {
    const catcherIds = selectedCatcherIds();
    if (catcherIds.length === 0) {
        toast('Select at least one catcher.', 'error');
        return;
    }

    if (catcherIds.length > SLOW_SELECTION) {
        toast('This might take a minute…', 'info');
    }

    const filters = currentFilters();
    const payload = { catcher_ids: catcherIds, ...filters };

    const reportOutput = document.querySelector('#report-output');
    const summaryArea = document.getElementById('catchingSummary');
    const button = document.getElementById('generateBtn');
    const spinnerStart = Date.now();

    if (reportOutput) reportOutput.innerHTML = SPINNER_SVG;
    if (summaryArea) summaryArea.innerHTML = '';
    if (button) button.disabled = true;

    let reportCount = 0;

    try {
        const response = await fetch('/api/catching/report', {
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

        // Server streams one NDJSON line per catcher as their report finishes
        // (built in parallel), plus a final 'done' line -- render each card as
        // its line arrives instead of waiting for the whole selection.
        for await (const msg of readNdjson(response)) {
            if (msg.type === 'report') {
                renderCatcherCard(msg);
                reportCount++;
            } else if (msg.type === 'done') {
                renderRunSummary({ ...msg, count: reportCount });
                if (msg.merged_pdf_url) updateDownloadLink(true, msg.merged_pdf_url);
                if (msg.failed && msg.failed.length) {
                    toast(`${msg.failed.length} catcher(s) could not be generated.`, 'error');
                }
            }
        }

        if (reportCount === 0 && reportOutput) {
            reportOutput.innerHTML = '<p style="margin: 32px;">No reports generated.</p>';
        }
    } catch (error) {
        console.error('Error generating catching reports:', error);
        toast('Error generating reports: ' + error.message, 'error');
        if (reportOutput) reportOutput.innerHTML = '';
    } finally {
        if (button) button.disabled = false;
    }
}

function renderRunSummary(result) {
    const area = document.getElementById('catchingSummary');
    if (!area) return;

    const count = result.count ?? 0;
    const mergedButton = result.merged_pdf_url
        ? `<a href="${result.merged_pdf_url}" class="download-btn" download style="text-decoration: none;">Download All (${count})</a>`
        : '';

    area.innerHTML = `
        <div class="bubble" style="display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap;">
            <div>
                <h2>${count} Catcher Report${count === 1 ? '' : 's'}</h2>
                <p>${result.date_range}</p>
            </div>
            <div style="display: flex; gap: 12px; flex-wrap: wrap; align-items: center;">${mergedButton}</div>
        </div>`;
}


// Stamps one catcher's data into the hidden <template> and appends the clone
function renderCatcherCard(data) {
    const template = document.querySelector('#catcher-report-template');
    if (!template) {
        console.error('Template #catcher-report-template not found');
        return;
    }

    const clone = template.content.cloneNode(true);

    clone.querySelector('.user-name').textContent = data.catcher_name;

    const downloadContainer = clone.querySelector('.download-container');
    if (downloadContainer && data.pdf_url) {
        downloadContainer.innerHTML = `
            <a href="${data.pdf_url}" download class="download-btn-small">
                ${_fileIcon()} Download PDF
            </a>`;
    }

    const currentTheme = document.documentElement.getAttribute('data-theme') ?? 'light';

    const heatMapContainer = clone.querySelector('.catcher-heatmap');
    if (heatMapContainer) {
        heatMapContainer.appendChild(chartBlock(
            data.heat_map_url, data.heat_map_dark_url, 'Notable', currentTheme,
            `${data.catcher_name} notable`, 'report-img-catcher'));
    }

    const pitchLocationContainer = clone.querySelector('.catcher-pitch-location');
    if (pitchLocationContainer) {
        pitchLocationContainer.appendChild(chartBlock(
            data.pitch_location_url, data.pitch_location_dark_url, 'Pitch Location', currentTheme,
            `${data.catcher_name} pitch location`, 'report-img-catcher'));
    }

    clone.querySelector('.framing-table').innerHTML =
        data.framing_table || '<p class="filter-note">No taken-pitch data in this range.</p>';

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
