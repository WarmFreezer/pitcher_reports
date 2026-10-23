// Plotly charts shared by the report pages (pitching, batting, catching).
//
// The server sends each chart as a {data, layout} figure drawn in the light theme
// (see app/services/plotly_charts.py). This file draws them, re-colors them when the
// theme toggles, renders the PNGs the PDF export posts back, and builds the shared
// pitch type / velocity / color-by / view filter bar.

const PLOTLY_CONFIG = { displaylogo: false, responsive: true, displayModeBar: false };

const CHART_COLORS = {
    light: { ink: '#111111', muted: '#444444', grid: 'rgba(68,68,68,0.25)' },
    dark: { ink: '#e0e0e0', muted: '#aaaaaa', grid: 'rgba(170,170,170,0.3)' },
};

// Layout for `theme`. The server's figure is light; this recolors text, axes and the
// zone shapes (named 'ink' or 'muted' by the server) without touching the data.
function chartLayout(layout, theme) {
    const colors = CHART_COLORS[theme] || CHART_COLORS.light;
    const out = structuredClone(layout);
    out.font = { ...out.font, color: colors.ink };
    for (const axis of ['xaxis', 'yaxis']) {
        if (!out[axis]) continue;
        Object.assign(out[axis], {
            gridcolor: colors.grid, linecolor: colors.muted, zerolinecolor: colors.muted,
        });
    }
    // Only shapes the server marked 'ink' or 'muted' follow the theme; any other shape (a school's
    // shaded zone, say) keeps the color its author gave it.
    for (const shape of out.shapes || []) {
        if (shape.name === 'ink' || shape.name === 'muted') {
            shape.line = { ...shape.line, color: shape.name === 'ink' ? colors.ink : colors.muted };
        }
    }
    return out;
}

function currentChartTheme() {
    return document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
}

// Draws `figure` into `el`, remembering it so a theme toggle can redraw the layout.
function renderChart(el, figure, theme = currentChartTheme()) {
    el._figure = figure;
    return Plotly.react(el, structuredClone(figure.data), chartLayout(figure.layout, theme), PLOTLY_CONFIG);
}

// Called by core.js when the theme toggles.
function applyThemeToCharts(theme) {
    document.querySelectorAll('.plotly-chart').forEach(el => {
        if (el._figure && el.data) {
            Plotly.react(el, structuredClone(el._figure.data), chartLayout(el._figure.layout, theme), PLOTLY_CONFIG);
        }
    });
}

// A figure as a PNG data URL, always in the light theme on white (it goes on a printed
// page) regardless of the theme on screen. Renders from the figure itself, so it works
// for a card whose body is still collapsed.
async function figureToPng(figure, { width = 760, height = 720, scale = 2 } = {}) {
    const layout = chartLayout(figure.layout, 'light');
    layout.paper_bgcolor = '#ffffff';
    layout.plot_bgcolor = '#ffffff';
    return Plotly.toImage(
        { data: structuredClone(figure.data), layout },
        { format: 'png', width, height, scale });
}

// ── Filter bar ───────────────────────────────────────────────────────────────

function _el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
}

function _filterGroup(label) {
    const group = _el('div', 'chart-filter-group');
    group.appendChild(_el('span', 'chart-filter-label', label));
    return group;
}

// A two-state switch in the same markup the account settings use (forms.css .switch-field):
// left text when off, right text when on.
function _switch(leftText, rightText, isRight, onPick) {
    const label = _el('label', 'switch-field switch-field-subtle');
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.className = 'switch-input';
    input.checked = isRight;
    input.addEventListener('change', () => onPick(input.checked));
    label.append(
        _el('span', 'switch-text', leftText), input,
        _el('span', 'switch-slider switch-slider-subtle'), _el('span', 'switch-text', rightText));
    return label;
}

// Builds the bar into `container` from the server's 'meta' message:
//   { pitch_types: [{name, abbreviation, color, count}], velo_min, velo_max,
//     defaults: {view, color_by}, charts_enabled, color_modes? }
// color_modes lists what the charts can be colored by (default pitch type / velocity; the
// catcher page adds framing). options.veloLabel names the velocity slider and
// options.veloColorLabel the velocity color mode (a hitter's spray chart colors by exit velocity).
// options.breakChartToggle adds the pitcher page's movement / flight-path break chart switch.
// onChange('filters' | 'charts') fires when the user commits a change -- 'filters' alters
// which pitches count (so numbers and charts both need a refetch), 'charts' only how the
// charts are drawn. Returns { getFilters(), getChartPrefs() } for building requests.
function createChartFilterBar(container, meta, onChange, options = {}) {
    const state = {
        types: new Set(meta.pitch_types.map(t => t.name)),
        velo: [meta.velo_min, meta.velo_max],
        colorBy: meta.defaults.color_by,
        view: meta.defaults.view,
        breakChart: 'movement',
        showPitchPaths: true,
        showNoSpin: true,
    };
    container.replaceChildren();
    container.hidden = false;

    let typeTimer = null;
    const typeBoxes = [];

    const typeGroup = _filterGroup('Pitch types');
    const chips = _el('div', 'chip-row');
    for (const t of meta.pitch_types) {
        const label = _el('label', 'type-chip');
        const box = document.createElement('input');
        box.type = 'checkbox';
        box.checked = true;
        box.value = t.name;
        box.addEventListener('change', () => {
            if (box.checked) state.types.add(t.name); else state.types.delete(t.name);
            clearTimeout(typeTimer);
            typeTimer = setTimeout(() => onChange('filters'), 250);
        });
        typeBoxes.push(box);
        const swatch = _el('span', 'type-chip-swatch');
        swatch.style.backgroundColor = t.color;
        label.append(box, swatch, _el('span', '', `${t.abbreviation} · ${t.count}`));
        label.title = t.name;
        chips.appendChild(label);
    }
    typeGroup.appendChild(chips);
    const quick = _el('div', 'chip-actions');
    for (const [text, checked] of [['All', true], ['None', false]]) {
        const button = _el('button', 'link-btn', text);
        button.type = 'button';
        button.addEventListener('click', () => {
            typeBoxes.forEach(box => {
                box.checked = checked;
                if (checked) state.types.add(box.value); else state.types.delete(box.value);
            });
            clearTimeout(typeTimer);
            onChange('filters');
        });
        quick.appendChild(button);
    }
    typeGroup.appendChild(quick);
    container.appendChild(typeGroup);

    if (meta.velo_min != null && meta.velo_max != null) {
        const veloGroup = _filterGroup(options.veloLabel || 'Velocity');
        const readout = _el('span', 'velo-readout');
        const range = _el('div', 'dual-range');
        const lo = document.createElement('input');
        const hi = document.createElement('input');
        for (const [input, value] of [[lo, meta.velo_min], [hi, meta.velo_max]]) {
            input.type = 'range';
            input.min = meta.velo_min;
            input.max = meta.velo_max;
            input.step = 1;
            input.value = value;
        }
        lo.setAttribute('aria-label', 'Minimum velocity');
        hi.setAttribute('aria-label', 'Maximum velocity');
        const sync = () => {
            let [a, b] = [Number(lo.value), Number(hi.value)];
            if (a > b) {
                // Handles crossed: keep whichever one the user is dragging as the leader.
                if (document.activeElement === lo) { a = b; lo.value = a; } else { b = a; hi.value = b; }
            }
            state.velo = [a, b];
            readout.textContent = `${a} – ${b} mph`;
            const span = meta.velo_max - meta.velo_min || 1;
            range.style.setProperty('--lo', `${((a - meta.velo_min) / span) * 100}%`);
            range.style.setProperty('--hi', `${((b - meta.velo_min) / span) * 100}%`);
        };
        for (const input of [lo, hi]) {
            input.addEventListener('input', sync);
            // 'change' fires on release, so a drag recomputes once rather than per tick.
            input.addEventListener('change', () => { sync(); onChange('filters'); });
        }
        sync();
        range.append(_el('div', 'dual-range-track'), lo, hi);
        veloGroup.append(range, readout);
        container.appendChild(veloGroup);
    }

    if (meta.charts_enabled) {
        const colorLabels = {
            pitch_type: 'Pitch type', velo: options.veloColorLabel || 'Velocity', framing: 'Framing value',
        };
        const modes = meta.color_modes || ['pitch_type', 'velo'];
        const colorGroup = _filterGroup('Color by');
        if (modes.length === 2) {
            colorGroup.appendChild(_switch(colorLabels[modes[0]], colorLabels[modes[1]], state.colorBy === modes[1], isRight => {
                state.colorBy = isRight ? modes[1] : modes[0];
                onChange('charts');
            }));
        } else {
            // More than two choices doesn't fit a switch.
            const select = document.createElement('select');
            select.className = 'chart-select';
            for (const mode of modes) {
                const option = document.createElement('option');
                option.value = mode;
                option.textContent = colorLabels[mode] || mode;
                option.selected = mode === state.colorBy;
                select.appendChild(option);
            }
            select.addEventListener('change', () => {
                state.colorBy = select.value;
                onChange('charts');
            });
            colorGroup.appendChild(select);
        }
        container.appendChild(colorGroup);

        const viewGroup = _filterGroup('View');
        viewGroup.appendChild(_switch('Heatmap', 'Scatter', state.view === 'scatter', isScatter => {
            state.view = isScatter ? 'scatter' : 'heatmap';
            onChange('charts');
        }));
        container.appendChild(viewGroup);

        if (options.breakChartToggle) {
            const breakGroup = _filterGroup('Break chart (beta)');
            const pathsGroup = _filterGroup('Each pitch line');
            pathsGroup.hidden = state.breakChart !== 'time';
            pathsGroup.appendChild(_switch('Off', 'On', state.showPitchPaths, isOn => {
                state.showPitchPaths = isOn;
                onChange('charts');
            }));
            const noSpinGroup = _filterGroup('No-spin path');
            noSpinGroup.hidden = state.breakChart !== 'time';
            noSpinGroup.appendChild(_switch('Off', 'On', state.showNoSpin, isOn => {
                state.showNoSpin = isOn;
                onChange('charts');
            }));
            breakGroup.appendChild(_switch('Movement', 'Flight path', state.breakChart === 'time', isTime => {
                state.breakChart = isTime ? 'time' : 'movement';
                pathsGroup.hidden = noSpinGroup.hidden = !isTime;
                onChange('charts');
            }));
            container.append(breakGroup, pathsGroup, noSpinGroup);
        }
    }

    return {
        // null means "no restriction" -- the server only filters on what was narrowed.
        getFilters() {
            const allTypes = state.types.size === meta.pitch_types.length;
            const fullRange = !state.velo || (state.velo[0] === meta.velo_min && state.velo[1] === meta.velo_max);
            return {
                pitch_types: allTypes ? null : [...state.types],
                velo: fullRange ? null : state.velo,
            };
        },
        getChartPrefs() {
            return {
                color_by: state.colorBy, view: state.view,
                ...(options.breakChartToggle ? { break_chart: state.breakChart, show_pitch_paths: state.showPitchPaths, show_no_spin: state.showNoSpin } : {}),
            };
        },
    };
}
