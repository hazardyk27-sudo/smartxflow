(function () {
    'use strict';

    var installed = false;
    var wrapped = false;
    var loading = false;
    var cards = [];
    var activeEngine = 'ALL';
    var activeDate = 'ALL';
    var sourceHealth = {};
    var lastLoadAt = null;

    var ENGINES = [
        { key:'underdog_pressure_v1', endpoint:'/api/underdog-pressure', label:'Underdog Pressure V2', short:'Underdog', tone:'watch' },
        { key:'confirmed_money_v1', endpoint:'/api/confirmed-money', label:'Confirmed Money V2', short:'Confirmed', tone:'op' },
        { key:'early_money_lock_v1', endpoint:'/api/early-money-lock', label:'Early Money Lock V2', short:'Early Lock', tone:'watch' },
        { key:'price_money_divergence_v1', endpoint:'/api/fake-sharp', label:'Price–Money Divergence', short:'Divergence', tone:'avoid' }
    ];

    var COPY = {
        en: {
            button:'Analyses V2', title:'Analyses V2', subtitle:'V1 engines · calibrated validation · clear decision',
            intro:'Every card starts from a real V1 engine trigger. V2 keeps the original engine identity, adds validation context, and refuses to turn unvalidated research patterns into a bet.',
            all:'All', today:'Today', tomorrow:'Tomorrow', unknownDate:'Date unknown',
            noData:'No engine-first V2 candidate in this view.', noDataSub:'Try another day or engine filter.',
            loadFail:'V2 engine signals could not be loaded.', partial:'Some engine sources could not be loaded.',
            watch:'WATCH', avoid:'AVOID', candidate:'CANDIDATE', tracked:'TRACKED SIDE', noBet:'NO BET',
            pct:'Money', volume:'Volume', amount:'Amount', move:'Odds move', source:'Source',
            refresh:'Refresh', refreshed:'Updated', research:'Research zone', pending:'forward validation pending',
            underdogReason:'Underdog Pressure found this side. V2 does not auto-bet a longshot ML; a real DNB/DC or a separately validated market expression is required.',
            cmReason:'Confirmed Money found this side: concentrated money and price shortening triggered the source engine.',
            emlReason:'Early Money Lock found persistent early money. Legacy rows do not reliably preserve the trigger price, so the candidate stays provisional.',
            divReason:'Money and price disagree. This is a warning only; V2 never flips it into an automatic opposite-side bet.',
            invalidSkipped:'invalid rows skipped'
        },
        tr: {
            button:'Analizler V2', title:'Analizler V2', subtitle:'V1 motorları · kalibre doğrulama · net karar',
            intro:'Her kart gerçek bir V1 motor tetiklemesinden başlar. V2 motor kimliğini korur, doğrulama bağlamı ekler ve henüz doğrulanmamış araştırma bölgelerini otomatik bahse çevirmez.',
            all:'Tümü', today:'Bugün', tomorrow:'Yarın', unknownDate:'Tarih bilinmiyor',
            noData:'Bu görünümde engine-first V2 adayı yok.', noDataSub:'Başka bir gün veya motor filtresi deneyin.',
            loadFail:'V2 motor sinyalleri yüklenemedi.', partial:'Bazı motor kaynakları yüklenemedi.',
            watch:'İZLE', avoid:'UZAK DUR', candidate:'ADAY', tracked:'TAKİP EDİLEN YÖN', noBet:'OYNAME',
            pct:'Para', volume:'Hacim', amount:'Tutar', move:'Oran hareketi', source:'Kaynak',
            refresh:'Yenile', refreshed:'Güncellendi', research:'Araştırma bölgesi', pending:'forward doğrulama bekliyor',
            underdogReason:'Underdog Pressure bu yönü buldu. V2 yüksek oranlı ML’yi otomatik oynatmaz; gerçek DNB/DC veya ayrıca doğrulanmış bir market ifadesi gerekir.',
            cmReason:'Confirmed Money bu yönü buldu: yoğun para ve oran kısalması kaynak motoru tetikledi.',
            emlReason:'Early Money Lock kalıcı erken para akışını buldu. Eski kayıtlarda gerçek trigger oranı güvenilir saklanmadığı için aday provisional kalır.',
            divReason:'Para ile fiyat çelişiyor. Bu yalnızca uyarıdır; V2 otomatik olarak karşı taraf bahsi üretmez.',
            invalidSkipped:'geçersiz satır atlandı'
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
            if (/^-?\d+,\d{1,3}$/.test(s)) s = s.replace(',','.');
            else s = s.replace(/,/g,'');
        } else if (s.indexOf(',') !== -1) {
            s = s.replace(/,/g,'');
        }
        var n = Number(s);
        return isFinite(n) ? n : null;
    }
    function fmtOdds(value) { var n=num(value); return n==null?'—':n.toFixed(2); }
    function fmtPct(value) { var n=num(value); return n==null?'—':n.toFixed(Math.abs(n%1)<0.001?0:1)+'%'; }
    function fmtMoney(value) {
        var n=num(value); if(n==null)return '—';
        var a=Math.abs(n),body;
        if(a>=1000000)body=(a/1000000).toFixed(a>=10000000?0:1)+'M';
        else if(a>=1000)body=(a/1000).toFixed(a>=100000?0:1)+'K';
        else body=a.toFixed(a>=100?0:1);
        return (n<0?'−':'')+'£'+body;
    }
    function first(row, keys) {
        for(var i=0;i<keys.length;i++) {
            if(row && row[keys[i]]!==undefined && row[keys[i]]!==null && row[keys[i]]!=='') return row[keys[i]];
        }
        return null;
    }
    function currentLicenseHeaders() {
        var key='';
        try { key=window.userLicenseKey||localStorage.getItem('smartxflow_web_license')||''; } catch(e) {}
        return key?{'X-License-Key':key}:{};
    }
    function dateRaw(row) { return String(first(row,['match_date','date','kickoff_utc'])||'').trim(); }
    function inferMonthDay(day, month) {
        var now = new Date();
        var candidates = [now.getFullYear()-1, now.getFullYear(), now.getFullYear()+1].map(function(y){ return new Date(y,month,day,12,0,0); });
        candidates.sort(function(a,b){ return Math.abs(a-now)-Math.abs(b-now); });
        return candidates[0];
    }
    function parseDate(value) {
        if(!value)return null;
        var s=String(value).trim();
        var iso=s.match(/^(\d{4})-(\d{2})-(\d{2})/);
        if(iso)return new Date(Number(iso[1]),Number(iso[2])-1,Number(iso[3]),12,0,0);
        var dmy=s.match(/^(\d{1,2})[.\/-](\d{1,2})[.\/-](\d{4})/);
        if(dmy)return new Date(Number(dmy[3]),Number(dmy[2])-1,Number(dmy[1]),12,0,0);
        var mon={jan:0,feb:1,mar:2,apr:3,may:4,jun:5,jul:6,aug:7,sep:8,oct:9,nov:10,dec:11};
        var md=s.match(/^(\d{1,2})\.([A-Za-z]{3})/);
        if(md&&mon[md[2].toLowerCase()]!==undefined)return inferMonthDay(Number(md[1]),mon[md[2].toLowerCase()]);
        var direct=Date.parse(s);
        return isNaN(direct)?null:new Date(direct);
    }
    function keyFromDate(d) {
        if(!d || isNaN(d.getTime()))return 'UNKNOWN';
        return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');
    }
    function dateKey(row) { return keyFromDate(parseDate(dateRaw(row))); }
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
    function cleanResult(row) { return String(row && row.result || '').trim().toUpperCase(); }
    function rowTimestamp(row) {
        var raw=first(row,['last_updated_at','updated_at','created_at','trigger_at']);
        var ts=raw?Date.parse(raw):NaN;
        return isNaN(ts)?0:ts;
    }
    function stableKey(engine,row) {
        var matchKey=String(first(row,['match_key','match_id_hash'])||'').trim();
        var home=String(row.home_team||'').trim().toLowerCase();
        var away=String(row.away_team||'').trim().toLowerCase();
        var league=String(row.league||'').trim().toLowerCase();
        var selection=String(first(row,['selection_code','selection'])||'').trim().toUpperCase();
        return engine.key+'|'+(matchKey||[league,home,away,dateKey(row)].join('|'))+'|'+selection;
    }
    function validSourceRow(row) {
        var home=String(row&&row.home_team||'').trim(), away=String(row&&row.away_team||'').trim();
        var selection=String(first(row||{},['selection_code','selection'])||'').trim().toUpperCase();
        return !!(home&&away&&['1','X','2'].indexOf(selection)!==-1);
    }

    function normalize(engine,row) {
        var c=t(), triggerOdds=null,currentOdds=null,pct=null,volume=null,amount=null,move=null;
        var state='IZLE',tone='watch',reason='',label=c.watch,actionKind='WATCH';
        var selection=String(first(row,['selection_code','selection'])||'').toUpperCase();

        if(engine.key==='underdog_pressure_v1') {
            triggerOdds=num(row.odds); currentOdds=num(row.current_odds!=null?row.current_odds:row.odds);
            pct=num(row.current_pct!=null?row.current_pct:row.pct);
            volume=num(row.current_volume!=null?row.current_volume:row.volume);
            amount=num(row.current_amt!=null?row.current_amt:row.amt);
            reason=c.underdogReason; label=c.tracked; actionKind='TRACK';
            if(triggerOdds!=null&&currentOdds!=null&&triggerOdds>0)move=(triggerOdds-currentOdds)/triggerOdds*100;
        } else if(engine.key==='confirmed_money_v1') {
            triggerOdds=num(row.odds_now); currentOdds=num(row.current_odds!=null?row.current_odds:row.odds_now);
            pct=num(row.current_pct!=null?row.current_pct:row.pct_now);
            volume=num(row.current_volume!=null?row.current_volume:row.volume_now);
            amount=num(first(row,['amount','amt_now','current_amt']));
            move=num(row.odds_drop_pct);
            reason=c.cmReason; label=c.candidate; actionKind='CANDIDATE';
        } else if(engine.key==='early_money_lock_v1') {
            triggerOdds=null; currentOdds=null; pct=num(row.pct_now); volume=num(row.volume_now); amount=num(row.amt_now);
            reason=c.emlReason; label=c.candidate; actionKind='CANDIDATE';
        } else {
            triggerOdds=num(row.odds_now); currentOdds=num(row.current_odds!=null?row.current_odds:row.odds_now);
            pct=num(row.current_pct!=null?row.current_pct:row.pct_now);
            volume=num(row.current_volume!=null?row.current_volume:row.volume_now);
            amount=num(first(row,['amount','amt_now','current_amt']));
            move=num(row.odds_rise_pct);
            state='UZAK_DUR'; tone='avoid'; reason=c.divReason; label=c.noBet; actionKind='NO_BET';
        }

        var sweet=engine.key==='confirmed_money_v1' && pct!=null && pct>=85 && pct<90 && move!=null && move>=5 && move<10;
        var result=cleanResult(row);
        return {
            id:stableKey(engine,row), engine:engine.key, engineLabel:engine.label, engineTone:engine.tone,
            match:(row.home_team||'')+' — '+(row.away_team||''), home:row.home_team||'', away:row.away_team||'', league:row.league||'',
            rawDate:dateRaw(row), dateKey:dateKey(row), selection:selection,
            triggerOdds:triggerOdds,currentOdds:currentOdds,pct:pct,volume:volume,amount:amount,move:move,
            state:state,tone:tone,statusLabel:label,actionKind:actionKind,reason:reason,sweet:sweet,result:result,
            selectionLabel:row.selection_label||'',sourceId:row.id||'',hoursBefore:num(row.hours_before_kickoff),updatedAt:rowTimestamp(row)
        };
    }

    function dedupeBatch(engine,rows) {
        var map={}, invalid=0;
        (rows||[]).forEach(function(row){
            if(!validSourceRow(row)){invalid+=1;return;}
            var key=stableKey(engine,row),existing=map[key];
            if(!existing||rowTimestamp(row)>=rowTimestamp(existing))map[key]=row;
        });
        return { rows:Object.keys(map).map(function(k){return map[k];}), invalid:invalid };
    }
    function availableDates() {
        var seen={},list=[];
        cards.forEach(function(card){if(!seen[card.dateKey]){seen[card.dateKey]=true;list.push(card.dateKey);}});
        list.sort(function(a,b){if(a==='UNKNOWN')return 1;if(b==='UNKNOWN')return -1;return b.localeCompare(a);});
        return list;
    }
    function chooseDefaultDate(force) {
        var dates=availableDates();
        if(!dates.length){activeDate='ALL';return;}
        if(!force && activeDate!=='ALL' && dates.indexOf(activeDate)!==-1)return;
        var now=new Date(),today=keyFromDate(now);
        if(dates.indexOf(today)!==-1){activeDate=today;return;}
        var future=dates.filter(function(k){return k!=='UNKNOWN'&&k>today;}).sort();
        if(future.length){activeDate=future[0];return;}
        var past=dates.filter(function(k){return k!=='UNKNOWN'&&k<today;}).sort().reverse();
        activeDate=past.length?past[0]:'ALL';
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
        ENGINES.forEach(function(e){html+='<button class="a2m-btn'+(activeEngine===e.key?' active':'')+'" onclick="analysisV2SetEngine(\''+e.key+'\')">'+esc(e.label)+'</button>';});
        return html+'</div>';
    }
    function dateControls() {
        var dates=availableDates(),html='<div class="a2m-tabs"><button class="a2m-btn'+(activeDate==='ALL'?' active':'')+'" onclick="analysisV2SetDate(\'ALL\')">'+esc(t().all)+'</button>';
        dates.slice(0,14).forEach(function(key){html+='<button class="a2m-btn'+(activeDate===key?' active':'')+'" onclick="analysisV2SetDate(\''+key+'\')">'+esc(dateLabel(key))+'</button>';});
        return html+'</div>';
    }
    function sourceHealthHtml() {
        var c=t(), ok=0, fail=0, skipped=0, details=[];
        ENGINES.forEach(function(e){
            var h=sourceHealth[e.key]||{};
            if(h.ok)ok+=1;else if(h.loaded)fail+=1;
            skipped+=Number(h.invalid||0);
            if(h.loaded&&!h.ok)details.push(e.short+': '+(h.error||'error'));
        });
        var status=(fail?c.partial:(ok===ENGINES.length?(ok+'/'+ENGINES.length+' sources'):(ok+'/'+ENGINES.length+' sources')));
        if(lang()==='tr'&&!fail)status=ok+'/'+ENGINES.length+' kaynak';
        var extra=skipped?(' · '+skipped+' '+c.invalidSkipped):'';
        return '<div style="margin:0 0 10px;color:'+(fail?'#d6a45c':'#7d8a94')+';font-size:10px">'+esc(status+extra)+(details.length?' · '+esc(details.join(' | ')):'')+'</div>';
    }
    function controlsHtml() {
        return '<div class="a2m-controls" style="align-items:flex-start;flex-direction:column;gap:8px">'+dateControls()+engineControls()+'</div>';
    }
    function metric(label,value) { return '<div class="a2m-metric"><span>'+esc(label)+'</span><strong>'+esc(value)+'</strong></div>'; }
    function actionText(card) {
        var c=t(),price=card.currentOdds!=null?card.currentOdds:card.triggerOdds;
        if(card.actionKind==='NO_BET')return c.noBet;
        var side=(card.selection||'—')+(price!=null?' @'+fmtOdds(price):'');
        return side;
    }
    function moveText(card) {
        if(card.move!=null) {
            if(card.engine==='price_money_divergence_v1')return '↑ '+Math.abs(card.move).toFixed(1)+'%';
            if(card.engine==='confirmed_money_v1')return '↓ '+Math.abs(card.move).toFixed(1)+'%';
            return (card.move>=0?'↓ ':'↑ ')+Math.abs(card.move).toFixed(1)+'%';
        }
        if(card.triggerOdds!=null&&card.currentOdds!=null)return fmtOdds(card.triggerOdds)+' → '+fmtOdds(card.currentOdds);
        return '—';
    }
    function cardHtml(card) {
        var c=t(),resultMeta=card.result?' · '+card.result:'',research='';
        if(card.sweet)research='<div style="margin-top:8px;color:#c7a45d;font-size:10px;font-weight:700">'+esc(c.research)+': 85–89.9% + 5–10% · '+esc(c.pending)+'</div>';
        return '<article class="a2m-card '+esc(card.tone)+'">'+
            '<div class="a2m-card-top"><div><span class="a2m-state '+esc(card.tone)+'">'+esc(card.state==='UZAK_DUR'?c.avoid:c.watch)+'</span>'+
            '<div style="margin-top:7px;font-size:10px;font-weight:800;letter-spacing:.04em;color:#8ba0b2">'+esc(card.engineLabel)+'</div>'+
            '<div class="a2m-match">'+esc(card.match)+'</div><div class="a2m-meta">'+esc((card.league||'')+(card.rawDate?' · '+card.rawDate:'')+resultMeta)+'</div></div>'+
            '<div class="a2m-reco"><small>'+esc(card.statusLabel)+'</small><strong>'+esc(actionText(card))+'</strong></div></div>'+
            '<div class="a2m-dir">'+esc(card.reason)+'</div>'+research+
            '<div class="a2m-metrics">'+metric(c.pct,fmtPct(card.pct))+metric(c.volume,fmtMoney(card.volume))+metric(c.amount,fmtMoney(card.amount))+metric(c.move,moveText(card))+'</div>'+
            '</article>';
    }
    function shellHtml() {
        var c=t(),refreshText=lastLoadAt?(c.refreshed+' '+new Intl.DateTimeFormat(lang()==='tr'?'tr-TR':'en-GB',{hour:'2-digit',minute:'2-digit',second:'2-digit'}).format(lastLoadAt)):'';
        return '<div class="a2m"><div class="a2m-hero"><div><div class="a2m-kicker">ENGINE-FIRST V2</div><h3>'+esc(c.title)+'</h3><p>'+esc(c.intro)+'</p></div>'+ 
            '<button class="a2m-btn" type="button" onclick="analysisV2Reload()">'+esc(c.refresh)+'</button></div>'+sourceHealthHtml()+controlsHtml()+
            (refreshText?'<div style="margin:8px 0;color:#66727d;font-size:9px">'+esc(refreshText)+'</div>':'')+'<div id="analysisV2List" class="a2m-list"></div></div>';
    }
    function render() {
        var area=document.getElementById('trendsContentArea'); if(!area)return;
        area.innerHTML=shellHtml();
        var list=document.getElementById('analysisV2List'),visible=visibleCards();
        if(!visible.length){list.innerHTML='<div class="a2m-empty"><strong>'+esc(t().noData)+'</strong><span>'+esc(t().noDataSub)+'</span></div>';return;}
        list.innerHTML=visible.map(cardHtml).join('');
    }

    function fetchEngine(engine) {
        var controller=typeof AbortController!=='undefined'?new AbortController():null;
        var timer=controller?setTimeout(function(){controller.abort();},12000):null;
        var options={headers:currentLicenseHeaders()};
        if(controller)options.signal=controller.signal;
        return fetch(engine.endpoint,options).then(function(r){
            if(timer)clearTimeout(timer);
            if(!r.ok)throw new Error('HTTP_'+r.status);
            return r.json();
        }).then(function(payload){
            if(!payload||!Array.isArray(payload.signals))throw new Error('INVALID_PAYLOAD');
            var deduped=dedupeBatch(engine,payload.signals);
            sourceHealth[engine.key]={loaded:true,ok:true,count:deduped.rows.length,invalid:deduped.invalid,error:''};
            return deduped.rows.map(function(row){return normalize(engine,row);});
        }).catch(function(err){
            if(timer)clearTimeout(timer);
            sourceHealth[engine.key]={loaded:true,ok:false,count:0,invalid:0,error:String(err&&err.message||err||'LOAD_FAILED')};
            return [];
        });
    }
    function loadSignals(forceDate) {
        if(loading)return;
        loading=true; sourceHealth={};
        var area=document.getElementById('trendsContentArea');
        if(!area){loading=false;return;}
        area.innerHTML='<div class="a2m-loading">Loading Analyses V2…</div>';
        Promise.all(ENGINES.map(fetchEngine)).then(function(groups){
            var out=[];
            groups.forEach(function(group){out=out.concat(group);});
            out.sort(function(a,b){
                if(a.dateKey!==b.dateKey)return b.dateKey.localeCompare(a.dateKey);
                if(a.engine!==b.engine)return a.engine.localeCompare(b.engine);
                if(a.match!==b.match)return String(a.match).localeCompare(String(b.match));
                return String(a.selection).localeCompare(String(b.selection));
            });
            cards=out; chooseDefaultDate(!!forceDate); lastLoadAt=new Date(); loading=false; render();
        }).catch(function(){
            loading=false;area.innerHTML='<div class="a2m"><div class="a2m-error">'+esc(t().loadFail)+'</div></div>';
        });
    }

    function removeMode(){var body=document.querySelector('.trends-modal-body');if(body)body.classList.remove('analysis-v2-mode');}
    function wrapExistingModalFunctions(){
        if(wrapped)return;wrapped=true;
        if(typeof window.openTrendsModal==='function'){var originalOpen=window.openTrendsModal;window.openTrendsModal=function(){removeMode();return originalOpen.apply(this,arguments);};}
        if(typeof window.closeTrendsModal==='function'){var originalClose=window.closeTrendsModal;window.closeTrendsModal=function(){removeMode();return originalClose.apply(this,arguments);};}
    }
    function setButtonLabel(button){
        if(!button)return;
        var label=button.querySelector('span[data-i18n], span:not(.analysis-active-badge)');
        if(label){label.removeAttribute('data-i18n');label.textContent=t().button;}
    }
    function installButtons(){
        if(installed)return;
        var desktopButtons=document.querySelectorAll('button.btn.btn-today.desktop-only'),desktopSource=null;
        for(var i=0;i<desktopButtons.length;i++)if((desktopButtons[i].getAttribute('onclick')||'').indexOf('_testGuardAnalysis')!==-1){desktopSource=desktopButtons[i];break;}
        if(desktopSource&&!document.getElementById('analysisV2Btn')){
            var desktop=desktopSource.cloneNode(true);desktop.id='analysisV2Btn';desktop.setAttribute('onclick','openAnalysisV2Modal()');desktop.removeAttribute('data-i18n');
            var badge=desktop.querySelector('.analysis-active-badge');if(badge)badge.remove();setButtonLabel(desktop);desktopSource.insertAdjacentElement('afterend',desktop);
        }
        var mobileButtons=document.querySelectorAll('#mobileOverflowMenu button'),mobileSource=null;
        for(var j=0;j<mobileButtons.length;j++)if((mobileButtons[j].getAttribute('onclick')||'').indexOf('_testGuardAnalysis')!==-1){mobileSource=mobileButtons[j];break;}
        if(mobileSource&&!document.getElementById('analysisV2BtnMobile')){
            var mobile=mobileSource.cloneNode(true);mobile.id='analysisV2BtnMobile';mobile.setAttribute('onclick','openAnalysisV2Modal(); closeMobileOverflow();');
            var mb=mobile.querySelector('.analysis-active-badge');if(mb)mb.remove();setButtonLabel(mobile);mobileSource.insertAdjacentElement('afterend',mobile);
        }
        installed=true;
    }

    window.analysisV2SetEngine=function(engine){activeEngine=ENGINES.some(function(e){return e.key===engine;})?engine:'ALL';render();};
    window.analysisV2SetDate=function(key){activeDate=key||'ALL';render();};
    window.analysisV2Reload=function(){loadSignals(false);};
    window.openAnalysisV2Modal=function(){
        if(window.userPlan&&window.userPlan!=='pro'){
            var message=lang()==='tr'?'Analizler V2 PRO üyelikte aktif. PRO paketine yükseltmek ister misiniz?':'Analyses V2 is available on PRO. Would you like to upgrade?';
            if(window.confirm(message))window.location.href='/pricing';return;
        }
        var overlay=document.getElementById('trendsModalOverlay'),title=document.getElementById('trendsModalTitle'),subtitle=document.getElementById('trendsModalSubtitle'),body=document.querySelector('.trends-modal-body');
        if(!overlay||!body)return;
        body.classList.remove('sidebar-mode','mobile-article-open');body.classList.add('analysis-v2-mode');
        if(title)title.textContent=t().title;if(subtitle)subtitle.textContent=t().subtitle;
        overlay.style.display='flex';document.body.style.overflow='hidden';activeEngine='ALL';activeDate='ALL';loadSignals(true);
    };
    function updateLabels(){
        setButtonLabel(document.getElementById('analysisV2Btn'));setButtonLabel(document.getElementById('analysisV2BtnMobile'));
        var body=document.querySelector('.trends-modal-body');if(body&&body.classList.contains('analysis-v2-mode'))render();
    }
    function init(){wrapExistingModalFunctions();installButtons();window.addEventListener('i18n:change',updateLabels);}
    if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
