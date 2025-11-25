let currentMarket = 'moneyway_1x2';
let matches = [];
let chart = null;
let selectedMatch = null;

document.addEventListener('DOMContentLoaded', () => {
    loadMatches();
    setupTabs();
    setupSearch();
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
    
    document.querySelectorAll('.chart-tabs .chart-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.chart-tabs .chart-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            if (selectedMatch) {
                loadChart(selectedMatch.home_team, selectedMatch.away_team, tab.dataset.market);
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
            <td colspan="6">
                <div class="loading-spinner"></div>
                Loading matches...
            </td>
        </tr>
    `;
    
    try {
        const response = await fetch(`/api/matches?market=${currentMarket}`);
        matches = await response.json();
        renderMatches(matches);
    } catch (error) {
        console.error('Error loading matches:', error);
        tbody.innerHTML = `
            <tr class="loading-row">
                <td colspan="6">
                    <div class="empty-state">
                        <p>No data available. Click "Scrape Now" to fetch matches.</p>
                    </div>
                </td>
            </tr>
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
        tbody.innerHTML = `
            <tr class="loading-row">
                <td colspan="6">
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
    
    tbody.innerHTML = data.map(match => {
        const odds = match.odds || {};
        let oddsHtml = '';
        
        if (currentMarket.includes('1x2')) {
            oddsHtml = `
                <span class="odd">${formatOdds(odds['1'])}</span>
                <span class="separator">-</span>
                <span class="odd">${formatOdds(odds['X'])}</span>
                <span class="separator">-</span>
                <span class="odd">${formatOdds(odds['2'])}</span>
            `;
        } else if (currentMarket.includes('ou25')) {
            oddsHtml = `
                <span class="odd">${formatOdds(odds['Under'])}</span>
                <span class="separator">/</span>
                <span class="odd">${formatOdds(odds['Over'])}</span>
            `;
        } else if (currentMarket.includes('btts')) {
            oddsHtml = `
                <span class="odd">${formatOdds(odds['Yes'])}</span>
                <span class="separator">/</span>
                <span class="odd">${formatOdds(odds['No'])}</span>
            `;
        }
        
        return `
            <tr>
                <td>
                    <div class="match-teams">
                        <span class="home">${match.home_team}</span>
                        <span class="away">${match.away_team}</span>
                    </div>
                </td>
                <td class="competition">${match.league || '-'}</td>
                <td class="date">${match.date || '-'}</td>
                <td><span class="status-badge">Upcoming</span></td>
                <td>
                    <div class="odds-display">${oddsHtml}</div>
                </td>
                <td>
                    <button class="view-details" onclick="openMatchDetails('${escapeHtml(match.home_team)}', '${escapeHtml(match.away_team)}')">
                        View Details
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/>
                            <polyline points="15 3 21 3 21 9"/>
                            <line x1="10" y1="14" x2="21" y2="3"/>
                        </svg>
                    </button>
                </td>
            </tr>
        `;
    }).join('');
}

function formatOdds(value) {
    if (!value || value === '-') return '-';
    const str = String(value);
    const num = parseFloat(str.split('\n')[0]);
    return isNaN(num) ? '-' : num.toFixed(2);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML.replace(/'/g, "\\'");
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

async function openMatchDetails(home, away) {
    selectedMatch = { home_team: home, away_team: away };
    
    const modal = document.getElementById('chartModal');
    const title = document.getElementById('modalMatchTitle');
    
    if (title) {
        title.textContent = `${home} vs ${away}`;
    }
    
    modal.classList.add('active');
    
    document.querySelectorAll('.chart-tabs .chart-tab').forEach(t => t.classList.remove('active'));
    document.querySelector('.chart-tabs .chart-tab[data-market="moneyway_1x2"]')?.classList.add('active');
    
    await loadChart(home, away, 'moneyway_1x2');
}

async function loadChart(home, away, market) {
    try {
        const response = await fetch(`/api/match/history?home=${encodeURIComponent(home)}&away=${encodeURIComponent(away)}&market=${market}`);
        const data = await response.json();
        
        if (chart) {
            chart.destroy();
        }
        
        const ctx = document.getElementById('oddsChart').getContext('2d');
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
                            pointStyle: 'circle'
                        }
                    },
                    tooltip: {
                        backgroundColor: '#1f2937',
                        titleColor: '#fff',
                        bodyColor: '#d1d5db',
                        borderColor: '#374151',
                        borderWidth: 1,
                        padding: 12,
                        displayColors: true,
                        callbacks: {
                            title: function(items) {
                                if (items.length > 0) {
                                    const date = new Date();
                                    return date.toLocaleDateString('tr-TR') + ' ' + items[0].label;
                                }
                                return '';
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: {
                            color: '#374151',
                            drawBorder: false
                        },
                        ticks: {
                            color: '#9ca3af'
                        }
                    },
                    y: {
                        grid: {
                            color: '#374151',
                            drawBorder: false
                        },
                        ticks: {
                            color: '#9ca3af'
                        }
                    }
                },
                elements: {
                    point: {
                        radius: 4,
                        hoverRadius: 6
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

function closeModal() {
    const modal = document.getElementById('chartModal');
    modal.classList.remove('active');
    selectedMatch = null;
}

document.getElementById('chartModal')?.addEventListener('click', (e) => {
    if (e.target.id === 'chartModal') {
        closeModal();
    }
});

async function triggerScrape() {
    const btn = document.getElementById('scrapeBtn');
    const originalText = btn.innerHTML;
    
    btn.disabled = true;
    btn.innerHTML = `
        <div class="loading-spinner" style="width:16px;height:16px;margin:0;border-width:2px;"></div>
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
