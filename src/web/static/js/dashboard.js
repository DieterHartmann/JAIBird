/**
 * JAIBird Executive Dashboard – Chart.js powered visualisations.
 * Phase 1 + Phase 2 widgets.
 */

// ---------------------------------------------------------------------------
// Colour palette
// ---------------------------------------------------------------------------
const COLOURS = [
    '#0d6efd', '#198754', '#ffc107', '#dc3545', '#0dcaf0',
    '#6f42c1', '#fd7e14', '#20c997', '#d63384', '#6610f2',
    '#0a58ca', '#146c43', '#cc9a06', '#b02a37', '#087990',
];

const COLOUR_STRATEGIC = '#198754';
const COLOUR_NOISE     = '#adb5bd';

const CATEGORY_COLOURS = {};
function getCategoryColour(cat) {
    if (!CATEGORY_COLOURS[cat]) {
        CATEGORY_COLOURS[cat] = COLOURS[Object.keys(CATEGORY_COLOURS).length % COLOURS.length];
    }
    return CATEGORY_COLOURS[cat];
}

// ---------------------------------------------------------------------------
// Chart instances
// ---------------------------------------------------------------------------
let chartTopCompanies = null;
let chartCategories   = null;
let chartVolume       = null;
let chartNoise        = null;
let chartSector       = null;
let chartSentiment    = null;

let dashData = null;

// ---------------------------------------------------------------------------
// Initialise
// ---------------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', () => {
    fetchDashboardData();

    document.getElementById('topCoExcludeNoise')?.addEventListener('change', () => renderTopCompanies());
    document.getElementById('catShowNoise')?.addEventListener('change', () => renderCategories());

    document.querySelectorAll('[data-bucket]').forEach(btn => {
        btn.addEventListener('click', (e) => {
            document.querySelectorAll('[data-bucket]').forEach(b => b.classList.remove('active'));
            e.target.classList.add('active');
            renderVolume();
        });
    });

    document.getElementById('dashDaysFilter')?.addEventListener('change', () => fetchDashboardData());
});

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
        if (json.status !== 'success') { console.error('Dashboard error:', json.message); return; }
        dashData = json.data;
        renderAll();
    } catch (err) {
        console.error('Failed to fetch dashboard data:', err);
    }
}

function renderAll() {
    if (!dashData) return;
    // Each widget is independently try/caught so one failure doesn't break the rest
    const widgets = [
        updateKPIs, renderTodayTicker, renderTopCompanies, renderCategories,
        renderVolume, renderNoiseDoughnut, renderSectorChart, renderHighlights,
        renderHeatmap, renderDirectorSignal, renderUnusualAlerts,
        renderWatchlistPulse, renderSentiment, renderSummaryCards, renderEvents,
    ];
    widgets.forEach(fn => { try { fn(); } catch(e) { console.warn('Widget render error:', fn.name, e); } });
}

// ---------------------------------------------------------------------------
// KPI Cards
// ---------------------------------------------------------------------------
function updateKPIs() {
    const ns = dashData.noise_summary || {};
    setT('kpiTotal', ns.total || 0);
    setT('kpiStrategic', ns.strategic || 0);
    setT('kpiStrategicPct', ns.noise_pct != null ? `${(100 - ns.noise_pct).toFixed(0)}% of total` : '');
    setT('kpiNoise', ns.noise || 0);
    setT('kpiNoisePct', ns.noise_pct != null ? `${ns.noise_pct}% of total` : '');
    setT('kpiUrgent', (dashData.urgency || {}).urgent || 0);

    // Sentiment KPI
    const sent = dashData.sentiment || {};
    const sentScore = sent.overall_score || 0;
    const sentLabel = sent.overall_label || 'N/A';
    setT('kpiSentiment', sentScore > 0 ? `+${sentScore}` : String(sentScore));
    const sentEl = document.getElementById('kpiSentimentLabel');
    if (sentEl) {
        sentEl.textContent = sentLabel;
        sentEl.className = sentLabel === 'Positive' ? 'text-success' : (sentLabel === 'Negative' ? 'text-danger' : 'text-muted');
    }

    // Director Signal KPI
    const ds = dashData.director_signal || {};
    setT('kpiDirectorSignal', ds.signal || '--');
    setT('kpiDirectorDetail', `${ds.buys || 0} buys / ${ds.sells || 0} sells`);
    const dsCard = document.getElementById('kpiDirectorSignal');
    if (dsCard) {
        dsCard.className = 'mb-0 ' + (ds.signal === 'Net Buying' ? 'text-success' : (ds.signal === 'Net Selling' ? 'text-danger' : ''));
    }
}

function setT(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
}

// ---------------------------------------------------------------------------
// Today Ticker
// ---------------------------------------------------------------------------
function renderTodayTicker() {
    const items = dashData.today_strategic || [];
    const wrapper = document.getElementById('todayTickerWrapper');
    const content = document.getElementById('todayTickerContent');
    if (!wrapper || !content) return;

    if (items.length === 0) {
        wrapper.style.display = 'none';
        return;
    }

    wrapper.style.display = 'block';
    const html = items.map(item => {
        const dt = item.date_published ? new Date(item.date_published).toLocaleTimeString('en-ZA', {hour:'2-digit', minute:'2-digit'}) : '';
        return `<span class="ticker-item"><strong>${esc(item.company_name)}</strong>: ${esc(item.title)} <span class="text-muted">(${dt})</span></span>`;
    }).join('<span class="ticker-sep mx-3 text-muted">|</span>');

    content.innerHTML = html;
}

// ---------------------------------------------------------------------------
// Top 10 Companies (horizontal bar)
// ---------------------------------------------------------------------------
function renderTopCompanies() {
    const excludeNoise = document.getElementById('topCoExcludeNoise')?.checked;
    const raw = excludeNoise ? dashData.top_companies_strategic : dashData.top_companies;
    const labels = raw.map(d => trunc(d.company, 30));
    const data = raw.map(d => d.count);

    if (chartTopCompanies) chartTopCompanies.destroy();
    const ctx = document.getElementById('chartTopCompanies')?.getContext('2d');
    if (!ctx) return;

    chartTopCompanies = new Chart(ctx, {
        type: 'bar',
        data: { labels, datasets: [{ data, backgroundColor: COLOURS.slice(0, data.length), borderRadius: 4, maxBarThickness: 28 }] },
        options: {
            indexAxis: 'y', responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: false }, tooltip: { callbacks: { title: (i) => raw[i[0].dataIndex].company } } },
            scales: { x: { beginAtZero: true, grid: { display: false } }, y: { grid: { display: false } } }
        }
    });
}

// ---------------------------------------------------------------------------
// Category Breakdown
// ---------------------------------------------------------------------------
function renderCategories() {
    const includeNoise = document.getElementById('catShowNoise')?.checked;
    const raw = includeNoise ? dashData.category_breakdown_all : dashData.category_breakdown;
    const labels = raw.map(d => d.category);
    const data = raw.map(d => d.count);
    const colours = raw.map(d => getCategoryColour(d.category));

    if (chartCategories) chartCategories.destroy();
    const ctx = document.getElementById('chartCategories')?.getContext('2d');
    if (!ctx) return;

    chartCategories = new Chart(ctx, {
        type: 'bar',
        data: { labels, datasets: [{ data, backgroundColor: colours, borderRadius: 4, maxBarThickness: 24 }] },
        options: {
            indexAxis: 'y', responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: { x: { beginAtZero: true, grid: { display: false } }, y: { grid: { display: false }, ticks: { font: { size: 11 } } } }
        }
    });
}

// ---------------------------------------------------------------------------
// Volume Over Time
// ---------------------------------------------------------------------------
function renderVolume() {
    const activeBtn = document.querySelector('[data-bucket].active');
    const bucket = activeBtn ? activeBtn.dataset.bucket : 'day';
    const raw = bucket === 'week' ? dashData.volume_by_week : dashData.volume_by_day;
    const labels = raw.map(d => fmtDate(d.date, bucket));
    const data = raw.map(d => d.count);

    if (chartVolume) chartVolume.destroy();
    const ctx = document.getElementById('chartVolume')?.getContext('2d');
    if (!ctx) return;

    chartVolume = new Chart(ctx, {
        type: 'bar',
        data: { labels, datasets: [{ data, backgroundColor: 'rgba(13,110,253,0.6)', borderColor: '#0d6efd', borderWidth: 1, borderRadius: 3 }] },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: { x: { grid: { display: false }, ticks: { maxRotation: 45, font: { size: 10 } } }, y: { beginAtZero: true, grid: { color: '#f0f0f0' } } }
        }
    });
}

// ---------------------------------------------------------------------------
// Sector Doughnut
// ---------------------------------------------------------------------------
function renderSectorChart() {
    const raw = dashData.sector_breakdown || [];
    if (!raw.length) return;

    // Take top 8, lump rest into "Other"
    const top = raw.slice(0, 8);
    const other = raw.slice(8).reduce((s, d) => s + d.count, 0);
    if (other > 0) top.push({ sector: 'Other', count: other });

    if (chartSector) chartSector.destroy();
    const ctx = document.getElementById('chartSector')?.getContext('2d');
    if (!ctx) return;

    chartSector = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: top.map(d => d.sector),
            datasets: [{ data: top.map(d => d.count), backgroundColor: COLOURS.slice(0, top.length), borderWidth: 2, borderColor: '#fff' }]
        },
        options: {
            responsive: true, maintainAspectRatio: false, cutout: '55%',
            plugins: { legend: { position: 'right', labels: { font: { size: 10 }, boxWidth: 12 } } }
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
            datasets: [{ data: [ns.strategic, ns.noise], backgroundColor: [COLOUR_STRATEGIC, COLOUR_NOISE], borderWidth: 2, borderColor: '#fff' }]
        },
        options: {
            responsive: true, maintainAspectRatio: false, cutout: '65%',
            plugins: {
                legend: { position: 'bottom', labels: { font: { size: 11 } } },
                tooltip: { callbacks: { label: (c) => ` ${c.label}: ${c.raw} (${((c.raw/ns.total)*100).toFixed(1)}%)` } }
            }
        }
    });
}

// ---------------------------------------------------------------------------
// Director Dealing Signal
// ---------------------------------------------------------------------------
function renderDirectorSignal() {
    const el = document.getElementById('directorSignalBody');
    if (!el) return;
    const ds = dashData.director_signal || {};

    if (!ds.total_dealings) {
        el.innerHTML = '<div class="text-center text-muted py-3">No director dealings in this period</div>';
        return;
    }

    const signalColor = ds.signal === 'Net Buying' ? 'text-success' : (ds.signal === 'Net Selling' ? 'text-danger' : 'text-muted');
    const arrow = ds.signal === 'Net Buying' ? 'bi-arrow-up-circle-fill' : (ds.signal === 'Net Selling' ? 'bi-arrow-down-circle-fill' : 'bi-dash-circle');

    let html = `
        <div class="text-center mb-3">
            <i class="bi ${arrow} fs-1 ${signalColor}"></i>
            <h5 class="${signalColor} mb-0">${ds.signal}</h5>
            <small class="text-muted">${ds.buys} buys / ${ds.sells} sells / ${ds.neutral} neutral</small>
        </div>`;

    if (ds.recent_buys?.length) {
        html += `<div class="mb-2"><strong class="text-success">Recent Buys:</strong></div>`;
        html += ds.recent_buys.map(b => `<div class="ps-2 mb-1 border-start border-success border-2">${esc(b.company_name)}<br><span class="text-muted" style="font-size:0.75rem;">${esc(trunc(b.title, 60))}</span></div>`).join('');
    }
    if (ds.recent_sells?.length) {
        html += `<div class="mb-2 mt-2"><strong class="text-danger">Recent Sells:</strong></div>`;
        html += ds.recent_sells.map(s => `<div class="ps-2 mb-1 border-start border-danger border-2">${esc(s.company_name)}<br><span class="text-muted" style="font-size:0.75rem;">${esc(trunc(s.title, 60))}</span></div>`).join('');
    }

    el.innerHTML = html;
}

// ---------------------------------------------------------------------------
// Unusual Activity Alerts
// ---------------------------------------------------------------------------
function renderUnusualAlerts() {
    const el = document.getElementById('unusualAlertsBody');
    if (!el) return;
    const alerts = dashData.unusual_alerts || [];

    if (!alerts.length) {
        el.innerHTML = '<div class="text-center text-muted py-4"><i class="bi bi-check-circle fs-3"></i><p class="mt-2 mb-0">No unusual activity detected</p></div>';
        return;
    }

    el.innerHTML = `<div class="list-group list-group-flush">${
        alerts.map(a => `
            <div class="list-group-item px-3 py-2">
                <div class="d-flex justify-content-between align-items-center">
                    <strong class="small">${esc(trunc(a.company, 30))}</strong>
                    <span class="badge bg-warning text-dark">${a.ratio}x normal</span>
                </div>
                <small class="text-muted">${a.recent_7d} in last 7d vs avg ${a.avg_weekly}/week</small>
            </div>
        `).join('')
    }</div>`;
}

// ---------------------------------------------------------------------------
// Watchlist Pulse
// ---------------------------------------------------------------------------
function renderWatchlistPulse() {
    const el = document.getElementById('watchlistPulseBody');
    if (!el) return;
    const wp = dashData.watchlist_pulse || {};

    if (!wp.watchlist_count && !wp.watchlist_companies?.length) {
        el.innerHTML = `<div class="text-center text-muted py-3"><i class="bi bi-star fs-3"></i><p class="mt-1 mb-0 small">Add companies to your watchlist</p></div>`;
        return;
    }

    let html = `
        <div class="row text-center mb-2 g-1">
            <div class="col-6">
                <div class="border rounded py-2">
                    <div class="fw-bold fs-5">${wp.watchlist_count}</div>
                    <div class="text-muted" style="font-size:0.7rem;">Watchlist SENS</div>
                </div>
            </div>
            <div class="col-6">
                <div class="border rounded py-2">
                    <div class="fw-bold fs-5">${wp.watchlist_pct || 0}%</div>
                    <div class="text-muted" style="font-size:0.7rem;">of Market</div>
                </div>
            </div>
        </div>`;

    if (wp.watchlist_companies?.length) {
        html += `<div class="list-group list-group-flush">`;
        wp.watchlist_companies.slice(0, 6).forEach(c => {
            html += `<div class="list-group-item d-flex justify-content-between align-items-center px-0 py-1">
                <span class="small">${esc(trunc(c.company, 25))}</span>
                <span><span class="badge bg-primary rounded-pill">${c.total}</span> <span class="badge bg-success rounded-pill">${c.strategic}</span></span>
            </div>`;
        });
        html += `</div><div class="text-muted mt-1" style="font-size:0.65rem;"><span class="badge bg-primary" style="font-size:0.6rem;">n</span> total &nbsp;<span class="badge bg-success" style="font-size:0.6rem;">n</span> strategic</div>`;
    }

    el.innerHTML = html;
}

// ---------------------------------------------------------------------------
// Sentiment Overview
// ---------------------------------------------------------------------------
function renderSentiment() {
    const sent = dashData.sentiment || {};
    if (!sent.total_analysed) {
        const el = document.getElementById('sentimentDetail');
        if (el) el.innerHTML = '<span class="text-muted">No AI summaries available yet</span>';
        return;
    }

    if (chartSentiment) chartSentiment.destroy();
    const ctx = document.getElementById('chartSentiment')?.getContext('2d');
    if (ctx) {
        chartSentiment = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['Positive', 'Neutral', 'Negative'],
                datasets: [{ data: [sent.positive, sent.neutral, sent.negative], backgroundColor: ['#198754', '#6c757d', '#dc3545'], borderWidth: 2, borderColor: '#fff' }]
            },
            options: {
                responsive: true, maintainAspectRatio: false, cutout: '60%',
                plugins: { legend: { display: false } }
            }
        });
    }

    const el = document.getElementById('sentimentDetail');
    if (el) {
        el.innerHTML = `
            <div class="d-flex justify-content-around text-center">
                <div><span class="text-success fw-bold">${sent.positive}</span><br><span class="text-muted" style="font-size:0.7rem;">Positive</span></div>
                <div><span class="text-muted fw-bold">${sent.neutral}</span><br><span class="text-muted" style="font-size:0.7rem;">Neutral</span></div>
                <div><span class="text-danger fw-bold">${sent.negative}</span><br><span class="text-muted" style="font-size:0.7rem;">Negative</span></div>
            </div>
            <div class="text-center mt-1 text-muted" style="font-size:0.7rem;">${sent.total_analysed} summaries analysed</div>`;
    }
}

// ---------------------------------------------------------------------------
// Strategic Highlights Table
// ---------------------------------------------------------------------------
function renderHighlights() {
    const tbody = document.getElementById('highlightsBody');
    if (!tbody) return;
    const data = dashData.strategic_highlights || [];

    if (!data.length) {
        tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted py-4"><i class="bi bi-inbox fs-3"></i><p class="mt-2 mb-0">No strategic announcements</p></td></tr>';
        return;
    }

    const badge = (cat) => {
        const m = { 'Trading Statements & Updates':'bg-danger', 'Financial Results':'bg-primary', 'Acquisitions & Disposals':'bg-warning text-dark', 'Dealings by Directors':'bg-info text-dark', 'Board & Management Changes':'bg-secondary', 'Cautionary Announcements':'bg-danger', 'Dividends & Distributions':'bg-success' };
        return m[cat] || 'bg-dark';
    };

    // Store tooltip text in a JS array to avoid attribute-escaping issues.
    // Fall back to the full title if no AI summary is available.
    _tooltipData.highlights = data.map(item =>
        item.ai_summary ? `AI Summary: ${item.ai_summary}` : item.title || ''
    );

    tbody.innerHTML = data.map((item, idx) => {
        const dt = item.date_published ? new Date(item.date_published).toLocaleDateString('en-ZA', { day:'2-digit', month:'short', hour:'2-digit', minute:'2-digit' }) : '—';
        return `<tr class="tooltip-row" data-tooltip-group="highlights" data-tooltip-idx="${idx}"><td><strong class="small">${esc(item.company_name)}</strong></td><td class="small">${esc(item.title)}</td><td><span class="badge ${badge(item.category)} small">${esc(item.category)}</span></td><td class="small text-muted text-nowrap">${dt}</td></tr>`;
    }).join('');

    attachRowTooltips();
}

// ---------------------------------------------------------------------------
// PDF Summary Cards
// ---------------------------------------------------------------------------
function renderSummaryCards() {
    const cards = dashData.watchlist_summaries || [];
    const row = document.getElementById('summaryCardsRow');
    const body = document.getElementById('summaryCardsBody');
    if (!row || !body) return;

    if (!cards.length) { row.style.display = 'none'; return; }
    row.style.display = '';

    body.innerHTML = `<div class="row g-3">${cards.map((c, i) => {
        const dt = c.date_published ? new Date(c.date_published).toLocaleDateString('en-ZA', { day:'2-digit', month:'short', year:'numeric' }) : '';
        const urgBadge = c.is_urgent ? '<span class="badge bg-danger ms-1">Urgent</span>' : '';
        return `
        <div class="col-md-6 col-xl-4">
            <div class="card h-100 ${c.is_urgent ? 'border-danger' : ''}">
                <div class="card-header py-2 d-flex justify-content-between align-items-center">
                    <strong class="small">${esc(c.company_name)} <small class="text-muted">(${esc(c.jse_code)})</small></strong>
                    ${urgBadge}
                </div>
                <div class="card-body py-2">
                    <p class="small text-muted mb-1">${esc(c.title)}</p>
                    <p class="small mb-0">${esc(c.ai_summary)}</p>
                </div>
                <div class="card-footer py-1 text-muted" style="font-size:0.7rem;">${esc(c.sens_number)} &mdash; ${dt}</div>
            </div>
        </div>`;
    }).join('')}</div>`;
}

// ---------------------------------------------------------------------------
// Upcoming Events
// ---------------------------------------------------------------------------
function renderEvents() {
    const events = dashData.upcoming_events || [];
    const row = document.getElementById('eventsRow');
    const body = document.getElementById('eventsBody');
    if (!row || !body) return;

    if (!events.length && (!dashData.company_heatmap || !dashData.company_heatmap.companies?.length)) {
        row.style.display = 'none';
        return;
    }
    row.style.display = '';

    if (!events.length) {
        body.innerHTML = '<tr><td colspan="3" class="text-center text-muted py-3">No recent events detected</td></tr>';
    } else {
        const typeBadge = (t) => {
            const m = { 'AGM / General Meeting':'bg-primary', 'Results Announcement':'bg-success', 'Cautionary Period':'bg-danger', 'M&A Event':'bg-warning text-dark', 'Trading Statement':'bg-info text-dark' };
            return m[t] || 'bg-secondary';
        };

        // Store tooltip data and pdf urls for events
        _tooltipData.events = events.map(e => {
            let tip = e.ai_summary ? `AI Summary: ${e.ai_summary}` : (e.title || '');
            if (e.pdf_url) tip += tip ? '\n\nDouble-click to open PDF' : 'Double-click to open PDF';
            return tip;
        });
        _tooltipData.eventPdfUrls = events.map(e => e.pdf_url || '');

        body.innerHTML = events.map((e, idx) => {
            const dt = e.date ? new Date(e.date).toLocaleDateString('en-ZA', { day:'2-digit', month:'short' }) : '—';
            const hasPdf = e.pdf_url ? ' style="cursor:pointer;"' : '';
            return `<tr class="tooltip-row" data-tooltip-group="events" data-tooltip-idx="${idx}"${hasPdf}><td class="small">${esc(trunc(e.company, 30))}</td><td><span class="badge ${typeBadge(e.event_type)} small">${esc(e.event_type)}</span></td><td class="small text-muted text-nowrap">${dt}</td></tr>`;
        }).join('');

        // Double-click to open PDF
        body.querySelectorAll('tr[data-tooltip-group="events"]').forEach(row => {
            row.addEventListener('dblclick', () => {
                const idx = parseInt(row.dataset.tooltipIdx, 10);
                const url = _tooltipData.eventPdfUrls[idx];
                if (url) window.open(url, '_blank');
            });
        });

        attachRowTooltips();
    }
}

// ---------------------------------------------------------------------------
// Company-Category Heatmap
// ---------------------------------------------------------------------------
function renderHeatmap() {
    const hm = dashData.company_heatmap;
    if (!hm || !hm.companies?.length) {
        document.getElementById('heatmapBody').innerHTML = '<tr><td colspan="2" class="text-center text-muted py-3">No data</td></tr>';
        return;
    }

    document.getElementById('heatmapHead').innerHTML = `
        <tr class="table-light">
            <th class="small" style="min-width:160px;">Company</th>
            ${hm.categories.map(c => `<th class="small text-center" style="writing-mode:vertical-lr;transform:rotate(180deg);max-width:36px;font-size:0.65rem;">${esc(c)}</th>`).join('')}
        </tr>`;

    const maxVal = Math.max(...hm.matrix.flat(), 1);
    document.getElementById('heatmapBody').innerHTML = hm.companies.map((co, ri) => {
        const cells = hm.matrix[ri].map(v => {
            const int = v / maxVal;
            const bg = v === 0 ? '#f8f9fa' : `rgba(13,110,253,${0.15+int*0.7})`;
            const tc = int > 0.5 ? '#fff' : '#333';
            return `<td class="text-center small" style="background:${bg};color:${tc};font-weight:${v?600:400};">${v||''}</td>`;
        }).join('');
        return `<tr><td class="small fw-bold">${esc(trunc(co, 30))}</td>${cells}</tr>`;
    }).join('');
}

// ---------------------------------------------------------------------------
// Unified Row Tooltip System
// ---------------------------------------------------------------------------
// Tooltip text is stored in this JS object keyed by group name + index,
// avoiding HTML-attribute escaping issues with quotes etc.
const _tooltipData = { highlights: [], events: [], eventPdfUrls: [] };
let _rowTooltipEl = null;

function _ensureTooltipEl() {
    if (!_rowTooltipEl) {
        _rowTooltipEl = document.createElement('div');
        _rowTooltipEl.className = 'highlight-tooltip';
        document.body.appendChild(_rowTooltipEl);
    }
    return _rowTooltipEl;
}

function attachRowTooltips() {
    const tip = _ensureTooltipEl();
    document.querySelectorAll('.tooltip-row').forEach(row => {
        // Avoid attaching duplicate listeners on re-render
        if (row._tipBound) return;
        row._tipBound = true;

        row.addEventListener('mouseenter', (e) => {
            const group = row.dataset.tooltipGroup;
            const idx = parseInt(row.dataset.tooltipIdx, 10);
            const text = (_tooltipData[group] || [])[idx];
            if (!text) return;
            tip.textContent = text;
            tip.style.display = 'block';
            _positionTooltip(e);
        });
        row.addEventListener('mousemove', _positionTooltip);
        row.addEventListener('mouseleave', () => {
            tip.style.display = 'none';
        });
    });
}

function _positionTooltip(e) {
    if (!_rowTooltipEl) return;
    const pad = 12;
    const tipW = _rowTooltipEl.offsetWidth;
    const tipH = _rowTooltipEl.offsetHeight;
    let x = e.clientX + pad;
    let y = e.clientY + pad;
    if (x + tipW > window.innerWidth - pad) x = e.clientX - tipW - pad;
    if (y + tipH > window.innerHeight - pad) y = e.clientY - tipH - pad;
    _rowTooltipEl.style.left = x + 'px';
    _rowTooltipEl.style.top = y + 'px';
}

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------
function trunc(t, n) { return !t ? '' : (t.length > n ? t.substring(0, n-1) + '\u2026' : t); }
function fmtDate(s, b) { if (!s) return ''; if (b==='month') return s; const d = new Date(s+'T00:00:00'); return d.toLocaleDateString('en-ZA',{day:'2-digit',month:'short'}); }
function esc(t) { if (!t) return ''; const d = document.createElement('div'); d.textContent = t; return d.innerHTML; }
