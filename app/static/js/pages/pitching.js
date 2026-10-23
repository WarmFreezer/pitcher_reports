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
            seedDateInputs(archiveBounds);
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

// ── Report generation ────────────────────────────────────────────────────────

const reports = createReportCards({
    idField: 'pitcher_id', nameField: 'pitcher_name', requestIdKey: 'pitcher_id',
    cardUrl: '/api/pitching/pitcher', exportUrl: '/api/pitching/export', exportListKey: 'pitchers',
    noun: 'pitcher',
    fill: fillPitcherCard,
});

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
    const filterArea = document.getElementById('chartFilters');
    const button = document.getElementById('generateBtn');
    const spinnerStart = Date.now();

    if (reportOutput) reportOutput.innerHTML = SPINNER_SVG;
    if (summaryArea) summaryArea.innerHTML = '';
    if (filterArea) { filterArea.hidden = true; filterArea.replaceChildren(); }
    if (button) button.disabled = true;

    reports.start(payload);
    updateDownloadLink(false);

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

        // Server streams one NDJSON line per pitcher as their card finishes, preceded by
        // a 'meta' line (what the filter bar is built from) and followed by 'done'.
        for await (const msg of readNdjson(response)) {
            if (msg.type === 'meta') {
                if (filterArea) reports.setFilterBar(createChartFilterBar(filterArea, msg, reports.handleFilterChange, { breakChartToggle: true }));
            } else if (msg.type === 'report') {
                renderPitcherCard(msg);
                reportCount++;
            } else if (msg.type === 'done') {
                renderRunSummary({ ...msg, count: reportCount });
                if (reportCount) updateDownloadLink(true, '#client');
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
    const mergedButton = count
        ? `<button type="button" class="download-btn" id="downloadAllBtn">Download All (${count})</button>`
        : '';
    const pitchByPitchButton = result.pitch_by_pitch_all_url
        ? `<a href="${result.pitch_by_pitch_all_url}" class="download-btn pbp-link" download style="text-decoration: none;">Download All Pitch-by-Pitch</a>`
        : '';

    area.innerHTML = `
        <div class="bubble" style="display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap;">
            <div>
                <h2>${count} Pitcher Report${count === 1 ? '' : 's'}</h2>
                <p>${result.date_range} · ${result.games} game${result.games === 1 ? '' : 's'} · ${result.opponent}</p>
            </div>
            <div style="display: flex; gap: 12px; flex-wrap: wrap; align-items: center;">${mergedButton}${pitchByPitchButton}</div>
        </div>`;

    document.getElementById('downloadAllBtn')?.addEventListener('click', () => reports.downloadAll());
}

// ── Cards ────────────────────────────────────────────────────────────────────

// The pitcher-specific part of a card: stat tables, custom stats, chart containers + legend.
// Runs for the first render and every refresh; a charts-only refresh has no tables in it.
function fillPitcherCard(card, data) {
    const root = card.el;

    if (data.pitcher_table !== undefined) {
        root.querySelector('.pitcher-table').innerHTML = data.pitcher_table || '';
        root.querySelector('.left-usage').innerHTML = data.left_usage_table || '';
        root.querySelector('.right-usage').innerHTML = data.right_usage_table || '';
        root.querySelector('.left-usage-summary').textContent = data.left_usage_summary || '';
        root.querySelector('.right-usage-summary').textContent = data.right_usage_summary || '';
        renderCustomStats(root, data);
    }

    const heatmapContainer = root.querySelector('.pitcher-heatmap');
    const breakmapContainer = root.querySelector('.pitcher-breakmap');
    if (data.figures) {
        if (!heatmapContainer.childElementCount) {
            heatmapContainer.append(
                plotBlock('vs Left-Handed Batters', 'heat_left'),
                plotBlock('vs Right-Handed Batters', 'heat_right'));
            breakmapContainer.append(plotBlock('Pitch Break', 'break'));
            const legend = document.createElement('div');
            legend.className = 'breakmap-legend-slot';
            breakmapContainer.appendChild(legend);
        }
        const prefs = reports.getFilterBar()?.getChartPrefs() ?? {};
        const overTime = prefs.break_chart === 'time';
        const title = overTime ? "Flight Path — Pitcher's View (beta)"
            : data.arm_angle ? `Pitch Break — Arm Angle: ${data.arm_angle}` : 'Pitch Break';
        breakmapContainer.querySelector('.graph-title').textContent = title;
        const slot = breakmapContainer.querySelector('.breakmap-legend-slot');
        slot.replaceChildren();
        // The over-time chart is always colored by pitch type, so it always needs the legend.
        if (data.legend && data.legend.length && (overTime || prefs.color_by !== 'velo')) {
            slot.appendChild(pitchTypeLegend(data.legend));
        }
    } else if (!heatmapContainer.childElementCount) {
        for (const container of [heatmapContainer, breakmapContainer]) {
            const note = document.createElement('p');
            note.className = 'chart-unavailable';
            note.textContent = 'Not available on your plan';
            container.appendChild(note);
        }
    }
}

function renderCustomStats(root, data) {
    const hasCustom = data.custom_stats || (data.custom_pitch_type_stats_tables && data.custom_pitch_type_stats_tables.length);
    const customSection = root.querySelector('.custom-stats-section');
    customSection.hidden = !hasCustom;

    const tiles = root.querySelector('.custom-stats');
    tiles.replaceChildren();
    if (data.custom_stats) renderStatTiles(tiles, data.custom_stats);

    const pitchTypeContainer = root.querySelector('.custom-pitch-type-stats');
    pitchTypeContainer.replaceChildren();
    for (const { title, html } of data.custom_pitch_type_stats_tables || []) {
        const section = document.createElement('div');
        section.style.cssText = 'max-width:1200px; margin: 8px auto;';
        section.innerHTML = `<p class="graph-title">${title}</p><div class="table-section"><div class="table-scroll">${html}</div></div>`;
        pitchTypeContainer.appendChild(section);
    }
}

// Stamps one pitcher's data into the hidden <template> and appends the clone
function renderPitcherCard(data) {
    const template = document.querySelector('#pitcher-report-template');
    if (!template) {
        console.error('Template #pitcher-report-template not found');
        return;
    }

    const clone = template.content.cloneNode(true);
    const el = clone.querySelector('.report-card');

    const downloadContainer = clone.querySelector('.download-container');
    const pdfButton = document.createElement('button');
    pdfButton.type = 'button';
    pdfButton.className = 'download-btn-small';
    pdfButton.innerHTML = `${_fileIcon()} Download PDF`;
    pdfButton.addEventListener('click', () => reports.download([data.pitcher_id], pdfButton));
    downloadContainer.appendChild(pdfButton);

    if (data.pitch_by_pitch_url) {
        const pbp = document.createElement('a');
        pbp.className = 'download-btn-small pbp-link';
        pbp.href = data.pitch_by_pitch_url;
        pbp.download = '';
        pbp.innerHTML = `${_listIcon()} Pitch-by-Pitch`;
        downloadContainer.appendChild(pbp);
    }

    el.querySelectorAll('.card-tab').forEach(tab => tab.addEventListener('click', () => selectTab(el, tab.dataset.tab, data)));

    reports.register(el, data);
    document.querySelector('#report-output')?.appendChild(clone);
}

// The pitch-by-pitch URLs carry the filters as they are at click time rather than as they
// were when the card was drawn.
function withCurrentFilters(href) {
    const url = new URL(href, window.location.origin);
    url.searchParams.delete('filters');
    const filters = reports.getFilterBar()?.getFilters();
    if (filters && (filters.pitch_types || filters.velo)) {
        url.searchParams.set('filters', JSON.stringify(filters));
    }
    return url.pathname + url.search;
}

document.addEventListener('click', (event) => {
    const link = event.target.closest('a.pbp-link');
    if (link) link.href = withCurrentFilters(link.href);
});

// ── Pitch-by-pitch tab ───────────────────────────────────────────────────────

async function selectTab(root, tab, data) {
    root.querySelectorAll('.card-tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
    const panel = root.querySelector('.pbp-panel');
    root.querySelector('.overall-panel').hidden = tab !== 'pbp';
    panel.hidden = tab !== 'pbp';
    if (tab !== 'pbp') return;

    // Fetched on every switch so the tab always matches the current filters.
    panel.textContent = 'Loading…';
    try {
        const response = await fetch(withCurrentFilters(data.pitch_by_pitch_url.replace('/pitch-by-pitch?', '/pitch-by-pitch/preview?')));
        const body = await response.json();
        if (!response.ok) throw new Error(body.error || 'Could not load pitch-by-pitch.');
        renderPitchByPitch(panel, body);
    } catch (error) {
        panel.textContent = error.message;
    }
}

function h(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
}

function renderPitchByPitch(panel, report) {
    panel.replaceChildren();
    if (!report.at_bats.length) {
        panel.append(h('p', 'No pitches found for the selected games.'));
        return;
    }
    for (const ab of report.at_bats) {
        const block = h('div', undefined, 'graph-block');
        block.append(h('p', `${ab.inning} · vs ${ab.batter_name} (${ab.batter_side})${ab.result ? ' — ' + ab.result : ''}`, 'graph-title'));

        const table = h('table');
        const head = table.createTHead().insertRow();
        for (const col of ['#', 'Pitch', 'Velo', 'Count', 'Result']) head.append(h('th', col));
        for (const p of ab.pitches) {
            const row = table.insertRow();
            for (const v of [p.number, p.pitch_type, p.velo == null ? '' : p.velo.toFixed(1), `${p.balls}-${p.strikes}`, p.result]) {
                row.insertCell().textContent = v;
            }
        }
        const tableWrap = h('div', undefined, 'table-scroll');
        tableWrap.append(table);

        const layout = h('div');
        layout.style.cssText = 'display:flex; gap:16px; align-items:flex-start; flex-wrap:wrap;';
        layout.append(zoneSvg(ab.pitches), tableWrap);
        block.append(layout);
        panel.append(block);
    }
}

// Strike-zone panel: numbered dots at plate location (catcher's view), 5 ft square.
// shortcut: dots are one color, not velo-scaled like the PDF; add the scale if coaches ask.
function zoneSvg(pitches) {
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', '-2.5 0 5 5');
    svg.setAttribute('width', 180);
    svg.setAttribute('height', 180);
    const add = (tag, attrs, text) => {
        const node = document.createElementNS(ns, tag);
        for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
        if (text !== undefined) node.textContent = text;
        svg.append(node);
    };
    // Frame, then the zone (17in plate = ±0.708ft, 1.5-3.5ft), y flipped so up is up.
    add('rect', { x: -2.5, y: 0, width: 5, height: 5, fill: 'none', stroke: 'currentColor', 'stroke-width': 0.03 });
    add('rect', { x: -0.708, y: 5 - 3.5, width: 1.417, height: 2, fill: 'none', stroke: 'currentColor', 'stroke-width': 0.03, 'stroke-dasharray': '0.12 0.08' });
    for (const p of pitches) {
        if (p.plate_loc_side == null || p.plate_loc_height == null) continue;
        const x = Math.min(Math.max(p.plate_loc_side, -2.3), 2.3);
        const y = 5 - Math.min(Math.max(p.plate_loc_height, 0.2), 4.8);
        add('circle', { cx: x, cy: y, r: 0.17, fill: 'var(--accent)', stroke: 'currentColor', 'stroke-width': 0.02 });
        add('text', { x, y: y + 0.07, 'text-anchor': 'middle', 'font-size': 0.2, 'font-weight': 700, fill: 'var(--text-on-accent)' }, p.number);
    }
    return svg;
}

// The navbar's download link.
window.downloadAllReports = () => reports.downloadAll();
