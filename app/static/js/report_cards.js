// The report cards on /pitching, /batting and /catching, and what they have in common:
// keeping each card in step with the filter bar, drawing its Plotly charts, and building a
// PDF from what is on screen.
//
// A page supplies what is particular to it (its endpoints, its chart slots, how a card's
// tables are filled in) through createReportCards(cfg); everything else lives here.
// Needs charts.js (renderChart, figureToPng) and core.js (toast, _fileIcon) loaded first.

// A heading + a chart container, so Plotly has an element to draw into.
function plotBlock(label, slot, extraClass = '') {
    const wrapper = document.createElement('div');
    wrapper.className = 'graph-block';
    const title = document.createElement('p');
    title.className = 'graph-title';
    title.textContent = label;
    wrapper.appendChild(title);
    const chart = document.createElement('div');
    chart.className = extraClass ? `plotly-chart ${extraClass}` : 'plotly-chart';
    chart.dataset.slot = slot;
    wrapper.appendChild(chart);
    return wrapper;
}

// Pitch-type key as its own element (colored swatch + abbreviation + pitch count per type)
// instead of a legend drawn inside the chart, so it never sits on top of the data.
function pitchTypeLegend(entries) {
    const legend = document.createElement('div');
    legend.className = 'breakmap-legend';
    for (const { abbreviation, color, count } of entries) {
        const item = document.createElement('span');
        item.className = 'breakmap-legend-item';
        const swatch = document.createElement('span');
        swatch.className = 'breakmap-legend-swatch';
        swatch.style.backgroundColor = color;
        item.appendChild(swatch);
        item.appendChild(document.createTextNode(`${abbreviation}: ${count}`));
        legend.appendChild(item);
    }
    return legend;
}

// Runs `worker` over `items`, at most `limit` at a time.
async function runLimited(items, limit, worker) {
    const queue = [...items];
    await Promise.all(Array.from({ length: Math.min(limit, queue.length) }, async () => {
        while (queue.length) await worker(queue.shift());
    }));
}

// Same logical size as the on-screen chart, so the text and markers keep their on-screen
// proportions when the PNG is shrunk onto the page; scale only adds resolution.
const DEFAULT_CHART_PNG_SIZE = { width: 400, height: 379, scale: 3 };

// cfg:
//   idField        key of the card's id in the server payload ('pitcher_id', 'hitter_id', ...)
//   nameField      key of its display name ('pitcher_name', ...)
//   requestIdKey   key the server expects for it in a card/export request ('pitcher_id', 'batter_id', ...)
//   cardUrl        endpoint that rebuilds one card
//   exportUrl      endpoint that builds the PDF
//   exportListKey  body key the export list goes under ('pitchers', 'hitters', ...)
//   noun           'pitcher' | 'hitter' | 'catcher', for messages
//   fill(card, data)   page-specific DOM updates (tables, chart containers, legend)
// A card's DOM needs .report-card-header/.report-card-body (toggling), .card-empty and
// .card-content (the empty state) and .user-name.
function createReportCards(cfg) {
    const cards = new Map();   // id -> card
    let run = null;            // what the cards were built from: {content_hashes|dates, target}
    let filterBar = null;

    function requestBase() {
        return { ...run, filters: filterBar?.getFilters() ?? null, ...(filterBar?.getChartPrefs() ?? {}) };
    }

    // Draws any chart whose figure changed since it was last drawn. Plotly can't size a chart
    // inside a collapsed card, so this only runs for an open one (and again when one opens).
    function ensurePlots(card) {
        if (!card.open || !card.figures) return;
        for (const slot of Object.keys(card.figures)) {
            const el = card.el.querySelector(`.plotly-chart[data-slot="${slot}"]`);
            const figure = card.figures[slot];
            if (!el || !figure || card.plotted[slot] === figure) continue;
            card.plotted[slot] = figure;
            if (typeof Plotly === 'undefined') {
                el.textContent = 'The chart library did not load.';
                continue;
            }
            renderChart(el, figure);
        }
    }

    // Puts server data into a card. Used for the first render and every refresh; a charts-only
    // refresh simply has no tables in it.
    function fillCard(card, data) {
        const root = card.el;
        card.data = { ...card.data, ...data };

        const empty = !!data.empty;
        root.querySelector('.card-empty').hidden = !empty;
        root.querySelector('.card-content').hidden = empty;
        if (data[cfg.nameField]) root.querySelector('.user-name').textContent = data[cfg.nameField];
        if (empty) {
            card.figures = null;
            return;
        }

        // Merged, not replaced: a charts-only refresh carries the standard charts but not a
        // page's extra ones (a school's custom charts), which must survive it.
        if (data.figures) card.figures = { ...(card.figures || {}), ...data.figures };
        cfg.fill(card, data);
        ensurePlots(card);
    }

    // Refetches one card for the current filters. A newer request supersedes an older one
    // (token), so dragging a slider twice in a row can't land the first answer last.
    async function refreshCard(card) {
        if (!card.stale || !run) return;
        const mode = card.stale;
        const token = ++card.token;
        card.el.classList.add('is-refreshing');
        try {
            const response = await fetch(cfg.cardUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ...requestBase(), [cfg.requestIdKey]: card.id, charts_only: mode === 'charts' }),
            });
            if (token !== card.token) return;
            if (!response.ok) throw new Error(`Could not update this ${cfg.noun}`);
            const data = await response.json();
            if (token !== card.token) return;
            card.stale = null;
            fillCard(card, data);
        } catch (error) {
            if (token !== card.token) return;
            console.error(`Error refreshing ${cfg.noun} card:`, error);
            toast(`Could not update that ${cfg.noun}.`, 'error');
        } finally {
            if (token === card.token) card.el.classList.remove('is-refreshing');
        }
    }

    // Called by the filter bar when the user commits a change. 'filters' changes which pitches
    // count, so every number is stale; 'charts' only changes how the charts are drawn. Open
    // cards refetch now; closed ones are marked and refetch when opened or exported.
    function handleFilterChange(kind) {
        for (const card of cards.values()) {
            if (kind === 'filters') card.stale = 'full';
            else if (!card.stale) card.stale = 'charts';
            if (card.open) refreshCard(card);
        }
    }

    // Registers a card for `data` (one entry of the server's stream), fills it and makes its
    // header open/close it.
    function register(el, data) {
        const card = {
            id: String(data[cfg.idField]), el, open: false, stale: null, token: 0,
            figures: null, plotted: {}, data: {},
        };
        cards.set(card.id, card);
        fillCard(card, data);

        const header = el.querySelector('.report-card-header');
        const body = el.querySelector('.report-card-body');
        header.addEventListener('click', (event) => {
            // The download buttons live inside the header; don't toggle when one is clicked
            if (event.target.closest('a, button')) return;
            card.open = body.classList.toggle('open');
            header.classList.toggle('open', card.open);
            if (!card.open) return;
            if (card.stale) refreshCard(card); else ensurePlots(card);
        });
        return card;
    }

    // Builds the PDF for `ids` from what's on screen: refresh any card the filters have
    // outdated, render each card's charts to PNG in this browser, and send those plus the
    // filters. The server recomputes every number itself and only takes the images from us.
    async function download(ids, button = null) {
        if (!run || !ids.length) return;
        if (typeof Plotly === 'undefined') {
            toast('The chart library did not load, so PDFs with charts are unavailable. Check your connection and reload.', 'error');
            return;
        }
        // Label stays put (so the button keeps its size); the wait cursor shows it's working.
        if (button) { button.disabled = true; button.style.cursor = 'wait'; }

        try {
            const chosen = ids.map(id => cards.get(String(id))).filter(Boolean);
            await runLimited(chosen.filter(c => c.stale), 3, refreshCard);

            const entries = [];
            for (const card of chosen) {
                if (card.data.empty) continue;   // nothing passes the filters for this one
                const images = {};
                for (const slot of Object.keys(card.figures || {})) {
                    if (card.figures[slot]) {
                        const size = typeof cfg.pngSize === 'function' ? cfg.pngSize(slot) : (cfg.pngSize || DEFAULT_CHART_PNG_SIZE);
                        images[slot] = await figureToPng(card.figures[slot], size);
                    }
                }
                entries.push({ [cfg.requestIdKey]: card.id, images });
            }
            if (!entries.length) {
                toast('No pitches match the current filters.', 'error');
                return;
            }

            const response = await fetch(cfg.exportUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ...requestBase(), [cfg.exportListKey]: entries }),
            });
            if (!response.ok) {
                const err = await response.json().catch(() => ({}));
                console.error('PDF export failed', response.status, err);
                toast(`${err.error || 'Could not build the PDF.'} (${response.status})`, 'error');
                return;
            }

            const disposition = response.headers.get('Content-Disposition') || '';
            const name = /filename="?([^";]+)"?/.exec(disposition)?.[1] || 'report.pdf';
            const url = URL.createObjectURL(await response.blob());
            const a = document.createElement('a');
            a.href = url;
            a.download = name;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            setTimeout(() => URL.revokeObjectURL(url), 10000);
        } catch (error) {
            console.error('Error building PDF:', error);
            toast('Could not build the PDF: ' + error.message, 'error');
        } finally {
            if (button) { button.disabled = false; button.style.cursor = ''; }
        }
    }

    return {
        cards,
        // A new selection starts clean: stale cards and the previous filter bar are gone.
        start(newRun) { cards.clear(); filterBar = null; run = newRun; },
        setFilterBar(bar) { filterBar = bar; },
        getFilterBar() { return filterBar; },
        register,
        handleFilterChange,
        download,
        downloadAll() {
            return download([...cards.keys()], document.getElementById('downloadAllBtn'));
        },
    };
}
