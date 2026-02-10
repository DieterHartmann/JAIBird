/**
 * JAIBird Executive Dashboard – Chart.js powered visualisations.
 *
 * Fetches data from /api/dashboard/full and renders:
 *   - Top 10 Companies bar chart
 *   - Category breakdown horizontal bar
 *   - Volume over time line chart
 *   - Strategic vs Noise doughnut
 *   - Strategic highlights table
 *   - Company-category heatmap table
 */

// ---------------------------------------------------------------------------
// Colour palette (Bootstrap-ish, accessible)
// ---------------------------------------------------------------------------
const COLOURS = [
    '#0d6efd', '#198754', '#ffc107', '#dc3545', '#0dcaf0',
    '#6f42c1', '#fd7e14', '#20c997', '#d63384', '#6610f2',
    '#0a58ca', '#146c43', '#cc9a06', '#b02a37', '#087990',
];

const COLOUR_STRATEGIC = '#198754';
const COLOUR_NOISE     = '#adb5bd';
const COLOUR_URGENT    = '#dc3545';
const COLOUR_NORMAL    = '#0d6efd';

// Category colour map for consistent colouring
const CATEGORY_COLOURS = {};
function getCategoryColour(cat, idx) {
    if (!CATEGORY_COLOURS[cat]) {
        CATEGORY_COLOURS[cat] = COLOURS[Object.keys(CATEGORY_COLOURS).length % COLOURS.length];
    }
    return CATEGORY_COLOURS[cat];
}

// ---------------------------------------------------------------------------
// Chart instances (so we can destroy & re-create on updates)
// ---------------------------------------------------------------------------
let chartTopCompanies = null;
let chartCategories   = null;
let chartVolume       = null;
let chartNoise        = null;

// Cached dashboard data
let dashData = null;

// ---------------------------------------------------------------------------
// Initialise
// ---------------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', () => {
    fetchDashboardData();

    // Wire up toggles
    document.getElementById('topCoExcludeNoise')?.addEventListener('change', () => renderTopCompanies());
    document.getElementById('catShowNoise')?.addEventListener('change', () => renderCategories());

    // Wire up time-bucket buttons
    document.querySelectorAll('[data-bucket]').forEach(btn => {
        btn.addEventListener('click', (e) => {
            document.querySelectorAll('[data-bucket]').forEach(b => b.classList.remove('active'));
            e.target.classList.add('active');
            renderVolume();
        });
    });

    // Wire up days filter
    document.getElementById('dashDaysFilter')?.addEventListener('change', () => fetchDashboardData());
});

// Global refresh helper (called from the refresh button)
function refreshDashboard() {
    fetchDashboardData();
}

// ---------------------------------------------------------------------------
// Data fetching
// ---------------------------------------------------------------------------
async function fetchDashboardData() {
    try {
        const days = document.getElementById('dashDaysFilter')?.value || '';
        const url = days ? `/api/dashboard/full?days=${days}` : '/api/dashboard/full';
        const resp = await fetch(url);
        const json = await resp.json();

        if (json.status !== 'success') {
            console.error('Dashboard data error:', json.message);
            return;
        }

        dashData = json.data;
        renderAll();
    } catch (err) {
        console.error('Failed to fetch dashboard data:', err);
    }
}

function renderAll() {
    if (!dashData) return;
    updateKPIs();
    renderTopCompanies();
    renderCategories();
    renderVolume();
    renderNoiseDoughnut();
    renderHighlights();
    renderHeatmap();
}

// ---------------------------------------------------------------------------
// KPI Cards
// ---------------------------------------------------------------------------
function updateKPIs() {
    const ns = dashData.noise_summary;
    setTextIfExists('kpiTotal', ns.total);
    setTextIfExists('kpiStrategic', ns.strategic);
    setTextIfExists('kpiStrategicPct', `${(100 - ns.noise_pct).toFixed(0)}% of total`);
    setTextIfExists('kpiNoise', ns.noise);
    setTextIfExists('kpiNoisePct', `${ns.noise_pct}% of total`);

    const urg = dashData.urgency;
    setTextIfExists('kpiUrgent', urg.urgent);
}

function setTextIfExists(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
}

// ---------------------------------------------------------------------------
// Top 10 Companies (horizontal bar)
// ---------------------------------------------------------------------------
function renderTopCompanies() {
    const excludeNoise = document.getElementById('topCoExcludeNoise')?.checked;
    const raw = excludeNoise ? dashData.top_companies_strategic : dashData.top_companies;

    const labels = raw.map(d => truncLabel(d.company, 30));
    const data   = raw.map(d => d.count);

    if (chartTopCompanies) chartTopCompanies.destroy();

    const ctx = document.getElementById('chartTopCompanies')?.getContext('2d');
    if (!ctx) return;

    chartTopCompanies = new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                label: 'Announcements',
                data,
                backgroundColor: COLOURS.slice(0, data.length),
                borderRadius: 4,
                maxBarThickness: 28,
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        title: (items) => raw[items[0].dataIndex].company,
                    }
                }
            },
            scales: {
                x: { beginAtZero: true, grid: { display: false } },
                y: { grid: { display: false } }
            }
        }
    });
}

// ---------------------------------------------------------------------------
// Category Breakdown (horizontal bar)
// ---------------------------------------------------------------------------
function renderCategories() {
    const includeNoise = document.getElementById('catShowNoise')?.checked;
    const raw = includeNoise ? dashData.category_breakdown_all : dashData.category_breakdown;

    const labels = raw.map(d => d.category);
    const data   = raw.map(d => d.count);
    const colours = raw.map((d, i) => getCategoryColour(d.category, i));

    if (chartCategories) chartCategories.destroy();

    const ctx = document.getElementById('chartCategories')?.getContext('2d');
    if (!ctx) return;

    chartCategories = new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                label: 'Count',
                data,
                backgroundColor: colours,
                borderRadius: 4,
                maxBarThickness: 24,
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
            },
            scales: {
                x: { beginAtZero: true, grid: { display: false } },
                y: { grid: { display: false }, ticks: { font: { size: 11 } } }
            }
        }
    });
}

// ---------------------------------------------------------------------------
// Volume Over Time (line / bar)
// ---------------------------------------------------------------------------
function renderVolume() {
    const activeBtn = document.querySelector('[data-bucket].active');
    const bucket = activeBtn ? activeBtn.dataset.bucket : 'day';
    const raw = bucket === 'week' ? dashData.volume_by_week : dashData.volume_by_day;

    const labels = raw.map(d => formatDateLabel(d.date, bucket));
    const data   = raw.map(d => d.count);

    if (chartVolume) chartVolume.destroy();

    const ctx = document.getElementById('chartVolume')?.getContext('2d');
    if (!ctx) return;

    chartVolume = new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                label: 'SENS Announcements',
                data,
                backgroundColor: 'rgba(13, 110, 253, 0.6)',
                borderColor: '#0d6efd',
                borderWidth: 1,
                borderRadius: 3,
                fill: true,
                tension: 0.3,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { maxRotation: 45, font: { size: 10 } }
                },
                y: { beginAtZero: true, grid: { color: '#f0f0f0' } }
            }
        }
    });
}

// ---------------------------------------------------------------------------
// Strategic vs Noise Doughnut
// ---------------------------------------------------------------------------
function renderNoiseDoughnut() {
    const ns = dashData.noise_summary;

    if (chartNoise) chartNoise.destroy();

    const ctx = document.getElementById('chartNoise')?.getContext('2d');
    if (!ctx) return;

    chartNoise = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Strategic', 'Noise / Admin'],
            datasets: [{
                data: [ns.strategic, ns.noise],
                backgroundColor: [COLOUR_STRATEGIC, COLOUR_NOISE],
                borderWidth: 2,
                borderColor: '#fff',
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '65%',
            plugins: {
                legend: { position: 'bottom', labels: { font: { size: 12 } } },
                tooltip: {
                    callbacks: {
                        label: (ctx) => {
                            const pct = ((ctx.raw / ns.total) * 100).toFixed(1);
                            return ` ${ctx.label}: ${ctx.raw} (${pct}%)`;
                        }
                    }
                }
            }
        }
    });
}

// ---------------------------------------------------------------------------
// Strategic Highlights Table
// ---------------------------------------------------------------------------
function renderHighlights() {
    const tbody = document.getElementById('highlightsBody');
    if (!tbody) return;

    const data = dashData.strategic_highlights || [];

    if (data.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="4" class="text-center text-muted py-4">
                    <i class="bi bi-inbox fs-3"></i>
                    <p class="mt-2 mb-0">No strategic announcements in this period</p>
                </td>
            </tr>`;
        return;
    }

    const categoryBadgeClass = (cat) => {
        const map = {
            'Trading Statements & Updates': 'bg-danger',
            'Financial Results': 'bg-primary',
            'Acquisitions & Disposals': 'bg-warning text-dark',
            'Dealings by Directors': 'bg-info text-dark',
            'Board & Management Changes': 'bg-secondary',
            'Cautionary Announcements': 'bg-danger',
            'Dividends & Distributions': 'bg-success',
        };
        return map[cat] || 'bg-dark';
    };

    tbody.innerHTML = data.map(item => {
        const dt = item.date_published
            ? new Date(item.date_published).toLocaleDateString('en-ZA', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
            : '—';
        return `
            <tr>
                <td><strong class="small">${escHtml(item.company_name)}</strong></td>
                <td class="small">${escHtml(item.title)}</td>
                <td><span class="badge ${categoryBadgeClass(item.category)} small">${escHtml(item.category)}</span></td>
                <td class="small text-muted text-nowrap">${dt}</td>
            </tr>`;
    }).join('');
}

// ---------------------------------------------------------------------------
// Company-Category Heatmap
// ---------------------------------------------------------------------------
function renderHeatmap() {
    const hm = dashData.company_heatmap;
    if (!hm || !hm.companies.length) {
        document.getElementById('heatmapBody').innerHTML =
            '<tr><td colspan="2" class="text-center text-muted py-3">No data</td></tr>';
        return;
    }

    // Build header row
    const thead = document.getElementById('heatmapHead');
    thead.innerHTML = `
        <tr class="table-light">
            <th class="small" style="min-width:180px;">Company</th>
            ${hm.categories.map(c => `<th class="small text-center" style="writing-mode: vertical-lr; transform: rotate(180deg); max-width:40px; font-size:0.7rem;">${escHtml(c)}</th>`).join('')}
        </tr>`;

    // Find max value for colour scaling
    const maxVal = Math.max(...hm.matrix.flat(), 1);

    const tbody = document.getElementById('heatmapBody');
    tbody.innerHTML = hm.companies.map((company, rowIdx) => {
        const cells = hm.matrix[rowIdx].map(val => {
            const intensity = val / maxVal;
            const bg = val === 0
                ? '#f8f9fa'
                : `rgba(13, 110, 253, ${0.15 + intensity * 0.7})`;
            const textCol = intensity > 0.5 ? '#fff' : '#333';
            return `<td class="text-center small" style="background:${bg};color:${textCol};font-weight:${val ? 600 : 400};">${val || ''}</td>`;
        }).join('');
        return `<tr><td class="small fw-bold">${escHtml(truncLabel(company, 35))}</td>${cells}</tr>`;
    }).join('');
}

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------
function truncLabel(text, max) {
    if (!text) return '';
    return text.length > max ? text.substring(0, max - 1) + '\u2026' : text;
}

function formatDateLabel(dateStr, bucket) {
    if (!dateStr) return '';
    if (bucket === 'month') return dateStr; // e.g. "2026-01"
    // For day/week, show "dd Mon"
    const d = new Date(dateStr + 'T00:00:00');
    return d.toLocaleDateString('en-ZA', { day: '2-digit', month: 'short' });
}

function escHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
