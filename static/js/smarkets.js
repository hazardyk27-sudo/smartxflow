let _smRefreshTimer = null;
let _smCountdownTimer = null;
let _smCountdownSec = 300;
const SM_REFRESH_INTERVAL = 5 * 60 * 1000;

function smFmt(n) {
    if (n === null || n === undefined) return '-';
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
    return n.toFixed(0);
}

function smFmtGBP(n) {
    if (n === null || n === undefined) return '-';
    return '\u00a3' + smFmt(n);
}

function smFmtOdds(n) {
    if (!n) return '-';
    return n.toFixed(2);
}

function smFmtPct(n) {
    if (n === null || n === undefined) return '-';
    return n.toFixed(1) + '%';
}

function smSetStatus(text, type) {
    var el = document.getElementById('smStatus');
    if (!el) return;
    var dot = el.querySelector('.sm-status-dot');
    var txt = el.querySelector('.sm-status-text');
    txt.textContent = text;
    dot.className = 'sm-status-dot sm-dot-' + type;
}

function smStartCountdown() {
    _smCountdownSec = 300;
    if (_smCountdownTimer) clearInterval(_smCountdownTimer);
    _smCountdownTimer = setInterval(function() {
        _smCountdownSec--;
        if (_smCountdownSec < 0) _smCountdownSec = 0;
        var m = Math.floor(_smCountdownSec / 60);
        var s = _smCountdownSec % 60;
        var el = document.getElementById('smCountdown');
        if (el) el.textContent = m + ':' + (s < 10 ? '0' : '') + s;
    }, 1000);
}

function smRenderEvents(data) {
    var container = document.getElementById('smEvents');
    if (!container) return;
    container.innerHTML = '';

    var events = data.events || [];
    if (events.length === 0) {
        container.innerHTML = '<div class="sm-no-data">Smarkets\'te aktif futbol maci bulunamadi.</div>';
        return;
    }

    events.forEach(function(ev) {
        var card = document.createElement('div');
        card.className = 'sm-card';

        var stateLabel = ev.state === 'live' ? '<span class="sm-live-badge">CANLI</span>' : '<span class="sm-upcoming-badge">YAKLASAN</span>';
        var totalVol = ev.market ? ev.market.total_volume_gbp : 0;

        var headerHTML = '<div class="sm-card-header">'
            + '<div class="sm-card-title">' + stateLabel + ' ' + escHtml(ev.name) + '</div>'
            + '<div class="sm-card-volume">Toplam Hacim: <strong>' + smFmtGBP(totalVol) + '</strong></div>'
            + '</div>';

        var sels = (ev.market && ev.market.selections) || [];
        var totalEstStake = 0;
        sels.forEach(function(s) { totalEstStake += s.est_back_stake || 0; });

        var tableHTML = '<table class="sm-table">'
            + '<thead><tr>'
            + '<th>Secenek</th>'
            + '<th>Bid (Back)</th>'
            + '<th>Offer (Lay)</th>'
            + '<th>Bekleyen Bid</th>'
            + '<th>Bekleyen Offer</th>'
            + '<th>Tahmini Stake</th>'
            + '<th>Dagılım</th>'
            + '<th>Spread</th>'
            + '</tr></thead><tbody>';

        sels.forEach(function(s) {
            var pct = totalEstStake > 0 ? (s.est_back_stake / totalEstStake * 100) : 0;
            var barW = Math.min(pct, 100);
            var barColor = s.sel_key === '1' ? '#4ade80' : s.sel_key === 'X' ? '#facc15' : '#60a5fa';

            var matchedHTML = '';
            if (ev.delta && ev.delta.per_sel_matched && ev.delta.per_sel_matched[s.id]) {
                var matched = ev.delta.per_sel_matched[s.id];
                matchedHTML = ' <span class="sm-matched-badge">+' + smFmtGBP(matched) + '</span>';
            }

            tableHTML += '<tr>'
                + '<td class="sm-sel-name"><span class="sm-sel-key sm-sel-' + s.sel_key + '">' + s.sel_key + '</span> ' + escHtml(s.name) + '</td>'
                + '<td class="sm-num">' + smFmtPct(s.best_bid_pct) + ' <span class="sm-odds">(' + smFmtOdds(s.best_bid_odds) + ')</span></td>'
                + '<td class="sm-num">' + smFmtPct(s.best_offer_pct) + ' <span class="sm-odds">(' + smFmtOdds(s.best_offer_odds) + ')</span></td>'
                + '<td class="sm-num sm-bid-val">' + smFmtGBP(s.total_bid_gbp) + '</td>'
                + '<td class="sm-num sm-offer-val">' + smFmtGBP(s.total_offer_gbp) + '</td>'
                + '<td class="sm-num sm-stake-val">' + smFmtGBP(s.est_back_stake) + matchedHTML + '</td>'
                + '<td class="sm-bar-cell"><div class="sm-bar-bg"><div class="sm-bar-fill" style="width:' + barW + '%;background:' + barColor + '"></div></div><span class="sm-bar-pct">' + pct.toFixed(1) + '%</span></td>'
                + '<td class="sm-num sm-spread-val">' + smFmtPct(s.spread) + '</td>'
                + '</tr>';
        });

        tableHTML += '</tbody></table>';

        var deltaHTML = '';
        if (ev.delta) {
            var d = ev.delta;
            deltaHTML = '<div class="sm-delta-bar">'
                + '<span class="sm-delta-item"><span class="sm-delta-label">Eslesme:</span> <span class="sm-delta-val sm-green">' + smFmtGBP(d.volume_increase) + '</span></span>'
                + '<span class="sm-delta-item"><span class="sm-delta-label">Akis:</span> <span class="sm-delta-val">' + smFmtGBP(d.flow_per_min) + '/dk</span></span>'
                + '<span class="sm-delta-item"><span class="sm-delta-label">Bid Dususu:</span> <span class="sm-delta-val sm-red">' + smFmtGBP(d.total_bid_drop) + '</span></span>'
                + '<span class="sm-delta-item"><span class="sm-delta-label">Tahmini Iptal:</span> <span class="sm-delta-val sm-yellow">' + smFmtGBP(d.estimated_cancelled) + '</span></span>'
                + '<span class="sm-delta-item sm-delta-time">' + d.elapsed_min + ' dk once</span>'
                + '</div>';
        }

        card.innerHTML = headerHTML + tableHTML + deltaHTML;
        container.appendChild(card);
    });
}

function escHtml(s) {
    if (!s) return '';
    var d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

function smFetchData() {
    var loadingEl = document.getElementById('smLoading');
    var errorEl = document.getElementById('smError');
    var eventsEl = document.getElementById('smEvents');
    var footerEl = document.getElementById('smFooterInfo');

    if (eventsEl.style.display === 'none') {
        loadingEl.style.display = '';
    }
    errorEl.style.display = 'none';
    smSetStatus('Yukleniyor...', 'loading');

    var savedKey = localStorage.getItem('smartxflow_web_license');
    var headers = {};
    if (savedKey) headers['X-License-Key'] = savedKey;

    fetch('/api/smarkets/data', { headers: headers })
        .then(function(r) {
            if (r.status === 403) {
                localStorage.removeItem('smartxflow_web_license');
                window.location.href = '/';
                return;
            }
            if (!r.ok) throw new Error('API hata: ' + r.status);
            return r.json();
        })
        .then(function(data) {
            if (!data) return;
            loadingEl.style.display = 'none';
            if (data.error) {
                errorEl.style.display = '';
                document.getElementById('smErrorText').textContent = data.error;
                smSetStatus('Hata', 'error');
                return;
            }
            eventsEl.style.display = '';
            footerEl.style.display = '';
            smRenderEvents(data);

            var now = new Date();
            var timeStr = (now.getHours() < 10 ? '0' : '') + now.getHours() + ':' + (now.getMinutes() < 10 ? '0' : '') + now.getMinutes();
            document.getElementById('smLastUpdate').textContent = timeStr;

            var statusText = data.has_previous ? 'Canli (delta aktif)' : 'Canli (ilk veri)';
            smSetStatus(statusText, 'live');
            smStartCountdown();
        })
        .catch(function(err) {
            loadingEl.style.display = 'none';
            errorEl.style.display = '';
            document.getElementById('smErrorText').textContent = err.message || 'Baglanti hatasi';
            smSetStatus('Hata', 'error');
        });
}

document.addEventListener('DOMContentLoaded', function() {
    smFetchData();
    _smRefreshTimer = setInterval(smFetchData, SM_REFRESH_INTERVAL);
});
