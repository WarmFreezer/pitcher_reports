let currentUploadResult = null;

// Display game data and upload summary combined
function displayGameData(data) {
    const contentArea = document.getElementById('gameDataDisplay');
    if (!contentArea) return;

    const { game_data, message, merged_pdf_url } = data;
    document.title = `${game_data.away_team} @ ${game_data.home_team}`;

    const downloadButton = merged_pdf_url
        ? `<a href="${merged_pdf_url}" download="all_pitcher_reports.pdf" class="download-btn" style="text-decoration: none;">Download Full PDF</a>`
        : '';

    contentArea.innerHTML = `
        <div class="bubble" style="display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap;">
            <div>
                <h2>${game_data.away_team} @ ${game_data.home_team}</h2>
                <p>${game_data.date}</p>
                <p>${message}</p>
            </div>
            <div style="display: flex; gap: 12px; flex-wrap: wrap; align-items: center;">
                ${downloadButton}
                <button id="save-to-db-btn" class="upload-btn" onclick="saveToDb()">Save to DB</button>
            </div>
        </div>
    `;
}

async function saveToDb() {
    if (!currentUploadResult) {
        toast('No file loaded.', 'error');
        return;
    }

    const btn = document.getElementById('save-to-db-btn');
    if (btn) {
        btn.disabled = true;
        btn.textContent = 'Saving...';
    }

    try {
        const res = await fetch('/api/save-game', { method: 'POST' });
        const data = await res.json();
        if (res.ok) {
            toast(data.message || 'Game saved.', 'success');
            if (btn) btn.textContent = 'Saved';
        } else {
            toast(data.error || 'Failed to save game.', 'error');
            if (btn) {
                btn.disabled = false;
                btn.textContent = 'Save to DB';
            }
        }
    } catch (e) {
        toast('Error saving game: ' + e.message, 'error');
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Save to DB';
        }
    }
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
    const spinnerStart = Date.now();
    if (reportOutput) {
        reportOutput.innerHTML = `<svg viewBox="0 0 90 90" xmlns="http://www.w3.org/2000/svg" style="width: 48px; margin: 32px auto; display: block;" aria-label="Loading...">
  <rect x="20" y="20" width="50" height="50" fill="var(--bg-bubble)" transform="rotate(45 45 45)"/>
  <line x1="26" y1="47" x2="64" y2="47" stroke="#8B1A1A" stroke-width="1.8" stroke-linecap="round"/>
  <line x1="30" y1="53" x2="60" y2="53" stroke="#8B1A1A" stroke-width="1" stroke-linecap="round" opacity="0.5"/>
  <path d="M 45,90 L 90,45 L 45,0.5 L 0.5,45 L 45,90" fill="none" stroke="var(--text-primary)" stroke-width="2.2" stroke-linecap="butt" stroke-dasharray="0 253.44" stroke-dashoffset="253.44">
    <animate attributeName="stroke-dasharray" values="0 253.44; 126.72 126.72; 0 253.44" keyTimes="0;0.5;1" dur="5s" calcMode="spline" keySplines="0.5 0 0.5 1;0.5 0 0.5 1" repeatCount="indefinite"/>
    <animate attributeName="stroke-dashoffset" values="253.44;253.44;0" keyTimes="0;0.5;1" dur="5s" calcMode="spline" keySplines="0.5 0 0.5 1;0.5 0 0.5 1" repeatCount="indefinite"/>
  </path>
</svg>`;
    }

    const formData = new FormData();
    formData.append('file', file);
    formData.append('target', document.getElementById('targetToggle')?.checked ? 'opponent' : 'own');

    const minDisplay = 600;

    try {
        const response = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            const elapsed = Date.now() - spinnerStart;
            if (elapsed < minDisplay) await new Promise(r => setTimeout(r, minDisplay - elapsed));
            toast(err.error || 'An error occurred while processing the file.', 'error');
            if (reportOutput) reportOutput.innerHTML = '';
            event.target.value = '';
            return;
        }

        const result = await response.json();
        const elapsed = Date.now() - spinnerStart;
        if (elapsed < minDisplay) await new Promise(r => setTimeout(r, minDisplay - elapsed));

        if (result.merged_pdf_url) {
            updateDownloadLink(true, result.merged_pdf_url);
        }

        currentUploadResult = result;
        displayGameData({
            game_data: result.game_data,
            message: result.message,
            merged_pdf_url: result.merged_pdf_url
        });

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
        if (reportOutput) reportOutput.innerHTML = '';
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

    const currentTheme = document.documentElement.getAttribute('data-theme') ?? 'light';

    const heatmapContainer = clone.querySelector('.pitcher-heatmap');
    if (heatmapContainer) {
        for (const [lightSrc, darkSrc, label] of [
            [data.heatmap_left_url,  data.heatmap_left_dark_url,  'vs Left-Handed Batters'],
            [data.heatmap_right_url, data.heatmap_right_dark_url, 'vs Right-Handed Batters'],
        ]) {
            const wrapper = document.createElement('div');
            wrapper.className = 'graph-block';
            const title = document.createElement('p');
            title.className = 'graph-title';
            title.textContent = label;
            const img = document.createElement('img');
            img.dataset.lightSrc = lightSrc;
            img.dataset.darkSrc = darkSrc;
            img.src = currentTheme === 'dark' ? darkSrc : lightSrc;
            img.alt = `${data.pitcher_name} Heat Map ${label}`;
            img.className = 'report-img report-img-heatmap';
            img.onerror = function() { this.style.display = 'none'; };
            wrapper.appendChild(title);
            wrapper.appendChild(img);
            heatmapContainer.appendChild(wrapper);
        }
    }

    const breakmapContainer = clone.querySelector('.pitcher-breakmap');
    if (breakmapContainer) {
        const wrapper = document.createElement('div');
        wrapper.className = 'graph-block';
        const title = document.createElement('p');
        title.className = 'graph-title';
        title.textContent = data.arm_angle ? `Pitch Break — Arm Angle: ${data.arm_angle}` : 'Pitch Break';
        const img = document.createElement('img');
        img.dataset.lightSrc = data.breakmap_url;
        img.dataset.darkSrc = data.breakmap_dark_url;
        img.src = currentTheme === 'dark' ? data.breakmap_dark_url : data.breakmap_url;
        img.alt = `${data.pitcher_name} Break Map`;
        img.className = 'report-img report-img-breakmap';
        img.onerror = function() {
            this.parentElement.innerHTML = '<p style="color: red;">Breakmap image not available. Update your subscription.</p>';
        };
        wrapper.appendChild(title);
        wrapper.appendChild(img);
        breakmapContainer.appendChild(wrapper);
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

    const header = clone.querySelector('.pitcher-report-header');
    const body = clone.querySelector('.pitcher-report-body');
    header.addEventListener('click', () => {
        const isOpen = body.classList.toggle('open');
        header.classList.toggle('open', isOpen);
    });

    document.querySelector('#report-output')?.appendChild(clone);
}
