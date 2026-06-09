/* ═══════════════════════════════════════════════════════
   QR LINK GENERATOR — CLIENT-SIDE LOGIC
════════════════════════════════════════════════════════ */

const dropZone      = document.getElementById('drop-zone');
const fileInput     = document.getElementById('file-input');
const fileList      = document.getElementById('file-list');
const processBtn    = document.getElementById('process-btn');
const loadingOv     = document.getElementById('loading-overlay');
const resultsSection= document.getElementById('results-section');
const statsRow      = document.getElementById('stats-row');
const tableHead     = document.getElementById('table-head');
const tableBody     = document.getElementById('table-body');
const downloadBtn   = document.getElementById('download-btn');
const automateBtn   = document.getElementById('automate-btn');
const automationSec = document.getElementById('automation-section');
const statusText    = document.getElementById('status-text');
const statusDot     = document.querySelector('.status-dot');
const logBox        = document.getElementById('log-box');
const toast         = document.getElementById('toast');

let selectedFiles = [];
let automationPollInterval = null;

// ── TOAST ─────────────────────────────────────────────
function showToast(msg, duration = 3500) {
  toast.textContent = msg;
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), duration);
}

// ── FILE SELECTION ─────────────────────────────────────
dropZone.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', () => handleFiles(Array.from(fileInput.files)));

dropZone.addEventListener('dragover', e => {
  e.preventDefault();
  dropZone.classList.add('drag-over');
});
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
dropZone.addEventListener('drop', e => {
  e.preventDefault();
  dropZone.classList.remove('drag-over');
  handleFiles(Array.from(e.dataTransfer.files));
});

function handleFiles(files) {
  const allowed = files.filter(f => f.name.match(/\.xlsx?$/i));
  if (allowed.length !== files.length) showToast('⚠️ Only .xlsx and .xls files are accepted');
  allowed.forEach(f => {
    if (!selectedFiles.find(sf => sf.name === f.name)) selectedFiles.push(f);
  });
  renderFileList();
}

function renderFileList() {
  fileList.innerHTML = '';
  selectedFiles.forEach((f, i) => {
    const chip = document.createElement('div');
    chip.className = 'file-chip';
    chip.innerHTML = `
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
      ${f.name}
      <span class="remove" data-idx="${i}" title="Remove">✕</span>
    `;
    fileList.appendChild(chip);
  });

  fileList.querySelectorAll('.remove').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      selectedFiles.splice(parseInt(btn.dataset.idx), 1);
      renderFileList();
    });
  });

  processBtn.disabled = selectedFiles.length === 0;
}

// ── PROCESS ────────────────────────────────────────────
processBtn.addEventListener('click', async () => {
  if (selectedFiles.length === 0) return;

  const formData = new FormData();
  selectedFiles.forEach(f => formData.append('files', f));

  processBtn.disabled = true;
  loadingOv.style.display = 'flex';
  resultsSection.classList.add('hidden');

  try {
    const res = await fetch('/process', { method: 'POST', body: formData });
    const data = await res.json();

    if (!res.ok || data.error) {
      showToast(`❌ Error: ${data.error}`);
      return;
    }

    renderResults(data);
    showToast(`✅ Processed ${data.stats.products_extracted} products from ${data.stats.files_processed} file(s)`);

  } catch (err) {
    showToast('❌ Network error. Is the server running?');
  } finally {
    loadingOv.style.display = 'none';
    processBtn.disabled = false;
  }
});

// ── RENDER RESULTS ─────────────────────────────────────
function renderResults(data) {
  const { stats, columns, rows } = data;

  // Stats
  statsRow.innerHTML = `
    <div class="stat-card">
      <div class="stat-value">${stats.files_processed}</div>
      <div class="stat-label">Files</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">${stats.products_extracted}</div>
      <div class="stat-label">Products</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">${stats.errors_logged}</div>
      <div class="stat-label">Errors</div>
    </div>
  `;

  // Table head
  tableHead.innerHTML = '<tr>' + columns.map(c => `<th>${c}</th>`).join('') + '</tr>';

  // Table body
  tableBody.innerHTML = '';
  rows.forEach((row, idx) => {
    const tr = document.createElement('tr');
    tr.innerHTML = columns.map(col => {
      const val = row[col] ?? '';
      if (col === 'URL' && val) {
        return `<td><a href="${val}" target="_blank" rel="noopener">${val}</a></td>`;
      }
      return `<td title="${val}">${val}</td>`;
    }).join('');
    tableBody.appendChild(tr);
  });

  resultsSection.classList.remove('hidden');
  resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ── DOWNLOAD ───────────────────────────────────────────
downloadBtn.addEventListener('click', () => {
  window.location.href = '/download';
  showToast('📥 Downloading processed file…');
});

// ── AUTOMATE ───────────────────────────────────────────
automateBtn.addEventListener('click', async () => {
  automateBtn.disabled = true;
  automationSec.classList.remove('hidden');
  logBox.innerHTML = '<p class="log-entry" style="color:var(--text-3)">Starting HoverCode automation…</p>';
  statusDot.className = 'status-dot running';
  statusText.textContent = 'Opening browser… Please log in to HoverCode when prompted.';

  try {
    const res = await fetch('/automate', { method: 'POST' });
    const data = await res.json();

    if (!res.ok || data.error) {
      showToast(`❌ ${data.error}`);
      automateBtn.disabled = false;
      return;
    }

    showToast('🤖 HoverCode automation started — check the browser window!');
    startPolling();

  } catch (err) {
    showToast('❌ Failed to start automation');
    automateBtn.disabled = false;
  }

  automationSec.scrollIntoView({ behavior: 'smooth', block: 'start' });
});

function startPolling() {
  if (automationPollInterval) clearInterval(automationPollInterval);

  automationPollInterval = setInterval(async () => {
    try {
      const res = await fetch('/automate/status');
      const data = await res.json();

      // Append new log lines
      const existing = logBox.querySelectorAll('.log-entry').length;
      data.log.slice(existing).forEach(line => {
        const p = document.createElement('p');
        p.className = 'log-entry';
        p.textContent = line;
        logBox.appendChild(p);
        logBox.scrollTop = logBox.scrollHeight;
      });

      if (!data.running) {
        clearInterval(automationPollInterval);
        statusDot.className = 'status-dot done';
        statusText.textContent = 'Automation complete!';
        automateBtn.disabled = false;
        showToast('✅ HoverCode automation finished!');
      }
    } catch {}
  }, 2000);
}
