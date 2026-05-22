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

// Load combined header + navbar
function loadNavbar(logo = '') {
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    const _logoFallback = `/static/resources/${isDark ? 'statline-logo' : 'statline-logo-light'}.svg`;
    const _isFallback = !logo;
    const avatarHTML = `<div class="avatar"><img src="${logo || _logoFallback}" alt="School logo" data-is-statline-fallback="${_isFallback}" onerror="this.src='${_logoFallback}'; this.dataset.isStatlineFallback='true'"></div>`;

    const p = window.location.pathname;
    const active = {
        home:     p === '/',
        file:     p.startsWith('/upload'),
        view:     p.startsWith('/report'),
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
                            <a href="/upload" onclick="uploadFile(); return false;">Upload</a>
                            <a href="#" id="nav-download-link" onclick="downloadPDFs(); return false;">Download</a>
                        </div>
                    </div>
                    <div class="nav-dropdown">
                        <a href="javascript:void(0)" class="nav-link${a('view')}">View ▾</a>
                        <div class="dropdown-content">
                            <a href="/report">Season Report</a>
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
                    ${avatarHTML}
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
        </footer>
    `;
    document.getElementById('footer-placeholder').innerHTML = footerHTML;
}

function _swapChartImages(theme) {
    document.querySelectorAll('img[data-light-src]').forEach(img => {
        img.src = theme === 'dark' ? img.dataset.darkSrc : img.dataset.lightSrc;
    });
}

// On page load, restore saved preference (default: light)
const saved = localStorage.getItem('theme') ?? 'light';
document.documentElement.setAttribute('data-theme', saved);
