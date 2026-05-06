// HEAD request avoids downloading the full body — used to check logos and pfps before rendering
async function fileExists(url) {
    try {
        const response = await fetch(url, { method: 'HEAD' });
        return response.ok;
    } catch {
        return false;
    }
}

// Load navbar
function loadNavbar() {
    const navbarHTML = `
        <nav class="main-nav">
            <ul class="nav-list">
                <li><a href="/" class="nav-link">Home</a></li>
                <li class="dropdown">
                    <a href="javascript:void(0)" class="nav-link">File ▼</a>
                    <div class="dropdown-content">
                        <a href="/upload" onclick="uploadFile(); return false;">📤 Upload</a>
                        <a href="#" id="nav-download-link" onclick="downloadPDFs(); return false;">📥 Download</a>
                    </div>
                </li>
                <li class="dropdown">
                    <a href="javascript:void(0)" class="nav-link">View ▼</a>
                    <div class="dropdown-content">
                        <a href="/report">📋 Season Report</a>
                    </div>
                </li>
                <li class="dropdown">
                    <a href="javascript:void(0)" class="nav-link">Settings ▼</a>
                    <div class="dropdown-content">
                        <a href="/account">👤 Account</a>
                        <a href="/subscription">💳 Subscription</a>
                    </div>
                </li>
                <li><a href="/about" class="nav-link">About</a></li>
                <li style="margin-left: auto;">
                    <a href="/logout" class="nav-link">
                        <button style="background: none; border: none; color: white; cursor: pointer; font-size: inherit; font-family: 'Cambria', serif; padding-right: 16px;">Logout</button>
                    </a>
                </li>
            </ul>
        </nav>
    `;
    document.getElementById('navbar-placeholder').innerHTML = navbarHTML;
    updateDownloadLink(false);
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
        alert('No reports available for download.');
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

// Load header
async function loadHeader(title = "Pitcher Report", pfp = "/static/resources/HomePlate.png", logo = "/static/resources/HomePlate.png") {
    if (!await fileExists(pfp)) {
        pfp = "/static/resources/HomePlate.png";
    }
    if (!await fileExists(logo)) {
        logo = "/static/resources/HomePlate.png";
    }

    const headerHTML = `
        <header class="site-header">
            <div class="header-container">
                <div class="header-left">
                    <img src=${pfp} height="128" alt="MSU Logo">
                </div>
                <div class="header-center">
                    <h1>${title}</h1>
                </div>
                <div class="header-right">
                    <img src=${logo} height="128" alt="App Icon">
                </div>
            </div>
        </header>
    `;
    document.getElementById('header-placeholder').innerHTML = headerHTML;
    setTimeout(() => {
        const header = document.querySelector('.site-header');
        if (header) header.classList.add('loaded');
    }, 10);
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
