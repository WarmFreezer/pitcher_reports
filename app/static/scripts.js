// Display uploaded data preview
function displayUploadData(data) {
    const contentArea = document.getElementById('uploadDataDisplay');
    if (!contentArea) return;

    const downloadButton = data.merged_pdf_url
        ? `<a href="${data.merged_pdf_url}" download="all_pitcher_reports.pdf" class="download-btn" style="text-decoration: none;">Download Full PDF</a>`
        : '';

    contentArea.innerHTML = `
        <div style="background: white; padding: 32px; margin: 32px; border-radius: 32px; background-color: var(--msu-light);">
            <h2>File Upload Summary</h2>
            <p>${data.message}</p>
            ${downloadButton}
        </div>
    `;
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
                        <a href="#" onclick="uploadFile(); return false;">📤 Upload</a>
                        <a href="#" id="nav-download-link" onclick="downloadPDFs(); return false;">📥 Download</a>
                        <a href="#print">🖨️ Print</a>
                        <a href="#save">💾 Save</a>
                    </div>
                </li>
                <li class="dropdown">
                    <a href="javascript:void(0)" class="nav-link">View ▼</a>
                    <div class="dropdown-content">
                        <a href="/report">📋 Full Report</a>
                    </div>
                </li>
                <li class="dropdown">
                    <a href="javascript:void(0)" class="nav-link">Tools ▼</a>
                    <div class="dropdown-content">
                        <a href="#settings">⚙️ Settings</a>
                    </div>
                </li>
                <li><a href="#help" class="nav-link">Help</a></li>
            </ul>
        </nav>
    `;
    document.getElementById('navbar-placeholder').innerHTML = navbarHTML;

    updateDownloadLink(false);
}

// Enable or disable download link
function updateDownloadLink(hasReports, downloadUrl = null)
{
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

// Trigger file upload
function uploadFile() {
    document.getElementById('fileUpload').click();
}

// Handle file upload
async function handleFileSelect(event) {
    const file = event.target.files[0];
    if (!file) return;

    // Show loading indicator
    const reportOutput = document.querySelector('#report-output');
    if (reportOutput) {
        reportOutput.innerHTML = '<p>Processing file and generating reports...</p>';
    }

    const formData = new FormData();
    formData.append('file', file);
    
    try {
        const response = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            throw new Error('HTTP Error: ' + response.status);
        }

        const result = await response.json();
        
        // Enable Download link if merged PDF URL is provided
        if (result.merged_pdf_url) {
            updateDownloadLink(true, result.merged_pdf_url);
        }

        // Display upload summary
        displayUploadData({
            message: result.message,
            num_reports: result.num_reports,
            merged_pdf_url: result.merged_pdf_url
        });

        // Clear existing reports
        if (reportOutput) {
            reportOutput.innerHTML = '';
        }

        // Build all reports from the returned data
        if (result.reports && result.reports.length > 0) {
            buildAllReports(result.reports);
        } else {
            if (reportOutput) {
                reportOutput.innerHTML = '<p>No reports generated.</p>';
            }
        }
    } catch (error) {
        console.error('Error uploading file:', error);
        alert('Error uploading file: ' + error.message);
        if (reportOutput) {
            reportOutput.innerHTML = `<p style="color: red;">Error: ${error.message}</p>`;
        }
    }

    event.target.value = '';
}

// Build all reports from array of report data
function buildAllReports(reports) {
    reports.forEach(reportData => {
        generateReport(reportData);
    });
}

// Load header
function loadHeader(title = "Pitcher Report", pfp = "/static/resources/HomePlate.png") {
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
                    <img src="/static/resources/strutting_eagle.png" height="128" alt="Strutting Eagle">
                </div>
            </div>
        </header>
    `;
    document.getElementById('header-placeholder').innerHTML = headerHTML;
}

// Load footer
function loadFooter() {
    const footerHTML = `
        <footer class="site-footer">
            <p>&copy; 2026 Thomas Eubank</p>
        </footer>
    `;
    document.getElementById('footer-placeholder').innerHTML = footerHTML;
}

// Generate a single report from template
function generateReport(data) {
    const template = document.querySelector('#pitcher-report-template');
    if (!template) {
        console.error('Template #pitcher-report-template not found');
        return;
    }

    const clone = template.content.cloneNode(true);

    // Update pitcher name
    const nameElement = clone.querySelector('.user-name');
    if (nameElement) {
        nameElement.textContent = data.pitcher_name;
    }

    // Add download pdf button for each report
    const downloadContainer = clone.querySelector('.download-container');
    if (downloadContainer) {
        if (data.pdf_url) {
            downloadContainer.innerHTML = `
                <a href="${data.pdf_url}" download="pitcher_${data.pitcher_id}_report.pdf" class="download-btn-small">
                    📄 Download PDF
                </a>
            `;
            console.log('Added download button for:', data.pitcher_name, data.pdf_url);
        } else {
            console.warn('No PDF URL provided for:', data.pitcher_name);
        }
    } else {
        console.error('Download container not found for:', data.pitcher_name);
    }

    // Add heatmap image
    const heatmapContainer = clone.querySelector('.pitcher-heatmap');
    if (heatmapContainer) {
        const img = document.createElement('img');
        img.src = data.image_url;
        img.alt = `${data.pitcher_name} Heat Map`;
        img.width = 800;
        img.onerror = function() {
            console.error('Failed to load image:', this.src);
            this.alt = 'Image not available';
        };
        heatmapContainer.appendChild(img);
    }

    // Add pitcher table
    const tableContainer = clone.querySelector('.pitcher-table');
    if (tableContainer && data.pitcher_table) {
        tableContainer.innerHTML = data.pitcher_table;
        tableContainer.style.fontSize = '12px';
    }

    const newLine = document.createElement('br');
    clone.appendChild(newLine);
    
    const reportOutputElement = document.querySelector('#report-output');
    if (reportOutputElement) {
        reportOutputElement.appendChild(clone);
    }
}

// Build HTML table from string data
function buildTableFromString(table, tableString) {
    const lines = tableString.trim().split("\n");
    
    if (lines.length === 0) return;

    // Create header row
    const headers = lines[0].split(/\s+/);
    const thead = document.createElement("thead");
    const headerRow = document.createElement("tr");

    headers.forEach(headerText => {
        const th = document.createElement("th");
        th.textContent = headerText;
        headerRow.appendChild(th);
    });

    thead.appendChild(headerRow);
    table.appendChild(thead);

    // Create body rows
    const tbody = document.createElement("tbody");
    for (let i = 1; i < lines.length; i++) {
        const row = document.createElement("tr");
        const values = lines[i].split(/\s+/);

        values.forEach(value => {
            const td = document.createElement("td");
            td.textContent = value;
            row.appendChild(td);
        });

        tbody.appendChild(row);
    }
    table.appendChild(tbody);
}