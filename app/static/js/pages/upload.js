// Display uploaded data preview
function displayUploadData(data) {
    const contentArea = document.getElementById('uploadDataDisplay');
    if (!contentArea) return;

    const downloadButton = data.merged_pdf_url
        ? `<a href="${data.merged_pdf_url}" download="all_pitcher_reports.pdf" class="download-btn" style="text-decoration: none;">Download Full PDF</a>`
        : '';

    contentArea.innerHTML = `
        <div class="bubble">
            <h2>File Upload Summary</h2>
            <p>${data.message}</p>
            ${downloadButton}
        </div>
    `;
}

// Display game data preview
function displayGameData(data) {
    const contentArea = document.getElementById('gameDataDisplay');
    if (!contentArea) return;

    const teamsTitle = `${data.game_data.away_team} @ ${data.game_data.home_team}`;
    document.title = teamsTitle;

    contentArea.innerHTML = `
        <div style="padding: 30px; background-color: var(--secondary);">
            <h2>Game Data</h2>
            <p>Date: ${data.game_data.date}</p>
            <p>Home Team: ${data.game_data.home_team}</p>
            <p>Away Team: ${data.game_data.away_team}</p>
        </div>
    `;
}

// Trigger file upload
function uploadFile() {
    document.getElementById('fileUpload').click();
}

// Handle file upload
async function handleFileSelect(event) {
    const file = event.target.files[0];
    if (!file) return;

    const reportOutput = document.querySelector('#report-output');
    if (reportOutput) {
        reportOutput.innerHTML = '<p style="margin: 32px;">Processing file and generating reports...</p>';
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

        if (result.merged_pdf_url) {
            updateDownloadLink(true, result.merged_pdf_url);
        }

        displayUploadData({
            message: result.message,
            num_reports: result.num_reports,
            merged_pdf_url: result.merged_pdf_url
        });

        displayGameData({ game_data: result.game_data });

        if (reportOutput) reportOutput.innerHTML = '';

        if (result.reports && result.reports.length > 0) {
            buildAllReports(result.reports);
        } else {
            if (reportOutput) {
                reportOutput.innerHTML = '<p style="margin: 32px;">No reports generated.</p>';
            }
        }
    } catch (error) {
        console.error('Error uploading file:', error);
        toast('Error uploading file: ' + error.message, 'error');
        if (reportOutput) {
            reportOutput.innerHTML = `<p style="color: red; margin: 32px;">Error: ${error.message}</p>`;
        }
    }

    event.target.value = '';
}

// Build all reports from array of report data
function buildAllReports(reports) {
    reports.forEach(reportData => generateReport(reportData));
}

// Stamps one pitcher's data into the hidden <template> element and appends the clone to the output area
function generateReport(data) {
    const template = document.querySelector('#pitcher-report-template');
    if (!template) {
        console.error('Template #pitcher-report-template not found');
        return;
    }

    const clone = template.content.cloneNode(true);

    const nameElement = clone.querySelector('.user-name');
    if (nameElement) nameElement.textContent = data.pitcher_name;

    const downloadContainer = clone.querySelector('.download-container');
    if (downloadContainer && data.pdf_url) {
        downloadContainer.innerHTML = `
            <a href="${data.pdf_url}" download="pitcher_${data.pitcher_id}_report.pdf" class="download-btn-small">
                📄 Download PDF
            </a>
        `;
    }

    const heatmapContainer = clone.querySelector('.pitcher-heatmap');
    if (heatmapContainer) {
        const img = document.createElement('img');
        img.src = data.heatmap_url;
        img.alt = `${data.pitcher_name} Heat Map`;
        img.className = 'report-img report-img-heatmap';
        // onerror fires when the image 404s (school subscription inactive = no charts generated)
        img.onerror = function() {
            this.parentElement.innerHTML = '<p style="color: red;">Heatmap image not available. Update your subscription.</p>';
        };
        heatmapContainer.appendChild(img);
    }

    const breakmapContainer = clone.querySelector('.pitcher-breakmap');
    if (breakmapContainer) {
        const img = document.createElement('img');
        img.src = data.breakmap_url;
        img.alt = `${data.pitcher_name} Break Map`;
        img.className = 'report-img report-img-breakmap';
        img.onerror = function() {
            this.parentElement.innerHTML = '<p style="color: red;">Breakmap image not available. Update your subscription.</p>';
        };
        breakmapContainer.appendChild(img);
    }

    const tableContainer = clone.querySelector('.pitcher-table');
    if (tableContainer && data.pitcher_table) {
        tableContainer.innerHTML = data.pitcher_table;
    }

    const leftUsageContainer = clone.querySelector('.left-usage');
    if (leftUsageContainer && data.left_usage_table) {
        leftUsageContainer.innerHTML = data.left_usage_table;
    }

    const rightUsageContainer = clone.querySelector('.right-usage');
    if (rightUsageContainer && data.right_usage_table) {
        rightUsageContainer.innerHTML = data.right_usage_table;
    }

    clone.appendChild(document.createElement('br'));
    document.querySelector('#report-output')?.appendChild(clone);
}
