let currentMarket = 'moneyway_1x2';
let matches = [];
let filteredMatches = [];
let chart = null;
let selectedMatch = null;
let selectedChartMarket = 'moneyway_1x2';
let autoScrapeRunning = false;
let currentSort = 'date_desc';

document.addEventListener('DOMContentLoaded', () => {
    loadMatches();
    setupTabs();
    setupSearch();
    setupChartTabs();
    checkStatus();
    window.statusInterval = window.setInterval(checkStatus, 3000);
});

function setupTabs() {
    document.querySelectorAll('.market-tabs .tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.market-tabs .tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            currentMarket = tab.dataset.market;
            loadMatches();
        });
    });
}

function setupChartTabs() {
    document.querySelectorAll('.chart-market-tabs .chart-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.chart-market-tabs .chart-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            selectedChartMarket = tab.dataset.market;
            if (selectedMatch) {
                loadChart(selectedMatch.home_team, selectedMatch.away_team, selectedChartMarket);
            }
        });
    });
}

function setupSearch() {
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            const query = e.target.value.toLowerCase();
            filterMatches(query);
        });
    }
}

async function loadMatches() {
    const tbody = document.getElementById('matchesTableBody');
    tbody.innerHTML = `
        <tr class="loading-row">
            <td colspan="7">
                <div class="loading-spinner"></div>
                Loading matches...
            </td>
        </tr>
    `;
    
    updateTableHeaders();
    
    try {
        const response = await fetch(`/api/matches?market=${currentMarket}`);
        matches = await response.json();
        filteredMatches = applySorting(matches);
        renderMatches(filteredMatches);
    } catch (error) {
        console.error('Error loading matches:', error);
        tbody.innerHTML = `
            <tr class="loading-row">
                <td colspan="7">
                    <div class="empty-state">
                        <p>No data available. Click "Scrape Now" to fetch matches.</p>
                    </div>
                </td>
            </tr>
        `;
    }
}

function updateTableHeaders() {
    const thead = document.querySelector('.matches-table thead tr');
    if (!thead) return;
    
    if (currentMarket.includes('1x2')) {
        thead.innerHTML = `
            <th class="col-date">DATE</th>
            <th class="col-league">LEAGUE</th>
            <th class="col-match">MATCH</th>
            <th class="col-selection">1</th>
            <th class="col-selection">X</th>
            <th class="col-selection">2</th>
            <th class="col-volume">VOLUME</th>
        `;
    } else if (currentMarket.includes('ou25')) {
        thead.innerHTML = `
            <th class="col-date">DATE</th>
            <th class="col-league">LEAGUE</th>
            <th class="col-match">MATCH</th>
            <th class="col-selection">UNDER</th>
            <th class="col-selection">OVER</th>
            <th class="col-volume">VOLUME</th>
        `;
    } else if (currentMarket.includes('btts')) {
        thead.innerHTML = `
            <th class="col-date">DATE</th>
            <th class="col-league">LEAGUE</th>
            <th class="col-match">MATCH</th>
            <th class="col-selection">YES</th>
            <th class="col-selection">NO</th>
            <th class="col-volume">VOLUME</th>
        `;
    }
}

function getPctClass(pctValue) {
    const num = parseFloat(String(pctValue).replace(/[^0-9.]/g, ''));
    if (isNaN(num)) return 'pct-normal';
    if (num >= 90) return 'pct-red';
    if (num >= 70) return 'pct-orange';
    if (num >= 50) return 'pct-yellow';
    return 'pct-normal';
}

function renderMatches(data) {
    const tbody = document.getElementById('matchesTableBody');
    const countEl = document.getElementById('matchCount');
    
    if (countEl) {
        countEl.textContent = data.length;
    }
    
    if (data.length === 0) {
        const colspan = currentMarket.includes('1x2') ? 7 : 6;
        tbody.innerHTML = `
            <tr class="loading-row">
                <td colspan="${colspan}">
                    <div class="empty-state">
                        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                            <circle cx="12" cy="12" r="10"/>
                            <path d="M12 6v6l4 2"/>
                        </svg>
                        <p>No matches found. Click "Scrape Now" to fetch data.</p>
                    </div>
                </td>
            </tr>
        `;
        return;
    }
    
    tbody.innerHTML = data.map((match, idx) => {
        const d = match.details || {};
        const isSelected = selectedMatch && 
            selectedMatch.home_team === match.home_team && 
            selectedMatch.away_team === match.away_team;
        
        if (currentMarket.includes('1x2')) {
            return `
                <tr data-index="${idx}" class="${isSelected ? 'selected' : ''}" onclick="selectMatch(${idx})">
                    <td class="match-date">${match.date || '-'}</td>
                    <td class="match-league" title="${match.league || ''}">${match.league || '-'}</td>
                    <td class="match-teams">${match.home_team}<span class="vs">-</span>${match.away_team}</td>
                    <td class="selection-cell">
                        <div class="selection-odds">${formatOdds(d.Odds1 || d['1'] || match.odds?.['1'])}</div>
                        ${d.Amt1 ? `<div class="selection-money">${d.Amt1}</div>` : ''}
                        ${d.Pct1 ? `<div class="selection-pct ${getPctClass(d.Pct1)}">${d.Pct1}%</div>` : ''}
                    </td>
                    <td class="selection-cell">
                        <div class="selection-odds">${formatOdds(d.OddsX || d['X'] || match.odds?.['X'])}</div>
                        ${d.AmtX ? `<div class="selection-money">${d.AmtX}</div>` : ''}
                        ${d.PctX ? `<div class="selection-pct ${getPctClass(d.PctX)}">${d.PctX}%</div>` : ''}
                    </td>
                    <td class="selection-cell">
                        <div class="selection-odds">${formatOdds(d.Odds2 || d['2'] || match.odds?.['2'])}</div>
                        ${d.Amt2 ? `<div class="selection-money">${d.Amt2}</div>` : ''}
                        ${d.Pct2 ? `<div class="selection-pct ${getPctClass(d.Pct2)}">${d.Pct2}%</div>` : ''}
                    </td>
                    <td class="volume-cell">${d.Volume || '-'}</td>
                </tr>
            `;
        } else if (currentMarket.includes('ou25')) {
            return `
                <tr data-index="${idx}" class="${isSelected ? 'selected' : ''}" onclick="selectMatch(${idx})">
                    <td class="match-date">${match.date || '-'}</td>
                    <td class="match-league" title="${match.league || ''}">${match.league || '-'}</td>
                    <td class="match-teams">${match.home_team}<span class="vs">-</span>${match.away_team}</td>
                    <td class="selection-cell">
                        <div class="selection-odds">${formatOdds(d.Under || match.odds?.Under)}</div>
                        ${d.AmtUnder ? `<div class="selection-money">${d.AmtUnder}</div>` : ''}
                        ${d.PctUnder ? `<div class="selection-pct ${getPctClass(d.PctUnder)}">${d.PctUnder}%</div>` : ''}
                    </td>
                    <td class="selection-cell">
                        <div class="selection-odds">${formatOdds(d.Over || match.odds?.Over)}</div>
                        ${d.AmtOver ? `<div class="selection-money">${d.AmtOver}</div>` : ''}
                        ${d.PctOver ? `<div class="selection-pct ${getPctClass(d.PctOver)}">${d.PctOver}%</div>` : ''}
                    </td>
                    <td class="volume-cell">${d.Volume || '-'}</td>
                </tr>
            `;
        } else {
            return `
                <tr data-index="${idx}" class="${isSelected ? 'selected' : ''}" onclick="selectMatch(${idx})">
                    <td class="match-date">${match.date || '-'}</td>
                    <td class="match-league" title="${match.league || ''}">${match.league || '-'}</td>
                    <td class="match-teams">${match.home_team}<span class="vs">-</span>${match.away_team}</td>
                    <td class="selection-cell">
                        <div class="selection-odds">${formatOdds(d.Yes || match.odds?.Yes)}</div>
                        ${d.AmtYes ? `<div class="selection-money">${d.AmtYes}</div>` : ''}
                        ${d.PctYes ? `<div class="selection-pct ${getPctClass(d.PctYes)}">${d.PctYes}%</div>` : ''}
                    </td>
                    <td class="selection-cell">
                        <div class="selection-odds">${formatOdds(d.No || match.odds?.No)}</div>
                        ${d.AmtNo ? `<div class="selection-money">${d.AmtNo}</div>` : ''}
                        ${d.PctNo ? `<div class="selection-pct ${getPctClass(d.PctNo)}">${d.PctNo}%</div>` : ''}
                    </td>
                    <td class="volume-cell">${d.Volume || '-'}</td>
                </tr>
            `;
        }
    }).join('');
}

function formatOdds(value) {
    if (!value || value === '-') return '-';
    const str = String(value);
    const firstLine = str.split('\n')[0];
    const num = parseFloat(firstLine);
    return isNaN(num) ? firstLine : num.toFixed(2);
}

function filterMatches(query) {
    let filtered = [...matches];
    
    if (query) {
        filtered = filtered.filter(m => 
            m.home_team.toLowerCase().includes(query) ||
            m.away_team.toLowerCase().includes(query) ||
            (m.league && m.league.toLowerCase().includes(query))
        );
    }
    
    filtered = applySorting(filtered);
    filteredMatches = filtered;
    renderMatches(filtered);
}

function applySorting(data) {
    const sortType = document.getElementById('sortSelect')?.value || currentSort;
    currentSort = sortType;
    
    return [...data].sort((a, b) => {
        if (sortType === 'date_asc') {
            return parseDate(a.date) - parseDate(b.date);
        } else if (sortType === 'date_desc') {
            return parseDate(b.date) - parseDate(a.date);
        } else if (sortType === 'volume_desc') {
            return parseVolume(b) - parseVolume(a);
        } else if (sortType === 'volume_asc') {
            return parseVolume(a) - parseVolume(b);
        }
        return 0;
    });
}

function parseDate(dateStr) {
    if (!dateStr || dateStr === '-') return 0;
    const parts = dateStr.match(/(\d{2})\.(\d{2})\.(\d{4})\s+(\d{2}):(\d{2})/);
    if (parts) {
        return new Date(parts[3], parts[2] - 1, parts[1], parts[4], parts[5]).getTime();
    }
    return new Date(dateStr).getTime() || 0;
}

function parseVolume(match) {
    const d = match.details || {};
    let vol = d.Volume || '0';
    if (typeof vol === 'string') {
        vol = vol.replace(/[£€$,\s]/g, '').replace(/k/i, '000').replace(/m/i, '000000');
    }
    return parseFloat(vol) || 0;
}

function sortMatches() {
    const searchInput = document.getElementById('searchInput');
    const query = searchInput?.value?.toLowerCase() || '';
    filterMatches(query);
}

function selectMatch(index) {
    const dataSource = filteredMatches.length > 0 ? filteredMatches : matches;
    if (index >= 0 && index < dataSource.length) {
        selectedMatch = dataSource[index];
        
        document.querySelectorAll('.matches-table tbody tr').forEach(tr => {
            tr.classList.remove('selected');
        });
        document.querySelector(`tr[data-index="${index}"]`)?.classList.add('selected');
        
        document.getElementById('chartTitle').textContent = 
            `${selectedMatch.home_team} vs ${selectedMatch.away_team}`;
        document.getElementById('chartSubtitle').textContent = 
            selectedMatch.league || 'Odds Movement Chart';
        
        document.getElementById('chartMarketTabs').style.display = 'flex';
        document.getElementById('chartEmpty').classList.add('hidden');
        document.querySelector('.chart-container').classList.add('active');
        
        loadChart(selectedMatch.home_team, selectedMatch.away_team, selectedChartMarket);
    }
}

function roundTo10Min(timestamp) {
    const date = new Date(timestamp);
    const minutes = date.getMinutes();
    const roundedMinutes = Math.floor(minutes / 10) * 10;
    date.setMinutes(roundedMinutes, 0, 0);
    return date;
}

function formatTimeLabel(date) {
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    return `${hours}:${minutes}`;
}

async function loadChart(home, away, market) {
    try {
        const response = await fetch(
            `/api/match/history?home=${encodeURIComponent(home)}&away=${encodeURIComponent(away)}&market=${market}`
        );
        const data = await response.json();
        
        if (chart) {
            chart.destroy();
        }
        
        const ctx = document.getElementById('oddsChart').getContext('2d');
        const isMoneyway = market.startsWith('moneyway');
        
        if (!data.history || data.history.length === 0) {
            chart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: ['No data'],
                    datasets: [{
                        label: 'No historical data available',
                        data: [0],
                        borderColor: '#536471'
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } }
                }
            });
            return;
        }
        
        const timeBlocks = {};
        data.history.forEach(h => {
            const ts = h.ScrapedAt || '';
            let date;
            try {
                date = new Date(ts);
            } catch {
                date = new Date();
            }
            const rounded = roundTo10Min(date);
            const key = rounded.getTime();
            timeBlocks[key] = h;
        });
        
        const sortedKeys = Object.keys(timeBlocks).map(Number).sort((a, b) => a - b);
        const labels = sortedKeys.map(k => formatTimeLabel(new Date(k)));
        const historyData = sortedKeys.map(k => timeBlocks[k]);
        
        let datasets = [];
        const colors = {
            '1': '#4ade80',
            'X': '#fbbf24', 
            '2': '#60a5fa',
            'Under': '#60a5fa',
            'Over': '#4ade80',
            'Yes': '#4ade80',
            'No': '#f87171'
        };
        
        if (market.includes('1x2')) {
            if (isMoneyway) {
                ['Pct1', 'PctX', 'Pct2'].forEach((key, idx) => {
                    const label = ['1%', 'X%', '2%'][idx];
                    const color = [colors['1'], colors['X'], colors['2']][idx];
                    datasets.push({
                        label: label,
                        data: historyData.map(h => {
                            const val = h[key];
                            return val ? parseFloat(String(val).replace(/[^0-9.]/g, '')) : null;
                        }),
                        borderColor: color,
                        backgroundColor: color,
                        tension: 0.3,
                        fill: false,
                        pointRadius: 5,
                        pointHoverRadius: 8,
                        pointBackgroundColor: color,
                        pointBorderColor: color,
                        pointStyle: 'circle'
                    });
                });
            } else {
                ['Odds1', 'OddsX', 'Odds2'].forEach((key, idx) => {
                    const altKey = ['1', 'X', '2'][idx];
                    const label = ['1', 'X', '2'][idx];
                    const color = [colors['1'], colors['X'], colors['2']][idx];
                    datasets.push({
                        label: label,
                        data: historyData.map(h => {
                            const val = h[key] || h[altKey];
                            if (!val) return null;
                            const num = parseFloat(String(val).split('\n')[0]);
                            return isNaN(num) ? null : num;
                        }),
                        borderColor: color,
                        backgroundColor: color,
                        tension: 0.3,
                        fill: false,
                        pointRadius: 5,
                        pointHoverRadius: 8,
                        pointBackgroundColor: color,
                        pointBorderColor: color,
                        pointStyle: 'circle'
                    });
                });
            }
        } else if (market.includes('ou25')) {
            if (isMoneyway) {
                ['PctUnder', 'PctOver'].forEach((key, idx) => {
                    const label = ['Under%', 'Over%'][idx];
                    const color = [colors['Under'], colors['Over']][idx];
                    datasets.push({
                        label: label,
                        data: historyData.map(h => {
                            const val = h[key];
                            return val ? parseFloat(String(val).replace(/[^0-9.]/g, '')) : null;
                        }),
                        borderColor: color,
                        backgroundColor: color,
                        tension: 0.3,
                        fill: false,
                        pointRadius: 5,
                        pointHoverRadius: 8,
                        pointBackgroundColor: color,
                        pointBorderColor: color,
                        pointStyle: 'circle'
                    });
                });
            } else {
                ['Under', 'Over'].forEach((key, idx) => {
                    const label = key;
                    const color = colors[key];
                    datasets.push({
                        label: label,
                        data: historyData.map(h => {
                            const val = h[key];
                            if (!val) return null;
                            const num = parseFloat(String(val).split('\n')[0]);
                            return isNaN(num) ? null : num;
                        }),
                        borderColor: color,
                        backgroundColor: color,
                        tension: 0.3,
                        fill: false,
                        pointRadius: 5,
                        pointHoverRadius: 8,
                        pointBackgroundColor: color,
                        pointBorderColor: color,
                        pointStyle: 'circle'
                    });
                });
            }
        } else if (market.includes('btts')) {
            if (isMoneyway) {
                ['PctYes', 'PctNo'].forEach((key, idx) => {
                    const label = ['Yes%', 'No%'][idx];
                    const color = [colors['Yes'], colors['No']][idx];
                    datasets.push({
                        label: label,
                        data: historyData.map(h => {
                            const val = h[key];
                            return val ? parseFloat(String(val).replace(/[^0-9.]/g, '')) : null;
                        }),
                        borderColor: color,
                        backgroundColor: color,
                        tension: 0.3,
                        fill: false,
                        pointRadius: 5,
                        pointHoverRadius: 8,
                        pointBackgroundColor: color,
                        pointBorderColor: color,
                        pointStyle: 'circle'
                    });
                });
            } else {
                ['Yes', 'No'].forEach((key, idx) => {
                    const label = key;
                    const color = colors[key];
                    datasets.push({
                        label: label,
                        data: historyData.map(h => {
                            const val = h[key];
                            if (!val) return null;
                            const num = parseFloat(String(val).split('\n')[0]);
                            return isNaN(num) ? null : num;
                        }),
                        borderColor: color,
                        backgroundColor: color,
                        tension: 0.3,
                        fill: false,
                        pointRadius: 5,
                        pointHoverRadius: 8,
                        pointBackgroundColor: color,
                        pointBorderColor: color,
                        pointStyle: 'circle'
                    });
                });
            }
        }
        
        const tooltipData = historyData;
        
        chart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: datasets
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: 'index',
                    intersect: false
                },
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            color: '#e7e9ea',
                            usePointStyle: true,
                            pointStyle: 'circle',
                            padding: 15,
                            font: { size: 12, weight: 'bold' },
                            boxWidth: 12,
                            boxHeight: 12
                        }
                    },
                    tooltip: {
                        backgroundColor: '#1f2937',
                        titleColor: '#fff',
                        titleFont: { size: 13, weight: 'bold' },
                        bodyColor: '#e7e9ea',
                        bodyFont: { size: 12 },
                        borderColor: '#374151',
                        borderWidth: 1,
                        padding: 12,
                        displayColors: true,
                        boxWidth: 12,
                        boxHeight: 12,
                        boxPadding: 4,
                        callbacks: {
                            label: function(context) {
                                const idx = context.dataIndex;
                                const h = tooltipData[idx];
                                if (!h) return context.dataset.label + ': ' + context.formattedValue;
                                
                                const datasetLabel = context.dataset.label;
                                let lines = [];
                                
                                if (market.includes('1x2')) {
                                    if (datasetLabel.includes('1')) {
                                        const odds = h.Odds1 || h['1'] || '-';
                                        const amt = h.Amt1 || '';
                                        const pct = h.Pct1 || '';
                                        lines.push(`1 • ${formatOdds(odds)}`);
                                        if (amt) lines.push(`${amt}  —  ${pct}%`);
                                    } else if (datasetLabel.includes('X')) {
                                        const odds = h.OddsX || h['X'] || '-';
                                        const amt = h.AmtX || '';
                                        const pct = h.PctX || '';
                                        lines.push(`X • ${formatOdds(odds)}`);
                                        if (amt) lines.push(`${amt}  —  ${pct}%`);
                                    } else if (datasetLabel.includes('2')) {
                                        const odds = h.Odds2 || h['2'] || '-';
                                        const amt = h.Amt2 || '';
                                        const pct = h.Pct2 || '';
                                        lines.push(`2 • ${formatOdds(odds)}`);
                                        if (amt) lines.push(`${amt}  —  ${pct}%`);
                                    }
                                } else if (market.includes('ou25')) {
                                    if (datasetLabel.toLowerCase().includes('under')) {
                                        const odds = h.Under || '-';
                                        const amt = h.AmtUnder || '';
                                        const pct = h.PctUnder || '';
                                        lines.push(`Under • ${formatOdds(odds)}`);
                                        if (amt) lines.push(`${amt}  —  ${pct}%`);
                                    } else {
                                        const odds = h.Over || '-';
                                        const amt = h.AmtOver || '';
                                        const pct = h.PctOver || '';
                                        lines.push(`Over • ${formatOdds(odds)}`);
                                        if (amt) lines.push(`${amt}  —  ${pct}%`);
                                    }
                                } else if (market.includes('btts')) {
                                    if (datasetLabel.toLowerCase().includes('yes')) {
                                        const odds = h.Yes || '-';
                                        const amt = h.AmtYes || '';
                                        const pct = h.PctYes || '';
                                        lines.push(`Yes • ${formatOdds(odds)}`);
                                        if (amt) lines.push(`${amt}  —  ${pct}%`);
                                    } else {
                                        const odds = h.No || '-';
                                        const amt = h.AmtNo || '';
                                        const pct = h.PctNo || '';
                                        lines.push(`No • ${formatOdds(odds)}`);
                                        if (amt) lines.push(`${amt}  —  ${pct}%`);
                                    }
                                }
                                
                                return lines.length > 0 ? lines : [context.dataset.label + ': ' + context.formattedValue];
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: {
                            color: '#2f3336',
                            drawBorder: false
                        },
                        ticks: {
                            color: '#8899a6',
                            font: { size: 11 }
                        }
                    },
                    y: {
                        grid: {
                            color: '#2f3336',
                            drawBorder: false
                        },
                        ticks: {
                            color: '#8899a6',
                            font: { size: 11 }
                        }
                    }
                },
                elements: {
                    point: {
                        radius: 5,
                        hoverRadius: 8,
                        borderWidth: 0
                    },
                    line: {
                        borderWidth: 3
                    }
                }
            }
        });
    } catch (error) {
        console.error('Error loading chart:', error);
    }
}

async function triggerScrape() {
    const btn = document.getElementById('scrapeBtn');
    const originalText = btn.innerHTML;
    
    btn.disabled = true;
    btn.innerHTML = `
        <div class="loading-spinner" style="width:14px;height:14px;margin:0;border-width:2px;"></div>
        Scraping...
    `;
    
    try {
        const response = await fetch('/api/scrape', { method: 'POST' });
        const result = await response.json();
        
        if (result.status === 'ok') {
            setTimeout(() => {
                loadMatches();
            }, 3000);
        }
    } catch (error) {
        console.error('Scrape error:', error);
    }
    
    setTimeout(() => {
        btn.disabled = false;
        btn.innerHTML = originalText;
        checkStatus();
    }, 5000);
}

async function checkStatus() {
    try {
        const response = await fetch('/api/status');
        const status = await response.json();
        
        autoScrapeRunning = status.auto_running;
        
        const indicator = document.getElementById('statusIndicator');
        if (indicator) {
            const dot = indicator.querySelector('.status-dot');
            const text = indicator.querySelector('.status-text');
            
            if (status.running) {
                dot.classList.add('running');
                text.textContent = 'Scraping...';
            } else if (status.auto_running) {
                dot.classList.add('running');
                if (status.next_scrape_time) {
                    const next = new Date(status.next_scrape_time);
                    const now = new Date();
                    const diffSec = Math.max(0, Math.floor((next - now) / 1000));
                    const min = Math.floor(diffSec / 60);
                    const sec = diffSec % 60;
                    text.textContent = `Next: ${min}:${sec.toString().padStart(2, '0')}`;
                } else {
                    text.textContent = 'Auto Active';
                }
            } else {
                dot.classList.remove('running');
                text.textContent = 'Ready';
            }
        }
        
        const autoBtn = document.getElementById('autoBtn');
        const autoBtnText = document.getElementById('autoBtnText');
        if (autoBtn && autoBtnText) {
            if (status.auto_running) {
                autoBtn.classList.add('active');
                autoBtnText.textContent = 'Stop';
            } else {
                autoBtn.classList.remove('active');
                autoBtnText.textContent = 'Auto';
            }
        }
        
        const intervalSelect = document.getElementById('intervalSelect');
        if (intervalSelect && status.interval_minutes) {
            intervalSelect.value = status.interval_minutes.toString();
        }
        
    } catch (error) {
        console.error('Status check error:', error);
    }
}

async function toggleAutoScrape() {
    const autoBtn = document.getElementById('autoBtn');
    const intervalSelect = document.getElementById('intervalSelect');
    const interval = parseInt(intervalSelect.value) || 5;
    
    autoBtn.disabled = true;
    
    try {
        const action = autoScrapeRunning ? 'stop' : 'start';
        const response = await fetch('/api/scrape/auto', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action, interval })
        });
        const result = await response.json();
        
        autoScrapeRunning = result.auto_running;
        
        if (action === 'start' && result.auto_running) {
            setTimeout(() => loadMatches(), 3000);
        }
        
        checkStatus();
    } catch (error) {
        console.error('Auto scrape toggle error:', error);
    }
    
    autoBtn.disabled = false;
}

async function updateInterval() {
    const intervalSelect = document.getElementById('intervalSelect');
    const newInterval = parseInt(intervalSelect.value) || 5;
    
    try {
        const response = await fetch('/api/interval', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ interval: newInterval })
        });
        
        if (!response.ok) {
            console.error('Interval API error:', response.status);
            return;
        }
        
        const result = await response.json();
        console.log('Interval updated:', result);
        
        checkStatus();
    } catch (error) {
        console.error('Update interval error:', error);
    }
}
