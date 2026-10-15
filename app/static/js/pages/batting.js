// Batting reports: pick a time frame, tick the hitters to build, generate them
// all at once with a merged PDF alongside the individual ones.

const MIN_SPINNER_MS = 600;
const SLOW_SELECTION = 10;   // past this many hitters, warn before the wait

let archiveBounds = { first: null, last: null };
let reloadTimer = null;

document.addEventListener('DOMContentLoaded', async () => {
    // First call has no dates, purely to learn the archive's bounds so the
    // pickers can be seeded before the real, range-filtered fetch.
    await loadHitters({ seedDates: true });

    document.getElementById('targetToggle')?.addEventListener('change', () => loadHitters());
    for (const id of ['startDate', 'endDate']) {
        document.getElementById(id)?.addEventListener('change', () => {
            clearTimeout(reloadTimer);
            reloadTimer = setTimeout(() => loadHitters(), 150);
        });
    }
});

async function loadHitters({ seedDates = false } = {}) {
    const list = document.getElementById('hitterList');
    const info = document.getElementById('archiveInfo');
    const filters = currentFilters();

    if (list) list.innerHTML = '<p class="filter-note">Loading…</p>';

    const params = new URLSearchParams({ target: filters.target });
    if (!seedDates) {
        if (filters.start_date) params.set('start_date', filters.start_date);
        if (filters.end_date) params.set('end_date', filters.end_date);
    }

    try {
        const response = await fetch(`/api/batting/hitters?${params.toString()}`);
        if (!response.ok) throw new Error('Could not load hitters');
        const data = await response.json();

        if (seedDates) {
            archiveBounds = { first: data.first_date, last: data.last_date };
            seedDateInputs(archiveBounds);
            if (info) {
                info.textContent = data.game_count
                    ? `${data.game_count} game${data.game_count === 1 ? '' : 's'} saved, ${data.first_date} through ${data.last_date}.`
                    : 'No games saved yet. Upload a game file and choose Save Game to build your archive.';
            }
            // Re-fetch now that the pickers carry a real range
            if (data.game_count) return loadHitters();
        }

        renderHitterList(data.hitters || []);
    } catch (error) {
        console.error('Error loading hitters:', error);
        toast('Could not load hitters.', 'error');
        if (list) list.innerHTML = '<p class="filter-note">Unavailable.</p>';
        updateSelectionCount();
    }
}

function renderHitterList(hitters) {
    const list = document.getElementById('hitterList');
    if (!list) return;

    if (hitters.length === 0) {
        list.innerHTML = '<p class="filter-note">No hitters with batted balls in this range.</p>';
        updateSelectionCount();
        return;
    }

    // All checked by default -- generating the whole roster is the common case
    list.innerHTML = hitters.map(h => `
        <label class="checkbox-row">
            <input type="checkbox" class="hitter-check" value="${h.id}" checked
                   onchange="updateSelectionCount()">
            <span class="row-label">${h.name}</span>
            <span class="row-meta">${h.batted_balls} BB · ${h.games}G</span>
        </label>`).join('');

    updateSelectionCount();
}

function setAllHitters(checked) {
    document.querySelectorAll('.hitter-check').forEach(box => { box.checked = checked; });
    updateSelectionCount();
}

function selectedHitterIds() {
    return Array.from(document.querySelectorAll('.hitter-check:checked')).map(box => box.value);
}

function updateSelectionCount() {
    const label = document.getElementById('selectionCount');
    if (!label) return;
    const n = selectedHitterIds().length;
    label.textContent = n ? `${n} hitter${n === 1 ? '' : 's'} selected` : 'No hitters selected';
}

// ── Report generation ────────────────────────────────────────────────────────

const reports = createReportCards({
    idField: 'hitter_id', nameField: 'hitter_name', requestIdKey: 'batter_id',
    cardUrl: '/api/batting/hitter', exportUrl: '/api/batting/export', exportListKey: 'hitters',
    noun: 'hitter',
    // Spray charts are landscape; a school's own charts are wider still.
    pngSize: slot => slot.startsWith('custom_')
        ? { width: 560, height: 311, scale: 3 }
        : { width: 560, height: 400, scale: 3 },
    fill: fillHitterCard,
});

// A hitter's spray chart colors by exit velocity, and the slider filters the pitches he saw.
const FILTER_BAR_OPTIONS = { veloLabel: 'Pitch velocity', veloColorLabel: 'Exit velocity' };

async function generateBattingReports() {
    const batterIds = selectedHitterIds();
    if (batterIds.length === 0) {
        toast('Select at least one hitter.', 'error');
        return;
    }

    if (batterIds.length > SLOW_SELECTION) {
        toast('This might take a minute…', 'info');
    }

    const filters = currentFilters();
    const payload = { batter_ids: batterIds, ...filters };

    const reportOutput = document.querySelector('#report-output');
    const summaryArea = document.getElementById('battingSummary');
    const filterArea = document.getElementById('chartFilters');
    const button = document.getElementById('generateBtn');
    const spinnerStart = Date.now();

    if (reportOutput) reportOutput.innerHTML = SPINNER_SVG;
    if (summaryArea) summaryArea.innerHTML = '';
    if (filterArea) { filterArea.hidden = true; filterArea.replaceChildren(); }
    if (button) button.disabled = true;

    reports.start(filters);   // what a single card / the export is built from: the window + side
    updateDownloadLink(false);

    let reportCount = 0;

    try {
        const response = await fetch('/api/batting/report', {
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

        // Server streams one NDJSON line per hitter as their card finishes, preceded by a
        // 'meta' line (what the filter bar is built from) and followed by 'done'.
        for await (const msg of readNdjson(response)) {
            if (msg.type === 'meta') {
                if (filterArea) {
                    reports.setFilterBar(createChartFilterBar(filterArea, msg, reports.handleFilterChange, FILTER_BAR_OPTIONS));
                }
            } else if (msg.type === 'report') {
                renderHitterCard(msg);
                reportCount++;
            } else if (msg.type === 'done') {
                renderRunSummary({ ...msg, count: reportCount });
                if (reportCount) updateDownloadLink(true, '#client');
                if (msg.failed && msg.failed.length) {
                    toast(`${msg.failed.length} hitter(s) could not be generated.`, 'error');
                }
            }
        }

        if (reportCount === 0 && reportOutput) {
            reportOutput.innerHTML = '<p style="margin: 32px;">No reports generated.</p>';
        }
    } catch (error) {
        console.error('Error generating batting reports:', error);
        toast('Error generating reports: ' + error.message, 'error');
        if (reportOutput) reportOutput.innerHTML = '';
    } finally {
        if (button) button.disabled = false;
    }
}

function renderRunSummary(result) {
    const area = document.getElementById('battingSummary');
    if (!area) return;

    const count = result.count ?? 0;
    const mergedButton = count
        ? `<button type="button" class="download-btn" id="downloadAllBtn">Download All (${count})</button>`
        : '';

    area.innerHTML = `
        <div class="bubble" style="display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap;">
            <div>
                <h2>${count} Hitter Report${count === 1 ? '' : 's'}</h2>
                <p>${result.date_range} · ${result.games} game${result.games === 1 ? '' : 's'}</p>
            </div>
            <div style="display: flex; gap: 12px; flex-wrap: wrap; align-items: center;">${mergedButton}</div>
        </div>`;

    document.getElementById('downloadAllBtn')?.addEventListener('click', () => reports.downloadAll());
}

// ── Cards ────────────────────────────────────────────────────────────────────

// The hitter-specific part of a card: summary tiles, tables, custom section, spray charts + legend.
// Runs for the first render and every refresh; a charts-only refresh has no tables in it.
function fillHitterCard(card, data) {
    const root = card.el;

    if (data.discipline_table !== undefined) {
        root.querySelector('.hitter-meta').textContent =
            `${data.summary?.PA ?? 0} PA · ${data.games} game${data.games === 1 ? '' : 's'}`;
        const tiles = root.querySelector('.summary-grid');
        tiles.replaceChildren();
        renderStatTiles(tiles, data.summary);
        root.querySelector('.batted-ball-table').innerHTML =
            data.batted_ball_table || '<p class="filter-note">No batted balls in this range.</p>';
        root.querySelector('.discipline-table').innerHTML =
            data.discipline_table || '<p class="filter-note">No pitch data in this range.</p>';
        renderHitterCustom(card, data);
    }

    const sprayContainer = root.querySelector('.hitter-spray');
    if (data.figures) {
        if (!sprayContainer.childElementCount) {
            sprayContainer.append(
                plotBlock('vs LHP', 'spray_left', 'plotly-chart-spray'),
                plotBlock('vs RHP', 'spray_right', 'plotly-chart-spray'));
        }
        const slot = root.querySelector('.spray-legend-slot');
        slot.replaceChildren();
        // Marker shape is the batted-ball type (keyed inside the chart); color is the pitch type
        // unless it is showing exit velocity, which has its own key.
        if (data.legend && data.legend.length && reports.getFilterBar()?.getChartPrefs().color_by !== 'velo') {
            slot.appendChild(pitchTypeLegend(data.legend));
        }
    } else if (!sprayContainer.childElementCount) {
        const note = document.createElement('p');
        note.className = 'chart-unavailable';
        note.textContent = 'Not available on your plan';
        sprayContainer.appendChild(note);
    }
}

// Custom stats/charts from the school's own uploaded report script, if any -- most schools
// have none, so the section stays hidden. A custom chart is a Plotly figure like the rest: it
// lives in card.figures under its own slot so it is drawn, themed and exported the same way.
function renderHitterCustom(card, data) {
    const root = card.el;
    const charts = data.custom_charts || [];
    const hasCustom = data.custom_stats
        || (data.custom_hit_type_stats_tables && data.custom_hit_type_stats_tables.length)
        || (data.custom_pitch_type_stats_tables && data.custom_pitch_type_stats_tables.length)
        || charts.length;
    root.querySelector('.custom-stats-section').hidden = !hasCustom;

    const tiles = root.querySelector('.custom-stats');
    tiles.replaceChildren();
    if (data.custom_stats) renderStatTiles(tiles, data.custom_stats);

    const chartsContainer = root.querySelector('.custom-charts');
    chartsContainer.replaceChildren();
    card.figures = card.figures || {};
    for (const slot of Object.keys(card.figures)) {
        if (slot.startsWith('custom_')) { delete card.figures[slot]; delete card.plotted[slot]; }
    }
    for (const { title, slot, figure } of charts) {
        card.figures[slot] = figure;
        chartsContainer.appendChild(plotBlock(title, slot, 'plotly-chart-wide'));
    }

    const renderStatSections = (container, tables) => {
        container.replaceChildren();
        for (const { title, html } of tables || []) {
            const section = document.createElement('div');
            section.style.cssText = 'max-width:1200px; margin: 8px auto;';
            section.innerHTML = `<p class="graph-title">${title}</p><div class="table-section"><div class="table-scroll">${html}</div></div>`;
            container.appendChild(section);
        }
    };
    renderStatSections(root.querySelector('.custom-hit-type-stats'), data.custom_hit_type_stats_tables);
    renderStatSections(root.querySelector('.custom-pitch-type-stats'), data.custom_pitch_type_stats_tables);
}

// Stamps one hitter's data into the hidden <template> and appends the clone
function renderHitterCard(data) {
    const template = document.querySelector('#hitter-report-template');
    if (!template) {
        console.error('Template #hitter-report-template not found');
        return;
    }

    const clone = template.content.cloneNode(true);
    const el = clone.querySelector('.report-card');

    const downloadContainer = clone.querySelector('.download-container');
    const pdfButton = document.createElement('button');
    pdfButton.type = 'button';
    pdfButton.className = 'download-btn-small';
    pdfButton.innerHTML = `${_fileIcon()} Download PDF`;
    pdfButton.addEventListener('click', () => reports.download([data.hitter_id], pdfButton));
    downloadContainer.appendChild(pdfButton);

    if (data.pitch_by_pitch_url) {
        const pbp = document.createElement('a');
        pbp.className = 'download-btn-small pbp-link';
        pbp.href = data.pitch_by_pitch_url;
        pbp.download = '';
        pbp.innerHTML = `${_listIcon()} Pitch-by-Pitch`;
        downloadContainer.appendChild(pbp);
    }

    reports.register(el, data);
    document.querySelector('#report-output')?.appendChild(clone);
}

// The pitch-by-pitch PDF is built from a link, so it carries the filters as they are at click
// time rather than as they were when the card was drawn.
document.addEventListener('click', (event) => {
    const link = event.target.closest('a.pbp-link');
    if (!link) return;
    const url = new URL(link.href, window.location.origin);
    url.searchParams.delete('filters');
    const filters = reports.getFilterBar()?.getFilters();
    if (filters && (filters.pitch_types || filters.velo)) {
        url.searchParams.set('filters', JSON.stringify(filters));
    }
    link.href = url.pathname + url.search;
});

// The navbar's download link.
window.downloadAllReports = () => reports.downloadAll();
