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
let dateFilterMode = 'ALL';
let chartTimeRange = '10min';
let currentChartHistoryData = [];
let chartViewMode = 'percent';
let alertsHistory = [];
const MAX_ALERTS_HISTORY = 500;
let isClientMode = true;

function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    })[c]);
}

let alarmCurrentPage = 0;
let alarmHasMore = false;
let alarmIsLoading = false;
let alarmTotalCount = 0;
let alarmEventCount = 0;
const ALARM_PAGE_SIZE = 30;


let masterAlarmData = [];

document.addEventListener('DOMContentLoaded', () => {
    loadMatches();
    setupTabs();
    setupSearch();
    setupModalChartTabs();
    checkStatus();
    loadMasterAlarms();
    window.statusInterval = window.setInterval(checkStatus, 30000);
    window.alarmInterval = window.setInterval(loadMasterAlarms, 60000);
});

function setupTabs() {
    document.querySelectorAll('.market-tabs .tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.market-tabs .tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            currentMarket = tab.dataset.market;
            
            const isDropMarket = currentMarket.startsWith('dropping_');
            showTrendSortButtons(isDropMarket);
            
            if (!isDropMarket && (currentSortColumn === 'trend_down' || currentSortColumn === 'trend_up')) {
                currentSortColumn = 'date';
                currentSortDirection = 'desc';
            }
            
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
                loadChartWithTrends(selectedMatch.home_team, selectedMatch.away_team, selectedChartMarket);
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
        if (currentMarket.startsWith('dropping')) {
            await loadOddsTrend(currentMarket);
        } else {
            oddsTrendCache = {};
        }
        
        const response = await fetch(`/api/matches?market=${currentMarket}`);
        const apiMatches = await response.json();
        matches = apiMatches || [];
        filteredMatches = applySorting(matches);
        renderMatches(filteredMatches);
        
        if (currentMarket.startsWith('dropping')) {
            attachTrendTooltipListeners();
        }
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

function getDonutColor(pctValue) {
    return '#22c55e';
}

function getMoneyColor(moneyStr) {
    if (!moneyStr) return 'money-low';
    const numStr = String(moneyStr).replace(/[£€$,\s]/g, '');
    const num = parseFloat(numStr);
    if (isNaN(num)) return 'money-low';
    return num >= 3000 ? 'money-high' : 'money-low';
}

function renderDonutSVG(percent, size = 48) {
    const num = parseFloat(String(percent).replace(/[^0-9.]/g, '')) || 0;
    const strokeWidth = size > 40 ? 5 : 4;
    const radius = (size - strokeWidth * 2) / 2;
    const circumference = 2 * Math.PI * radius;
    const offset = circumference - (num / 100) * circumference;
    const trackColor = '#1c2533';
    const isHigh = num >= 50;
    const fillColor = isHigh ? '#22c55e' : '#111827';
    const textColor = isHigh ? '#ffffff' : '#9ca3af';
    const fontSize = size > 40 ? 11 : 9;
    
    return `
        <svg class="donut-svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
            <circle class="ring-track" cx="${size/2}" cy="${size/2}" r="${radius}" fill="none" stroke="${trackColor}" stroke-width="${strokeWidth}"/>
            <circle class="ring-fill" cx="${size/2}" cy="${size/2}" r="${radius}" fill="none" stroke="${fillColor}" stroke-width="${strokeWidth}"
                stroke-dasharray="${circumference}" stroke-dashoffset="${offset}"
                stroke-linecap="round" transform="rotate(-90 ${size/2} ${size/2})"/>
            <text class="percent-text" x="${size/2}" y="${size/2}" text-anchor="middle" dominant-baseline="central" 
                fill="${textColor}" font-size="${fontSize}" font-weight="600">${num.toFixed(0)}%</text>
        </svg>
    `;
}

function renderMoneywayBlock(label, percent, odds, money) {
    const donut = renderDonutSVG(percent, 52);
    
    return `
        <div class="mw-outcome-block">
            <div class="mw-info-stack">
                <div class="mw-odds">${formatOdds(odds)}</div>
                ${money ? `<div class="mw-money">${money}</div>` : ''}
            </div>
            <div class="mw-donut">${donut}</div>
        </div>
    `;
}

function formatPct(val) {
    if (!val || val === '-') return '-';
    const cleaned = String(val).replace(/[%\s]/g, '');
    const num = parseFloat(cleaned);
    if (isNaN(num)) return '-';
    return num.toFixed(1) + '%';
}

function cleanPct(val) {
    if (!val || val === '-') return '';
    return String(val).replace(/%/g, '').trim();
}

function renderMatches(data) {
    const tbody = document.getElementById('matchesTableBody');
    const countEl = document.getElementById('matchCount');
    
    if (countEl) {
        countEl.textContent = data.length;
    }
    
    if (data.length === 0) {
        const colspan = currentMarket.includes('1x2') ? 7 : 6;
        const emptyMessage = isClientMode 
            ? "Bu market için veri bulunamadı. Scraper'ın Supabase'e veri gönderdiğinden emin olun."
            : "No matches found for this market. Click 'Scrape Now' to fetch data.";
        tbody.innerHTML = `
            <tr class="loading-row">
                <td colspan="${colspan}">
                    <div class="empty-state">
                        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                            <circle cx="12" cy="12" r="10"/>
                            <path d="M12 6v6l4 2"/>
                        </svg>
                        <p>${emptyMessage}</p>
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
                const block1 = renderMoneywayBlock('1', d.Pct1, d.Odds1 || d['1'], d.Amt1);
                const blockX = renderMoneywayBlock('X', d.PctX, d.OddsX || d['X'], d.AmtX);
                const block2 = renderMoneywayBlock('2', d.Pct2, d.Odds2 || d['2'], d.Amt2);
                return `
                    <tr data-index="${idx}" onclick="openMatchModal(${idx})">
                        <td class="match-date">${formatDateTwoLine(match.date)}</td>
                        <td class="match-league" title="${match.league || ''}">${match.league || '-'}</td>
                        <td class="match-teams">${match.home_team}<span class="vs">-</span>${match.away_team}</td>
                        <td class="mw-outcomes-cell" colspan="3">
                            <div class="mw-grid mw-grid-3">
                                ${block1}
                                ${blockX}
                                ${block2}
                            </div>
                        </td>
                        <td class="volume-cell">${formatVolume(d.Volume)}</td>
                    </tr>
                `;
            } else {
                const trend1Data = getOddsTrendData(match.home_team, match.away_team, 'odds1');
                const trendXData = getOddsTrendData(match.home_team, match.away_team, 'oddsx');
                const trend2Data = getOddsTrendData(match.home_team, match.away_team, 'odds2');
                
                const cell1 = renderDrop1X2Cell('1', d.Odds1 || d['1'], trend1Data);
                const cellX = renderDrop1X2Cell('X', d.OddsX || d['X'], trendXData);
                const cell2 = renderDrop1X2Cell('2', d.Odds2 || d['2'], trend2Data);
                
                return `
                    <tr class="dropping-1x2-row" data-index="${idx}" onclick="openMatchModal(${idx})">
                        <td class="match-date">${formatDateTwoLine(match.date)}</td>
                        <td class="match-league" title="${match.league || ''}">${match.league || '-'}</td>
                        <td class="match-teams">${match.home_team}<span class="vs">-</span>${match.away_team}</td>
                        <td class="drop-cell">${cell1}</td>
                        <td class="drop-cell">${cellX}</td>
                        <td class="drop-cell">${cell2}</td>
                        <td class="volume-cell">${formatVolume(d.Volume)}</td>
                    </tr>
                `;
            }
        } else if (currentMarket.includes('ou25')) {
            const trendUnder = isDropping ? (getDirectTrendArrow(d.TrendUnder) || getTableTrendArrow(d.Under, d.PrevUnder)) : '';
            const trendOver = isDropping ? (getDirectTrendArrow(d.TrendOver) || getTableTrendArrow(d.Over, d.PrevOver)) : '';
            
            if (isMoneyway) {
                const blockUnder = renderMoneywayBlock('U 2.5', d.PctUnder, d.Under, d.AmtUnder);
                const blockOver = renderMoneywayBlock('O 2.5', d.PctOver, d.Over, d.AmtOver);
                return `
                    <tr data-index="${idx}" onclick="openMatchModal(${idx})">
                        <td class="match-date">${formatDateTwoLine(match.date)}</td>
                        <td class="match-league" title="${match.league || ''}">${match.league || '-'}</td>
                        <td class="match-teams">${match.home_team}<span class="vs">-</span>${match.away_team}</td>
                        <td class="mw-outcomes-cell" colspan="2">
                            <div class="mw-grid mw-grid-2">
                                ${blockUnder}
                                ${blockOver}
                            </div>
                        </td>
                        <td class="volume-cell">${formatVolume(d.Volume)}</td>
                    </tr>
                `;
            } else {
                const trendUnderData = getOddsTrendData(match.home_team, match.away_team, 'under');
                const trendOverData = getOddsTrendData(match.home_team, match.away_team, 'over');
                
                const cellUnder = renderOddsWithTrend(d.Under, trendUnderData);
                const cellOver = renderOddsWithTrend(d.Over, trendOverData);
                
                return `
                    <tr data-index="${idx}" onclick="openMatchModal(${idx})">
                        <td class="match-date">${formatDateTwoLine(match.date)}</td>
                        <td class="match-league" title="${match.league || ''}">${match.league || '-'}</td>
                        <td class="match-teams">${match.home_team}<span class="vs">-</span>${match.away_team}</td>
                        <td class="selection-cell"><div>${cellUnder}</div></td>
                        <td class="selection-cell"><div>${cellOver}</div></td>
                        <td class="volume-cell">${formatVolume(d.Volume)}</td>
                    </tr>
                `;
            }
        } else {
            const trendYes = isDropping ? (getDirectTrendArrow(d.TrendYes) || getTableTrendArrow(d.OddsYes || d.Yes, d.PrevYes)) : '';
            const trendNo = isDropping ? (getDirectTrendArrow(d.TrendNo) || getTableTrendArrow(d.OddsNo || d.No, d.PrevNo)) : '';
            
            if (isMoneyway) {
                const blockYes = renderMoneywayBlock('Yes', d.PctYes, d.OddsYes || d.Yes, d.AmtYes);
                const blockNo = renderMoneywayBlock('No', d.PctNo, d.OddsNo || d.No, d.AmtNo);
                return `
                    <tr data-index="${idx}" onclick="openMatchModal(${idx})">
                        <td class="match-date">${formatDateTwoLine(match.date)}</td>
                        <td class="match-league" title="${match.league || ''}">${match.league || '-'}</td>
                        <td class="match-teams">${match.home_team}<span class="vs">-</span>${match.away_team}</td>
                        <td class="mw-outcomes-cell" colspan="2">
                            <div class="mw-grid mw-grid-2">
                                ${blockYes}
                                ${blockNo}
                            </div>
                        </td>
                        <td class="volume-cell">${formatVolume(d.Volume)}</td>
                    </tr>
                `;
            } else {
                const trendYesData = getOddsTrendData(match.home_team, match.away_team, 'yes');
                const trendNoData = getOddsTrendData(match.home_team, match.away_team, 'no');
                
                const cellYes = renderOddsWithTrend(d.OddsYes || d.Yes, trendYesData);
                const cellNo = renderOddsWithTrend(d.OddsNo || d.No, trendNoData);
                
                return `
                    <tr data-index="${idx}" onclick="openMatchModal(${idx})">
                        <td class="match-date">${formatDateTwoLine(match.date)}</td>
                        <td class="match-league" title="${match.league || ''}">${match.league || '-'}</td>
                        <td class="match-teams">${match.home_team}<span class="vs">-</span>${match.away_team}</td>
                        <td class="selection-cell"><div>${cellYes}</div></td>
                        <td class="selection-cell"><div>${cellNo}</div></td>
                        <td class="volume-cell">${formatVolume(d.Volume)}</td>
                    </tr>
                `;
            }
        }
    }).join('');
    
    if (currentMarket.startsWith('dropping')) {
        setTimeout(() => attachTrendTooltipListeners(), 50);
    }
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

function formatDateTwoLine(dateStr) {
    if (!dateStr || dateStr === '-') return '<div class="date-line">-</div>';
    
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    
    const pattern1 = dateStr.match(/(\d{1,2})\.(\w{3})\s*(\d{2}:\d{2})/i);
    if (pattern1) {
        return `<div class="date-line">${pattern1[1]}.${pattern1[2]}</div><div class="time-line">${pattern1[3]}</div>`;
    }
    
    const pattern2 = dateStr.match(/(\d{1,2})\.(\w{3})(\d{2}:\d{2})/i);
    if (pattern2) {
        return `<div class="date-line">${pattern2[1]}.${pattern2[2]}</div><div class="time-line">${pattern2[3]}</div>`;
    }
    
    const pattern3 = dateStr.match(/(\d{4})-(\d{2})-(\d{2})\s*(\d{2}:\d{2})?/);
    if (pattern3) {
        const day = parseInt(pattern3[3]);
        const monthIdx = parseInt(pattern3[2]) - 1;
        const time = pattern3[4] || '00:00';
        return `<div class="date-line">${day}.${months[monthIdx]}</div><div class="time-line">${time}</div>`;
    }
    
    const pattern4 = dateStr.match(/(\d{4})-(\d{2})-(\d{2})/);
    if (pattern4) {
        const day = parseInt(pattern4[3]);
        const monthIdx = parseInt(pattern4[2]) - 1;
        return `<div class="date-line">${day}.${months[monthIdx]}</div><div class="time-line">-</div>`;
    }
    
    const pattern5 = dateStr.match(/(\d{4})/);
    if (pattern5 && dateStr.length === 4) {
        return `<div class="date-line">${dateStr}</div><div class="time-line">-</div>`;
    }
    
    return `<div class="date-line">${dateStr}</div>`;
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

function getMatchTrendPct(match, selection) {
    const matchKey = `${match.home_team}|${match.away_team}`;
    const matchData = oddsTrendCache[matchKey];
    if (!matchData || !matchData.values) return 0;
    
    let selKey = selection;
    if (currentMarket.includes('1x2')) {
        if (selection === 'sel1') selKey = 'odds1';
        else if (selection === 'selX') selKey = 'oddsx';
        else if (selection === 'sel2') selKey = 'odds2';
    } else if (currentMarket.includes('ou25')) {
        if (selection === 'sel1') selKey = 'under';
        else if (selection === 'sel2') selKey = 'over';
    } else if (currentMarket.includes('btts')) {
        if (selection === 'sel1') selKey = 'yes';
        else if (selection === 'sel2') selKey = 'no';
    }
    
    if (!matchData.values[selKey]) return 0;
    return matchData.values[selKey].pct_change || 0;
}

function getMinTrendPct(match) {
    const matchKey = `${match.home_team}|${match.away_team}`;
    const matchData = oddsTrendCache[matchKey];
    if (!matchData || !matchData.values) return 0;
    
    let minPct = 0;
    for (const sel in matchData.values) {
        const pct = matchData.values[sel].pct_change || 0;
        if (pct < minPct) {
            minPct = pct;
        }
    }
    return minPct;
}

function getMaxTrendPct(match) {
    const matchKey = `${match.home_team}|${match.away_team}`;
    const matchData = oddsTrendCache[matchKey];
    if (!matchData || !matchData.values) return 0;
    
    let maxPct = 0;
    for (const sel in matchData.values) {
        const pct = matchData.values[sel].pct_change || 0;
        if (pct > maxPct) {
            maxPct = pct;
        }
    }
    return maxPct;
}

function applySorting(data) {
    let sortedData = [...data];
    
    sortedData = sortedData.filter(m => hasValidMarketData(m, currentMarket));
    
    const now = new Date();
    const todayDay = now.getDate();
    const todayMonth = now.getMonth() + 1;
    const yesterday = new Date(now);
    yesterday.setDate(now.getDate() - 1);
    const yesterdayDay = yesterday.getDate();
    const yesterdayMonth = yesterday.getMonth() + 1;
    
    const monthNames = {
        'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
        'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
    };
    
    function parseMatchDate(dateStr) {
        if (!dateStr) return null;
        const numericMatch = dateStr.match(/^(\d{1,2})\.(\d{1,2})/);
        if (numericMatch) {
            return { day: parseInt(numericMatch[1], 10), month: parseInt(numericMatch[2], 10) };
        }
        const textMatch = dateStr.match(/^(\d{1,2})\.(\w{3})/);
        if (textMatch) {
            const day = parseInt(textMatch[1], 10);
            const monthStr = textMatch[2];
            const month = monthNames[monthStr];
            if (month) return { day, month };
        }
        return null;
    }
    
    function isDateTodayOrFuture(parsed) {
        if (!parsed) return false;
        if (parsed.month > todayMonth) return true;
        if (parsed.month === todayMonth && parsed.day >= todayDay) return true;
        return false;
    }
    
    if (dateFilterMode === 'YESTERDAY') {
        console.log('[Filter] YESTERDAY mode:', yesterdayDay + '.' + yesterdayMonth);
        sortedData = sortedData.filter(m => {
            const parsed = parseMatchDate(m.date);
            if (!parsed) return false;
            return parsed.day === yesterdayDay && parsed.month === yesterdayMonth;
        });
        console.log('[Filter] YESTERDAY filtered count:', sortedData.length);
    } else if (dateFilterMode === 'TODAY') {
        console.log('[Filter] TODAY mode:', todayDay + '.' + todayMonth);
        sortedData = sortedData.filter(m => {
            const parsed = parseMatchDate(m.date);
            if (!parsed) return false;
            return parsed.day === todayDay && parsed.month === todayMonth;
        });
        console.log('[Filter] TODAY filtered count:', sortedData.length);
    } else {
        console.log('[Filter] ALL mode (today + future):', todayDay + '.' + todayMonth, '+');
        sortedData = sortedData.filter(m => {
            const parsed = parseMatchDate(m.date);
            return isDateTodayOrFuture(parsed);
        });
        console.log('[Filter] ALL filtered count:', sortedData.length);
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
                if (currentMarket.startsWith('dropping_')) {
                    valA = getMatchTrendPct(a, 'sel1');
                    valB = getMatchTrendPct(b, 'sel1');
                } else if (currentMarket.includes('1x2')) {
                    valA = parsePctValue(d1.Pct1);
                    valB = parsePctValue(d2.Pct1);
                } else if (currentMarket.includes('ou25')) {
                    valA = parsePctValue(d1.PctUnder);
                    valB = parsePctValue(d2.PctUnder);
                } else if (currentMarket.includes('btts')) {
                    valA = parsePctValue(d1.PctYes);
                    valB = parsePctValue(d2.PctYes);
                }
                break;
            case 'selX':
                if (currentMarket.startsWith('dropping_')) {
                    valA = getMatchTrendPct(a, 'selX');
                    valB = getMatchTrendPct(b, 'selX');
                } else {
                    valA = parsePctValue(d1.PctX);
                    valB = parsePctValue(d2.PctX);
                }
                break;
            case 'sel2':
                if (currentMarket.startsWith('dropping_')) {
                    valA = getMatchTrendPct(a, 'sel2');
                    valB = getMatchTrendPct(b, 'sel2');
                } else if (currentMarket.includes('1x2')) {
                    valA = parsePctValue(d1.Pct2);
                    valB = parsePctValue(d2.Pct2);
                } else if (currentMarket.includes('ou25')) {
                    valA = parsePctValue(d1.PctOver);
                    valB = parsePctValue(d2.PctOver);
                } else if (currentMarket.includes('btts')) {
                    valA = parsePctValue(d1.PctNo);
                    valB = parsePctValue(d2.PctNo);
                }
                break;
            case 'volume':
                valA = parseVolume(a);
                valB = parseVolume(b);
                break;
            case 'trend_down':
                valA = getMinTrendPct(a);
                valB = getMinTrendPct(b);
                return valA - valB;
            case 'trend_up':
                valA = getMaxTrendPct(a);
                valB = getMaxTrendPct(b);
                return valB - valA;
            default:
                valA = parseDate(a.date);
                valB = parseDate(b.date);
        }
        
        valA = valA || 0;
        valB = valB || 0;
        
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

function parseOddsValue(val) {
    if (!val || val === '-') return 0;
    
    const values = String(val)
        .replace(/[↑↓]/g, '')
        .match(/[\d.,]+/g);
    
    if (!values || values.length === 0) return 0;
    
    const last = values[values.length - 1];
    const num = parseFloat(last.replace(',', '.'));
    return isNaN(num) ? 0 : num;
}

function parsePctValue(val) {
    if (!val || val === '-') return 0;
    const numMatch = String(val).match(/[\d.,]+/);
    if (!numMatch) return 0;
    const num = parseFloat(numMatch[0].replace(',', '.'));
    return isNaN(num) ? 0 : num;
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
    
    const ddmmyyyyHHMM = dateStr.match(/(\d{2})\.(\d{2})\.(\d{4})\s+\d{2}:\d{2}/);
    if (ddmmyyyyHHMM) {
        return `${ddmmyyyyHHMM[3]}-${ddmmyyyyHHMM[2]}-${ddmmyyyyHHMM[1]}`;
    }
    
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
    
    const dmySlash = dateStr.match(/(\d{1,2})\/(\d{1,2})\/(\d{4})/);
    if (dmySlash) {
        const day = dmySlash[1].padStart(2, '0');
        const month = dmySlash[2].padStart(2, '0');
        return `${dmySlash[3]}-${month}-${day}`;
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
    
    updateTrendSortButtons();
    updateTableHeaders();
    filteredMatches = applySorting(matches);
    renderMatches(filteredMatches);
}

function sortByTrend(direction) {
    const downBtn = document.getElementById('trendDownBtn');
    const upBtn = document.getElementById('trendUpBtn');
    
    if (direction === 'down') {
        if (currentSortColumn === 'trend_down') {
            currentSortColumn = 'date';
            currentSortDirection = 'desc';
        } else {
            currentSortColumn = 'trend_down';
            currentSortDirection = 'desc';
        }
    } else {
        if (currentSortColumn === 'trend_up') {
            currentSortColumn = 'date';
            currentSortDirection = 'desc';
        } else {
            currentSortColumn = 'trend_up';
            currentSortDirection = 'desc';
        }
    }
    
    updateTrendSortButtons();
    updateTableHeaders();
    filteredMatches = applySorting(matches);
    renderMatches(filteredMatches);
}

function updateTrendSortButtons() {
    const downBtn = document.getElementById('trendDownBtn');
    const upBtn = document.getElementById('trendUpBtn');
    
    if (downBtn) {
        downBtn.classList.remove('active', 'down');
        if (currentSortColumn === 'trend_down') {
            downBtn.classList.add('active', 'down');
        }
    }
    
    if (upBtn) {
        upBtn.classList.remove('active');
        if (currentSortColumn === 'trend_up') {
            upBtn.classList.add('active');
        }
    }
}

function showTrendSortButtons(show) {
    const btns = document.getElementById('trendSortBtns');
    if (btns) {
        btns.style.display = show ? 'flex' : 'none';
    }
}

function toggleTodayFilter() {
    const todayBtn = document.getElementById('todayBtn');
    const yesterdayBtn = document.getElementById('yesterdayBtn');
    
    if (dateFilterMode === 'TODAY') {
        dateFilterMode = 'ALL';
        if (todayBtn) todayBtn.classList.remove('active');
    } else {
        dateFilterMode = 'TODAY';
        if (todayBtn) todayBtn.classList.add('active');
        if (yesterdayBtn) yesterdayBtn.classList.remove('active');
    }
    
    console.log('[Filter] Mode changed to:', dateFilterMode);
    const searchInput = document.getElementById('searchInput');
    const query = searchInput?.value?.toLowerCase() || '';
    filterMatches(query);
}

function toggleYesterdayFilter() {
    const todayBtn = document.getElementById('todayBtn');
    const yesterdayBtn = document.getElementById('yesterdayBtn');
    
    if (dateFilterMode === 'YESTERDAY') {
        dateFilterMode = 'ALL';
        if (yesterdayBtn) yesterdayBtn.classList.remove('active');
    } else {
        dateFilterMode = 'YESTERDAY';
        if (yesterdayBtn) yesterdayBtn.classList.add('active');
        if (todayBtn) todayBtn.classList.remove('active');
    }
    
    console.log('[Filter] Mode changed to:', dateFilterMode);
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
let modalOddsData = null;

let modalSmartMoneyEventsOpen = false;

function toggleModalSmartMoneyEvents() {
    const wrapper = document.getElementById('modalEventsGridWrapper');
    const chevron = document.getElementById('modalEventsChevron');
    modalSmartMoneyEventsOpen = !modalSmartMoneyEventsOpen;
    
    if (modalSmartMoneyEventsOpen) {
        wrapper.classList.remove('collapsed');
        wrapper.classList.add('expanded');
        chevron.classList.add('rotated');
    } else {
        wrapper.classList.remove('expanded');
        wrapper.classList.add('collapsed');
        chevron.classList.remove('rotated');
    }
}

function openMatchModal(index) {
    const dataSource = filteredMatches.length > 0 ? filteredMatches : matches;
    if (index >= 0 && index < dataSource.length) {
        selectedMatch = dataSource[index];
        selectedChartMarket = currentMarket;
        previousOddsData = null;
        modalOddsData = selectedMatch.odds || selectedMatch.details || null;
        
        modalSmartMoneyEventsOpen = false;
        const wrapper = document.getElementById('modalEventsGridWrapper');
        const chevron = document.getElementById('modalEventsChevron');
        if (wrapper) {
            wrapper.classList.remove('expanded');
            wrapper.classList.add('collapsed');
        }
        if (chevron) {
            chevron.classList.remove('rotated');
        }
        
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
        loadMatchAlarms(selectedMatch.home_team, selectedMatch.away_team);
    }
}

let bulkHistoryCache = {};
let bulkHistoryCacheKey = '';

async function loadAllMarketsAtOnce(home, away) {
    const cacheKey = `${home}|${away}`;
    if (bulkHistoryCacheKey === cacheKey && Object.keys(bulkHistoryCache).length > 0) {
        console.log('[Bulk] Using cached data for', cacheKey);
        return bulkHistoryCache;
    }
    
    try {
        console.log('[Bulk] Fetching all markets for', home, 'vs', away);
        const startTime = performance.now();
        const response = await fetch(
            `/api/match/history/bulk?home=${encodeURIComponent(home)}&away=${encodeURIComponent(away)}`
        );
        const data = await response.json();
        const elapsed = performance.now() - startTime;
        console.log(`[Bulk] Loaded all 6 markets in ${elapsed.toFixed(0)}ms`);
        
        if (data.markets) {
            bulkHistoryCache = data.markets;
            bulkHistoryCacheKey = cacheKey;
        }
        return data.markets || {};
    } catch (e) {
        console.error('[Bulk] Error fetching all markets:', e);
        return {};
    }
}

async function loadChartWithTrends(home, away, market) {
    try {
        let data = { history: [] };
        
        const cacheKey = `${home}|${away}`;
        if (bulkHistoryCacheKey === cacheKey && bulkHistoryCache[market]) {
            data = bulkHistoryCache[market];
            console.log('[Modal] Using bulk cache for', market, 'count:', data.history?.length);
        } else {
            try {
                const response = await fetch(
                    `/api/match/history?home=${encodeURIComponent(home)}&away=${encodeURIComponent(away)}&market=${market}`
                );
                data = await response.json();
                console.log('[Modal] Loaded history for', home, 'vs', away, 'market:', market, 'count:', data.history?.length);
            } catch (e) {
                console.log('Using demo history data');
            }
        }
        
        if (data.history && data.history.length >= 1) {
            modalOddsData = data.history[data.history.length - 1];
            console.log('[Modal] Latest odds data:', modalOddsData);
        } else {
            modalOddsData = null;
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
    const baseData = selectedMatch.odds || selectedMatch.details || {};
    const d = modalOddsData || baseData;
    const p = previousOddsData || {};
    const isMoneyway = selectedChartMarket.startsWith('moneyway');
    const isDropping = selectedChartMarket.startsWith('dropping');
    
    console.log('[Modal Card] Market:', selectedChartMarket, 'isMoneyway:', isMoneyway, 'isDropping:', isDropping);
    console.log('[Modal Card] Data source:', modalOddsData ? 'API (modalOddsData)' : 'Match (baseData)');
    console.log('[Modal Card] Data:', d);
    
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
                                <span class="pct ${c1}" style="font-family:'JetBrains Mono',monospace;font-size:15px;font-weight:700;">${formatPct(d.Pct1)}</span>
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
                                <span class="pct ${cX}" style="font-family:'JetBrains Mono',monospace;font-size:15px;font-weight:700;">${formatPct(d.PctX)}</span>
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
                                <span class="pct ${c2}" style="font-family:'JetBrains Mono',monospace;font-size:15px;font-weight:700;">${formatPct(d.Pct2)}</span>
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
                            <span class="row-value pct ${cU}">${formatPct(d.PctUnder)}</span>
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
                            <span class="row-value pct ${cO}">${formatPct(d.PctOver)}</span>
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
                            <span class="row-value pct ${cY}">${formatPct(d.PctYes)}</span>
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
                            <span class="row-value pct ${cN}">${formatPct(d.PctNo)}</span>
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
                const dataKeys = chartViewMode === 'money' 
                    ? ['Amt1', 'AmtX', 'Amt2'] 
                    : ['Pct1', 'PctX', 'Pct2'];
                dataKeys.forEach((key, idx) => {
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
                const dataKeys = chartViewMode === 'money' 
                    ? ['AmtUnder', 'AmtOver'] 
                    : ['PctUnder', 'PctOver'];
                dataKeys.forEach((key, idx) => {
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
                const dataKeys = chartViewMode === 'money' 
                    ? ['AmtYes', 'AmtNo'] 
                    : ['PctYes', 'PctNo'];
                dataKeys.forEach((key, idx) => {
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
                        enabled: false,
                        external: function(context) {
                            let tooltipEl = document.getElementById('chartjs-tooltip');
                            if (!tooltipEl) {
                                tooltipEl = document.createElement('div');
                                tooltipEl.id = 'chartjs-tooltip';
                                tooltipEl.innerHTML = '<div class="chart-tooltip-inner"></div>';
                                document.body.appendChild(tooltipEl);
                            }
                            
                            const tooltipModel = context.tooltip;
                            if (tooltipModel.opacity === 0) {
                                tooltipEl.style.opacity = 0;
                                return;
                            }
                            
                            if (tooltipModel.body) {
                                const dataIndex = tooltipModel.dataPoints[0].dataIndex;
                                const h = tooltipHistory[dataIndex];
                                const titleLines = tooltipModel.title || [];
                                
                                let innerHtml = '<div class="chart-tooltip-title">' + titleLines.join('<br>') + '</div>';
                                innerHtml += '<div class="chart-tooltip-body">';
                                
                                tooltipModel.dataPoints.forEach(function(dataPoint) {
                                    const datasetLabel = dataPoint.dataset.label;
                                    const boxColor = dataPoint.dataset.borderColor;
                                    
                                    if (isDropping && h) {
                                        const graphPointOdds = getOddsFromHistory(h, datasetLabel, market);
                                        const currentLatestOdds = getLatestOdds(latestData, datasetLabel.replace('%', ''), market);
                                        
                                        innerHtml += '<div class="chart-tooltip-row">';
                                        innerHtml += '<span class="chart-tooltip-box" style="background:' + boxColor + '"></span>';
                                        
                                        if (graphPointOdds > 0 && currentLatestOdds > 0 && graphPointOdds !== currentLatestOdds) {
                                            const pctChange = ((currentLatestOdds - graphPointOdds) / graphPointOdds) * 100;
                                            const changeSign = pctChange >= 0 ? '+' : '';
                                            const changeStr = changeSign + pctChange.toFixed(1) + '%';
                                            const arrow = pctChange >= 0 ? '↑' : '↓';
                                            const colorClass = pctChange >= 0 ? 'trend-color-up' : 'trend-color-down';
                                            
                                            innerHtml += '<span class="chart-tooltip-label">' + datasetLabel + ': ' + graphPointOdds.toFixed(2) + ' → ' + currentLatestOdds.toFixed(2) + '</span>';
                                            innerHtml += '</div>';
                                            innerHtml += '<div class="chart-tooltip-row chart-tooltip-change">';
                                            innerHtml += '<span class="chart-tooltip-box" style="background:transparent"></span>';
                                            innerHtml += '<span class="chart-tooltip-label">Change vs Latest: <span class="' + colorClass + '">' + changeStr + ' ' + arrow + '</span></span>';
                                        } else if (graphPointOdds > 0) {
                                            innerHtml += '<span class="chart-tooltip-label">' + datasetLabel + ': ' + graphPointOdds.toFixed(2) + '</span>';
                                        } else {
                                            innerHtml += '<span class="chart-tooltip-label">' + datasetLabel + ': ' + dataPoint.formattedValue + '</span>';
                                        }
                                        innerHtml += '</div>';
                                    } else if (h) {
                                        innerHtml += '<div class="chart-tooltip-row">';
                                        innerHtml += '<span class="chart-tooltip-box" style="background:' + boxColor + '"></span>';
                                        
                                        if (market.includes('1x2')) {
                                            if (datasetLabel.includes('1')) {
                                                const odds = h.Odds1 || h['1'] || '-';
                                                const amt = h.Amt1 || '';
                                                const pct = h.Pct1 || '';
                                                innerHtml += '<span class="chart-tooltip-label">1 • ' + formatOdds(odds) + '</span>';
                                                if (amt) innerHtml += '</div><div class="chart-tooltip-row"><span class="chart-tooltip-box" style="background:transparent"></span><span class="chart-tooltip-label">' + amt + ' — ' + cleanPct(pct) + '%</span>';
                                            } else if (datasetLabel.includes('X')) {
                                                const odds = h.OddsX || h['X'] || '-';
                                                const amt = h.AmtX || '';
                                                const pct = h.PctX || '';
                                                innerHtml += '<span class="chart-tooltip-label">X • ' + formatOdds(odds) + '</span>';
                                                if (amt) innerHtml += '</div><div class="chart-tooltip-row"><span class="chart-tooltip-box" style="background:transparent"></span><span class="chart-tooltip-label">' + amt + ' — ' + cleanPct(pct) + '%</span>';
                                            } else if (datasetLabel.includes('2')) {
                                                const odds = h.Odds2 || h['2'] || '-';
                                                const amt = h.Amt2 || '';
                                                const pct = h.Pct2 || '';
                                                innerHtml += '<span class="chart-tooltip-label">2 • ' + formatOdds(odds) + '</span>';
                                                if (amt) innerHtml += '</div><div class="chart-tooltip-row"><span class="chart-tooltip-box" style="background:transparent"></span><span class="chart-tooltip-label">' + amt + ' — ' + cleanPct(pct) + '%</span>';
                                            }
                                        } else if (market.includes('ou25')) {
                                            if (datasetLabel.toLowerCase().includes('under')) {
                                                const odds = h.Under || '-';
                                                const amt = h.AmtUnder || '';
                                                const pct = h.PctUnder || '';
                                                innerHtml += '<span class="chart-tooltip-label">Under • ' + formatOdds(odds) + '</span>';
                                                if (amt) innerHtml += '</div><div class="chart-tooltip-row"><span class="chart-tooltip-box" style="background:transparent"></span><span class="chart-tooltip-label">' + amt + ' — ' + cleanPct(pct) + '%</span>';
                                            } else {
                                                const odds = h.Over || '-';
                                                const amt = h.AmtOver || '';
                                                const pct = h.PctOver || '';
                                                innerHtml += '<span class="chart-tooltip-label">Over • ' + formatOdds(odds) + '</span>';
                                                if (amt) innerHtml += '</div><div class="chart-tooltip-row"><span class="chart-tooltip-box" style="background:transparent"></span><span class="chart-tooltip-label">' + amt + ' — ' + cleanPct(pct) + '%</span>';
                                            }
                                        } else if (market.includes('btts')) {
                                            if (datasetLabel.toLowerCase().includes('yes')) {
                                                const odds = h.Yes || '-';
                                                const amt = h.AmtYes || '';
                                                const pct = h.PctYes || '';
                                                innerHtml += '<span class="chart-tooltip-label">Yes • ' + formatOdds(odds) + '</span>';
                                                if (amt) innerHtml += '</div><div class="chart-tooltip-row"><span class="chart-tooltip-box" style="background:transparent"></span><span class="chart-tooltip-label">' + amt + ' — ' + cleanPct(pct) + '%</span>';
                                            } else {
                                                const odds = h.No || '-';
                                                const amt = h.AmtNo || '';
                                                const pct = h.PctNo || '';
                                                innerHtml += '<span class="chart-tooltip-label">No • ' + formatOdds(odds) + '</span>';
                                                if (amt) innerHtml += '</div><div class="chart-tooltip-row"><span class="chart-tooltip-box" style="background:transparent"></span><span class="chart-tooltip-label">' + amt + ' — ' + cleanPct(pct) + '%</span>';
                                            }
                                        }
                                        innerHtml += '</div>';
                                    } else {
                                        innerHtml += '<div class="chart-tooltip-row">';
                                        innerHtml += '<span class="chart-tooltip-box" style="background:' + boxColor + '"></span>';
                                        innerHtml += '<span class="chart-tooltip-label">' + datasetLabel + ': ' + dataPoint.formattedValue + '</span>';
                                        innerHtml += '</div>';
                                    }
                                });
                                
                                innerHtml += '</div>';
                                tooltipEl.querySelector('.chart-tooltip-inner').innerHTML = innerHtml;
                            }
                            
                            const position = context.chart.canvas.getBoundingClientRect();
                            tooltipEl.style.opacity = 1;
                            tooltipEl.style.position = 'absolute';
                            tooltipEl.style.left = position.left + window.pageXOffset + tooltipModel.caretX + 'px';
                            tooltipEl.style.top = position.top + window.pageYOffset + tooltipModel.caretY + 'px';
                            tooltipEl.style.pointerEvents = 'none';
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
    
    const isMoneyway = market.startsWith('moneyway');
    const viewModeButtons = isMoneyway ? `
        <div class="chart-filter-group view-mode-filters">
            <button class="chart-view-btn ${chartViewMode === 'percent' ? 'active' : ''}" 
                    data-mode="percent"
                    onclick="setChartViewMode('percent')">
                % Yüzde
            </button>
            <button class="chart-view-btn ${chartViewMode === 'money' ? 'active' : ''}" 
                    data-mode="money"
                    onclick="setChartViewMode('money')">
                £ Para
            </button>
        </div>
        <div class="chart-filter-divider"></div>
    ` : '';
    
    container.innerHTML = `
        ${viewModeButtons}
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

function setChartViewMode(mode) {
    chartViewMode = mode;
    
    document.querySelectorAll('.chart-view-btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.mode === mode) {
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
    
    if (chart) {
        chart.options.animation = false;
        chart.update('none');
    }
    
    setTimeout(() => {
        html2canvas(modalContent, {
            backgroundColor: '#15202b',
            scale: 2,
            useCORS: true,
            allowTaint: false,
            logging: true,
            onclone: function(clonedDoc) {
                const clonedCanvas = clonedDoc.querySelector('#oddsChart');
                if (clonedCanvas) {
                    clonedCanvas.crossOrigin = 'anonymous';
                }
            }
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
    }, 300);
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
    
    if (chart) {
        chart.options.animation = false;
        chart.update('none');
    }
    
    setTimeout(() => {
        html2canvas(modalContent, {
            backgroundColor: '#161b22',
            scale: 2,
            logging: false,
            useCORS: true,
            allowTaint: false,
            height: modalContent.scrollHeight,
            windowHeight: modalContent.scrollHeight,
            scrollY: 0,
            scrollX: 0,
            onclone: function(clonedDoc) {
                const clonedCanvas = clonedDoc.querySelector('#oddsChart');
                if (clonedCanvas) {
                    clonedCanvas.crossOrigin = 'anonymous';
                }
            }
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
    }, 300);
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
        isClientMode = status.mode === 'client';
        
        const indicator = document.getElementById('statusIndicator');
        if (indicator) {
            const dot = indicator.querySelector('.status-dot');
            const text = indicator.querySelector('.status-text');
            
            if (status.running) {
                dot.classList.add('running');
                text.textContent = 'Scraping...';
            } else {
                dot.classList.remove('running');
                text.textContent = status.supabase_connected ? 'Ready' : 'Offline';
            }
        }
        
        const lastUpdateTime = document.getElementById('lastUpdateTime');
        if (lastUpdateTime) {
            if (status.last_data_update_tr) {
                lastUpdateTime.textContent = status.last_data_update_tr;
            } else {
                lastUpdateTime.textContent = '--:--';
            }
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

let highlightedAlarmType = null;

const AlarmColors = {
    sharp: { hex: '#22c55e', name: 'Sharp Money', icon: '🟢', priority: 1 },
    rlm: { hex: '#f97316', name: 'Reverse Line Move', icon: '🔴', priority: 2 },
    big_money: { hex: '#eab308', name: 'Big Money', icon: '💰', priority: 3 },
    momentum_change: { hex: '#06b6d4', name: 'Momentum Change', icon: '🔄', priority: 4 },
    momentum: { hex: '#a855f7', name: 'Momentum', icon: '🟣', priority: 5 },
    line_freeze: { hex: '#3b82f6', name: 'Line Freeze', icon: '🔵', priority: 6 },
    public_surge: { hex: '#eab308', name: 'Public Surge', icon: '🟡', priority: 7 },
    dropping: { hex: '#ef4444', name: 'Dropping', icon: '📉', priority: 8 },
    default: { hex: '#666666', name: 'Alert', icon: '⚡', priority: 99 }
};

function getAlarmColor(alarmType) {
    return AlarmColors[alarmType] || AlarmColors.default;
}

async function loadMasterAlarms() {
    try {
        const response = await fetch('/api/alarms?page=0&page_size=100&filter=all&sort=newest');
        const data = await response.json();
        
        if (!data.alarms) {
            masterAlarmData = [];
            updateAlarmBadge(0);
            renderSmartMoneyBand();
            return;
        }
        
        masterAlarmData = data.alarms;
        
        masterAlarmData.sort((a, b) => new Date(b.latest_time || 0) - new Date(a.latest_time || 0));
        
        updateAlarmBadge(data.total || masterAlarmData.length);
        
        renderSmartMoneyBand();
        
    } catch (error) {
        console.error('[MasterAlarms] Error:', error);
    }
}

let tickerLastAlarmId = null;
let tickerAnimationPaused = false;

function renderSmartMoneyBand(highlightNewAlarm = false) {
    const tickerTrack = document.getElementById('tickerTrack');
    if (!tickerTrack) return;
    
    if (masterAlarmData.length === 0) {
        tickerTrack.innerHTML = '<div class="ticker-empty">Aktif kritik alarm yok</div>';
        tickerTrack.style.animation = 'none';
        return;
    }
    
    const allEvents = [];
    masterAlarmData.forEach(group => {
        if (group.events && group.events.length > 0) {
            group.events.forEach(event => {
                allEvents.push({
                    ...event,
                    home: group.home,
                    away: group.away,
                    league: group.league,
                    match_id: group.match_id,
                    date: group.date
                });
            });
        }
    });
    
    allEvents.sort((a, b) => new Date(b.timestamp || 0) - new Date(a.timestamp || 0));
    
    const latest10 = allEvents.slice(0, 10);
    
    if (latest10.length === 0) {
        tickerTrack.innerHTML = '<div class="ticker-empty">Aktif kritik alarm yok</div>';
        tickerTrack.style.animation = 'none';
        return;
    }
    
    const newFirstAlarmId = `${latest10[0].type}_${latest10[0].home}_${latest10[0].away}_${latest10[0].timestamp}`;
    const hasNewAlarm = tickerLastAlarmId !== null && tickerLastAlarmId !== newFirstAlarmId;
    tickerLastAlarmId = newFirstAlarmId;
    
    tickerTrack.style.animation = 'none';
    tickerTrack.offsetHeight;
    tickerTrack.innerHTML = '';
    
    const createPill = (alarm, index, isClone = false) => {
        const pill = document.createElement('div');
        pill.className = 'ticker-pill';
        pill.dataset.alarmType = alarm.type;
        pill.dataset.alarm = alarm.type;
        
        pill.dataset.matchId = alarm.match_id || '';
        pill.dataset.home = alarm.home;
        pill.dataset.away = alarm.away;
        pill.dataset.league = alarm.league || '';
        
        const alarmInfo = getAlarmColor(alarm.type);
        const color = alarmInfo.hex;
        const shortName = alarm.name ? alarm.name.split(' ')[0].toUpperCase() : '';
        const moneyText = alarm.money_diff ? `+£${alarm.money_diff.toLocaleString()}` : '';
        const sideText = alarm.side ? `(${alarm.side})` : '';
        
        pill.innerHTML = `
            <span class="pill-dot" style="background: ${color};"></span>
            <span class="pill-type" style="color: ${color};">${shortName}</span>
            <span class="pill-match">${alarm.home} – ${alarm.away}</span>
            ${moneyText ? `<span class="pill-money">${moneyText}</span>` : ''}
            ${sideText ? `<span class="pill-side">${sideText}</span>` : ''}
        `;
        
        if (index === 0 && !isClone && (hasNewAlarm || highlightNewAlarm)) {
            pill.classList.add('ticker-pill-new');
            setTimeout(() => pill.classList.remove('ticker-pill-new'), 2000);
        }
        
        pill.onclick = () => {
            console.log('[Band→Match] Clicked:', alarm.home, 'vs', alarm.away, 'match_id:', alarm.match_id);
            openMatchModalById(
                alarm.match_id, 
                alarm.home, 
                alarm.away, 
                'moneyway_1x2', 
                alarm.league
            );
        };
        
        return pill;
    };
    
    latest10.forEach((alarm, index) => tickerTrack.appendChild(createPill(alarm, index, false)));
    latest10.forEach((alarm, index) => tickerTrack.appendChild(createPill(alarm, index, true)));
    
    requestAnimationFrame(() => {
        const pillCount = latest10.length;
        const avgPillWidth = 320;
        const gap = 16;
        const totalWidth = (avgPillWidth + gap) * pillCount;
        
        const speed = 240;
        const duration = totalWidth / speed;
        const finalDuration = Math.max(duration, 5);
        
        tickerTrack.style.animation = `tickerScroll ${finalDuration}s linear infinite`;
        
        console.log(`[Ticker] ${pillCount} alarms, duration: ${finalDuration.toFixed(1)}s`);
    });
}

function addToAlertsHistory(alarm) {
    const alarmId = `${alarm.type}_${alarm.home}_${alarm.away}_${alarm.side || ''}_${Date.now()}`;
    
    const exists = alertsHistory.find(a => 
        a.type === alarm.type && 
        a.home === alarm.home && 
        a.away === alarm.away && 
        a.side === alarm.side &&
        (Date.now() - a.timestamp) < 60000
    );
    
    if (exists) return;
    
    const historyEntry = {
        id: alarmId,
        type: alarm.type,
        name: alarm.name,
        icon: alarm.icon,
        color: alarm.color,
        home: alarm.home,
        away: alarm.away,
        market: alarm.side || '',
        moneyDiff: alarm.money_text || '',
        oddsOld: alarm.odds_from || '',
        oddsNew: alarm.odds_to || '',
        detail: alarm.detail || '',
        timestamp: Date.now()
    };
    
    alertsHistory.unshift(historyEntry);
    
    if (alertsHistory.length > MAX_ALERTS_HISTORY) {
        alertsHistory = alertsHistory.slice(0, MAX_ALERTS_HISTORY);
    }
}

function updateAlarmBadge(count) {
    const badge = document.getElementById('alarmCountBadge');
    if (badge) {
        const displayCount = count !== undefined ? count : alertsHistory.length;
        badge.textContent = displayCount > 99 ? '99+' : displayCount;
        badge.style.display = displayCount > 0 ? 'inline-block' : 'none';
    }
}

let groupedAlarmsData = [];
let expandedAlarmGroups = new Set();

function openAlarmPanel() {
    document.getElementById('alarmDrawerOverlay').classList.add('open');
    document.getElementById('alarmDrawer').classList.add('open');
    document.body.style.overflow = 'hidden';
    
    renderAlarmListFromMaster();
}

function closeAlarmPanel() {
    document.getElementById('alarmDrawerOverlay').classList.remove('open');
    document.getElementById('alarmDrawer').classList.remove('open');
    document.body.style.overflow = '';
}

function renderAlarmListFromMaster() {
    const container = document.getElementById('alarmDrawerContent');
    if (!container) return;
    
    const typeFilter = document.getElementById('alarmTypeFilter')?.value || 'all';
    const searchQuery = document.getElementById('alarmTeamSearch')?.value.trim().toLowerCase() || '';
    
    let filtered = [...masterAlarmData];
    
    if (searchQuery) {
        filtered = filtered.filter(a => 
            (a.home || '').toLowerCase().includes(searchQuery) || 
            (a.away || '').toLowerCase().includes(searchQuery)
        );
    }
    
    if (typeFilter !== 'all') {
        filtered = filtered.filter(a => (a.type || '').includes(typeFilter));
    }
    
    filtered.sort((a, b) => new Date(b.latest_time || 0) - new Date(a.latest_time || 0));
    
    groupedAlarmsData = filtered;
    alarmTotalCount = filtered.length;
    alarmEventCount = filtered.reduce((sum, g) => sum + (g.count || 0), 0);
    
    if (filtered.length === 0) {
        container.innerHTML = '<div class="alarm-empty">Aktif alarm yok</div>';
        return;
    }
    
    renderGroupedAlarmList();
}

function filterAlarms() {
    renderAlarmListFromMaster();
}

let alarmSearchTimeout = null;

function debounceAlarmSearch() {
    const searchInput = document.getElementById('alarmTeamSearch');
    const clearBtn = document.getElementById('searchClearBtn');
    
    if (clearBtn) {
        clearBtn.style.display = searchInput?.value.trim() ? 'flex' : 'none';
    }
    
    if (alarmSearchTimeout) {
        clearTimeout(alarmSearchTimeout);
    }
    
    alarmSearchTimeout = setTimeout(() => {
        filterAlarms();
    }, 300);
}

function clearAlarmSearch() {
    const searchInput = document.getElementById('alarmTeamSearch');
    const clearBtn = document.getElementById('searchClearBtn');
    
    if (searchInput) {
        searchInput.value = '';
    }
    if (clearBtn) {
        clearBtn.style.display = 'none';
    }
    
    filterAlarms();
}

function renderGroupedAlarmList() {
    const container = document.getElementById('alarmDrawerContent');
    if (!container) return;
    
    if (groupedAlarmsData.length === 0) {
        container.innerHTML = '<div class="alarm-empty">Filtre kriterlerine uygun alarm yok</div>';
        return;
    }
    
    const countInfo = alarmTotalCount > 0 
        ? `<div class="alarm-count-info">${groupedAlarmsData.length} maç · ${alarmEventCount} alarm</div>` 
        : '';
    
    const alarmsHtml = groupedAlarmsData.map((group, idx) => {
        const groupId = `${group.type}_${group.home}_${group.away}`;
        const isExpanded = expandedAlarmGroups.has(groupId);
        const latestTime = group.latest_time ? formatAlarmTime(group.latest_time) : '';
        const moneyText = group.max_money > 0 ? `+£${group.max_money.toLocaleString()}` : '';
        const dropText = group.max_drop > 0 ? `${group.max_drop.toFixed(2)} drop` : '';
        
        let eventsHtml = '';
        if (isExpanded && group.events && group.events.length > 0) {
            eventsHtml = `
                <div class="alarm-events-timeline">
                    <div class="events-title">Alarm Geçmişi (${group.events.length} olay)</div>
                    ${group.events.map(e => `
                        <div class="event-item">
                            <div class="event-time">${formatAlarmTime(e.timestamp)}</div>
                            ${e.side ? `<span class="selection-pill">${e.side}</span>` : ''}
                            <div class="event-detail">${e.detail || e.name}</div>
                            ${e.money_diff > 0 ? `<div class="event-money">+£${e.money_diff.toLocaleString()}</div>` : ''}
                        </div>
                    `).join('')}
                </div>
            `;
        }
        
        return `
            <div class="alarm-group-card ${isExpanded ? 'expanded' : ''}" 
                 style="--alarm-color: ${group.color};">
                <div class="alarm-group-header" onclick="toggleAlarmGroup('${groupId}')">
                    <div class="alarm-group-left">
                        <span class="alarm-icon">${group.icon}</span>
                        <div class="alarm-group-info">
                            <div class="alarm-group-type">${group.name}</div>
                            <div class="alarm-group-match">${group.home} - ${group.away}</div>
                        </div>
                    </div>
                    <div class="alarm-group-right">
                        <div class="alarm-group-badge">x${group.count}</div>
                        <div class="alarm-group-stats">
                            ${moneyText ? `<span class="stat-money">${moneyText}</span>` : ''}
                            ${dropText ? `<span class="stat-drop">${dropText}</span>` : ''}
                        </div>
                        <div class="alarm-group-time">${latestTime}</div>
                        <div class="alarm-expand-icon">${isExpanded ? '▼' : '▶'}</div>
                    </div>
                </div>
                ${eventsHtml}
                <div class="alarm-group-action" onclick="event.stopPropagation(); goToMatchFromAlarm('${escapeHtml(group.home)}', '${escapeHtml(group.away)}', '${escapeHtml(group.match_id || '')}', '${escapeHtml(group.league || '')}')">
                    Maç Detayı →
                </div>
            </div>
        `;
    }).join('');
    
    const loadMoreHtml = alarmHasMore 
        ? '<div class="alarm-load-more">Daha fazla alarm için aşağı kaydırın...</div>' 
        : '';
    
    container.innerHTML = countInfo + alarmsHtml + loadMoreHtml;
}

function toggleAlarmGroup(groupId) {
    if (expandedAlarmGroups.has(groupId)) {
        expandedAlarmGroups.delete(groupId);
    } else {
        expandedAlarmGroups.add(groupId);
    }
    renderGroupedAlarmList();
}

function formatAlarmTime(timestamp) {
    if (!timestamp) return '';
    try {
        const date = new Date(timestamp);
        return date.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' });
    } catch {
        return timestamp.substring(11, 16) || '';
    }
}

function renderAlarmList() {
    const container = document.getElementById('alarmDrawerContent');
    if (!container) return;
    
    const typeFilter = document.getElementById('alarmTypeFilter')?.value || 'all';
    const sortBy = document.getElementById('alarmSortBy')?.value || 'newest';
    
    let filtered = [...alertsHistory];
    
    if (typeFilter !== 'all') {
        filtered = filtered.filter(a => a.type === typeFilter);
    }
    
    if (sortBy === 'money') {
        filtered.sort((a, b) => {
            const moneyA = parseFloat(String(a.moneyDiff).replace(/[^0-9.-]/g, '')) || 0;
            const moneyB = parseFloat(String(b.moneyDiff).replace(/[^0-9.-]/g, '')) || 0;
            return moneyB - moneyA;
        });
    } else if (sortBy === 'odds') {
        filtered.sort((a, b) => {
            const diffA = Math.abs((parseFloat(a.oddsNew) || 0) - (parseFloat(a.oddsOld) || 0));
            const diffB = Math.abs((parseFloat(b.oddsNew) || 0) - (parseFloat(b.oddsOld) || 0));
            return diffB - diffA;
        });
    } else {
        filtered.sort((a, b) => b.timestamp - a.timestamp);
    }
    
    if (filtered.length === 0) {
        container.innerHTML = '<div class="alarm-empty">Filtre kriterlerine uygun alarm yok</div>';
        return;
    }
    
    container.innerHTML = filtered.map(alarm => {
        const timeAgo = getTimeAgo(alarm.timestamp);
        const dateStr = new Date(alarm.timestamp).toLocaleString('tr-TR', {
            day: '2-digit', month: '2-digit', year: 'numeric',
            hour: '2-digit', minute: '2-digit'
        });
        const oddsText = (alarm.oddsOld && alarm.oddsNew) 
            ? `${parseFloat(alarm.oddsOld).toFixed(2)} → ${parseFloat(alarm.oddsNew).toFixed(2)}`
            : '';
        
        return `
            <div class="alarm-list-card" 
                 style="--alarm-color: ${alarm.color};"
                 onclick="goToMatchFromAlarm('${escapeHtml(alarm.home)}', '${escapeHtml(alarm.away)}', '${escapeHtml(alarm.match_id || '')}', '${escapeHtml(alarm.league || '')}')">
                <div class="alarm-card-header">
                    <div class="alarm-card-type">
                        <span class="icon">${alarm.icon}</span>
                        <span>${alarm.name}</span>
                    </div>
                    <div class="alarm-card-time">
                        <div>${timeAgo}</div>
                        <div>${dateStr}</div>
                    </div>
                </div>
                <div class="alarm-card-match">${alarm.home} – ${alarm.away}</div>
                <div class="alarm-card-details">
                    ${alarm.moneyDiff ? `<span class="alarm-card-money">${alarm.moneyDiff}</span>` : ''}
                    ${alarm.market ? `<span class="alarm-card-market">${alarm.market}</span>` : ''}
                    ${oddsText ? `<span class="alarm-card-odds">${oddsText}</span>` : ''}
                </div>
            </div>
        `;
    }).join('');
}

function getTimeAgo(timestamp) {
    const seconds = Math.floor((Date.now() - timestamp) / 1000);
    if (seconds < 60) return 'Az önce';
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes} dk önce`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours} saat önce`;
    const days = Math.floor(hours / 24);
    return `${days} gün önce`;
}

function goToMatchFromAlarm(home, away, matchId, league) {
    closeAlarmPanel();
    
    const homeLower = home.trim().toLowerCase();
    const awayLower = away.trim().toLowerCase();
    
    const foundMatch = matches.find(m => 
        m.home_team.trim().toLowerCase() === homeLower && 
        m.away_team.trim().toLowerCase() === awayLower
    );
    
    console.log('[Alarm→Match] Searching:', home, 'vs', away, '| Found:', foundMatch ? 'YES' : 'NO');
    
    if (foundMatch) {
        openMatchModalDirect(foundMatch);
    } else {
        console.log('[Alarm→Match] Not in matches list, opening directly with API');
        openMatchDirectly(home, away, league);
    }
}

function openMatchModalDirect(match) {
    selectedMatch = match;
    selectedChartMarket = currentMarket;
    previousOddsData = null;
    modalOddsData = match.odds || match.details || null;
    
    modalSmartMoneyEventsOpen = false;
    const wrapper = document.getElementById('modalEventsGridWrapper');
    const chevron = document.getElementById('modalEventsChevron');
    if (wrapper) {
        wrapper.classList.remove('expanded');
        wrapper.classList.add('collapsed');
    }
    if (chevron) {
        chevron.classList.remove('rotated');
    }
    
    console.log('[Alarm→Match] Opening modal for:', match.home_team, 'vs', match.away_team);
    
    document.getElementById('modalMatchTitle').textContent = 
        `${match.home_team} vs ${match.away_team}`;
    document.getElementById('modalLeague').textContent = 
        `${match.league || ''} • ${match.date || ''}`;
    
    updateMatchInfoCard();
    
    document.querySelectorAll('#modalChartTabs .chart-tab').forEach(t => {
        t.classList.remove('active');
        if (t.dataset.market === selectedChartMarket) {
            t.classList.add('active');
        }
    });
    
    document.getElementById('modalOverlay').classList.add('active');
    loadChartWithTrends(match.home_team, match.away_team, selectedChartMarket);
    loadMatchAlarms(match.home_team, match.away_team);
}

function openMatchDirectly(home, away, league) {
    selectedMatch = { 
        home_team: home, 
        away_team: away, 
        league: league || '', 
        date: ''
    };
    selectedChartMarket = currentMarket;
    previousOddsData = null;
    modalOddsData = null;
    
    modalSmartMoneyEventsOpen = false;
    const wrapper = document.getElementById('modalEventsGridWrapper');
    const chevron = document.getElementById('modalEventsChevron');
    if (wrapper) {
        wrapper.classList.remove('expanded');
        wrapper.classList.add('collapsed');
    }
    if (chevron) {
        chevron.classList.remove('rotated');
    }
    
    document.getElementById('modalMatchTitle').textContent = `${home} vs ${away}`;
    document.getElementById('modalLeague').textContent = league || 'Yükleniyor...';
    
    updateMatchInfoCard();
    
    document.querySelectorAll('#modalChartTabs .chart-tab').forEach(t => {
        t.classList.remove('active');
        if (t.dataset.market === selectedChartMarket) {
            t.classList.add('active');
        }
    });
    
    document.getElementById('modalOverlay').classList.add('active');
    loadChartWithTrends(home, away, selectedChartMarket);
    loadMatchAlarms(home, away);
}

function openMatchModalById(matchId, home, away, market, league, alarmType) {
    console.log('[Ticker→Match] Searching:', home, 'vs', away);
    
    const homeLower = home.trim().toLowerCase();
    const awayLower = away.trim().toLowerCase();
    
    const foundMatch = matches.find(m => 
        m.home_team.trim().toLowerCase() === homeLower && 
        m.away_team.trim().toLowerCase() === awayLower
    );
    
    console.log('[Ticker→Match] Found:', foundMatch ? 'YES' : 'NO');
    
    if (foundMatch) {
        openMatchModalDirect(foundMatch);
    } else {
        console.log('[Ticker→Match] Not in matches list, opening directly with API');
        openMatchDirectly(home, away, league);
    }
}

async function openMatchModalByTeams(home, away, alarmType) {
    const homeLower = home.trim().toLowerCase();
    const awayLower = away.trim().toLowerCase();
    
    const foundMatch = matches.find(m => 
        m.home_team.trim().toLowerCase() === homeLower && 
        m.away_team.trim().toLowerCase() === awayLower
    );
    
    if (foundMatch) {
        openMatchModalDirect(foundMatch);
    } else {
        console.log('[Modal] Match not in current list, fetching from API:', home, 'vs', away);
        
        selectedMatch = { home_team: home, away_team: away, league: '', date: '' };
        selectedChartMarket = 'moneyway_1x2';
        previousOddsData = null;
        modalOddsData = null;
        
        modalSmartMoneyEventsOpen = false;
        const wrapper = document.getElementById('modalEventsGridWrapper');
        const chevron = document.getElementById('modalEventsChevron');
        if (wrapper) {
            wrapper.classList.remove('expanded');
            wrapper.classList.add('collapsed');
        }
        if (chevron) {
            chevron.classList.remove('rotated');
        }
        
        document.getElementById('modalMatchTitle').textContent = `${home} vs ${away}`;
        document.getElementById('modalLeague').textContent = 'Yükleniyor...';
        
        document.querySelectorAll('#modalChartTabs .chart-tab').forEach(t => {
            t.classList.remove('active');
            if (t.dataset.market === selectedChartMarket) {
                t.classList.add('active');
            }
        });
        
        document.getElementById('modalOverlay').classList.add('active');
        
        try {
            const response = await fetch(`/api/match/details?home=${encodeURIComponent(home)}&away=${encodeURIComponent(away)}`);
            const data = await response.json();
            
            if (data.success && data.match) {
                selectedMatch = data.match;
                modalOddsData = data.match.odds || data.match.details || null;
                
                document.getElementById('modalMatchTitle').textContent = `${home} vs ${away}`;
                document.getElementById('modalLeague').textContent = data.match.league || '';
                
                console.log('[Modal] Match data loaded from API:', modalOddsData);
            }
        } catch (error) {
            console.error('[Modal] Failed to fetch match details:', error);
        }
        
        updateMatchInfoCard();
        loadChartWithTrends(home, away, selectedChartMarket);
        loadMatchAlarms(home, away);
    }
}

function getAlarmRGB(color) {
    const colorMap = {
        '#ef4444': '239, 68, 68',
        '#22c55e': '34, 197, 94',
        '#f59e0b': '245, 158, 11',
        '#3b82f6': '59, 130, 246',
        '#eab308': '234, 179, 8',
        '#a855f7': '168, 85, 247'
    };
    return colorMap[color] || '88, 166, 255';
}

function groupAlarmsByType(alarms) {
    const grouped = {};
    alarms.forEach(alarm => {
        const key = alarm.type;
        if (!grouped[key]) {
            grouped[key] = {
                ...alarm,
                count: 1,
                sides: [alarm.side],
                allSides: [alarm.side],
                allDetails: [alarm.detail],
                allTimestamps: [alarm.timestamp],
                allMoneyDiffs: [alarm.money_diff || 0]
            };
        } else {
            grouped[key].count++;
            grouped[key].allSides.push(alarm.side);
            if (alarm.side && !grouped[key].sides.includes(alarm.side)) {
                grouped[key].sides.push(alarm.side);
            }
            grouped[key].allDetails.push(alarm.detail);
            grouped[key].allTimestamps.push(alarm.timestamp);
            grouped[key].allMoneyDiffs.push(alarm.money_diff || 0);
        }
    });
    return Object.values(grouped);
}

function formatAlarmDateTime(timestamp) {
    if (!timestamp) return '';
    try {
        const date = new Date(timestamp);
        if (isNaN(date.getTime())) {
            if (timestamp.includes(' ')) {
                const [datePart, timePart] = timestamp.split(' ');
                const time = timePart ? timePart.substring(0, 5) : '';
                return `${datePart.substring(5, 10)} · ${time}`;
            }
            return timestamp.substring(0, 16);
        }
        const day = date.getDate().toString().padStart(2, '0');
        const months = ['Oca', 'Şub', 'Mar', 'Nis', 'May', 'Haz', 'Tem', 'Ağu', 'Eyl', 'Eki', 'Kas', 'Ara'];
        const month = months[date.getMonth()];
        const hours = date.getHours().toString().padStart(2, '0');
        const mins = date.getMinutes().toString().padStart(2, '0');
        return `${day} ${month} · ${hours}:${mins}`;
    } catch {
        return timestamp.substring(0, 16) || '';
    }
}

function showAlarmHistoryPopover(badge, data) {
    closeAlarmHistoryPopover();
    
    const popover = document.createElement('div');
    popover.className = 'alarm-history-popover';
    popover.id = 'alarmHistoryPopover';
    
    const events = [];
    for (let i = 0; i < data.count; i++) {
        events.push({
            timestamp: data.timestamps[i] || '',
            detail: data.details[i] || data.name,
            moneyDiff: data.moneyDiffs[i] || 0,
            side: data.sides ? data.sides[i] : ''
        });
    }
    
    events.sort((a, b) => {
        const dateA = new Date(a.timestamp);
        const dateB = new Date(b.timestamp);
        return dateB - dateA;
    });
    
    const eventsList = events.map(event => {
        const timeStr = formatAlarmTime(event.timestamp);
        const sidePill = event.side ? `<span class="selection-pill">${event.side}</span>` : '';
        return `
            <div class="popover-event-item">
                <div class="popover-event-time">${timeStr}</div>
                ${sidePill}
                <div class="popover-event-detail">${event.detail}</div>
                ${event.moneyDiff > 0 ? `<div class="popover-event-money" style="color: ${data.color};">+£${event.moneyDiff.toLocaleString()}</div>` : ''}
            </div>
        `;
    });
    
    popover.innerHTML = `
        <div class="popover-header" style="border-color: ${data.color};">
            <span class="popover-icon">${data.icon}</span>
            <span class="popover-title">ALARM GEÇMİŞİ (${data.count} OLAY)</span>
            <button class="popover-close" onclick="closeAlarmHistoryPopover()">✕</button>
        </div>
        <div class="popover-events-list">
            ${eventsList.join('')}
        </div>
    `;
    
    document.body.appendChild(popover);
    
    const rect = badge.getBoundingClientRect();
    const popoverRect = popover.getBoundingClientRect();
    
    let left = rect.left + rect.width / 2 - popoverRect.width / 2;
    let top = rect.bottom + 8;
    
    if (left < 10) left = 10;
    if (left + popoverRect.width > window.innerWidth - 10) {
        left = window.innerWidth - popoverRect.width - 10;
    }
    if (top + popoverRect.height > window.innerHeight - 10) {
        top = rect.top - popoverRect.height - 8;
    }
    
    popover.style.left = `${left}px`;
    popover.style.top = `${top}px`;
    popover.style.opacity = '1';
    popover.style.transform = 'translateY(0)';
    
    setTimeout(() => {
        document.addEventListener('click', closePopoverOnClickOutside);
    }, 100);
}

function closeAlarmHistoryPopover() {
    const popover = document.getElementById('alarmHistoryPopover');
    if (popover) {
        popover.remove();
    }
    document.removeEventListener('click', closePopoverOnClickOutside);
}

function closePopoverOnClickOutside(e) {
    const popover = document.getElementById('alarmHistoryPopover');
    if (popover && !popover.contains(e.target)) {
        closeAlarmHistoryPopover();
    }
}

function formatAlarmTime(timestamp) {
    if (!timestamp) return '';
    try {
        const date = new Date(timestamp);
        if (isNaN(date.getTime())) {
            if (timestamp.includes(' ')) {
                return timestamp.split(' ')[1]?.substring(0, 5) || '';
            }
            return '';
        }
        return date.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' });
    } catch {
        return timestamp.substring(11, 16) || '';
    }
}

async function loadMatchAlarms(home, away) {
    try {
        const response = await fetch(`/api/match/alarms?home=${encodeURIComponent(home)}&away=${encodeURIComponent(away)}`);
        const data = await response.json();
        
        const container = document.getElementById('matchAlarmsContainer');
        if (!container) return;
        
        if (!data.alarms || data.alarms.length === 0) {
            container.innerHTML = '<div class="no-alarms">Bu maç için aktif alarm yok</div>';
            highlightedAlarmType = null;
            return;
        }
        
        const groupedAlarms = groupAlarmsByType(data.alarms);
        
        if (highlightedAlarmType) {
            groupedAlarms.sort((a, b) => {
                if (a.type === highlightedAlarmType) return -1;
                if (b.type === highlightedAlarmType) return 1;
                return 0;
            });
        }
        
        const alarmsHtml = groupedAlarms.map(alarm => {
            const isHighlighted = alarm.type === highlightedAlarmType;
            const rgb = getAlarmRGB(alarm.color);
            const sidesText = alarm.sides.filter(s => s).join(', ');
            
            const latestTimestamp = alarm.allTimestamps && alarm.allTimestamps[0] 
                ? formatAlarmDateTime(alarm.allTimestamps[0]) 
                : formatAlarmDateTime(alarm.timestamp);
            
            let countBadge = '';
            if (alarm.count > 1) {
                const badgeId = `badge_${alarm.type}_${Date.now()}`;
                window[badgeId] = {
                    name: alarm.name,
                    icon: alarm.icon,
                    color: alarm.color,
                    count: alarm.count,
                    timestamps: alarm.allTimestamps,
                    details: alarm.allDetails,
                    moneyDiffs: alarm.allMoneyDiffs || [],
                    sides: alarm.allSides || []
                };
                countBadge = `<span class="alarm-count-badge clickable" data-badge-id="${badgeId}" onclick="event.stopPropagation(); showAlarmHistoryPopover(this, window['${badgeId}'])">x${alarm.count}</span>`;
            }
            
            return `
                <div class="alarm-card ${isHighlighted ? 'highlighted' : ''}" 
                     style="--alarm-color: ${alarm.color}; --alarm-rgb: ${rgb};">
                    <div class="alarm-header">
                        <div class="alarm-header-left">
                            <span class="alarm-icon">${alarm.icon}</span>
                            <span class="alarm-name">${alarm.name}</span>
                            ${countBadge}
                        </div>
                        <div class="alarm-tags">
                            ${sidesText ? `<span class="alarm-tag market">${sidesText}</span>` : ''}
                            <span class="alarm-tag time">${latestTimestamp}</span>
                        </div>
                    </div>
                    <div class="alarm-detail">${alarm.detail}</div>
                    <div class="alarm-description">${alarm.description}</div>
                </div>
            `;
        }).join('');
        
        container.innerHTML = alarmsHtml;
        highlightedAlarmType = null;
        
    } catch (error) {
        console.error('[Match Alarms] Error:', error);
        highlightedAlarmType = null;
    }
}

let oddsTrendCache = {};

async function loadOddsTrend(market) {
    if (!market.startsWith('dropping')) {
        oddsTrendCache = {};
        return;
    }
    
    try {
        const response = await fetch(`/api/odds-trend/${market}`);
        const result = await response.json();
        oddsTrendCache = result.data || {};
        console.log(`[Odds Trend] Loaded ${Object.keys(oddsTrendCache).length} matches for ${market}`);
    } catch (error) {
        console.error('[Odds Trend] Error loading:', error);
        oddsTrendCache = {};
    }
}

function generateSparklineSVG(values, trend) {
    if (!values || values.length < 2) {
        return '';
    }
    
    const width = 40;
    const height = 16;
    const padding = 2;
    
    const validValues = values.filter(v => v !== null && v !== undefined);
    if (validValues.length < 2) return '';
    
    const min = Math.min(...validValues);
    const max = Math.max(...validValues);
    const range = max - min || 1;
    
    const points = validValues.map((val, idx) => {
        const x = padding + (idx / (validValues.length - 1)) * (width - 2 * padding);
        const y = height - padding - ((val - min) / range) * (height - 2 * padding);
        return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
    
    let strokeColor = '#6b7280';
    if (trend === 'down') {
        strokeColor = '#ef4444';
    } else if (trend === 'up') {
        strokeColor = '#22c55e';
    }
    
    return `<svg class="sparkline-svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
        <polyline points="${points}" fill="none" stroke="${strokeColor}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>`;
}

function getTrendArrowHTML(trend, pctChange) {
    if (trend === 'down') {
        return `<span class="trend-arrow-drop trend-down-drop">↓</span>`;
    } else if (trend === 'up') {
        return `<span class="trend-arrow-drop trend-up-drop">↑</span>`;
    }
    return `<span class="trend-arrow-drop trend-stable-drop">↔</span>`;
}

function formatPctChange(pctChange, trend) {
    if (pctChange === 0 || pctChange === null || pctChange === undefined) {
        return '';
    }
    
    const sign = pctChange > 0 ? '+' : '';
    const absVal = Math.abs(pctChange).toFixed(1);
    
    let colorClass = 'pct-stable';
    if (trend === 'down') {
        colorClass = 'pct-down';
    } else if (trend === 'up') {
        colorClass = 'pct-up';
    }
    
    return `<span class="pct-change ${colorClass}">${sign}${pctChange.toFixed(1)}%</span>`;
}

function getOddsTrendData(home, away, selection) {
    const key = `${home}|${away}`;
    const matchData = oddsTrendCache[key];
    
    if (!matchData || !matchData.values) {
        return null;
    }
    
    return matchData.values[selection] || null;
}

function renderOddsWithTrend(oddsValue, trendData) {
    const formattedOdds = formatOdds(oddsValue);
    
    if (!trendData || !trendData.history || trendData.history.length < 2) {
        const flatSparkline = generateFlatSparklineSVG();
        return `
            <div class="odds-trend-cell odds-trend-no-data">
                <div class="sparkline-container">${flatSparkline}</div>
                <div class="odds-value-trend">${formattedOdds}</div>
                <span class="trend-arrow-drop trend-stable-drop">→</span>
            </div>
        `;
    }
    
    const sparkline = generateSparklineSVG(trendData.history, trendData.trend);
    const pctHtml = formatPctChange(trendData.pct_change, trendData.trend);
    const arrowHtml = getTrendArrowHTML(trendData.trend, trendData.pct_change);
    
    const tooltipData = JSON.stringify({
        old: trendData.old,
        new: trendData.new,
        pct: trendData.pct_change,
        trend: trendData.trend
    }).replace(/"/g, '&quot;');
    
    return `
        <div class="odds-trend-cell" data-tooltip="${tooltipData}">
            <div class="sparkline-container">${sparkline}</div>
            <div class="odds-value-trend">${formattedOdds}</div>
            ${pctHtml}
            ${arrowHtml}
        </div>
    `;
}

function renderDrop1X2Cell(label, oddsValue, trendData) {
    const formattedOdds = formatOdds(oddsValue);
    
    if (!trendData || !trendData.history || trendData.history.length < 2) {
        const flatSparkline = generateFlatSparklineSVG();
        return `
            <div class="drop-mini-card">
                <div class="drop-spark">${flatSparkline}</div>
                <div class="drop-odds">${formattedOdds}</div>
            </div>
        `;
    }
    
    const sparkline = generateSparklineSVG(trendData.history, trendData.trend);
    const pctHtml = formatPctChange(trendData.pct_change, trendData.trend);
    const arrowHtml = getTrendArrowHTML(trendData.trend, trendData.pct_change);
    
    const tooltipData = JSON.stringify({
        old: trendData.old,
        new: trendData.new,
        pct: trendData.pct_change,
        trend: trendData.trend
    }).replace(/"/g, '&quot;');
    
    const changeClass = trendData.trend === 'up' ? 'positive' : (trendData.trend === 'down' ? 'negative' : '');
    
    return `
        <div class="drop-mini-card" data-tooltip="${tooltipData}">
            <div class="drop-spark">${sparkline}</div>
            <div class="drop-odds">${formattedOdds}</div>
            <div class="drop-change ${changeClass}">${pctHtml}${arrowHtml}</div>
        </div>
    `;
}

function generateFlatSparklineSVG() {
    const width = 40;
    const height = 16;
    const y = height / 2;
    
    return `<svg class="sparkline-svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
        <line x1="2" y1="${y}" x2="${width - 2}" y2="${y}" stroke="#6b7280" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`;
}

function createTrendTooltip() {
    let tooltip = document.getElementById('oddsTrendTooltip');
    if (!tooltip) {
        tooltip = document.createElement('div');
        tooltip.id = 'oddsTrendTooltip';
        tooltip.className = 'odds-trend-tooltip';
        document.body.appendChild(tooltip);
    }
    return tooltip;
}

function showTrendTooltip(event) {
    const cell = event.currentTarget;
    const tooltipData = cell.dataset.tooltip;
    if (!tooltipData) return;
    
    try {
        const data = JSON.parse(tooltipData);
        const tooltip = createTrendTooltip();
        
        const trendText = data.trend === 'down' ? 'Oran düştü' : 
                         data.trend === 'up' ? 'Oran yükseldi' : 'Değişim yok';
        const trendClass = data.trend === 'down' ? 'tooltip-down' : 
                          data.trend === 'up' ? 'tooltip-up' : 'tooltip-stable';
        
        const diff = data.new - data.old;
        const diffSign = diff > 0 ? '+' : '';
        
        tooltip.innerHTML = `
            <div class="tooltip-title">Son 6 Saatlik Değişim</div>
            <div class="tooltip-row">
                <span class="tooltip-label">Eski oran:</span>
                <span class="tooltip-value">${data.old ? data.old.toFixed(2) : '-'}</span>
            </div>
            <div class="tooltip-row">
                <span class="tooltip-label">Yeni oran:</span>
                <span class="tooltip-value">${data.new ? data.new.toFixed(2) : '-'}</span>
            </div>
            <div class="tooltip-row">
                <span class="tooltip-label">Değişim:</span>
                <span class="tooltip-value ${trendClass}">${diffSign}${diff.toFixed(2)} (${data.pct > 0 ? '+' : ''}${data.pct}%)</span>
            </div>
            <div class="tooltip-trend ${trendClass}">${trendText}</div>
        `;
        
        const rect = cell.getBoundingClientRect();
        tooltip.style.left = `${rect.left + rect.width / 2}px`;
        tooltip.style.top = `${rect.top - 10}px`;
        tooltip.classList.add('visible');
    } catch (e) {
        console.error('[Tooltip] Parse error:', e);
    }
}

function hideTrendTooltip() {
    const tooltip = document.getElementById('oddsTrendTooltip');
    if (tooltip) {
        tooltip.classList.remove('visible');
    }
}

function attachTrendTooltipListeners() {
    document.querySelectorAll('.odds-trend-cell, .drop-mini-card[data-tooltip]').forEach(cell => {
        cell.addEventListener('mouseenter', showTrendTooltip);
        cell.addEventListener('mouseleave', hideTrendTooltip);
    });
}
