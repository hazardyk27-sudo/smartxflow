(function(){async function loadAllAlarms(forceRefresh=false){const body=document.getElementById('alarmsList');body.innerHTML='<div class="alarms-loading">Alarmlar yukleniyor...</div>';try{const data=await fetchAlarmsBatch(forceRefresh);const rawSharp=data.sharp||[];const rawBigmoney=data.bigmoney||[];const rawVolumeshock=data.volumeshock||[];const rawDropping=data.dropping||[];const rawPublicmove=data.publicmove||[];const rawVolumeleader=data.volumeleader||[];const rawMim=data.mim||[];alarmsDataByType.sharp=rawSharp.filter(isMatchYesterdayOrLater);alarmsDataByType.bigmoney=rawBigmoney.filter(isMatchYesterdayOrLater);alarmsDataByType.volumeshock=rawVolumeshock.filter(isMatchYesterdayOrLater);alarmsDataByType.dropping=rawDropping.filter(isMatchYesterdayOrLater);alarmsDataByType.publicmove=rawPublicmove.filter(isMatchYesterdayOrLater);alarmsDataByType.volumeleader=rawVolumeleader.filter(isMatchYesterdayOrLater);alarmsDataByType.mim=rawMim.filter(isMatchYesterdayOrLater);const sharpWithType=alarmsDataByType.sharp.map(a=>({...a,_type:'sharp'}));const bigmoneyWithType=alarmsDataByType.bigmoney.map(a=>({...a,_type:'bigmoney'}));const volumeshockWithType=alarmsDataByType.volumeshock.map(a=>({...a,_type:'volumeshock'}));const droppingWithType=alarmsDataByType.dropping.map(a=>({...a,_type:'dropping'}));const publicmoveWithType=alarmsDataByType.publicmove.map(a=>({...a,_type:'publicmove'}));const volumeleaderWithType=alarmsDataByType.volumeleader.map(a=>({...a,_type:'volumeleader'}));const mimWithType=alarmsDataByType.mim.map(a=>({...a,_type:'mim'}));allAlarmsData=[...sharpWithType,...bigmoneyWithType,...volumeshockWithType,...droppingWithType,...publicmoveWithType,...volumeleaderWithType,...mimWithType];allAlarmsData.sort((a,b)=>{const dateA=parseAlarmDate(a.trigger_at||a.event_time||a.created_at);const dateB=parseAlarmDate(b.trigger_at||b.event_time||b.created_at);return dateB-dateA;});groupedAlarmsData=groupAlarmsByMatch(allAlarmsData);updateAlarmCounts();updateDateFilterCounts();alarmsDisplayCount=10;const labelEl=document.getElementById('dateLabelDisplay');if(labelEl){labelEl.textContent=dateFilterLabels[currentAlarmDateFilter]||_t('app.flt.all','Tümü');}
renderAlarmsList(currentAlarmFilter);}catch(error){console.error('Alarm yukleme hatasi:',error);body.innerHTML='<div class="alarms-empty"><p>Alarmlar yuklenirken hata olustu.</p></div>';}}
function updateAlarmCounts(){const badge=document.getElementById('alarmsBadge');const mobileBadge=document.getElementById('mobileAlarmBadge');const filteredGroups=groupedAlarmsData.filter(g=>{if(currentAlarmDateFilter==='all'){const matchDateStr=g.match_date||g.fixture_date||getMatchDateFromAlarm(g.latestAlarm);if(!matchDateStr)return true;const{todayStr}=getDateFilterStrings();return matchDateStr>=todayStr;}
return true;});const totalCount=filteredGroups.length;if(badge)badge.textContent=totalCount;if(mobileBadge)mobileBadge.textContent=totalCount;const typeCounts={sharp:0,bigmoney:0,volumeshock:0,dropping:0,publicmove:0,volumeleader:0,mim:0};filteredGroups.forEach(g=>{if(typeCounts.hasOwnProperty(g.type))typeCounts[g.type]++;});const countAll=document.getElementById('countAll');const countSharp=document.getElementById('countSharp');const countBigmoney=document.getElementById('countBigmoney');const countVolumeshock=document.getElementById('countVolumeshock');const countDropping=document.getElementById('countDropping');const countPublicmove=document.getElementById('countPublicmove');const countVolumeleader=document.getElementById('countVolumeleader');const countMim=document.getElementById('countMim');if(countAll)countAll.textContent=totalCount;if(countSharp)countSharp.textContent=typeCounts.sharp;if(countBigmoney)countBigmoney.textContent=typeCounts.bigmoney;if(countVolumeshock)countVolumeshock.textContent=typeCounts.volumeshock;if(countDropping)countDropping.textContent=typeCounts.dropping;if(countPublicmove)countPublicmove.textContent=typeCounts.publicmove;if(countVolumeleader)countVolumeleader.textContent=typeCounts.volumeleader;if(countMim)countMim.textContent=typeCounts.mim;}
function selectDateFilter(dateFilter){void 0;currentAlarmDateFilter=dateFilter;const labelEl=document.getElementById('dateLabelDisplay');if(labelEl){labelEl.textContent=dateFilterLabels[dateFilter]||_t('app.flt.all','Tümü');}
const dotEl=document.getElementById('dateDotDisplay');if(dotEl){dotEl.style.background=dateFilterColors[dateFilter]||'#ffffff';}
const dropdown=document.getElementById('alarmDateDropdown');const options=document.getElementById('alarmDateOptions');if(dropdown)dropdown.classList.remove('open');if(options)options.style.display='none';alarmsDisplayCount=10;renderAlarmsList(currentAlarmFilter);}
function filterAlarmsByMatchDate(alarms){if(currentAlarmDateFilter==='all'){const today=dayjs().tz('Europe/Istanbul').format('YYYY-MM-DD');return alarms.filter(alarm=>{const matchDateStr=getMatchDateFromAlarm(alarm);if(!matchDateStr)return true;return matchDateStr>=today;});}
const today=dayjs().tz('Europe/Istanbul');const todayStr=today.format('YYYY-MM-DD');const yesterdayStr=today.subtract(1,'day').format('YYYY-MM-DD');const tomorrowStr=today.add(1,'day').format('YYYY-MM-DD');return alarms.filter(alarm=>{const matchDateStr=getMatchDateFromAlarm(alarm);if(!matchDateStr)return currentAlarmDateFilter==='all';if(currentAlarmDateFilter==='today'){return matchDateStr===todayStr;}else if(currentAlarmDateFilter==='yesterday'){return matchDateStr===yesterdayStr;}else if(currentAlarmDateFilter==='future'){return matchDateStr>=tomorrowStr;}
return true;});}
function updateDateFilterCounts(){const alarms=allAlarmsData||[];const today=dayjs().tz('Europe/Istanbul');const todayStr=today.format('YYYY-MM-DD');const yesterdayStr=today.subtract(1,'day').format('YYYY-MM-DD');const tomorrowStr=today.add(1,'day').format('YYYY-MM-DD');let countAll=0;let countToday=0;let countYesterday=0;let countFuture=0;alarms.forEach(alarm=>{const matchDateStr=getMatchDateFromAlarm(alarm);if(!matchDateStr)return;if(matchDateStr===todayStr){countToday++;countAll++;}else if(matchDateStr===yesterdayStr){countYesterday++;}else if(matchDateStr>=tomorrowStr){countFuture++;countAll++;}});const elAll=document.getElementById('dateCountAll');const elToday=document.getElementById('dateCountToday');const elYesterday=document.getElementById('dateCountYesterday');const elFuture=document.getElementById('dateCountFuture');if(elAll)elAll.textContent=countAll;if(elToday)elToday.textContent=countToday;if(elYesterday)elYesterday.textContent=countYesterday;if(elFuture)elFuture.textContent=countFuture;}
function filterAlarms(type){currentAlarmFilter=type;alarmsDisplayCount=10;document.querySelectorAll('.alarm-pill').forEach(btn=>{btn.classList.toggle('active',btn.dataset.type===type);});renderAlarmsList(type);}
function searchAlarms(query){alarmSearchQuery=query.toLowerCase().trim();alarmsDisplayCount=10;renderAlarmsList(currentAlarmFilter);}
function getFilteredAlarms(){let groups=currentAlarmFilter==='all'?[...groupedAlarmsData]:groupedAlarmsData.filter(g=>g.type===currentAlarmFilter);if(currentAlarmDateFilter!=='none'){const{todayStr,yesterdayStr,tomorrowStr}=getDateFilterStrings();groups=groups.filter(g=>{const matchDateStr=g.match_date||g.fixture_date||getMatchDateFromAlarm(g.latestAlarm);if(!matchDateStr)return currentAlarmDateFilter==='all';if(currentAlarmDateFilter==='all'){return matchDateStr>=todayStr;}else if(currentAlarmDateFilter==='today'){return matchDateStr===todayStr;}else if(currentAlarmDateFilter==='yesterday'){return matchDateStr===yesterdayStr;}else if(currentAlarmDateFilter==='future'){return matchDateStr>=tomorrowStr;}
return true;});}
if(alarmSearchQuery){groups=groups.filter(g=>{const home=g.home.toLowerCase();const away=g.away.toLowerCase();const league=(g.league||'').toLowerCase();return home.includes(alarmSearchQuery)||away.includes(alarmSearchQuery)||league.includes(alarmSearchQuery);});}
void 0;groups.sort((a,b)=>{const dateA=parseAlarmDate(a.latestAlarm.trigger_at||a.latestAlarm.event_time||a.latestAlarm.created_at);const dateB=parseAlarmDate(b.latestAlarm.trigger_at||b.latestAlarm.event_time||b.latestAlarm.created_at);return dateB-dateA;});if(groups.length>0){void 0;}
return groups;}
function renderAlarmsList(filterType){const body=document.getElementById('alarmsList');const groups=getFilteredAlarms();if(groups.length===0){body.innerHTML=`<div class="alarms-empty">${alarmSearchQuery ? 'Arama sonucu bulunamadi' : 'Aktif alarm yok'}</div>`;return;}
const displayGroups=groups.slice(0,alarmsDisplayCount);const hasMore=groups.length>alarmsDisplayCount;const typeLabels={sharp:'SHARP',bigmoney:'BIG MONEY',volumeshock:_t('app.j.alarm_volume_shock','HACIM SOKU'),dropping:_t('app.j.alarm_odds_drop','ORAN DÜŞÜŞÜ'),publicmove:'PUBLIC MOVE',volumeleader:_t('app.j.alarm_leader_changed','LİDER DEĞİŞTİ'),mim:'MIM'};const typeColors={sharp:'#4ade80',bigmoney:'#F08A24',volumeshock:'#F6C343',dropping:'#f85149',publicmove:'#FFCC00',volumeleader:'#06b6d4',mim:'#3B82F6'};let html=displayGroups.map((group,idx)=>{const type=group.type;const alarm=group.latestAlarm;const home=group.home;const away=group.away;const market=group.market;const selection=group.selection;const alarmId=`alarm_${type}_${idx}`;const isOpen=openAlarmId===alarmId;let mainValue='';let centerBadge='';if(type==='sharp'){const score=(alarm.sharp_score||0).toFixed(1);const oddsDrop=alarm.odds_drop_pct||alarm.drop_pct||0;const prevOdds=alarm.previous_odds||0;const currOdds=alarm.current_odds||0;const oddsSign=oddsDrop>0?'\u25BC':'\u25B2';const volume=alarm.volume||alarm.stake||0;const moneyPart=volume>0?`<span class="value-money">\u00A3${Number(volume).toLocaleString('en-GB')}</span><span class="sep">\u2022</span>`:'';const oddsPart=prevOdds>0&&currOdds>0?`<span class="value-odds">${prevOdds.toFixed(2)}</span><span class="arrow">\u2192</span><span class="value-odds-new">${currOdds.toFixed(2)}</span><span class="sep">\u2022</span>`:'';mainValue=`${moneyPart}${oddsPart}<span class="value-highlight">Sharp Puanı ${score}</span><span class="sep">\u2022</span><span class="value-pct">${oddsSign}${Math.abs(oddsDrop).toFixed(1)}%</span>`;}else if(type==='bigmoney'){const money=alarm.incoming_money||alarm.stake||0;mainValue=`<span class="value-money">£${Math.round(Number(money)).toLocaleString('en-GB')}</span>`;const isHuge=alarm.is_huge||alarm.alarm_type==='HUGE MONEY';if(isHuge){centerBadge='<span class="huge-badge">HUGE</span>';}}else if(type==='volumeshock'){const shockValue=alarm.volume_shock_value||alarm.volume_shock||alarm.volume_shock_multiplier||0;const hoursToKickoff=calculateHoursToKickoff(alarm);mainValue=`<span class="value-highlight">${shockValue.toFixed(1)}x</span><span class="sep">•</span><span class="value-pct">${hoursToKickoff.toFixed(1)} ${_t('app.j.saat_kala','saat kala')}</span>`;}else if(type==='dropping'){const openingOdds=alarm.opening_odds||0;const currentOdds=alarm.current_odds||0;const dropPct=alarm.drop_pct||0;const level=alarm.level||'L1';mainValue=`<span class="value-odds">${openingOdds.toFixed(2)}</span><span class="arrow">→</span><span class="value-odds-new">${currentOdds.toFixed(2)}</span><span class="sep">•</span><span class="value-pct-drop">▼${dropPct.toFixed(1)}%</span>`;centerBadge=`<span class="level-badge level-${level.toLowerCase()}">${level}</span>`;}else if(type==='publicmove'){const score=alarm.move_score||alarm.trap_score||alarm.sharp_score||0;const volume=alarm.volume||0;const moneyPart=volume>0?`<span class="value-money">£${Number(volume).toLocaleString('en-GB')}</span><span class="sep">•</span>`:'';mainValue=`${moneyPart}<span class="value-highlight">Move Skor ${score.toFixed(0)}</span>`;}else if(type==='volumeleader'){const oldLeader=alarm.old_leader||'-';const newLeader=alarm.new_leader||'-';const oldShare=(alarm.old_leader_share||0).toFixed(0);const newShare=(alarm.new_leader_share||0).toFixed(0);mainValue=`<span class="value-odds">${oldLeader} %${oldShare}</span><span class="arrow">→</span><span class="value-odds-new">${newLeader} %${newShare}</span>`;}else if(type==='mim'){const level=alarm.level||1;const impact=(alarm.impact||alarm.impact_score||alarm.money_impact||0).toFixed(2);mainValue=`<span class="value-highlight">L${level}</span><span class="sep">•</span><span class="value-pct">${impact}</span>`;}
const timeSource=alarm.trigger_at||alarm.event_time||alarm.created_at;const triggerTimeShort=formatTriggerTimeShort(timeSource);const triggerPill=group.triggerCount>1?`<span class="trigger-pill">×${group.triggerCount}</span>`:'';const marketLabel=formatMarketChip(market,selection);const expandIcon=isOpen?'▼':'▶';const stripeColors={'bigmoney':'#F08A24','sharp':'#22c55e','dropping':'#f85149','volumeshock':'#F6C343','publicmove':'#FFCC00','volumeleader':'#06b6d4','mim':'#3B82F6'};const stripeColor=stripeColors[type]||'#64748b';const typeBadges={'bigmoney':alarm.is_huge?'HUGE':'BIG','sharp':'SHARP','dropping':alarm.level||_t('app.j.alarm_drop_word','DÜŞÜŞ'),'volumeshock':'HS','publicmove':'TRAP','volumeleader':_t('app.j.alarm_leader_word','LİDER'),'mim':'MIM'};const typeBadge=typeBadges[type]||type.toUpperCase();let mainMoney=0;if(type==='bigmoney'){mainMoney=alarm.incoming_money||alarm.stake||0;}else if(type==='sharp'){mainMoney=alarm.volume||alarm.stake||0;}else if(type==='volumeshock'){mainMoney=alarm.incoming_money||0;}else if(type==='dropping'){mainMoney=0;}else if(type==='publicmove'){mainMoney=alarm.volume||0;}else if(type==='volumeleader'){mainMoney=alarm.total_volume||0;}else if(type==='mim'){mainMoney=0;}
const homeEscaped=home.replace(/'/g,"\\'");const awayEscaped=away.replace(/'/g,"\\'");const marketEscaped=market.replace(/'/g,"\\'");const leagueEscaped=(group.league||'').replace(/'/g,"\\'");const kickoffEscaped=(group.kickoff_utc||group.match_date||'').replace(/'/g,"\\'");const hashEscaped=(group.match_id||group.latestAlarm?.match_id_hash||group.latestAlarm?.match_id||'').replace(/'/g,"\\'");const matchTimeFormatted=formatMatchTime3(group.kickoff_utc||group.match_date);const marketLabel2=`${translateMarket(market)} → ${translateSelection(selection, market)}`;const triggerTimeSource=type==='dropping'?(alarm.created_at||alarm.event_time||alarm.trigger_at):(alarm.trigger_at||alarm.event_time||alarm.created_at);const triggerTime=formatTriggerTime(triggerTimeSource);let badgeLabel='';let metricContent='';let historyLine='';if(type==='sharp'){badgeLabel='SHARP';const score=(alarm.sharp_score||0).toFixed(1);const volumeContrib=(alarm.volume_contrib||0).toFixed(1);const oddsContrib=(alarm.odds_contrib||0).toFixed(1);const prevOdds=(alarm.previous_odds||0).toFixed(2);const currOdds=(alarm.current_odds||0).toFixed(2);metricContent=`<div class="acd-grid cols-3">
                <div class="acd-stat">
                    <div class="acd-stat-val sharp">${score}</div>
                    <div class="acd-stat-lbl">${_t('app.j.sharp_score_label','Sharp Skor')}</div>
                </div>
                <div class="acd-stat">
                    <div class="acd-stat-val">${volumeContrib}</div>
                    <div class="acd-stat-lbl">${_t('app.j.hacim_puan','Hacim Puan')}</div>
                </div>
                <div class="acd-stat">
                    <div class="acd-stat-val">${oddsContrib}</div>
                    <div class="acd-stat-lbl">${_t('app.j.oran_puan','Oran Puan')}</div>
                </div>
            </div>
            <div class="acd-info-row">
                <span>${_t('app.j.odds_lbl','Oran:')} ${prevOdds} → ${currOdds}</span>
            </div>`;historyLine=`${triggerTime}`;}else if(type==='volumeshock'){badgeLabel=_t('app.j.alarm_volume_shock','HACİM ŞOKU');const newMoney=alarm.incoming_money||0;const shockVal=(alarm.volume_shock_value||alarm.volume_shock||alarm.volume_shock_multiplier||0).toFixed(1);const hoursToKickoff=calculateHoursToKickoff(alarm);metricContent=`<div class="acd-grid cols-2">
                <div class="acd-stat">
                    <div class="acd-stat-val volumeshock">${shockVal}x</div>
                    <div class="acd-stat-lbl">${_t('app.j.acd_volume_shock','Hacim Şoku')}</div>
                </div>
                <div class="acd-stat">
                    <div class="acd-stat-val">£${Number(newMoney).toLocaleString('en-GB')}</div>
                    <div class="acd-stat-lbl">${_t('app.j.acd_incoming_money','Gelen Para')}</div>
                </div>
            </div>
            <div class="acd-info-row">
                <span>${_t('app.j.maca_once','Maça')} ${hoursToKickoff.toFixed(1)} ${_t('app.j.saat_kala','saat kala')}</span>
            </div>`;historyLine=`${triggerTime}`;}else if(type==='bigmoney'){badgeLabel=alarm.is_huge?'HUGE MONEY':'BIG MONEY';const money=alarm.incoming_money||alarm.stake||0;const selectionTotal=alarm.total_selection||alarm.selection_total||alarm.volume||alarm.total_volume||0;let historyHtml='';let alarmHistory=alarm.alarm_history||[];if(typeof alarmHistory==='string'){try{alarmHistory=JSON.parse(alarmHistory);}catch(e){alarmHistory=[];}}
if(alarmHistory&&alarmHistory.length>0){const currentTs=alarm.trigger_at?new Date(alarm.trigger_at).getTime():0;const currentMoney=Math.round(alarm.incoming_money||alarm.stake||0);const seen=new Set();const uniqueHistory=alarmHistory.filter(h=>{const ts=h.trigger_at?new Date(h.trigger_at).getTime():0;const histMoney=Math.round(h.incoming_money||0);if(ts===currentTs&&histMoney===currentMoney)return false;const key=`${ts}|${histMoney}`;if(seen.has(key))return false;seen.add(key);return true;});if(uniqueHistory.length>0){const historyItems=uniqueHistory.slice().sort((a,b)=>{const tsA=a.trigger_at?new Date(a.trigger_at).getTime():0;const tsB=b.trigger_at?new Date(b.trigger_at).getTime():0;return tsB-tsA;}).map(h=>{const hTime=formatTriggerTimeFull(h.trigger_at);const hMoney=Number(h.incoming_money||0).toLocaleString('en-GB');return`<div class="acd-history-item"><span class="acd-history-time">${hTime}</span><span class="acd-history-val">£${hMoney}</span></div>`;}).join('');historyHtml=`<div class="acd-history-section">
                        <div class="acd-history-title">${_t('app.j.acd_previous','ÖNCEKİ')}</div>
                        ${historyItems}
                    </div>`;}}
const totalHtml=selectionTotal>0?`<div class="acd-stat acd-stat-secondary">
                    <div class="acd-stat-val muted">£${Number(selectionTotal).toLocaleString('en-GB')}</div>
                    <div class="acd-stat-lbl">${_t('app.j.acd_total','Toplam')}</div>
                  </div>`:'';metricContent=`<div class="acd-bigmoney-hero">
                <div class="acd-hero-amount">£${Number(money).toLocaleString('en-GB')}</div>
                <div class="acd-hero-label">${_t('app.j.acd_big_money_in','Büyük Para Girişi')}</div>
            </div>${totalHtml ? `<div class="acd-grid cols-1">${totalHtml}</div>` : ''}${historyHtml}`;const historyCount=(typeof uniqueHistory!=='undefined'&&uniqueHistory.length>0)?uniqueHistory.length:(alarmHistory.length>0?alarmHistory.length:0);historyLine=historyCount>0?`×${historyCount + 1}`:`${triggerTime}`;}else if(type==='dropping'){const level=alarm.level||'L1';badgeLabel=`${_t('app.j.alarm_odds_drop','ORAN DÜŞÜŞÜ')} ${level}`;const openOdds=(alarm.opening_odds||0).toFixed(2);const currOdds=(alarm.current_odds||0).toFixed(2);const dropPct=(alarm.drop_pct||0).toFixed(1);const matchDateFormatted=formatMatchDateShort(alarm.match_date||'');metricContent=`<div class="acd-grid cols-2">
                <div class="acd-stat">
                    <div class="acd-stat-val dropping">${openOdds} → ${currOdds}</div>
                    <div class="acd-stat-lbl">${_t('app.j.oran_degisimi','Oran Değişimi')}</div>
                </div>
                <div class="acd-stat">
                    <div class="acd-stat-val drop">▼ ${dropPct}%</div>
                    <div class="acd-stat-lbl">${_t('app.j.dusus_lbl','Düşüş')} (${level})</div>
                </div>
            </div>
            ${matchDateFormatted ? `<div class="acd-info-row"><span>📅 ${_t('app.j.match_word','Maç')}:${matchDateFormatted}</span></div>` : ''}`;historyLine=`${triggerTime}`;}else if(type==='publicmove'){badgeLabel='PUBLIC MOVE';const score=(alarm.move_score||alarm.trap_score||alarm.sharp_score||0).toFixed(0);const volume=alarm.volume||0;metricContent=`<div class="acd-grid cols-2">
                <div class="acd-stat">
                    <div class="acd-stat-val publicmove">${score}</div>
                    <div class="acd-stat-lbl">Move Skor</div>
                </div>
                <div class="acd-stat">
                    <div class="acd-stat-val">£${Number(volume).toLocaleString('en-GB')}</div>
                    <div class="acd-stat-lbl">Hacim</div>
                </div>
            </div>`;historyLine=`${triggerTime}`;}else if(type==='volumeleader'){badgeLabel=_t('app.j.alarm_leader_changed','LİDER DEĞİŞTİ');const oldLeader=alarm.old_leader||'-';const newLeader=alarm.new_leader||'-';const oldShare=(alarm.old_leader_share||0).toFixed(0);const newShare=(alarm.new_leader_share||0).toFixed(0);const totalVol=alarm.total_volume||0;metricContent=`<div class="acd-grid cols-2">
                <div class="acd-stat">
                    <div class="acd-stat-val volumeleader">${oldLeader} %${oldShare}</div>
                    <div class="acd-stat-lbl">${_t('app.j.eski_lider','Eski Lider')}</div>
                </div>
                <div class="acd-stat">
                    <div class="acd-stat-val volumeleader-new">${newLeader} %${newShare}</div>
                    <div class="acd-stat-lbl">${_t('app.j.yeni_lider','Yeni Lider')}</div>
                </div>
            </div>
            <div class="acd-info-row">
                <span>${_t('app.j.toplam_hacim_lbl','Toplam Hacim')}: £${Number(totalVol).toLocaleString('en-GB')}</span>
            </div>`;historyLine=`${triggerTime}`;}else if(type==='mim'){badgeLabel='MIM';const impact=alarm.impact||alarm.impact_score||alarm.money_impact||0;const impactPct=(impact*100).toFixed(1);const prevVol=alarm.prev_volume||alarm.previous_volume||0;const currVol=alarm.current_volume||alarm.curr_volume||alarm.total_volume||0;const incomingMoney=alarm.incoming_volume||(currVol-prevVol);const totalMarketVol=alarm.total_market_volume||currVol;metricContent=`<div class="acd-grid cols-3">
                <div class="acd-stat">
                    <div class="acd-stat-val mim">${impactPct}%</div>
                    <div class="acd-stat-lbl">Impact</div>
                </div>
                <div class="acd-stat">
                    <div class="acd-stat-val" style="color: #22c55e;">+£${Math.round(Number(incomingMoney)).toLocaleString('en-GB')}</div>
                    <div class="acd-stat-lbl">${_t('app.j.acd_incoming_money','Gelen Para')}</div>
                </div>
                <div class="acd-stat">
                    <div class="acd-stat-val">£${Math.round(Number(totalMarketVol)).toLocaleString('en-GB')}</div>
                    <div class="acd-stat-lbl">${_t('app.j.market_hacmi','Market Hacmi')}</div>
                </div>
            </div>
            <div class="acd-info-row">
                <span>${_t('app.j.secenek','Seçenek')}: £${Math.round(Number(prevVol)).toLocaleString('en-GB')} → £${Math.round(Number(currVol)).toLocaleString('en-GB')}</span>
            </div>`;historyLine=`${triggerTime}`;}
const fullMatchName=`${home} – ${away}`;let metricValue='';if(type==='sharp'){metricValue=(alarm.sharp_score||0).toFixed(1);}else if(type==='volumeshock'){metricValue=`${(alarm.volume_shock_value || alarm.volume_shock || alarm.volume_shock_multiplier || 0).toFixed(1)}x`;}else if(type==='bigmoney'){metricValue=`£${Math.round(Number(alarm.incoming_money || alarm.stake || 0)).toLocaleString('en-GB')}`;}else if(type==='dropping'){metricValue=`▼ ${(alarm.drop_pct || 0).toFixed(1)}%`;}else if(type==='publicmove'){metricValue=(alarm.move_score||alarm.trap_score||alarm.sharp_score||0).toFixed(0);}else if(type==='volumeleader'){const oldL=alarm.old_leader||'-';const newL=alarm.new_leader||'-';metricValue=`<span class="vl-transition"><span class="vl-old">${oldL}</span><span class="vl-arrow">›</span><span class="vl-new">${newL}</span></span>`;}else if(type==='mim'){const impact=alarm.impact||alarm.impact_score||alarm.money_impact||0;const impactPct=(impact*100).toFixed(0);const incomingMoney=alarm.incoming_volume||((alarm.current_volume||alarm.curr_volume||0)-(alarm.prev_volume||0));metricValue=incomingMoney>0?`+£${Math.round(Number(incomingMoney)).toLocaleString('en-GB')}`:`${impactPct}%`;}
const historyCount=group.history.length;const historyBadge=historyCount>0?`<span class="history-badge history-badge-${type}">×${historyCount + 1}</span>`:'';let historySection='';if(historyCount>0&&isOpen){const historyItems=group.history.map(h=>{const hTime=formatTriggerTimeWithDay(h.trigger_at||h.event_time||h.created_at);let hValue='';if(type==='sharp'){hValue=`Sharp ${(h.sharp_score || 0).toFixed(1)}`;}else if(type==='volumeshock'){hValue=`${(h.volume_shock_value || h.volume_shock || h.volume_shock_multiplier || 0).toFixed(1)}x`;}else if(type==='bigmoney'){hValue=`£${Math.round(Number(h.incoming_money || h.stake || 0)).toLocaleString('en-GB')}`;}else if(type==='dropping'){hValue=`▼ ${(h.drop_pct || 0).toFixed(1)}%`;}else if(type==='publicmove'){hValue=`Trap ${(h.trap_score || h.sharp_score || 0).toFixed(0)}`;}else if(type==='volumeleader'){hValue=`<span class="vl-mini">${h.old_leader || '-'} › ${h.new_leader || '-'}</span>`;}else if(type==='mim'){const hImpact=h.impact||h.impact_score||h.money_impact||0;const hIncoming=(h.current_volume||h.curr_volume||0)-(h.prev_volume||0);hValue=hIncoming>0?`+£${Math.round(Number(hIncoming)).toLocaleString('en-GB')}`:`${(hImpact * 100).toFixed(0)}%`;}
return`<div class="history-item history-item-${type}"><span class="history-time">${hTime}</span><span class="history-val">${hValue}</span></div>`;}).join('');historySection=`<div class="acd-history-list"><div class="history-title">Önceki Alarmlar</div>${historyItems}</div>`;}
return`
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
                            <button class="acd-btn" onclick="event.stopPropagation(); goToMatchFromAlarm('${homeEscaped}', '${awayEscaped}', '${type}', '${marketEscaped}', '${leagueEscaped}', '${kickoffEscaped}', '${hashEscaped}')">${_t('app.j.acd_open_match','Maç Sayfasını Aç')}</button>
                        </div>
                    </div>
                </div>
            </div>
        `;}).join('');if(hasMore){html+=`
            <div class="load-more-container" style="padding: 8px;">
                <button class="load-more-btn" style="width: 100%;" onclick="loadMoreAlarms()">
                    Daha Fazla (${groups.length - alarmsDisplayCount})
                </button>
            </div>
        `;}
body.innerHTML=html;}
function toggleAlarmDetail(alarmId){if(openAlarmId===alarmId){openAlarmId=null;}else{openAlarmId=alarmId;}
renderAlarmsList(currentAlarmFilter);if(openAlarmId){setTimeout(()=>{const detailEl=document.getElementById('detail_'+alarmId);if(detailEl){detailEl.scrollIntoView({behavior:'smooth',block:'nearest'});}},50);}}
function formatMarketChip(market,selection){let marketShort=market;if(market.toLowerCase().includes('1x2'))marketShort='1X2';else if(market.toLowerCase().includes('ou')||market.toLowerCase().includes('2.5'))marketShort='A/Ü 2.5';else if(market.toLowerCase().includes('btts'))marketShort='KG';const rawSel=(selection||'').toUpperCase();const selMap={'U':_t('app.dyn.alt','Alt'),'O':_t('app.dyn.ust','Üst'),'Y':_t('app.dyn.evet','Evet'),'N':_t('app.dyn.hayir','Hayır'),'1':'1','X':'X','2':'2','UNDER':_t('app.dyn.alt','Alt'),'OVER':_t('app.dyn.ust','Üst'),'YES':_t('app.dyn.evet','Evet'),'NO':_t('app.dyn.hayir','Hayır')};const mappedSel=selMap[rawSel]||rawSel;return`${marketShort} · ${mappedSel}`;}
function loadMoreAlarms(){alarmsDisplayCount+=10;renderAlarmsList(currentAlarmFilter);const container=document.getElementById('alarmsList');const cards=container.querySelectorAll('.alarm-card');if(cards.length>0){cards[cards.length-30]?.scrollIntoView({behavior:'smooth',block:'start'});}}
window.__sxfLoadAllAlarmsImpl=loadAllAlarms;window.__sxfSelectDateFilterImpl=selectDateFilter;window.__sxfFilterAlarmsImpl=filterAlarms;window.__sxfSearchAlarmsImpl=searchAlarms;window.__sxfToggleAlarmDetailImpl=toggleAlarmDetail;window.__sxfLoadMoreAlarmsImpl=loadMoreAlarms;})();