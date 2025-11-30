/**
 * SmartXFlow Alarm Renderer
 * ==========================
 * 
 * Frontend tarafında alarm listesini render eden modül.
 * 
 * Kurallar:
 * - Alarm Listesi: Sadece is_alarm === true olanlar görünür
 * - Maç Detayı Log: Sadece is_alarm === false olanlar görünür
 * - Kategoriye göre renk: sharp=yeşil, dropping=turuncu, reversal=kırmızı
 */

const AlarmConfig = {
    categories: {
        sharp: {
            color: '#22c55e',
            bgColor: 'rgba(34, 197, 94, 0.1)',
            icon: '🟢',
            name: 'Sharp'
        },
        dropping: {
            color: '#f97316',
            bgColor: 'rgba(249, 115, 22, 0.1)',
            icon: '📉',
            name: 'Dropping'
        },
        reversal: {
            color: '#ef4444',
            bgColor: 'rgba(239, 68, 68, 0.1)',
            icon: '🔄',
            name: 'Reversal Move'
        }
    },
    severityColors: {
        1: '#fbbf24',
        2: '#f97316',
        3: '#ef4444'
    }
};

/**
 * Örnek alarm array'i (Backend'den gelir)
 */
const exampleAlarms = [
    {
        id: "uuid-1",
        match_id: "Liverpool|Arsenal|EPL|29.11.2025",
        market: "moneyway_1x2",
        side: "1",
        category: "sharp",
        is_alarm: true,
        is_preview: false,
        severity: 3,
        score: 86,
        conditions_met: 0,
        message: "Sharp 86/100",
        created_at: "2025-11-29T04:45:00Z",
        extra: { criteria_count: 4 }
    },
    {
        id: "uuid-2",
        match_id: "Chelsea|Tottenham|EPL|29.11.2025",
        market: "moneyway_1x2",
        side: "X",
        category: "sharp",
        is_alarm: false,
        is_preview: true,
        severity: 1,
        score: 55,
        conditions_met: 0,
        message: "Sharp Skor: 55/100 (orta seviye)",
        created_at: "2025-11-29T04:40:00Z",
        extra: {}
    },
    {
        id: "uuid-3",
        match_id: "Barcelona|RealMadrid|LaLiga|29.11.2025",
        market: "moneyway_1x2",
        side: "1",
        category: "dropping",
        is_alarm: true,
        is_preview: false,
        severity: 2,
        score: 12.5,
        conditions_met: 0,
        message: "Dropping L2 – 12.5% (30dk+ kalıcı)",
        created_at: "2025-11-29T04:30:00Z",
        extra: { level: 2, drop_pct: 12.5 }
    },
    {
        id: "uuid-4",
        match_id: "Juventus|Milan|SerieA|29.11.2025",
        market: "moneyway_1x2",
        side: "2",
        category: "dropping",
        is_alarm: false,
        is_preview: true,
        severity: 1,
        score: 8.2,
        conditions_met: 0,
        message: "Dropping L1 – 8.2% (15/30dk, preview)",
        created_at: "2025-11-29T04:35:00Z",
        extra: { level: 1, drop_pct: 8.2, minutes_persisted: 15 }
    },
    {
        id: "uuid-5",
        match_id: "Dortmund|Bayern|Bundesliga|29.11.2025",
        market: "moneyway_1x2",
        side: "2",
        category: "reversal",
        is_alarm: true,
        is_preview: false,
        severity: 3,
        score: 0,
        conditions_met: 3,
        message: "Trend tersine döndü — 3/3 kriter (Reversal Move)",
        created_at: "2025-11-29T04:25:00Z",
        extra: { criteria_text: "Retracement: 75% | Momentum: Değişti | Volume Switch: Evet" }
    },
    {
        id: "uuid-6",
        match_id: "Ajax|PSV|Eredivisie|29.11.2025",
        market: "moneyway_1x2",
        side: "1",
        category: "reversal",
        is_alarm: false,
        is_preview: false,
        severity: 1,
        score: 0,
        conditions_met: 2,
        message: "Reversal denemesi — 2/3 kriter (sadece log)",
        created_at: "2025-11-29T04:20:00Z",
        extra: {}
    },
    {
        id: "uuid-7",
        match_id: "Porto|Benfica|Liga|29.11.2025",
        market: "moneyway_1x2",
        side: "X",
        category: "reversal",
        is_alarm: false,
        is_preview: false,
        severity: 1,
        score: 0,
        conditions_met: 0,
        message: "Reversal denemesi — 0/3 kriter (sadece log)",
        created_at: "2025-11-29T04:15:00Z",
        extra: {}
    }
];

/**
 * Maç ID'sinden Home/Away çıkar
 */
function parseMatchId(matchId) {
    const parts = matchId.split('|');
    return {
        home: parts[0] || '',
        away: parts[1] || '',
        league: parts[2] || '',
        date: parts[3] || ''
    };
}

/**
 * Timestamp'i formatla
 */
function formatTime(timestamp) {
    if (!timestamp) return '';
    const date = new Date(timestamp);
    return date.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' });
}

/**
 * ============================================================
 * ANA FİLTRELEME FONKSİYONU
 * ============================================================
 * 
 * Alarm Listesi için SADECE is_alarm === true olanları döndür
 */
function filterRealAlarms(alarms) {
    return alarms.filter(alarm => alarm.is_alarm === true);
}

/**
 * Preview / Log için SADECE is_alarm === false olanları döndür
 */
function filterPreviewAlarms(alarms) {
    return alarms.filter(alarm => alarm.is_alarm === false);
}

/**
 * Para miktarını formatla
 */
function formatMoney(amount) {
    if (!amount || amount === 0) return '';
    const num = parseFloat(amount);
    return num.toLocaleString('en-GB') + ' £';
}

/**
 * ============================================================
 * ALARM KARTI RENDER FONKSİYONU
 * ============================================================
 */
function renderAlarmCard(alarm) {
    const config = AlarmConfig.categories[alarm.category] || AlarmConfig.categories.sharp;
    const match = parseMatchId(alarm.match_id);
    const time = formatTime(alarm.created_at);
    
    let displayText = alarm.message;
    
    if (alarm.category === 'sharp') {
        const score = alarm.sharp_score || alarm.score || 0;
        const newBet = alarm.new_bet_amount || alarm.money_diff || alarm.extra?.new_bet_amount || 0;
        const oddOld = alarm.odd_old || alarm.odds_from || alarm.extra?.odd_old || alarm.extra?.odds_from || 0;
        const oddNew = alarm.odd_new || alarm.odds_to || alarm.extra?.odd_new || alarm.extra?.odds_to || 0;
        const dropPct = alarm.drop_pct || alarm.extra?.drop_pct || 0;
        
        let parts = [`Sharp Money`, `Skor: ${score.toFixed(1)}`];
        
        if (newBet > 0) {
            parts.push(`Gelen Para: ${formatMoney(newBet)}`);
        }
        
        if (oddOld > 0 && oddNew > 0 && dropPct > 0) {
            parts.push(`Oran: ${oddOld.toFixed(2)} → ${oddNew.toFixed(2)} (${dropPct.toFixed(1)}%)`);
        }
        
        displayText = parts.join(' | ');
    }
    
    return `
        <div class="alarm-card" 
             style="border-left: 4px solid ${config.color}; background: ${config.bgColor};"
             data-alarm-id="${alarm.id}"
             data-category="${alarm.category}">
            <div class="alarm-card-header">
                <span class="alarm-icon">${config.icon}</span>
                <span class="alarm-type" style="color: ${config.color};">${displayText}</span>
            </div>
            <div class="alarm-card-match">
                ${match.home} - ${match.away}
            </div>
            <div class="alarm-card-meta">
                <span class="alarm-side">${alarm.side}</span>
                <span class="alarm-time">${time}</span>
            </div>
        </div>
    `;
}

/**
 * ============================================================
 * ALARM LİSTESİ RENDER FONKSİYONU
 * ============================================================
 * 
 * SADECE is_alarm === true olanlar gösterilir
 */
function renderAlarmList(containerId, alarms) {
    const container = document.getElementById(containerId);
    if (!container) {
        console.error(`Container not found: ${containerId}`);
        return;
    }
    
    const realAlarms = filterRealAlarms(alarms);
    
    if (realAlarms.length === 0) {
        container.innerHTML = `
            <div class="alarm-empty">
                <span>Aktif alarm yok</span>
            </div>
        `;
        return;
    }
    
    const sortedAlarms = realAlarms.sort((a, b) => 
        new Date(b.created_at) - new Date(a.created_at)
    );
    
    const stats = {
        sharp: sortedAlarms.filter(a => a.category === 'sharp').length,
        dropping: sortedAlarms.filter(a => a.category === 'dropping').length,
        reversal: sortedAlarms.filter(a => a.category === 'reversal').length
    };
    
    container.innerHTML = `
        <div class="alarm-list-header">
            <span class="alarm-count">${realAlarms.length} Aktif Alarm</span>
            <div class="alarm-stats">
                ${stats.sharp > 0 ? `<span class="stat-badge" style="background: ${AlarmConfig.categories.sharp.color};">Sharp: ${stats.sharp}</span>` : ''}
                ${stats.dropping > 0 ? `<span class="stat-badge" style="background: ${AlarmConfig.categories.dropping.color};">Dropping: ${stats.dropping}</span>` : ''}
                ${stats.reversal > 0 ? `<span class="stat-badge" style="background: ${AlarmConfig.categories.reversal.color};">Reversal: ${stats.reversal}</span>` : ''}
            </div>
        </div>
        <div class="alarm-list-content">
            ${sortedAlarms.map(alarm => renderAlarmCard(alarm)).join('')}
        </div>
    `;
}

/**
 * ============================================================
 * ALARM LOG RENDER FONKSİYONU (Maç Detayı İçin)
 * ============================================================
 * 
 * SADECE is_alarm === false olanlar gösterilir
 */
function renderAlarmLog(containerId, alarms) {
    const container = document.getElementById(containerId);
    if (!container) {
        console.error(`Container not found: ${containerId}`);
        return;
    }
    
    const logAlarms = filterPreviewAlarms(alarms);
    
    if (logAlarms.length === 0) {
        container.innerHTML = `
            <div class="alarm-log-empty">
                <span>Alarm geçmişi boş</span>
            </div>
        `;
        return;
    }
    
    const sortedLogs = logAlarms.sort((a, b) => 
        new Date(b.created_at) - new Date(a.created_at)
    );
    
    container.innerHTML = `
        <div class="alarm-log-header">
            <span>Alarm Geçmişi / Log (${logAlarms.length})</span>
        </div>
        <div class="alarm-log-content">
            ${sortedLogs.map(alarm => {
                const config = AlarmConfig.categories[alarm.category] || AlarmConfig.categories.sharp;
                const match = parseMatchId(alarm.match_id);
                const time = formatTime(alarm.created_at);
                
                return `
                    <div class="alarm-log-item" style="border-left: 2px solid ${config.color}; opacity: 0.7;">
                        <span class="log-icon">${config.icon}</span>
                        <span class="log-message">${alarm.message}</span>
                        <span class="log-match">${match.home} vs ${match.away}</span>
                        <span class="log-time">${time}</span>
                    </div>
                `;
            }).join('')}
        </div>
    `;
}

/**
 * ============================================================
 * DEMO / TEST FONKSİYONU
 * ============================================================
 */
function demoAlarmSystem() {
    console.log('='.repeat(60));
    console.log('ALARM SİSTEMİ DEMO');
    console.log('='.repeat(60));
    
    console.log('\nTüm alarmlar:', exampleAlarms.length);
    console.log('\n--- GERÇEK ALARMLAR (is_alarm === true) ---');
    
    const realAlarms = filterRealAlarms(exampleAlarms);
    console.log(`Toplam: ${realAlarms.length}`);
    realAlarms.forEach(a => {
        console.log(`  [${a.category.toUpperCase()}] ${a.message}`);
    });
    
    console.log('\n--- PREVIEW / LOG ALARMLAR (is_alarm === false) ---');
    
    const previewAlarms = filterPreviewAlarms(exampleAlarms);
    console.log(`Toplam: ${previewAlarms.length}`);
    previewAlarms.forEach(a => {
        console.log(`  [${a.category.toUpperCase()}] ${a.message}`);
    });
    
    console.log('\n' + '='.repeat(60));
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        AlarmConfig,
        filterRealAlarms,
        filterPreviewAlarms,
        renderAlarmList,
        renderAlarmLog,
        parseMatchId,
        formatTime
    };
}
