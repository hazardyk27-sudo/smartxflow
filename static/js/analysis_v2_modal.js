(function () {
    'use strict';

    var installed = false;
    var wrapped = false;
    var loading = false;
    var cards = [];
    var activeEngine = 'ALL';
    var activeDate = 'ALL';

    var ENGINES = [
        { key:'underdog_pressure_v1', endpoint:'/api/underdog-pressure', label:'Underdog Pressure V2', tone:'watch' },
        { key:'confirmed_money_v1', endpoint:'/api/confirmed-money', label:'Confirmed Money V2', tone:'op' },
        { key:'early_money_lock_v1', endpoint:'/api/early-money-lock', label:'Early Money Lock V2', tone:'watch' },
        { key:'price_money_divergence_v1', endpoint:'/api/fake-sharp', label:'Price–Money Divergence', tone:'avoid' }
    ];

    var COPY = {
        en: {
            button:'Analyses V2', title:'Analyses V2', subtitle:'V1 engines · smarter validation · clear playable decision',
            intro:'V2 starts from the existing Analyses engines. Every card tells you which engine found the match, which side triggered it and why it is being watched.',
            all:'All', noData:'No engine-first V2 candidate in this view.', loadFail:'V2 engine signals could not be loaded.',
            watch:'WATCH', avoid:'AVOID', candidate:'V2 CANDIDATE', tracked:'TRACKED SIDE', noBet:'NO BET',
            pct:'Money', volume:'Volume', move:'Odds move', engine:'Engine', historical:'Historical sweet spot · forward validation pending',
            underdogReason:'Underdog Pressure triggered this side. V2 does not auto-bet a longshot ML; DNB/DC or a validated market selector must confirm it first.',
            cmReason:'Confirmed Money triggered this side: concentrated money plus price shortening.',
            emlReason:'Early Money Lock triggered this side with persistent early money. Historical rows may not contain the true trigger price, so V2 keeps it provisional.',
            divReason:'Money and price disagree. This is a warning, never an automatic opposite-side bet.',
            source:'Source signal', today:'Today', tomorrow:'Tomorrow', unknownDate:'Date unknown'
        },
        tr: {
            button:'Analizler V2', title:'Analizler V2', subtitle:'V1 motorları · daha akıllı doğrulama · net oynanabilir karar',
            intro:'V2 mevcut Analizler motorlarından başlar. Her kart hangi motorun maçı bulduğunu, hangi yönün tetiklendiğini ve neden izlediğimizi açıkça gösterir.',
            all:'Tümü', noData:'Bu görünümde engine-first V2 adayı yok.', loadFail:'V2 motor sinyalleri yüklenemedi.',
            watch:'İZLE', avoid:'UZAK DUR', candidate:'V2 ADAYI', tracked:'TAKİP EDİLEN YÖN', noBet:'OYNAME',
            pct:'Para', volume:'Hacim', move:'Oran hareketi', engine:'Motor', historical:'Tarihsel güçlü bölge · forward doğrulama bekliyor',
            underdogReason:'Underdog Pressure bu yönü tetikledi. V2 yüksek oranlı ML’yi otomatik oynatmaz; gerçek DNB/DC veya doğrulanmış market seçimi gerekir.',
            cmReason:'Confirmed Money bu yönü tetikledi: yoğun para ile fiyat kısalması aynı yönde.',
            emlReason:'Early Money Lock kalıcı erken para akışıyla bu yönü tetikledi. Eski kayıtlarda gerçek trigger oranı güvenilir olmadığı için V2 bunu provisional tutar.',
            divReason:'Para ile fiyat birbiriyle çelişiyor. Bu bir uyarıdır; otomatik olarak karşı taraf bahsi üretmez.',
            source:'Kaynak sinyal', today:'Bugün', tomorrow:'Yarın', unknownDate:'Tarih bilinmiyor'
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
        var s = String(value).replace(/[£€$%\s]/g,'').trim();
        if (!s) return null;
        if (s.indexOf(',') !== -1 && s.indexOf('.') === -1) {
            if (/^-?\d+,\d{1,2}$/.test(s)) s = s.replace(',','.');
            else s = s.replace(/,/g,'');
        } else if (s.indexOf(',') !== -1) s = s.replace(/,/g,'');
        var n = Number(s);
        return isFinite(n) ? n : null;
    }
    function fmtOdds(value) { var n=num(value); return n==null?'—':n.toFixed(2); }
    function fmtPct(value) { var n=num(value); return n==null?'—':n.toFixed(Math.abs(n%1)<0.001?0:1)+'%'; }
    function fmtMoney(value) {
        var n=num(value); if(n==null)return '—'; var a=Math.abs(n),body;
        if(a>=1000000)body=(a/1000000).toFixed(a>=10000000?0:1)+'M';
        else if(a>=1000)body=(a/1000).toFixed(a>=100000?0:1)+'K';
        else body=a.toFixed(a>=100?0:1);
        return (n<0?'−':'')+'£'+body;
    }
    function currentLicenseHeaders() {
        var key='';
        try { key=window.userLicenseKey||localStorage.getItem('smartxflow_web_license')||''; } catch(e) {}
        return key?{'X-License-Key':key}:{};
    }
    function first(row, keys) {
        for(var i=0;i<keys.length;i++) if(row[keys[i]]!==undefined && row[keys[i]]!==null && row[keys[i]]!=='') return row[keys[i]];
        return null;
    }
    function dateRaw(row) { return String(first(row,['match_date','date','kickoff_utc'])||'').trim(); }
    function parseDate(value) {
        if(!value)return null;
        var direct=Date.parse(value); if(!isNaN(direct))return new Date(direct);
        var m=String(value).match(/^(\d{1,2})[.\/-](\d{1,2})[.\/-](\d{4})/);
        if(m)return new Date(Number(m[3]),Number(m[2])-1,Number(m[1]));
        var mon={jan:0,feb:1,mar:2,apr:3,may:4,jun:5,jul:6,aug:7,sep:8,oct:9,nov:10,dec:11};
        var e=String(value).match(/^(\d{1,2})\.([A-Za-z]{3})/);
        if(e&&mon[e[2].toLowerCase()]!==undefined)return new Date(new Date().getFullYear(),mon[e[2].toLowerCase()],Number(e[1]));
        return null;
    }
    function dateKey(row) {
        var d=parseDate(dateRaw(row));
        if(!d)return 'UNKNOWN';
        return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');
    }
    function dateLabel(key) {
        if(key==='ALL')return t().all;
        if(key==='UNKNOWN')return t().unknownDate;
        var d=new Date(key+'T12:00:00');
        var now=new Date(), today=new Date(now.getFullYear(),now.getMonth(),now.getDate());
        var diff=Math.round((new Date(d.getFullYear(),d.getMonth(),d.getDate())-today)/86400000);
        if(diff===0)return t().today;
        if(diff===1)return t().tomorrow;
        return new Intl.DateTimeFormat(lang()==='tr'?'tr-TR':'en-GB',{day:'2-digit',month:'short'}).format(d);
    }
    function cleanResult(row) { return String(row.result||'').trim().toUpperCase(); }

    function normalize(engine, row) {
        var c=t(), odds=null,currentOdds=null,pct=null,volume=null,amount=null,move=null,state='IZLE',tone='watch',reason='',label=c.watch;
        var selection=String(row.selection_code||row.selection||'').toUpperCase();
        if(engine.key==='underdog_pressure_v1') {
            odds=num(row.odds); currentOdds=num(row.current_odds); pct=num(row.current_pct!=null?row.current_pct:row.pct);
            volume=num(row.current_volume!=null?row.current_volume:row.volume); amount=num(row.current_amt!=null?row.current_amt:row.amt);
            reason=c.underdogReason; label=c.tracked;
        } else if(engine.key==='confirmed_money_v1') {
            odds=num(row.odds_now); currentOdds=num(row.current_odds!=null?row.current_odds:row.odds_now); pct=num(row.current_pct!=null?row.current_pct:row.pct_now);
            volume=num(row.current_volume!=null?row.current_volume:row.volume_now); amount=num(row.amount);
            move=num(row.odds_drop_pct); reason=c.cmReason; label=c.candidate;
        } else if(engine.key==='early_money_lock_v1') {
            odds=null; currentOdds=null; pct=num(row.pct_now); volume=num(row.volume_now); amount=num(row.amt_now);
            reason=c.emlReason; label=c.candidate;
        } else {
            odds=num(row.odds_now); currentOdds=num(row.current_odds!=null?row.current_odds:row.odds_now); pct=num(row.current_pct!=null?row.current_pct:row.pct_now);
            volume=num(row.current_volume!=null?row.current_volume:row.volume_now); amount=num(row.amount);
            move=num(row.odds_rise_pct); state='UZAK_DUR'; tone='avoid'; reason=c.divReason; label=c.noBet;
        }
        var sweet=engine.key==='confirmed_money_v1' && pct!=null && pct>=85 && pct<90 && move!=null && move>=5 && move<10;
        var result=cleanResult(row);
        return {
            id:engine.key+':'+String(row.id||row.match_key||Math.random()),
            engine:engine.key, engineLabel:engine.label, engineTone:engine.tone,
            match:(row.home_team||'')+' — '+(row.away_team||''), home:row.home_team||'', away:row.away_team||'', league:row.league||'',
            rawDate:dateRaw(row), dateKey:dateKey(row), selection:selection, triggerOdds:odds, currentOdds:currentOdds,
            pct:pct, volume:volume, amount:amount, move:move, state:state, tone:tone, statusLabel:label,
            reason:reason, sweet:sweet, result:result, selectionLabel:row.selection_label||'', sourceId:row.id||'',
            hoursBefore:num(row.hours_before_kickoff)
        };
    }

    function availableDates() {
        var seen={},list=[];
        cards.forEach(function(card){if(!seen[card.dateKey]){seen[card.dateKey]=true;list.push(card.dateKey);}});
        list.sort(function(a,b){if(a==='UNKNOWN')return 1;if(b==='UNKNOWN')return -1;return a.localeCompare(b);});
        return list;
    }
    function chooseDefaultDate() {
        var dates=availableDates(); if(!dates.length){activeDate='ALL';return;}
        var now=new Date(), today=now.getFullYear()+'-'+String(now.getMonth()+1).padStart(2,'0')+'-'+String(now.getDate()).padStart(2,'0');
        for(var i=0;i<dates.length;i++) if(dates[i]!=='UNKNOWN'&&dates[i]>=today){activeDate=dates[i];return;}
        activeDate=dates[dates.length-1];
    }
    function visibleCards() {
        return cards.filter(function(card){
            if(activeEngine!=='ALL'&&card.engine!==activeEngine)return false;
            if(activeDate!=='ALL'&&card.dateKey!==activeDate)return false;
            return true;
        });
    }
    function engineControls() {
        var html='<div class="a2m-states"><button class="a2m-btn'+(activeEngine==='ALL'?' active':'')+'" onclick="analysisV2SetEngine(\'ALL\')">'+esc(t().all)+'</button>';
        ENGINES.forEach(function(e){html+='<button class="a2m-btn'+(activeEngine===e.key?' active':'')+'" onclick="analysisV2SetEngine(\''+esc(e.key)+'\')">'+esc(e.label)+'</button>';});
        return html+'</div>';
    }
    function dateControls() {
        var dates=availableDates(), html='<div class="a2m-tabs"><button class="a2m-btn'+(activeDate==='ALL'?' active':'')+'" onclick="analysisV2SetDate(\'ALL\')">'+esc(t().all)+'</button>';
        dates.slice(0,10).forEach(function(key){html+='<button class="a2m-btn'+(activeDate===key?' active':'')+'" onclick="analysisV2SetDate(\''+esc(key)+'\')">'+esc(dateLabel(key))+'</button>';});
        return html+'</div>';
    }
    function controlsHtml() { return '<div class="a2m-controls" style="align-items:flex-start;flex-direction:column;gap:8px">'+dateControls()+engineControls()+'</div>'; }

    function metric(label,value) { return '<div class="a2m-metric"><span>'+esc(label)+'</span><strong>'+esc(value)+'</strong></div>'; }
    function cardHtml(card) {
        var c=t(), price=card.currentOdds!=null?card.currentOdds:card.triggerOdds;
        var pick=card.state==='UZAK_DUR'?c.noBet:(card.selection||'—')+(price!=null?' @'+fmtOdds(price):'');
        var moveText='—';
        if(card.engine==='confirmed_money_v1'&&card.move!=null)moveText='↓ '+card.move.toFixed(1)+'%';
        else if(card.engine==='price_money_divergence_v1'&&card.move!=null)moveText='↑ '+card.move.toFixed(1)+'%';
        else if(card.triggerOdds!=null&&card.currentOdds!=null)moveText=fmtOdds(card.triggerOdds)+' → '+fmtOdds(card.currentOdds);
        var why=card.reason+(card.sweet?' '+c.historical:'');
        var resultMeta=card.result?' · '+card.result:'';
        return '<article class="a2m-card '+esc(card.tone)+'">'+
            '<div class="a2m-card-top"><div><span class="a2m-state '+esc(card.tone)+'">'+esc(card.state==='UZAK_DUR'?c.avoid:c.watch)+'</span>'+
            '<div style="margin-top:7px;font-size:10px;font-weight:800;letter-spacing:.04em;color:#8ba0b2">'+esc(card.engineLabel)+'</div>'+
            '<div class="a2m-match">'+esc(card.match)+'</div><div class="a2m-meta">'+esc((card.league||'')+(card.rawDate?' · '+card.rawDate:'')+resultMeta)+'</div></div>'+
            '<div class="a2m-reco"><small>'+esc(card.statusLabel)+'</small><strong>'+esc(pick)+'</strong></div></div>'+
            '<div class="a2m-dir">'+esc(why)+'</div>'+
            '<div class="a2m-metrics">'+metric(c.pct,fmtPct(card.pct))+metric(c.volume,fmtMoney(card.volume))+metric(c.move,moveText)+metric(c.source,card.selection||'—')+'</div>'+
            '</article>';
    }
    function shellHtml() {
        var c=t();
        return '<div class="a2m"><div class="a2m-hero"><div><div class="a2m-kicker">ENGINE-FIRST V2</div><h3>'+esc(c.title)+'</h3><p>'+esc(c.intro)+'</p></div></div>'+controlsHtml()+'<div id="analysisV2List" class="a2m-list"></div></div>';
    }
    function render() {
        var area=document.getElementById('trendsContentArea'); if(!area)return;
        area.innerHTML=shellHtml();
        var list=document.getElementById('analysisV2List'),visible=visibleCards();
        if(!visible.length){list.innerHTML='<div class="a2m-empty"><strong>'+esc(t().noData)+'</strong></div>';return;}
        list.innerHTML=visible.map(cardHtml).join('');
    }

    function loadSignals() {
        if(loading)return; loading=true;
        var area=document.getElementById('trendsContentArea'); if(!area){loading=false;return;}
        area.innerHTML='<div class="a2m-loading">Loading Analyses V2…</div>';
        Promise.all(ENGINES.map(function(engine){
            return fetch(engine.endpoint,{headers:currentLicenseHeaders()})
                .then(function(r){if(r.status===401||r.status===403)throw new Error('AUTH');return r.json();})
                .then(function(payload){return {engine:engine,signals:Array.isArray(payload.signals)?payload.signals:[]};})
                .catch(function(){return {engine:engine,signals:[]};});
        })).then(function(batches){
            var out=[];
            batches.forEach(function(batch){batch.signals.forEach(function(row){out.push(normalize(batch.engine,row));});});
            out.sort(function(a,b){
                if(a.dateKey!==b.dateKey)return b.dateKey.localeCompare(a.dateKey);
                if(a.engine!==b.engine)return a.engine.localeCompare(b.engine);
                return String(a.match).localeCompare(String(b.match));
            });
            cards=out; chooseDefaultDate(); loading=false; render();
        }).catch(function(){loading=false;area.innerHTML='<div class="a2m"><div class="a2m-error">'+esc(t().loadFail)+'</div></div>';});
    }

    function removeMode(){var body=document.querySelector('.trends-modal-body');if(body)body.classList.remove('analysis-v2-mode');}
    function wrapExistingModalFunctions(){
        if(wrapped)return;wrapped=true;
        if(typeof window.openTrendsModal==='function'){var originalOpen=window.openTrendsModal;window.openTrendsModal=function(){removeMode();return originalOpen.apply(this,arguments);};}
        if(typeof window.closeTrendsModal==='function'){var originalClose=window.closeTrendsModal;window.closeTrendsModal=function(){removeMode();return originalClose.apply(this,arguments);};}
    }
    function setButtonLabel(button){if(!button)return;var label=button.querySelector('span[data-i18n], span:not(.analysis-active-badge)');if(label){label.removeAttribute('data-i18n');label.textContent=t().button;}}
    function installButtons(){
        if(installed)return;
        var desktopButtons=document.querySelectorAll('button.btn.btn-today.desktop-only'),desktopSource=null;
        for(var i=0;i<desktopButtons.length;i++)if((desktopButtons[i].getAttribute('onclick')||'').indexOf('_testGuardAnalysis')!==-1){desktopSource=desktopButtons[i];break;}
        if(desktopSource&&!document.getElementById('analysisV2Btn')){var desktop=desktopSource.cloneNode(true);desktop.id='analysisV2Btn';desktop.setAttribute('onclick','openAnalysisV2Modal()');desktop.removeAttribute('data-i18n');var badge=desktop.querySelector('.analysis-active-badge');if(badge)badge.remove();setButtonLabel(desktop);desktopSource.insertAdjacentElement('afterend',desktop);}
        var mobileButtons=document.querySelectorAll('#mobileOverflowMenu button'),mobileSource=null;
        for(var j=0;j<mobileButtons.length;j++)if((mobileButtons[j].getAttribute('onclick')||'').indexOf('_testGuardAnalysis')!==-1){mobileSource=mobileButtons[j];break;}
        if(mobileSource&&!document.getElementById('analysisV2BtnMobile')){var mobile=mobileSource.cloneNode(true);mobile.id='analysisV2BtnMobile';mobile.setAttribute('onclick','openAnalysisV2Modal(); closeMobileOverflow();');var mb=mobile.querySelector('.analysis-active-badge');if(mb)mb.remove();setButtonLabel(mobile);mobileSource.insertAdjacentElement('afterend',mobile);}
        installed=true;
    }

    window.analysisV2SetEngine=function(engine){activeEngine=ENGINES.some(function(e){return e.key===engine;})?engine:'ALL';render();};
    window.analysisV2SetDate=function(key){activeDate=key||'ALL';render();};
    window.openAnalysisV2Modal=function(){
        if(window.userPlan&&window.userPlan!=='pro'){var message=lang()==='tr'?'Analizler V2 PRO üyelikte aktif. PRO paketine yükseltmek ister misiniz?':'Analyses V2 is available on PRO. Would you like to upgrade?';if(window.confirm(message))window.location.href='/pricing';return;}
        var overlay=document.getElementById('trendsModalOverlay'),title=document.getElementById('trendsModalTitle'),subtitle=document.getElementById('trendsModalSubtitle'),body=document.querySelector('.trends-modal-body');
        if(!overlay||!body)return;
        body.classList.remove('sidebar-mode','mobile-article-open');body.classList.add('analysis-v2-mode');
        if(title)title.textContent=t().title;if(subtitle)subtitle.textContent=t().subtitle;
        overlay.style.display='flex';document.body.style.overflow='hidden';activeEngine='ALL';loadSignals();
    };
    function updateLabels(){setButtonLabel(document.getElementById('analysisV2Btn'));setButtonLabel(document.getElementById('analysisV2BtnMobile'));var body=document.querySelector('.trends-modal-body');if(body&&body.classList.contains('analysis-v2-mode'))render();}
    function init(){wrapExistingModalFunctions();installButtons();window.addEventListener('i18n:change',updateLabels);}
    if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();