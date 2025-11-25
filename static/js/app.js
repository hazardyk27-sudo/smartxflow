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
let chartTimeRange = '5min';
let currentChartHistoryData = [];


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
        matches = apiMatches || [];
        filteredMatches = applySorting(matches);
        renderMatches(filteredMatches);
    } catch (error) {
        console.error('Error loading matches:', error);
        matches = [];
        filteredMatches = [];
        renderMatches([]);
    }
}

function updateTableHeaders() {
    const table = document.querySelector('.matches-table');
    const thead = document.querySelector('.matches-table thead tr');
    const colgroup = document.querySelector('.matches-table colgroup');
    if (!thead || !table) return;
    
    const getArrow = (col) => {
        if (currentSortColumn === col) {
            return currentSortDirection === 'asc' ? '↑' : '↓';
        }
        return '';
    };
    
    const getActiveClass = (col) => currentSortColumn === col ? 'active' : '';
    
    if (currentMarket.includes('1x2')) {
        table.setAttribute('data-selection-count', '3');
        if (colgroup) {
            colgroup.innerHTML = `
                <col class="col-date">
                <col class="col-league">
                <col class="col-match">
                <col class="col-selection">
                <col class="col-selection">
                <col class="col-selection">
                <col class="col-volume">
            `;
        }
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
        table.setAttribute('data-selection-count', '2');
        if (colgroup) {
            colgroup.innerHTML = `
                <col class="col-date">
                <col class="col-league">
                <col class="col-match">
                <col class="col-selection">
                <col class="col-selection">
                <col class="col-volume">
            `;
        }
        thead.innerHTML = `
            <th class="col-date sortable ${getActiveClass('date')}" data-sort="date" onclick="sortByColumn('date')">DATE <span class="sort-arrow">${getArrow('date')}</span></th>
            <th class="col-league sortable ${getActiveClass('league')}" data-sort="league" onclick="sortByColumn('league')">LEAGUE <span class="sort-arrow">${getArrow('league')}</span></th>
            <th class="col-match sortable ${getActiveClass('match')}" data-sort="match" onclick="sortByColumn('match')">MATCH <span class="sort-arrow">${getArrow('match')}</span></th>
            <th class="col-selection sortable ${getActiveClass('sel1')}" data-sort="sel1" onclick="sortByColumn('sel1')">UNDER <span class="sort-arrow">${getArrow('sel1')}</span></th>
            <th class="col-selection sortable ${getActiveClass('sel2')}" data-sort="sel2" onclick="sortByColumn('sel2')">OVER <span class="sort-arrow">${getArrow('sel2')}</span></th>
            <th class="col-volume sortable ${getActiveClass('volume')}" data-sort="volume" onclick="sortByColumn('volume')">VOLUME <span class="sort-arrow">${getArrow('volume')}</span></th>
        `;
    } else if (currentMarket.includes('btts')) {
        table.setAttribute('data-selection-count', '2');
        if (colgroup) {
            colgroup.innerHTML = `
                <col class="col-date">
                <col class="col-league">
                <col class="col-match">
                <col class="col-selection">
                <col class="col-selection">
                <col class="col-volume">
            `;
        }
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
        const d = match.details || match.odds || {};
        
        if (currentMarket.includes('1x2')) {
            const trend1 = isDropping ? (getDirectTrendArrow(d.Trend1) || getTableTrendArrow(d.Odds1 || d['1'], d.PrevOdds1)) : '';
            const trendX = isDropping ? (getDirectTrendArrow(d.TrendX) || getTableTrendArrow(d.OddsX || d['X'], d.PrevOddsX)) : '';
            const trend2 = isDropping ? (getDirectTrendArrow(d.Trend2) || getTableTrendArrow(d.Odds2 || d['2'], d.PrevOdds2)) : '';
            
            if (isMoneyway) {
                const c1 = getColorClass(d.Pct1);
                const cX = getColorClass(d.PctX);
                const c2 = getColorClass(d.Pct2);
                return `
                    <tr data-index="${idx}" onclick="openMatchModal(${idx})">
                        <td class="match-date">${match.date || '-'}</td>
                        <td class="match-league" title="${match.league || ''}">${match.league || '-'}</td>
                        <td class="match-teams">${match.home_team}<span class="vs">-</span>${match.away_team}</td>
                        <td class="selection-cell"><div>
                            <div class="selection-odds">${formatOdds(d.Odds1 || d['1'])}</div>
                            ${d.Amt1 ? `<div class="selection-money ${c1}">${d.Amt1}</div>` : ''}
                            ${d.Pct1 ? `<div class="selection-pct ${c1}">${d.Pct1}%</div>` : ''}
                        </div></td>
                        <td class="selection-cell"><div>
                            <div class="selection-odds">${formatOdds(d.OddsX || d['X'])}</div>
                            ${d.AmtX ? `<div class="selection-money ${cX}">${d.AmtX}</div>` : ''}
                            ${d.PctX ? `<div class="selection-pct ${cX}">${d.PctX}%</div>` : ''}
                        </div></td>
                        <td class="selection-cell"><div>
                            <div class="selection-odds">${formatOdds(d.Odds2 || d['2'])}</div>
                            ${d.Amt2 ? `<div class="selection-money ${c2}">${d.Amt2}</div>` : ''}
                            ${d.Pct2 ? `<div class="selection-pct ${c2}">${d.Pct2}%</div>` : ''}
                        </div></td>
                        <td class="volume-cell">${formatVolume(d.Volume)}</td>
                    </tr>
                `;
            } else {
                return `
                    <tr data-index="${idx}" onclick="openMatchModal(${idx})">
                        <td class="match-date">${match.date || '-'}</td>
                        <td class="match-league" title="${match.league || ''}">${match.league || '-'}</td>
                        <td class="match-teams">${match.home_team}<span class="vs">-</span>${match.away_team}</td>
                        <td class="selection-cell"><div>
                            <div class="selection-odds drop-odds">${formatOdds(d.Odds1 || d['1'])}${trend1}</div>
                        </div></td>
                        <td class="selection-cell"><div>
                            <div class="selection-odds drop-odds">${formatOdds(d.OddsX || d['X'])}${trendX}</div>
                        </div></td>
                        <td class="selection-cell"><div>
                            <div class="selection-odds drop-odds">${formatOdds(d.Odds2 || d['2'])}${trend2}</div>
                        </div></td>
                        <td class="volume-cell">${formatVolume(d.Volume)}</td>
                    </tr>
                `;
            }
        } else if (currentMarket.includes('ou25')) {
            const trendUnder = isDropping ? (getDirectTrendArrow(d.TrendUnder) || getTableTrendArrow(d.Under, d.PrevUnder)) : '';
            const trendOver = isDropping ? (getDirectTrendArrow(d.TrendOver) || getTableTrendArrow(d.Over, d.PrevOver)) : '';
            
            if (isMoneyway) {
                const cU = getColorClass(d.PctUnder);
                const cO = getColorClass(d.PctOver);
                return `
                    <tr data-index="${idx}" onclick="openMatchModal(${idx})">
                        <td class="match-date">${match.date || '-'}</td>
                        <td class="match-league" title="${match.league || ''}">${match.league || '-'}</td>
                        <td class="match-teams">${match.home_team}<span class="vs">-</span>${match.away_team}</td>
                        <td class="selection-cell"><div>
                            <div class="selection-odds">${formatOdds(d.Under)}</div>
                            ${d.AmtUnder ? `<div class="selection-money ${cU}">${d.AmtUnder}</div>` : ''}
                            ${d.PctUnder ? `<div class="selection-pct ${cU}">${d.PctUnder}%</div>` : ''}
                        </div></td>
                        <td class="selection-cell"><div>
                            <div class="selection-odds">${formatOdds(d.Over)}</div>
                            ${d.AmtOver ? `<div class="selection-money ${cO}">${d.AmtOver}</div>` : ''}
                            ${d.PctOver ? `<div class="selection-pct ${cO}">${d.PctOver}%</div>` : ''}
                        </div></td>
                        <td class="volume-cell">${formatVolume(d.Volume)}</td>
                    </tr>
                `;
            } else {
                return `
                    <tr data-index="${idx}" onclick="openMatchModal(${idx})">
                        <td class="match-date">${match.date || '-'}</td>
                        <td class="match-league" title="${match.league || ''}">${match.league || '-'}</td>
                        <td class="match-teams">${match.home_team}<span class="vs">-</span>${match.away_team}</td>
                        <td class="selection-cell"><div>
                            <div class="selection-odds drop-odds">${formatOdds(d.Under)}${trendUnder}</div>
                        </div></td>
                        <td class="selection-cell"><div>
                            <div class="selection-odds drop-odds">${formatOdds(d.Over)}${trendOver}</div>
                        </div></td>
                        <td class="volume-cell">${formatVolume(d.Volume)}</td>
                    </tr>
                `;
            }
        } else {
            const trendYes = isDropping ? (getDirectTrendArrow(d.TrendYes) || getTableTrendArrow(d.OddsYes || d.Yes, d.PrevYes)) : '';
            const trendNo = isDropping ? (getDirectTrendArrow(d.TrendNo) || getTableTrendArrow(d.OddsNo || d.No, d.PrevNo)) : '';
            
            if (isMoneyway) {
                const cY = getColorClass(d.PctYes);
                const cN = getColorClass(d.PctNo);
                return `
                    <tr data-index="${idx}" onclick="openMatchModal(${idx})">
                        <td class="match-date">${match.date || '-'}</td>
                        <td class="match-league" title="${match.league || ''}">${match.league || '-'}</td>
                        <td class="match-teams">${match.home_team}<span class="vs">-</span>${match.away_team}</td>
                        <td class="selection-cell"><div>
                            <div class="selection-odds">${formatOdds(d.OddsYes || d.Yes)}</div>
                            ${d.AmtYes ? `<div class="selection-money ${cY}">${d.AmtYes}</div>` : ''}
                            ${d.PctYes ? `<div class="selection-pct ${cY}">${d.PctYes}%</div>` : ''}
                        </div></td>
                        <td class="selection-cell"><div>
                            <div class="selection-odds">${formatOdds(d.OddsNo || d.No)}</div>
                            ${d.AmtNo ? `<div class="selection-money ${cN}">${d.AmtNo}</div>` : ''}
                            ${d.PctNo ? `<div class="selection-pct ${cN}">${d.PctNo}%</div>` : ''}
                        </div></td>
                        <td class="volume-cell">${formatVolume(d.Volume)}</td>
                    </tr>
                `;
            } else {
                return `
                    <tr data-index="${idx}" onclick="openMatchModal(${idx})">
                        <td class="match-date">${match.date || '-'}</td>
                        <td class="match-league" title="${match.league || ''}">${match.league || '-'}</td>
                        <td class="match-teams">${match.home_team}<span class="vs">-</span>${match.away_team}</td>
                        <td class="selection-cell"><div>
                            <div class="selection-odds drop-odds">${formatOdds(d.OddsYes || d.Yes)}${trendYes}</div>
                        </div></td>
                        <td class="selection-cell"><div>
                            <div class="selection-odds drop-odds">${formatOdds(d.OddsNo || d.No)}${trendNo}</div>
                        </div></td>
                        <td class="volume-cell">${formatVolume(d.Volume)}</td>
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
    const diff = Math.abs(curr - prev);
    if (diff < 0.001) return '';
    if (curr > prev) return '<span class="trend-up">↑</span>';
    if (curr < prev) return '<span class="trend-down">↓</span>';
    return '';
}

function getDirectTrendArrow(trendValue) {
    if (!trendValue) return '';
    const t = String(trendValue).trim();
    if (t === '↑' || t.includes('↑')) return '<span class="trend-up">↑</span>';
    if (t === '↓' || t.includes('↓')) return '<span class="trend-down">↓</span>';
    return '';
}

function formatOdds(value) {
    if (!value || value === '-') return '-';
    const str = String(value);
    const firstLine = str.split('\n')[0];
    const num = parseFloat(firstLine);
    return isNaN(num) ? firstLine : num.toFixed(2);
}

function formatVolume(value) {
    if (!value || value === '-') return '-';
    const num = parseInt(String(value).replace(/[^0-9]/g, ''));
    if (isNaN(num)) return '-';
    return '£' + num.toLocaleString('en-GB');
}

function hasValidMarketData(match, market) {
    const d = match.details || match.odds || {};
    
    if (market.includes('1x2')) {
        const odds1 = d.Odds1 || d['1'];
        const oddsX = d.OddsX || d['X'];
        const odds2 = d.Odds2 || d['2'];
        return isValidOdds(odds1) || isValidOdds(oddsX) || isValidOdds(odds2);
    } else if (market.includes('ou25')) {
        const under = d.Under;
        const over = d.Over;
        return isValidOdds(under) || isValidOdds(over);
    } else if (market.includes('btts')) {
        const yes = d.OddsYes || d.Yes;
        const no = d.OddsNo || d.No;
        return isValidOdds(yes) || isValidOdds(no);
    }
    return false;
}

function isValidOdds(value) {
    if (!value || value === '-' || value === '') return false;
    const num = parseFloat(String(value).replace(/[^0-9.]/g, ''));
    return !isNaN(num) && num > 0;
}

function filterMatches(query) {
    let filtered = [...matches];
    
    filtered = filtered.filter(m => hasValidMarketData(m, currentMarket));
    
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
    
    sortedData = sortedData.filter(m => hasValidMarketData(m, currentMarket));
    
    if (todayFilterActive) {
        const today = getTodayDateString();
        sortedData = sortedData.filter(m => {
            const matchDate = extractDateOnly(m.date);
            return matchDate === today;
        });
    }
    
    return sortedData.sort((a, b) => {
        let valA, valB;
        const d1 = a.details || a.odds || {};
        const d2 = b.details || b.odds || {};
        
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
    return `${year}-${month}-${day}`;
}

function extractDateOnly(dateStr) {
    if (!dateStr) return '';
    
    const ddmmyyyy = dateStr.match(/(\d{2})\.(\d{2})\.(\d{4})/);
    if (ddmmyyyy) {
        return `${ddmmyyyy[3]}-${ddmmyyyy[2]}-${ddmmyyyy[1]}`;
    }
    
    const yyyymmdd = dateStr.match(/(\d{4})-(\d{2})-(\d{2})/);
    if (yyyymmdd) {
        return `${yyyymmdd[1]}-${yyyymmdd[2]}-${yyyymmdd[3]}`;
    }
    
    const isoMatch = dateStr.match(/(\d{4})-(\d{2})-(\d{2})T/);
    if (isoMatch) {
        return `${isoMatch[1]}-${isoMatch[2]}-${isoMatch[3]}`;
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
    const d = match.odds || match.details || {};
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
    const d = selectedMatch.odds || selectedMatch.details || {};
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
                    <span style="font-family:'JetBrains Mono',monospace;font-size:18px;font-weight:700;color:#4ade80;">${formatVolume(d.Volume)}</span>
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
                    <span class="volume-value">${formatVolume(d.Volume)}</span>
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
                    <span class="volume-value">${formatVolume(d.Volume)}</span>
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
                    <span class="volume-value">${formatVolume(d.Volume)}</span>
                </div>
            `;
        }
    } else if (selectedChartMarket.includes('btts')) {
        const trendYes = isDropping ? getTrendArrow(d.OddsYes || d.Yes, p.OddsYes || p.Yes) : '';
        const trendNo = isDropping ? getTrendArrow(d.OddsNo || d.No, p.OddsNo || p.No) : '';
        
        if (isMoneyway) {
            const cY = getColorClass(d.PctYes);
            const cN = getColorClass(d.PctNo);
            html = `
                <div class="info-columns">
                    <div class="info-column">
                        <div class="column-header">Yes</div>
                        <div class="column-row">
                            <span class="row-label">Odds</span>
                            <span class="row-value odds">${formatOdds(d.OddsYes || d.Yes)}</span>
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
                            <span class="row-value odds">${formatOdds(d.OddsNo || d.No)}</span>
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
                    <span class="volume-value">${formatVolume(d.Volume)}</span>
                </div>
            `;
        } else {
            html = `
                <div class="info-columns">
                    <div class="info-column">
                        <div class="column-header">Yes</div>
                        <div class="column-row">
                            <span class="row-label">Odds</span>
                            <span class="row-value odds">${formatOdds(d.OddsYes || d.Yes)}${trendYes}</span>
                        </div>
                    </div>
                    <div class="info-column">
                        <div class="column-header">No</div>
                        <div class="column-row">
                            <span class="row-label">Odds</span>
                            <span class="row-value odds">${formatOdds(d.OddsNo || d.No)}${trendNo}</span>
                        </div>
                    </div>
                </div>
                <div class="volume-bar">
                    <span class="volume-label">Volume</span>
                    <span class="volume-value">${formatVolume(d.Volume)}</span>
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

function getBucketConfig() {
    switch (chartTimeRange) {
        case '5min':
            return { bucketMinutes: 5, labelFormat: 'time' };
        case '10min':
            return { bucketMinutes: 10, labelFormat: 'time' };
        case '30min':
            return { bucketMinutes: 30, labelFormat: 'time' };
        case '1hour':
            return { bucketMinutes: 60, labelFormat: 'time' };
        case '6hour':
            return { bucketMinutes: 360, labelFormat: 'datetime' };
        case '12hour':
            return { bucketMinutes: 720, labelFormat: 'datetime' };
        case '1day':
        default:
            return { bucketMinutes: 1440, labelFormat: 'date' };
    }
}

function roundToBucket(timestamp) {
    const date = new Date(timestamp);
    const config = getBucketConfig();
    const bucketMs = config.bucketMinutes * 60 * 1000;
    const roundedTime = Math.floor(date.getTime() / bucketMs) * bucketMs;
    return new Date(roundedTime);
}

function formatTimeLabel(date) {
    const config = getBucketConfig();
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const month = String(date.getMonth() + 1).padStart(2, '0');
    
    if (config.labelFormat === 'date') {
        return `${day}.${month}`;
    }
    if (config.labelFormat === 'datetime') {
        return `${day}.${month} ${hours}:${minutes}`;
    }
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
            console.log('No history data available');
        }
        
        if (!data.history) {
            data.history = [];
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
            const rounded = roundToBucket(date);
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
                        pointRadius: 3,
                        pointHoverRadius: 5,
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
                        pointRadius: 3,
                        pointHoverRadius: 5,
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
                        pointRadius: 3,
                        pointHoverRadius: 5,
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
                        pointRadius: 3,
                        pointHoverRadius: 5,
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
                        pointRadius: 3,
                        pointHoverRadius: 5,
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
                        pointRadius: 3,
                        pointHoverRadius: 5,
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
                                    const graphPointOdds = getOddsFromHistory(h, datasetLabel, market);
                                    const currentLatestOdds = getLatestOdds(latestData, datasetLabel.replace('%', ''), market);
                                    
                                    if (graphPointOdds > 0 && currentLatestOdds > 0 && graphPointOdds !== currentLatestOdds) {
                                        const pctChange = ((currentLatestOdds - graphPointOdds) / graphPointOdds) * 100;
                                        const changeSign = pctChange >= 0 ? '+' : '';
                                        const changeStr = `${changeSign}${pctChange.toFixed(1)}%`;
                                        const arrow = pctChange >= 0 ? '↑' : '↓';
                                        
                                        lines.push(`${datasetLabel}: ${graphPointOdds.toFixed(2)} → ${currentLatestOdds.toFixed(2)}`);
                                        lines.push(`Change vs Latest: ${changeStr} ${arrow}`);
                                    } else if (graphPointOdds > 0) {
                                        lines.push(`${datasetLabel}: ${graphPointOdds.toFixed(2)}`);
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
        { key: '5min', label: '5 dk' },
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
        <div class="chart-filter-divider"></div>
        <div class="chart-export-btns">
            <button class="chart-export-btn" onclick="exportChartPNG()">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                    <circle cx="8.5" cy="8.5" r="1.5"/>
                    <polyline points="21 15 16 10 5 21"/>
                </svg>
                PNG
            </button>
            <button class="chart-export-btn" onclick="exportChartCSV()">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                    <polyline points="7 10 12 15 17 10"/>
                    <line x1="12" y1="15" x2="12" y2="3"/>
                </svg>
                CSV
            </button>
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
    return historyData || [];
}

function generateExportFilename(extension) {
    const match = selectedMatch;
    if (!match) return `SmartXFlow_export.${extension}`;
    
    const now = new Date();
    const dateStr = now.getFullYear().toString() +
        String(now.getMonth() + 1).padStart(2, '0') +
        String(now.getDate()).padStart(2, '0') + '_' +
        String(now.getHours()).padStart(2, '0') +
        String(now.getMinutes()).padStart(2, '0');
    
    const league = (match.league || 'League').replace(/[^a-zA-Z0-9]/g, '');
    const home = (match.home_team || 'Home').replace(/[^a-zA-Z0-9]/g, '');
    const away = (match.away_team || 'Away').replace(/[^a-zA-Z0-9]/g, '');
    
    const marketMap = {
        'moneyway_1x2': 'MW1X2',
        'moneyway_ou25': 'MW25',
        'moneyway_btts': 'MWBTTS',
        'dropping_1x2': 'Drop1X2',
        'dropping_ou25': 'Drop25',
        'dropping_btts': 'DropBTTS'
    };
    const marketLabel = marketMap[selectedChartMarket] || 'Chart';
    
    return `SmartXFlow_${league}_${home}-${away}_${marketLabel}_${dateStr}.${extension}`;
}

function isEXEEnvironment() {
    return typeof window.pywebview !== 'undefined' || 
           window.location.protocol === 'file:' ||
           navigator.userAgent.toLowerCase().includes('pywebview');
}

function showExportNotification(message, isError = false) {
    const existing = document.querySelector('.export-notification');
    if (existing) existing.remove();
    
    const notification = document.createElement('div');
    notification.className = 'export-notification';
    notification.style.cssText = `
        position: fixed;
        bottom: 20px;
        right: 20px;
        padding: 12px 20px;
        background: ${isError ? '#dc2626' : '#22c55e'};
        color: white;
        border-radius: 8px;
        font-size: 14px;
        font-weight: 500;
        z-index: 10000;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        animation: slideIn 0.3s ease;
    `;
    notification.textContent = message;
    document.body.appendChild(notification);
    
    setTimeout(() => notification.remove(), 4000);
}

async function savePNGViaAPI(imageData, filename) {
    console.log('[PNG Export] Starting save, filename:', filename);
    console.log('[PNG Export] isEXE:', isEXEEnvironment());
    
    try {
        const response = await fetch('/api/export/png', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ image: imageData, filename: filename })
        });
        const result = await response.json();
        console.log('[PNG Export] API response:', result);
        
        if (result.success) {
            showExportNotification(`PNG kaydedildi: ${result.path}`);
            return true;
        } else {
            console.warn('[PNG Export] API failed:', result.error);
        }
    } catch (err) {
        console.error('[PNG Export] API error:', err);
    }
    
    console.log('[PNG Export] Falling back to browser download');
    try {
        const link = document.createElement('a');
        link.download = filename;
        link.href = imageData;
        link.style.display = 'none';
        document.body.appendChild(link);
        link.click();
        
        setTimeout(() => {
            document.body.removeChild(link);
        }, 100);
        
        showExportNotification('PNG indirildi');
        return true;
    } catch (downloadErr) {
        console.error('[PNG Export] Download error:', downloadErr);
        showExportNotification('PNG indirme hatası', true);
        return false;
    }
}

function exportChartPNG() {
    console.log('[PNG Export] exportChartPNG called');
    
    if (!selectedMatch) {
        console.error('[PNG Export] No match selected');
        showExportNotification('Maç bulunamadı', true);
        return;
    }
    
    const exportBtn = document.querySelector('.chart-export-btn');
    if (exportBtn) exportBtn.textContent = 'Exporting...';
    
    const resetButton = () => {
        if (exportBtn) {
            exportBtn.innerHTML = `
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                    <circle cx="8.5" cy="8.5" r="1.5"/>
                    <polyline points="21 15 16 10 5 21"/>
                </svg>
                PNG
            `;
        }
    };
    
    const filename = generateExportFilename('png');
    console.log('[PNG Export] Filename:', filename);
    
    const modalContent = document.querySelector('.modal-content');
    if (!modalContent) {
        console.error('[PNG Export] Modal content not found');
        showExportNotification('Modal bulunamadı', true);
        resetButton();
        return;
    }
    
    const closeBtn = document.querySelector('.modal-close');
    const exportBtns = document.querySelector('.chart-export-btns');
    if (closeBtn) closeBtn.style.visibility = 'hidden';
    if (exportBtns) exportBtns.style.visibility = 'hidden';
    
    const modalBody = document.querySelector('.modal-body');
    const originalStyles = {
        modalContent: {
            maxHeight: modalContent.style.maxHeight,
            height: modalContent.style.height,
            overflow: modalContent.style.overflow
        },
        modalBody: modalBody ? {
            maxHeight: modalBody.style.maxHeight,
            height: modalBody.style.height,
            overflow: modalBody.style.overflow
        } : null
    };
    
    modalContent.style.maxHeight = 'none';
    modalContent.style.height = 'auto';
    modalContent.style.overflow = 'visible';
    
    if (modalBody) {
        modalBody.style.maxHeight = 'none';
        modalBody.style.height = 'auto';
        modalBody.style.overflow = 'visible';
    }
    
    const restoreStyles = () => {
        modalContent.style.maxHeight = originalStyles.modalContent.maxHeight;
        modalContent.style.height = originalStyles.modalContent.height;
        modalContent.style.overflow = originalStyles.modalContent.overflow;
        if (modalBody && originalStyles.modalBody) {
            modalBody.style.maxHeight = originalStyles.modalBody.maxHeight;
            modalBody.style.height = originalStyles.modalBody.height;
            modalBody.style.overflow = originalStyles.modalBody.overflow;
        }
        if (closeBtn) closeBtn.style.visibility = '';
        if (exportBtns) exportBtns.style.visibility = '';
    };
    
    if (typeof html2canvas === 'undefined') {
        console.error('[PNG Export] html2canvas not loaded');
        restoreStyles();
        showExportNotification('PNG kütüphanesi yüklenemedi', true);
        resetButton();
        return;
    }
    
    console.log('[PNG Export] html2canvas available, starting capture...');
    
    setTimeout(() => {
        html2canvas(modalContent, {
            backgroundColor: '#15202b',
            scale: 2,
            useCORS: true,
            allowTaint: true,
            logging: true
        }).then(async canvas => {
            console.log('[PNG Export] Canvas created, size:', canvas.width, 'x', canvas.height);
            restoreStyles();
            const imageData = canvas.toDataURL('image/png');
            console.log('[PNG Export] Image data length:', imageData.length);
            await savePNGViaAPI(imageData, filename);
            resetButton();
        }).catch(err => {
            restoreStyles();
            console.error('[PNG Export] html2canvas error:', err);
            showExportNotification('PNG oluşturma hatası: ' + err.message, true);
            resetButton();
        });
    }, 100);
}

function exportChartPNGFallback(filename, resetButton) {
    const modalContent = document.querySelector('.modal-content');
    if (!modalContent) {
        showExportNotification('Modal bulunamadı', true);
        resetButton();
        return;
    }
    
    const closeBtn = document.querySelector('.modal-close');
    if (closeBtn) closeBtn.style.display = 'none';
    
    const modalBody = document.querySelector('.modal-body');
    const originalStyles = {
        modalContent: {
            maxHeight: modalContent.style.maxHeight,
            height: modalContent.style.height,
            overflow: modalContent.style.overflow
        },
        modalBody: modalBody ? {
            maxHeight: modalBody.style.maxHeight,
            height: modalBody.style.height,
            overflow: modalBody.style.overflow
        } : null
    };
    
    const fullHeight = modalContent.scrollHeight;
    modalContent.style.maxHeight = 'none';
    modalContent.style.height = fullHeight + 'px';
    modalContent.style.overflow = 'visible';
    
    if (modalBody) {
        modalBody.style.maxHeight = 'none';
        modalBody.style.height = 'auto';
        modalBody.style.overflow = 'visible';
    }
    
    const restoreStyles = () => {
        modalContent.style.maxHeight = originalStyles.modalContent.maxHeight;
        modalContent.style.height = originalStyles.modalContent.height;
        modalContent.style.overflow = originalStyles.modalContent.overflow;
        if (modalBody && originalStyles.modalBody) {
            modalBody.style.maxHeight = originalStyles.modalBody.maxHeight;
            modalBody.style.height = originalStyles.modalBody.height;
            modalBody.style.overflow = originalStyles.modalBody.overflow;
        }
        if (closeBtn) closeBtn.style.display = '';
    };
    
    if (typeof html2canvas === 'undefined') {
        restoreStyles();
        showExportNotification('PNG kütüphanesi yüklenemedi', true);
        resetButton();
        return;
    }
    
    setTimeout(() => {
        html2canvas(modalContent, {
            backgroundColor: '#161b22',
            scale: 2,
            logging: false,
            useCORS: true,
            allowTaint: true,
            height: modalContent.scrollHeight,
            windowHeight: modalContent.scrollHeight,
            scrollY: 0,
            scrollX: 0
        }).then(async canvas => {
            restoreStyles();
            
            const imageData = canvas.toDataURL('image/png', 1.0);
            const saved = await savePNGViaAPI(imageData, filename);
            
            if (!saved) {
                const link = document.createElement('a');
                link.download = filename;
                link.href = imageData;
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
                showExportNotification('PNG indirildi');
            }
            
            resetButton();
        }).catch(err => {
            restoreStyles();
            console.error('html2canvas error:', err);
            showExportNotification('PNG oluşturma hatası', true);
            resetButton();
        });
    }, 100);
}

function exportChartCSV() {
    if (!chart || !selectedMatch) return;
    
    const market = selectedChartMarket;
    const isMoneyway = market.startsWith('moneyway');
    
    const datasets = chart.data.datasets;
    const labels = chart.data.labels;
    
    const visibleDatasets = datasets.filter(ds => !ds.hidden);
    const visibleSeriesNames = visibleDatasets.map(ds => ds.label).join(', ');
    
    const timeRangeLabels = {
        '5min': '5 dakika',
        '10min': '10 dakika',
        '30min': '30 dakika',
        '1hour': '1 saat',
        '6hour': '6 saat',
        '12hour': '12 saat',
        '1day': '1 gün'
    };
    const timeRangeLabel = timeRangeLabels[chartTimeRange] || '1 gün';
    
    const marketLabels = {
        'moneyway_1x2': 'Moneyway 1X2',
        'moneyway_ou25': 'Moneyway Over/Under 2.5',
        'moneyway_btts': 'Moneyway BTTS',
        'dropping_1x2': 'Dropping Odds 1X2',
        'dropping_ou25': 'Dropping Odds O/U 2.5',
        'dropping_btts': 'Dropping Odds BTTS'
    };
    const marketLabel = marketLabels[market] || market;
    
    let csvContent = '\uFEFF';
    
    csvContent += `# SmartXFlow - Odds Export\n`;
    csvContent += `# Match: ${selectedMatch.home_team} vs ${selectedMatch.away_team}\n`;
    csvContent += `# League: ${selectedMatch.league}\n`;
    csvContent += `# Match Date: ${selectedMatch.start_time || 'N/A'}\n`;
    csvContent += `# Chart Type: ${marketLabel}\n`;
    csvContent += `# Time Range: ${timeRangeLabel}\n`;
    csvContent += `# Visible Series: ${visibleSeriesNames}\n`;
    csvContent += `# Export Date: ${new Date().toLocaleString('tr-TR')}\n`;
    csvContent += `#\n`;
    
    let headers = ['timestamp'];
    visibleDatasets.forEach(ds => {
        headers.push(ds.label.toLowerCase().replace(/\s+/g, '_'));
    });
    
    csvContent += headers.join(',') + '\n';
    
    for (let i = 0; i < labels.length; i++) {
        let row = [labels[i]];
        
        visibleDatasets.forEach(ds => {
            const val = ds.data[i];
            row.push(val !== null && val !== undefined ? val : '');
        });
        
        csvContent += row.map(cell => {
            if (typeof cell === 'string' && (cell.includes(',') || cell.includes('"') || cell.includes('\n'))) {
                return '"' + cell.replace(/"/g, '""') + '"';
            }
            return cell;
        }).join(',') + '\n';
    }
    
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = generateExportFilename('csv');
    link.click();
    URL.revokeObjectURL(link.href);
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

function getOddsFromHistory(historyPoint, label, market) {
    if (!historyPoint) return 0;
    
    if (market.includes('1x2')) {
        if (label === '1') {
            const val = historyPoint.Odds1 || historyPoint['1'];
            return val ? parseFloat(String(val).split('\n')[0]) || 0 : 0;
        }
        if (label === 'X') {
            const val = historyPoint.OddsX || historyPoint['X'];
            return val ? parseFloat(String(val).split('\n')[0]) || 0 : 0;
        }
        if (label === '2') {
            const val = historyPoint.Odds2 || historyPoint['2'];
            return val ? parseFloat(String(val).split('\n')[0]) || 0 : 0;
        }
    } else if (market.includes('ou25')) {
        if (label === 'Under' || label.toLowerCase().includes('under')) {
            const val = historyPoint.Under;
            return val ? parseFloat(String(val).split('\n')[0]) || 0 : 0;
        }
        if (label === 'Over' || label.toLowerCase().includes('over')) {
            const val = historyPoint.Over;
            return val ? parseFloat(String(val).split('\n')[0]) || 0 : 0;
        }
    } else if (market.includes('btts')) {
        if (label === 'Yes' || label.toLowerCase().includes('yes')) {
            const val = historyPoint.OddsYes || historyPoint.Yes;
            return val ? parseFloat(String(val).split('\n')[0]) || 0 : 0;
        }
        if (label === 'No' || label.toLowerCase().includes('no')) {
            const val = historyPoint.OddsNo || historyPoint.No;
            return val ? parseFloat(String(val).split('\n')[0]) || 0 : 0;
        }
    }
    return 0;
}

function getLatestOdds(latestData, label, market) {
    if (market.includes('1x2')) {
        if (label === '1') return parseFloat(latestData.Odds1 || latestData['1']) || 0;
        if (label === 'X') return parseFloat(latestData.OddsX || latestData['X']) || 0;
        if (label === '2') return parseFloat(latestData.Odds2 || latestData['2']) || 0;
    } else if (market.includes('ou25')) {
        if (label === 'Under' || label.toLowerCase().includes('under')) return parseFloat(latestData.Under) || 0;
        if (label === 'Over' || label.toLowerCase().includes('over')) return parseFloat(latestData.Over) || 0;
    } else if (market.includes('btts')) {
        if (label === 'Yes' || label.toLowerCase().includes('yes')) return parseFloat(latestData.OddsYes || latestData.Yes) || 0;
        if (label === 'No' || label.toLowerCase().includes('no')) return parseFloat(latestData.OddsNo || latestData.No) || 0;
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
