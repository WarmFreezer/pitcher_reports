// Show a non-blocking toast notification. type: 'success' | 'error' | 'info'
function toast(message, type = 'info') {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        document.body.appendChild(container);
        _watchToastPosition(container);
    }

    const el = document.createElement('div');
    el.className = `toast toast-${type}`;
    el.innerHTML = `<span>${message}</span><button class="toast-close" onclick="this.parentElement.remove()">×</button>`;
    container.appendChild(el);

    setTimeout(() => el.remove(), 5000);
}

// Keep the toast container just above the footer, matching the FAB scroll behaviour
function _watchToastPosition(container) {
    function update() {
        const footer = document.getElementById('footer-placeholder');
        if (!footer) return;
        const margin = 32;
        const footerTop = footer.getBoundingClientRect().top;
        container.style.bottom = Math.max(margin, window.innerHeight - footerTop + margin) + 'px';
    }
    window.addEventListener('scroll', update, { passive: true });
    update();
}

const _SUN_ICON = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>`;
const _MOON_ICON = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>`;

// Shared download-button icons, reused by batting.js/pitching.js/catching.js.
// Functions (not constants) so they always reflect the theme at call time; the
// data-light-src/data-dark-src pair also lets _swapChartImages() re-color them
// if the user toggles theme after the button is already on the page.
function _fileIcon() {
    const dark = document.documentElement.getAttribute('data-theme') === 'dark';
    const light = '/static/resources/icons/file-text.svg';
    const darkSrc = '/static/resources/icons/file-text-dark.svg';
    return `<img src="${dark ? darkSrc : light}" data-light-src="${light}" data-dark-src="${darkSrc}" alt="" width="16" height="16">`;
}
function _listIcon() {
    const dark = document.documentElement.getAttribute('data-theme') === 'dark';
    const light = '/static/resources/icons/list.svg';
    const darkSrc = '/static/resources/icons/list-dark.svg';
    return `<img src="${dark ? darkSrc : light}" data-light-src="${light}" data-dark-src="${darkSrc}" alt="" width="16" height="16">`;
}

// Load combined header + navbar
// The nav's Upload item opens the file picker when you are already on /upload,
// and otherwise navigates there. uploadFile() only exists on that page, so
// calling it unconditionally made the link dead everywhere else.
function _navUpload() {
    if (window.location.pathname.startsWith('/upload') && typeof uploadFile === 'function') {
        uploadFile();
        return false;
    }
    return true;
}

function loadNavbar(logo = '') {
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    const _logoFallback = `/static/resources/${isDark ? 'statline-logo' : 'statline-logo-light'}.svg`;
    const _isFallback = !logo;
    const avatarHTML = `<div class="avatar"><img src="${logo || _logoFallback}" alt="Organization logo" data-is-statline-fallback="${_isFallback}" onerror="this.src='${_logoFallback}'; this.dataset.isStatlineFallback='true'"></div>`;

    const p = window.location.pathname;
    const active = {
        home:     p === '/',
        file:     p.startsWith('/upload'),
        view:     p.startsWith('/batting') || p.startsWith('/pitching') || p.startsWith('/catching'),
        settings: p.startsWith('/account') || p.startsWith('/subscription'),
        about:    p.startsWith('/about'),
    };
    const a = key => active[key] ? ' active' : '';
    const showLogout = p !== '/login' && p !== '/register';

    document.getElementById('navbar-placeholder').innerHTML = `
        <header class="site-header">
            <div class="header-inner">
                <a href="/" class="logo-lockup">
                    <img src="/static/resources/statline-logo.svg" alt="Statline" class="logo-img">
                </a>

                <nav class="nav-links" id="main-nav-links">
                    <a href="/" class="nav-link${a('home')}">Home</a>
                    <div class="nav-dropdown">
                        <a href="javascript:void(0)" class="nav-link${a('file')}">File ▾</a>
                        <div class="dropdown-content">
                            <a href="/upload" onclick="return _navUpload();">Upload</a>
                            <a href="#" id="nav-download-link" onclick="downloadPDFs(); return false;">Download</a>
                        </div>
                    </div>
                    <div class="nav-dropdown">
                        <a href="javascript:void(0)" class="nav-link${a('view')}">View ▾</a>
                        <div class="dropdown-content">
                            <a href="/pitching">Pitching Report</a>
                            <a href="/batting">Batting Report</a>
                            <a href="/catching">Catching Report</a>
                        </div>
                    </div>
                    <div class="nav-dropdown">
                        <a href="javascript:void(0)" class="nav-link${a('settings')}">Settings ▾</a>
                        <div class="dropdown-content">
                            <a href="/account">Account</a>
                            <a href="/subscription">Subscription</a>
                        </div>
                    </div>
                    <a href="/about" class="nav-link${a('about')}">About</a>
                    ${showLogout ? '<a href="/logout" class="nav-link nav-logout-mobile">Logout</a>' : ''}
                </nav>

                <div class="nav-right">
                    <button id="theme-toggle" class="icon-btn" aria-label="Toggle theme">
                        ${isDark ? _SUN_ICON : _MOON_ICON}
                    </button>
                    ${logo ? avatarHTML : ''}
                    ${showLogout ? '<a href="/logout" style="text-decoration: none;"><button class="logout-btn">Logout</button></a>' : ''}
                    <button class="hamburger-btn" id="hamburger-btn" aria-label="Open navigation">☰</button>
                </div>
            </div>
        </header>
    `;

    // Theme toggle
    document.getElementById('theme-toggle').addEventListener('click', () => {
        const currentlyDark = document.documentElement.getAttribute('data-theme') === 'dark';
        const newTheme = currentlyDark ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', newTheme);
        localStorage.setItem('theme', newTheme);
        document.getElementById('theme-toggle').innerHTML = newTheme === 'dark' ? _SUN_ICON : _MOON_ICON;
        const avatarImg = document.querySelector('.avatar img');
        if (avatarImg && avatarImg.dataset.isStatlineFallback === 'true') {
            avatarImg.src = `/static/resources/${newTheme === 'dark' ? 'statline-logo' : 'statline-logo-light'}.svg`;
        }
        _swapChartImages(newTheme);
    });

    // Hamburger
    document.getElementById('hamburger-btn').addEventListener('click', toggleMobileNav);

    // Mobile: tap dropdown triggers
    document.querySelectorAll('.nav-dropdown .nav-link').forEach(link => {
        link.addEventListener('click', e => {
            if (window.innerWidth > 768) return;
            e.preventDefault();
            link.closest('.nav-dropdown').classList.toggle('mobile-open');
        });
    });

    // Overlay
    const overlay = document.createElement('div');
    overlay.className = 'nav-overlay';
    overlay.addEventListener('click', closeMobileNav);
    document.body.appendChild(overlay);

    updateDownloadLink(false);
}

function toggleMobileNav() {
    const nav = document.getElementById('main-nav-links');
    const overlay = document.querySelector('.nav-overlay');
    const btn = document.getElementById('hamburger-btn');
    const isOpen = nav.classList.toggle('mobile-open');
    overlay?.classList.toggle('active', isOpen);
    btn.textContent = isOpen ? '✕' : '☰';
    btn.setAttribute('aria-label', isOpen ? 'Close navigation' : 'Open navigation');
}

function closeMobileNav() {
    const nav = document.getElementById('main-nav-links');
    const overlay = document.querySelector('.nav-overlay');
    const btn = document.getElementById('hamburger-btn');
    nav?.classList.remove('mobile-open');
    nav?.querySelectorAll('.nav-dropdown.mobile-open').forEach(d => d.classList.remove('mobile-open'));
    overlay?.classList.remove('active');
    if (btn) { btn.textContent = '☰'; btn.setAttribute('aria-label', 'Open navigation'); }
}

// Stores the PDF URL on the link element itself so downloadPDFs() can retrieve it on click
function updateDownloadLink(hasReports, downloadUrl = null) {
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
        toast('No reports available for download.', 'info');
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

// Load footer
function loadFooter() {
    const footerHTML = `
        <footer class="site-footer">
            <a href="https://warmfreezer.github.io/about_me/" style="color: white; font-family: 'Cambria', serif;">&copy; 2026 Thomas Eubank</a>
            <br>
            <a href=/about style="color: white; font-family: 'Cambria', serif;">About</a>
            <a href=/terms style="color: white; margin-left: 16px; font-family: 'Cambria', serif;">Terms</a>
            <a href=/privacy style="color: white; margin-left: 16px; font-family: 'Cambria', serif;">Privacy Policy</a>
        </footer>
    `;
    document.getElementById('footer-placeholder').innerHTML = footerHTML;
}

// Reads a fetch Response body as newline-delimited JSON, yielding each parsed
// line as it arrives. Shared by pitching.js/batting.js's streaming report routes,
// which send one line per pitcher/hitter as their report finishes.
async function* readNdjson(response) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        let newlineIndex;
        while ((newlineIndex = buffer.indexOf('\n')) !== -1) {
            const line = buffer.slice(0, newlineIndex);
            buffer = buffer.slice(newlineIndex + 1);
            if (line.trim()) yield JSON.parse(line);
        }
    }

    if (buffer.trim()) yield JSON.parse(buffer);
}

// Renders a {label: value} object as .summary-grid tiles (see reports.css) --
// shared by the hitter summary grid and the custom-stats section on both
// /pitching and /batting, so a name/value stat always looks like a stat tile
// rather than a table, matching the PDF's generate_stats_grid.
function renderStatTiles(container, stats) {
    if (!container) return;
    container.innerHTML = Object.entries(stats || {})
        .map(([label, value]) => `
            <div class="summary-tile">
                <div class="tile-value">${value}</div>
                <div class="tile-label">${label}</div>
            </div>`).join('');
}

// Inline SVG rather than an <img> so the spinner picks up theme CSS variables.
// Shared by every page that shows a loading state while a report streams in.
const SPINNER_SVG = `<svg viewBox="0 0 90 90" xmlns="http://www.w3.org/2000/svg" style="width: 48px; margin: 32px auto; display: block;" aria-label="Loading...">
  <rect x="20" y="20" width="50" height="50" fill="var(--bg-bubble)" transform="rotate(45 45 45)"/>
  <line x1="26" y1="47" x2="64" y2="47" stroke="#8B1A1A" stroke-width="1.8" stroke-linecap="round"/>
  <line x1="30" y1="53" x2="60" y2="53" stroke="#8B1A1A" stroke-width="1" stroke-linecap="round" opacity="0.5"/>
  <path d="M 45,90 L 90,45 L 45,0.5 L 0.5,45 L 45,90" fill="none" stroke="var(--text-primary)" stroke-width="2.2" stroke-linecap="butt" stroke-dasharray="0 253.44" stroke-dashoffset="253.44">
    <animate attributeName="stroke-dasharray" values="0 253.44; 126.72 126.72; 0 253.44" keyTimes="0;0.5;1" dur="5s" calcMode="spline" keySplines="0.5 0 0.5 1;0.5 0 0.5 1" repeatCount="indefinite"/>
    <animate attributeName="stroke-dashoffset" values="253.44;253.44;0" keyTimes="0;0.5;1" dur="5s" calcMode="spline" keySplines="0.5 0 0.5 1;0.5 0 0.5 1" repeatCount="indefinite"/>
  </path>
</svg>`;

// Builds one chart <img> (theme-aware via data-light-src/data-dark-src, see
// _swapChartImages), wrapped with its title and a small spinner that covers the
// gap between the image landing in the DOM and it actually finishing its
// download -- these are large 300 DPI PNGs, so that gap is often still open
// when a report card's collapsed body is first opened. errorText customizes
// the message shown if the image 404s (charts gated behind a subscription
// tier vs. an optional custom chart that simply doesn't exist read differently).
function chartBlock(lightSrc, darkSrc, label, theme, alt, imgClass, errorText = 'Not available on your plan') {
    const wrapper = document.createElement('div');
    wrapper.className = 'graph-block';

    const title = document.createElement('p');
    title.className = 'graph-title';
    title.textContent = label;
    wrapper.appendChild(title);

    const spinner = document.createElement('div');
    spinner.className = 'chart-spinner';
    spinner.innerHTML = SPINNER_SVG;
    wrapper.appendChild(spinner);

    const img = document.createElement('img');
    img.hidden = true;
    img.dataset.lightSrc = lightSrc;
    img.dataset.darkSrc = darkSrc;
    img.src = (theme === 'dark' && darkSrc) ? darkSrc : lightSrc;
    img.alt = alt;
    img.className = `report-img ${imgClass}`;
    img.onload = () => { spinner.remove(); img.hidden = false; };
    img.onerror = function () {
        spinner.remove();
        this.outerHTML = `<p class="chart-unavailable">${errorText}</p>`;
    };
    wrapper.appendChild(img);

    return wrapper;
}

// Generic custom dropdown: a trigger button + menu of option buttons, used in
// place of a native <select> (e.g. organization picker, chart style picker).
// Expects: .custom-dropdown > .dropdown-trigger, .dropdown-value (hidden input), .dropdown-option[data-value]
function dropdownInit() {
    document.querySelectorAll('.custom-dropdown').forEach(picker => {
        const trigger = picker.querySelector('.dropdown-trigger');
        const hidden = picker.querySelector('.dropdown-value');
        const options = picker.querySelectorAll('.dropdown-option');

        if (!trigger || !hidden || options.length === 0) return;

        trigger.addEventListener('click', () => picker.classList.toggle('open'));

        options.forEach(btn => {
            btn.addEventListener('click', () => {
                hidden.value = btn.dataset.value;
                trigger.textContent = `${btn.textContent.trim()} ▼`;
                picker.classList.remove('open');
            });
        });

        // Close the dropdown when the user clicks anywhere outside it
        document.addEventListener('click', (e) => {
            if (!picker.contains(e.target)) picker.classList.remove('open');
        });
    });
}

function _swapChartImages(theme) {
    document.querySelectorAll('img[data-light-src]').forEach(img => {
        img.src = theme === 'dark' ? img.dataset.darkSrc : img.dataset.lightSrc;
    });
}

// On page load, restore saved preference (default: light)
const saved = localStorage.getItem('theme') ?? 'light';
document.documentElement.setAttribute('data-theme', saved);
// Fix up any icons already in the server-rendered HTML (e.g. about/subscription
// contact icons) to match; images built later by page scripts pick their own
// src at creation time instead.
_swapChartImages(saved);

document.addEventListener('DOMContentLoaded', async () => {
    dropdownInit();

    const res = await fetch('/api/toasts');
    if (!res.ok) return;
    const toasts = await res.json();
    toasts.forEach(t => toast(t.message, t.type));
});
