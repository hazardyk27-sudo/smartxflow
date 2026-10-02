(function () {
    'use strict';

    var activeScope = 'active';
    var activeState = 'ALL';
    var cards = [];
    var installed = false;
    var wrapped = false;
    var liveFallbackMode = false;
    var liveFallbackCache = null;
    var liveFallbackCacheTs = 0;
    var LIVE_CACHE_TTL = 45000;

    var COPY = {
        en: {
            button: 'Analyses V2', title: 'Analyses V2', subtitle: 'Explainable price & money market analysis',
            question: 'What is the market saying?',
            intro: 'Money percentage alone is not a signal. V2 reads what the price does when money arrives, then checks real cross-market confirmation and risks.',
            ruleTitle: 'CORE RULE', rule: 'Money arrived → odds shortened → market confirmed.',
            active: 'Active', history: 'History', all: 'All',
            opportunity: 'OPPORTUNITY', watch: 'WATCH', avoid: 'AVOID', unknown: 'NO DATA', total: 'Total',
            noData: 'No V2 movement meets the current rules in this view.',
            noDataSub: 'High money percentage alone is intentionally ignored. V2 waits for a real price + money pattern.',
            ledgerWaiting: 'Immutable ledger is not deployed. Showing live read-only V2 diagnosis from existing snapshots; history and settlement remain off.',
            loadFail: 'V2 signals could not be loaded.', recommendation: 'Recommended expression', diagnosis: 'Market diagnosis only',
            window: 'Window', moneyAdded: 'Money added', oddsMove: 'Odds move', moneyShare: 'Money share',
            whyRisk: 'Why / Risks', noRisk: 'No material risk recorded.',
            liveMode: 'LIVE READ-ONLY · Existing snapshot/history data · no DB writes · cross-market protection unavailable until the V2 ledger/runtime is deployed.',
            components: {price_confirmation:'Price confirmation',money_flow:'Money flow',timing:'Timing',cross_market:'Cross-market',poly:'Poly',risk:'Risk'},
            levels: {STRONG:'Strong',MEDIUM:'Medium',WEAK:'Weak',NEUTRAL:'Neutral',MIXED:'Mixed',CONFLICT:'Conflict',UNAVAILABLE:'No data',UNKNOWN:'No data'}
        },
        tr: {
            button: 'Analizler V2', title: 'Analizler V2', subtitle: 'Açıklanabilir fiyat ve para akışı analizi',
            question: 'Piyasa ne söylüyor?',
            intro: 'Para yüzdesi tek başına sinyal değildir. V2 para geldiğinde fiyatın ne yaptığını, gerçek çapraz market teyidini ve riskleri birlikte okur.',
            ruleTitle: 'TEMEL KURAL', rule: 'Para geldi → oran düştü → piyasa teyit etti.',
            active: 'Aktif', history: 'Geçmiş', all: 'Tümü',
            opportunity: 'FIRSAT', watch: 'İZLE', avoid: 'UZAK DUR', unknown: 'VERİ YOK', total: 'Toplam',
            noData: 'Bu görünümde V2 kurallarını karşılayan piyasa hareketi yok.',
            noDataSub: 'Yüksek para yüzdesi tek başına özellikle sinyal sayılmaz. V2 gerçek fiyat + para davranışını bekler.',
            ledgerWaiting: 'Immutable ledger deploy edilmedi. Mevcut snapshotlardan canlı read-only V2 teşhisi gösteriliyor; geçmiş ve settlement kapalı.',
            loadFail: 'V2 sinyalleri yüklenemedi.', recommendation: 'Önerilen ifade', diagnosis: 'Yalnızca piyasa teşhisi',
            window: 'Pencere', moneyAdded: 'Eklenen para', oddsMove: 'Oran hareketi', moneyShare: 'Para payı',
            whyRisk: 'Neden / Riskler', noRisk: 'Kayıtlı materyal risk yok.',
            liveMode: 'CANLI READ-ONLY · Mevcut snapshot/history verisi · DB yazımı yok · V2 ledger/runtime açılana kadar cross-market koruması kullanılamaz.',
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
    function num(value) {
        if (value === null || value === undefined || value === '' || value === '-') return null;
        var n = Number(String(value).replace(/[^0-9.\-]/g,''));
        return isFinite(n) ? n : null;
    }
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
    function parseTime(value) {
        if (!value) return null;
        var direct = Date.parse(value);
        if (!isNaN(direct)) return direct;
        var m = String(value).match(/^(\d{1,2})[.\/-](\d{1,2})[.\/-](\d{4})(?:\s+(\d{1,2}):(\d{2}))?/);
        if (!m) return null;
        return Date.UTC(Number(m[3]), Number(m[2]) - 1, Number(m[1]), Number(m[4] || 0), Number(m[5] || 0));
    }
    function stateTone(card) { return card && card.state_tone ? card.state_tone : 'muted'; }
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
            window.openTrendsModal = function () { removeMode(); return originalOpen.apply(this, arguments); };
        }
        if (typeof window.closeTrendsModal === 'function') {
            var originalClose = window.closeTrendsModal;
            window.closeTrendsModal = function () { removeMode(); return originalClose.apply(this, arguments); };
        }
    }
    function setButtonLabel(button) {
        if (!button) return;
        var label = button.querySelector('span[data-i18n], span:not(.analysis-active-badge)');
        if (label) { label.removeAttribute('data-i18n'); label.textContent = t().button; }
    }
    function installButtons() {
        if (installed) return;
        var desktopButtons = document.querySelectorAll('button.btn.btn-today.desktop-only'), desktopSource = null;
        for (var i = 0; i < desktopButtons.length; i++) {
            if ((desktopButtons[i].getAttribute('onclick') || '').indexOf('_testGuardAnalysis') !== -1) { desktopSource = desktopButtons[i]; break; }
        }
        if (desktopSource && !document.getElementById('analysisV2Btn')) {
            var desktop = desktopSource.cloneNode(true);
            desktop.id = 'analysisV2Btn'; desktop.setAttribute('onclick', 'openAnalysisV2Modal()'); desktop.removeAttribute('data-i18n');
            var badge = desktop.querySelector('.analysis-active-badge'); if (badge) badge.remove();
            setButtonLabel(desktop); desktopSource.insertAdjacentElement('afterend', desktop);
        }
        var mobileButtons = document.querySelectorAll('#mobileOverflowMenu button'), mobileSource = null;
        for (var j = 0; j < mobileButtons.length; j++) {
            if ((mobileButtons[j].getAttribute('onclick') || '').indexOf('_testGuardAnalysis') !== -1) { mobileSource = mobileButtons[j]; break; }
        }
        if (mobileSource && !document.getElementById('analysisV2BtnMobile')) {
            var mobile = mobileSource.cloneNode(true);
            mobile.id = 'analysisV2BtnMobile'; mobile.setAttribute('onclick', 'openAnalysisV2Modal(); closeMobileOverflow();');
            var mb = mobile.querySelector('.analysis-active-badge'); if (mb) mb.remove();
            setButtonLabel(mobile); mobileSource.insertAdjacentElement('afterend', mobile);
        }
        installed = true;
    }

    function visibleCards() {
        if (activeState === 'ALL') return cards;
        return cards.filter(function (card) { return card.state === activeState; });
    }
    function countsHtml() {
        var c = t(), counts = {FIRSAT:0,IZLE:0,UZAK_DUR:0,UNKNOWN:0};
        cards.forEach(function (card) { var key = counts[card.state] !== undefined ? card.state : 'UNKNOWN'; counts[key] += 1; });
        return '<div class="a2m-counts">' +
            '<div class="a2m-count"><span>' + esc(c.total) + '</span><strong>' + cards.length + '</strong></div>' +
            '<div class="a2m-count op"><span>' + esc(c.opportunity) + '</span><strong>' + counts.FIRSAT + '</strong></div>' +
            '<div class="a2m-count watch"><span>' + esc(c.watch) + '</span><strong>' + counts.IZLE + '</strong></div>' +
            '<div class="a2m-count avoid"><span>' + esc(c.avoid) + '</span><strong>' + counts.UZAK_DUR + '</strong></div></div>';
    }
    function controlsHtml() {
        var c = t();
        function b(label, value, current, cls, disabled) {
            return '<button class="a2m-btn' + (value === current ? ' active' : '') + '" ' + (disabled ? 'disabled title="Immutable ledger required" ' : '') + 'onclick="' + cls + '(\'' + value + '\')">' + esc(label) + '</button>';
        }
        return '<div class="a2m-controls"><div class="a2m-tabs">' +
            b(c.active,'active',activeScope,'analysisV2SetScope',false) +
            b(c.history,'history',activeScope,'analysisV2SetScope',liveFallbackMode) +
            b(c.all,'all',activeScope,'analysisV2SetScope',false) +
            '</div><div class="a2m-states">' +
            b(c.all,'ALL',activeState,'analysisV2SetState',false) +
            b(c.opportunity,'FIRSAT',activeState,'analysisV2SetState',false) +
            b(c.watch,'IZLE',activeState,'analysisV2SetState',false) +
            b(c.avoid,'UZAK_DUR',activeState,'analysisV2SetState',false) + '</div></div>';
    }
    function componentHtml(item) {
        var c = t(), key = item && item.key ? item.key : '', level = String(item && item.level || 'UNKNOWN').toUpperCase();
        return '<div class="a2m-component"><span>' + esc(c.components[key] || (item && item.label) || key) + '</span><strong class="' + esc(levelClass(level)) + '">' + esc(c.levels[level] || (item && item.level_label) || level) + '</strong></div>';
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
        var flowHtml = flow.map(function (step, idx) { return (idx ? '<span class="a2m-arrow">→</span>' : '') + '<span class="a2m-step ' + esc(step.tone || '') + '">' + esc(step.label || '') + '</span>'; }).join('');
        var meta = [card.league || '', card.outcome ? ('· ' + card.outcome) : ''].filter(Boolean).join(' ');
        return '<article class="a2m-card ' + esc(stateTone(card)) + '">' +
            '<div class="a2m-card-top"><div><span class="a2m-state ' + esc(stateTone(card)) + '">' + esc(stateText(card)) + '</span>' +
            '<div class="a2m-match">' + esc(card.match || '') + '</div><div class="a2m-meta">' + esc(meta) + '</div></div>' +
            '<div class="a2m-reco"><small>' + esc(recoTitle) + '</small><strong>' + recoLine + '</strong></div></div>' +
            '<div class="a2m-dir">' + esc(reco.direction_copy || '') + '</div><div class="a2m-flow">' + flowHtml + '</div>' +
            '<div class="a2m-metrics"><div class="a2m-metric"><span>' + esc(c.window) + '</span><strong>' + esc(windowText(mv.window)) + '</strong></div>' +
            '<div class="a2m-metric"><span>' + esc(c.moneyAdded) + '</span><strong>' + esc(money(mv.money_added,true)) + '</strong></div>' +
            '<div class="a2m-metric"><span>' + esc(c.oddsMove) + '</span><strong>' + esc(oddsMove) + '</strong></div>' +
            '<div class="a2m-metric"><span>' + esc(c.moneyShare) + '</span><strong>' + esc(moneyShare) + '</strong></div></div>' +
            '<div class="a2m-components">' + components.map(componentHtml).join('') + '</div>' +
            '<details class="a2m-details"><summary>' + esc(c.whyRisk) + '</summary><div class="a2m-detail-body">' + detailHtml(card) + '</div></details></article>';
    }
    function shellHtml() {
        var c = t();
        var live = liveFallbackMode ? '<div style="margin:0 0 10px;padding:8px 11px;border:1px solid rgba(246,185,74,.18);border-radius:9px;background:rgba(246,185,74,.055);color:#c8a660;font-size:10px;line-height:1.5;">' + esc(c.liveMode) + '</div>' : '';
        return '<div class="a2m"><div class="a2m-hero"><div><div class="a2m-kicker">ANALYSES V2</div><h3>' + esc(c.question) + '</h3><p>' + esc(c.intro) + '</p></div>' +
            '<div class="a2m-rule"><strong>' + esc(c.ruleTitle) + '</strong>' + esc(c.rule) + '</div></div>' + live + controlsHtml() + countsHtml() + '<div id="analysisV2List" class="a2m-list"></div></div>';
    }
    function renderList() {
        var list = document.getElementById('analysisV2List'); if (!list) return;
        var visible = visibleCards(), c = t();
        if (!visible.length) { list.innerHTML = '<div class="a2m-empty"><strong>' + esc(c.noData) + '</strong>' + esc(c.noDataSub) + '</div>'; return; }
        list.innerHTML = visible.map(cardHtml).join('');
    }
    function refreshChrome() {
        var area = document.getElementById('trendsContentArea'); if (!area) return;
        area.innerHTML = shellHtml(); renderList();
    }

    /* ---------- read-only live fallback: exact Part 4 thresholds ---------- */
    var V2CFG = {
        minMarketVolume:5000, minMoneyAdded:500, confirmedDrop:5, divergenceRise:5, flatBand:1,
        anomalyAdded:5000, anomalyAmount:10000, lateHours:2, lateDrop:3, lateMoney:1000,
        earlyHours:24, earlyDrop:3, earlyMoney:1000, anchorToleranceMs:60*60*1000, currentToleranceMs:60*60*1000
    };
    var SEL = {
        '1':{odds:'Odds1',pct:'Pct1',amt:'Amt1'},
        'X':{odds:'OddsX',pct:'PctX',amt:'AmtX'},
        '2':{odds:'Odds2',pct:'Pct2',amt:'Amt2'}
    };
    function historyPoint(row, code) {
        var s = SEL[code], ts = parseTime(row.ScrapedAt || row.scraped_at || row.scraped_at_utc);
        var p = num(row[s.pct]), v = num(row.Volume), a = num(row[s.amt]);
        if (a == null && p != null && v != null) a = p * v / 100;
        return {ts:ts, odds:num(row[s.odds]), pct:p, amount:a, market_volume:v};
    }
    function movement(base, current) {
        if (!base || !current || base.odds == null || current.odds == null || base.odds <= 0) return null;
        return {
            odds_drop_pct:(base.odds-current.odds)/base.odds*100,
            amount_delta:(base.amount != null && current.amount != null) ? current.amount-base.amount : null,
            pct_delta:(base.pct != null && current.pct != null) ? current.pct-base.pct : null
        };
    }
    function anchorAt(points, target) {
        var found = null;
        for (var i=0;i<points.length;i++) if (points[i].ts != null && points[i].ts <= target) found = points[i]; else if (points[i].ts != null && points[i].ts > target) break;
        if (!found || target-found.ts > V2CFG.anchorToleranceMs) return null;
        return found;
    }
    function evidence(base, current) {
        var mv = movement(base,current), out = {available:!!(base&&current&&mv),state:'NO_EDGE',price_state:'UNKNOWN',money_state:'UNKNOWN',market_volume_ok:false,odds_drop_pct:null,money_added:null,pct_delta:null};
        if (!out.available) return out;
        out.odds_drop_pct=mv.odds_drop_pct; out.money_added=mv.amount_delta; out.pct_delta=mv.pct_delta;
        out.market_volume_ok=current.market_volume!=null && current.market_volume>=V2CFG.minMarketVolume;
        var d=mv.odds_drop_pct, m=mv.amount_delta;
        out.price_state=d>=V2CFG.confirmedDrop?'SHORTENED':d<=-V2CFG.divergenceRise?'DRIFTED':Math.abs(d)<=V2CFG.flatBand?'FLAT':d>0?'SLIGHTLY_SHORTER':'SLIGHTLY_HIGHER';
        out.money_state=m==null?'UNKNOWN':m>=V2CFG.minMoneyAdded?'UP':m<=-V2CFG.minMoneyAdded?'DOWN':'FLAT';
        if (out.market_volume_ok && out.money_state==='UP') {
            if (d>=V2CFG.confirmedDrop) out.state='CONFIRMED_MOVE';
            else if (d<=-V2CFG.divergenceRise) out.state='PRICE_MONEY_DIVERGENCE';
            else if ((m>=V2CFG.anomalyAdded || (current.amount>=V2CFG.anomalyAmount && m>=V2CFG.minMoneyAdded)) && Math.abs(d)<=V2CFG.flatBand) out.state='ANOMALOUS_MONEY';
        }
        return out;
    }
    function firstAvailable(states, order) {
        for (var i=0;i<order.length;i++) if (states[order[i]] && states[order[i]].available) return {key:order[i],value:states[order[i]]};
        return null;
    }
    function classify(points, kickoffMs) {
        if (!points.length) return null;
        points.sort(function(a,b){return (a.ts||0)-(b.ts||0);});
        var current=points[points.length-1];
        if (!current.ts || Date.now()-current.ts>V2CFG.currentToleranceMs*3) return null;
        var asOf=current.ts, opening=points[0];
        var bases={
            '30m':anchorAt(points,asOf-30*60*1000), '2h':anchorAt(points,asOf-2*60*60*1000),
            '6h':anchorAt(points,asOf-6*60*60*1000), 'open':opening
        };
        var states={}; Object.keys(bases).forEach(function(k){states[k]=evidence(bases[k],current);});
        var decision=firstAvailable(states,['2h','6h','30m','open']);
        var recent=firstAvailable(states,['30m','2h','6h','open']);
        var hours=kickoffMs!=null?(kickoffMs-asOf)/3600000:null;
        var late=hours!=null&&hours>=0&&hours<=V2CFG.lateHours&&states['30m'].market_volume_ok&&states['30m'].money_added>=V2CFG.lateMoney&&states['30m'].odds_drop_pct>=V2CFG.lateDrop;
        var early=false, earlyKey=null;
        if (hours!=null&&hours>=V2CFG.earlyHours) {
            ['6h','open'].some(function(k){var s=states[k]; if(s.available&&s.market_volume_ok&&s.money_added>=V2CFG.earlyMoney&&s.odds_drop_pct>=V2CFG.earlyDrop){early=true;earlyKey=k;return true;} return false;});
        }
        var primary='NO_EDGE', key=decision&&decision.key, chosen=decision&&decision.value;
        if (recent&&recent.value.state==='PRICE_MONEY_DIVERGENCE'){primary='PRICE_MONEY_DIVERGENCE';key=recent.key;chosen=recent.value;}
        else if(late){primary='LATE_STEAM';key='30m';chosen=states['30m'];}
        else if(decision&&decision.value.state==='PRICE_MONEY_DIVERGENCE'){primary='PRICE_MONEY_DIVERGENCE';}
        else if(early){primary='EARLY_POSITION';key=earlyKey;chosen=states[earlyKey];}
        else if(decision&&decision.value.state==='CONFIRMED_MOVE'){primary='CONFIRMED_MOVE';}
        else if(decision&&decision.value.state==='ANOMALOUS_MONEY'){primary='ANOMALOUS_MONEY';}
        else if(recent&&recent.value.state==='ANOMALOUS_MONEY'){primary='ANOMALOUS_MONEY';key=recent.key;chosen=recent.value;}
        return {primary:primary,key:key,current:current,base:bases[key]||opening,evidence:chosen||{},hours:hours};
    }
    function flowFor(primary) {
        var tr=lang()==='tr';
        if(primary==='PRICE_MONEY_DIVERGENCE') return [
            {label:tr?'PARA GELDİ':'MONEY ARRIVED',tone:'positive'},{label:tr?'ORAN TERSİNE GİTTİ':'ODDS DRIFTED',tone:'negative'},{label:tr?'PİYASA ÇELİŞİYOR':'MARKET CONFLICT',tone:'negative'}];
        if(primary==='ANOMALOUS_MONEY') return [
            {label:tr?'OLAĞANDIŞI PARA':'UNUSUAL MONEY',tone:'positive'},{label:tr?'FİYAT TEPKİSİ ZAYIF':'PRICE FLAT',tone:'watch'},{label:tr?'İZLE':'WATCH',tone:'watch'}];
        return [
            {label:tr?'PARA GELDİ':'MONEY ARRIVED',tone:'positive'},{label:tr?'ORAN DÜŞTÜ':'ODDS SHORTENED',tone:'positive'},{label:tr?'CROSS-MARKET BEKLENİYOR':'CROSS-MARKET PENDING',tone:'watch'}];
    }
    function buildLiveCard(match, code, result) {
        var tr=lang()==='tr', supportive=['CONFIRMED_MOVE','LATE_STEAM','EARLY_POSITION'].indexOf(result.primary)!==-1;
        var divergence=result.primary==='PRICE_MONEY_DIVERGENCE', anomaly=result.primary==='ANOMALOUS_MONEY';
        if(!supportive&&!divergence&&!anomaly) return null;
        var current=result.current, base=result.base||{}, ev=result.evidence||{};
        var state=divergence?'UZAK_DUR':'IZLE', tone=divergence?'avoid':'watch';
        var directionCopy=code==='1'?(tr?'Ev sahibi tarafı güçleniyor.':'Home side is strengthening.'):code==='2'?(tr?'Deplasman tarafı güçleniyor.':'Away side is strengthening.'):(tr?'Beraberlik tarafında baskı oluşuyor.':'Draw pressure is building.');
        var highProtected=(code==='1'||code==='2')&&current.odds!=null&&current.odds>=2.75;
        var recommend=supportive&&!highProtected;
        var why=[];
        if(divergence) why.push(tr?'Para artarken oran ters yönde açılıyor.':'Money is rising while the price drifts the wrong way.');
        else if(anomaly) why.push(tr?'Olağandışı para geldi ancak fiyat henüz tepki vermiyor.':'Unusual money arrived but the price has not reacted yet.');
        else why.push(tr?'Para artışı fiyat kısalmasıyla teyit edildi.':'Money inflow is confirmed by price shortening.');
        why.push(tr?'DC/DNB generic app API’de gerçek quote olarak okunamadığı için cross-market teyidi verilmedi.':'DC/DNB are not exposed as real quotes by the generic app API, so cross-market confirmation is withheld.');
        var risks=[];
        if(divergence) risks.push({code:'PRICE_MONEY_DIVERGENCE',severity:'HARD'});
        if(highProtected) risks.push({code:'PROTECTED_MARKET_UNAVAILABLE',severity:'MEDIUM'});
        return {
            signal_id:'live_'+String(match.match_id||match.match_id_hash||'')+'_'+code,
            state:state,state_tone:tone,state_label:state,
            match:String(match.home_team||'')+' — '+String(match.away_team||''),league:String(match.league||''),outcome:null,
            recommendation:{decision:recommend?'RECOMMEND':'WATCH_ONLY',market:recommend?'1X2':'',selection:recommend?code:'',odds:recommend?current.odds:null,direction_copy:directionCopy},
            flow:flowFor(result.primary),
            movement:{window:result.key,base_odds:base.odds,current_odds:current.odds,money_added:ev.money_added,pct_delta:ev.pct_delta,current_pct:current.pct},
            components:[
                {key:'price_confirmation',level:divergence?'CONFLICT':supportive?'STRONG':'NEUTRAL'},
                {key:'money_flow',level:ev.money_added>=5000?'STRONG':'MEDIUM'},
                {key:'timing',level:(result.primary==='LATE_STEAM'||result.primary==='EARLY_POSITION')?'STRONG':'MEDIUM'},
                {key:'cross_market',level:'UNAVAILABLE'},{key:'poly',level:'UNAVAILABLE'},{key:'risk',level:divergence?'CONFLICT':risks.length?'MEDIUM':'NEUTRAL'}
            ],why:why,risks:risks,
            details:{primary_class:result.primary,decision_window:result.key,source_market:'1X2',source_selection:code,engine_key:'live_read_only_v2',engine_version:'part4-browser-parity-1.0.0'},
            current_state:'LIVE_READ_ONLY',live_preview:true
        };
    }
    function rowVolume(match) {
        var o=match&&match.odds?match.odds:match||{}; return num(o.Volume)||0;
    }
    function loadLiveFallback(area) {
        var c=t(), now=Date.now();
        liveFallbackMode=true;
        if(liveFallbackCache&&now-liveFallbackCacheTs<LIVE_CACHE_TTL){cards=liveFallbackCache.slice();refreshChrome();return Promise.resolve();}
        area.innerHTML='<div class="a2m-loading">' + esc(lang()==='tr'?'Canlı V2 snapshotları analiz ediliyor…':'Analysing live V2 snapshots…') + '</div>';
        return fetch('/api/matches?market=moneyway_1x2&date_filter=today_future&bulk=1',{headers:currentLicenseHeaders()})
            .then(function(r){if(!r.ok)throw new Error('MATCHES');return r.json();})
            .then(function(payload){
                var matches=Array.isArray(payload.matches)?payload.matches:[];
                matches.sort(function(a,b){return rowVolume(b)-rowVolume(a);});
                matches=matches.slice(0,18);
                return Promise.all(matches.map(function(match){
                    var home=match.home_team||'',away=match.away_team||'';
                    var url='/api/match/history?home='+encodeURIComponent(home)+'&away='+encodeURIComponent(away)+'&market=moneyway_1x2';
                    return fetch(url,{headers:currentLicenseHeaders()}).then(function(r){return r.ok?r.json():{history:[]};}).then(function(data){return {match:match,history:Array.isArray(data.history)?data.history:[]};}).catch(function(){return {match:match,history:[]};});
                }));
            })
            .then(function(items){
                var out=[];
                items.forEach(function(item){
                    if(!item.history.length)return;
                    var kickoff=parseTime(item.match.date||item.match.kickoff_utc||item.match.match_date);
                    ['1','X','2'].forEach(function(code){
                        var points=item.history.map(function(row){return historyPoint(row,code);}).filter(function(p){return p.ts!=null&&p.odds!=null&&p.market_volume!=null;});
                        var result=classify(points,kickoff), card=result&&buildLiveCard(item.match,code,result); if(card)out.push(card);
                    });
                });
                var priority={UZAK_DUR:3,IZLE:2,FIRSAT:1};
                out.sort(function(a,b){return (priority[b.state]||0)-(priority[a.state]||0);});
                cards=out; liveFallbackCache=out.slice(); liveFallbackCacheTs=Date.now(); refreshChrome();
            })
            .catch(function(){area.innerHTML='<div class="a2m"><div class="a2m-error">'+esc(c.loadFail)+'</div></div>';});
    }

    function loadSignals() {
        var area=document.getElementById('trendsContentArea'),c=t(); if(!area)return;
        area.innerHTML='<div class="a2m-loading">Loading Analyses V2…</div>';
        fetch('/api/analysis-v2/signals?scope='+encodeURIComponent(activeScope)+'&limit=100',{headers:currentLicenseHeaders()})
            .then(function(r){if(r.status===401||r.status===403)throw new Error('AUTH');return r.json();})
            .then(function(payload){
                if(!payload.available){
                    if(payload.reason==='V2_LEDGER_NOT_DEPLOYED'&&(activeScope==='active'||activeScope==='all')) return loadLiveFallback(area);
                    area.innerHTML='<div class="a2m"><div class="a2m-error">'+esc(payload.reason==='V2_LEDGER_NOT_DEPLOYED'?c.ledgerWaiting:c.loadFail)+'</div></div>';return;
                }
                liveFallbackMode=false; cards=Array.isArray(payload.signals)?payload.signals:[]; refreshChrome();
            })
            .catch(function(){area.innerHTML='<div class="a2m"><div class="a2m-error">'+esc(c.loadFail)+'</div></div>';});
    }

    window.analysisV2SetScope=function(scope){
        if(liveFallbackMode&&scope==='history')return;
        activeScope=(scope==='history'||scope==='all')?scope:'active';activeState='ALL';loadSignals();
    };
    window.analysisV2SetState=function(state){activeState=['FIRSAT','IZLE','UZAK_DUR'].indexOf(state)!==-1?state:'ALL';refreshChrome();};
    window.openAnalysisV2Modal=function(){
        if(window.userPlan&&window.userPlan!=='pro'){
            var message=lang()==='tr'?'Analizler V2 PRO üyelikte aktif. PRO paketine yükseltmek ister misiniz?':'Analyses V2 is available on PRO. Would you like to upgrade?';
            if(window.confirm(message))window.location.href='/pricing';return;
        }
        var overlay=document.getElementById('trendsModalOverlay'),title=document.getElementById('trendsModalTitle'),subtitle=document.getElementById('trendsModalSubtitle'),body=document.querySelector('.trends-modal-body');
        if(!overlay||!body)return;
        body.classList.remove('sidebar-mode','mobile-article-open');body.classList.add('analysis-v2-mode');
        if(title)title.textContent=t().title;if(subtitle)subtitle.textContent=t().subtitle;
        overlay.style.display='flex';document.body.style.overflow='hidden';activeScope='active';activeState='ALL';loadSignals();
    };
    function updateLabels(){
        setButtonLabel(document.getElementById('analysisV2Btn'));setButtonLabel(document.getElementById('analysisV2BtnMobile'));
        var body=document.querySelector('.trends-modal-body');if(body&&body.classList.contains('analysis-v2-mode')){var title=document.getElementById('trendsModalTitle'),subtitle=document.getElementById('trendsModalSubtitle');if(title)title.textContent=t().title;if(subtitle)subtitle.textContent=t().subtitle;refreshChrome();}
    }
    function init(){wrapExistingModalFunctions();installButtons();window.addEventListener('i18n:change',updateLabels);}
    if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
