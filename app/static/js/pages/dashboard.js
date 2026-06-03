// ── Team Overview ─────────────────────────────────────────────────────────────

async function loadTeamOverview() {
    const container = document.getElementById('team-overview-placeholder');
    if (!container) return;
    container.innerHTML = '<p style="color: var(--text-secondary); margin-top: 8px;">Loading...</p>';
    try {
        const res = await fetch('/api/team/overview');
        const data = await res.json();
        if (res.ok) renderTeamOverview(data);
        else container.innerHTML = '<p style="color: red;">Failed to load team data.</p>';
    } catch {
        container.innerHTML = '<p style="color: red;">Failed to load team data.</p>';
    }
}

function fmt(val, decimals = 1) {
    return val != null ? Number(val).toFixed(decimals) : '—';
}

function renderTeamOverview(pitchers) {
    const container = document.getElementById('team-overview-placeholder');
    if (!pitchers.length) {
        container.innerHTML = '<p style="color: var(--text-secondary); margin-top: 8px;">No data uploaded yet.</p>';
        return;
    }

    const rows = pitchers.map((p, i) => `
        <tr class="pitcher-row${i % 2 === 1 ? ' row-alt' : ''}" style="cursor: pointer;" onclick="togglePitchTypes(${i}, ${p.pitcher_id})">
            <td>${p.pitcher_name} <span style="font-size: 0.75em; color: var(--text-secondary);">▶</span></td>
            <td>${p.total_pitches ?? '—'}</td>
            <td>${fmt(p.lo_obp)}</td>
            <td>${fmt(p.lo_bb_percentage)}</td>
            <td>${fmt(p.two_out_eff_percentage)}</td>
            <td>${fmt(p.two_out_bb_percentage)}</td>
        </tr>
        <tr id="pitch-types-${i}" class="dropdown-row" style="display: none;">
            <td colspan="6" style="padding: 0;">
                <div id="pitch-types-content-${i}" style="padding: 0 8px 8px 8px;">
                    <p style="color: var(--text-secondary);">Loading...</p>
                </div>
            </td>
        </tr>
    `).join('');

    container.innerHTML = `
        <div class="table-section">
            <div class="table-scroll">
                <table class="pitcher-data-table">
                    <thead>
                        <tr>
                            <th>Pitcher</th>
                            <th>Pitches</th>
                            <th>LO OBP</th>
                            <th>LO BB%</th>
                            <th>2-Out Eff%</th>
                            <th>2-Out BB%</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>
        </div>`;
}

async function togglePitchTypes(index, pitcherId) {
    const row = document.getElementById(`pitch-types-${index}`);
    const content = document.getElementById(`pitch-types-content-${index}`);
    if (!row) return;

    const isOpen = row.style.display !== 'none';
    row.style.display = isOpen ? 'none' : '';

    // Update chevron
    const chevron = document.querySelectorAll('.pitcher-row')[index]?.querySelector('span');
    if (chevron) chevron.textContent = isOpen ? '▶' : '▼';

    if (!isOpen && !row.dataset.loaded) {
        row.dataset.loaded = 'true';
        try {
            const res = await fetch(`/api/pitcher/${pitcherId}/averages`);
            const data = await res.json();
            if (res.ok && data.length) {
                content.innerHTML = renderPitchTypeTable(data, pitcherId);
            } else {
                content.innerHTML = '<p style="color: var(--text-secondary);">No pitch data.</p>';
            }
        } catch {
            content.innerHTML = '<p style="color: red;">Failed to load pitch data.</p>';
        }
    }
}

function renderPitchTypeTable(pitchTypes, pitcherId) {
    const rows = pitchTypes.map(pt => `
        <tr>
            <td>${pt.pitch_type}</td>
            <td>${pt.tot_count ?? '—'}</td>
            <td>${fmt(pt.strike_percentage ? pt.strike_percentage * 100 : null)}%</td>
            <td>${fmt(pt.sw_percentage ? pt.sw_percentage * 100 : null)}%</td>
            <td>${fmt(pt.sw_miss_percentage ? pt.sw_miss_percentage * 100 : null)}%</td>
            <td>${fmt(pt.avg_low_quartile_speed)} / ${fmt(pt.avg_median_speed)} / ${fmt(pt.avg_high_quartile_speed)}</td>
        </tr>
    `).join('');
    return `
        <div style="display: flex; justify-content: flex-end;">
            <a href="/api/pitcher/${pitcherId}/averages/download" class="download-btn-small">Download Excel</a>
        </div>
        <div class="table-section">
            <div class="table-scroll">
                <table class="pitcher-data-table">
                    <thead>
                        <tr>
                            <th>Pitch</th>
                            <th>Count</th>
                            <th>Strike%</th>
                            <th>Swing%</th>
                            <th>Whiff%</th>
                            <th>Velo (Lo / Med / Hi)</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>
        </div>`;
}

document.addEventListener('DOMContentLoaded', loadTeamOverview);
