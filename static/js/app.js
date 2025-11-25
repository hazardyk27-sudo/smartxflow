let currentMarket = 'moneyway_1x2';
let matches = [];
let filteredMatches = [];
let chart = null;
let selectedMatch = null;
let selectedChartMarket = 'moneyway_1x2';
let autoScrapeRunning = false;
let currentSort = 'date_desc';

const demoMatches = {
    'moneyway_1x2': [
        {
            home_team: 'Galatasaray',
            away_team: 'Fenerbahçe',
            league: 'Super Lig',
            date: '25.11.2025 20:00',
            details: {
                Odds1: '2.10', OddsX: '3.40', Odds2: '3.25',
                Amt1: '£125,400', AmtX: '£45,200', Amt2: '£38,600',
                Pct1: '59.8', PctX: '21.6', Pct2: '18.6',
                Volume: '£209,200'
            }
        },
        {
            home_team: 'Manchester City',
            away_team: 'Liverpool',
            league: 'Premier League',
            date: '25.11.2025 17:30',
            details: {
                Odds1: '1.85', OddsX: '3.80', Odds2: '4.00',
                Amt1: '£234,500', AmtX: '£67,800', Amt2: '£52,300',
                Pct1: '66.1', PctX: '19.1', Pct2: '14.8',
                Volume: '£354,600'
            }
        },
        {
            home_team: 'Real Madrid',
            away_team: 'Barcelona',
            league: 'La Liga',
            date: '25.11.2025 21:00',
            details: {
                Odds1: '2.25', OddsX: '3.50', Odds2: '2.90',
                Amt1: '£189,200', AmtX: '£56,400', Amt2: '£112,800',
                Pct1: '52.8', PctX: '15.7', Pct2: '31.5',
                Volume: '£358,400'
            }
        },
        {
            home_team: 'Bayern Munich',
            away_team: 'Dortmund',
            league: 'Bundesliga',
            date: '25.11.2025 18:30',
            details: {
                Odds1: '1.45', OddsX: '4.80', Odds2: '6.50',
                Amt1: '£312,600', AmtX: '£28,400', Amt2: '£15,200',
                Pct1: '87.8', PctX: '8.0', Pct2: '4.2',
                Volume: '£356,200'
            }
        },
        {
            home_team: 'PSG',
            away_team: 'Monaco',
            league: 'Ligue 1',
            date: '25.11.2025 21:00',
            details: {
                Odds1: '1.35', OddsX: '5.20', Odds2: '8.00',
                Amt1: '£285,400', AmtX: '£18,600', Amt2: '£9,200',
                Pct1: '91.2', PctX: '5.9', Pct2: '2.9',
                Volume: '£313,200'
            }
        },
        {
            home_team: 'Besiktas',
            away_team: 'Trabzonspor',
            league: 'Super Lig',
            date: '26.11.2025 19:00',
            details: {
                Odds1: '1.90', OddsX: '3.60', Odds2: '3.80',
                Amt1: '£156,800', AmtX: '£52,400', Amt2: '£48,200',
                Pct1: '60.9', PctX: '20.3', Pct2: '18.8',
                Volume: '£257,400'
            }
        },
        {
            home_team: 'Arsenal',
            away_team: 'Chelsea',
            league: 'Premier League',
            date: '26.11.2025 17:00',
            details: {
                Odds1: '2.00', OddsX: '3.50', Odds2: '3.40',
                Amt1: '£178,300', AmtX: '£64,500', Amt2: '£68,900',
                Pct1: '57.2', PctX: '20.7', Pct2: '22.1',
                Volume: '£311,700'
            }
        },
        {
            home_team: 'Juventus',
            away_team: 'AC Milan',
            league: 'Serie A',
            date: '25.11.2025 20:45',
            details: {
                Odds1: '2.40', OddsX: '3.20', Odds2: '2.85',
                Amt1: '£98,500', AmtX: '£42,300', Amt2: '£76,800',
                Pct1: '45.3', PctX: '19.4', Pct2: '35.3',
                Volume: '£217,600'
            }
        }
    ],
    'moneyway_ou25': [
        {
            home_team: 'Galatasaray',
            away_team: 'Fenerbahçe',
            league: 'Super Lig',
            date: '25.11.2025 20:00',
            details: {
                Under: '2.10', Over: '1.72',
                AmtUnder: '£85,200', AmtOver: '£124,000',
                PctUnder: '40.7', PctOver: '59.3',
                Volume: '£209,200'
            }
        },
        {
            home_team: 'Manchester City',
            away_team: 'Liverpool',
            league: 'Premier League',
            date: '25.11.2025 17:30',
            details: {
                Under: '2.30', Over: '1.58',
                AmtUnder: '£98,400', AmtOver: '£256,200',
                PctUnder: '27.8', PctOver: '72.2',
                Volume: '£354,600'
            }
        },
        {
            home_team: 'Bayern Munich',
            away_team: 'Dortmund',
            league: 'Bundesliga',
            date: '25.11.2025 18:30',
            details: {
                Under: '2.50', Over: '1.50',
                AmtUnder: '£62,400', AmtOver: '£293,800',
                PctUnder: '17.5', PctOver: '82.5',
                Volume: '£356,200'
            }
        }
    ],
    'moneyway_btts': [
        {
            home_team: 'Galatasaray',
            away_team: 'Fenerbahçe',
            league: 'Super Lig',
            date: '25.11.2025 20:00',
            details: {
                Yes: '1.65', No: '2.20',
                AmtYes: '£142,300', AmtNo: '£66,900',
                PctYes: '68.0', PctNo: '32.0',
                Volume: '£209,200'
            }
        },
        {
            home_team: 'Real Madrid',
            away_team: 'Barcelona',
            league: 'La Liga',
            date: '25.11.2025 21:00',
            details: {
                Yes: '1.55', No: '2.40',
                AmtYes: '£268,400', AmtNo: '£90,000',
                PctYes: '74.9', PctNo: '25.1',
                Volume: '£358,400'
            }
        }
    ],
    'dropping_1x2': [
        {
            home_team: 'Galatasaray',
            away_team: 'Fenerbahçe',
            league: 'Super Lig',
            date: '25.11.2025 20:00',
            details: {
                Odds1: '2.05', OddsX: '3.45', Odds2: '3.30',
                Volume: '£209,200'
            }
        },
        {
            home_team: 'Manchester City',
            away_team: 'Liverpool',
            league: 'Premier League',
            date: '25.11.2025 17:30',
            details: {
                Odds1: '1.80', OddsX: '3.90', Odds2: '4.20',
                Volume: '£354,600'
            }
        },
        {
            home_team: 'Bayern Munich',
            away_team: 'Dortmund',
            league: 'Bundesliga',
            date: '25.11.2025 18:30',
            details: {
                Odds1: '1.42', OddsX: '4.90', Odds2: '6.80',
                Volume: '£356,200'
            }
        }
    ],
    'dropping_ou25': [
        {
            home_team: 'Bayern Munich',
            away_team: 'Dortmund',
            league: 'Bundesliga',
            date: '25.11.2025 18:30',
            details: {
                Under: '2.45', Over: '1.52',
                Volume: '£356,200'
            }
        },
        {
            home_team: 'Real Madrid',
            away_team: 'Barcelona',
            league: 'La Liga',
            date: '25.11.2025 21:00',
            details: {
                Under: '2.35', Over: '1.55',
                Volume: '£358,400'
            }
        }
    ],
    'dropping_btts': [
        {
            home_team: 'Juventus',
            away_team: 'AC Milan',
            league: 'Serie A',
            date: '25.11.2025 20:45',
            details: {
                Yes: '1.70', No: '2.10',
                Volume: '£217,600'
            }
        },
        {
            home_team: 'Arsenal',
            away_team: 'Chelsea',
            league: 'Premier League',
            date: '26.11.2025 17:00',
            details: {
                Yes: '1.62', No: '2.25',
                Volume: '£311,700'
            }
        }
    ]
};

const demoHistory = [
    { ScrapedAt: '2025-11-25T16:00:00', Odds1: '2.20', OddsX: '3.30', Odds2: '3.15', Pct1: '56.2', PctX: '23.1', Pct2: '20.7', Amt1: '£112,200', AmtX: '£46,100', Amt2: '£41,300', Volume: '£199,600' },
    { ScrapedAt: '2025-11-25T16:10:00', Odds1: '2.18', OddsX: '3.32', Odds2: '3.18', Pct1: '57.0', PctX: '22.8', Pct2: '20.2', Amt1: '£115,800', AmtX: '£46,300', Amt2: '£41,000', Volume: '£203,100' },
    { ScrapedAt: '2025-11-25T16:20:00', Odds1: '2.15', OddsX: '3.35', Odds2: '3.20', Pct1: '58.2', PctX: '22.1', Pct2: '19.7', Amt1: '£118,200', AmtX: '£44,800', Amt2: '£40,000', Volume: '£203,000' },
    { ScrapedAt: '2025-11-25T16:30:00', Odds1: '2.12', OddsX: '3.38', Odds2: '3.22', Pct1: '58.8', PctX: '21.9', Pct2: '19.3', Amt1: '£120,500', AmtX: '£44,900', Amt2: '£39,600', Volume: '£205,000' },
    { ScrapedAt: '2025-11-25T16:40:00', Odds1: '2.10', OddsX: '3.40', Odds2: '3.25', Pct1: '59.5', PctX: '21.7', Pct2: '18.8', Amt1: '£123,800', AmtX: '£45,100', Amt2: '£39,100', Volume: '£208,000' },
    { ScrapedAt: '2025-11-25T16:50:00', Odds1: '2.10', OddsX: '3.40', Odds2: '3.25', Pct1: '59.8', PctX: '21.6', Pct2: '18.6', Amt1: '£125,400', AmtX: '£45,200', Amt2: '£38,600', Volume: '£209,200' }
];

document.addEventListener('DOMContentLoaded', () => {
    loadMatches();
    setupTabs();
    setupSearch();
    setupModalChartTabs();
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

function setupModalChartTabs() {
    document.querySelectorAll('#modalChartTabs .chart-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('#modalChartTabs .chart-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            selectedChartMarket = tab.dataset.market;
            if (selectedMatch) {
                updateMatchInfoCard();
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
        const apiMatches = await response.json();
        
        if (apiMatches && apiMatches.length > 0) {
            matches = apiMatches;
        } else {
            matches = demoMatches[currentMarket] || [];
        }
        
        filteredMatches = applySorting(matches);
        renderMatches(filteredMatches);
    } catch (error) {
        console.error('Error loading matches, using demo data:', error);
        matches = demoMatches[currentMarket] || [];
        filteredMatches = applySorting(matches);
        renderMatches(filteredMatches);
    }
}

function updateTableHeaders() {
    const thead = document.querySelector('.matches-table thead tr');
    if (!thead) return;
    
    const isDropping = currentMarket.startsWith('dropping');
    
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
                        <p>No matches found for this market. Click "Scrape Now" to fetch data.</p>
                    </div>
                </td>
            </tr>
        `;
        return;
    }
    
    const isDropping = currentMarket.startsWith('dropping');
    const isMoneyway = currentMarket.startsWith('moneyway');
    
    tbody.innerHTML = data.map((match, idx) => {
        const d = match.details || {};
        
        if (currentMarket.includes('1x2')) {
            if (isMoneyway) {
                return `
                    <tr data-index="${idx}" onclick="openMatchModal(${idx})">
                        <td class="match-date">${match.date || '-'}</td>
                        <td class="match-league" title="${match.league || ''}">${match.league || '-'}</td>
                        <td class="match-teams">${match.home_team}<span class="vs">-</span>${match.away_team}</td>
                        <td class="selection-cell">
                            <div class="selection-odds">${formatOdds(d.Odds1 || d['1'])}</div>
                            ${d.Amt1 ? `<div class="selection-money">${d.Amt1}</div>` : ''}
                            ${d.Pct1 ? `<div class="selection-pct ${getPctClass(d.Pct1)}">${d.Pct1}%</div>` : ''}
                        </td>
                        <td class="selection-cell">
                            <div class="selection-odds">${formatOdds(d.OddsX || d['X'])}</div>
                            ${d.AmtX ? `<div class="selection-money">${d.AmtX}</div>` : ''}
                            ${d.PctX ? `<div class="selection-pct ${getPctClass(d.PctX)}">${d.PctX}%</div>` : ''}
                        </td>
                        <td class="selection-cell">
                            <div class="selection-odds">${formatOdds(d.Odds2 || d['2'])}</div>
                            ${d.Amt2 ? `<div class="selection-money">${d.Amt2}</div>` : ''}
                            ${d.Pct2 ? `<div class="selection-pct ${getPctClass(d.Pct2)}">${d.Pct2}%</div>` : ''}
                        </td>
                        <td class="volume-cell">${d.Volume || '-'}</td>
                    </tr>
                `;
            } else {
                return `
                    <tr data-index="${idx}" onclick="openMatchModal(${idx})">
                        <td class="match-date">${match.date || '-'}</td>
                        <td class="match-league" title="${match.league || ''}">${match.league || '-'}</td>
                        <td class="match-teams">${match.home_team}<span class="vs">-</span>${match.away_team}</td>
                        <td class="selection-cell">
                            <div class="selection-odds">${formatOdds(d.Odds1 || d['1'])}</div>
                        </td>
                        <td class="selection-cell">
                            <div class="selection-odds">${formatOdds(d.OddsX || d['X'])}</div>
                        </td>
                        <td class="selection-cell">
                            <div class="selection-odds">${formatOdds(d.Odds2 || d['2'])}</div>
                        </td>
                        <td class="volume-cell">${d.Volume || '-'}</td>
                    </tr>
                `;
            }
        } else if (currentMarket.includes('ou25')) {
            if (isMoneyway) {
                return `
                    <tr data-index="${idx}" onclick="openMatchModal(${idx})">
                        <td class="match-date">${match.date || '-'}</td>
                        <td class="match-league" title="${match.league || ''}">${match.league || '-'}</td>
                        <td class="match-teams">${match.home_team}<span class="vs">-</span>${match.away_team}</td>
                        <td class="selection-cell">
                            <div class="selection-odds">${formatOdds(d.Under)}</div>
                            ${d.AmtUnder ? `<div class="selection-money">${d.AmtUnder}</div>` : ''}
                            ${d.PctUnder ? `<div class="selection-pct ${getPctClass(d.PctUnder)}">${d.PctUnder}%</div>` : ''}
                        </td>
                        <td class="selection-cell">
                            <div class="selection-odds">${formatOdds(d.Over)}</div>
                            ${d.AmtOver ? `<div class="selection-money">${d.AmtOver}</div>` : ''}
                            ${d.PctOver ? `<div class="selection-pct ${getPctClass(d.PctOver)}">${d.PctOver}%</div>` : ''}
                        </td>
                        <td class="volume-cell">${d.Volume || '-'}</td>
                    </tr>
                `;
            } else {
                return `
                    <tr data-index="${idx}" onclick="openMatchModal(${idx})">
                        <td class="match-date">${match.date || '-'}</td>
                        <td class="match-league" title="${match.league || ''}">${match.league || '-'}</td>
                        <td class="match-teams">${match.home_team}<span class="vs">-</span>${match.away_team}</td>
                        <td class="selection-cell">
                            <div class="selection-odds">${formatOdds(d.Under)}</div>
                        </td>
                        <td class="selection-cell">
                            <div class="selection-odds">${formatOdds(d.Over)}</div>
                        </td>
                        <td class="volume-cell">${d.Volume || '-'}</td>
                    </tr>
                `;
            }
        } else {
            if (isMoneyway) {
                return `
                    <tr data-index="${idx}" onclick="openMatchModal(${idx})">
                        <td class="match-date">${match.date || '-'}</td>
                        <td class="match-league" title="${match.league || ''}">${match.league || '-'}</td>
                        <td class="match-teams">${match.home_team}<span class="vs">-</span>${match.away_team}</td>
                        <td class="selection-cell">
                            <div class="selection-odds">${formatOdds(d.Yes)}</div>
                            ${d.AmtYes ? `<div class="selection-money">${d.AmtYes}</div>` : ''}
                            ${d.PctYes ? `<div class="selection-pct ${getPctClass(d.PctYes)}">${d.PctYes}%</div>` : ''}
                        </td>
                        <td class="selection-cell">
                            <div class="selection-odds">${formatOdds(d.No)}</div>
                            ${d.AmtNo ? `<div class="selection-money">${d.AmtNo}</div>` : ''}
                            ${d.PctNo ? `<div class="selection-pct ${getPctClass(d.PctNo)}">${d.PctNo}%</div>` : ''}
                        </td>
                        <td class="volume-cell">${d.Volume || '-'}</td>
                    </tr>
                `;
            } else {
                return `
                    <tr data-index="${idx}" onclick="openMatchModal(${idx})">
                        <td class="match-date">${match.date || '-'}</td>
                        <td class="match-league" title="${match.league || ''}">${match.league || '-'}</td>
                        <td class="match-teams">${match.home_team}<span class="vs">-</span>${match.away_team}</td>
                        <td class="selection-cell">
                            <div class="selection-odds">${formatOdds(d.Yes)}</div>
                        </td>
                        <td class="selection-cell">
                            <div class="selection-odds">${formatOdds(d.No)}</div>
                        </td>
                        <td class="volume-cell">${d.Volume || '-'}</td>
                    </tr>
                `;
            }
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

function openMatchModal(index) {
    const dataSource = filteredMatches.length > 0 ? filteredMatches : matches;
    if (index >= 0 && index < dataSource.length) {
        selectedMatch = dataSource[index];
        selectedChartMarket = currentMarket;
        
        document.getElementById('modalMatchTitle').textContent = 
            `${selectedMatch.home_team} vs ${selectedMatch.away_team}`;
        document.getElementById('modalLeague').textContent = 
            `${selectedMatch.league || ''} • ${selectedMatch.date || ''}`;
        
        updateMatchInfoCard();
        
        document.querySelectorAll('#modalChartTabs .chart-tab').forEach(t => {
            t.classList.remove('active');
            if (t.dataset.market === currentMarket) {
                t.classList.add('active');
            }
        });
        
        document.getElementById('modalOverlay').classList.add('active');
        loadChart(selectedMatch.home_team, selectedMatch.away_team, selectedChartMarket);
    }
}

function updateMatchInfoCard() {
    const card = document.getElementById('matchInfoCard');
    const d = selectedMatch.details || {};
    const isMoneyway = selectedChartMarket.startsWith('moneyway');
    const isDropping = selectedChartMarket.startsWith('dropping');
    
    let html = '';
    
    if (selectedChartMarket.includes('1x2')) {
        if (isMoneyway) {
            html = `
                <div class="info-row">
                    <div class="info-item">
                        <div class="info-label">1 Odds</div>
                        <div class="info-value odds">${formatOdds(d.Odds1 || d['1'])}</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">X Odds</div>
                        <div class="info-value odds">${formatOdds(d.OddsX || d['X'])}</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">2 Odds</div>
                        <div class="info-value odds">${formatOdds(d.Odds2 || d['2'])}</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">Total Volume</div>
                        <div class="info-value volume">${d.Volume || '-'}</div>
                    </div>
                </div>
                <div class="info-row">
                    <div class="info-item">
                        <div class="info-label">1 Stake</div>
                        <div class="info-value money">${d.Amt1 || '-'}</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">X Stake</div>
                        <div class="info-value money">${d.AmtX || '-'}</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">2 Stake</div>
                        <div class="info-value money">${d.Amt2 || '-'}</div>
                    </div>
                </div>
                <div class="info-row">
                    <div class="info-item">
                        <div class="info-label">1 %</div>
                        <div class="info-value pct ${getPctClass(d.Pct1)}">${d.Pct1 || '-'}%</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">X %</div>
                        <div class="info-value pct ${getPctClass(d.PctX)}">${d.PctX || '-'}%</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">2 %</div>
                        <div class="info-value pct ${getPctClass(d.Pct2)}">${d.Pct2 || '-'}%</div>
                    </div>
                </div>
            `;
        } else {
            html = `
                <div class="info-row">
                    <div class="info-item">
                        <div class="info-label">1 Odds</div>
                        <div class="info-value odds">${formatOdds(d.Odds1 || d['1'])}</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">X Odds</div>
                        <div class="info-value odds">${formatOdds(d.OddsX || d['X'])}</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">2 Odds</div>
                        <div class="info-value odds">${formatOdds(d.Odds2 || d['2'])}</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">Volume</div>
                        <div class="info-value volume">${d.Volume || '-'}</div>
                    </div>
                </div>
            `;
        }
    } else if (selectedChartMarket.includes('ou25')) {
        if (isMoneyway) {
            html = `
                <div class="info-row">
                    <div class="info-item">
                        <div class="info-label">Under 2.5</div>
                        <div class="info-value odds">${formatOdds(d.Under)}</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">Over 2.5</div>
                        <div class="info-value odds">${formatOdds(d.Over)}</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">Total Volume</div>
                        <div class="info-value volume">${d.Volume || '-'}</div>
                    </div>
                </div>
                <div class="info-row">
                    <div class="info-item">
                        <div class="info-label">Under Stake</div>
                        <div class="info-value money">${d.AmtUnder || '-'}</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">Over Stake</div>
                        <div class="info-value money">${d.AmtOver || '-'}</div>
                    </div>
                </div>
                <div class="info-row">
                    <div class="info-item">
                        <div class="info-label">Under %</div>
                        <div class="info-value pct ${getPctClass(d.PctUnder)}">${d.PctUnder || '-'}%</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">Over %</div>
                        <div class="info-value pct ${getPctClass(d.PctOver)}">${d.PctOver || '-'}%</div>
                    </div>
                </div>
            `;
        } else {
            html = `
                <div class="info-row">
                    <div class="info-item">
                        <div class="info-label">Under 2.5</div>
                        <div class="info-value odds">${formatOdds(d.Under)}</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">Over 2.5</div>
                        <div class="info-value odds">${formatOdds(d.Over)}</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">Volume</div>
                        <div class="info-value volume">${d.Volume || '-'}</div>
                    </div>
                </div>
            `;
        }
    } else if (selectedChartMarket.includes('btts')) {
        if (isMoneyway) {
            html = `
                <div class="info-row">
                    <div class="info-item">
                        <div class="info-label">Yes</div>
                        <div class="info-value odds">${formatOdds(d.Yes)}</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">No</div>
                        <div class="info-value odds">${formatOdds(d.No)}</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">Total Volume</div>
                        <div class="info-value volume">${d.Volume || '-'}</div>
                    </div>
                </div>
                <div class="info-row">
                    <div class="info-item">
                        <div class="info-label">Yes Stake</div>
                        <div class="info-value money">${d.AmtYes || '-'}</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">No Stake</div>
                        <div class="info-value money">${d.AmtNo || '-'}</div>
                    </div>
                </div>
                <div class="info-row">
                    <div class="info-item">
                        <div class="info-label">Yes %</div>
                        <div class="info-value pct ${getPctClass(d.PctYes)}">${d.PctYes || '-'}%</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">No %</div>
                        <div class="info-value pct ${getPctClass(d.PctNo)}">${d.PctNo || '-'}%</div>
                    </div>
                </div>
            `;
        } else {
            html = `
                <div class="info-row">
                    <div class="info-item">
                        <div class="info-label">Yes</div>
                        <div class="info-value odds">${formatOdds(d.Yes)}</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">No</div>
                        <div class="info-value odds">${formatOdds(d.No)}</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">Volume</div>
                        <div class="info-value volume">${d.Volume || '-'}</div>
                    </div>
                </div>
            `;
        }
    }
    
    card.innerHTML = html;
}

function closeModal() {
    document.getElementById('modalOverlay').classList.remove('active');
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
        let data = { history: [] };
        
        try {
            const response = await fetch(
                `/api/match/history?home=${encodeURIComponent(home)}&away=${encodeURIComponent(away)}&market=${market}`
            );
            data = await response.json();
        } catch (e) {
            console.log('Using demo history data');
        }
        
        if (!data.history || data.history.length === 0) {
            data.history = demoHistory;
        }
        
        if (chart) {
            chart.destroy();
        }
        
        const ctx = document.getElementById('oddsChart').getContext('2d');
        const isMoneyway = market.startsWith('moneyway');
        const isDropping = market.startsWith('dropping');
        
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
            '1': '#3b82f6',
            'X': '#22c55e', 
            '2': '#eab308',
            'Under': '#3b82f6',
            'Over': '#22c55e',
            'Yes': '#22c55e',
            'No': '#ef4444'
        };
        
        const latestData = historyData[historyData.length - 1] || {};
        
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
                        tension: 0.1,
                        fill: false,
                        pointRadius: 6,
                        pointHoverRadius: 9,
                        pointBackgroundColor: color,
                        pointBorderColor: '#fff',
                        pointBorderWidth: 2,
                        pointStyle: 'circle',
                        borderWidth: 3
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
                        tension: 0.1,
                        fill: false,
                        pointRadius: 6,
                        pointHoverRadius: 9,
                        pointBackgroundColor: color,
                        pointBorderColor: '#fff',
                        pointBorderWidth: 2,
                        pointStyle: 'circle',
                        borderWidth: 3
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
                        tension: 0.1,
                        fill: false,
                        pointRadius: 6,
                        pointHoverRadius: 9,
                        pointBackgroundColor: color,
                        pointBorderColor: '#fff',
                        pointBorderWidth: 2,
                        pointStyle: 'circle',
                        borderWidth: 3
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
                        tension: 0.1,
                        fill: false,
                        pointRadius: 6,
                        pointHoverRadius: 9,
                        pointBackgroundColor: color,
                        pointBorderColor: '#fff',
                        pointBorderWidth: 2,
                        pointStyle: 'circle',
                        borderWidth: 3
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
                        tension: 0.1,
                        fill: false,
                        pointRadius: 6,
                        pointHoverRadius: 9,
                        pointBackgroundColor: color,
                        pointBorderColor: '#fff',
                        pointBorderWidth: 2,
                        pointStyle: 'circle',
                        borderWidth: 3
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
                        tension: 0.1,
                        fill: false,
                        pointRadius: 6,
                        pointHoverRadius: 9,
                        pointBackgroundColor: color,
                        pointBorderColor: '#fff',
                        pointBorderWidth: 2,
                        pointStyle: 'circle',
                        borderWidth: 3
                    });
                });
            }
        }
        
        const tooltipHistory = historyData;
        
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
                            padding: 20,
                            font: { size: 13, weight: 'bold' },
                            boxWidth: 14,
                            boxHeight: 14
                        }
                    },
                    tooltip: {
                        backgroundColor: '#1f2937',
                        titleColor: '#fff',
                        titleFont: { size: 14, weight: 'bold' },
                        bodyColor: '#e7e9ea',
                        bodyFont: { size: 13 },
                        borderColor: '#374151',
                        borderWidth: 1,
                        padding: 16,
                        displayColors: true,
                        boxWidth: 14,
                        boxHeight: 14,
                        boxPadding: 6,
                        callbacks: {
                            label: function(context) {
                                const idx = context.dataIndex;
                                const h = tooltipHistory[idx];
                                if (!h) return context.dataset.label + ': ' + context.formattedValue;
                                
                                const datasetLabel = context.dataset.label;
                                let lines = [];
                                
                                if (isDropping) {
                                    const currentOdds = parseFloat(context.formattedValue);
                                    const latestOdds = getLatestOdds(latestData, datasetLabel.replace('%', ''), market);
                                    
                                    if (!isNaN(currentOdds) && !isNaN(latestOdds) && currentOdds > 0) {
                                        const pctChange = ((latestOdds - currentOdds) / currentOdds) * 100;
                                        const changeSign = pctChange >= 0 ? '+' : '';
                                        const changeStr = `${changeSign}${pctChange.toFixed(1)}%`;
                                        
                                        lines.push(`${datasetLabel}: ${currentOdds.toFixed(2)} → ${latestOdds.toFixed(2)}`);
                                        if (pctChange >= 0) {
                                            lines.push(`Change: ${changeStr} (UP)`);
                                        } else {
                                            lines.push(`Change: ${changeStr} (DOWN)`);
                                        }
                                    } else {
                                        lines.push(`${datasetLabel}: ${context.formattedValue}`);
                                    }
                                } else {
                                    if (market.includes('1x2')) {
                                        if (datasetLabel.includes('1')) {
                                            const odds = h.Odds1 || h['1'] || '-';
                                            const amt = h.Amt1 || '';
                                            const pct = h.Pct1 || '';
                                            lines.push(`1 • ${formatOdds(odds)}`);
                                            if (amt) lines.push(`${amt} — ${pct}%`);
                                        } else if (datasetLabel.includes('X')) {
                                            const odds = h.OddsX || h['X'] || '-';
                                            const amt = h.AmtX || '';
                                            const pct = h.PctX || '';
                                            lines.push(`X • ${formatOdds(odds)}`);
                                            if (amt) lines.push(`${amt} — ${pct}%`);
                                        } else if (datasetLabel.includes('2')) {
                                            const odds = h.Odds2 || h['2'] || '-';
                                            const amt = h.Amt2 || '';
                                            const pct = h.Pct2 || '';
                                            lines.push(`2 • ${formatOdds(odds)}`);
                                            if (amt) lines.push(`${amt} — ${pct}%`);
                                        }
                                    } else if (market.includes('ou25')) {
                                        if (datasetLabel.toLowerCase().includes('under')) {
                                            const odds = h.Under || '-';
                                            const amt = h.AmtUnder || '';
                                            const pct = h.PctUnder || '';
                                            lines.push(`Under • ${formatOdds(odds)}`);
                                            if (amt) lines.push(`${amt} — ${pct}%`);
                                        } else {
                                            const odds = h.Over || '-';
                                            const amt = h.AmtOver || '';
                                            const pct = h.PctOver || '';
                                            lines.push(`Over • ${formatOdds(odds)}`);
                                            if (amt) lines.push(`${amt} — ${pct}%`);
                                        }
                                    } else if (market.includes('btts')) {
                                        if (datasetLabel.toLowerCase().includes('yes')) {
                                            const odds = h.Yes || '-';
                                            const amt = h.AmtYes || '';
                                            const pct = h.PctYes || '';
                                            lines.push(`Yes • ${formatOdds(odds)}`);
                                            if (amt) lines.push(`${amt} — ${pct}%`);
                                        } else {
                                            const odds = h.No || '-';
                                            const amt = h.AmtNo || '';
                                            const pct = h.PctNo || '';
                                            lines.push(`No • ${formatOdds(odds)}`);
                                            if (amt) lines.push(`${amt} — ${pct}%`);
                                        }
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
                            color: 'rgba(55, 65, 81, 0.5)',
                            drawBorder: false
                        },
                        ticks: {
                            color: '#8899a6',
                            font: { size: 12 }
                        }
                    },
                    y: {
                        grid: {
                            color: 'rgba(55, 65, 81, 0.5)',
                            drawBorder: false
                        },
                        ticks: {
                            color: '#8899a6',
                            font: { size: 12 }
                        }
                    }
                },
                elements: {
                    point: {
                        radius: 6,
                        hoverRadius: 9,
                        borderWidth: 2
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

function getLatestOdds(latestData, label, market) {
    if (market.includes('1x2')) {
        if (label === '1') return parseFloat(latestData.Odds1 || latestData['1']) || 0;
        if (label === 'X') return parseFloat(latestData.OddsX || latestData['X']) || 0;
        if (label === '2') return parseFloat(latestData.Odds2 || latestData['2']) || 0;
    } else if (market.includes('ou25')) {
        if (label === 'Under') return parseFloat(latestData.Under) || 0;
        if (label === 'Over') return parseFloat(latestData.Over) || 0;
    } else if (market.includes('btts')) {
        if (label === 'Yes') return parseFloat(latestData.Yes) || 0;
        if (label === 'No') return parseFloat(latestData.No) || 0;
    }
    return 0;
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

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeModal();
    }
});
