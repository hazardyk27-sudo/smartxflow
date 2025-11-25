let currentMarket = 'moneyway_1x2';
let matches = [];
let filteredMatches = [];
let chart = null;
let selectedMatch = null;
let selectedChartMarket = 'moneyway_1x2';
let autoScrapeRunning = false;
let currentSortColumn = 'date';
let currentSortDirection = 'desc';
let chartVisibleSeries = {};
let todayFilterActive = false;
let chartTimeRange = '1day';
let currentChartHistoryData = [];

const demoMatches = {
    'moneyway_1x2': [
        {
            home_team: 'Galatasaray',
            away_team: 'Fenerbahçe',
            league: 'Super Lig',
            date: '25.11.2025 20:00',
            details: {
                Odds1: '2.10', OddsX: '3.40', Odds2: '3.25',
                PrevOdds1: '2.08', PrevOddsX: '3.42', PrevOdds2: '3.28',
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
                PrevOdds1: '1.90', PrevOddsX: '3.75', PrevOdds2: '3.95',
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
                PrevOdds1: '2.30', PrevOddsX: '3.45', PrevOdds2: '2.85',
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
                PrevOdds1: '1.48', PrevOddsX: '4.75', PrevOdds2: '6.40',
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
                PrevOdds1: '1.38', PrevOddsX: '5.10', PrevOdds2: '7.80',
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
                PrevOdds1: '1.95', PrevOddsX: '3.55', PrevOdds2: '3.75',
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
                PrevOdds1: '2.05', PrevOddsX: '3.45', PrevOdds2: '3.35',
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
                PrevOdds1: '2.35', PrevOddsX: '3.25', PrevOdds2: '2.90',
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
                PrevOdds1: '2.15', PrevOddsX: '3.40', PrevOdds2: '3.20',
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
                PrevOdds1: '1.95', PrevOddsX: '3.75', PrevOdds2: '4.00',
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
                PrevOdds1: '1.50', PrevOddsX: '4.70', PrevOdds2: '6.50',
                Volume: '£356,200'
            }
        },
        {
            home_team: 'Real Madrid',
            away_team: 'Barcelona',
            league: 'La Liga',
            date: '25.11.2025 21:00',
            details: {
                Odds1: '2.20', OddsX: '3.55', Odds2: '2.95',
                PrevOdds1: '2.30', PrevOddsX: '3.50', PrevOdds2: '2.85',
                Volume: '£358,400'
            }
        },
        {
            home_team: 'PSG',
            away_team: 'Monaco',
            league: 'Ligue 1',
            date: '25.11.2025 21:00',
            details: {
                Odds1: '1.32', OddsX: '5.30', Odds2: '8.20',
                PrevOdds1: '1.40', PrevOddsX: '5.10', PrevOdds2: '7.80',
                Volume: '£313,200'
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
                PrevUnder: '2.55', PrevOver: '1.48',
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
                PrevUnder: '2.25', PrevOver: '1.62',
                Volume: '£358,400'
            }
        },
        {
            home_team: 'Manchester City',
            away_team: 'Liverpool',
            league: 'Premier League',
            date: '25.11.2025 17:30',
            details: {
                Under: '2.28', Over: '1.60',
                PrevUnder: '2.35', PrevOver: '1.55',
                Volume: '£354,600'
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
                PrevYes: '1.80', PrevNo: '2.00',
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
                PrevYes: '1.72', PrevNo: '2.10',
                Volume: '£311,700'
            }
        },
        {
            home_team: 'Real Madrid',
            away_team: 'Barcelona',
            league: 'La Liga',
            date: '25.11.2025 21:00',
            details: {
                Yes: '1.52', No: '2.45',
                PrevYes: '1.58', PrevNo: '2.35',
                Volume: '£358,400'
            }
        }
    ]
};

const demoHistory = [
    { ScrapedAt: '2025-11-25T16:00:00', Odds1: '2.20', OddsX: '3.30', Odds2: '3.15', Pct1: '56.2', PctX: '23.1', Pct2: '20.7', Amt1: '£112,200', AmtX: '£46,100', Amt2: '£41,300', Volume: '£199,600', Under: '1.95', Over: '1.85', Yes: '1.75', No: '1.95' },
    { ScrapedAt: '2025-11-25T16:10:00', Odds1: '2.18', OddsX: '3.32', Odds2: '3.18', Pct1: '57.0', PctX: '22.8', Pct2: '20.2', Amt1: '£115,800', AmtX: '£46,300', Amt2: '£41,000', Volume: '£203,100', Under: '1.92', Over: '1.88', Yes: '1.78', No: '1.92' },
    { ScrapedAt: '2025-11-25T16:20:00', Odds1: '2.15', OddsX: '3.35', Odds2: '3.20', Pct1: '58.2', PctX: '22.1', Pct2: '19.7', Amt1: '£118,200', AmtX: '£44,800', Amt2: '£40,000', Volume: '£203,000', Under: '1.88', Over: '1.92', Yes: '1.82', No: '1.88' },
    { ScrapedAt: '2025-11-25T16:30:00', Odds1: '2.12', OddsX: '3.38', Odds2: '3.22', Pct1: '58.8', PctX: '21.9', Pct2: '19.3', Amt1: '£120,500', AmtX: '£44,900', Amt2: '£39,600', Volume: '£205,000', Under: '1.85', Over: '1.95', Yes: '1.85', No: '1.85' },
    { ScrapedAt: '2025-11-25T16:40:00', Odds1: '2.08', OddsX: '3.42', Odds2: '3.28', Pct1: '59.5', PctX: '21.7', Pct2: '18.8', Amt1: '£123,800', AmtX: '£45,100', Amt2: '£39,100', Volume: '£208,000', Under: '1.82', Over: '1.98', Yes: '1.88', No: '1.82' },
    { ScrapedAt: '2025-11-25T16:50:00', Odds1: '2.10', OddsX: '3.40', Odds2: '3.25', Pct1: '59.8', PctX: '21.6', Pct2: '18.6', Amt1: '£125,400', AmtX: '£45,200', Amt2: '£38,600', Volume: '£209,200', Under: '1.80', Over: '2.00', Yes: '1.90', No: '1.80' }
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
    
    const getArrow = (col) => {
        if (currentSortColumn === col) {
            return currentSortDirection === 'asc' ? '↑' : '↓';
        }
        return '';
    };
    
    const getActiveClass = (col) => currentSortColumn === col ? 'active' : '';
    
    if (currentMarket.includes('1x2')) {
        thead.innerHTML = `
            <th class="col-date sortable ${getActiveClass('date')}" data-sort="date" onclick="sortByColumn('date')">DATE <span class="sort-arrow">${getArrow('date')}</span></th>
            <th class="col-league sortable ${getActiveClass('league')}" data-sort="league" onclick="sortByColumn('league')">LEAGUE <span class="sort-arrow">${getArrow('league')}</span></th>
            <th class="col-match sortable ${getActiveClass('match')}" data-sort="match" onclick="sortByColumn('match')">MATCH <span class="sort-arrow">${getArrow('match')}</span></th>
            <th class="col-selection sortable ${getActiveClass('sel1')}" data-sort="sel1" onclick="sortByColumn('sel1')">1 <span class="sort-arrow">${getArrow('sel1')}</span></th>
            <th class="col-selection sortable ${getActiveClass('selX')}" data-sort="selX" onclick="sortByColumn('selX')">X <span class="sort-arrow">${getArrow('selX')}</span></th>
            <th class="col-selection sortable ${getActiveClass('sel2')}" data-sort="sel2" onclick="sortByColumn('sel2')">2 <span class="sort-arrow">${getArrow('sel2')}</span></th>
            <th class="col-volume sortable ${getActiveClass('volume')}" data-sort="volume" onclick="sortByColumn('volume')">VOLUME <span class="sort-arrow">${getArrow('volume')}</span></th>
        `;
    } else if (currentMarket.includes('ou25')) {
        thead.innerHTML = `
            <th class="col-date sortable ${getActiveClass('date')}" data-sort="date" onclick="sortByColumn('date')">DATE <span class="sort-arrow">${getArrow('date')}</span></th>
            <th class="col-league sortable ${getActiveClass('league')}" data-sort="league" onclick="sortByColumn('league')">LEAGUE <span class="sort-arrow">${getArrow('league')}</span></th>
            <th class="col-match sortable ${getActiveClass('match')}" data-sort="match" onclick="sortByColumn('match')">MATCH <span class="sort-arrow">${getArrow('match')}</span></th>
            <th class="col-selection sortable ${getActiveClass('sel1')}" data-sort="sel1" onclick="sortByColumn('sel1')">UNDER <span class="sort-arrow">${getArrow('sel1')}</span></th>
            <th class="col-selection sortable ${getActiveClass('sel2')}" data-sort="sel2" onclick="sortByColumn('sel2')">OVER <span class="sort-arrow">${getArrow('sel2')}</span></th>
            <th class="col-volume sortable ${getActiveClass('volume')}" data-sort="volume" onclick="sortByColumn('volume')">VOLUME <span class="sort-arrow">${getArrow('volume')}</span></th>
        `;
    } else if (currentMarket.includes('btts')) {
        thead.innerHTML = `
            <th class="col-date sortable ${getActiveClass('date')}" data-sort="date" onclick="sortByColumn('date')">DATE <span class="sort-arrow">${getArrow('date')}</span></th>
            <th class="col-league sortable ${getActiveClass('league')}" data-sort="league" onclick="sortByColumn('league')">LEAGUE <span class="sort-arrow">${getArrow('league')}</span></th>
            <th class="col-match sortable ${getActiveClass('match')}" data-sort="match" onclick="sortByColumn('match')">MATCH <span class="sort-arrow">${getArrow('match')}</span></th>
            <th class="col-selection sortable ${getActiveClass('sel1')}" data-sort="sel1" onclick="sortByColumn('sel1')">YES <span class="sort-arrow">${getArrow('sel1')}</span></th>
            <th class="col-selection sortable ${getActiveClass('sel2')}" data-sort="sel2" onclick="sortByColumn('sel2')">NO <span class="sort-arrow">${getArrow('sel2')}</span></th>
            <th class="col-volume sortable ${getActiveClass('volume')}" data-sort="volume" onclick="sortByColumn('volume')">VOLUME <span class="sort-arrow">${getArrow('volume')}</span></th>
        `;
    }
}

function getColorClass(pctValue) {
    const num = parseFloat(String(pctValue).replace(/[^0-9.]/g, ''));
    if (isNaN(num)) return 'color-normal';
    if (num >= 90) return 'color-red';
    if (num >= 70) return 'color-orange';
    if (num >= 50) return 'color-yellow';
    return 'color-normal';
}

function formatPct(val) {
    if (!val || val === '-') return '-';
    const cleaned = String(val).replace(/[%\s]/g, '');
    const num = parseFloat(cleaned);
    if (isNaN(num)) return '-';
    return num.toFixed(1);
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
            const trend1 = isDropping ? getTableTrendArrow(d.Odds1 || d['1'], d.PrevOdds1) : '';
            const trendX = isDropping ? getTableTrendArrow(d.OddsX || d['X'], d.PrevOddsX) : '';
            const trend2 = isDropping ? getTableTrendArrow(d.Odds2 || d['2'], d.PrevOdds2) : '';
            
            if (isMoneyway) {
                const c1 = getColorClass(d.Pct1);
                const cX = getColorClass(d.PctX);
                const c2 = getColorClass(d.Pct2);
                return `
                    <tr data-index="${idx}" onclick="openMatchModal(${idx})">
                        <td class="match-date">${match.date || '-'}</td>
                        <td class="match-league" title="${match.league || ''}">${match.league || '-'}</td>
                        <td class="match-teams">${match.home_team}<span class="vs">-</span>${match.away_team}</td>
                        <td class="selection-cell">
                            <div class="selection-odds">${formatOdds(d.Odds1 || d['1'])}</div>
                            ${d.Amt1 ? `<div class="selection-money ${c1}">${d.Amt1}</div>` : ''}
                            ${d.Pct1 ? `<div class="selection-pct ${c1}">${d.Pct1}%</div>` : ''}
                        </td>
                        <td class="selection-cell">
                            <div class="selection-odds">${formatOdds(d.OddsX || d['X'])}</div>
                            ${d.AmtX ? `<div class="selection-money ${cX}">${d.AmtX}</div>` : ''}
                            ${d.PctX ? `<div class="selection-pct ${cX}">${d.PctX}%</div>` : ''}
                        </td>
                        <td class="selection-cell">
                            <div class="selection-odds">${formatOdds(d.Odds2 || d['2'])}</div>
                            ${d.Amt2 ? `<div class="selection-money ${c2}">${d.Amt2}</div>` : ''}
                            ${d.Pct2 ? `<div class="selection-pct ${c2}">${d.Pct2}%</div>` : ''}
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
                            <div class="selection-odds drop-odds">${formatOdds(d.Odds1 || d['1'])}${trend1}</div>
                        </td>
                        <td class="selection-cell">
                            <div class="selection-odds drop-odds">${formatOdds(d.OddsX || d['X'])}${trendX}</div>
                        </td>
                        <td class="selection-cell">
                            <div class="selection-odds drop-odds">${formatOdds(d.Odds2 || d['2'])}${trend2}</div>
                        </td>
                        <td class="volume-cell">${d.Volume || '-'}</td>
                    </tr>
                `;
            }
        } else if (currentMarket.includes('ou25')) {
            const trendUnder = isDropping ? getTableTrendArrow(d.Under, d.PrevUnder) : '';
            const trendOver = isDropping ? getTableTrendArrow(d.Over, d.PrevOver) : '';
            
            if (isMoneyway) {
                const cU = getColorClass(d.PctUnder);
                const cO = getColorClass(d.PctOver);
                return `
                    <tr data-index="${idx}" onclick="openMatchModal(${idx})">
                        <td class="match-date">${match.date || '-'}</td>
                        <td class="match-league" title="${match.league || ''}">${match.league || '-'}</td>
                        <td class="match-teams">${match.home_team}<span class="vs">-</span>${match.away_team}</td>
                        <td class="selection-cell">
                            <div class="selection-odds">${formatOdds(d.Under)}</div>
                            ${d.AmtUnder ? `<div class="selection-money ${cU}">${d.AmtUnder}</div>` : ''}
                            ${d.PctUnder ? `<div class="selection-pct ${cU}">${d.PctUnder}%</div>` : ''}
                        </td>
                        <td class="selection-cell">
                            <div class="selection-odds">${formatOdds(d.Over)}</div>
                            ${d.AmtOver ? `<div class="selection-money ${cO}">${d.AmtOver}</div>` : ''}
                            ${d.PctOver ? `<div class="selection-pct ${cO}">${d.PctOver}%</div>` : ''}
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
                            <div class="selection-odds drop-odds">${formatOdds(d.Under)}${trendUnder}</div>
                        </td>
                        <td class="selection-cell">
                            <div class="selection-odds drop-odds">${formatOdds(d.Over)}${trendOver}</div>
                        </td>
                        <td class="volume-cell">${d.Volume || '-'}</td>
                    </tr>
                `;
            }
        } else {
            const trendYes = isDropping ? getTableTrendArrow(d.Yes, d.PrevYes) : '';
            const trendNo = isDropping ? getTableTrendArrow(d.No, d.PrevNo) : '';
            
            if (isMoneyway) {
                const cY = getColorClass(d.PctYes);
                const cN = getColorClass(d.PctNo);
                return `
                    <tr data-index="${idx}" onclick="openMatchModal(${idx})">
                        <td class="match-date">${match.date || '-'}</td>
                        <td class="match-league" title="${match.league || ''}">${match.league || '-'}</td>
                        <td class="match-teams">${match.home_team}<span class="vs">-</span>${match.away_team}</td>
                        <td class="selection-cell">
                            <div class="selection-odds">${formatOdds(d.Yes)}</div>
                            ${d.AmtYes ? `<div class="selection-money ${cY}">${d.AmtYes}</div>` : ''}
                            ${d.PctYes ? `<div class="selection-pct ${cY}">${d.PctYes}%</div>` : ''}
                        </td>
                        <td class="selection-cell">
                            <div class="selection-odds">${formatOdds(d.No)}</div>
                            ${d.AmtNo ? `<div class="selection-money ${cN}">${d.AmtNo}</div>` : ''}
                            ${d.PctNo ? `<div class="selection-pct ${cN}">${d.PctNo}%</div>` : ''}
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
                            <div class="selection-odds drop-odds">${formatOdds(d.Yes)}${trendYes}</div>
                        </td>
                        <td class="selection-cell">
                            <div class="selection-odds drop-odds">${formatOdds(d.No)}${trendNo}</div>
                        </td>
                        <td class="volume-cell">${d.Volume || '-'}</td>
                    </tr>
                `;
            }
        }
    }).join('');
}

function getTableTrendArrow(current, previous) {
    if (!current || !previous) return '';
    const curr = parseFloat(String(current).replace(/[^0-9.]/g, ''));
    const prev = parseFloat(String(previous).replace(/[^0-9.]/g, ''));
    if (isNaN(curr) || isNaN(prev)) return '';
    if (curr > prev) return '<span class="trend-up">↑</span>';
    if (curr < prev) return '<span class="trend-down">↓</span>';
    return '';
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
    let sortedData = [...data];
    
    if (todayFilterActive) {
        const today = getTodayDateString();
        sortedData = sortedData.filter(m => {
            const matchDate = extractDateOnly(m.date);
            return matchDate === today;
        });
    }
    
    return sortedData.sort((a, b) => {
        let valA, valB;
        const d1 = a.details || {};
        const d2 = b.details || {};
        
        switch (currentSortColumn) {
            case 'date':
                valA = parseDate(a.date);
                valB = parseDate(b.date);
                break;
            case 'league':
                valA = (a.league || '').toLowerCase();
                valB = (b.league || '').toLowerCase();
                break;
            case 'match':
                valA = (a.home_team || '').toLowerCase();
                valB = (b.home_team || '').toLowerCase();
                break;
            case 'sel1':
                if (currentMarket.includes('1x2')) {
                    valA = parseFloat(d1.Odds1 || d1['1'] || 0);
                    valB = parseFloat(d2.Odds1 || d2['1'] || 0);
                } else if (currentMarket.includes('ou25')) {
                    valA = parseFloat(d1.Under || 0);
                    valB = parseFloat(d2.Under || 0);
                } else if (currentMarket.includes('btts')) {
                    valA = parseFloat(d1.Yes || 0);
                    valB = parseFloat(d2.Yes || 0);
                }
                break;
            case 'selX':
                valA = parseFloat(d1.OddsX || d1['X'] || 0);
                valB = parseFloat(d2.OddsX || d2['X'] || 0);
                break;
            case 'sel2':
                if (currentMarket.includes('1x2')) {
                    valA = parseFloat(d1.Odds2 || d1['2'] || 0);
                    valB = parseFloat(d2.Odds2 || d2['2'] || 0);
                } else if (currentMarket.includes('ou25')) {
                    valA = parseFloat(d1.Over || 0);
                    valB = parseFloat(d2.Over || 0);
                } else if (currentMarket.includes('btts')) {
                    valA = parseFloat(d1.No || 0);
                    valB = parseFloat(d2.No || 0);
                }
                break;
            case 'volume':
                valA = parseVolume(a);
                valB = parseVolume(b);
                break;
            default:
                valA = parseDate(a.date);
                valB = parseDate(b.date);
        }
        
        if (typeof valA === 'string' && typeof valB === 'string') {
            if (currentSortDirection === 'asc') {
                return valA.localeCompare(valB);
            } else {
                return valB.localeCompare(valA);
            }
        } else {
            if (currentSortDirection === 'asc') {
                return valA - valB;
            } else {
                return valB - valA;
            }
        }
    });
}

function getTodayDateString() {
    const now = new Date();
    const day = String(now.getDate()).padStart(2, '0');
    const month = String(now.getMonth() + 1).padStart(2, '0');
    const year = now.getFullYear();
    return `${day}.${month}.${year}`;
}

function extractDateOnly(dateStr) {
    if (!dateStr) return '';
    const parts = dateStr.match(/(\d{2})\.(\d{2})\.(\d{4})/);
    if (parts) {
        return `${parts[1]}.${parts[2]}.${parts[3]}`;
    }
    return '';
}

function sortByColumn(column) {
    if (currentSortColumn === column) {
        currentSortDirection = currentSortDirection === 'asc' ? 'desc' : 'asc';
    } else {
        currentSortColumn = column;
        currentSortDirection = 'desc';
    }
    
    updateTableHeaders();
    filteredMatches = applySorting(matches);
    renderMatches(filteredMatches);
}

function toggleTodayFilter() {
    todayFilterActive = !todayFilterActive;
    
    const btn = document.getElementById('todayBtn');
    if (btn) {
        if (todayFilterActive) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    }
    
    const searchInput = document.getElementById('searchInput');
    const query = searchInput?.value?.toLowerCase() || '';
    filterMatches(query);
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


let previousOddsData = null;

function openMatchModal(index) {
    const dataSource = filteredMatches.length > 0 ? filteredMatches : matches;
    if (index >= 0 && index < dataSource.length) {
        selectedMatch = dataSource[index];
        selectedChartMarket = currentMarket;
        previousOddsData = null;
        
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
        loadChartWithTrends(selectedMatch.home_team, selectedMatch.away_team, selectedChartMarket);
    }
}

async function loadChartWithTrends(home, away, market) {
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
        
        if (data.history && data.history.length >= 2) {
            previousOddsData = data.history[data.history.length - 2];
        } else {
            previousOddsData = null;
        }
        
        updateMatchInfoCard();
        
        loadChart(home, away, market);
    } catch (e) {
        console.error('Error loading chart with trends:', e);
        loadChart(home, away, market);
    }
}

function updateMatchInfoCard() {
    const card = document.getElementById('matchInfoCard');
    const d = selectedMatch.details || {};
    const p = previousOddsData || {};
    const isMoneyway = selectedChartMarket.startsWith('moneyway');
    const isDropping = selectedChartMarket.startsWith('dropping');
    
    let html = '';
    
    if (selectedChartMarket.includes('1x2')) {
        const trend1 = isDropping ? getTrendArrow(d.Odds1 || d['1'], p.Odds1 || p['1']) : '';
        const trendX = isDropping ? getTrendArrow(d.OddsX || d['X'], p.OddsX || p['X']) : '';
        const trend2 = isDropping ? getTrendArrow(d.Odds2 || d['2'], p.Odds2 || p['2']) : '';
        
        if (isMoneyway) {
            const c1 = getColorClass(d.Pct1);
            const cX = getColorClass(d.PctX);
            const c2 = getColorClass(d.Pct2);
            html = `
                <table style="width:100%;border-collapse:separate;border-spacing:10px 0;">
                    <tr>
                        <td style="width:33%;vertical-align:top;text-align:center;padding:16px;background:#0f1419;border-radius:10px;">
                            <div style="font-size:16px;font-weight:700;color:#fff;margin-bottom:16px;padding-bottom:10px;border-bottom:1px solid #2f3336;">1</div>
                            <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #2f3336;">
                                <span style="font-size:12px;color:#8899a6;">Odds</span>
                                <span style="font-family:'JetBrains Mono',monospace;font-size:18px;font-weight:700;color:#4ade80;">${formatOdds(d.Odds1 || d['1'])}</span>
                            </div>
                            <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #2f3336;">
                                <span style="font-size:12px;color:#8899a6;">Stake</span>
                                <span class="money ${c1}" style="font-family:'JetBrains Mono',monospace;font-size:14px;">${d.Amt1 || '-'}</span>
                            </div>
                            <div style="display:flex;justify-content:space-between;padding:8px 0;">
                                <span style="font-size:12px;color:#8899a6;">%</span>
                                <span class="pct ${c1}" style="font-family:'JetBrains Mono',monospace;font-size:15px;font-weight:700;">${formatPct(d.Pct1)}%</span>
                            </div>
                        </td>
                        <td style="width:33%;vertical-align:top;text-align:center;padding:16px;background:#0f1419;border-radius:10px;">
                            <div style="font-size:16px;font-weight:700;color:#fff;margin-bottom:16px;padding-bottom:10px;border-bottom:1px solid #2f3336;">X</div>
                            <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #2f3336;">
                                <span style="font-size:12px;color:#8899a6;">Odds</span>
                                <span style="font-family:'JetBrains Mono',monospace;font-size:18px;font-weight:700;color:#4ade80;">${formatOdds(d.OddsX || d['X'])}</span>
                            </div>
                            <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #2f3336;">
                                <span style="font-size:12px;color:#8899a6;">Stake</span>
                                <span class="money ${cX}" style="font-family:'JetBrains Mono',monospace;font-size:14px;">${d.AmtX || '-'}</span>
                            </div>
                            <div style="display:flex;justify-content:space-between;padding:8px 0;">
                                <span style="font-size:12px;color:#8899a6;">%</span>
                                <span class="pct ${cX}" style="font-family:'JetBrains Mono',monospace;font-size:15px;font-weight:700;">${formatPct(d.PctX)}%</span>
                            </div>
                        </td>
                        <td style="width:33%;vertical-align:top;text-align:center;padding:16px;background:#0f1419;border-radius:10px;">
                            <div style="font-size:16px;font-weight:700;color:#fff;margin-bottom:16px;padding-bottom:10px;border-bottom:1px solid #2f3336;">2</div>
                            <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #2f3336;">
                                <span style="font-size:12px;color:#8899a6;">Odds</span>
                                <span style="font-family:'JetBrains Mono',monospace;font-size:18px;font-weight:700;color:#4ade80;">${formatOdds(d.Odds2 || d['2'])}</span>
                            </div>
                            <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #2f3336;">
                                <span style="font-size:12px;color:#8899a6;">Stake</span>
                                <span class="money ${c2}" style="font-family:'JetBrains Mono',monospace;font-size:14px;">${d.Amt2 || '-'}</span>
                            </div>
                            <div style="display:flex;justify-content:space-between;padding:8px 0;">
                                <span style="font-size:12px;color:#8899a6;">%</span>
                                <span class="pct ${c2}" style="font-family:'JetBrains Mono',monospace;font-size:15px;font-weight:700;">${formatPct(d.Pct2)}%</span>
                            </div>
                        </td>
                    </tr>
                </table>
                <div style="display:flex;justify-content:space-between;align-items:center;margin-top:16px;padding:14px 20px;background:#0f1419;border-radius:10px;border:1px solid #2f3336;">
                    <span style="font-size:12px;color:#8899a6;text-transform:uppercase;font-weight:600;">Total Volume</span>
                    <span style="font-family:'JetBrains Mono',monospace;font-size:18px;font-weight:700;color:#4ade80;">${d.Volume || '-'}</span>
                </div>
            `;
        } else {
            html = `
                <div class="info-columns">
                    <div class="info-column">
                        <div class="column-header">1</div>
                        <div class="column-row">
                            <span class="row-label">Odds</span>
                            <span class="row-value odds">${formatOdds(d.Odds1 || d['1'])}${trend1}</span>
                        </div>
                    </div>
                    <div class="info-column">
                        <div class="column-header">X</div>
                        <div class="column-row">
                            <span class="row-label">Odds</span>
                            <span class="row-value odds">${formatOdds(d.OddsX || d['X'])}${trendX}</span>
                        </div>
                    </div>
                    <div class="info-column">
                        <div class="column-header">2</div>
                        <div class="column-row">
                            <span class="row-label">Odds</span>
                            <span class="row-value odds">${formatOdds(d.Odds2 || d['2'])}${trend2}</span>
                        </div>
                    </div>
                </div>
                <div class="volume-bar">
                    <span class="volume-label">Volume</span>
                    <span class="volume-value">${d.Volume || '-'}</span>
                </div>
            `;
        }
    } else if (selectedChartMarket.includes('ou25')) {
        const trendUnder = isDropping ? getTrendArrow(d.Under, p.Under) : '';
        const trendOver = isDropping ? getTrendArrow(d.Over, p.Over) : '';
        
        if (isMoneyway) {
            const cU = getColorClass(d.PctUnder);
            const cO = getColorClass(d.PctOver);
            html = `
                <div class="info-columns">
                    <div class="info-column">
                        <div class="column-header">Under 2.5</div>
                        <div class="column-row">
                            <span class="row-label">Odds</span>
                            <span class="row-value odds">${formatOdds(d.Under)}</span>
                        </div>
                        <div class="column-row">
                            <span class="row-label">Stake</span>
                            <span class="row-value money ${cU}">${d.AmtUnder || '-'}</span>
                        </div>
                        <div class="column-row">
                            <span class="row-label">%</span>
                            <span class="row-value pct ${cU}">${formatPct(d.PctUnder)}%</span>
                        </div>
                    </div>
                    <div class="info-column">
                        <div class="column-header">Over 2.5</div>
                        <div class="column-row">
                            <span class="row-label">Odds</span>
                            <span class="row-value odds">${formatOdds(d.Over)}</span>
                        </div>
                        <div class="column-row">
                            <span class="row-label">Stake</span>
                            <span class="row-value money ${cO}">${d.AmtOver || '-'}</span>
                        </div>
                        <div class="column-row">
                            <span class="row-label">%</span>
                            <span class="row-value pct ${cO}">${formatPct(d.PctOver)}%</span>
                        </div>
                    </div>
                </div>
                <div class="volume-bar">
                    <span class="volume-label">Total Volume</span>
                    <span class="volume-value">${d.Volume || '-'}</span>
                </div>
            `;
        } else {
            html = `
                <div class="info-columns">
                    <div class="info-column">
                        <div class="column-header">Under 2.5</div>
                        <div class="column-row">
                            <span class="row-label">Odds</span>
                            <span class="row-value odds">${formatOdds(d.Under)}${trendUnder}</span>
                        </div>
                    </div>
                    <div class="info-column">
                        <div class="column-header">Over 2.5</div>
                        <div class="column-row">
                            <span class="row-label">Odds</span>
                            <span class="row-value odds">${formatOdds(d.Over)}${trendOver}</span>
                        </div>
                    </div>
                </div>
                <div class="volume-bar">
                    <span class="volume-label">Volume</span>
                    <span class="volume-value">${d.Volume || '-'}</span>
                </div>
            `;
        }
    } else if (selectedChartMarket.includes('btts')) {
        const trendYes = isDropping ? getTrendArrow(d.Yes, p.Yes) : '';
        const trendNo = isDropping ? getTrendArrow(d.No, p.No) : '';
        
        if (isMoneyway) {
            const cY = getColorClass(d.PctYes);
            const cN = getColorClass(d.PctNo);
            html = `
                <div class="info-columns">
                    <div class="info-column">
                        <div class="column-header">Yes</div>
                        <div class="column-row">
                            <span class="row-label">Odds</span>
                            <span class="row-value odds">${formatOdds(d.Yes)}</span>
                        </div>
                        <div class="column-row">
                            <span class="row-label">Stake</span>
                            <span class="row-value money ${cY}">${d.AmtYes || '-'}</span>
                        </div>
                        <div class="column-row">
                            <span class="row-label">%</span>
                            <span class="row-value pct ${cY}">${formatPct(d.PctYes)}%</span>
                        </div>
                    </div>
                    <div class="info-column">
                        <div class="column-header">No</div>
                        <div class="column-row">
                            <span class="row-label">Odds</span>
                            <span class="row-value odds">${formatOdds(d.No)}</span>
                        </div>
                        <div class="column-row">
                            <span class="row-label">Stake</span>
                            <span class="row-value money ${cN}">${d.AmtNo || '-'}</span>
                        </div>
                        <div class="column-row">
                            <span class="row-label">%</span>
                            <span class="row-value pct ${cN}">${formatPct(d.PctNo)}%</span>
                        </div>
                    </div>
                </div>
                <div class="volume-bar">
                    <span class="volume-label">Total Volume</span>
                    <span class="volume-value">${d.Volume || '-'}</span>
                </div>
            `;
        } else {
            html = `
                <div class="info-columns">
                    <div class="info-column">
                        <div class="column-header">Yes</div>
                        <div class="column-row">
                            <span class="row-label">Odds</span>
                            <span class="row-value odds">${formatOdds(d.Yes)}${trendYes}</span>
                        </div>
                    </div>
                    <div class="info-column">
                        <div class="column-header">No</div>
                        <div class="column-row">
                            <span class="row-label">Odds</span>
                            <span class="row-value odds">${formatOdds(d.No)}${trendNo}</span>
                        </div>
                    </div>
                </div>
                <div class="volume-bar">
                    <span class="volume-label">Volume</span>
                    <span class="volume-value">${d.Volume || '-'}</span>
                </div>
            `;
        }
    }
    
    card.innerHTML = html;
}

function getTrendArrow(current, previous) {
    if (!current || !previous) return '';
    const curr = parseFloat(String(current).replace(/[^0-9.]/g, ''));
    const prev = parseFloat(String(previous).replace(/[^0-9.]/g, ''));
    if (isNaN(curr) || isNaN(prev)) return '';
    if (curr > prev) return '<span class="trend-up">↑</span>';
    if (curr < prev) return '<span class="trend-down">↓</span>';
    return '';
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
        
        const filteredHistory = filterHistoryByTimeRange(data.history);
        
        const timeBlocks = {};
        filteredHistory.forEach(h => {
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
                    const label = ['1', 'X', '2'][idx];
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
                    const label = ['Under', 'Over'][idx];
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
                    const label = ['Yes', 'No'][idx];
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
        
        renderChartLegendFilters(datasets, market);
        
        datasets.forEach((ds, idx) => {
            const key = `${market}_${ds.label}`;
            if (chartVisibleSeries[key] === undefined) {
                chartVisibleSeries[key] = true;
            }
            ds.hidden = !chartVisibleSeries[key];
        });
        
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
                        display: false
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
                                            lines.push(`Change: ${changeStr} ↑`);
                                        } else {
                                            lines.push(`Change: ${changeStr} ↓`);
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

function renderChartLegendFilters(datasets, market) {
    const container = document.getElementById('chartLegendFilters');
    if (!container) return;
    
    const legendLabels = {
        'moneyway_1x2': [
            { key: '1', label: '1', color: '#3b82f6' },
            { key: 'X', label: 'X', color: '#22c55e' },
            { key: '2', label: '2', color: '#eab308' }
        ],
        'moneyway_ou25': [
            { key: 'Under', label: 'Under 2.5', color: '#3b82f6' },
            { key: 'Over', label: 'Over 2.5', color: '#22c55e' }
        ],
        'moneyway_btts': [
            { key: 'Yes', label: 'BTTS Yes', color: '#22c55e' },
            { key: 'No', label: 'BTTS No', color: '#ef4444' }
        ],
        'dropping_1x2': [
            { key: '1', label: '1', color: '#3b82f6' },
            { key: 'X', label: 'X', color: '#22c55e' },
            { key: '2', label: '2', color: '#eab308' }
        ],
        'dropping_ou25': [
            { key: 'Under', label: 'Under 2.5', color: '#3b82f6' },
            { key: 'Over', label: 'Over 2.5', color: '#22c55e' }
        ],
        'dropping_btts': [
            { key: 'Yes', label: 'BTTS Yes', color: '#22c55e' },
            { key: 'No', label: 'BTTS No', color: '#ef4444' }
        ]
    };
    
    const items = legendLabels[market] || [];
    
    const timeRanges = [
        { key: '10min', label: '10 dk' },
        { key: '30min', label: '30 dk' },
        { key: '1hour', label: '1 saat' },
        { key: '6hour', label: '6 saat' },
        { key: '12hour', label: '12 saat' },
        { key: '1day', label: '1 gün' }
    ];
    
    const seriesButtons = items.map(item => {
        const stateKey = `${market}_${item.key}`;
        const isActive = chartVisibleSeries[stateKey] !== false;
        const activeClass = isActive ? 'active' : 'inactive';
        
        return `
            <button class="chart-legend-btn ${activeClass}" 
                    style="--legend-color: ${item.color};"
                    onclick="toggleChartSeries('${market}', '${item.key}', this)">
                <span class="legend-color-dot"></span>
                <span>${item.label}</span>
            </button>
        `;
    }).join('');
    
    const timeButtons = timeRanges.map(tr => {
        const isActive = chartTimeRange === tr.key;
        return `
            <button class="chart-time-btn ${isActive ? 'active' : ''}" 
                    data-range="${tr.key}"
                    onclick="setChartTimeRange('${tr.key}')">
                ${tr.label}
            </button>
        `;
    }).join('');
    
    container.innerHTML = `
        <div class="chart-filter-group series-filters">
            ${seriesButtons}
        </div>
        <div class="chart-filter-divider"></div>
        <div class="chart-filter-group time-filters">
            ${timeButtons}
        </div>
    `;
}

function setChartTimeRange(range) {
    chartTimeRange = range;
    
    document.querySelectorAll('.chart-time-btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.range === range) {
            btn.classList.add('active');
        }
    });
    
    if (selectedMatch) {
        loadChart(selectedMatch.home_team, selectedMatch.away_team, selectedChartMarket);
    }
}

function filterHistoryByTimeRange(historyData) {
    if (!historyData || historyData.length === 0) return historyData;
    
    const now = new Date();
    let cutoffTime;
    
    switch (chartTimeRange) {
        case '10min':
            cutoffTime = new Date(now.getTime() - 10 * 60 * 1000);
            break;
        case '30min':
            cutoffTime = new Date(now.getTime() - 30 * 60 * 1000);
            break;
        case '1hour':
            cutoffTime = new Date(now.getTime() - 60 * 60 * 1000);
            break;
        case '6hour':
            cutoffTime = new Date(now.getTime() - 6 * 60 * 60 * 1000);
            break;
        case '12hour':
            cutoffTime = new Date(now.getTime() - 12 * 60 * 60 * 1000);
            break;
        case '1day':
        default:
            cutoffTime = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 0, 0, 0);
            break;
    }
    
    return historyData.filter(h => {
        const ts = h.ScrapedAt || '';
        let date;
        try {
            date = new Date(ts);
        } catch {
            return true;
        }
        return date >= cutoffTime;
    });
}

function toggleChartSeries(market, seriesKey, btn) {
    const stateKey = `${market}_${seriesKey}`;
    
    chartVisibleSeries[stateKey] = !chartVisibleSeries[stateKey];
    
    if (btn) {
        if (chartVisibleSeries[stateKey]) {
            btn.classList.remove('inactive');
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
            btn.classList.add('inactive');
        }
    }
    
    if (chart) {
        const datasetIndex = chart.data.datasets.findIndex(ds => ds.label === seriesKey);
        if (datasetIndex !== -1) {
            chart.data.datasets[datasetIndex].hidden = !chartVisibleSeries[stateKey];
            chart.update();
        }
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
