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
let dateFilterMode = 'TODAY';
let chartTimeRange = '10min';
let currentChartHistoryData = [];
let chartViewMode = 'percent';
let isClientMode = true;
let isAlarmsPageActive = false;
let matchesDisplayCount = 20;

const APP_TIMEZONE = 'Europe/Istanbul';

function showToast(message, type = 'info') {
    const existing = document.querySelector('.toast-notification');
    if (existing) existing.remove();
    
    const toast = document.createElement('div');
    toast.className = `toast-notification toast-${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    
    setTimeout(() => toast.classList.add('show'), 10);
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

/**
 * TEK KAYNAK: Tüm timestamp dönüşümleri bu fonksiyon üzerinden yapılmalı
 * 
 * VERİ SÖZLEŞMESİ:
 * - Backend (Supabase) offset'li timestamp gönderdiğinde: UTC (+00:00 veya Z) → TR'ye çevrilir
 * - Backend offset'siz ISO gönderdiğinde: ZATEN TR saatinde (scraper TR'de çalışıyor)
 * - Arbworld formatı: ZATEN TR saatinde (Türkiye'ye göre maç saatleri)
 * 
 * Formatlar:
 * 1. UTC with offset: "2025-11-28T22:48:21+00:00" veya "...Z" → UTC→TR dönüşümü
 * 2. Other offset: "+01:00", "+02:00" vb → parseZone ile yorumla → TR'ye çevir  
 * 3. Arbworld format: "30.Nov 23:55:00" → ZATEN TR saatinde, direkt yorumla
 * 4. ISO no offset: "2025-11-29T01:21:38" → ZATEN TR saatinde (backend TR-local)
 * 5. Numeric (ms): timestamp → TR'ye çevir
 */
function toTurkeyTime(raw) {
    if (!raw) return null;
    
    try {
        // 1) Numeric timestamp (ms)
        if (typeof raw === 'number') {
            return dayjs(raw).tz(APP_TIMEZONE);
        }
        
        const str = String(raw).trim();
        
        // 2) UTC string with 'Z' suffix
        if (str.endsWith('Z')) {
            return dayjs.utc(str).tz(APP_TIMEZONE);
        }
        
        // 3) UTC string with '+00:00' suffix
        if (str.endsWith('+00:00')) {
            return dayjs.utc(str.replace('+00:00', 'Z')).tz(APP_TIMEZONE);
        }
        
        // 4) Timezone offset handling
        const offsetMatch = str.match(/([+-])(\d{2}):(\d{2})$/);
        if (offsetMatch) {
            // +03:00 zaten Turkey saati - offset'i kaldır ve TR olarak işaretle
            if (offsetMatch[1] === '+' && offsetMatch[2] === '03' && offsetMatch[3] === '00') {
                // Remove offset, keep the time as-is, mark as Istanbul
                const withoutOffset = str.replace(/\+03:00$/, '').replace(/\.\d+$/, '');
                return dayjs(withoutOffset).tz(APP_TIMEZONE, true);
            }
            // Diger offset'ler icin parseZone ile parse et ve Turkey'e cevir
            const parsed = dayjs.parseZone(str);
            if (!parsed.isValid()) return null;
            return parsed.tz(APP_TIMEZONE);
        }
        
        // 5) Arbworld format: "30.Nov 23:55:00" - UTC olarak gelir, TR'ye çevir (+3 saat)
        const arbworldMatch = str.match(/^(\d{1,2})\.(\w{3})\s*(\d{2}:\d{2}(?::\d{2})?)$/i);
        if (arbworldMatch) {
            const monthMap = {
                'Jan': 0, 'Feb': 1, 'Mar': 2, 'Apr': 3, 'May': 4, 'Jun': 5,
                'Jul': 6, 'Aug': 7, 'Sep': 8, 'Oct': 9, 'Nov': 10, 'Dec': 11
            };
            const day = parseInt(arbworldMatch[1]);
            const month = monthMap[arbworldMatch[2]];
            if (month === undefined) return dayjs(str).tz(APP_TIMEZONE, true);
            
            const timeParts = arbworldMatch[3].split(':').map(Number);
            const now = dayjs().tz(APP_TIMEZONE);
            const currentYear = now.year();
            
            // Year rollover logic: en yakın tarihi seç
            // ISO format ile UTC olarak parse et, sonra TR'ye çevir (+3 saat eklenir)
            const candidates = [currentYear - 1, currentYear, currentYear + 1].map(year => {
                const isoStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}T${arbworldMatch[3]}`;
                return dayjs.utc(isoStr).tz(APP_TIMEZONE);
            });
            
            const nowTR = dayjs().tz(APP_TIMEZONE);
            let best = candidates[1]; // default: current year
            let minDiff = Math.abs(candidates[1].diff(nowTR, 'day'));
            
            candidates.forEach(c => {
                if (!c.isValid()) return;
                const diff = Math.abs(c.diff(nowTR, 'day'));
                if (diff < minDiff) {
                    minDiff = diff;
                    best = c;
                }
            });
            
            return best.isValid() ? best : dayjs().tz(APP_TIMEZONE);
        }
        
        // 6) DD.MM.YYYY HH:MM format - ZATEN TR saatinde, dönüşüm yapma
        const ddmmMatch = str.match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})\s*(\d{2}):(\d{2})(?::(\d{2}))?$/);
        if (ddmmMatch) {
            const [, day, month, year, hour, min, sec] = ddmmMatch;
            const isoStr = `${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')}T${hour}:${min}:${sec || '00'}`;
            // Parse as local time, then mark as Istanbul WITHOUT conversion
            return dayjs(isoStr).tz(APP_TIMEZONE, true);
        }
        
        // 7) ISO format without offset: "2025-11-28T22:48:21" → already TR time
        //    Backend sends TR-local timestamps without offset - keepLocalTime=true
        if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/.test(str)) {
            return dayjs(str).tz(APP_TIMEZONE, true);
        }
        
        // 8) ISO date only: "2025-11-28" → TR timezone'da yorumla
        if (/^\d{4}-\d{2}-\d{2}$/.test(str)) {
            return dayjs(str).tz(APP_TIMEZONE, true);
        }
        
        // 9) HH:MM or HH:MM:SS only (no date) - bugünün tarihi ile birleştir
        if (/^\d{2}:\d{2}(:\d{2})?$/.test(str)) {
            const today = dayjs().tz(APP_TIMEZONE).format('YYYY-MM-DD');
            return dayjs(`${today}T${str}`).tz(APP_TIMEZONE, true);
        }
        
        // 10) Fallback: direkt TR'de yorumla (bilinmeyen format)
        const parsed = dayjs(str);
        if (parsed.isValid()) {
            return parsed.tz(APP_TIMEZONE, true);
        }
        
        return dayjs(str).tz(APP_TIMEZONE, true);
    } catch (e) {
        // Sessiz hata - gereksiz console spam önle
        return dayjs().tz(APP_TIMEZONE);
    }
}

function nowTurkey() {
    return dayjs().tz(APP_TIMEZONE);
}

function formatTurkeyTime(value, format = 'HH:mm') {
    const dt = toTurkeyTime(value);
    return dt ? dt.format(format) : '';
}

function formatTurkeyDateTime(value, format = 'DD.MM HH:mm') {
    const dt = toTurkeyTime(value);
    return dt ? dt.format(format) : '';
}

function isTodayTurkey(value) {
    const dt = toTurkeyTime(value);
    if (!dt) return false;
    return dt.format('YYYY-MM-DD') === nowTurkey().format('YYYY-MM-DD');
}

function isYesterdayTurkey(value) {
    const dt = toTurkeyTime(value);
    if (!dt) return false;
    return dt.format('YYYY-MM-DD') === nowTurkey().subtract(1, 'day').format('YYYY-MM-DD');
}

/**
 * VolumeShock için maça kaç saat kala hesaplama
 * @param {Object} alarm - Alarm objesi (match_date, trigger_at, hours_to_kickoff içerebilir)
 * @returns {number} Maça kalan saat (0 veya pozitif değer)
 */
function calculateHoursToKickoff(alarm) {
    // Önce mevcut değeri kontrol et
    if (alarm.hours_to_kickoff && alarm.hours_to_kickoff > 0) {
        return alarm.hours_to_kickoff;
    }
    
    // match_date ve trigger_at'tan hesapla
    const matchDateRaw = alarm.match_date || alarm.kickoff || alarm.fixture_date;
    const triggerAtRaw = alarm.trigger_at || alarm.event_time || alarm.created_at;
    
    if (!matchDateRaw || !triggerAtRaw) {
        return 0;
    }
    
    const matchTime = toTurkeyTime(matchDateRaw);
    const triggerTime = toTurkeyTime(triggerAtRaw);
    
    if (!matchTime || !triggerTime || !matchTime.isValid() || !triggerTime.isValid()) {
        return 0;
    }
    
    // Saat farkı hesapla (maç zamanı - alarm zamanı)
    const diffHours = matchTime.diff(triggerTime, 'hour', true);
    
    // Negatif değilse (maç henüz başlamamışsa) döndür
    return diffHours > 0 ? diffHours : 0;
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    })[c]);
}

document.addEventListener('DOMContentLoaded', () => {
    // Günün Maçları butonunu aktif yap (dateFilterMode = 'TODAY' default)
    const todayBtn = document.getElementById('todayBtn');
    if (todayBtn) todayBtn.classList.add('active');
    
    loadMatches();
    setupTabs();
    setupSearch();
    setupModalChartTabs();
    checkStatus();
    window.statusInterval = window.setInterval(checkStatus, 60000);
    
    setTimeout(() => preloadDropMarkets(), 2000);
});

function setupTabs() {
    document.querySelectorAll('.market-tabs .tab').forEach(tab => {
        tab.addEventListener('click', () => {
            const market = tab.dataset.market;
            
            if (market === 'alarms') {
                return;
            }
            
            if (isAlarmsPageActive) {
                hideAlarmsPage();
            }
            
            document.querySelectorAll('.market-tabs .tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            currentMarket = market;
            
            const isDropMarket = currentMarket.startsWith('dropping_');
            showTrendSortButtons(isDropMarket);
            
            if (!isDropMarket && (currentSortColumn === 'trend_down' || currentSortColumn === 'trend_up')) {
                currentSortColumn = 'date';
                currentSortDirection = 'desc';
            }
            
            matchesDisplayCount = 20;
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
    const colspan = currentMarket.includes('1x2') ? 7 : 6;
    tbody.innerHTML = `
        <tr class="loading-row">
            <td colspan="${colspan}">
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
        
        let apiUrl = `/api/matches?market=${currentMarket}`;
        if (dateFilterMode === 'YESTERDAY') {
            apiUrl += '&date_filter=yesterday';
        } else if (dateFilterMode === 'TODAY') {
            apiUrl += '&date_filter=today';
        }
        
        const response = await fetch(apiUrl);
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
                ${money ? `<div class="mw-money">${formatVolume(money)}</div>` : ''}
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
    
    const displayData = data.slice(0, matchesDisplayCount);
    const hasMore = data.length > matchesDisplayCount;
    const remainingCount = data.length - matchesDisplayCount;
    const colspan = currentMarket.includes('1x2') ? 7 : 6;
    
    let html = displayData.map((match, idx) => {
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
                const trendYesData = getOddsTrendData(match.home_team, match.away_team, 'oddsyes');
                const trendNoData = getOddsTrendData(match.home_team, match.away_team, 'oddsno');
                
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
    
    if (hasMore) {
        html += `
            <tr class="load-more-row">
                <td colspan="${colspan}">
                    <button class="load-more-btn" onclick="loadMoreMatches()">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="6 9 12 15 18 9"/>
                        </svg>
                        Daha Fazla Yukle (${remainingCount} kaldi)
                    </button>
                </td>
            </tr>
        `;
    }
    
    tbody.innerHTML = html;
    
    if (currentMarket.startsWith('dropping')) {
        setTimeout(() => attachTrendTooltipListeners(), 50);
    }
}

function loadMoreMatches() {
    matchesDisplayCount += 20;
    renderMatches(filteredMatches);
    
    const tbody = document.getElementById('matchesTableBody');
    const rows = tbody.querySelectorAll('tr:not(.load-more-row)');
    if (rows.length > 20) {
        rows[rows.length - 20]?.scrollIntoView({ behavior: 'smooth', block: 'start' });
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
    let str = String(value).replace(/[£€$,\s]/g, '');
    let multiplier = 1;
    if (str.toUpperCase().includes('M')) { 
        multiplier = 1000000; 
        str = str.replace(/M/gi, ''); 
    } else if (str.toUpperCase().includes('K')) { 
        multiplier = 1000; 
        str = str.replace(/K/gi, ''); 
    }
    const num = parseFloat(str) * multiplier;
    if (isNaN(num)) return '-';
    return '£' + Math.round(num).toLocaleString('en-GB');
}

function formatVolumeCompact(value) {
    if (!value || value === '-') return '-';
    let str = String(value).replace(/[£€$,\s]/g, '');
    let multiplier = 1;
    if (str.toUpperCase().includes('M')) { 
        multiplier = 1000000; 
        str = str.replace(/M/gi, ''); 
    } else if (str.toUpperCase().includes('K')) { 
        multiplier = 1000; 
        str = str.replace(/K/gi, ''); 
    }
    const num = parseFloat(str) * multiplier;
    if (isNaN(num)) return '-';
    if (num >= 1000000) {
        return '£' + (num / 1000000).toFixed(1) + 'M';
    } else if (num >= 1000) {
        return '£' + (num / 1000).toFixed(1) + 'k';
    }
    return '£' + Math.round(num).toLocaleString('en-GB');
}

function formatDateTwoLine(dateStr) {
    if (!dateStr || dateStr === '-') return '<div class="date-line">-</div>';
    
    const dt = toTurkeyTime(dateStr);
    if (dt && dt.isValid()) {
        const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
        const day = dt.date();
        const month = months[dt.month()];
        const time = dt.format('HH:mm');
        return `<div class="date-line">${day}.${month}</div><div class="time-line">${time}</div>`;
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
        if (selection === 'sel1') selKey = 'oddsyes';
        else if (selection === 'sel2') selKey = 'oddsno';
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
    
    const nowTR = nowTurkey();
    const todayStr = nowTR.format('YYYY-MM-DD');
    const yesterdayStr = nowTR.subtract(1, 'day').format('YYYY-MM-DD');
    
    function getMatchDateTR(dateStr) {
        const dt = toTurkeyTime(dateStr);
        if (!dt || !dt.isValid()) return null;
        return dt.format('YYYY-MM-DD');
    }
    
    function isDateTodayOrFutureTR(dateStr) {
        const dt = toTurkeyTime(dateStr);
        if (!dt || !dt.isValid()) return false;
        return dt.format('YYYY-MM-DD') >= todayStr;
    }
    
    if (dateFilterMode === 'YESTERDAY') {
        console.log('[Filter] YESTERDAY mode:', yesterdayStr);
        sortedData = sortedData.filter(m => {
            const matchDateStr = getMatchDateTR(m.date);
            if (!matchDateStr) return false;
            return matchDateStr === yesterdayStr;
        });
        console.log('[Filter] YESTERDAY filtered count:', sortedData.length);
    } else if (dateFilterMode === 'TODAY') {
        console.log('[Filter] TODAY mode:', todayStr);
        sortedData = sortedData.filter(m => {
            const matchDateStr = getMatchDateTR(m.date);
            if (!matchDateStr) return false;
            return matchDateStr === todayStr;
        });
        console.log('[Filter] TODAY filtered count:', sortedData.length);
    } else {
        console.log('[Filter] ALL mode (today + future):', todayStr, '+');
        sortedData = sortedData.filter(m => {
            return isDateTodayOrFutureTR(m.date);
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
    loadMatches();
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
    loadMatches();
}

function parseDate(dateStr) {
    if (!dateStr || dateStr === '-') return 0;
    const dt = toTurkeyTime(dateStr);
    return dt && dt.isValid() ? dt.valueOf() : 0;
}

function parseVolume(match) {
    const d = match.odds || match.details || {};
    let vol = d.Volume || '0';
    if (typeof vol === 'string') {
        let str = vol.replace(/[£€$,\s]/g, '');
        let multiplier = 1;
        if (str.toUpperCase().includes('M')) {
            multiplier = 1000000;
            str = str.replace(/M/gi, '');
        } else if (str.toUpperCase().includes('K')) {
            multiplier = 1000;
            str = str.replace(/K/gi, '');
        }
        return parseFloat(str) * multiplier || 0;
    }
    return parseFloat(vol) || 0;
}


let previousOddsData = null;
let modalOddsData = null;

function openMatchModal(index) {
    const dataSource = filteredMatches.length > 0 ? filteredMatches : matches;
    if (index >= 0 && index < dataSource.length) {
        selectedMatch = dataSource[index];
        selectedChartMarket = currentMarket;
        previousOddsData = null;
        modalOddsData = selectedMatch.odds || selectedMatch.details || null;
        
        document.getElementById('modalMatchTitle').textContent = 
            `${selectedMatch.home_team} vs ${selectedMatch.away_team}`;
        
        const headerDt = toTurkeyTime(selectedMatch.date);
        let headerDateText = selectedMatch.date || '';
        if (headerDt && headerDt.isValid()) {
            headerDateText = headerDt.format('DD.MM HH:mm');
        }
        document.getElementById('modalLeague').textContent = 
            `${selectedMatch.league || ''} • ${headerDateText}`;
        
        updateMatchInfoCard();
        
        document.querySelectorAll('#modalChartTabs .chart-tab').forEach(t => {
            t.classList.remove('active');
            if (t.dataset.market === currentMarket) {
                t.classList.add('active');
            }
        });
        
        document.getElementById('modalOverlay').classList.add('active');
        loadChartWithTrends(selectedMatch.home_team, selectedMatch.away_team, selectedChartMarket);
        
        renderMatchAlarmsSection(selectedMatch.home_team, selectedMatch.away_team);
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
                <div class="info-columns info-columns-3">
                    <div class="info-column">
                        <div class="column-header">1</div>
                        <div class="column-row">
                            <span class="row-label">Odds</span>
                            <span class="row-value odds">${formatOdds(d.Odds1 || d['1'])}</span>
                        </div>
                        <div class="column-row">
                            <span class="row-label">Stake</span>
                            <span class="row-value money ${c1}">${formatVolume(d.Amt1)}</span>
                        </div>
                        <div class="column-row">
                            <span class="row-label">%</span>
                            <span class="row-value pct ${c1}">${formatPct(d.Pct1)}</span>
                        </div>
                    </div>
                    <div class="info-column">
                        <div class="column-header">X</div>
                        <div class="column-row">
                            <span class="row-label">Odds</span>
                            <span class="row-value odds">${formatOdds(d.OddsX || d['X'])}</span>
                        </div>
                        <div class="column-row">
                            <span class="row-label">Stake</span>
                            <span class="row-value money ${cX}">${formatVolume(d.AmtX)}</span>
                        </div>
                        <div class="column-row">
                            <span class="row-label">%</span>
                            <span class="row-value pct ${cX}">${formatPct(d.PctX)}</span>
                        </div>
                    </div>
                    <div class="info-column">
                        <div class="column-header">2</div>
                        <div class="column-row">
                            <span class="row-label">Odds</span>
                            <span class="row-value odds">${formatOdds(d.Odds2 || d['2'])}</span>
                        </div>
                        <div class="column-row">
                            <span class="row-label">Stake</span>
                            <span class="row-value money ${c2}">${formatVolume(d.Amt2)}</span>
                        </div>
                        <div class="column-row">
                            <span class="row-label">%</span>
                            <span class="row-value pct ${c2}">${formatPct(d.Pct2)}</span>
                        </div>
                    </div>
                </div>
                <div class="volume-bar">
                    <span class="volume-label">TOTAL VOLUME</span>
                    <span class="volume-value">${formatVolume(d.Volume)}</span>
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
                            <span class="row-value money ${cU}">${formatVolume(d.AmtUnder)}</span>
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
                            <span class="row-value money ${cO}">${formatVolume(d.AmtOver)}</span>
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
                            <span class="row-value money ${cY}">${formatVolume(d.AmtYes)}</span>
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
                            <span class="row-value money ${cN}">${formatVolume(d.AmtNo)}</span>
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
    
    const chartTooltip = document.getElementById('chartjs-tooltip');
    if (chartTooltip) {
        chartTooltip.style.opacity = 0;
        chartTooltip.style.visibility = 'hidden';
        chartTooltip.style.display = 'none';
    }
    
    const trendTooltip = document.querySelector('.odds-trend-tooltip');
    if (trendTooltip) {
        trendTooltip.classList.remove('visible');
    }
    
    if (chart) {
        chart.options.plugins.tooltip.enabled = false;
        chart.update('none');
        chart.options.plugins.tooltip.enabled = true;
    }
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
    const dt = toTurkeyTime(timestamp);
    if (!dt || !dt.isValid()) return dayjs().tz(APP_TIMEZONE);
    const config = getBucketConfig();
    const bucketMinutes = config.bucketMinutes;
    const minutes = dt.hour() * 60 + dt.minute();
    const roundedMinutes = Math.floor(minutes / bucketMinutes) * bucketMinutes;
    return dt.startOf('day').add(roundedMinutes, 'minute');
}

function formatTimeLabel(date) {
    const dt = toTurkeyTime(date);
    if (!dt || !dt.isValid()) return '';
    return dt.format('DD.MM • HH:mm');
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
        
        function createGradient(color) {
            const gradient = ctx.createLinearGradient(0, 0, 0, 400);
            gradient.addColorStop(0, color.replace(')', ', 0.35)').replace('rgb', 'rgba'));
            gradient.addColorStop(1, color.replace(')', ', 0.02)').replace('rgb', 'rgba'));
            return gradient;
        }
        
        function hexToRgba(hex, alpha) {
            const r = parseInt(hex.slice(1, 3), 16);
            const g = parseInt(hex.slice(3, 5), 16);
            const b = parseInt(hex.slice(5, 7), 16);
            return `rgba(${r}, ${g}, ${b}, ${alpha})`;
        }
        
        function createHexGradient(hex) {
            const gradient = ctx.createLinearGradient(0, 0, 0, 400);
            gradient.addColorStop(0, hexToRgba(hex, 0.35));
            gradient.addColorStop(1, hexToRgba(hex, 0.02));
            return gradient;
        }
        
        const filteredHistory = filterHistoryByTimeRange(data.history);
        
        const timeBlocks = {};
        filteredHistory.forEach(h => {
            const ts = h.ScrapedAt || '';
            const rounded = roundToBucket(ts);
            const key = rounded.valueOf();
            timeBlocks[key] = h;
        });
        
        const sortedKeys = Object.keys(timeBlocks).map(Number).sort((a, b) => a - b);
        const labels = sortedKeys.map(k => formatTimeLabel(k));
        const historyData = sortedKeys.map(k => timeBlocks[k]);
        
        if (sortedKeys.length > 0) {
            const lastKey = sortedKeys[sortedKeys.length - 1];
            const lastLabel = formatTimeLabel(lastKey);
            const lastData = timeBlocks[lastKey];
            console.log('[Chart] Last bucket:', lastLabel, 'ScrapedAt:', lastData?.ScrapedAt);
        }
        
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
                        backgroundColor: createHexGradient(color),
                        tension: 0.4,
                        fill: true,
                        pointRadius: 0,
                        pointHoverRadius: 4,
                        pointBackgroundColor: color,
                        pointBorderColor: '#fff',
                        pointBorderWidth: 2,
                        pointStyle: 'circle',
                        borderWidth: 2
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
                        backgroundColor: createHexGradient(color),
                        tension: 0.4,
                        fill: true,
                        pointRadius: 0,
                        pointHoverRadius: 4,
                        pointBackgroundColor: color,
                        pointBorderColor: '#fff',
                        pointBorderWidth: 2,
                        pointStyle: 'circle',
                        borderWidth: 2
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
                        backgroundColor: createHexGradient(color),
                        tension: 0.4,
                        fill: true,
                        pointRadius: 0,
                        pointHoverRadius: 4,
                        pointBackgroundColor: color,
                        pointBorderColor: '#fff',
                        pointBorderWidth: 2,
                        pointStyle: 'circle',
                        borderWidth: 2
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
                        backgroundColor: createHexGradient(color),
                        tension: 0.4,
                        fill: true,
                        pointRadius: 0,
                        pointHoverRadius: 4,
                        pointBackgroundColor: color,
                        pointBorderColor: '#fff',
                        pointBorderWidth: 2,
                        pointStyle: 'circle',
                        borderWidth: 2
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
                        backgroundColor: createHexGradient(color),
                        tension: 0.4,
                        fill: true,
                        pointRadius: 0,
                        pointHoverRadius: 4,
                        pointBackgroundColor: color,
                        pointBorderColor: '#fff',
                        pointBorderWidth: 2,
                        pointStyle: 'circle',
                        borderWidth: 2
                    });
                });
            } else {
                ['Yes', 'No'].forEach((key, idx) => {
                    const label = key;
                    const color = colors[key];
                    datasets.push({
                        label: label,
                        data: historyData.map(h => {
                            const val = h['Odds' + key] || h[key];
                            if (!val) return null;
                            const num = parseFloat(String(val).split('\n')[0]);
                            return isNaN(num) ? null : num;
                        }),
                        borderColor: color,
                        backgroundColor: createHexGradient(color),
                        tension: 0.4,
                        fill: true,
                        pointRadius: 0,
                        pointHoverRadius: 4,
                        pointBackgroundColor: color,
                        pointBorderColor: '#fff',
                        pointBorderWidth: 2,
                        pointStyle: 'circle',
                        borderWidth: 2
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
                                tooltipEl.style.visibility = 'hidden';
                                return;
                            }
                            
                            tooltipEl.style.display = 'block';
                            tooltipEl.style.visibility = 'visible';
                            
                            if (tooltipModel.body) {
                                const dataIndex = tooltipModel.dataPoints[0].dataIndex;
                                const h = tooltipHistory[dataIndex];
                                const titleLines = tooltipModel.title || [];
                                
                                let innerHtml = '<div class="chart-tooltip-title">' + titleLines.join(' — ') + '</div>';
                                innerHtml += '<div class="chart-tooltip-body">';
                                
                                const processedLabels = new Set();
                                
                                tooltipModel.dataPoints.forEach(function(dataPoint) {
                                    const datasetLabel = dataPoint.dataset.label;
                                    const boxColor = dataPoint.dataset.borderColor;
                                    
                                    if (processedLabels.has(datasetLabel)) return;
                                    processedLabels.add(datasetLabel);
                                    
                                    if (isDropping && h) {
                                        const graphPointOdds = getOddsFromHistory(h, datasetLabel, market);
                                        const currentLatestOdds = getLatestOdds(latestData, datasetLabel.replace('%', ''), market);
                                        
                                        innerHtml += '<div class="chart-tooltip-row">';
                                        innerHtml += '<div class="chart-tooltip-main">';
                                        innerHtml += '<span class="chart-tooltip-option"><span class="color-dot" style="background:' + boxColor + '"></span>' + datasetLabel.replace('%', '') + '</span>';
                                        innerHtml += '<span class="chart-tooltip-odds">' + graphPointOdds.toFixed(2) + '</span>';
                                        innerHtml += '</div>';
                                        
                                        if (graphPointOdds > 0 && currentLatestOdds > 0 && graphPointOdds !== currentLatestOdds) {
                                            const pctChange = ((currentLatestOdds - graphPointOdds) / graphPointOdds) * 100;
                                            const changeSign = pctChange >= 0 ? '+' : '';
                                            const colorClass = pctChange >= 0 ? 'trend-color-up' : 'trend-color-down';
                                            innerHtml += '<div class="chart-tooltip-sub">';
                                            innerHtml += '→ ' + currentLatestOdds.toFixed(2);
                                            innerHtml += '<span class="separator">•</span>';
                                            innerHtml += '<span class="' + colorClass + '">' + changeSign + pctChange.toFixed(1) + '%</span>';
                                            innerHtml += '</div>';
                                        }
                                        innerHtml += '</div>';
                                    } else if (h) {
                                        let label = '', odds = '-', amt = '', pct = '';
                                        
                                        if (market.includes('1x2')) {
                                            if (datasetLabel.includes('1')) {
                                                label = '1'; odds = h.Odds1 || h['1'] || '-'; amt = h.Amt1 || ''; pct = h.Pct1 || '';
                                            } else if (datasetLabel.includes('X')) {
                                                label = 'X'; odds = h.OddsX || h['X'] || '-'; amt = h.AmtX || ''; pct = h.PctX || '';
                                            } else if (datasetLabel.includes('2')) {
                                                label = '2'; odds = h.Odds2 || h['2'] || '-'; amt = h.Amt2 || ''; pct = h.Pct2 || '';
                                            }
                                        } else if (market.includes('ou25')) {
                                            if (datasetLabel.toLowerCase().includes('under')) {
                                                label = 'Under'; odds = h.Under || '-'; amt = h.AmtUnder || ''; pct = h.PctUnder || '';
                                            } else {
                                                label = 'Over'; odds = h.Over || '-'; amt = h.AmtOver || ''; pct = h.PctOver || '';
                                            }
                                        } else if (market.includes('btts')) {
                                            if (datasetLabel.toLowerCase().includes('yes')) {
                                                label = 'Yes'; odds = h.Yes || '-'; amt = h.AmtYes || ''; pct = h.PctYes || '';
                                            } else {
                                                label = 'No'; odds = h.No || '-'; amt = h.AmtNo || ''; pct = h.PctNo || '';
                                            }
                                        }
                                        
                                        innerHtml += '<div class="chart-tooltip-row">';
                                        innerHtml += '<div class="chart-tooltip-main">';
                                        innerHtml += '<span class="chart-tooltip-option"><span class="color-dot" style="background:' + boxColor + '"></span>' + label + '</span>';
                                        innerHtml += '<span class="chart-tooltip-odds">' + formatOdds(odds) + '</span>';
                                        if (amt) {
                                            innerHtml += '<span class="chart-tooltip-volume" style="color:' + boxColor + '">' + formatVolumeCompact(amt) + '</span>';
                                        }
                                        innerHtml += '</div>';
                                        if (pct) {
                                            innerHtml += '<div class="chart-tooltip-pct">' + cleanPct(pct) + '%</div>';
                                        }
                                        innerHtml += '</div>';
                                    } else {
                                        innerHtml += '<div class="chart-tooltip-row">';
                                        innerHtml += '<div class="chart-tooltip-main">';
                                        innerHtml += '<span class="chart-tooltip-option"><span class="color-dot" style="background:' + boxColor + '"></span>' + datasetLabel + '</span>';
                                        innerHtml += '<span class="chart-tooltip-odds">' + dataPoint.formattedValue + '</span>';
                                        innerHtml += '</div>';
                                        innerHtml += '</div>';
                                    }
                                });
                                
                                innerHtml += '</div>';
                                tooltipEl.querySelector('.chart-tooltip-inner').innerHTML = innerHtml;
                            }
                            
                            const position = context.chart.canvas.getBoundingClientRect();
                            tooltipEl.style.opacity = 1;
                            tooltipEl.style.position = 'absolute';
                            tooltipEl.style.pointerEvents = 'none';
                            
                            let left = position.left + window.pageXOffset + tooltipModel.caretX;
                            let top = position.top + window.pageYOffset + tooltipModel.caretY;
                            
                            const tooltipWidth = tooltipEl.offsetWidth || 200;
                            const tooltipHeight = tooltipEl.offsetHeight || 100;
                            const viewportWidth = window.innerWidth;
                            const viewportHeight = window.innerHeight;
                            
                            if (left + tooltipWidth > viewportWidth - 20) {
                                left = viewportWidth - tooltipWidth - 20;
                            }
                            if (left < 10) left = 10;
                            
                            if (top + tooltipHeight > viewportHeight + window.pageYOffset - 20) {
                                top = top - tooltipHeight - 20;
                            }
                            if (top < window.pageYOffset + 10) top = window.pageYOffset + 10;
                            
                            tooltipEl.style.left = left + 'px';
                            tooltipEl.style.top = top + 'px';
                        }
                    }
                },
                scales: {
                    x: {
                        grid: {
                            color: 'rgba(255, 255, 255, 0.06)',
                            drawBorder: false
                        },
                        border: {
                            display: false
                        },
                        ticks: {
                            color: '#a1a1aa',
                            font: { size: 11 }
                        }
                    },
                    y: {
                        grid: {
                            color: 'rgba(255, 255, 255, 0.06)',
                            drawBorder: false
                        },
                        border: {
                            display: false
                        },
                        ticks: {
                            color: '#8e8e95',
                            font: { size: 11 },
                            callback: function(value) {
                                if (value >= 1000000) {
                                    return '£' + (value / 1000000).toFixed(1) + 'M';
                                } else if (value >= 1000) {
                                    return '£' + (value / 1000).toFixed(0) + 'K';
                                }
                                return '£' + value;
                            }
                        }
                    }
                },
                elements: {
                    point: {
                        radius: 0,
                        hoverRadius: 4,
                        borderWidth: 2
                    },
                    line: {
                        borderWidth: 2
                    }
                }
            },
            plugins: {
                zoom: {
                    pan: {
                        enabled: true,
                        mode: 'x',
                        modifierKey: 'shift'
                    },
                    zoom: {
                        wheel: {
                            enabled: true
                        },
                        pinch: {
                            enabled: true
                        },
                        drag: {
                            enabled: true,
                            backgroundColor: 'rgba(76, 139, 245, 0.15)',
                            borderColor: '#4C8BF5',
                            borderWidth: 1
                        },
                        mode: 'x'
                    },
                    limits: {
                        x: { min: 'original', max: 'original' }
                    }
                }
            }
        });
        
        const chartContainer = document.getElementById('oddsChart').parentElement;
        
        createBrushSlider(chartContainer, historyData, chart);
    } catch (error) {
        console.error('Error loading chart:', error);
    }
}

let brushStartIndex = 0;
let brushEndIndex = 100;
let brushDataLength = 0;

function createBrushSlider(container, historyData, mainChart) {
    brushDataLength = historyData.length;
    brushStartIndex = 0;
    brushEndIndex = brushDataLength - 1;
    
    let brushContainer = container.parentElement.querySelector('.chart-brush-container');
    if (!brushContainer) {
        brushContainer = document.createElement('div');
        brushContainer.className = 'chart-brush-container';
        brushContainer.innerHTML = `
            <div class="range-slider-container">
                <div class="range-slider-track"></div>
                <div class="range-slider-highlight" id="brushHighlight"></div>
                <canvas id="brushMiniChart" class="chart-brush-mini" height="40"></canvas>
                <input type="range" class="range-slider-input" id="brushStart" min="0" max="100" value="0">
                <input type="range" class="range-slider-input" id="brushEnd" min="0" max="100" value="100">
            </div>
            <div class="brush-info">
                <span class="brush-info-label">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0zM10 7v6m3-3H7"/>
                    </svg>
                    Drag handles to zoom
                </span>
                <span id="brushRange">Showing all data</span>
            </div>
        `;
        container.parentElement.appendChild(brushContainer);
    }
    
    const brushStart = brushContainer.querySelector('#brushStart');
    const brushEnd = brushContainer.querySelector('#brushEnd');
    const brushHighlight = brushContainer.querySelector('#brushHighlight');
    const brushRangeInfo = brushContainer.querySelector('#brushRange');
    
    brushStart.max = brushDataLength - 1;
    brushEnd.max = brushDataLength - 1;
    brushStart.value = 0;
    brushEnd.value = brushDataLength - 1;
    
    drawMiniChart(brushContainer.querySelector('#brushMiniChart'), historyData);
    updateBrushHighlight();
    
    function updateBrushHighlight() {
        const startPct = (parseInt(brushStart.value) / (brushDataLength - 1)) * 100;
        const endPct = (parseInt(brushEnd.value) / (brushDataLength - 1)) * 100;
        brushHighlight.style.left = `${startPct}%`;
        brushHighlight.style.width = `${endPct - startPct}%`;
        
        const startIdx = parseInt(brushStart.value);
        const endIdx = parseInt(brushEnd.value);
        const showing = endIdx - startIdx + 1;
        brushRangeInfo.textContent = showing === brushDataLength 
            ? 'Showing all data' 
            : `Showing ${showing} of ${brushDataLength} points`;
    }
    
    function applyZoom() {
        const startIdx = parseInt(brushStart.value);
        const endIdx = parseInt(brushEnd.value);
        
        if (startIdx >= endIdx) return;
        
        const labels = mainChart.data.labels;
        if (!labels || labels.length === 0) return;
        
        const minLabel = labels[startIdx];
        const maxLabel = labels[endIdx];
        
        mainChart.options.scales.x.min = minLabel;
        mainChart.options.scales.x.max = maxLabel;
        mainChart.update('none');
        
        updateBrushHighlight();
    }
    
    brushStart.addEventListener('input', function() {
        if (parseInt(brushStart.value) >= parseInt(brushEnd.value) - 1) {
            brushStart.value = parseInt(brushEnd.value) - 1;
        }
        applyZoom();
    });
    
    brushEnd.addEventListener('input', function() {
        if (parseInt(brushEnd.value) <= parseInt(brushStart.value) + 1) {
            brushEnd.value = parseInt(brushStart.value) + 1;
        }
        applyZoom();
    });
}

function resetBrushSlider() {
    const brushStart = document.querySelector('#brushStart');
    const brushEnd = document.querySelector('#brushEnd');
    if (brushStart && brushEnd) {
        brushStart.value = 0;
        brushEnd.value = brushDataLength - 1;
        const brushHighlight = document.querySelector('#brushHighlight');
        if (brushHighlight) {
            brushHighlight.style.left = '0%';
            brushHighlight.style.width = '100%';
        }
        const brushRangeInfo = document.querySelector('#brushRange');
        if (brushRangeInfo) {
            brushRangeInfo.textContent = 'Showing all data';
        }
    }
}

function resetChartZoom() {
    if (chart) {
        chart.resetZoom();
        chart.options.scales.x.min = undefined;
        chart.options.scales.x.max = undefined;
        chart.update('none');
    }
    resetBrushSlider();
}

function drawMiniChart(canvas, historyData) {
    if (!canvas || !historyData || historyData.length === 0) return;
    
    const ctx = canvas.getContext('2d');
    const width = canvas.parentElement.offsetWidth || 400;
    const height = 40;
    
    canvas.width = width;
    canvas.height = height;
    
    ctx.clearRect(0, 0, width, height);
    
    let values = [];
    historyData.forEach(h => {
        const val = h.Odds1 || h['1'] || h.Over || h.Yes || h.Pct1 || h.Amt1 || 0;
        const num = parseFloat(String(val).replace(/[^0-9.]/g, ''));
        if (!isNaN(num)) values.push(num);
    });
    
    if (values.length < 2) return;
    
    const minVal = Math.min(...values);
    const maxVal = Math.max(...values);
    const range = maxVal - minVal || 1;
    
    const gradient = ctx.createLinearGradient(0, 0, 0, height);
    gradient.addColorStop(0, 'rgba(76, 139, 245, 0.4)');
    gradient.addColorStop(1, 'rgba(76, 139, 245, 0.05)');
    
    ctx.beginPath();
    ctx.moveTo(0, height);
    
    values.forEach((val, i) => {
        const x = (i / (values.length - 1)) * width;
        const y = height - ((val - minVal) / range) * (height - 8) - 4;
        if (i === 0) {
            ctx.lineTo(x, y);
        } else {
            ctx.lineTo(x, y);
        }
    });
    
    ctx.lineTo(width, height);
    ctx.closePath();
    ctx.fillStyle = gradient;
    ctx.fill();
    
    ctx.beginPath();
    values.forEach((val, i) => {
        const x = (i / (values.length - 1)) * width;
        const y = height - ((val - minVal) / range) * (height - 8) - 4;
        if (i === 0) {
            ctx.moveTo(x, y);
        } else {
            ctx.lineTo(x, y);
        }
    });
    ctx.strokeStyle = '#4C8BF5';
    ctx.lineWidth = 2;
    ctx.stroke();
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
    csvContent += `# Export Date: ${nowTurkey().format('DD.MM.YYYY HH:mm')} (TR)\n`;
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


let oddsTrendCache = {};
let oddsTrendCacheByMarket = {};
let dropMarketsPreloaded = false;

async function preloadDropMarkets() {
    if (dropMarketsPreloaded) return;
    dropMarketsPreloaded = true;
    
    const dropMarkets = ['dropping_1x2', 'dropping_ou25', 'dropping_btts'];
    console.log('[Preload] Starting background load for drop markets...');
    
    for (const market of dropMarkets) {
        if (!oddsTrendCacheByMarket[market]) {
            try {
                const response = await fetch(`/api/odds-trend/${market}`);
                const result = await response.json();
                oddsTrendCacheByMarket[market] = result.data || {};
                console.log(`[Preload] Cached ${market}: ${Object.keys(oddsTrendCacheByMarket[market]).length} matches`);
            } catch (e) {
                console.warn(`[Preload] Failed ${market}:`, e.message);
            }
        }
    }
    console.log('[Preload] Drop markets ready');
}

async function loadOddsTrend(market) {
    if (!market.startsWith('dropping')) {
        oddsTrendCache = {};
        return;
    }
    
    if (oddsTrendCacheByMarket[market]) {
        oddsTrendCache = oddsTrendCacheByMarket[market];
        console.log(`[Odds Trend] Using JS cache for ${market}`);
        return;
    }
    
    try {
        const response = await fetch(`/api/odds-trend/${market}`);
        const result = await response.json();
        oddsTrendCache = result.data || {};
        oddsTrendCacheByMarket[market] = oddsTrendCache;
        console.log(`[Odds Trend] Loaded ${Object.keys(oddsTrendCache).length} matches for ${market}`);
    } catch (error) {
        console.error('[Odds Trend] Error loading:', error);
        oddsTrendCache = {};
    }
}

function generateTrendIconSVG(trend, pctChange) {
    let color, path;
    const absPct = Math.abs(pctChange || 0);
    
    if (trend === 'down') {
        color = '#ff0000';
        if (absPct >= 20) {
            path = 'M2 1 L6 1 L6 4 L10 4 L10 7 L14 7 L14 10 L18 10 L18 11 L26 11';
        } else if (absPct >= 10) {
            path = 'M2 2 L8 2 L8 5 L14 5 L14 8 L20 8 L20 10 L26 10';
        } else if (absPct >= 5) {
            path = 'M2 3 L10 3 L10 6 L18 6 L18 9 L26 9';
        } else if (absPct >= 2) {
            path = 'M2 4 L12 4 L12 7 L26 7 L26 8';
        } else {
            path = 'M2 5 L14 5 L14 7 L26 7';
        }
    } else if (trend === 'up') {
        color = '#22c55e';
        if (absPct >= 20) {
            path = 'M2 11 L6 11 L6 8 L10 8 L10 5 L14 5 L14 2 L18 2 L18 1 L26 1';
        } else if (absPct >= 10) {
            path = 'M2 10 L8 10 L8 7 L14 7 L14 4 L20 4 L20 2 L26 2';
        } else if (absPct >= 5) {
            path = 'M2 9 L10 9 L10 6 L18 6 L18 3 L26 3';
        } else if (absPct >= 2) {
            path = 'M2 8 L12 8 L12 5 L26 5 L26 4';
        } else {
            path = 'M2 7 L14 7 L14 5 L26 5';
        }
    } else {
        color = '#6B7280';
        path = 'M2 6 L26 6';
    }
    
    return `<svg class="trend-icon-svg" width="28" height="12" viewBox="0 0 28 12">
        <path d="${path}" stroke="${color}" stroke-width="2" fill="none" stroke-linecap="square" stroke-linejoin="miter"/>
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
        const trendIcon = generateTrendIconSVG('flat', 0);
        return `
            <div class="odds-trend-cell odds-trend-no-data">
                <div class="trend-icon-container">${trendIcon}</div>
                <div class="odds-value-trend">${formattedOdds}</div>
            </div>
        `;
    }
    
    const trendIcon = generateTrendIconSVG(trendData.trend, trendData.pct_change);
    const pctHtml = formatPctChange(trendData.pct_change, trendData.trend);
    
    const tooltipData = JSON.stringify({
        old: trendData.old,
        new: trendData.new,
        pct: trendData.pct_change,
        trend: trendData.trend,
        first_scraped: trendData.first_scraped || null
    }).replace(/"/g, '&quot;');
    
    return `
        <div class="odds-trend-cell" data-tooltip="${tooltipData}">
            <div class="trend-icon-container">${trendIcon}</div>
            <div class="odds-value-trend">${formattedOdds}</div>
            ${pctHtml}
        </div>
    `;
}

function renderDrop1X2Cell(label, oddsValue, trendData) {
    const formattedOdds = formatOdds(oddsValue);
    
    if (!trendData || !trendData.history || trendData.history.length < 2) {
        const trendIcon = generateTrendIconSVG('flat', 0);
        return `
            <div class="drop-mini-card">
                <div class="drop-trend-icon">${trendIcon}</div>
                <div class="drop-odds">${formattedOdds}</div>
            </div>
        `;
    }
    
    const trendIcon = generateTrendIconSVG(trendData.trend, trendData.pct_change);
    const pctHtml = formatPctChange(trendData.pct_change, trendData.trend);
    
    const tooltipData = JSON.stringify({
        old: trendData.old,
        new: trendData.new,
        pct: trendData.pct_change,
        trend: trendData.trend,
        first_scraped: trendData.first_scraped || null
    }).replace(/"/g, '&quot;');
    
    const changeClass = trendData.trend === 'up' ? 'positive' : (trendData.trend === 'down' ? 'negative' : '');
    
    return `
        <div class="drop-mini-card" data-tooltip="${tooltipData}">
            <div class="drop-trend-icon">${trendIcon}</div>
            <div class="drop-odds">${formattedOdds}</div>
            <div class="drop-change ${changeClass}">${pctHtml}</div>
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
        
        let firstScrapedText = '';
        if (data.first_scraped) {
            const dt = toTurkeyTime(data.first_scraped);
            if (dt && dt.isValid()) {
                firstScrapedText = dt.format('DD.MM HH:mm');
            }
        }
        
        tooltip.innerHTML = `
            <div class="tooltip-title">AÇILIŞTAN BUGÜNE DEĞİŞİM</div>
            <div class="tooltip-block">
                <div class="tooltip-row">
                    <span class="tooltip-label">Açılış oranı:</span>
                    <span class="tooltip-value">${data.old ? data.old.toFixed(2) : '-'}</span>
                </div>
                ${firstScrapedText ? `<div class="tooltip-date">(${firstScrapedText})</div>` : ''}
            </div>
            <div class="tooltip-block">
                <div class="tooltip-row">
                    <span class="tooltip-label">Son oran:</span>
                    <span class="tooltip-value">${data.new ? data.new.toFixed(2) : '-'}</span>
                </div>
            </div>
            <div class="tooltip-block">
                <div class="tooltip-row">
                    <span class="tooltip-label">Değişim:</span>
                    <span class="tooltip-value ${trendClass}">${diffSign}${diff.toFixed(2)} (${data.pct > 0 ? '+' : ''}${data.pct}%)</span>
                </div>
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

// ============================================
// ALERT BAND - Top Notification Strip
// ============================================

let alertBandData = [];
let alertBandRenderTimeout = null;
let lastAlertBandHash = '';
let lastTopAlarmKey = null;
let isHighlightingNewAlarm = false;

function getAlarmKey(alarm) {
    if (!alarm) return null;
    const home = alarm.home || alarm.home_team || '';
    const type = alarm._type || '';
    const eventTime = alarm.trigger_at || alarm.event_time || alarm.created_at || '';
    return `${home}|${type}|${eventTime}`;
}

function scheduleAlertBandRender() {
    if (alertBandRenderTimeout) {
        clearTimeout(alertBandRenderTimeout);
    }
    alertBandRenderTimeout = setTimeout(() => {
        const newHash = JSON.stringify(alertBandData.slice(0, 10).map(a => a.home + a._type + (a.trigger_at || a.event_time || '')));
        
        // İlk yükleme veya hash değişti - MUTLAKA render et
        const isFirstRender = lastAlertBandHash === '';
        const hashChanged = newHash !== lastAlertBandHash;
        
        if (isFirstRender || hashChanged) {
            lastAlertBandHash = newHash;
            
            // Yeni en üst alarm kontrolü
            const currentTopKey = getAlarmKey(alertBandData[0]);
            const isNewTopAlarm = lastTopAlarmKey !== null && currentTopKey !== lastTopAlarmKey;
            
            if (isNewTopAlarm && alertBandData[0] && !isHighlightingNewAlarm) {
                // Yeni alarm geldi - highlight göster
                highlightNewAlarm(alertBandData[0]);
            } else {
                renderAlertBand();
            }
            
            lastTopAlarmKey = currentTopKey;
        }
        updateAlertBandBadge();
    }, 100);
}

function highlightNewAlarm(alarm) {
    isHighlightingNewAlarm = true;
    const band = document.getElementById('alertBandTrack');
    if (!band) {
        isHighlightingNewAlarm = false;
        return;
    }
    
    // Band'ı highlight moduna al - scroll durur, ortala
    band.classList.add('highlight-mode');
    
    const info = getAlertType(alarm);
    const home = alarm.home || alarm.home_team || '?';
    const away = alarm.away || alarm.away_team || '?';
    const selection = alarm.selection || alarm.side || '';
    const alarmType = alarm._type || 'sharp';
    
    // Value hesapla
    let value = '';
    if (alarmType === 'sharp') {
        value = (alarm.sharp_score || 0).toFixed(1);
    } else if (alarmType === 'insider') {
        value = `▼ ${Math.abs(alarm.oran_dusus_pct || alarm.odds_drop_pct || 0).toFixed(1)}%`;
    } else if (alarmType === 'volumeshock') {
        value = `${(alarm.volume_shock_value || alarm.volume_shock || alarm.volume_shock_multiplier || 0).toFixed(1)}x`;
    } else if (alarmType === 'bigmoney') {
        value = `£${Number(alarm.incoming_money || alarm.stake || 0).toLocaleString('en-GB')}`;
    } else if (alarmType === 'dropping') {
        value = `▼ ${(alarm.drop_pct || 0).toFixed(1)}%`;
    } else if (alarmType === 'publicmove') {
        value = `${(alarm.move_score || alarm.trap_score || alarm.sharp_score || 0).toFixed(0)}`;
    } else if (alarmType === 'volumeleader') {
        value = `%${(alarm.new_leader_share || 0).toFixed(0)}`;
    }
    
    // Volume Leader için özel format
    let contentHtml = '';
    if (alarmType === 'volumeleader') {
        const oldLeader = alarm.old_leader || alarm.previous_leader || '?';
        const newLeader = alarm.new_leader || alarm.selection || '?';
        contentHtml = `
            <span class="ab-dot dot-${info.pillClass}"></span>
            <span class="ab-type">${info.label}</span>
            <span class="ab-sep">—</span>
            <span class="ab-match">${home} - ${away}</span>
            <span class="ab-sep">—</span>
            <span class="ab-leader-change">${oldLeader} <span class="ab-arrow">▸</span> ${newLeader}</span>
        `;
    } else {
        contentHtml = `
            <span class="ab-dot dot-${info.pillClass}"></span>
            <span class="ab-type">${info.label}</span>
            <span class="ab-sep">—</span>
            <span class="ab-match">${home} - ${away}</span>
            <span class="ab-sep">—</span>
            <span class="ab-sel">${selection}</span>
            <span class="ab-val">${value}</span>
        `;
    }
    
    // Highlight container oluştur - tek alarm ortada (label kaldırıldı)
    band.innerHTML = `
        <div class="new-alarm-highlight">
            <div class="ab-pill ${info.pillClass} highlight-pill">
                ${contentHtml}
            </div>
        </div>
    `;
    
    console.log('[AlertBand] New alarm highlight:', home, 'vs', away, '- showing for 5 seconds');
    
    // 5 saniye sonra normal band'a dön
    setTimeout(() => {
        isHighlightingNewAlarm = false;
        band.classList.remove('highlight-mode');
        renderAlertBand();
        console.log('[AlertBand] Highlight ended, returning to normal scroll');
    }, 5000);
}

// Alarm zamanını parse et (format: "DD.MM.YYYY HH:MM")
function parseAlarmTime(timeStr) {
    if (!timeStr) return 0;
    try {
        // Format: "02.12.2024 14:35"
        const parts = timeStr.split(' ');
        if (parts.length < 2) return 0;
        
        const dateParts = parts[0].split('.');
        const timeParts = parts[1].split(':');
        
        if (dateParts.length < 3 || timeParts.length < 2) return 0;
        
        const day = parseInt(dateParts[0]);
        const month = parseInt(dateParts[1]) - 1;
        const year = parseInt(dateParts[2]);
        const hour = parseInt(timeParts[0]);
        const minute = parseInt(timeParts[1]);
        
        return new Date(year, month, day, hour, minute).getTime();
    } catch (e) {
        return 0;
    }
}

// Maç saatini +3 saat ekleyerek formatla (format: "02.Dec 12:00:00" -> "02 Ara • 15:00")
function formatMatchTime3(dateStr) {
    if (!dateStr) return '-';
    
    const monthNames = ['Oca', 'Sub', 'Mar', 'Nis', 'May', 'Haz', 'Tem', 'Agu', 'Eyl', 'Eki', 'Kas', 'Ara'];
    const monthMap = { 'Jan': 0, 'Feb': 1, 'Mar': 2, 'Apr': 3, 'May': 4, 'Jun': 5, 
                       'Jul': 6, 'Aug': 7, 'Sep': 8, 'Oct': 9, 'Nov': 10, 'Dec': 11 };
    
    // Format: "02.Dec 12:00:00"
    const match1 = dateStr.match(/^(\d{2})\.([A-Za-z]{3})\s+(\d{2}):(\d{2}):?(\d{2})?$/);
    if (match1) {
        const [, day, monthStr, hour, min] = match1;
        const monthIdx = monthMap[monthStr] ?? 0;
        const dt = new Date(2025, monthIdx, parseInt(day), parseInt(hour), parseInt(min));
        dt.setHours(dt.getHours() + 3); // +3 saat Türkiye
        const monthName = monthNames[dt.getMonth()];
        const h = String(dt.getHours()).padStart(2, '0');
        const m = String(dt.getMinutes()).padStart(2, '0');
        const d = String(dt.getDate()).padStart(2, '0');
        return `${d} ${monthName} • ${h}:${m}`;
    }
    
    // Format: "DD.MM.YYYY HH:MM"
    const match2 = dateStr.match(/^(\d{2})\.(\d{2})\.(\d{4})\s+(\d{2}):(\d{2})$/);
    if (match2) {
        const [, day, month, year, hour, min] = match2;
        const dt = new Date(parseInt(year), parseInt(month) - 1, parseInt(day), parseInt(hour), parseInt(min));
        dt.setHours(dt.getHours() + 3); // +3 saat Türkiye
        const monthName = monthNames[dt.getMonth()];
        const h = String(dt.getHours()).padStart(2, '0');
        const m = String(dt.getMinutes()).padStart(2, '0');
        const d = String(dt.getDate()).padStart(2, '0');
        return `${d} ${monthName} • ${h}:${m}`;
    }
    
    // Fallback
    return dateStr;
}

// Maç tarihini kısa formatta göster (format: "02.Dec 14:00:00" -> "02 Ara 17:00")
function formatMatchDateShort(dateStr) {
    if (!dateStr) return '';
    
    const monthNames = ['Oca', 'Şub', 'Mar', 'Nis', 'May', 'Haz', 'Tem', 'Ağu', 'Eyl', 'Eki', 'Kas', 'Ara'];
    const monthMap = { 'Jan': 0, 'Feb': 1, 'Mar': 2, 'Apr': 3, 'May': 4, 'Jun': 5, 
                       'Jul': 6, 'Aug': 7, 'Sep': 8, 'Oct': 9, 'Nov': 10, 'Dec': 11 };
    
    // Format: "02.Dec 14:00:00"
    const match1 = dateStr.match(/^(\d{2})\.([A-Za-z]{3})\s+(\d{2}):(\d{2}):?(\d{2})?$/);
    if (match1) {
        const [, day, monthStr, hour, min] = match1;
        const monthIdx = monthMap[monthStr] ?? 0;
        const dt = new Date(2025, monthIdx, parseInt(day), parseInt(hour), parseInt(min));
        dt.setHours(dt.getHours() + 3); // +3 saat Türkiye
        const monthName = monthNames[dt.getMonth()];
        const h = String(dt.getHours()).padStart(2, '0');
        const m = String(dt.getMinutes()).padStart(2, '0');
        const d = String(dt.getDate()).padStart(2, '0');
        return `${d} ${monthName} ${h}:${m}`;
    }
    
    // Fallback
    return '';
}

// Dünün maçlarını filtrele - sadece bugün ve gelecek maçları göster
// ÖNEMLİ: match_date/fixture_date baz alınır, created_at DEĞİL!
function isMatchTodayOrFuture(alarm) {
    const matchDateStr = alarm.match_date || alarm.fixture_date || '';
    
    // Türkiye saati için bugünün tarihini al
    const now = new Date();
    const trTime = new Date(now.toLocaleString('en-US', { timeZone: 'Europe/Istanbul' }));
    const currentMonth = trTime.getMonth();
    const currentDay = trTime.getDate();
    
    // match_date formatları:
    // 1. "06.Dec 15:00:00" (boşluklu)
    // 2. "06.Dec00:00:00" (boşluksuz)
    if (matchDateStr) {
        // Regex ile DD.MMM kısmını parse et (boşluklu veya boşluksuz)
        const match = matchDateStr.match(/^(\d{1,2})\.([A-Za-z]{3})/);
        if (match) {
            const dayStr = match[1];
            const monthStr = match[2];
            const monthMap = { 'Jan': 0, 'Feb': 1, 'Mar': 2, 'Apr': 3, 'May': 4, 'Jun': 5, 
                              'Jul': 6, 'Aug': 7, 'Sep': 8, 'Oct': 9, 'Nov': 10, 'Dec': 11 };
            const matchMonth = monthMap[monthStr];
            const matchDay = parseInt(dayStr);
            
            if (matchMonth !== undefined && !isNaN(matchDay)) {
                // Bugün veya gelecek tarihse göster
                if (matchMonth > currentMonth) return true;
                if (matchMonth === currentMonth && matchDay >= currentDay) return true;
                // Yıl geçişi durumu (Aralık -> Ocak)
                if (matchMonth < currentMonth && currentMonth >= 10 && matchMonth <= 2) return true;
                return false;
            }
        }
    }
    
    // match_date yoksa gösterme (eski/geçersiz alarm)
    return false;
}

async function loadAlertBand() {
    try {
        const [sharpRes, insiderRes, bigMoneyRes, volumeShockRes, droppingRes, publicmoveRes, volumeLeaderRes] = await Promise.all([
            fetch('/api/sharp/alarms'),
            fetch('/api/insider/alarms'),
            fetch('/api/bigmoney/alarms'),
            fetch('/api/volumeshock/alarms'),
            fetch('/api/dropping/alarms'),
            fetch('/api/publicmove/alarms'),
            fetch('/api/volumeleader/alarms')
        ]);
        
        let allAlarms = [];
        
        if (sharpRes.ok) {
            const sharp = await sharpRes.json();
            sharp.forEach(a => { a._type = 'sharp'; a._score = a.sharp_score || 0; });
            allAlarms = allAlarms.concat(sharp);
        }
        
        if (insiderRes.ok) {
            const insider = await insiderRes.json();
            insider.forEach(a => { a._type = 'insider'; a._score = a.insider_score || 0; });
            allAlarms = allAlarms.concat(insider);
        }
        
        if (bigMoneyRes.ok) {
            const bigmoney = await bigMoneyRes.json();
            bigmoney.forEach(a => { a._type = 'bigmoney'; a._score = a.incoming_money || a.stake || a.volume || 0; });
            allAlarms = allAlarms.concat(bigmoney);
        }
        
        if (volumeShockRes.ok) {
            const volumeshock = await volumeShockRes.json();
            volumeshock.forEach(a => { a._type = 'volumeshock'; a._score = (a.volume_shock_value || a.volume_shock || a.volume_shock_multiplier || 0) * 100; });
            allAlarms = allAlarms.concat(volumeshock);
        }
        
        if (droppingRes.ok) {
            const dropping = await droppingRes.json();
            dropping.forEach(a => { a._type = 'dropping'; a._score = a.drop_pct || 0; });
            allAlarms = allAlarms.concat(dropping);
        }
        
        if (publicmoveRes.ok) {
            const publicmove = await publicmoveRes.json();
            publicmove.forEach(a => { a._type = 'publicmove'; a._score = a.trap_score || a.sharp_score || 0; });
            allAlarms = allAlarms.concat(publicmove);
        }
        
        if (volumeLeaderRes.ok) {
            const volumeleader = await volumeLeaderRes.json();
            volumeleader.forEach(a => { a._type = 'volumeleader'; a._score = a.new_leader_share || 50; });
            allAlarms = allAlarms.concat(volumeleader);
        }
        
        console.log('[AlertBand] Total alarms before filter:', allAlarms.length);
        const filteredAlarms = allAlarms.filter(isMatchTodayOrFuture);
        console.log('[AlertBand] Alarms after filter (today+future):', filteredAlarms.length);
        
        const groupedForBand = groupAlarmsForBand(filteredAlarms);
        console.log('[AlertBand] Grouped alarms (unique):', groupedForBand.length);
        
        alertBandData = groupedForBand.sort((a, b) => {
            const timeA = new Date(a.trigger_at || a.event_time || a.created_at || 0).getTime();
            const timeB = new Date(b.trigger_at || b.event_time || b.created_at || 0).getTime();
            return timeB - timeA;
        });
        
        console.log('[AlertBand] Top 3 sorted:', alertBandData.slice(0, 3).map(a => ({
            home: a.home,
            event_time: a.trigger_at || a.event_time,
            type: a._type
        })));
        
        // İlk yüklemede doğrudan render et, sonraki güncellemelerde schedule kullan
        if (lastAlertBandHash === '') {
            console.log('[AlertBand] First render - direct call');
            renderAlertBand();
            updateAlertBandBadge();
            lastAlertBandHash = JSON.stringify(alertBandData.slice(0, 10).map(a => a.home + a._type + (a.trigger_at || a.event_time || '')));
            lastTopAlarmKey = getAlarmKey(alertBandData[0]);
        } else {
            scheduleAlertBandRender();
        }
    } catch (e) {
        console.error('[AlertBand] Load error:', e);
    }
}

function groupAlarmsForBand(alarms) {
    const groups = {};
    
    alarms.forEach(alarm => {
        const home = (alarm.home || alarm.home_team || '').toLowerCase().trim();
        const away = (alarm.away || alarm.away_team || '').toLowerCase().trim();
        const market = (alarm.market || '').toLowerCase().trim();
        const selection = (alarm.selection || alarm.side || '').toLowerCase().trim();
        const type = alarm._type;
        
        const groupKey = `${type}|${home}|${away}|${market}|${selection}`;
        
        if (!groups[groupKey]) {
            groups[groupKey] = alarm;
        } else {
            const currentBest = parseAlarmDate(groups[groupKey].trigger_at || groups[groupKey].event_time || groups[groupKey].created_at);
            const thisDate = parseAlarmDate(alarm.trigger_at || alarm.event_time || alarm.created_at);
            if (thisDate > currentBest) {
                groups[groupKey] = alarm;
            }
        }
    });
    
    return Object.values(groups);
}

function getAlertType(alarm) {
    const type = alarm._type;
    if (type === 'sharp') return { label: 'SHARP MOVE', color: 'green', pillClass: 'sharp' };
    if (type === 'insider') return { label: 'INSIDER INFO', color: 'purple', pillClass: 'insider' };
    if (type === 'bigmoney') {
        const stake = alarm.stake || alarm.volume || 0;
        if (stake >= 50000) {
            return { label: 'HUGE MONEY', color: 'orange-red', pillClass: 'hugemoney' };
        }
        return { label: 'BIG MONEY', color: 'orange', pillClass: 'bigmoney' };
    }
    if (type === 'volumeshock') return { label: 'HACIM SOKU', color: 'gold', pillClass: 'volumeshock' };
    if (type === 'dropping') {
        const level = alarm.level || 'L1';
        if (level === 'L3') return { label: 'DROP L3', color: 'red', pillClass: 'dropping-l3' };
        if (level === 'L2') return { label: 'DROP L2', color: 'red', pillClass: 'dropping-l2' };
        return { label: 'DROP L1', color: 'red', pillClass: 'dropping-l1' };
    }
    if (type === 'publicmove') return { label: 'PUBLIC MOVE', color: 'gold', pillClass: 'publicmove' };
    if (type === 'volumeleader') return { label: 'LIDER DEGISTI', color: 'cyan', pillClass: 'volumeleader' };
    return { label: 'ALERT', color: 'green', pillClass: '' };
}

function formatAlertValue(alarm) {
    const type = alarm._type;
    if (type === 'sharp') {
        return '+' + (alarm.sharp_score || 0).toFixed(0);
    }
    if (type === 'insider') {
        const dropPct = alarm.oran_dusus_pct || alarm.odds_drop_pct || 0;
        return '-' + dropPct.toFixed(1) + '%';
    }
    if (type === 'bigmoney') {
        const val = alarm.incoming_money || alarm.stake || alarm.volume || 0;
        return '£' + Number(val).toLocaleString('en-GB');
    }
    if (type === 'volumeshock') {
        const shockValue = alarm.volume_shock_value || alarm.volume_shock || alarm.volume_shock_multiplier || 0;
        return shockValue.toFixed(1) + 'x';
    }
    if (type === 'dropping') {
        const dropPct = alarm.drop_pct || 0;
        return '▼ ' + dropPct.toFixed(1) + '%';
    }
    if (type === 'publicmove') {
        const score = alarm.move_score || alarm.trap_score || alarm.sharp_score || 0;
        return score.toFixed(0);
    }
    if (type === 'volumeleader') {
        const share = alarm.new_leader_share || 0;
        return '%' + share.toFixed(0);
    }
    return '';
}

function renderAlertBand() {
    const track = document.getElementById('alertBandTrack');
    if (!track) return;
    
    if (!alertBandData || alertBandData.length === 0) {
        track.innerHTML = '<span class="alert-band-empty">Alarm bekleniyor...</span>';
        return;
    }
    
    // En yeni 10 alarm (en yeniden eskiye)
    const top = alertBandData.slice(0, 10);
    
    const pillsHtml = top.map((alarm, idx) => {
        const info = getAlertType(alarm);
        const home = alarm.home || alarm.home_team || '?';
        const away = alarm.away || alarm.away_team || '?';
        const selection = alarm.selection || alarm.side || '';
        
        // Minimal value format
        let value = '';
        if (alarm._type === 'sharp') {
            value = (alarm.sharp_score || 0).toFixed(1);
        } else if (alarm._type === 'insider') {
            const dropPct = Math.abs(alarm.oran_dusus_pct || alarm.odds_drop_pct || 0).toFixed(1);
            value = `▼ ${dropPct}%`;
        } else if (alarm._type === 'volumeshock') {
            value = `${(alarm.volume_shock_value || alarm.volume_shock || alarm.volume_shock_multiplier || 0).toFixed(1)}x`;
        } else if (alarm._type === 'bigmoney') {
            value = `£${Number(alarm.incoming_money || alarm.stake || 0).toLocaleString('en-GB')}`;
        } else if (alarm._type === 'dropping') {
            value = `▼ ${(alarm.drop_pct || 0).toFixed(1)}%`;
        } else if (alarm._type === 'publicmove') {
            value = `${(alarm.move_score || alarm.trap_score || alarm.sharp_score || 0).toFixed(0)}`;
        } else if (alarm._type === 'volumeleader') {
            value = `%${(alarm.new_leader_share || 0).toFixed(0)}`;
        }
        
        // Maç sayfasına yönlendirme için match_key oluştur
        const matchKey = `${home}_vs_${away}`.replace(/\s+/g, '_');
        
        const alarmType = alarm._type || '';
        const alarmMarket = (alarm.market || '').replace(/'/g, "\\'");
        
        // Volume Leader için özel format: OLD_LEADER > NEW_LEADER
        if (alarm._type === 'volumeleader') {
            const oldLeader = alarm.old_leader || alarm.previous_leader || '?';
            const newLeader = alarm.new_leader || alarm.selection || '?';
            return `
                <div class="ab-pill ${info.pillClass}" onclick="goToMatchPage('${matchKey}', '${alarmType}', '${alarmMarket}')" style="cursor: pointer;">
                    <span class="ab-dot dot-${info.pillClass}"></span>
                    <span class="ab-type">${info.label}</span>
                    <span class="ab-sep">—</span>
                    <span class="ab-match">${home} - ${away}</span>
                    <span class="ab-sep">—</span>
                    <span class="ab-leader-change">${oldLeader} <span class="ab-arrow">▸</span> ${newLeader}</span>
                </div>
            `;
        }
        
        return `
            <div class="ab-pill ${info.pillClass}" onclick="goToMatchPage('${matchKey}', '${alarmType}', '${alarmMarket}')" style="cursor: pointer;">
                <span class="ab-dot dot-${info.pillClass}"></span>
                <span class="ab-type">${info.label}</span>
                <span class="ab-sep">—</span>
                <span class="ab-match">${home} - ${away}</span>
                <span class="ab-sep">—</span>
                <span class="ab-sel">${selection}</span>
                <span class="ab-val">${value}</span>
            </div>
        `;
    }).join('');
    
    // Sonsuz döngü için alarmları duplicate et (10. sonrası 1. gelsin)
    track.innerHTML = `
        <div class="alert-band-track-inner">
            ${pillsHtml}${pillsHtml}
        </div>
    `;
}

function updateAlertBandBadge() {
    const badge = document.getElementById('alarmsBadge');
    if (badge) {
        const count = alertBandData.length;
        badge.textContent = count;
        badge.setAttribute('data-count', count);
    }
}

function showAlertBandDetail(index) {
    const alarm = alertBandData[index];
    if (!alarm) return;
    
    const info = getAlertType(alarm);
    const home = alarm.home || alarm.home_team || '-';
    const away = alarm.away || alarm.away_team || '-';
    const value = formatAlertValue(alarm);
    
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.id = 'alertBandModal';
    modal.onclick = (e) => { if (e.target === modal) modal.remove(); };
    
    let detailsHtml = '';
    if (alarm._type === 'sharp') {
        detailsHtml = `
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                <div style="background: #21262d; border-radius: 8px; padding: 12px; text-align: center;">
                    <div style="color: #4ade80; font-size: 20px; font-weight: 700;">${alarm.volume ? '£' + Number(alarm.volume).toLocaleString('en-GB') : '-'}</div>
                    <div style="color: #8b949e; font-size: 11px;">Volume</div>
                </div>
                <div style="background: #21262d; border-radius: 8px; padding: 12px; text-align: center;">
                    <div style="color: #f0883e; font-size: 20px; font-weight: 700;">${alarm.stake_share ? alarm.stake_share.toFixed(1) + '%' : '-'}</div>
                    <div style="color: #8b949e; font-size: 11px;">Stake Share</div>
                </div>
                <div style="background: #21262d; border-radius: 8px; padding: 12px; text-align: center;">
                    <div style="color: #58a6ff; font-size: 20px; font-weight: 700;">${alarm.odds_move ? (alarm.odds_move > 0 ? '+' : '') + alarm.odds_move.toFixed(2) : '-'}</div>
                    <div style="color: #8b949e; font-size: 11px;">Odds Move</div>
                </div>
                <div style="background: #21262d; border-radius: 8px; padding: 12px; text-align: center;">
                    <div style="color: #a371f7; font-size: 20px; font-weight: 700;">${alarm.volume_shock ? alarm.volume_shock.toFixed(1) + 'x' : '-'}</div>
                    <div style="color: #8b949e; font-size: 11px;">Volume Shock</div>
                </div>
            </div>
        `;
    } else if (alarm._type === 'insider') {
        detailsHtml = `
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                <div style="background: #21262d; border-radius: 8px; padding: 12px; text-align: center;">
                    <div style="color: #60a5fa; font-size: 20px; font-weight: 700;">${alarm.stake ? '£' + Number(alarm.stake).toLocaleString('en-GB') : '-'}</div>
                    <div style="color: #8b949e; font-size: 11px;">Stake</div>
                </div>
                <div style="background: #21262d; border-radius: 8px; padding: 12px; text-align: center;">
                    <div style="color: #f87171; font-size: 20px; font-weight: 700;">${alarm.odds_drop_pct ? alarm.odds_drop_pct.toFixed(2) + '%' : '-'}</div>
                    <div style="color: #8b949e; font-size: 11px;">Odds Drop</div>
                </div>
            </div>
        `;
    } else {
        detailsHtml = `
            <div style="background: #21262d; border-radius: 8px; padding: 16px; text-align: center;">
                <div style="color: #fbbf24; font-size: 28px; font-weight: 700;">${alarm.stake ? '£' + Number(alarm.stake).toLocaleString('en-GB') : (alarm.volume ? '£' + Number(alarm.volume).toLocaleString('en-GB') : '-')}</div>
                <div style="color: #8b949e; font-size: 12px; margin-top: 4px;">Stake Amount</div>
            </div>
        `;
    }
    
    const typeColors = { sharp: '#ef4444', insider: '#60a5fa', bigmoney: '#fbbf24', volumeshock: '#F6C343', dropping: '#f85149', publicmove: '#FFCC00', volumeleader: '#06b6d4' };
    
    modal.innerHTML = `
        <div class="modal-content" style="max-width: 480px;">
            <div class="modal-header">
                <h2 style="display: flex; align-items: center; gap: 10px;">
                    <span style="background: ${typeColors[alarm._type] || '#8b949e'}; width: 12px; height: 12px; border-radius: 50%;"></span>
                    ${info.label}
                </h2>
                <button class="close-btn" onclick="document.getElementById('alertBandModal').remove()">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                    </svg>
                </button>
            </div>
            <div class="modal-body" style="padding: 20px;">
                <div style="text-align: center; margin-bottom: 20px;">
                    <div style="font-size: 42px; font-weight: 700; color: ${typeColors[alarm._type] || '#8b949e'};">${value}</div>
                    <div style="color: #8b949e; font-size: 13px;">${alarm._type === 'sharp' ? 'Sharp Score' : (alarm._type === 'insider' ? 'Insider Score' : 'Stake')}</div>
                </div>
                <div style="background: #0d1117; border-radius: 8px; padding: 16px; margin-bottom: 16px;">
                    <div style="font-size: 18px; font-weight: 600; color: #fff; text-align: center; margin-bottom: 8px;">
                        ${home} vs ${away}
                    </div>
                    <div style="text-align: center; color: #8b949e; font-size: 13px;">
                        ${alarm.market || '-'} | <span style="color: #58a6ff;">${alarm.selection || alarm.side || '-'}</span>
                    </div>
                </div>
                ${detailsHtml}
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
}

setInterval(loadAlertBand, 60000);
document.addEventListener('DOMContentLoaded', () => {
    setTimeout(loadAlertBand, 500);
});

// ============================================
// ALARMS SIDEBAR FUNCTIONALITY
// ============================================

let currentAlarmFilter = 'all';
let currentAlarmSort = 'newest';
let allAlarmsData = [];
let groupedAlarmsData = [];
let alarmsDataByType = {
    sharp: [],
    insider: [],
    bigmoney: [],
    volumeshock: [],
    dropping: [],
    publicmove: [],
    volumeleader: []
};
let alarmSearchQuery = '';
let alarmsDisplayCount = 30;
let alarmsSidebarOpen = false;
let openAlarmId = null;

function toggleAlarmsSidebar() {
    if (alarmsSidebarOpen) {
        closeAlarmsSidebar();
    } else {
        openAlarmsSidebar();
    }
}

function openAlarmsSidebar() {
    alarmsSidebarOpen = true;
    document.getElementById('alarmsSidebar').classList.add('open');
    document.getElementById('alarmsSidebarOverlay').classList.add('open');
    document.body.style.overflow = 'hidden';
    const btn = document.getElementById('alarmsBtn');
    if (btn) btn.classList.add('active');
    loadAllAlarms();
}

function closeAlarmsSidebar() {
    alarmsSidebarOpen = false;
    document.getElementById('alarmsSidebar').classList.remove('open');
    document.getElementById('alarmsSidebarOverlay').classList.remove('open');
    document.body.style.overflow = '';
    const btn = document.getElementById('alarmsBtn');
    if (btn) btn.classList.remove('active');
}

async function loadAllAlarms() {
    const body = document.getElementById('alarmsList');
    body.innerHTML = '<div class="alarms-loading">Alarmlar yukleniyor...</div>';
    
    try {
        const [sharpRes, insiderRes, bigMoneyRes, volumeShockRes, droppingRes, publicmoveRes, volumeLeaderRes] = await Promise.all([
            fetch('/api/sharp/alarms').catch(() => ({ ok: false })),
            fetch('/api/insider/alarms').catch(() => ({ ok: false })),
            fetch('/api/bigmoney/alarms').catch(() => ({ ok: false })),
            fetch('/api/volumeshock/alarms').catch(() => ({ ok: false })),
            fetch('/api/dropping/alarms').catch(() => ({ ok: false })),
            fetch('/api/publicmove/alarms').catch(() => ({ ok: false })),
            fetch('/api/volumeleader/alarms').catch(() => ({ ok: false }))
        ]);
        
        const rawSharp = sharpRes.ok ? await sharpRes.json() : [];
        const rawInsider = insiderRes.ok ? await insiderRes.json() : [];
        const rawBigmoney = bigMoneyRes.ok ? await bigMoneyRes.json() : [];
        const rawVolumeshock = volumeShockRes.ok ? await volumeShockRes.json() : [];
        const rawDropping = droppingRes.ok ? await droppingRes.json() : [];
        const rawPublicmove = publicmoveRes.ok ? await publicmoveRes.json() : [];
        const rawVolumeleader = volumeLeaderRes.ok ? await volumeLeaderRes.json() : [];
        
        alarmsDataByType.sharp = rawSharp.filter(isMatchTodayOrFuture);
        alarmsDataByType.insider = rawInsider.filter(isMatchTodayOrFuture);
        alarmsDataByType.bigmoney = rawBigmoney.filter(isMatchTodayOrFuture);
        alarmsDataByType.volumeshock = rawVolumeshock.filter(isMatchTodayOrFuture);
        alarmsDataByType.dropping = rawDropping.filter(isMatchTodayOrFuture);
        alarmsDataByType.publicmove = rawPublicmove.filter(isMatchTodayOrFuture);
        alarmsDataByType.volumeleader = rawVolumeleader.filter(isMatchTodayOrFuture);
        
        const sharpWithType = alarmsDataByType.sharp.map(a => ({ ...a, _type: 'sharp' }));
        const insiderWithType = alarmsDataByType.insider.map(a => ({ ...a, _type: 'insider' }));
        const bigmoneyWithType = alarmsDataByType.bigmoney.map(a => ({ ...a, _type: 'bigmoney' }));
        const volumeshockWithType = alarmsDataByType.volumeshock.map(a => ({ ...a, _type: 'volumeshock' }));
        const droppingWithType = alarmsDataByType.dropping.map(a => ({ ...a, _type: 'dropping' }));
        const publicmoveWithType = alarmsDataByType.publicmove.map(a => ({ ...a, _type: 'publicmove' }));
        const volumeleaderWithType = alarmsDataByType.volumeleader.map(a => ({ ...a, _type: 'volumeleader' }));
        
        allAlarmsData = [...sharpWithType, ...insiderWithType, ...bigmoneyWithType, ...volumeshockWithType, ...droppingWithType, ...publicmoveWithType, ...volumeleaderWithType];
        
        allAlarmsData.sort((a, b) => {
            const dateA = parseAlarmDate(a.trigger_at || a.event_time || a.created_at);
            const dateB = parseAlarmDate(b.trigger_at || b.event_time || b.created_at);
            return dateB - dateA;
        });
        
        groupedAlarmsData = groupAlarmsByMatch(allAlarmsData);
        
        updateAlarmCounts();
        alarmsDisplayCount = 30;
        
        const selectEl = document.getElementById('alarmSortSelect');
        if (selectEl) {
            selectEl.value = currentAlarmSort;
        }
        
        renderAlarmsList(currentAlarmFilter);
    } catch (error) {
        console.error('Alarm yukleme hatasi:', error);
        body.innerHTML = '<div class="alarms-empty"><p>Alarmlar yuklenirken hata olustu.</p></div>';
    }
}

function groupAlarmsByMatch(alarms) {
    const groups = {};
    
    alarms.forEach(alarm => {
        const home = (alarm.home || alarm.home_team || '').toLowerCase().trim();
        const away = (alarm.away || alarm.away_team || '').toLowerCase().trim();
        const market = (alarm.market || '').toLowerCase().trim();
        const selection = (alarm.selection || alarm.side || '').toLowerCase().trim();
        const type = alarm._type;
        
        const groupKey = `${type}|${home}|${away}|${market}|${selection}`;
        
        if (!groups[groupKey]) {
            groups[groupKey] = {
                key: groupKey,
                type: type,
                home: alarm.home || alarm.home_team || '-',
                away: alarm.away || alarm.away_team || '-',
                home_team: alarm.home_team || alarm.home || '-',
                away_team: alarm.away_team || alarm.away || '-',
                match_id: alarm.match_id || '',
                market: alarm.market || '',
                selection: alarm.selection || alarm.side || '',
                league: alarm.league || '',
                match_date: alarm.match_date || alarm.fixture_date || '',
                fixture_date: alarm.fixture_date || alarm.match_date || '',
                latestAlarm: alarm,
                allAlarms: [],
                history: [],
                triggerCount: 0
            };
        }
        
        groups[groupKey].allAlarms.push(alarm);
        groups[groupKey].triggerCount++;
        
        const currentLatest = parseAlarmDate(groups[groupKey].latestAlarm.trigger_at || groups[groupKey].latestAlarm.event_time || groups[groupKey].latestAlarm.created_at);
        const thisDate = parseAlarmDate(alarm.trigger_at || alarm.event_time || alarm.created_at);
        if (thisDate > currentLatest) {
            groups[groupKey].latestAlarm = alarm;
            groups[groupKey].match_id = alarm.match_id || groups[groupKey].match_id;
            groups[groupKey].match_date = alarm.match_date || alarm.fixture_date || groups[groupKey].match_date;
            groups[groupKey].fixture_date = alarm.fixture_date || alarm.match_date || groups[groupKey].fixture_date;
        }
    });
    
    Object.values(groups).forEach(group => {
        group.allAlarms.sort((a, b) => parseAlarmDate(b.trigger_at || b.event_time || b.created_at) - parseAlarmDate(a.trigger_at || a.event_time || a.created_at));
        group.history = group.allAlarms.slice(1);
    });
    
    return Object.values(groups).sort((a, b) => {
        const dateA = parseAlarmDate(a.latestAlarm.trigger_at || a.latestAlarm.event_time || a.latestAlarm.created_at);
        const dateB = parseAlarmDate(b.latestAlarm.trigger_at || b.latestAlarm.event_time || b.latestAlarm.created_at);
        return dateB - dateA;
    });
}

function updateAlarmCounts() {
    const badge = document.getElementById('alarmsBadge');
    if (badge) badge.textContent = allAlarmsData.length;
    
    const countAll = document.getElementById('countAll');
    const countSharp = document.getElementById('countSharp');
    const countInsider = document.getElementById('countInsider');
    const countBigmoney = document.getElementById('countBigmoney');
    const countVolumeshock = document.getElementById('countVolumeshock');
    const countDropping = document.getElementById('countDropping');
    const countPublicmove = document.getElementById('countPublicmove');
    const countVolumeleader = document.getElementById('countVolumeleader');
    
    if (countAll) countAll.textContent = allAlarmsData.length;
    if (countSharp) countSharp.textContent = alarmsDataByType.sharp?.length || 0;
    if (countInsider) countInsider.textContent = alarmsDataByType.insider?.length || 0;
    if (countBigmoney) countBigmoney.textContent = alarmsDataByType.bigmoney?.length || 0;
    if (countVolumeshock) countVolumeshock.textContent = alarmsDataByType.volumeshock?.length || 0;
    if (countDropping) countDropping.textContent = alarmsDataByType.dropping?.length || 0;
    if (countPublicmove) countPublicmove.textContent = alarmsDataByType.publicmove?.length || 0;
    if (countVolumeleader) countVolumeleader.textContent = alarmsDataByType.volumeleader?.length || 0;
}

function sortAlarms(sortType) {
    console.log('[sortAlarms] Sort type changed to:', sortType);
    currentAlarmSort = sortType;
    
    const selectEl = document.getElementById('alarmSortSelect');
    if (selectEl && selectEl.value !== sortType) {
        selectEl.value = sortType;
    }
    
    alarmsDisplayCount = 30;
    renderAlarmsList(currentAlarmFilter);
}

function parseAlarmDate(dateStr) {
    if (!dateStr) return new Date(0);
    
    const str = String(dateStr).trim();
    
    // DD.MM.YYYY HH:MM format (legacy format)
    const ddmmMatch = str.match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})\s*(\d{2}:\d{2})?$/);
    if (ddmmMatch) {
        const [, day, month, year, time] = ddmmMatch;
        const [hour, min] = (time || '00:00').split(':');
        // Bu format zaten TR saatinde, Date objesi oluştur
        return new Date(parseInt(year), parseInt(month) - 1, parseInt(day), parseInt(hour), parseInt(min));
    }
    
    // toTurkeyTime ile parse et (ISO formatları, UTC, timezone offset'li vs.)
    const turkeyTime = toTurkeyTime(str);
    if (turkeyTime && turkeyTime.isValid()) {
        return turkeyTime.toDate();
    }
    
    // Fallback
    return new Date(str) || new Date(0);
}

const alarmFilterColors = {
    all: null,
    sharp: '#4ade80',
    insider: '#a855f7',
    bigmoney: '#F08A24',
    volumeshock: '#F6C343',
    dropping: '#f85149',
    publicmove: '#FFCC00',
    volumeleader: '#06b6d4'
};

const alarmFilterLabels = {
    all: 'Tumu',
    sharp: 'Sharp',
    insider: 'Insider Info',
    bigmoney: 'Buyuk Para',
    volumeshock: 'Hacim Soku',
    dropping: 'Dropping',
    publicmove: 'Public Move',
    volumeleader: 'Lider Degisti'
};

function toggleAlarmFilterDropdown() {
    const dropdown = document.getElementById('alarmFilterDropdown');
    dropdown.classList.toggle('open');
}

function selectAlarmFilter(type) {
    const dropdown = document.getElementById('alarmFilterDropdown');
    const dotDisplay = document.getElementById('filterDotDisplay');
    const labelDisplay = document.getElementById('filterLabelDisplay');
    
    dropdown.classList.remove('open');
    
    document.querySelectorAll('.alarm-filter-option').forEach(opt => {
        opt.classList.toggle('selected', opt.dataset.value === type);
    });
    
    labelDisplay.textContent = alarmFilterLabels[type] || 'Tumu';
    
    if (type === 'all') {
        dotDisplay.className = 'filter-dot-display show';
        dotDisplay.style.background = '#6b7280';
        dotDisplay.innerHTML = '';
    } else {
        dotDisplay.className = 'filter-dot-display show';
        dotDisplay.style.background = alarmFilterColors[type] || '#8b949e';
        dotDisplay.innerHTML = '';
    }
    
    filterAlarms(type);
}

document.addEventListener('click', function(e) {
    const dropdown = document.getElementById('alarmFilterDropdown');
    if (dropdown && !dropdown.contains(e.target)) {
        dropdown.classList.remove('open');
    }
});

function filterAlarms(type) {
    currentAlarmFilter = type;
    alarmsDisplayCount = 30;
    
    document.querySelectorAll('.alarm-pill').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.type === type);
    });
    
    renderAlarmsList(type);
}

function searchAlarms(query) {
    alarmSearchQuery = query.toLowerCase().trim();
    alarmsDisplayCount = 30;
    renderAlarmsList(currentAlarmFilter);
}

function getFilteredAlarms() {
    let groups = currentAlarmFilter === 'all' 
        ? [...groupedAlarmsData]
        : groupedAlarmsData.filter(g => g.type === currentAlarmFilter);
    
    if (alarmSearchQuery) {
        groups = groups.filter(g => {
            const home = g.home.toLowerCase();
            const away = g.away.toLowerCase();
            const league = (g.league || '').toLowerCase();
            return home.includes(alarmSearchQuery) || 
                   away.includes(alarmSearchQuery) || 
                   league.includes(alarmSearchQuery);
        });
    }
    
    console.log('[getFilteredAlarms] Sorting by:', currentAlarmSort, 'Groups count:', groups.length);
    
    groups.sort((a, b) => {
        const dateA = parseAlarmDate(a.latestAlarm.trigger_at || a.latestAlarm.event_time || a.latestAlarm.created_at);
        const dateB = parseAlarmDate(b.latestAlarm.trigger_at || b.latestAlarm.event_time || b.latestAlarm.created_at);
        
        if (currentAlarmSort === 'newest') {
            return dateB - dateA;
        } else if (currentAlarmSort === 'oldest') {
            return dateA - dateB;
        } else if (currentAlarmSort === 'score_high') {
            const scoreA = a.latestAlarm.sharp_score || a.latestAlarm.insider_score || a.latestAlarm.incoming_money || 0;
            const scoreB = b.latestAlarm.sharp_score || b.latestAlarm.insider_score || b.latestAlarm.incoming_money || 0;
            return scoreB - scoreA;
        } else if (currentAlarmSort === 'score_low') {
            const scoreA = a.latestAlarm.sharp_score || a.latestAlarm.insider_score || a.latestAlarm.incoming_money || 0;
            const scoreB = b.latestAlarm.sharp_score || b.latestAlarm.insider_score || b.latestAlarm.incoming_money || 0;
            return scoreA - scoreB;
        }
        return dateB - dateA;
    });
    
    if (groups.length > 0) {
        console.log('[getFilteredAlarms] First 3 after sort:', groups.slice(0, 3).map(g => ({
            home: g.home,
            time: g.latestAlarm.trigger_at || g.latestAlarm.event_time
        })));
    }
    
    return groups;
}

function renderAlarmsList(filterType) {
    const body = document.getElementById('alarmsList');
    const groups = getFilteredAlarms();
    
    if (groups.length === 0) {
        body.innerHTML = `<div class="alarms-empty">${alarmSearchQuery ? 'Arama sonucu bulunamadi' : 'Aktif alarm yok'}</div>`;
        return;
    }
    
    const displayGroups = groups.slice(0, alarmsDisplayCount);
    const hasMore = groups.length > alarmsDisplayCount;
    const typeLabels = { sharp: 'SHARP', insider: 'INSIDER', bigmoney: 'BIG MONEY', volumeshock: 'HACIM SOKU', dropping: 'DROPPING', publicmove: 'PUBLIC MOVE', volumeleader: 'LİDER DEĞİŞTİ' };
    const typeColors = { sharp: '#4ade80', insider: '#a855f7', bigmoney: '#F08A24', volumeshock: '#F6C343', dropping: '#f85149', publicmove: '#FFCC00', volumeleader: '#06b6d4' };
    
    let html = displayGroups.map((group, idx) => {
        const type = group.type;
        const alarm = group.latestAlarm;
        const home = group.home;
        const away = group.away;
        const market = group.market;
        const selection = group.selection;
        const alarmId = `alarm_${type}_${idx}`;
        const isOpen = openAlarmId === alarmId;
        
        let mainValue = '';
        let centerBadge = '';
        
        if (type === 'sharp') {
            const score = (alarm.sharp_score || 0).toFixed(1);
            const oddsDrop = alarm.odds_drop_pct || 0;
            const oddsSign = oddsDrop < 0 ? '\u2212' : '+';
            const volume = alarm.volume || alarm.stake || 0;
            const moneyPart = volume > 0 ? `<span class="value-money">\u00A3${Number(volume).toLocaleString('en-GB')}</span><span class="sep">\u2022</span>` : '';
            mainValue = `${moneyPart}<span class="value-highlight">Sharp Puanı ${score}</span><span class="sep">\u2022</span><span class="value-pct">%${oddsSign}${Math.abs(oddsDrop).toFixed(1)}</span>`;
        } else if (type === 'insider') {
            const openingOdds = alarm.opening_odds || 0;
            const lastOdds = alarm.last_odds || 0;
            const oddsDrop = alarm.oran_dusus_pct || alarm.odds_drop_pct || 0;
            mainValue = `<span class="value-odds">${openingOdds.toFixed(2)}</span><span class="arrow">\u2192</span><span class="value-odds-new">${lastOdds.toFixed(2)}</span><span class="sep">\u2022</span><span class="value-pct-drop">\u2212${Math.abs(oddsDrop).toFixed(1)}%</span>`;
        } else if (type === 'bigmoney') {
            const money = alarm.incoming_money || alarm.stake || 0;
            mainValue = `<span class="value-money">£${Number(money).toLocaleString('en-GB')}</span>`;
            const isHuge = alarm.is_huge || alarm.alarm_type === 'HUGE MONEY';
            if (isHuge) {
                centerBadge = '<span class="huge-badge">HUGE</span>';
            }
        } else if (type === 'volumeshock') {
            const shockValue = alarm.volume_shock_value || alarm.volume_shock || alarm.volume_shock_multiplier || 0;
            const hoursToKickoff = calculateHoursToKickoff(alarm);
            mainValue = `<span class="value-highlight">${shockValue.toFixed(1)}x</span><span class="sep">•</span><span class="value-pct">${hoursToKickoff.toFixed(1)} saat kala</span>`;
        } else if (type === 'dropping') {
            const openingOdds = alarm.opening_odds || 0;
            const currentOdds = alarm.current_odds || 0;
            const dropPct = alarm.drop_pct || 0;
            const level = alarm.level || 'L1';
            mainValue = `<span class="value-odds">${openingOdds.toFixed(2)}</span><span class="arrow">→</span><span class="value-odds-new">${currentOdds.toFixed(2)}</span><span class="sep">•</span><span class="value-pct-drop">▼${dropPct.toFixed(1)}%</span>`;
            centerBadge = `<span class="level-badge level-${level.toLowerCase()}">${level}</span>`;
        } else if (type === 'publicmove') {
            const score = alarm.move_score || alarm.trap_score || alarm.sharp_score || 0;
            const volume = alarm.volume || 0;
            const moneyPart = volume > 0 ? `<span class="value-money">£${Number(volume).toLocaleString('en-GB')}</span><span class="sep">•</span>` : '';
            mainValue = `${moneyPart}<span class="value-highlight">Move Skor ${score.toFixed(0)}</span>`;
        } else if (type === 'volumeleader') {
            const oldLeader = alarm.old_leader || '-';
            const newLeader = alarm.new_leader || '-';
            const oldShare = (alarm.old_leader_share || 0).toFixed(0);
            const newShare = (alarm.new_leader_share || 0).toFixed(0);
            mainValue = `<span class="value-odds">${oldLeader} %${oldShare}</span><span class="arrow">→</span><span class="value-odds-new">${newLeader} %${newShare}</span>`;
        }
        
        // Tum alarmlar icin trigger_at oncelikli (alarmın tetiklendigi an)
        const timeSource = alarm.trigger_at || alarm.event_time || alarm.created_at;
        console.log(`[AlarmCard] ${type} ${home}: trigger_at=${alarm.trigger_at}, event_time=${alarm.event_time}, created_at=${alarm.created_at}, timeSource=${timeSource}`);
        const triggerTimeShort = formatTriggerTimeShort(timeSource);
        const triggerPill = group.triggerCount > 1 ? `<span class="trigger-pill">×${group.triggerCount}</span>` : '';
        const marketLabel = formatMarketChip(market, selection);
        const expandIcon = isOpen ? '▼' : '▶';
        
        const stripeColors = {
            'bigmoney': '#F08A24',
            'sharp': '#22c55e',
            'insider': '#a855f7',
            'dropping': '#f85149',
            'volumeshock': '#F6C343',
            'publicmove': '#FFCC00',
            'volumeleader': '#06b6d4'
        };
        const stripeColor = stripeColors[type] || '#64748b';
        
        const typeBadges = {
            'bigmoney': alarm.is_huge ? 'HUGE' : 'BIG',
            'sharp': 'SHARP',
            'insider': 'INSIDER',
            'dropping': alarm.level || 'DROP',
            'volumeshock': 'HS',
            'publicmove': 'TRAP',
            'volumeleader': 'LİDER'
        };
        const typeBadge = typeBadges[type] || type.toUpperCase();
        
        let mainMoney = 0;
        if (type === 'bigmoney') {
            mainMoney = alarm.incoming_money || alarm.stake || 0;
        } else if (type === 'sharp') {
            mainMoney = alarm.volume || alarm.stake || 0;
        } else if (type === 'insider') {
            mainMoney = alarm.stake || alarm.volume || 0;
        } else if (type === 'volumeshock') {
            mainMoney = alarm.incoming_money || 0;
        } else if (type === 'dropping') {
            mainMoney = 0;
        } else if (type === 'publicmove') {
            mainMoney = alarm.volume || 0;
        } else if (type === 'volumeleader') {
            mainMoney = alarm.total_volume || 0;
        }
        
        // Alarm detay paneli - Tip'e göre içerik
        const homeEscaped = home.replace(/'/g, "\\'");
        const awayEscaped = away.replace(/'/g, "\\'");
        const marketEscaped = market.replace(/'/g, "\\'");
        const matchTimeFormatted = formatMatchTime3(group.match_date);
        const marketLabel2 = `${market} → ${selection}`;
        // Dropping alarmlar icin created_at (oranin dustugu an) oncelikli
        const triggerTimeSource = type === 'dropping' 
            ? (alarm.created_at || alarm.event_time || alarm.trigger_at)
            : (alarm.trigger_at || alarm.event_time || alarm.created_at);
        const triggerTime = formatTriggerTime(triggerTimeSource);
        
        // Badge ve metrik içeriği
        let badgeLabel = '';
        let metricContent = '';
        let historyLine = '';
        
        if (type === 'sharp') {
            badgeLabel = 'SHARP';
            const score = (alarm.sharp_score || 0).toFixed(1);
            const volumeContrib = (alarm.volume_contrib || 0).toFixed(1);
            const oddsContrib = (alarm.odds_contrib || 0).toFixed(1);
            const shareContrib = (alarm.share_contrib || 0).toFixed(1);
            const prevOdds = (alarm.previous_odds || 0).toFixed(2);
            const currOdds = (alarm.current_odds || 0).toFixed(2);
            const prevShare = (alarm.previous_share || 0).toFixed(1);
            const currShare = (alarm.current_share || 0).toFixed(1);
            metricContent = `<div class="acd-grid">
                <div class="acd-stat">
                    <div class="acd-stat-val sharp">${score}</div>
                    <div class="acd-stat-lbl">Sharp Skor</div>
                </div>
                <div class="acd-stat">
                    <div class="acd-stat-val">${volumeContrib}</div>
                    <div class="acd-stat-lbl">Hacim Puan</div>
                </div>
                <div class="acd-stat">
                    <div class="acd-stat-val">${oddsContrib}</div>
                    <div class="acd-stat-lbl">Oran Puan</div>
                </div>
                <div class="acd-stat">
                    <div class="acd-stat-val">${shareContrib}</div>
                    <div class="acd-stat-lbl">Pay Puan</div>
                </div>
            </div>
            <div class="acd-info-row">
                <span>Oran: ${prevOdds} → ${currOdds}</span>
                <span>Pay: ${prevShare}% → ${currShare}%</span>
            </div>`;
            historyLine = `${triggerTime}`;
        } else if (type === 'insider') {
            badgeLabel = 'INSIDER';
            const openOdds = (alarm.opening_odds || 0).toFixed(2);
            const lastOdds = (alarm.current_odds || alarm.last_odds || 0).toFixed(2);
            const dropPct = Math.abs(alarm.oran_dusus_pct || alarm.odds_drop_pct || 0).toFixed(1);
            const gelenPara = alarm.gelen_para || 0;
            metricContent = `<div class="acd-grid cols-2">
                <div class="acd-stat">
                    <div class="acd-stat-val insider">${openOdds} → ${lastOdds}</div>
                    <div class="acd-stat-lbl">Oran Değişimi</div>
                </div>
                <div class="acd-stat">
                    <div class="acd-stat-val drop">▼ ${dropPct}%</div>
                    <div class="acd-stat-lbl">Düşüş</div>
                </div>
            </div>
            <div class="acd-info-row">
                <span>Gelen Para: £${Number(gelenPara).toLocaleString('en-GB')}</span>
            </div>`;
            historyLine = `${triggerTime}`;
        } else if (type === 'volumeshock') {
            badgeLabel = 'HACİM ŞOKU';
            const newMoney = alarm.incoming_money || 0;
            const shockVal = (alarm.volume_shock_value || alarm.volume_shock || alarm.volume_shock_multiplier || 0).toFixed(1);
            const hoursToKickoff = calculateHoursToKickoff(alarm);
            metricContent = `<div class="acd-grid cols-2">
                <div class="acd-stat">
                    <div class="acd-stat-val volumeshock">${shockVal}x</div>
                    <div class="acd-stat-lbl">Hacim Şoku</div>
                </div>
                <div class="acd-stat">
                    <div class="acd-stat-val">£${Number(newMoney).toLocaleString('en-GB')}</div>
                    <div class="acd-stat-lbl">Gelen Para</div>
                </div>
            </div>
            <div class="acd-info-row">
                <span>Maça ${hoursToKickoff.toFixed(1)} saat kala</span>
            </div>`;
            historyLine = `${triggerTime}`;
        } else if (type === 'bigmoney') {
            badgeLabel = alarm.is_huge ? 'HUGE MONEY' : 'BIG MONEY';
            const money = alarm.incoming_money || alarm.stake || 0;
            const selectionTotal = alarm.selection_total || alarm.volume || alarm.total_volume || 0;
            
            // Önceki alarmlar - alarm_history'den al
            let historyHtml = '';
            let alarmHistory = alarm.alarm_history || [];
            if (typeof alarmHistory === 'string') {
                try { alarmHistory = JSON.parse(alarmHistory); } catch(e) { alarmHistory = []; }
            }
            if (alarmHistory && alarmHistory.length > 0) {
                const historyItems = alarmHistory.slice().reverse().map(h => {
                    const hTime = formatTriggerTime(h.trigger_at);
                    const hMoney = Number(h.incoming_money || 0).toLocaleString('en-GB');
                    return `<div class="acd-history-item"><span class="acd-history-time">${hTime}</span><span class="acd-history-val">£${hMoney}</span></div>`;
                }).join('');
                historyHtml = `<div class="acd-history-section">
                    <div class="acd-history-title">ÖNCEKİ</div>
                    ${historyItems}
                </div>`;
            }
            
            // Toplam 0 ise gösterme, değilse göster
            const totalHtml = selectionTotal > 0 
                ? `<div class="acd-stat acd-stat-secondary">
                    <div class="acd-stat-val muted">£${Number(selectionTotal).toLocaleString('en-GB')}</div>
                    <div class="acd-stat-lbl">Toplam</div>
                  </div>` 
                : '';
            
            metricContent = `<div class="acd-bigmoney-hero">
                <div class="acd-hero-amount">£${Number(money).toLocaleString('en-GB')}</div>
                <div class="acd-hero-label">Büyük Para Girişi</div>
            </div>${totalHtml ? `<div class="acd-grid cols-1">${totalHtml}</div>` : ''}${historyHtml}`;
            historyLine = alarmHistory.length > 0 ? `×${alarmHistory.length + 1}` : `${triggerTime}`;
        } else if (type === 'dropping') {
            const level = alarm.level || 'L1';
            badgeLabel = `DROPPING ${level}`;
            const openOdds = (alarm.opening_odds || 0).toFixed(2);
            const currOdds = (alarm.current_odds || 0).toFixed(2);
            const dropPct = (alarm.drop_pct || 0).toFixed(1);
            const matchDateFormatted = formatMatchDateShort(alarm.match_date || '');
            metricContent = `<div class="acd-grid cols-2">
                <div class="acd-stat">
                    <div class="acd-stat-val dropping">${openOdds} → ${currOdds}</div>
                    <div class="acd-stat-lbl">Oran Değişimi</div>
                </div>
                <div class="acd-stat">
                    <div class="acd-stat-val drop">▼ ${dropPct}%</div>
                    <div class="acd-stat-lbl">Düşüş (${level})</div>
                </div>
            </div>
            ${matchDateFormatted ? `<div class="acd-info-row"><span>📅 Maç: ${matchDateFormatted}</span></div>` : ''}`;
            historyLine = `${triggerTime}`;
        } else if (type === 'publicmove') {
            badgeLabel = 'PUBLIC MOVE';
            const score = (alarm.move_score || alarm.trap_score || alarm.sharp_score || 0).toFixed(0);
            const volume = alarm.volume || 0;
            metricContent = `<div class="acd-grid cols-2">
                <div class="acd-stat">
                    <div class="acd-stat-val publicmove">${score}</div>
                    <div class="acd-stat-lbl">Move Skor</div>
                </div>
                <div class="acd-stat">
                    <div class="acd-stat-val">£${Number(volume).toLocaleString('en-GB')}</div>
                    <div class="acd-stat-lbl">Hacim</div>
                </div>
            </div>`;
            historyLine = `${triggerTime}`;
        } else if (type === 'volumeleader') {
            badgeLabel = 'LİDER DEĞİŞTİ';
            const oldLeader = alarm.old_leader || '-';
            const newLeader = alarm.new_leader || '-';
            const oldShare = (alarm.old_leader_share || 0).toFixed(0);
            const newShare = (alarm.new_leader_share || 0).toFixed(0);
            const totalVol = alarm.total_volume || 0;
            metricContent = `<div class="acd-grid cols-2">
                <div class="acd-stat">
                    <div class="acd-stat-val volumeleader">${oldLeader} %${oldShare}</div>
                    <div class="acd-stat-lbl">Eski Lider</div>
                </div>
                <div class="acd-stat">
                    <div class="acd-stat-val volumeleader-new">${newLeader} %${newShare}</div>
                    <div class="acd-stat-lbl">Yeni Lider</div>
                </div>
            </div>
            <div class="acd-info-row">
                <span>Toplam Hacim: £${Number(totalVol).toLocaleString('en-GB')}</span>
            </div>`;
            historyLine = `${triggerTime}`;
        }
        
        const fullMatchName = `${home} – ${away}`;
        
        // Metrik değer (sağ tarafa)
        let metricValue = '';
        if (type === 'sharp') {
            metricValue = (alarm.sharp_score || 0).toFixed(1);
        } else if (type === 'insider') {
            const dropPct = Math.abs(alarm.oran_dusus_pct || alarm.odds_drop_pct || 0).toFixed(1);
            metricValue = `▼ ${dropPct}%`;
        } else if (type === 'volumeshock') {
            metricValue = `${(alarm.volume_shock_value || alarm.volume_shock || alarm.volume_shock_multiplier || 0).toFixed(1)}x`;
        } else if (type === 'bigmoney') {
            metricValue = `£${Number(alarm.incoming_money || alarm.stake || 0).toLocaleString('en-GB')}`;
        } else if (type === 'dropping') {
            metricValue = `▼ ${(alarm.drop_pct || 0).toFixed(1)}%`;
        } else if (type === 'publicmove') {
            metricValue = (alarm.move_score || alarm.trap_score || alarm.sharp_score || 0).toFixed(0);
        } else if (type === 'volumeleader') {
            const oldL = alarm.old_leader || '-';
            const newL = alarm.new_leader || '-';
            metricValue = `<span class="vl-transition"><span class="vl-old">${oldL}</span><span class="vl-arrow">›</span><span class="vl-new">${newL}</span></span>`;
        }
        
        const historyCount = group.history.length;
        const historyBadge = historyCount > 0 ? `<span class="history-badge">×${historyCount + 1}</span>` : '';
        
        let historySection = '';
        if (historyCount > 0 && isOpen) {
            const historyItems = group.history.map(h => {
                const hTime = formatTriggerTime(h.trigger_at || h.event_time || h.created_at);
                let hValue = '';
                if (type === 'sharp') {
                    hValue = `Sharp ${(h.sharp_score || 0).toFixed(1)}`;
                } else if (type === 'insider') {
                    hValue = `▼ ${Math.abs(h.oran_dusus_pct || h.odds_drop_pct || 0).toFixed(1)}%`;
                } else if (type === 'volumeshock') {
                    hValue = `${(h.volume_shock_value || h.volume_shock || h.volume_shock_multiplier || 0).toFixed(1)}x`;
                } else if (type === 'bigmoney') {
                    hValue = `£${Number(h.incoming_money || h.stake || 0).toLocaleString('en-GB')}`;
                } else if (type === 'dropping') {
                    hValue = `▼ ${(h.drop_pct || 0).toFixed(1)}%`;
                } else if (type === 'publicmove') {
                    hValue = `Trap ${(h.trap_score || h.sharp_score || 0).toFixed(0)}`;
                } else if (type === 'volumeleader') {
                    hValue = `<span class="vl-mini">${h.old_leader || '-'} › ${h.new_leader || '-'}</span>`;
                }
                return `<div class="history-item"><span class="history-time">${hTime}</span><span class="history-val">${hValue}</span></div>`;
            }).join('');
            historySection = `<div class="acd-history-list"><div class="history-title">Önceki Alarmlar</div>${historyItems}</div>`;
        }
        
        return `
            <div class="ac ${type} ${isOpen ? 'open' : ''}" id="card_${alarmId}">
                <div class="ac-stripe"></div>
                <div class="ac-body" onclick="toggleAlarmDetail('${alarmId}')">
                    <div class="ac-summary">
                        <div class="ac-top">
                            <span class="ac-dot"></span>
                            <span class="ac-label">${typeLabels[type]}</span>
                            ${historyBadge}
                            <span class="ac-sep">·</span>
                            <span class="ac-time">${triggerTimeShort}</span>
                        </div>
                        <div class="ac-mid">
                            <span class="ac-match">${fullMatchName}</span>
                            <span class="ac-value">${metricValue}</span>
                        </div>
                        <div class="ac-bot">${marketLabel}</div>
                    </div>
                    <div class="ac-detail" id="detail_${alarmId}" onclick="event.stopPropagation()">
                        <div class="ac-detail-inner">
                            <div class="acd-divider"></div>
                            <div class="acd-header">${matchTimeFormatted}</div>
                            ${metricContent}
                            <div class="acd-history">${historyLine}</div>
                            ${historySection}
                            <button class="acd-btn" onclick="event.stopPropagation(); goToMatchFromAlarm('${homeEscaped}', '${awayEscaped}', '${type}', '${marketEscaped}')">Maç Sayfasını Aç</button>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }).join('');
    
    if (hasMore) {
        html += `
            <div class="load-more-container" style="padding: 8px;">
                <button class="load-more-btn" style="width: 100%;" onclick="loadMoreAlarms()">
                    Daha Fazla (${groups.length - alarmsDisplayCount})
                </button>
            </div>
        `;
    }
    
    body.innerHTML = html;
}

function toggleAlarmDetail(alarmId) {
    if (openAlarmId === alarmId) {
        openAlarmId = null;
    } else {
        openAlarmId = alarmId;
    }
    renderAlarmsList(currentAlarmFilter);
    
    if (openAlarmId) {
        setTimeout(() => {
            const detailEl = document.getElementById('detail_' + alarmId);
            if (detailEl) {
                detailEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }
        }, 50);
    }
}

function formatMarketChip(market, selection) {
    let marketShort = market;
    if (market.toLowerCase().includes('1x2')) marketShort = '1X2';
    else if (market.toLowerCase().includes('ou') || market.toLowerCase().includes('2.5')) marketShort = 'O/U 2.5';
    else if (market.toLowerCase().includes('btts')) marketShort = 'BTTS';
    
    return `${marketShort} · ${selection}`;
}

function loadMoreAlarms() {
    alarmsDisplayCount += 30;
    renderAlarmsList(currentAlarmFilter);
    
    const container = document.getElementById('alarmsList');
    const cards = container.querySelectorAll('.alarm-card');
    if (cards.length > 0) {
        cards[cards.length - 30]?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
}

function formatTimeAgo(dateStr) {
    if (!dateStr) return '';
    const date = parseAlarmDate(dateStr);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);
    
    if (diffMins < 1) return 'Simdi';
    if (diffMins < 60) return `${diffMins}dk once`;
    if (diffHours < 24) return `${diffHours}sa once`;
    if (diffDays < 7) return `${diffDays}g once`;
    return dateStr.split(' ')[0];
}

function formatTimeAgoTR(dateStr) {
    if (!dateStr) return '';
    
    const alarmDT = parseAlarmDateTR(dateStr);
    if (!alarmDT || !alarmDT.isValid()) return '';
    
    // Gerçek tarih ve saat göster (örn: "04.12 14:35")
    return alarmDT.format('DD.MM HH:mm');
}

function parseAlarmDateTR(dateStr) {
    if (!dateStr) return null;
    
    // DD.MM.YYYY HH:MM formatı - zaten TR saati, keepLocalTime kullan
    if (dateStr.includes('.') && dateStr.includes(' ')) {
        const [datePart, timePart] = dateStr.split(' ');
        const dateParts = datePart.split('.');
        if (dateParts.length === 3) {
            const [day, month, year] = dateParts;
            const [hour, min] = (timePart || '00:00').split(':');
            const isoStr = `${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')}T${hour.padStart(2, '0')}:${min.padStart(2, '0')}:00`;
            return dayjs(isoStr).tz(APP_TIMEZONE, true);
        }
    }
    
    // ISO format offset'siz (2025-12-03T16:03:07) - scraper'dan geliyor ve ZATEN Turkey saati
    if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/.test(dateStr)) {
        return dayjs(dateStr).tz(APP_TIMEZONE, true);
    }
    
    return toTurkeyTime(dateStr);
}

function formatTriggerTime(dateStr) {
    if (!dateStr) return '-';
    
    // Eğer format DD.MM.YYYY HH:MM ise zaten Turkey saati - direkt göster
    if (dateStr.includes('.') && dateStr.includes(' ')) {
        const parts = dateStr.split(' ');
        if (parts.length >= 2 && parts[1].includes(':')) {
            return parts[1]; // Sadece saat kısmını döndür (HH:MM)
        }
    }
    
    // ISO format with timezone offset (2025-12-04T20:36:12.818075+03:00) - zaten Turkey saati
    if (dateStr.includes('+03:00') || dateStr.includes('+03')) {
        const dt = dayjs(dateStr).tz(APP_TIMEZONE);
        if (dt && dt.isValid()) {
            return dt.format('HH:mm');
        }
    }
    
    // ISO format offsetsiz (2025-12-03T16:03:07) - scraper'dan geliyor ve ZATEN Turkey saati
    // keepLocalTime=true ile UTC dönüşümü yapma
    if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/.test(dateStr)) {
        const dt = dayjs(dateStr).tz(APP_TIMEZONE, true);
        if (dt && dt.isValid()) {
            return dt.format('HH:mm');
        }
    }
    
    // Diğer formatlar için parseAlarmDateTR kullan
    const dt = parseAlarmDateTR(dateStr);
    if (!dt || !dt.isValid()) return '-';
    return dt.format('HH:mm');
}

function formatTriggerTimeShort(dateStr) {
    if (!dateStr) return '-';
    
    const str = String(dateStr).trim();
    
    // DD.MM.YYYY HH:MM formatı - zaten Turkey saati, keepLocalTime kullan
    const ddmmMatch = str.match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})\s*(\d{2}:\d{2})?$/);
    if (ddmmMatch) {
        const [, day, month, year, time] = ddmmMatch;
        const isoStr = `${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')}T${time || '00:00'}:00`;
        const dt = dayjs(isoStr).tz(APP_TIMEZONE, true);
        if (dt && dt.isValid()) {
            return dt.format('DD.MM HH:mm');
        }
    }
    
    // toTurkeyTime kullanarak tüm diğer formatları parse et
    const dt = toTurkeyTime(str);
    if (!dt || !dt.isValid()) return '-';
    
    // Gün ve saat formatı: "04.12 22:56"
    return dt.format('DD.MM HH:mm');
}

function goToMatchPage(matchKey, alarmType, alarmMarket) {
    // matchKey format: "Home_vs_Away"
    const parts = matchKey.split('_vs_');
    if (parts.length === 2) {
        const home = parts[0].replace(/_/g, ' ');
        const away = parts[1].replace(/_/g, ' ');
        goToMatchFromAlarm(home, away, alarmType, alarmMarket);
    }
}

function goToMatchFromAlarm(homeTeam, awayTeam, alarmType, alarmMarket) {
    openAlarmId = null;
    closeAlarmsSidebar();
    
    const homeLower = homeTeam.toLowerCase().trim();
    const awayLower = awayTeam.toLowerCase().trim();
    const marketLower = (alarmMarket || '').toLowerCase();
    
    let targetMarket = null;
    
    if (alarmType === 'dropping') {
        targetMarket = 'dropping_1x2';
        if (marketLower.includes('btts') || marketLower.includes('gg')) {
            targetMarket = 'dropping_btts';
        } else if (marketLower.includes('o/u') || marketLower.includes('over') || marketLower.includes('under') || marketLower.includes('ou25') || marketLower.includes('2.5')) {
            targetMarket = 'dropping_ou25';
        }
    } else if (alarmMarket) {
        if (marketLower.includes('dropping')) {
            if (marketLower.includes('btts') || marketLower.includes('gg')) {
                targetMarket = 'dropping_btts';
            } else if (marketLower.includes('ou') || marketLower.includes('2.5')) {
                targetMarket = 'dropping_ou25';
            } else {
                targetMarket = 'dropping_1x2';
            }
        } else if (marketLower.includes('moneyway') || marketLower.includes('mw')) {
            if (marketLower.includes('btts') || marketLower.includes('gg')) {
                targetMarket = 'moneyway_btts';
            } else if (marketLower.includes('ou') || marketLower.includes('2.5')) {
                targetMarket = 'moneyway_ou25';
            } else {
                targetMarket = 'moneyway_1x2';
            }
        }
    }
    
    if (targetMarket) {
        switchMarketAndFindMatch(targetMarket, homeLower, awayLower, homeTeam, awayTeam);
        return;
    }
    
    const dataSource = filteredMatches.length > 0 ? filteredMatches : matches;
    let foundIndex = -1;
    
    for (let i = 0; i < dataSource.length; i++) {
        const m = dataSource[i];
        const mHome = (m.home_team || m.Home || '').toLowerCase().trim();
        const mAway = (m.away_team || m.Away || '').toLowerCase().trim();
        
        if ((mHome.includes(homeLower) || homeLower.includes(mHome)) &&
            (mAway.includes(awayLower) || awayLower.includes(mAway))) {
            foundIndex = i;
            break;
        }
    }
    
    if (foundIndex >= 0) {
        openMatchModal(foundIndex);
    } else {
        tryFindMatchInAllMarkets(homeLower, awayLower, homeTeam, awayTeam);
    }
}

async function tryFindMatchInAllMarkets(homeLower, awayLower, homeTeam, awayTeam) {
    const marketsToTry = ['moneyway_1x2', 'moneyway_ou25', 'moneyway_btts', 'dropping_1x2', 'dropping_ou25', 'dropping_btts'];
    
    for (const market of marketsToTry) {
        const marketTab = document.querySelector(`[data-market="${market}"]`);
        if (marketTab) {
            marketTab.click();
            await new Promise(resolve => setTimeout(resolve, 1200));
            
            const dataSource = filteredMatches.length > 0 ? filteredMatches : matches;
            for (let i = 0; i < dataSource.length; i++) {
                const m = dataSource[i];
                const mHome = (m.home_team || m.Home || '').toLowerCase().trim();
                const mAway = (m.away_team || m.Away || '').toLowerCase().trim();
                
                if ((mHome.includes(homeLower) || homeLower.includes(mHome)) &&
                    (mAway.includes(awayLower) || awayLower.includes(mAway))) {
                    openMatchModal(i);
                    return;
                }
            }
        }
    }
    
    console.log('Mac bulunamadi:', homeTeam, 'vs', awayTeam);
    showToast(`Maç tüm marketlerde bulunamadı. Alarm detayları kartta mevcut.`, 'info');
}

async function switchMarketAndFindMatch(targetMarket, homeLower, awayLower, homeTeam, awayTeam) {
    const marketTab = document.querySelector(`[data-market="${targetMarket}"]`);
    if (marketTab) {
        marketTab.click();
    }
    
    await new Promise(resolve => setTimeout(resolve, 1500));
    
    const dataSource = filteredMatches.length > 0 ? filteredMatches : matches;
    let foundIndex = -1;
    
    for (let i = 0; i < dataSource.length; i++) {
        const m = dataSource[i];
        const mHome = (m.home_team || m.Home || '').toLowerCase().trim();
        const mAway = (m.away_team || m.Away || '').toLowerCase().trim();
        
        if ((mHome.includes(homeLower) || homeLower.includes(mHome)) &&
            (mAway.includes(awayLower) || awayLower.includes(mAway))) {
            foundIndex = i;
            break;
        }
    }
    
    if (foundIndex >= 0) {
        openMatchModal(foundIndex);
    } else {
        const tbody = document.getElementById('matchesTableBody');
        if (tbody) {
            const rows = tbody.querySelectorAll('tr[onclick*="openMatchModal"]');
            for (let row of rows) {
                const text = row.textContent.toLowerCase();
                if (text.includes(homeLower) && text.includes(awayLower)) {
                    const onclickAttr = row.getAttribute('onclick');
                    const indexMatch = onclickAttr?.match(/openMatchModal\((\d+)\)/);
                    if (indexMatch) {
                        openMatchModal(parseInt(indexMatch[1]));
                        return;
                    }
                }
            }
        }
        
        const marketLabels = {
            'dropping_1x2': 'Drop 1X2',
            'dropping_ou25': 'Drop 2.5',
            'dropping_btts': 'Drop BTTS'
        };
        showToast(`Maç henüz veritabanında yok. Alarm detayları kartta mevcut.`, 'info');
    }
}

// ============================================
// SMART MONEY EVENTS - Match Detail Modal
// ============================================

let cachedAllAlarms = null;
let smartMoneySectionOpen = true;

async function loadAllAlarmsOnce() {
    if (cachedAllAlarms) return cachedAllAlarms;
    
    try {
        const [sharpRes, insiderRes, bigMoneyRes, volumeShockRes, droppingRes, publicmoveRes, volumeLeaderRes] = await Promise.all([
            fetch('/api/sharp/alarms').catch(() => ({ ok: false })),
            fetch('/api/insider/alarms').catch(() => ({ ok: false })),
            fetch('/api/bigmoney/alarms').catch(() => ({ ok: false })),
            fetch('/api/volumeshock/alarms').catch(() => ({ ok: false })),
            fetch('/api/dropping/alarms').catch(() => ({ ok: false })),
            fetch('/api/publicmove/alarms').catch(() => ({ ok: false })),
            fetch('/api/volumeleader/alarms').catch(() => ({ ok: false }))
        ]);
        
        let allAlarms = [];
        
        if (sharpRes.ok) {
            const sharp = await sharpRes.json();
            sharp.forEach(a => { a._type = 'sharp'; });
            allAlarms = allAlarms.concat(sharp);
        }
        
        if (insiderRes.ok) {
            const insider = await insiderRes.json();
            insider.forEach(a => { a._type = 'insider'; });
            allAlarms = allAlarms.concat(insider);
        }
        
        if (bigMoneyRes.ok) {
            const bigmoney = await bigMoneyRes.json();
            bigmoney.forEach(a => { a._type = 'bigmoney'; });
            allAlarms = allAlarms.concat(bigmoney);
        }
        
        if (volumeShockRes.ok) {
            const volumeshock = await volumeShockRes.json();
            volumeshock.forEach(a => { a._type = 'volumeshock'; });
            allAlarms = allAlarms.concat(volumeshock);
        }
        
        if (droppingRes.ok) {
            const dropping = await droppingRes.json();
            dropping.forEach(a => { a._type = 'dropping'; });
            allAlarms = allAlarms.concat(dropping);
        }
        
        if (publicmoveRes.ok) {
            const publicmove = await publicmoveRes.json();
            publicmove.forEach(a => { a._type = 'publicmove'; });
            allAlarms = allAlarms.concat(publicmove);
        }
        
        if (volumeLeaderRes.ok) {
            const volumeleader = await volumeLeaderRes.json();
            volumeleader.forEach(a => { a._type = 'volumeleader'; });
            allAlarms = allAlarms.concat(volumeleader);
        }
        
        cachedAllAlarms = allAlarms;
        return allAlarms;
    } catch (e) {
        console.error('[SmartMoney] Load error:', e);
        return [];
    }
}

function getMatchAlarms(homeTeam, awayTeam) {
    if (!cachedAllAlarms) return [];
    
    const homeLower = homeTeam.toLowerCase().trim();
    const awayLower = awayTeam.toLowerCase().trim();
    
    return cachedAllAlarms.filter(a => {
        const aHome = (a.home || a.home_team || '').toLowerCase().trim();
        const aAway = (a.away || a.away_team || '').toLowerCase().trim();
        
        return (aHome.includes(homeLower) || homeLower.includes(aHome)) &&
               (aAway.includes(awayLower) || awayLower.includes(aAway));
    });
}

function formatSmartMoneyTime(dateStr) {
    if (!dateStr) return '-';
    
    const monthNames = ['Oca', 'Sub', 'Mar', 'Nis', 'May', 'Haz', 'Tem', 'Agu', 'Eyl', 'Eki', 'Kas', 'Ara'];
    
    // Direct parse for DD.MM.YYYY HH:MM format - +3 saat ekle
    const match1 = dateStr.match(/^(\d{2})\.(\d{2})\.(\d{4})\s+(\d{2}):(\d{2})$/);
    if (match1) {
        const [, day, month, year, hour, min] = match1;
        const dt = new Date(parseInt(year), parseInt(month) - 1, parseInt(day), parseInt(hour), parseInt(min));
        dt.setHours(dt.getHours() + 3); // +3 saat Türkiye
        const monthName = monthNames[dt.getMonth()];
        const h = String(dt.getHours()).padStart(2, '0');
        const m = String(dt.getMinutes()).padStart(2, '0');
        const d = String(dt.getDate()).padStart(2, '0');
        return `${d} ${monthName} • ${h}:${m}`;
    }
    
    // ISO format: 2025-12-01T18:31:21 - +3 saat ekle
    const match2 = dateStr.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
    if (match2) {
        const [, year, month, day, hour, min] = match2;
        const dt = new Date(parseInt(year), parseInt(month) - 1, parseInt(day), parseInt(hour), parseInt(min));
        dt.setHours(dt.getHours() + 3); // +3 saat Türkiye
        const monthName = monthNames[dt.getMonth()];
        const h = String(dt.getHours()).padStart(2, '0');
        const m = String(dt.getMinutes()).padStart(2, '0');
        const d = String(dt.getDate()).padStart(2, '0');
        return `${d} ${monthName} • ${h}:${m}`;
    }
    
    const dt = parseAlarmDateTR(dateStr);
    if (!dt || !dt.isValid()) return '-';
    return dt.format('DD MMM • HH:mm');
}

async function renderMatchAlarmsSection(homeTeam, awayTeam) {
    const section = document.getElementById('smartMoneySection');
    const grid = document.getElementById('smartMoneyGrid');
    const empty = document.getElementById('smartMoneyEmpty');
    const chevron = document.getElementById('smartMoneyChevron');
    
    if (!section) return;
    
    await loadAllAlarmsOnce();
    const matchAlarms = getMatchAlarms(homeTeam, awayTeam);
    
    smartMoneySectionOpen = true;
    chevron.textContent = '▼';
    grid.style.display = 'grid';
    
    if (matchAlarms.length === 0) {
        grid.style.display = 'none';
        empty.style.display = 'block';
        return;
    }
    
    empty.style.display = 'none';
    
    const grouped = { sharp: [], insider: [], bigmoney: [], volumeshock: [], dropping: [], publicmove: [], volumeleader: [] };
    matchAlarms.forEach(a => {
        if (a._type && grouped[a._type]) {
            grouped[a._type].push(a);
        }
    });
    
    Object.keys(grouped).forEach(type => {
        grouped[type].sort((a, b) => {
            const getTime = (alarm) => {
                const dt = parseAlarmDateTR(alarm.created_at || alarm.triggered_at);
                return dt && dt.isValid() ? dt.valueOf() : 0;
            };
            return getTime(b) - getTime(a);
        });
    });
    
    const cardConfigs = {
        sharp: {
            title: 'Sharp',
            color: '#22C55E',
            icon: '⚡',
            description: 'Profesyonel yatirimci girisi.'
        },
        bigmoney: {
            title: 'Big Money',
            color: '#f97316',
            icon: '💰',
            description: 'Yuksek hacimli para girisi.'
        },
        insider: {
            title: 'Insider',
            color: '#A855F7',
            icon: '🕵',
            description: 'Dusuk hacim, yuksek oran dususu.'
        },
        volumeshock: {
            title: 'Hacim Soku',
            color: '#ff6b6b',
            icon: '⚡',
            description: 'Mactan once erken hacim artisi.'
        },
        dropping: {
            title: 'Dropping',
            color: '#f85149',
            icon: '📉',
            description: 'Acilisindan bu yana oran dususu.'
        },
        publicmove: {
            title: 'Public Move',
            color: '#FFCC00',
            icon: '🪤',
            description: 'Halk tuzagi tespit edildi.'
        },
        volumeleader: {
            title: 'Lider Degisti',
            color: '#06b6d4',
            icon: '👑',
            description: 'Hacim lideri degisti.'
        }
    };
    
    let cardsHtml = '';
    
    Object.keys(cardConfigs).forEach(type => {
        const alarms = grouped[type];
        if (alarms.length === 0) return;
        
        const config = cardConfigs[type];
        const latest = alarms[0];
        const count = alarms.length;
        
        const markets = [...new Set(alarms.map(a => a.selection || a.side || a.market || '-'))];
        const marketText = markets.slice(0, 3).join(', ');
        
        const lastTime = formatSmartMoneyTime(latest.trigger_at || latest.event_time || latest.created_at || latest.triggered_at);
        
        let row2Left = '';
        let row2Right = '';
        let row3Left = '';
        let row3Right = '';
        let row4 = '';
        
        if (type === 'sharp') {
            const score = latest.sharp_score || 0;
            const incomingMoney = latest.incoming_money || latest.amount_change || latest.volume || 0;
            const dropPct = latest.drop_pct || latest.odds_drop_pct || 0;
            const prevShare = latest.previous_share || 0;
            const currShare = latest.current_share || 0;
            const selection = latest.selection || latest.side || '-';
            const market = latest.market || '';
            const selTotal = latest.selection_total || latest.volume || 0;
            row2Left = `${selection} (${market})`;
            row2Right = `Sharp: ${score.toFixed(0)} | ▼${dropPct.toFixed(1)}%`;
            row3Left = `<span class="sm-money-hero">£${Number(incomingMoney).toLocaleString('en-GB')}</span> <span class="sm-money-label">yeni para</span>`;
            row3Right = selTotal > 0 ? `<span class="sm-total-muted">Sonrası: £${Number(selTotal).toLocaleString('en-GB')}</span>` : '';
            row4 = `Bu seçenekte 10 dk içinde yüksek hacimli para + oran düşüşü tespit edildi.`;
        } else if (type === 'bigmoney') {
            const money = latest.incoming_money || latest.stake || 0;
            const selection = latest.selection || latest.side || '-';
            const market = latest.market || '';
            const selectionTotal = latest.selection_total || latest.volume || latest.total_volume || 0;
            
            // BigMoney için özel kart yapısı
            const marketFormatted = market === '1X2' ? '1-X-2' : (market === 'OU25' ? 'O/U 2.5' : market);
            row2Left = `${selection} (${marketFormatted})`;
            row2Right = '';
            row3Left = `<span class="sm-money-hero">£${Number(money).toLocaleString('en-GB')}</span> <span class="sm-money-label">gelen para</span>`;
            row3Right = selectionTotal > 0 ? `<span class="sm-total-muted">Olay sonrası: £${Number(selectionTotal).toLocaleString('en-GB')}</span>` : '';
            row4 = `Seçeneğe 10 dakika içinde büyük para girişi tespit edildi.`;
        } else if (type === 'insider') {
            const dropPct = Math.abs(latest.oran_dusus_pct || latest.odds_drop_pct || 0);
            const openOdds = (latest.opening_odds || 0).toFixed(2);
            const lastOdds = (latest.last_odds || 0).toFixed(2);
            const selection = latest.selection || latest.side || '-';
            const market = latest.market || '';
            const gelenPara = latest.gelen_para || latest.incoming_money || 0;
            const hoursToKickoff = calculateHoursToKickoff(latest);
            const selTotal = latest.selection_total || latest.volume || 0;
            row2Left = `${selection} (${market})`;
            row2Right = `${openOdds} → ${lastOdds} <span class="sm-drop-badge">▼${dropPct.toFixed(1)}%</span>`;
            row3Left = `<span class="sm-money-hero">£${Number(gelenPara).toLocaleString('en-GB')}</span> <span class="sm-money-label">gelen para</span>`;
            row3Right = selTotal > 0 ? `<span class="sm-total-muted">Sonrası: £${Number(selTotal).toLocaleString('en-GB')}</span>` : '';
            row4 = `Favori seçenek için maç öncesi senkron para + oran düşüşü tespit edildi.`;
        } else if (type === 'volumeshock') {
            const shockValue = latest.volume_shock_value || latest.volume_shock || latest.volume_shock_multiplier || 0;
            const incomingMoney = latest.incoming_money || 0;
            const avgLast10 = latest.avg_last_amounts || latest.average_amount || 0;
            const selection = latest.selection || latest.side || '-';
            const market = latest.market || '';
            const selTotal = latest.selection_total || latest.volume || 0;
            row2Left = `${selection} (${market})`;
            row2Right = `<span class="sm-shock-badge">X${shockValue.toFixed(0)}</span> hacim şoku`;
            row3Left = `<span class="sm-money-hero">£${Number(incomingMoney).toLocaleString('en-GB')}</span> <span class="sm-money-label">yeni para</span>`;
            row3Right = selTotal > 0 ? `<span class="sm-total-muted">Sonrası: £${Number(selTotal).toLocaleString('en-GB')}</span>` : '';
            row4 = `Son 10 giriş ortalamasına göre X${shockValue.toFixed(0)} kat yüksek para akışı tespit edildi.`;
        } else if (type === 'dropping') {
            const openOdds = (latest.opening_odds || 0).toFixed(2);
            const currOdds = (latest.current_odds || 0).toFixed(2);
            const dropPct = latest.drop_pct || 0;
            const level = latest.level || 'L1';
            const selection = latest.selection || latest.side || '-';
            const market = latest.market || '';
            const volume = latest.volume || latest.selection_total || 0;
            const levelTooltip = level === 'L1' ? 'Orta seviye düşüş (8-13%)' : (level === 'L2' ? 'Güçlü düşüş (13-20%)' : 'Çok güçlü düşüş (20%+)');
            row2Left = `${selection} (${market})`;
            row2Right = `<span class="sm-dropping-main">${openOdds} → ${currOdds}</span> <span class="sm-drop-pct-hero">▼${dropPct.toFixed(1)}%</span> <span class="sm-level-badge ${level.toLowerCase()}" title="${levelTooltip}">${level}</span>`;
            row3Left = volume > 0 ? `<span class="sm-volume-highlight">Volume: £${Number(volume).toLocaleString('en-GB')}</span>` : '';
            row3Right = `<span class="sm-drop-support">10 dk içi hacim ile doğrulandı</span>`;
            row4 = `Seçenek oranında kısa sürede güçlü bir düşüş tespit edildi.`;
        } else if (type === 'publicmove') {
            const prevShare = latest.previous_share || latest.old_share || 0;
            const currShare = latest.current_share || latest.new_share || 0;
            const publicPara = latest.incoming_money || latest.public_money || latest.volume || 0;
            const selection = latest.selection || latest.side || '-';
            const market = latest.market || '';
            row2Left = `${selection} (${market})`;
            row2Right = `Public: %${prevShare.toFixed(0)} → %${currShare.toFixed(0)}`;
            row3Left = publicPara > 0 ? `<span class="sm-money-hero">£${Number(publicPara).toLocaleString('en-GB')}</span> <span class="sm-money-label">public para</span>` : '';
            row3Right = '';
            row4 = `Public para akışı kısa sürede bu seçenekte yoğunlaştı.`;
        } else if (type === 'volumeleader') {
            const oldLeader = latest.old_leader || latest.previous_leader || '-';
            const newLeader = latest.new_leader || latest.selection || '-';
            const oldVol = latest.old_leader_volume || 0;
            const newVol = latest.new_leader_volume || latest.selection_total || 0;
            const market = latest.market || '';
            row2Left = `${market}`;
            row2Right = `${oldLeader} → <span class="sm-leader-new">${newLeader}</span>`;
            row3Left = `<span class="sm-total-muted">£${Number(oldVol).toLocaleString('en-GB')} → £${Number(newVol).toLocaleString('en-GB')}</span>`;
            row3Right = '';
            row4 = `Market lideri değişti. Bu seçenekte hacim üstünlüğü ele geçirildi.`;
        }
        
        // Tüm alarm tipleri için portal tooltip oluştur
        let countBadgeHtml = '';
        if (count > 1) {
            const tooltipId = `${type}-tooltip-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
            
            // Alarm tipine göre tooltip item formatı
            const tooltipItems = alarms.slice(0, 10).map(a => {
                const t = formatSmartMoneyTime(a.trigger_at || a.event_time || a.created_at);
                const timeOnly = t.includes('•') ? t.split('•')[1].trim() : t;
                
                if (type === 'bigmoney') {
                    const money = Number(a.incoming_money || a.stake || 0).toLocaleString('en-GB');
                    const sel = a.selection || a.side || '-';
                    const total = Number(a.selection_total || a.volume || a.total_volume || 0).toLocaleString('en-GB');
                    return `<div class="smc-tooltip-item">• ${timeOnly} — <span class="tt-money">£${money}</span> gelen para — ${sel} — <span class="tt-total">Olay sonrası: £${total}</span></div>`;
                } else if (type === 'sharp') {
                    const money = Number(a.incoming_money || a.amount_change || a.volume || 0).toLocaleString('en-GB');
                    const prevOdds = (a.previous_odds || 0).toFixed(2);
                    const currOdds = (a.current_odds || 0).toFixed(2);
                    const prevShare = (a.previous_share || 0).toFixed(0);
                    const currShare = (a.current_share || 0).toFixed(0);
                    const total = Number(a.selection_total || a.volume || 0).toLocaleString('en-GB');
                    return `<div class="smc-tooltip-item">• ${timeOnly} — <span class="tt-money">£${money}</span> para — Oran: ${prevOdds} → ${currOdds} — Pay: %${prevShare} → %${currShare} — <span class="tt-total">Sonrası: £${total}</span></div>`;
                } else if (type === 'volumeshock') {
                    const money = Number(a.incoming_money || 0).toLocaleString('en-GB');
                    const shock = (a.volume_shock_value || a.volume_shock || 0).toFixed(1);
                    const avg = Number(a.avg_last_amounts || a.average_amount || 0).toLocaleString('en-GB');
                    const total = Number(a.selection_total || a.volume || 0).toLocaleString('en-GB');
                    return `<div class="smc-tooltip-item">• ${timeOnly} — <span class="tt-money">£${money}</span> → şok <span class="tt-shock">X${shock}</span> — Son 10 ort: £${avg} — <span class="tt-total">Sonrası: £${total}</span></div>`;
                } else if (type === 'dropping') {
                    const openOdds = (a.opening_odds || 0).toFixed(2);
                    const currOdds = (a.current_odds || 0).toFixed(2);
                    const dropPct = (a.drop_pct || 0).toFixed(1);
                    const vol = Number(a.volume || a.selection_total || 0).toLocaleString('en-GB');
                    return `<div class="smc-tooltip-item">• ${timeOnly} — Oran: ${openOdds} → ${currOdds} (<span class="tt-drop">%${dropPct}</span>) — <span class="tt-total">Volume: £${vol}</span></div>`;
                } else if (type === 'publicmove') {
                    const prevShare = (a.previous_share || a.old_share || 0).toFixed(0);
                    const currShare = (a.current_share || a.new_share || 0).toFixed(0);
                    const publicPara = Number(a.incoming_money || a.public_money || a.volume || 0).toLocaleString('en-GB');
                    return `<div class="smc-tooltip-item">• ${timeOnly} — Public: <span class="tt-share">%${prevShare} → %${currShare}</span> — Yeni public para: <span class="tt-money">£${publicPara}</span></div>`;
                } else if (type === 'volumeleader') {
                    const oldL = a.old_leader || a.previous_leader || '-';
                    const newL = a.new_leader || a.selection || '-';
                    const oldVol = Number(a.old_leader_volume || 0).toLocaleString('en-GB');
                    const newVol = Number(a.new_leader_volume || a.selection_total || 0).toLocaleString('en-GB');
                    return `<div class="smc-tooltip-item">• ${timeOnly} — Lider değişimi: ${oldL} → <span class="tt-leader">${newL}</span> — Fark: £${oldVol} → £${newVol}</div>`;
                } else if (type === 'insider') {
                    const money = Number(a.gelen_para || a.incoming_money || 0).toLocaleString('en-GB');
                    const openOdds = (a.opening_odds || 0).toFixed(2);
                    const lastOdds = (a.last_odds || 0).toFixed(2);
                    const hours = calculateHoursToKickoff(a).toFixed(0);
                    const total = Number(a.selection_total || a.volume || 0).toLocaleString('en-GB');
                    return `<div class="smc-tooltip-item">• ${timeOnly} — <span class="tt-money">£${money}</span> — Oran: ${openOdds} → ${lastOdds} — Maça kalan: ${hours} saat — <span class="tt-total">Sonrası: £${total}</span></div>`;
                }
                return `<div class="smc-tooltip-item">• ${timeOnly}</div>`;
            }).join('');
            
            countBadgeHtml = `<span class="smc-count-badge smc-count-${type}" data-tooltip-id="${tooltipId}" onclick="event.stopPropagation();">x${count}</span>`;
            
            // Tooltip'i body'ye ekle (portal)
            setTimeout(() => {
                let tooltipEl = document.getElementById(tooltipId);
                if (!tooltipEl) {
                    tooltipEl = document.createElement('div');
                    tooltipEl.id = tooltipId;
                    tooltipEl.className = 'smc-tooltip-portal';
                    tooltipEl.innerHTML = `<div class="smc-tooltip-header">Geçmiş Alarmlar</div>${tooltipItems}`;
                    document.body.appendChild(tooltipEl);
                }
                
                const badge = document.querySelector(`[data-tooltip-id="${tooltipId}"]`);
                if (badge) {
                    badge.addEventListener('mouseenter', () => {
                        const rect = badge.getBoundingClientRect();
                        tooltipEl.style.display = 'block';
                        tooltipEl.style.top = (rect.bottom + window.scrollY + 8) + 'px';
                        
                        const tooltipWidth = tooltipEl.offsetWidth;
                        const viewportWidth = window.innerWidth;
                        let leftPos = rect.left + window.scrollX;
                        
                        if (leftPos + tooltipWidth > viewportWidth - 10) {
                            leftPos = viewportWidth - tooltipWidth - 10;
                        }
                        if (leftPos < 10) {
                            leftPos = 10;
                        }
                        
                        tooltipEl.style.left = leftPos + 'px';
                    });
                    badge.addEventListener('mouseleave', () => {
                        tooltipEl.style.display = 'none';
                    });
                }
            }, 100);
        }
        
        cardsHtml += `
            <div class="smc-card ${type}">
                <div class="smc-stripe" style="background: ${config.color};"></div>
                <div class="smc-content">
                    <div class="smc-row smc-header">
                        <div class="smc-left">
                            <span class="smc-dot" style="background: ${config.color};"></span>
                            <span class="smc-badge">${config.title.toUpperCase()}</span>
                            ${countBadgeHtml}
                        </div>
                        <span class="smc-time">${lastTime}</span>
                    </div>
                    <div class="smc-row">
                        <span class="smc-label">${row2Left}</span>
                        <span class="smc-value" style="color: ${config.color};">${row2Right}</span>
                    </div>
                    <div class="smc-row">
                        <span class="smc-detail">${row3Left}</span>
                        <span class="smc-detail">${row3Right}</span>
                    </div>
                    <div class="smc-row smc-desc">${row4}</div>
                </div>
            </div>
        `;
    });
    
    grid.innerHTML = cardsHtml;
}

function toggleSmartMoneySection() {
    const grid = document.getElementById('smartMoneyGrid');
    const empty = document.getElementById('smartMoneyEmpty');
    const chevron = document.getElementById('smartMoneyChevron');
    
    smartMoneySectionOpen = !smartMoneySectionOpen;
    
    if (smartMoneySectionOpen) {
        chevron.textContent = '▼';
        const hasAlarms = grid.innerHTML.trim() !== '';
        if (hasAlarms) {
            grid.style.display = 'grid';
            empty.style.display = 'none';
        } else {
            grid.style.display = 'none';
            empty.style.display = 'block';
        }
    } else {
        chevron.textContent = '▲';
        grid.style.display = 'none';
        empty.style.display = 'none';
    }
}

// Update badge on page load
document.addEventListener('DOMContentLoaded', async () => {
    try {
        const [sharpRes, insiderRes, bigMoneyRes, volumeShockRes, droppingRes, publicmoveRes] = await Promise.all([
            fetch('/api/sharp/alarms').catch(() => ({ ok: false })),
            fetch('/api/insider/alarms').catch(() => ({ ok: false })),
            fetch('/api/bigmoney/alarms').catch(() => ({ ok: false })),
            fetch('/api/volumeshock/alarms').catch(() => ({ ok: false })),
            fetch('/api/dropping/alarms').catch(() => ({ ok: false })),
            fetch('/api/publicmove/alarms').catch(() => ({ ok: false }))
        ]);
        
        const sharpCount = sharpRes.ok ? (await sharpRes.json()).length : 0;
        const insiderCount = insiderRes.ok ? (await insiderRes.json()).length : 0;
        const bigMoneyCount = bigMoneyRes.ok ? (await bigMoneyRes.json()).length : 0;
        const volumeShockCount = volumeShockRes.ok ? (await volumeShockRes.json()).length : 0;
        const droppingCount = droppingRes.ok ? (await droppingRes.json()).length : 0;
        const publicmoveCount = publicmoveRes.ok ? (await publicmoveRes.json()).length : 0;
        
        const total = sharpCount + insiderCount + bigMoneyCount + volumeShockCount + droppingCount + publicmoveCount;
        const badge = document.getElementById('tabAlarmBadge');
        if (badge) badge.textContent = total;
    } catch (e) {
        console.log('Badge guncelleme hatasi:', e);
    }
    
    // Keyboard shortcut: Ctrl+Shift+A for Admin Panel (hidden feature)
    document.addEventListener('keydown', (e) => {
        if (e.ctrlKey && e.shiftKey && e.key === 'A') {
            e.preventDefault();
            openAdminPanel();
        }
    });
});

function openAdminPanel() {
    const overlay = document.getElementById('adminPanelOverlay');
    if (overlay) {
        overlay.classList.add('open');
        loadAdminInsiderData();
    }
}

function closeAdminPanel() {
    const overlay = document.getElementById('adminPanelOverlay');
    if (overlay) {
        overlay.classList.remove('open');
    }
}

async function loadAdminInsiderData() {
    const body = document.getElementById('adminPanelBody');
    if (!body) return;
    
    body.innerHTML = '<div style="text-align:center; padding:40px; color:#94a3b8;">Yükleniyor...</div>';
    
    try {
        const res = await fetch('/api/insider/alarms');
        if (!res.ok) throw new Error('API error');
        
        const alarms = await res.json();
        
        if (!alarms || alarms.length === 0) {
            body.innerHTML = '<div class="admin-no-data">Insider alarm bulunamadı.</div>';
            return;
        }
        
        // Sort by event_time descending
        alarms.sort((a, b) => {
            const ta = new Date(a.trigger_at || a.event_time || a.created_at).getTime();
            const tb = new Date(b.trigger_at || b.event_time || b.created_at).getTime();
            return tb - ta;
        });
        
        let tableHtml = `
            <table class="admin-table">
                <thead>
                    <tr>
                        <th>Maç</th>
                        <th>Market</th>
                        <th>Maç Saati</th>
                        <th>Oran Düşüşü</th>
                        <th>Gelen Para</th>
                        <th>Hacim Şok</th>
                        <th>Snapshot Sayısı</th>
                        <th>Alarm Zamanı</th>
                    </tr>
                </thead>
                <tbody>
        `;
        
        alarms.forEach(alarm => {
            const matchName = `${alarm.home || '-'} vs ${alarm.away || '-'}`;
            const market = `${alarm.market || '-'} → ${alarm.selection || '-'}`;
            
            // Match time (TR saati olarak formatla)
            const matchDate = formatMatchDateShort(alarm.match_date) || '-';
            
            // Odds drop percentage
            const oddsDrop = alarm.oran_dusus_pct || alarm.odds_drop_pct || 0;
            const oddsDropDisplay = oddsDrop > 0 ? `${oddsDrop.toFixed(1)}%` : '-';
            
            // Money in
            const moneyIn = alarm.gelen_para || alarm.stake || alarm.incoming_money || 0;
            const moneyDisplay = moneyIn > 0 ? `£${Number(moneyIn).toLocaleString('en-GB', {minimumFractionDigits: 0, maximumFractionDigits: 0})}` : '-';
            
            // Volume shock
            const volShock = alarm.hacim_sok || alarm.volume_shock || 0;
            const volShockDisplay = volShock > 0 ? `${volShock.toFixed(3)}x` : '-';
            
            // Snapshot count
            const snapCount = alarm.snapshot_count || '-';
            
            // Event time (alarm creation time based on snapshot)
            const eventTime = alarm.trigger_at || alarm.event_time || alarm.created_at;
            let eventTimeDisplay = '-';
            if (eventTime) {
                const dt = toTurkeyTime(eventTime);
                if (dt && dt.isValid()) {
                    eventTimeDisplay = dt.format('DD.MM.YYYY HH:mm:ss');
                }
            }
            
            tableHtml += `
                <tr>
                    <td class="match-col">${matchName}</td>
                    <td class="market-col"><span class="admin-badge insider">🕵️ ${market}</span></td>
                    <td>${matchDate}</td>
                    <td class="admin-value-negative">${oddsDropDisplay}</td>
                    <td class="admin-value-positive">${moneyDisplay}</td>
                    <td class="admin-value-warning">${volShockDisplay}</td>
                    <td style="text-align:center;">${snapCount}</td>
                    <td class="admin-value-muted">${eventTimeDisplay}</td>
                </tr>
            `;
        });
        
        tableHtml += `
                </tbody>
            </table>
            <div style="margin-top:16px; padding:12px; background:#161b22; border-radius:8px; font-size:12px; color:#64748b;">
                <strong style="color:#a855f7;">📊 Özet:</strong> Toplam ${alarms.length} Insider alarm | 
                Eşik: Hacim Şok &lt; ${alarms[0]?.insider_hacim_sok_esigi ?? 'N/A'}x, 
                Oran Düşüş &gt; ${alarms[0]?.insider_oran_dusus_esigi ?? 'N/A'}%, 
                Max Para &lt; £${alarms[0]?.insider_max_para ?? 'N/A'}
            </div>
        `;
        
        body.innerHTML = tableHtml;
        
    } catch (e) {
        console.error('Admin panel veri yükleme hatası:', e);
        body.innerHTML = '<div class="admin-no-data">Veri yüklenirken hata oluştu.</div>';
    }
}

let currentAdminTab = 'insider';

function switchAdminTab(tab) {
    currentAdminTab = tab;
    
    document.querySelectorAll('.admin-tab').forEach(t => {
        t.classList.toggle('active', t.dataset.tab === tab);
    });
    
    if (tab === 'insider') {
        loadAdminInsiderData();
    } else if (tab === 'volumeleader') {
        loadAdminVolumeLeaderData();
    } else if (tab === 'dropping') {
        loadAdminDroppingData();
    }
}

async function loadAdminVolumeLeaderData() {
    const body = document.getElementById('adminPanelBody');
    if (!body) return;
    
    body.innerHTML = '<div style="text-align:center; padding:40px; color:#94a3b8;">Yükleniyor...</div>';
    
    try {
        const [configRes, alarmsRes, statusRes] = await Promise.all([
            fetch('/api/volumeleader/config'),
            fetch('/api/volumeleader/alarms'),
            fetch('/api/volumeleader/status')
        ]);
        
        const config = configRes.ok ? await configRes.json() : {};
        const alarms = alarmsRes.ok ? await alarmsRes.json() : [];
        const status = statusRes.ok ? await statusRes.json() : {};
        
        let html = `
            <div class="admin-section">
                <h3 style="color:#06b6d4; margin-bottom:16px;">⚡ Hacim Lideri Değişti - Ayarlar</h3>
                
                <div class="admin-config-form">
                    <div class="config-row">
                        <label>Lider Eşiği (%)</label>
                        <input type="number" id="vlLeaderThreshold" value="${config.leader_threshold || 50}" min="40" max="70" step="1">
                        <span class="config-hint">Minimum pay oranı (varsayılan: %50)</span>
                    </div>
                    
                    <div class="config-row">
                        <label>Min. Hacim 1X2 (£)</label>
                        <input type="number" id="vlMinVolume1x2" value="${config.min_volume_1x2 || 5000}" min="1000" step="500">
                    </div>
                    
                    <div class="config-row">
                        <label>Min. Hacim O/U (£)</label>
                        <input type="number" id="vlMinVolumeOu25" value="${config.min_volume_ou25 || 2000}" min="500" step="250">
                    </div>
                    
                    <div class="config-row">
                        <label>Min. Hacim BTTS (£)</label>
                        <input type="number" id="vlMinVolumeBtts" value="${config.min_volume_btts || 1000}" min="250" step="250">
                    </div>
                    
                    <div class="config-actions">
                        <button class="admin-btn primary" onclick="saveVolumeLeaderConfig()">💾 Ayarları Kaydet</button>
                        <button class="admin-btn success" onclick="calculateVolumeLeaderAlarms()" id="vlCalcBtn">🔍 Hesapla</button>
                        <button class="admin-btn danger" onclick="deleteVolumeLeaderAlarms()">🗑️ Alarmları Sil</button>
                    </div>
                    
                    <div id="vlCalcStatus" style="display:none; margin-top:12px; padding:8px; background:#0d1117; border-radius:4px; color:#8b949e; font-size:12px;"></div>
                </div>
            </div>
            
            <div class="admin-section" style="margin-top:24px;">
                <h3 style="color:#06b6d4; margin-bottom:16px;">📊 Alarmlar (${alarms.length})</h3>
        `;
        
        if (alarms.length === 0) {
            html += '<div class="admin-no-data">Henüz alarm yok. "Hesapla" butonuna tıklayın.</div>';
        } else {
            html += `
                <table class="admin-table">
                    <thead>
                        <tr>
                            <th>Maç</th>
                            <th>Market</th>
                            <th>Eski Lider</th>
                            <th>Yeni Lider</th>
                            <th>Toplam Hacim</th>
                            <th>Alarm Zamanı</th>
                        </tr>
                    </thead>
                    <tbody>
            `;
            
            alarms.slice(0, 50).forEach(alarm => {
                const matchName = `${alarm.home || '-'} vs ${alarm.away || '-'}`;
                const market = alarm.market || '-';
                const oldLeader = `${alarm.old_leader || '-'} (%${(alarm.old_leader_share || 0).toFixed(0)})`;
                const newLeader = `${alarm.new_leader || '-'} (%${(alarm.new_leader_share || 0).toFixed(0)})`;
                const totalVol = `£${Number(alarm.total_volume || 0).toLocaleString('en-GB')}`;
                const eventTime = alarm.trigger_at || alarm.event_time || '-';
                
                html += `
                    <tr>
                        <td class="match-col">${matchName}</td>
                        <td><span class="admin-badge volumeleader">${market}</span></td>
                        <td style="color:#f87171;">${oldLeader}</td>
                        <td style="color:#22d3ee;">${newLeader}</td>
                        <td>${totalVol}</td>
                        <td class="admin-value-muted">${eventTime}</td>
                    </tr>
                `;
            });
            
            html += '</tbody></table>';
        }
        
        html += '</div>';
        body.innerHTML = html;
        
    } catch (e) {
        console.error('Volume Leader admin veri hatası:', e);
        body.innerHTML = '<div class="admin-no-data">Veri yüklenirken hata oluştu.</div>';
    }
}

async function saveVolumeLeaderConfig() {
    const config = {
        leader_threshold: parseInt(document.getElementById('vlLeaderThreshold').value) || 50,
        min_volume_1x2: parseInt(document.getElementById('vlMinVolume1x2').value) || 5000,
        min_volume_ou25: parseInt(document.getElementById('vlMinVolumeOu25').value) || 2000,
        min_volume_btts: parseInt(document.getElementById('vlMinVolumeBtts').value) || 1000
    };
    
    try {
        const res = await fetch('/api/volumeleader/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });
        
        if (res.ok) {
            showToast('Ayarlar kaydedildi', 'success');
        } else {
            showToast('Kaydetme hatası', 'error');
        }
    } catch (e) {
        showToast('Bağlantı hatası', 'error');
    }
}

async function calculateVolumeLeaderAlarms() {
    const btn = document.getElementById('vlCalcBtn');
    const statusDiv = document.getElementById('vlCalcStatus');
    
    if (btn) btn.disabled = true;
    if (statusDiv) {
        statusDiv.style.display = 'block';
        statusDiv.textContent = 'Hesaplama başlatılıyor...';
    }
    
    try {
        const res = await fetch('/api/volumeleader/calculate', { method: 'POST' });
        const data = await res.json();
        
        if (data.success) {
            showToast(`${data.count} yeni alarm bulundu!`, 'success');
            loadAdminVolumeLeaderData();
        } else {
            showToast(data.error || 'Hesaplama hatası', 'error');
        }
    } catch (e) {
        showToast('Bağlantı hatası', 'error');
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function deleteVolumeLeaderAlarms() {
    if (!confirm('Tüm Hacim Lideri alarmlarını silmek istediğinize emin misiniz?')) return;
    
    try {
        const res = await fetch('/api/volumeleader/alarms', { method: 'DELETE' });
        if (res.ok) {
            showToast('Alarmlar silindi', 'success');
            loadAdminVolumeLeaderData();
        } else {
            showToast('Silme hatası', 'error');
        }
    } catch (e) {
        showToast('Bağlantı hatası', 'error');
    }
}

async function loadAdminDroppingData() {
    const body = document.getElementById('adminPanelBody');
    if (!body) return;
    
    body.innerHTML = '<div style="text-align:center; padding:40px; color:#94a3b8;">Yükleniyor...</div>';
    
    try {
        const [configRes, alarmsRes] = await Promise.all([
            fetch('/api/dropping/config'),
            fetch('/api/dropping/alarms')
        ]);
        
        const config = configRes.ok ? await configRes.json() : {};
        const alarms = alarmsRes.ok ? await alarmsRes.json() : [];
        
        let html = `
            <div class="admin-section">
                <h3 style="color:#f85149; margin-bottom:16px;">📉 Dropping Alarm - Max Oran Eşiği</h3>
                <p style="color:#8b949e; font-size:12px; margin-bottom:16px;">
                    Açılış oranı bu eşiklerin üzerindeyse dropping alarmı tetiklenmez.
                </p>
                
                <div class="admin-config-form">
                    <div class="config-row">
                        <label>Max Oran 1X2</label>
                        <input type="number" id="drMaxOdds1x2" value="${config.max_odds_1x2 || 5.0}" min="1.5" max="20" step="0.5">
                        <span class="config-hint">1X2 için max açılış oranı (varsayılan: 5.0)</span>
                    </div>
                    
                    <div class="config-row">
                        <label>Max Oran O/U 2.5</label>
                        <input type="number" id="drMaxOddsOu25" value="${config.max_odds_ou25 || 3.0}" min="1.5" max="10" step="0.25">
                        <span class="config-hint">Alt/Üst için max açılış oranı (varsayılan: 3.0)</span>
                    </div>
                    
                    <div class="config-row">
                        <label>Max Oran BTTS</label>
                        <input type="number" id="drMaxOddsBtts" value="${config.max_odds_btts || 3.0}" min="1.5" max="10" step="0.25">
                        <span class="config-hint">BTTS için max açılış oranı (varsayılan: 3.0)</span>
                    </div>
                    
                    <div style="border-top: 1px solid #30363d; margin-top: 16px; padding-top: 16px;">
                        <h4 style="color:#f85149; margin-bottom:12px; font-size:13px;">📊 Düşüş Yüzde Eşikleri</h4>
                        
                        <div class="config-row">
                            <label>L1 Min (%)</label>
                            <input type="number" id="drMinDropL1" value="${config.min_drop_l1 || 10}" min="5" max="30" step="1">
                        </div>
                        
                        <div class="config-row">
                            <label>L1 Max (%)</label>
                            <input type="number" id="drMaxDropL1" value="${config.max_drop_l1 || 17}" min="5" max="30" step="1">
                        </div>
                        
                        <div class="config-row">
                            <label>L2 Min (%)</label>
                            <input type="number" id="drMinDropL2" value="${config.min_drop_l2 || 17}" min="10" max="40" step="1">
                        </div>
                        
                        <div class="config-row">
                            <label>L2 Max (%)</label>
                            <input type="number" id="drMaxDropL2" value="${config.max_drop_l2 || 20}" min="10" max="40" step="1">
                        </div>
                        
                        <div class="config-row">
                            <label>L3 Min (%)</label>
                            <input type="number" id="drMinDropL3" value="${config.min_drop_l3 || 20}" min="15" max="50" step="1">
                            <span class="config-hint">L3 ve üzeri düşüşler</span>
                        </div>
                    </div>
                    
                    <div class="config-actions">
                        <button class="admin-btn primary" onclick="saveDroppingConfig()">💾 Ayarları Kaydet</button>
                        <button class="admin-btn success" onclick="calculateDroppingAlarms()" id="drCalcBtn">🔍 Hesapla</button>
                        <button class="admin-btn danger" onclick="deleteDroppingAlarms()">🗑️ Alarmları Sil</button>
                    </div>
                    
                    <div id="drCalcStatus" style="display:none; margin-top:12px; padding:8px; background:#0d1117; border-radius:4px; color:#8b949e; font-size:12px;"></div>
                </div>
            </div>
            
            <div class="admin-section" style="margin-top:24px;">
                <h3 style="color:#f85149; margin-bottom:16px;">📊 Alarmlar (${alarms.length})</h3>
        `;
        
        if (alarms.length === 0) {
            html += '<div class="admin-no-data">Henüz alarm yok.</div>';
        } else {
            html += `
                <table class="admin-table">
                    <thead>
                        <tr>
                            <th>Maç</th>
                            <th>Market</th>
                            <th>Seviye</th>
                            <th>Açılış → Güncel</th>
                            <th>Düşüş %</th>
                        </tr>
                    </thead>
                    <tbody>
            `;
            
            alarms.slice(0, 30).forEach(alarm => {
                const matchName = `${alarm.home || '-'} vs ${alarm.away || '-'}`;
                const market = `${alarm.market || '-'} → ${alarm.selection || '-'}`;
                const level = alarm.level || '-';
                const odds = `${alarm.opening_odds?.toFixed(2) || '-'} → ${alarm.current_odds?.toFixed(2) || '-'}`;
                const dropPct = `${alarm.drop_pct?.toFixed(1) || 0}%`;
                
                const levelColor = level === 'L3' ? '#f85149' : level === 'L2' ? '#ffa657' : '#ffc107';
                
                html += `
                    <tr>
                        <td class="match-col">${matchName}</td>
                        <td><span class="admin-badge dropping">${market}</span></td>
                        <td><span style="color:${levelColor}; font-weight:600;">${level}</span></td>
                        <td>${odds}</td>
                        <td class="admin-value-negative">${dropPct}</td>
                    </tr>
                `;
            });
            
            html += '</tbody></table>';
            if (alarms.length > 30) {
                html += `<div style="text-align:center; padding:12px; color:#6e7681; font-size:12px;">+${alarms.length - 30} daha fazla alarm...</div>`;
            }
        }
        
        html += '</div>';
        body.innerHTML = html;
        
    } catch (e) {
        console.error('Dropping admin veri hatası:', e);
        body.innerHTML = '<div class="admin-no-data">Veri yüklenirken hata oluştu.</div>';
    }
}

async function saveDroppingConfig() {
    const config = {
        max_odds_1x2: parseFloat(document.getElementById('drMaxOdds1x2').value) || 5.0,
        max_odds_ou25: parseFloat(document.getElementById('drMaxOddsOu25').value) || 3.0,
        max_odds_btts: parseFloat(document.getElementById('drMaxOddsBtts').value) || 3.0,
        min_drop_l1: parseInt(document.getElementById('drMinDropL1').value) || 10,
        max_drop_l1: parseInt(document.getElementById('drMaxDropL1').value) || 17,
        min_drop_l2: parseInt(document.getElementById('drMinDropL2').value) || 17,
        max_drop_l2: parseInt(document.getElementById('drMaxDropL2').value) || 20,
        min_drop_l3: parseInt(document.getElementById('drMinDropL3').value) || 20
    };
    
    try {
        const res = await fetch('/api/dropping/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });
        
        if (res.ok) {
            showToast('Dropping ayarları kaydedildi', 'success');
        } else {
            showToast('Kaydetme hatası', 'error');
        }
    } catch (e) {
        showToast('Bağlantı hatası', 'error');
    }
}

async function calculateDroppingAlarms() {
    const btn = document.getElementById('drCalcBtn');
    const statusDiv = document.getElementById('drCalcStatus');
    
    if (btn) btn.disabled = true;
    if (statusDiv) {
        statusDiv.style.display = 'block';
        statusDiv.textContent = 'Dropping alarmları hesaplanıyor...';
    }
    
    try {
        const res = await fetch('/api/dropping/calculate', { method: 'POST' });
        const data = await res.json();
        
        if (data.success) {
            showToast(`${data.count} dropping alarm bulundu!`, 'success');
            loadAdminDroppingData();
        } else {
            showToast(data.error || 'Hesaplama hatası', 'error');
        }
    } catch (e) {
        showToast('Bağlantı hatası', 'error');
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function deleteDroppingAlarms() {
    if (!confirm('Tüm Dropping alarmlarını silmek istediğinize emin misiniz?')) return;
    
    try {
        const res = await fetch('/api/dropping/alarms', { method: 'DELETE' });
        if (res.ok) {
            showToast('Dropping alarmları silindi', 'success');
            loadAdminDroppingData();
        } else {
            showToast('Silme hatası', 'error');
        }
    } catch (e) {
        showToast('Bağlantı hatası', 'error');
    }
}
