(function () {
    'use strict';

    var activeScope = 'active';
    var activeState = 'ALL';
    var cards = [];
    var installed = false;
    var wrapped = false;

    var COPY = {
        en: {
            button: 'Analyses V2',
            title: 'Analyses V2',
            subtitle: 'Explainable price & money market analysis',
            question: 'What is the market saying?',
            intro: 'Money percentage alone is not a signal. V2 reads what the price does when money arrives, then checks real cross-market confirmation and risks.',
            ruleTitle: 'CORE RULE',
            rule: 'Money arrived → odds shortened → market confirmed.',
            active: 'Active', history: 'History', all: 'All',
            opportunity: 'OPPORTUNITY', watch: 'WATCH', avoid: 'AVOID', unknown: 'NO DATA',
            total: 'Total', noData: 'No V2 signals in this view.',
            noDataSub: 'The interface does not fabricate demo signals. Real immutable V2 records will appear here.',
            ledgerWaiting: 'V2 interface is ready, but the immutable V2 ledger is not available in this environment yet.',
            loadFail: 'V2 signals could not be loaded.',
            recommendation: 'Recommended expression', diagnosis: 'Market diagnosis only',
            window: 'Window', moneyAdded: 'Money added', oddsMove: 'Odds move', moneyShare: 'Money share',
            whyRisk: 'Why / Risks', noRisk: 'No material risk recorded.',
            components: {price_confirmation:'Price confirmation',money_flow:'Money flow',timing:'Timing',cross_market:'Cross-market',poly:'Poly',risk:'Risk'},
            levels: {STRONG:'Strong',MEDIUM:'Medium',WEAK:'Weak',NEUTRAL:'Neutral',MIXED:'Mixed',CONFLICT:'Conflict',UNAVAILABLE:'No data',UNKNOWN:'No data'}
        },
        tr: {
            button: 'Analizler V2',
            title: 'Analizler V2',
            subtitle: 'Açıklanabilir fiyat ve para akışı analizi',
            question: 'Piyasa ne söylüyor?',
            intro: 'Para yüzdesi tek başına sinyal değildir. V2 para geldiğinde fiyatın ne yaptığını, gerçek çapraz market teyidini ve riskleri birlikte okur.',
            ruleTitle: 'TEMEL KURAL',
            rule: 'Para geldi → oran düştü → piyasa teyit etti.',
            active: 'Aktif', history: 'Geçmiş', all: 'Tümü',
            opportunity: 'FIRSAT', watch: 'İZLE', avoid: 'UZAK DUR', unknown: 'VERİ YOK',
            total: 'Toplam', noData: 'Bu görünümde V2 sinyali yok.',
            noDataSub: 'Arayüz sahte/demo sinyal üretmez. Gerçek immutable V2 kayıtları burada görünecek.',
            ledgerWaiting: 'V2 arayüzü hazır; fakat immutable V2 ledger bu ortamda henüz kullanılamıyor.',
            loadFail: 'V2 sinyalleri yüklenemedi.',
            recommendation: 'Önerilen ifade', diagnosis: 'Yalnızca piyasa teşhisi',
            window: 'Pencere', moneyAdded: 'Eklenen para', oddsMove: 'Oran hareketi', moneyShare: 'Para payı',
            whyRisk: 'Neden / Riskler', noRisk: 'Kayıtlı materyal risk yok.',
            components: {price_confirmation:'Fiyat teyidi',money_flow:'Para akışı',timing:'Zamanlama',cross_market:'Cross-market',poly:'Poly',risk:'Risk'},
            levels: {STRONG:'Güçlü',MEDIUM:'Orta',WEAK:'Zayıf',NEUTRAL:'Nötr',MIXED:'Karışık',CONFLICT:'Çelişki',UNAVAILABLE:'Veri yok',UNKNOWN:'Veri yok'}
        }
    };

    function lang() {
        try {
            var value = window.SXFI18n && window.SXFI18n.current ? window.SXFI18n.current() : 'en';
            return value === 'tr' ? 'tr' : 'en';
        } catch (e) { return 'en'; }
    }
    function t() { return COPY[lang()]; }
    function esc(value) {
        return String(value == null ? '' : value)
            .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
            .replace(/"/g,'&quot;').replace(/'/g,'&#039;');
    }
    function num(value) { var n = Number(value); return isFinite(n) ? n : null; }
    function odds(value) { var n = num(value); return n == null ? '—' : n.toFixed(2); }
    function pct(value) { var n = num(value); return n == null ? '—' : (n.toFixed(Math.abs(n % 1) < 0.001 ? 0 : 1) + '%'); }
    function money(value, signed) {
        var n = num(value); if (n == null) return '—';
        var sign = signed && n > 0 ? '+' : (n < 0 ? '−' : '');
        var a = Math.abs(n), body;
        if (a >= 1000000) body = (a / 1000000).toFixed(a >= 10000000 ? 0 : 1) + 'M';
        else if (a >= 1000) body = (a / 1000).toFixed(a >= 100000 ? 0 : 1) + 'K';
        else body = a.toFixed(a >= 100 ? 0 : 1);
        return sign + '£' + body;
    }
    function stateTone(card) {
        return card && card.state_tone ? card.state_tone : 'muted';
    }
    function stateText(card) {
        var c = t();
        if (!card) return c.unknown;
        if (card.state === 'FIRSAT') return c.opportunity;
        if (card.state === 'IZLE') return c.watch;
        if (card.state === 'UZAK_DUR') return c.avoid;
        return c.unknown;
    }
    function windowText(value) {
        var tr = lang() === 'tr';
        return ({'30m':tr?'Son 30 dk':'Last 30m','2h':tr?'Son 2 saat':'Last 2h','6h':tr?'Son 6 saat':'Last 6h','open':tr?'Açılıştan beri':'Since open'})[value] || '—';
    }
    function levelClass(level) { return String(level || 'unknown').toLowerCase(); }
    function currentLicenseHeaders() {
        var key = '';
        try { key = window.userLicenseKey || localStorage.getItem('smartxflow_web_license') || ''; } catch (e) {}
        return key ? {'X-License-Key': key} : {};
    }

    function removeMode() {
        var body = document.querySelector('.trends-modal-body');
        if (body) body.classList.remove('analysis-v2-mode');
    }

    function wrapExistingModalFunctions() {
        if (wrapped) return;
        wrapped = true;
        if (typeof window.openTrendsModal === 'function') {
            var originalOpen = window.openTrendsModal;
            window.openTrendsModal = function () {
                removeMode();
                return originalOpen.apply(this, arguments);
            };
        }
        if (typeof window.closeTrendsModal === 'function') {
            var originalClose = window.closeTrendsModal;
            window.closeTrendsModal = function () {
                removeMode();
                return originalClose.apply(this, arguments);
            };
        }
    }

    function setButtonLabel(button) {
        if (!button) return;
        var label = button.querySelector('span[data-i18n], span:not(.analysis-active-badge)');
        if (label) {
            label.removeAttribute('data-i18n');
            label.textContent = t().button;
        }
    }

    function installButtons() {
        if (installed) return;
        var desktopButtons = document.querySelectorAll('button.btn.btn-today.desktop-only');
        var desktopSource = null;
        for (var i = 0; i < desktopButtons.length; i++) {
            if ((desktopButtons[i].getAttribute('onclick') || '').indexOf('_testGuardAnalysis') !== -1) {
                desktopSource = desktopButtons[i]; break;
            }
        }
        if (desktopSource && !document.getElementById('analysisV2Btn')) {
            var desktop = desktopSource.cloneNode(true);
            desktop.id = 'analysisV2Btn';
            desktop.setAttribute('onclick', 'openAnalysisV2Modal()');
            desktop.removeAttribute('data-i18n');
            var badge = desktop.querySelector('.analysis-active-badge');
            if (badge) badge.remove();
            setButtonLabel(desktop);
            desktopSource.insertAdjacentElement('afterend', desktop);
        }

        var mobileButtons = document.querySelectorAll('#mobileOverflowMenu button');
        var mobileSource = null;
        for (var j = 0; j < mobileButtons.length; j++) {
            if ((mobileButtons[j].getAttribute('onclick') || '').indexOf('_testGuardAnalysis') !== -1) {
                mobileSource = mobileButtons[j]; break;
            }
        }
        if (mobileSource && !document.getElementById('analysisV2BtnMobile')) {
            var mobile = mobileSource.cloneNode(true);
            mobile.id = 'analysisV2BtnMobile';
            mobile.setAttribute('onclick', 'openAnalysisV2Modal(); closeMobileOverflow();');
            var mb = mobile.querySelector('.analysis-active-badge');
            if (mb) mb.remove();
            setButtonLabel(mobile);
            mobileSource.insertAdjacentElement('afterend', mobile);
        }
        installed = true;
    }

    function visibleCards() {
        if (activeState === 'ALL') return cards;
        return cards.filter(function (card) { return card.state === activeState; });
    }

    function countsHtml() {
        var c = t(), counts = {FIRSAT:0,IZLE:0,UZAK_DUR:0,UNKNOWN:0};
        cards.forEach(function (card) {
            var key = counts[card.state] !== undefined ? card.state : 'UNKNOWN';
            counts[key] += 1;
        });
        return '<div class="a2m-counts">' +
            '<div class="a2m-count"><span>' + esc(c.total) + '</span><strong>' + cards.length + '</strong></div>' +
            '<div class="a2m-count op"><span>' + esc(c.opportunity) + '</span><strong>' + counts.FIRSAT + '</strong></div>' +
            '<div class="a2m-count watch"><span>' + esc(c.watch) + '</span><strong>' + counts.IZLE + '</strong></div>' +
            '<div class="a2m-count avoid"><span>' + esc(c.avoid) + '</span><strong>' + counts.UZAK_DUR + '</strong></div>' +
            '</div>';
    }

    function controlsHtml() {
        var c = t();
        function b(label, value, current, cls) {
            return '<button class="a2m-btn' + (value === current ? ' active' : '') + '" onclick="' + cls + '(\'' + value + '\')">' + esc(label) + '</button>';
        }
        return '<div class="a2m-controls"><div class="a2m-tabs">' +
            b(c.active,'active',activeScope,'analysisV2SetScope') +
            b(c.history,'history',activeScope,'analysisV2SetScope') +
            b(c.all,'all',activeScope,'analysisV2SetScope') +
            '</div><div class="a2m-states">' +
            b(c.all,'ALL',activeState,'analysisV2SetState') +
            b(c.opportunity,'FIRSAT',activeState,'analysisV2SetState') +
            b(c.watch,'IZLE',activeState,'analysisV2SetState') +
            b(c.avoid,'UZAK_DUR',activeState,'analysisV2SetState') +
            '</div></div>';
    }

    function componentHtml(item) {
        var c = t(), key = item && item.key ? item.key : '', level = String(item && item.level || 'UNKNOWN').toUpperCase();
        var label = c.components[key] || (item && item.label) || key;
        var levelLabel = c.levels[level] || (item && item.level_label) || level;
        return '<div class="a2m-component"><span>' + esc(label) + '</span><strong class="' + esc(levelClass(level)) + '">' + esc(levelLabel) + '</strong></div>';
    }

    function detailHtml(card) {
        var c = t(), why = card.why || [], risks = card.risks || [], html = '';
        if (why.length) html += '<div><strong style="color:#909aa3">Why</strong><br>' + why.map(esc).join('<br>') + '</div>';
        if (risks.length) html += '<div style="margin-top:6px"><strong style="color:#c98787">Risks</strong><br>' + risks.map(function (r) { return esc(String(r.code || '').replace(/_/g,' ')) + ' · ' + esc(r.severity || ''); }).join('<br>') + '</div>';
        if (!why.length && !risks.length) html = esc(c.noRisk);
        return html;
    }

    function cardHtml(card) {
        var c = t(), reco = card.recommendation || {}, mv = card.movement || {}, flow = card.flow || [], components = card.components || [];
        var isReco = reco.decision === 'RECOMMEND' || (!!reco.market && reco.odds != null);
        var recoTitle = isReco ? c.recommendation : c.diagnosis;
        var selection = reco.selection || (card.details && card.details.source_selection) || '—';
        var recoLine = esc(selection) + (isReco && reco.odds != null ? '<em>@' + esc(odds(reco.odds)) + '</em>' : '');
        var oddsMove = (mv.base_odds != null || mv.current_odds != null) ? odds(mv.base_odds) + ' → ' + odds(mv.current_odds) : '—';
        var moneyShare = pct(mv.current_pct) + (num(mv.pct_delta) != null ? ' · ' + (num(mv.pct_delta) > 0 ? '+' : '') + Number(mv.pct_delta).toFixed(1) + 'pp' : '');
        var flowHtml = flow.map(function (step, idx) {
            return (idx ? '<span class="a2m-arrow">→</span>' : '') + '<span class="a2m-step ' + esc(step.tone || '') + '">' + esc(step.label || '') + '</span>';
        }).join('');
        var meta = [card.league || '', card.outcome ? ('· ' + card.outcome) : ''].filter(Boolean).join(' ');
        return '<article class="a2m-card ' + esc(stateTone(card)) + '">' +
            '<div class="a2m-card-top"><div><span class="a2m-state ' + esc(stateTone(card)) + '">' + esc(stateText(card)) + '</span>' +
            '<div class="a2m-match">' + esc(card.match || '') + '</div><div class="a2m-meta">' + esc(meta) + '</div></div>' +
            '<div class="a2m-reco"><small>' + esc(recoTitle) + '</small><strong>' + recoLine + '</strong></div></div>' +
            '<div class="a2m-dir">' + esc(reco.direction_copy || '') + '</div>' +
            '<div class="a2m-flow">' + flowHtml + '</div>' +
            '<div class="a2m-metrics">' +
            '<div class="a2m-metric"><span>' + esc(c.window) + '</span><strong>' + esc(windowText(mv.window)) + '</strong></div>' +
            '<div class="a2m-metric"><span>' + esc(c.moneyAdded) + '</span><strong>' + esc(money(mv.money_added,true)) + '</strong></div>' +
            '<div class="a2m-metric"><span>' + esc(c.oddsMove) + '</span><strong>' + esc(oddsMove) + '</strong></div>' +
            '<div class="a2m-metric"><span>' + esc(c.moneyShare) + '</span><strong>' + esc(moneyShare) + '</strong></div></div>' +
            '<div class="a2m-components">' + components.map(componentHtml).join('') + '</div>' +
            '<details class="a2m-details"><summary>' + esc(c.whyRisk) + '</summary><div class="a2m-detail-body">' + detailHtml(card) + '</div></details>' +
            '</article>';
    }

    function shellHtml() {
        var c = t();
        return '<div class="a2m"><div class="a2m-hero"><div><div class="a2m-kicker">ANALYSES V2</div><h3>' + esc(c.question) + '</h3><p>' + esc(c.intro) + '</p></div>' +
            '<div class="a2m-rule"><strong>' + esc(c.ruleTitle) + '</strong>' + esc(c.rule) + '</div></div>' + controlsHtml() + countsHtml() + '<div id="analysisV2List" class="a2m-list"></div></div>';
    }

    function renderList() {
        var list = document.getElementById('analysisV2List');
        if (!list) return;
        var visible = visibleCards(), c = t();
        if (!visible.length) {
            list.innerHTML = '<div class="a2m-empty"><strong>' + esc(c.noData) + '</strong>' + esc(c.noDataSub) + '</div>';
            return;
        }
        list.innerHTML = visible.map(cardHtml).join('');
    }

    function refreshChrome() {
        var area = document.getElementById('trendsContentArea');
        if (!area) return;
        area.innerHTML = shellHtml();
        renderList();
    }

    function loadSignals() {
        var area = document.getElementById('trendsContentArea'), c = t();
        if (!area) return;
        area.innerHTML = '<div class="a2m-loading">Loading Analyses V2…</div>';
        fetch('/api/analysis-v2/signals?scope=' + encodeURIComponent(activeScope) + '&limit=100', {headers: currentLicenseHeaders()})
            .then(function (r) {
                if (r.status === 401 || r.status === 403) throw new Error('AUTH');
                return r.json();
            })
            .then(function (payload) {
                if (!payload.available) {
                    area.innerHTML = '<div class="a2m"><div class="a2m-error">' + esc(payload.reason === 'V2_LEDGER_NOT_DEPLOYED' ? c.ledgerWaiting : c.loadFail) + '</div></div>';
                    return;
                }
                cards = Array.isArray(payload.signals) ? payload.signals : [];
                refreshChrome();
            })
            .catch(function () {
                area.innerHTML = '<div class="a2m"><div class="a2m-error">' + esc(c.loadFail) + '</div></div>';
            });
    }

    window.analysisV2SetScope = function (scope) {
        activeScope = (scope === 'history' || scope === 'all') ? scope : 'active';
        activeState = 'ALL';
        loadSignals();
    };
    window.analysisV2SetState = function (state) {
        activeState = ['FIRSAT','IZLE','UZAK_DUR'].indexOf(state) !== -1 ? state : 'ALL';
        refreshChrome();
    };

    window.openAnalysisV2Modal = function () {
        if (window.userPlan && window.userPlan !== 'pro') {
            var message = lang() === 'tr' ? 'Analizler V2 PRO üyelikte aktif. PRO paketine yükseltmek ister misiniz?' : 'Analyses V2 is available on PRO. Would you like to upgrade?';
            if (window.confirm(message)) window.location.href = '/pricing';
            return;
        }
        var overlay = document.getElementById('trendsModalOverlay');
        var title = document.getElementById('trendsModalTitle');
        var subtitle = document.getElementById('trendsModalSubtitle');
        var body = document.querySelector('.trends-modal-body');
        if (!overlay || !body) return;
        body.classList.remove('sidebar-mode','mobile-article-open');
        body.classList.add('analysis-v2-mode');
        if (title) title.textContent = t().title;
        if (subtitle) subtitle.textContent = t().subtitle;
        overlay.style.display = 'flex';
        document.body.style.overflow = 'hidden';
        activeScope = 'active';
        activeState = 'ALL';
        loadSignals();
    };

    function updateLabels() {
        setButtonLabel(document.getElementById('analysisV2Btn'));
        setButtonLabel(document.getElementById('analysisV2BtnMobile'));
        var body = document.querySelector('.trends-modal-body');
        if (body && body.classList.contains('analysis-v2-mode')) {
            var title = document.getElementById('trendsModalTitle');
            var subtitle = document.getElementById('trendsModalSubtitle');
            if (title) title.textContent = t().title;
            if (subtitle) subtitle.textContent = t().subtitle;
            refreshChrome();
        }
    }

    function init() {
        wrapExistingModalFunctions();
        installButtons();
        window.addEventListener('i18n:change', updateLabels);
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
