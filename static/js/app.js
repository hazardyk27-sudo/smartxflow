let currentMarket = 'moneyway_1x2';
let matches = [];
let chart = null;
let selectedMatch = null;
let selectedChartMarket = 'moneyway_1x2';

document.addEventListener('DOMContentLoaded', () => {
    loadMatches();
    setupTabs();
    setupSearch();
    setupChartTabs();
    checkStatus();
    setInterval(checkStatus, 5000);
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
        renderMatches(matches);
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
                        ${d.Pct1 ? `<div class="selection-pct">${d.Pct1}%</div>` : ''}
                    </td>
                    <td class="selection-cell">
                        <div class="selection-odds">${formatOdds(d.OddsX || d['X'] || match.odds?.['X'])}</div>
                        ${d.AmtX ? `<div class="selection-money">${d.AmtX}</div>` : ''}
                        ${d.PctX ? `<div class="selection-pct">${d.PctX}%</div>` : ''}
                    </td>
                    <td class="selection-cell">
                        <div class="selection-odds">${formatOdds(d.Odds2 || d['2'] || match.odds?.['2'])}</div>
                        ${d.Amt2 ? `<div class="selection-money">${d.Amt2}</div>` : ''}
                        ${d.Pct2 ? `<div class="selection-pct">${d.Pct2}%</div>` : ''}
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
                        ${d.PctUnder ? `<div class="selection-pct">${d.PctUnder}%</div>` : ''}
                    </td>
                    <td class="selection-cell">
                        <div class="selection-odds">${formatOdds(d.Over || match.odds?.Over)}</div>
                        ${d.AmtOver ? `<div class="selection-money">${d.AmtOver}</div>` : ''}
                        ${d.PctOver ? `<div class="selection-pct">${d.PctOver}%</div>` : ''}
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
                        ${d.PctYes ? `<div class="selection-pct">${d.PctYes}%</div>` : ''}
                    </td>
                    <td class="selection-cell">
                        <div class="selection-odds">${formatOdds(d.No || match.odds?.No)}</div>
                        ${d.AmtNo ? `<div class="selection-money">${d.AmtNo}</div>` : ''}
                        ${d.PctNo ? `<div class="selection-pct">${d.PctNo}%</div>` : ''}
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
    if (!query) {
        renderMatches(matches);
        return;
    }
    
    const filtered = matches.filter(m => 
        m.home_team.toLowerCase().includes(query) ||
        m.away_team.toLowerCase().includes(query) ||
        (m.league && m.league.toLowerCase().includes(query))
    );
    renderMatches(filtered);
}

function selectMatch(index) {
    if (index >= 0 && index < matches.length) {
        selectedMatch = matches[index];
        
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
        
        if (!data.chart_data.labels.length) {
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
                    plugins: {
                        legend: { display: false }
                    }
                }
            });
            return;
        }
        
        chart = new Chart(ctx, {
            type: 'line',
            data: data.chart_data,
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
                            color: '#9ca3af',
                            usePointStyle: true,
                            pointStyle: 'circle',
                            padding: 15,
                            font: { size: 11 }
                        }
                    },
                    tooltip: {
                        backgroundColor: '#1f2937',
                        titleColor: '#fff',
                        bodyColor: '#d1d5db',
                        borderColor: '#374151',
                        borderWidth: 1,
                        padding: 10,
                        displayColors: true
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
                            font: { size: 10 }
                        }
                    },
                    y: {
                        grid: {
                            color: '#2f3336',
                            drawBorder: false
                        },
                        ticks: {
                            color: '#8899a6',
                            font: { size: 10 }
                        }
                    }
                },
                elements: {
                    point: {
                        radius: 3,
                        hoverRadius: 5
                    },
                    line: {
                        borderWidth: 2
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
        
        const indicator = document.getElementById('statusIndicator');
        if (indicator) {
            const dot = indicator.querySelector('.status-dot');
            const text = indicator.querySelector('.status-text');
            
            if (status.running || status.auto_running) {
                dot.classList.add('running');
                text.textContent = status.auto_running ? 'Auto Scraping' : 'Scraping...';
            } else {
                dot.classList.remove('running');
                text.textContent = 'Ready';
            }
        }
    } catch (error) {
        console.error('Status check error:', error);
    }
}
