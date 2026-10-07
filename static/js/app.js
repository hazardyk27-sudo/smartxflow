if(typeof window._t!=='function'){window._t=function(k,fb){try{var v=(window.SXFI18n&&window.SXFI18n.t)?window.SXFI18n.t(k):null;return(v&&v!==k)?v:fb;}catch(e){return fb;}};}
var _t=window._t;var _MONTH_FB=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];function _tms(i){return _t('app.j.ms'+i,_MONTH_FB[i]||'');}
if(typeof dayjs!=='undefined'){if(typeof dayjs_plugin_utc!=='undefined')dayjs.extend(dayjs_plugin_utc);if(typeof dayjs_plugin_timezone!=='undefined')dayjs.extend(dayjs_plugin_timezone);if(typeof dayjs_plugin_customParseFormat!=='undefined')dayjs.extend(dayjs_plugin_customParseFormat);}
window._chartLibsLoaded=false;window._chartLibsLoading=false;window.loadChartLibs=function(){return new Promise(function(resolve){if(window._chartLibsLoaded&&typeof Chart!=='undefined')return resolve();if(window._chartLibsLoading&&!window._chartLibsRetry){var check=setInterval(function(){if(window._chartLibsLoaded){clearInterval(check);resolve();}},50);return;}
window._chartLibsLoading=true;window._chartLibsRetry=false;var coreScripts=['https://cdn.jsdelivr.net/npm/chart.js'];var pluginScripts=['https://cdn.jsdelivr.net/npm/hammerjs@2.0.8','https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js'];var zoomScript='https://cdn.jsdelivr.net/npm/chartjs-plugin-zoom@2.0.1/dist/chartjs-plugin-zoom.min.js';var failed=[];function loadScript(src){return new Promise(function(res){var s=document.createElement('script');s.src=src;s.onload=function(){res(true);};s.onerror=function(){failed.push(src);res(false);};document.head.appendChild(s);});}
loadScript(coreScripts[0]).then(function(){var parallel=pluginScripts.map(function(src){return loadScript(src);});parallel.push(loadScript(zoomScript));return Promise.all(parallel);}).then(function(){if(typeof Chart!=='undefined'){window._chartLibsLoaded=true;}else{console.error('[ChartLibs] Chart.js failed to load. Failed scripts:',failed);window._chartLibsLoaded=false;window._chartLibsLoading=false;window._chartLibsRetry=true;}
resolve();});});};let currentMarket='moneyway_1x2';let matches=[];let filteredMatches=[];let chart=null;let selectedMatch=null;let selectedChartMarket='moneyway_1x2';let autoScrapeRunning=false;let currentSortColumn='volume';let currentSortDirection='desc';let chartVisibleSeries={};let dateFilterMode='ALL';let chartTimeRange='10min';let currentChartHistoryData=[];let chartViewMode='percent';let isClientMode=true;let _modalRequestId=0;let _analysisMatchHashes=[];let _mobileHideEnded=false;let _mobileHideLive=false;let _mobileOnlyLive=false;let _analysisHashesFetched=false;let currentSource='betfair';let _licenseReadyResolve;const _licenseReady=new Promise(r=>{_licenseReadyResolve=r;});let _isLicensed=false;function getWebDeviceId(){let did=localStorage.getItem('smartxflow_device_id');if(!did||did.length>16){did='w-'+crypto.randomUUID().replace(/-/g,'').substring(0,14);localStorage.setItem('smartxflow_device_id',did);}
return did;}
let _userFavorites=new Set();let _favCounts={};let _favFilterActive=false;function _getMatchKey(match){return(match.home_team||'')+'|'+(match.away_team||'')+'|'+(match.league||'');}
function loadUserFavorites(){var did=getWebDeviceId();if(!did)return Promise.resolve();return fetch('/api/favorites?device_id='+encodeURIComponent(did)).then(function(r){return r.json();}).then(function(data){_userFavorites=new Set(data.favorites||[]);}).catch(function(){});}
function loadFavoriteCounts(){return fetch('/api/favorite/all-counts').then(function(r){if(!r.ok)throw new Error('HTTP '+r.status);return r.json();}).then(function(data){void 0;_favCounts=data.counts||{};_updateFavCountsInDOM();}).catch(function(err){console.error('[Fav] loadFavoriteCounts error:',err);});}
function loadFavoritesBootstrap() {
    var did = getWebDeviceId();
    if (!did) return Promise.resolve();
    return fetch('/api/favorites/bootstrap?device_id=' + encodeURIComponent(did))
        .then(function(r) {
            if (!r.ok) throw new Error('HTTP ' + r.status);
            return r.json();
        })
        .then(function(data) {
            if (!data || !Array.isArray(data.favorites) || !data.counts || typeof data.counts !== 'object') {
                throw new Error('invalid favorites bootstrap payload');
            }
            _userFavorites = new Set(data.favorites);
            _favCounts = data.counts;
            _updateFavCountsInDOM();
        })
        .catch(function(error) {
            console.warn('[Fav] Bootstrap fallback:', error);
            return Promise.all([loadUserFavorites(), loadFavoriteCounts()]);
        });
}

function _updateFavCountsInDOM(){document.querySelectorAll('.fav-heart').forEach(function(el){var mk=el.getAttribute('data-matchkey');var c=_favCounts[mk]||0;var countEl=el.parentElement.querySelector('.fav-count');if(countEl&&mk){countEl.innerHTML=_favCountHtml(c);}});document.querySelectorAll('.mobile-fav-count').forEach(function(el){var mk=el.getAttribute('data-matchkey');if(mk){var c=_favCounts[mk]||0;el.textContent=c+(window.SXFI18n?window.SXFI18n.t('app.dyn.kisi')+' '+window.SXFI18n.t('app.dyn.takip_ediyor'):' kişi takip ediyor');}});}
function toggleFavorite(el){var mk=el.getAttribute('data-matchkey');if(!mk)return;var did=getWebDeviceId();void 0;fetch('/api/favorite/toggle',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({match_key:mk,device_id:did})}).then(function(r){void 0;return r.json();}).then(function(data){if(data.error){console.warn('[Fav] error:',data.error);return;}
void 0;if(data.favorited){_userFavorites.add(mk);}else{_userFavorites.delete(mk);}
document.querySelectorAll('.fav-heart').forEach(function(h){if(h.getAttribute('data-matchkey')===mk){if(data.favorited){h.classList.add('fav-active');}else{h.classList.remove('fav-active');}}});_favCounts[mk]=data.total_count||0;var displayCount=_favCounts[mk];document.querySelectorAll('.fav-count').forEach(function(fc){var heart=fc.parentElement?fc.parentElement.querySelector('.fav-heart'):null;if(heart&&heart.getAttribute('data-matchkey')===mk){fc.innerHTML=_favCountHtml(displayCount);}});document.querySelectorAll('.mobile-fav-count').forEach(function(mc){if(mc.getAttribute('data-matchkey')===mk){mc.textContent=(displayCount>0?displayCount:0)+(window.SXFI18n?window.SXFI18n.t('app.dyn.kisi')+' '+window.SXFI18n.t('app.dyn.takip_ediyor'):' kişi takip ediyor');}});if(_favFilterActive&&!data.favorited){var row=el.closest('tr');if(row)row.style.display='none';var card=el.closest('.match-card');if(card)card.style.display='none';}}).catch(function(){});}
function _setModalFavBtnState(mk){var btn=document.getElementById('modalFavBtn');if(!btn)return;btn.setAttribute('data-matchkey',mk||'');var isFav=mk&&_userFavorites.has(mk);if(isFav){btn.classList.add('fav-active');}else{btn.classList.remove('fav-active');}
if(window.SXFI18n){btn.setAttribute('title',window.SXFI18n.t(isFav?'idx.fav_remove':'idx.fav_add'));}}
function toggleModalFavorite(){var btn=document.getElementById('modalFavBtn');if(!btn||!selectedMatch)return;var mk=_getMatchKey(selectedMatch);if(!mk)return;var did=getWebDeviceId();fetch('/api/favorite/toggle',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({match_key:mk,device_id:did})}).then(function(r){return r.json();}).then(function(data){if(data.error){console.warn('[Fav] modal error:',data.error);return;}
if(data.favorited){_userFavorites.add(mk);}else{_userFavorites.delete(mk);}
_setModalFavBtnState(mk);document.querySelectorAll('.fav-heart').forEach(function(h){if(h.getAttribute('data-matchkey')===mk){if(data.favorited){h.classList.add('fav-active');}else{h.classList.remove('fav-active');}}});_favCounts[mk]=data.total_count||0;var displayCount=_favCounts[mk];document.querySelectorAll('.fav-count').forEach(function(fc){var heart=fc.parentElement?fc.parentElement.querySelector('.fav-heart'):null;if(heart&&heart.getAttribute('data-matchkey')===mk){fc.innerHTML=_favCountHtml(displayCount);}});document.querySelectorAll('.mobile-fav-count').forEach(function(mc){if(mc.getAttribute('data-matchkey')===mk){mc.textContent=(displayCount>0?displayCount:0)+(window.SXFI18n?window.SXFI18n.t('app.dyn.kisi')+' '+window.SXFI18n.t('app.dyn.takip_ediyor'):' kişi takip ediyor');}});}).catch(function(){});}
function toggleFavoritesFilter(){_favFilterActive=!_favFilterActive;var btn=document.getElementById('favoritesBtn');var btnM=document.getElementById('favoritesBtnMobile');if(_favFilterActive){if(btn)btn.classList.add('btn-favorites-active');if(btnM)btnM.classList.add('btn-favorites-active');_loadAndApplyFavoritesFilter();}else{if(btn)btn.classList.remove('btn-favorites-active');if(btnM)btnM.classList.remove('btn-favorites-active');_clearFavoritesFilter();}}
async function _loadAndApplyFavoritesFilter(){if(_userFavorites.size===0){_applyFavoritesFilter();return;}
var renderedKeys=new Set();document.querySelectorAll('#matchesTableBody tr').forEach(function(row){var mk=row.getAttribute('data-matchkey');if(!mk){var h=row.querySelector('.fav-heart');if(h)mk=h.getAttribute('data-matchkey');}
if(mk)renderedKeys.add(mk);});document.querySelectorAll('#matchCardList .match-card').forEach(function(card){var mk=card.getAttribute('data-matchkey');if(!mk){var h=card.querySelector('.fav-heart');if(h)mk=h.getAttribute('data-matchkey');}
if(mk)renderedKeys.add(mk);});var missingFavs=[];_userFavorites.forEach(function(mk){if(!renderedKeys.has(mk))missingFavs.push(mk);});if(missingFavs.length===0){_applyFavoritesFilter();return;}
try{var did=getWebDeviceId();var mkt=(typeof currentMarket!=='undefined')?currentMarket:'moneyway_1x2';var srcParam=(typeof currentSource!=='undefined'&&currentSource!=='betfair')?'&source='+encodeURIComponent(currentSource):'';var url='/api/favorites-matches?device_id='+encodeURIComponent(did||'')+'&market='+encodeURIComponent(mkt)+srcParam;var resp=await fetch(url);var data=await resp.json();var extraMatches=data.matches||[];if(extraMatches.length>0){var missingSet=new Set(missingFavs);var existingKeys=new Set();(matches||[]).forEach(function(m){existingKeys.add((m.home_team||'')+'|'+(m.away_team||'')+'|'+(m.league||''));});var toAdd=extraMatches.filter(function(m){var mk=(m.home_team||'')+'|'+(m.away_team||'')+'|'+(m.league||'');return missingSet.has(mk)&&!existingKeys.has(mk);});if(toAdd.length>0){matches=(matches||[]).concat(toAdd);filteredMatches=applySorting(matches);renderMatches(filteredMatches);return;}}}catch(e){console.error('[Fav] Error loading past favorites:',e);}
_applyFavoritesFilter();}
function _applyFavoritesFilter(){document.querySelectorAll('#matchesTableBody tr').forEach(function(row){var mk=row.getAttribute('data-matchkey');if(!mk){var heart=row.querySelector('.fav-heart');if(heart)mk=heart.getAttribute('data-matchkey');}
if(mk){row.style.display=_userFavorites.has(mk)?'':'none';}});document.querySelectorAll('#matchCardList .match-card').forEach(function(card){var mk=card.getAttribute('data-matchkey');if(!mk){var heart=card.querySelector('.fav-heart');if(heart)mk=heart.getAttribute('data-matchkey');}
if(mk){card.style.display=_userFavorites.has(mk)?'':'none';}});}
function _clearFavoritesFilter(){document.querySelectorAll('#matchesTableBody tr').forEach(function(row){row.style.display='';});document.querySelectorAll('#matchCardList .match-card').forEach(function(card){card.style.display='';});}
function _favCountHtml(count){if(!count||count<=0)return'';return'<span class="fav-count-num">'+count+(window.SXFI18n?window.SXFI18n.t('app.dyn.kisi'):' kişi')+'</span>'+(window.SXFI18n?window.SXFI18n.t('app.dyn.takip_ediyor'):'takip ediyor');}
var _heartSvg='<svg viewBox="0 0 24 24" width="1em" height="1em" fill="currentColor"><path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/></svg>';function _buildLiveFavCell(match){var mk=_getMatchKey(match);var isFav=_userFavorites.has(mk);var count=_favCounts[mk]||0;return'<td class="fav-cell"><span class="fav-heart '+(isFav?'fav-active':'')+'" data-matchkey="'+mk.replace(/"/g,'&quot;')+'" onclick="event.stopPropagation(); toggleFavorite(this);">'+_heartSvg+'</span><span class="fav-count">'+_favCountHtml(count)+'</span></td>';}
function _buildFavCell(match){var mk=_getMatchKey(match);var isFav=_userFavorites.has(mk);var count=_favCounts[mk]||0;return'<td class="fav-cell"><span class="fav-heart '+(isFav?'fav-active':'')+'" data-matchkey="'+mk.replace(/"/g,'&quot;')+'" onclick="event.stopPropagation(); toggleFavorite(this);">'+_heartSvg+'</span><span class="fav-count">'+_favCountHtml(count)+'</span></td>';}
let _licenseExpiredShown=false;function showLicenseExpiredOverlay(){if(_licenseExpiredShown)return;_licenseExpiredShown=true;const appContent=document.querySelector('.main-content')||document.querySelector('main')||document.getElementById('appContainer');if(appContent){appContent.style.filter='blur(12px)';appContent.style.pointerEvents='none';appContent.style.userSelect='none';}
const header=document.querySelector('.top-bar')||document.querySelector('header')||document.querySelector('nav');if(header){header.style.filter='blur(12px)';header.style.pointerEvents='none';}
let overlay=document.getElementById('licenseExpiredOverlay');if(overlay){overlay.style.display='flex';}else{overlay=document.createElement('div');overlay.id='licenseExpiredOverlay';overlay.style.cssText='position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.85);z-index:99999;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(8px);';overlay.innerHTML='<div style="background:#1c1f23;border:1px solid #2e3238;border-radius:16px;padding:48px 40px;max-width:440px;width:90%;text-align:center;">'
+'<div style="font-size:48px;margin-bottom:16px;">⏳</div>'
+'<h2 style="color:#f0f6fc;font-size:22px;font-weight:700;margin:0 0 12px;">Lisansınızın Süresi Doldu</h2>'
+'<p style="color:#7d848c;font-size:15px;line-height:1.6;margin:0 0 28px;">Lisans süreniz sona ermiştir. Uygulamayı kullanmaya devam etmek için paketinizi yenileyin.</p>'
+'<a href="/pricing" style="display:inline-block;background:linear-gradient(135deg,#2BFF88,#1ae070);color:#141719;font-size:15px;font-weight:700;padding:14px 36px;border-radius:12px;text-decoration:none;transition:transform 0.2s,box-shadow 0.2s;">Paketleri İncele →</a>'
+'</div>';document.body.appendChild(overlay);}}
let _deviceKickedShown=false;function showDeviceKickedOverlay(){if(_deviceKickedShown)return;_deviceKickedShown=true;const appContent=document.querySelector('.main-content')||document.querySelector('main')||document.getElementById('appContainer');if(appContent){appContent.style.filter='blur(12px)';appContent.style.pointerEvents='none';appContent.style.userSelect='none';}
const header=document.querySelector('.header')||document.querySelector('header')||document.querySelector('nav');if(header){header.style.filter='blur(12px)';header.style.pointerEvents='none';}
let overlay=document.getElementById('deviceKickedOverlay');if(overlay){overlay.style.display='flex';}else{overlay=document.createElement('div');overlay.id='deviceKickedOverlay';overlay.style.cssText='position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.85);z-index:99999;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(8px);';overlay.innerHTML='<div style="background:#1c1f23;border:1px solid #2e3238;border-radius:16px;padding:48px 40px;max-width:440px;width:90%;text-align:center;">'
+'<div style="font-size:48px;margin-bottom:16px;">🔒</div>'
+'<h2 style="color:#f0f6fc;font-size:22px;font-weight:700;margin:0 0 12px;">Başka Bir Cihazdan Giriş Yapıldı</h2>'
+'<p style="color:#7d848c;font-size:15px;line-height:1.6;margin:0 0 28px;">Hesabınıza başka bir cihazdan giriş yapılmıştır. Aynı anda yalnızca izin verilen sayıda cihazda oturum açılabilir.</p>'
+'<button onclick="deviceKickedRelogin()" style="display:inline-block;background:linear-gradient(135deg,#2BFF88,#1ae070);color:#141719;font-size:15px;font-weight:700;padding:14px 36px;border-radius:12px;border:none;cursor:pointer;transition:transform 0.2s,box-shadow 0.2s;">Tekrar Giriş Yap</button>'
+'</div>';document.body.appendChild(overlay);}}
function deviceKickedRelogin(){fetch('/api/licenses/logout',{method:'POST'}).catch(()=>{});localStorage.removeItem('smartxflow_web_license');localStorage.removeItem('smartxflow_web_license_valid');localStorage.removeItem('license_days_remaining');localStorage.removeItem('license_plan');window.location.reload();}
let _licenseStatusInterval=null;function startLicenseStatusRefresh(){if(_licenseStatusInterval)return;async function checkLicenseStatus(){try{const savedLicKey=localStorage.getItem('smartxflow_web_license');const statusHeaders={};if(savedLicKey)statusHeaders['X-License-Key']=savedLicKey;const webDid=getWebDeviceId();const statusUrl='/api/license/status?device_id='+encodeURIComponent(webDid);const resp=await _originalFetch(statusUrl,{headers:statusHeaders});if(!resp.ok){try{const data=await resp.json();if(data.error==='DEVICE_KICKED'){showDeviceKickedOverlay();}else if(data.error==='LICENSE_EXPIRED'||data.error==='LICENSE_REVOKED'||data.error==='LICENSE_NOT_FOUND'){showLicenseExpiredOverlay();updateLicenseDaysBadge(0);localStorage.setItem('license_days_remaining','0');}}catch(parseErr){}
return;}
const data=await resp.json();if(data.valid&&data.days_left!==undefined){localStorage.setItem('license_days_remaining',data.days_left);updateLicenseDaysBadge(data.days_left);}else if(!data.valid){if(data.error==='DEVICE_KICKED'){showDeviceKickedOverlay();}else{showLicenseExpiredOverlay();updateLicenseDaysBadge(0);localStorage.setItem('license_days_remaining','0');}}}catch(e){}}
checkLicenseStatus();_licenseStatusInterval=setInterval(checkLicenseStatus,5*60*1000);}
const _originalFetch=window.fetch;window.fetch=function(url,options={}){const urlStr=typeof url==='string'?url:url.url||'';if(urlStr.startsWith('/api/')){const savedKey=localStorage.getItem('smartxflow_web_license');if(savedKey){options=options||{};options.headers=options.headers||{};if(options.headers instanceof Headers){options.headers.set('X-License-Key',savedKey);}else{options.headers['X-License-Key']=savedKey;}}}
return _originalFetch.call(window,url,options).then(function(response){if(response.status===403&&urlStr.startsWith('/api/')){response.clone().json().then(function(data){if(data&&(data.error==='LICENSE_EXPIRED'||data.error==='LICENSE_REVOKED'||data.error==='LICENSE_REQUIRED')){showLicenseExpiredOverlay();}}).catch(function(){});}
return response;});};let mobileSelectedLine='1';let mobileTimeRange='1440';let isAlarmsPageActive=false;let matchesDisplayCount=20;let _allFilteredMatches=[];let _renderedCount=0;const _RENDER_BATCH=20;let _scrollListenerAttached=false;let currentOffset=0;let totalMatchCount=0;let hasMoreMatches=false;let _loadMatchesLock=false;let _loadMatchesPending=null;let _loadMatchesPendingSince=0;let _loadMatchesRequestId=0;let _loadMatchesRequestKey=null;let _loadMatchesQueued=null;const _LOAD_MATCHES_PENDING_STALE_MS=45000;let _lastMatchRefreshTime=null;let _matchRefreshInterval=null;const MATCH_REFRESH_INTERVAL=10*60*1000;const APP_TIMEZONE='Europe/Istanbul';function translateSelection(sel,market){if(!sel)return'-';const s=String(sel).trim();const m=String(market||'').toUpperCase();if(m.includes('OU')||m.includes('O/U')||m.includes('2.5')){if(s==='O'||s==='Over'||s.toLowerCase()==='over')return _t('app.dyn.ust','Üst');if(s==='U'||s==='Under'||s.toLowerCase()==='under')return _t('app.dyn.alt','Alt');}
if(m.includes('BTTS')||m.includes('KG')){if(s==='Y'||s==='Yes'||s.toLowerCase()==='yes')return _t('app.dyn.evet','Evet');if(s==='N'||s==='No'||s.toLowerCase()==='no')return _t('app.dyn.hayir','Hayır');}
if(s==='Over'||s.toLowerCase()==='over')return _t('app.dyn.ust','Üst');if(s==='Under'||s.toLowerCase()==='under')return _t('app.dyn.alt','Alt');if(s==='Yes'||s.toLowerCase()==='yes')return _t('app.dyn.evet','Evet');if(s==='No'||s.toLowerCase()==='no')return _t('app.dyn.hayir','Hayır');return s;}
function translateMarket(market){if(!market)return'';const m=String(market).toUpperCase();if(m==='OU25'||m==='O/U 2.5'||m==='OU 2.5')return _t('app.dyn.ou25_label','Ü/A 2.5');if(m==='BTTS')return _t('app.j.btts','KG');if(m==='1X2')return'1X2';return market;}
let _alarmBatchCache=null;let _alarmCacheTime=0;const ALARM_CACHE_TTL=60000;async function fetchAlarmsBatch(forceRefresh=false){const now=Date.now();if(!forceRefresh&&_alarmBatchCache&&(now-_alarmCacheTime)<ALARM_CACHE_TTL){void 0;return _alarmBatchCache;}
try{const response=await fetch('/api/alarms/all');if(!response.ok)throw new Error('Batch alarm fetch failed');const data=await response.json();_alarmBatchCache=data;_alarmCacheTime=now;void 0;return data;}catch(e){console.error('[AlarmCache] Fetch error:',e);return _alarmBatchCache||{};}}
function getCachedAlarmsByType(type){if(!_alarmBatchCache)return[];return _alarmBatchCache[type]||[];}
function getCachedAlarmsWithType(){if(!_alarmBatchCache)return[];let all=[];const types=['sharp','bigmoney','volumeshock','dropping','volumeleader','mim'];types.forEach(type=>{const items=_alarmBatchCache[type]||[];items.forEach(a=>{a._type=type;});all=all.concat(items);});return all;}
function getCachedAlarmCounts(){if(!_alarmBatchCache)return{sharp:0,bigmoney:0,volumeshock:0,dropping:0,volumeleader:0,mim:0,total:0};const counts={sharp:(_alarmBatchCache.sharp||[]).length,bigmoney:(_alarmBatchCache.bigmoney||[]).length,volumeshock:(_alarmBatchCache.volumeshock||[]).length,dropping:(_alarmBatchCache.dropping||[]).length,volumeleader:(_alarmBatchCache.volumeleader||[]).length,mim:(_alarmBatchCache.mim||[]).length};counts.total=counts.sharp+counts.bigmoney+counts.volumeshock+counts.dropping+counts.volumeleader+counts.mim;return counts;}
function invalidateAlarmCache(){_alarmCacheTime=0;void 0;}
function showToast(message,type='info',anchorEl){const existing=document.querySelector('.toast-notification');if(existing)existing.remove();const toast=document.createElement('div');toast.className=`toast-notification toast-${type}`;toast.textContent=message;if(anchorEl){toast.classList.add('toast-anchored');document.body.appendChild(toast);const rect=anchorEl.getBoundingClientRect();const centerX=rect.left+rect.width/2;const topY=rect.bottom+6;toast.style.top=topY+'px';toast.style.left=centerX+'px';}else{document.body.appendChild(toast);}
setTimeout(()=>toast.classList.add('show'),10);setTimeout(()=>{toast.classList.remove('show');setTimeout(()=>toast.remove(),300);},2500);}
function toTurkeyTime(raw){if(!raw)return null;try{if(typeof raw==='number'){return dayjs(raw).tz(APP_TIMEZONE);}
const str=String(raw).trim();if(str.endsWith('Z')){return dayjs.utc(str).tz(APP_TIMEZONE);}
if(str.endsWith('+00:00')){return dayjs.utc(str.replace('+00:00','Z')).tz(APP_TIMEZONE);}
const offsetMatch=str.match(/([+-])(\d{2}):(\d{2})$/);if(offsetMatch){if(offsetMatch[1]==='+'&&offsetMatch[2]==='03'&&offsetMatch[3]==='00'){const withoutOffset=str.replace(/\+03:00$/,'').replace(/\.\d+$/,'');return dayjs(withoutOffset).tz(APP_TIMEZONE,true);}
const parsed=dayjs.parseZone(str);if(!parsed.isValid())return null;return parsed.tz(APP_TIMEZONE);}
const arbworldReverseMatch=str.match(/^(\d{2}:\d{2})\s+(\d{1,2})\.(\w{3})$/i);if(arbworldReverseMatch){const monthMap={'Jan':0,'Feb':1,'Mar':2,'Apr':3,'May':4,'Jun':5,'Jul':6,'Aug':7,'Sep':8,'Oct':9,'Nov':10,'Dec':11};const time=arbworldReverseMatch[1];const day=parseInt(arbworldReverseMatch[2]);const month=monthMap[arbworldReverseMatch[3]];if(month===undefined){return dayjs(str).tz(APP_TIMEZONE,true);}
const now=dayjs().tz(APP_TIMEZONE);const currentYear=now.year();const candidates=[currentYear-1,currentYear,currentYear+1].map(year=>{const isoStr=`${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}T${time}:00`;return dayjs.tz(isoStr,APP_TIMEZONE);});let best=candidates[1];let minDiff=Math.abs(candidates[1].diff(now,'day'));candidates.forEach(c=>{if(!c.isValid())return;const diff=Math.abs(c.diff(now,'day'));if(diff<minDiff){minDiff=diff;best=c;}});return best.isValid()?best:dayjs().tz(APP_TIMEZONE);}
const arbworldMatch=str.match(/^(\d{1,2})\.(\w{3})\s*(\d{2}:\d{2}(?::\d{2})?)$/i);if(arbworldMatch){const monthMap={'Jan':0,'Feb':1,'Mar':2,'Apr':3,'May':4,'Jun':5,'Jul':6,'Aug':7,'Sep':8,'Oct':9,'Nov':10,'Dec':11};const day=parseInt(arbworldMatch[1]);const month=monthMap[arbworldMatch[2]];if(month===undefined){return dayjs(str).tz(APP_TIMEZONE,true);}
const now=dayjs().tz(APP_TIMEZONE);const currentYear=now.year();const candidates=[currentYear-1,currentYear,currentYear+1].map(year=>{const isoStr=`${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}T${arbworldMatch[3]}`;return dayjs.tz(isoStr,APP_TIMEZONE);});const nowTR=dayjs().tz(APP_TIMEZONE);let best=candidates[1];let minDiff=Math.abs(candidates[1].diff(nowTR,'day'));candidates.forEach(c=>{if(!c.isValid())return;const diff=Math.abs(c.diff(nowTR,'day'));if(diff<minDiff){minDiff=diff;best=c;}});return best.isValid()?best:dayjs().tz(APP_TIMEZONE);}
const ddmmMatch=str.match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})\s*(\d{2}):(\d{2})(?::(\d{2}))?$/);if(ddmmMatch){const[,day,month,year,hour,min,sec]=ddmmMatch;const isoStr=`${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')}T${hour}:${min}:${sec || '00'}`;return dayjs(isoStr).tz(APP_TIMEZONE,true);}
if(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/.test(str)){return dayjs(str).tz(APP_TIMEZONE,true);}
if(/^\d{4}-\d{2}-\d{2}$/.test(str)){return dayjs(str).tz(APP_TIMEZONE,true);}
if(/^\d{2}:\d{2}(:\d{2})?$/.test(str)){const today=dayjs().tz(APP_TIMEZONE).format('YYYY-MM-DD');return dayjs(`${today}T${str}`).tz(APP_TIMEZONE,true);}
const parsed=dayjs(str);if(parsed.isValid()){return parsed.tz(APP_TIMEZONE,true);}
return dayjs(str).tz(APP_TIMEZONE,true);}catch(e){return dayjs().tz(APP_TIMEZONE);}}
function nowTurkey(){return dayjs().tz(APP_TIMEZONE);}
function getMatchStatus(dateStr){if(!dateStr)return'';const matchTime=toTurkeyTime(dateStr);if(!matchTime||!matchTime.isValid())return'';const now=nowTurkey();const diffMinutes=now.diff(matchTime,'minute');if(diffMinutes<0){return'';}else if(diffMinutes<=113){return'<span class="match-status live">'+_t('app.live.badge','CANLI')+'</span>';}else{return'<span class="match-status ended">BİTTİ</span>';}}
function _findLiveMatchByHash(matchId){if(!matchId||!_liveData||!_liveData.length)return null;for(var i=0;i<_liveData.length;i++){if(_liveData[i].match_id_hash===matchId)return _liveData[i];}
return null;}
function _findLiveMatch(homeTeam,awayTeam){if(!_liveData||!_liveData.length)return null;var h=(homeTeam||'').toLowerCase().trim();var a=(awayTeam||'').toLowerCase().trim();for(var i=0;i<_liveData.length;i++){var lm=_liveData[i];var lh=(lm.home_team||'').toLowerCase().trim();var la=(lm.away_team||'').toLowerCase().trim();if(lh===h&&la===a)return lm;if(h.length>3&&lh.includes(h))return lm;if(a.length>3&&la.includes(a))return lm;if(lh.length>3&&h.includes(lh))return lm;}
return null;}
function _isFinishedLiveMatch(lm){if(!lm)return false;var st=(lm.status||'').toLowerCase();var mn=(lm.minute||'').trim().toUpperCase();return st==='ft'||mn==='FT'||mn==='MS'||mn==='AET'||mn==='PEN';}
function _buildFinishedCapsule(lm,extraClass){var scoreHtml='';var sc=lm.score||'';if(sc){var parts=sc.split('-');var sh=(parts[0]||'').trim();var sa=(parts[1]||'').trim();scoreHtml='<span class="lc-divider"></span>'+'<span class="lc-score-val"><span class="lc-score-h">'+sh+'</span>'+'<span class="lc-score-sep">-</span>'+'<span class="lc-score-a">'+sa+'</span></span>';}
return'<div class="live-capsule lc-ended'+(extraClass?' '+extraClass:'')+'">'+'<span class="lc-min">BİTTİ</span>'+
scoreHtml+'</div>';}
function _findLiveMatchExact(homeTeam,awayTeam){if(!_liveData||!_liveData.length)return null;var h=(homeTeam||'').toLowerCase().trim();var a=(awayTeam||'').toLowerCase().trim();for(var i=0;i<_liveData.length;i++){var lm=_liveData[i];var lh=(lm.home_team||'').toLowerCase().trim();var la=(lm.away_team||'').toLowerCase().trim();if(lh===h&&la===a)return lm;}
return null;}
function _findFinishedScore(homeTeam,awayTeam,matchId){if(matchId&&_finishedScores[matchId])return _finishedScores[matchId];var key=((homeTeam||'')+'|'+(awayTeam||'')).toLowerCase();return _finishedScores[key]||null;}
function _getModalFinishedCapsule(match){if(!match||!match.date)return'';var mt=toTurkeyTime(match.date);if(!mt||!mt.isValid())return'';var diff=nowTurkey().diff(mt,'minute');if(diff<80)return'';var lmExact=_findLiveMatchExact(match.home_team,match.away_team);if(_isFinishedLiveMatch(lmExact)){return' '+_buildFinishedCapsule(lmExact,'lc-modal');}
var ft=_findFinishedScore(match.home_team,match.away_team,match.match_id);if(ft){return' '+_buildFinishedCapsule({score:ft.score,status:'ft'},'lc-modal');}
return'';}
async function loadFinishedScores(reRender){try{var resp=await fetch('/api/finished-scores');var data=await resp.json();if(data&&data.scores){_finishedScores=data.scores;if(reRender&&filteredMatches&&filteredMatches.length){renderMatches(filteredMatches);}}}catch(e){}}
function getMatchLiveCapsule(dateStr,homeTeam,awayTeam,matchId){if(!dateStr)return'';const matchTime=toTurkeyTime(dateStr);if(!matchTime||!matchTime.isValid())return'';const now=nowTurkey();const diffMinutes=now.diff(matchTime,'minute');if(diffMinutes>=80){var lmHash=_findLiveMatchByHash(matchId);if(_isFinishedLiveMatch(lmHash)){return _buildFinishedCapsule(lmHash,'');}
var lmExact=_findLiveMatchExact(homeTeam,awayTeam);if(_isFinishedLiveMatch(lmExact)){return _buildFinishedCapsule(lmExact,'');}
var ftScore=_findFinishedScore(homeTeam,awayTeam,matchId);if(ftScore){return _buildFinishedCapsule({score:ftScore.score,status:'ft'},'');}}
var lm=_findLiveMatchByHash(matchId)||_findLiveMatch(homeTeam,awayTeam);if(diffMinutes<0||diffMinutes>113)return'';var minStr='';var scoreHtml='';if(lm){var rawMin=(lm.minute||'').trim();minStr=rawMin||diffMinutes+"'";var sc=lm.score||'';if(sc){var parts=sc.split('-');var sh=(parts[0]||'').trim();var sa=(parts[1]||'').trim();scoreHtml='<span class="lc-divider"></span>'+'<span class="lc-score-val"><span class="lc-score-h">'+sh+'</span>'+'<span class="lc-score-sep">-</span>'+'<span class="lc-score-a">'+sa+'</span></span>';}}else{if(diffMinutes<=45){minStr=diffMinutes+"'";}else if(diffMinutes<=60){minStr='HT';}else if(diffMinutes<=105){minStr=(diffMinutes-15)+"'";}else{minStr="90+'";}}
return'<div class="live-capsule">'+'<span class="lc-dot"></span>'+'<span class="lc-min">'+minStr+'</span>'+
scoreHtml+'</div>';}
function getMatchLiveCapsuleDT(dateStr,homeTeam,awayTeam,matchId){if(!dateStr)return'';const matchTime=toTurkeyTime(dateStr);if(!matchTime||!matchTime.isValid())return'';const now=nowTurkey();const diffMinutes=now.diff(matchTime,'minute');if(diffMinutes>=80){var lmHash=_findLiveMatchByHash(matchId);if(_isFinishedLiveMatch(lmHash)){return _buildFinishedCapsule(lmHash,'live-capsule-desk');}
var lmExact=_findLiveMatchExact(homeTeam,awayTeam);if(_isFinishedLiveMatch(lmExact)){return _buildFinishedCapsule(lmExact,'live-capsule-desk');}
var ftScore=_findFinishedScore(homeTeam,awayTeam,matchId);if(ftScore){return _buildFinishedCapsule({score:ftScore.score,status:'ft'},'live-capsule-desk');}}
var lm=_findLiveMatchByHash(matchId)||_findLiveMatch(homeTeam,awayTeam);if(diffMinutes<0||diffMinutes>113)return'';var minStr='';var scoreHtml='';if(lm){var rawMin=(lm.minute||'').trim();minStr=rawMin||diffMinutes+"'";var sc=lm.score||'';if(sc){var parts=sc.split('-');var sh=(parts[0]||'').trim();var sa=(parts[1]||'').trim();scoreHtml='<span class="lc-divider"></span>'+'<span class="lc-score-val"><span class="lc-score-h">'+sh+'</span>'+'<span class="lc-score-sep">-</span>'+'<span class="lc-score-a">'+sa+'</span></span>';}}else{if(diffMinutes<=45){minStr=diffMinutes+"'";}else if(diffMinutes<=60){minStr='HT';}else if(diffMinutes<=105){minStr=(diffMinutes-15)+"'";}else{minStr="90+'";}}
return'<div class="live-capsule live-capsule-desk">'+'<span class="lc-dot"></span>'+'<span class="lc-min">'+minStr+'</span>'+
scoreHtml+'</div>';}
function formatTurkeyTime(value,format='HH:mm'){const dt=toTurkeyTime(value);return dt?dt.format(format):'';}
function formatTurkeyDateTime(value,format='DD.MM HH:mm'){const dt=toTurkeyTime(value);return dt?dt.format(format):'';}
function isTodayTurkey(value){const dt=toTurkeyTime(value);if(!dt)return false;return dt.format('YYYY-MM-DD')===nowTurkey().format('YYYY-MM-DD');}
function isYesterdayTurkey(value){const dt=toTurkeyTime(value);if(!dt)return false;return dt.format('YYYY-MM-DD')===nowTurkey().subtract(1,'day').format('YYYY-MM-DD');}
function calculateHoursToKickoff(alarm){if(alarm.hours_to_kickoff&&alarm.hours_to_kickoff>0){return alarm.hours_to_kickoff;}
const kickoffRaw=alarm.kickoff_utc||alarm.kickoff||alarm.fixture_date;const triggerAtRaw=alarm.trigger_at||alarm.event_time||alarm.created_at;if(!kickoffRaw||!triggerAtRaw){return 0;}
const kickoffTime=toTurkeyTime(kickoffRaw);const triggerTime=toTurkeyTime(triggerAtRaw);if(!kickoffTime||!triggerTime||!kickoffTime.isValid()||!triggerTime.isValid()){return 0;}
const diffHours=kickoffTime.diff(triggerTime,'hour',true);return diffHours>0?diffHours:0;}
function escapeHtml(str){if(!str)return'';return String(str).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);}
let _sxfDeferredModalPrefetchScheduled = false;
function scheduleDeferredModalRuntimePrefetch() {
    if (_sxfDeferredModalPrefetchScheduled) return;
    _sxfDeferredModalPrefetchScheduled = true;

    const prefetch = () => {
        const candidates = [];
        if (typeof window.__sxfLoadChartImpl !== 'function') {
            candidates.push(_getModalChartRuntimeUrl());
        }
        if (typeof window.__sxfRenderMatchAlarmsSectionImpl !== 'function') {
            candidates.push(_getModalAlarmsRuntimeUrl());
        }
        if (typeof window.__sxfCheckModalLiveDataImpl !== 'function') {
            candidates.push(_getModalLiveRuntimeUrl());
        }
        candidates.forEach(url => {
            const link = document.createElement('link');
            link.rel = 'prefetch';
            link.as = 'script';
            link.href = url;
            link.dataset.sxfModalPrefetch = '1';
            document.head.appendChild(link);
        });
    };

    if (typeof window.requestIdleCallback === 'function') {
        window.requestIdleCallback(prefetch, { timeout: 7000 });
    } else {
        setTimeout(prefetch, 4000);
    }
}

document.addEventListener('DOMContentLoaded',async()=>{const allBtn=document.getElementById('allBtn');if(allBtn)allBtn.classList.add('active');const runOptionalStartupTask=(name,task)=>{try{const result=task();if(result&&typeof result.catch==='function'){result.catch(error=>console.warn('[Startup] Optional task failed:',name,error));}}catch(error){console.warn('[Startup] Optional task failed:',name,error);}};runOptionalStartupTask('tab setup',setupTabs);runOptionalStartupTask('search setup',setupSearch);runOptionalStartupTask('chart tab setup',setupModalChartTabs);await _licenseReady;if(!_isLicensed)return;try{const initialMatchLoad=loadMatches();if(initialMatchLoad&&typeof initialMatchLoad.catch==='function'){initialMatchLoad.catch(error=>{console.error('[Matches] Initial load failed before completion:',error);if(!_liveMode)renderMatchLoadError('Maç listesi yüklemesi başlatılamadı. Tekrar deneyin.');});}}catch(error){console.error('[Matches] Initial load could not be started:',error);if(!_liveMode)renderMatchLoadError('Maç listesi yüklemesi başlatılamadı. Tekrar deneyin.');}
runOptionalStartupTask('analysis match hashes',fetchAnalysisMatchHashes);runOptionalStartupTask('finished scores', () => {
    const loadScores = () => loadFinishedScores(true);
    if (typeof window.requestIdleCallback === 'function') {
        window.requestIdleCallback(loadScores, { timeout: 5000 });
    } else {
        setTimeout(loadScores, 2500);
    }
});runOptionalStartupTask('favorites',()=>loadFavoritesBootstrap().then(()=>{document.querySelectorAll('.fav-heart[data-matchkey]').forEach(function(el){const matchKey=el.getAttribute('data-matchkey');el.classList.toggle('fav-active',_userFavorites.has(matchKey));});if(_favFilterActive)_applyFavoritesFilter();}).catch(error=>console.warn('[Fav] Startup favorites failed:',error)));runOptionalStartupTask('background live data',_startBackgroundLiveFetch);
runOptionalStartupTask('modal runtime prefetch', scheduleDeferredModalRuntimePrefetch);runOptionalStartupTask('status check',checkStatus);runOptionalStartupTask('status interval',()=>{window.statusInterval=window.setInterval(checkStatus,60000);});runOptionalStartupTask('auto refresh',setupAutoRefresh);runOptionalStartupTask('visibility handler',()=>{document.addEventListener('visibilitychange',handleVisibilityChange);});});function updateLastRefreshDisplay(){const now=dayjs().tz(APP_TIMEZONE);_lastMatchRefreshTime=now;let refreshEl=document.getElementById('lastRefreshTime');if(!refreshEl){const statusArea=document.querySelector('.status-area');if(statusArea){refreshEl=document.createElement('span');refreshEl.id='lastRefreshTime';refreshEl.className='last-refresh-time';refreshEl.style.cssText='margin-left: 15px; color: #888; font-size: 12px;';statusArea.appendChild(refreshEl);}}
if(refreshEl){refreshEl.textContent=`Son güncelleme: ${now.format('HH:mm')} (TR)`;}}
function getRefreshJitter(){return Math.floor(Math.random()*60000);}
function setupAutoRefresh(){updateLastRefreshDisplay();const jitter=getRefreshJitter();const intervalWithJitter=MATCH_REFRESH_INTERVAL+jitter;_matchRefreshInterval=setInterval(async()=>{void 0;await refreshMatchData();},intervalWithJitter);void 0;}
async function refreshMatchData(){if(_liveMode)return;if(_loadMatchesLock){void 0;return;}
try{if(window._bulkMatchesCache){window._bulkMatchesCache={};}
await loadMatches();updateLastRefreshDisplay();void 0;}catch(e){console.error('[AutoRefresh] Hata:',e);}}
function handleVisibilityChange(){if(document.visibilityState==='visible'){if(!_matchRefreshInterval){const jitter=getRefreshJitter();const intervalWithJitter=MATCH_REFRESH_INTERVAL+jitter;void 0;_matchRefreshInterval=setInterval(async()=>{void 0;await refreshMatchData();},intervalWithJitter);}
if(!_bgLiveInterval){_fetchBackgroundLiveData();_bgLiveInterval=setInterval(_fetchBackgroundLiveData,60000);}
if(_lastMatchRefreshTime){const now=dayjs().tz(APP_TIMEZONE);const diffMs=now.diff(_lastMatchRefreshTime);if(diffMs>MATCH_REFRESH_INTERVAL){void 0;refreshMatchData();}else{void 0;}}}else if(document.visibilityState==='hidden'){if(_matchRefreshInterval){clearInterval(_matchRefreshInterval);_matchRefreshInterval=null;void 0;}
if(_bgLiveInterval){clearInterval(_bgLiveInterval);_bgLiveInterval=null;}}}
function setupTabs(){document.querySelectorAll('.market-tabs .tab').forEach(tab=>{tab.addEventListener('click',()=>{const market=tab.dataset.market;if(market==='alarms'){return;}
if(market==='live'){return;}
if(_isTestLockedMarket(market)){_showTestLockedToast(tab);return;}
if(_liveMode)switchFromLive();if(isAlarmsPageActive){hideAlarmsPage();}
document.querySelectorAll('.market-tabs .tab').forEach(t=>t.classList.remove('active'));tab.classList.add('active');currentMarket=market;const isDropMarket=currentMarket.startsWith('dropping_');showTrendSortButtons(isDropMarket);if(!isDropMarket&&(currentSortColumn==='trend_down'||currentSortColumn==='trend_up')){currentSortColumn='volume';currentSortDirection='desc';}
matchesDisplayCount=20;loadMatches();});});}
function setupModalChartTabs(){document.querySelectorAll('#modalChartTabs .chart-tab').forEach(tab=>{tab.addEventListener('click',()=>{document.querySelectorAll('#modalChartTabs .chart-tab').forEach(t=>t.classList.remove('active'));tab.classList.add('active');selectedChartMarket=tab.dataset.market;if(typeof mobileBigValueTween!=='undefined'){mobileBigValueTween.reset();}
if(selectedMatch){showChartLoading();loadChartWithTrends(selectedMatch.home_team,selectedMatch.away_team,selectedChartMarket,selectedMatch.league||'');}});});}
function setupSearch(){const searchInput=document.getElementById('searchInput');if(searchInput){searchInput.addEventListener('input',(e)=>{const query=e.target.value.toLowerCase();filterMatches(query);});}}
async function _fetchMatchesWithTimeout(url,timeoutMs){const controller=new AbortController();const timeoutId=setTimeout(()=>controller.abort(),timeoutMs);try{const response=await fetch(url,{signal:controller.signal});const result=response.ok?await response.json():null;return{response,result};}finally{clearTimeout(timeoutId);}}
let _matchesMarketCache={};const _MATCHES_CACHE_TTL=90000;function renderMatchLoadError(message,reloadPage=false){const retryLabel=reloadPage?'Sayfayı yenile':'Tekrar dene';const errorMarkup='<div role="alert" style="text-align:center;padding:20px;color:#b54747"><p>'+
message+'</p><button type="button" class="match-load-retry" style="padding:8px 14px;border:0;border-radius:6px;background:#315efb;color:#fff;cursor:pointer">'+
retryLabel+'</button></div>';const tbody=document.getElementById('matchesTableBody');if(tbody){const colspan=currentMarket.includes('1x2')?8:7;tbody.innerHTML='<tr class="loading-row"><td colspan="'+colspan+'">'+errorMarkup+'</td></tr>';const button=tbody.querySelector('.match-load-retry');if(button)button.addEventListener('click',()=>reloadPage?window.location.reload():loadMatches(false,true));}
const cardList=document.getElementById('matchCardList');if(cardList){cardList.innerHTML='<div class="match-card" style="justify-content:center;padding:24px 20px">'+errorMarkup+'</div>';const button=cardList.querySelector('.match-load-retry');if(button)button.addEventListener('click',()=>reloadPage?window.location.reload():loadMatches(false,true));}
const countEl=document.getElementById('matchCount');const mobileCountEl=document.getElementById('mobileMatchCount');if(countEl)countEl.textContent='0';if(mobileCountEl)mobileCountEl.textContent='0';}
async function loadMatches(appendMode=false,forceNetwork=false){if(_liveMode){void 0;return;}
const requestMarket=currentMarket;const requestSource=currentSource;const requestDateFilter=dateFilterMode;const cacheKey=`${requestMarket}|${requestDateFilter}|${requestSource}`;const queueFollowupLoad=(queuedAppendMode,queuedForceNetwork)=>{const previous=_loadMatchesQueued;_loadMatchesQueued={appendMode:!!queuedAppendMode&&(!previous||previous.appendMode),forceNetwork:!!queuedForceNetwork||!!(previous&&previous.forceNetwork)};};if(!_loadMatchesLock&&_loadMatchesPending){console.warn('[Matches] stale pending promise without load lock; discarding');_loadMatchesRequestId+=1;_loadMatchesPending=null;_loadMatchesPendingSince=0;_loadMatchesRequestKey=null;}
if(_loadMatchesLock){const pendingAge=_loadMatchesPendingSince?Date.now()-_loadMatchesPendingSince:Number.POSITIVE_INFINITY;if(!_loadMatchesPending||pendingAge>_LOAD_MATCHES_PENDING_STALE_MS){console.warn('[Matches] stale load lock/pending state; resetting',{hasPending:!!_loadMatchesPending,ageMs:pendingAge});_loadMatchesRequestId+=1;_loadMatchesLock=false;_loadMatchesPending=null;_loadMatchesPendingSince=0;_loadMatchesRequestKey=null;_loadMatchesQueued=null;}else{if(forceNetwork||cacheKey!==_loadMatchesRequestKey){queueFollowupLoad(false,forceNetwork);void 0;}else{void 0;}
return _loadMatchesPending;}}
_loadMatchesLock=true;const cached=_matchesMarketCache[cacheKey];if(forceNetwork){void 0;}
if(!appendMode&&!forceNetwork&&cached&&(Date.now()-cached.ts)<_MATCHES_CACHE_TTL){matches=cached.matches;totalMatchCount=cached.total;hasMoreMatches=false;currentOffset=matches.length;filteredMatches=applySorting(matches);updateTableHeaders();renderMatches(filteredMatches);if(requestMarket.startsWith('dropping')){attachTrendTooltipListeners();}
_loadMatchesLock=false;_loadMatchesPendingSince=0;_loadMatchesRequestKey=null;void 0;return;}
const tbody=document.getElementById('matchesTableBody');const colspan=currentMarket.includes('1x2')?8:7;if(!appendMode){currentOffset=0;matches=[];tbody.innerHTML=`
            <tr class="loading-row">
                <td colspan="${colspan}">
                    <div class="loading-spinner"></div>
                    Yükleniyor...
                </td>
            </tr>
        `;const cardList=document.getElementById('matchCardList');if(cardList){cardList.innerHTML=`
                <div class="match-card" style="justify-content: center; padding: 40px 20px;">
                    <div style="text-align: center; color: #7d848c;">
                        <div class="loading-spinner" style="margin: 0 auto 12px;"></div>
                        <p style="font-size: 13px; margin: 0;">Yükleniyor...</p>
                    </div>
                </div>
            `;}}
updateTableHeaders();const requestId=++_loadMatchesRequestId;_loadMatchesPendingSince=Date.now();_loadMatchesRequestKey=cacheKey;const requestIsCurrent=()=>(requestId===_loadMatchesRequestId&&!_liveMode&&currentMarket===requestMarket&&currentSource===requestSource&&dateFilterMode===requestDateFilter);_loadMatchesPending=(async()=>{try{if(requestMarket.startsWith('dropping')){oddsTrendCache={};}else{oddsTrendCache={};}
let apiUrl;const srcParam=requestSource!=='betfair'?`&source=${requestSource}`:'';if(dateFilterMode==='ALL'){apiUrl=`/api/matches?market=${requestMarket}&date_filter=today_future&bulk=1${srcParam}`;}else if(dateFilterMode==='YESTERDAY'){apiUrl=`/api/matches?market=${requestMarket}&date_filter=yesterday&bulk=1${srcParam}`;}else if(dateFilterMode==='TODAY'){apiUrl=`/api/matches?market=${requestMarket}&date_filter=today&bulk=1${srcParam}`;}else if(dateFilterMode&&dateFilterMode.startsWith('PAST_')){const daysBack=dateFilterMode.split('_')[1];apiUrl=`/api/matches?market=${requestMarket}&date_filter=d-${daysBack}&bulk=1${srcParam}`;}else{apiUrl=`/api/matches?market=${requestMarket}&date_filter=today_future&bulk=1${srcParam}`;}
void 0;const startTime=performance.now();let matchPayload;try{matchPayload=await _fetchMatchesWithTimeout(apiUrl,12000);}catch(fetchErr){if(fetchErr.name==='AbortError'){console.warn('[Matches] Fetch timeout (12s), retrying...');await new Promise(r=>setTimeout(r,1500));matchPayload=await _fetchMatchesWithTimeout(apiUrl,20000);}else{throw fetchErr;}}
if(requestId!==_loadMatchesRequestId){void 0;return;}
const response=matchPayload.response;if(response.status===403){if(!requestIsCurrent()){if(!_liveMode)queueFollowupLoad(false,forceNetwork);return;}
console.warn('[Matches] 403 License error');renderMatchLoadError('Lisans doğrulanamadı. Yeniden giriş yapmayı deneyin.',true);return;}
if(!response.ok){throw new Error(`HTTP ${response.status}`);}
const result=matchPayload.result;const responseMatches=Array.isArray(result)?result:(result&&Array.isArray(result.matches)?result.matches:null);if(!responseMatches){throw new Error('Invalid match response');}
const elapsed=Math.round(performance.now()-startTime);void 0;if(!requestIsCurrent()){void 0;if(!_liveMode)queueFollowupLoad(false,forceNetwork);return;}
if(result&&!Array.isArray(result)&&result.finished_scores){_finishedScores=result.finished_scores;}
matches=responseMatches;totalMatchCount=result&&!Array.isArray(result)&&Number.isFinite(result.total)?result.total:matches.length;hasMoreMatches=false;currentOffset=matches.length;_matchesMarketCache[cacheKey]={matches:matches,total:totalMatchCount,ts:Date.now()};filteredMatches=applySorting(matches);renderMatches(filteredMatches);if(currentMarket.startsWith('dropping')){attachTrendTooltipListeners();}}catch(error){if(requestId!==_loadMatchesRequestId){void 0;return;}
if(!requestIsCurrent()){void 0;if(!_liveMode)queueFollowupLoad(false,forceNetwork);return;}
console.error('Error loading matches:',error);matches=[];filteredMatches=[];renderMatchLoadError('Maçlar yüklenemedi. Bağlantınızı kontrol edip tekrar deneyin.');}finally{if(requestId===_loadMatchesRequestId){_loadMatchesLock=false;_loadMatchesPending=null;_loadMatchesPendingSince=0;_loadMatchesRequestKey=null;const queuedLoad=_loadMatchesQueued;_loadMatchesQueued=null;if(queuedLoad&&!_liveMode){void 0;setTimeout(()=>{if(!_liveMode)loadMatches(queuedLoad.appendMode,queuedLoad.forceNetwork);},0);}}}})();return _loadMatchesPending;}
async function loadAllRemainingMatches(){const maxPages=50;let page=0;let allNewMatches=[];while(hasMoreMatches&&page<maxPages){page++;try{let apiUrl=`/api/matches?market=${currentMarket}&limit=${matchesDisplayCount}&offset=${currentOffset}`;if(dateFilterMode==='YESTERDAY'){apiUrl+='&date_filter=yesterday';}else if(dateFilterMode==='TODAY'){apiUrl+='&date_filter=today';}else if(dateFilterMode&&dateFilterMode.startsWith('PAST_')){apiUrl+=`&date_filter=d-${dateFilterMode.split('_')[1]}`;}
const response=await fetch(apiUrl);const result=await response.json();if(result.matches!==undefined){const newMatches=result.matches||[];hasMoreMatches=result.has_more||false;if(newMatches.length===0){hasMoreMatches=false;break;}
allNewMatches=[...allNewMatches,...newMatches];currentOffset+=newMatches.length;}else{break;}}catch(error){console.error('[Background] Error loading page',page,error);break;}}
if(allNewMatches.length>0){matches=[...matches,...allNewMatches];filteredMatches=applySorting(matches);renderMatches(filteredMatches);if(currentMarket.startsWith('dropping')){attachTrendTooltipListeners();}}
void 0;}
function updateTableHeaders(){const table=document.querySelector('.matches-table');const thead=document.querySelector('.matches-table thead tr');const colgroup=document.querySelector('.matches-table colgroup');if(!thead||!table)return;const getArrow=(col)=>{if(currentSortColumn===col){return currentSortDirection==='asc'?'↑':'↓';}
return'';};const getActiveClass=(col)=>currentSortColumn===col?'active':'';if(currentMarket.includes('1x2')){table.setAttribute('data-selection-count','3');if(colgroup){colgroup.innerHTML=`
                <col class="col-fav">
                <col class="col-date">
                <col class="col-league">
                <col class="col-match">
                <col class="col-selection">
                <col class="col-selection">
                <col class="col-selection">
                <col class="col-volume">
            `;}
thead.innerHTML=`
            <th class="col-fav"></th>
            <th class="col-date sortable ${getActiveClass('date')}" data-sort="date" onclick="sortByColumn('date')">${_t('app.tbl.date','TARİH')} <span class="sort-arrow">${getArrow('date')}</span></th>
            <th class="col-league sortable ${getActiveClass('league')}" data-sort="league" onclick="sortByColumn('league')">${_t('app.tbl.league','LİG')} <span class="sort-arrow">${getArrow('league')}</span></th>
            <th class="col-match sortable ${getActiveClass('match')}" data-sort="match" onclick="sortByColumn('match')">${_t('app.tbl.match','MAÇ')} <span class="sort-arrow">${getArrow('match')}</span></th>
            <th class="col-selection sortable ${getActiveClass('sel1')}" data-sort="sel1" onclick="sortByColumn('sel1')">1 <span class="sort-arrow">${getArrow('sel1')}</span></th>
            <th class="col-selection sortable ${getActiveClass('selX')}" data-sort="selX" onclick="sortByColumn('selX')">X <span class="sort-arrow">${getArrow('selX')}</span></th>
            <th class="col-selection sortable ${getActiveClass('sel2')}" data-sort="sel2" onclick="sortByColumn('sel2')">2 <span class="sort-arrow">${getArrow('sel2')}</span></th>
            <th class="col-volume sortable ${getActiveClass('volume')}" data-sort="volume" onclick="sortByColumn('volume')">${_t('app.tbl.volume','HACİM')} <span class="sort-arrow">${getArrow('volume')}</span></th>
        `;}else if(currentMarket.includes('ou25')){table.setAttribute('data-selection-count','2');if(colgroup){colgroup.innerHTML=`
                <col class="col-fav">
                <col class="col-date">
                <col class="col-league">
                <col class="col-match">
                <col class="col-selection">
                <col class="col-selection">
                <col class="col-volume">
            `;}
thead.innerHTML=`
            <th class="col-fav"></th>
            <th class="col-date sortable ${getActiveClass('date')}" data-sort="date" onclick="sortByColumn('date')">${_t('app.tbl.date','TARİH')} <span class="sort-arrow">${getArrow('date')}</span></th>
            <th class="col-league sortable ${getActiveClass('league')}" data-sort="league" onclick="sortByColumn('league')">${_t('app.tbl.league','LİG')} <span class="sort-arrow">${getArrow('league')}</span></th>
            <th class="col-match sortable ${getActiveClass('match')}" data-sort="match" onclick="sortByColumn('match')">${_t('app.tbl.match','MAÇ')} <span class="sort-arrow">${getArrow('match')}</span></th>
            <th class="col-selection sortable ${getActiveClass('sel1')}" data-sort="sel1" onclick="sortByColumn('sel1')">${_t('app.j.sel_alt','ALT')} <span class="sort-arrow">${getArrow('sel1')}</span></th>
            <th class="col-selection sortable ${getActiveClass('sel2')}" data-sort="sel2" onclick="sortByColumn('sel2')">${_t('app.j.sel_ust','ÜST')} <span class="sort-arrow">${getArrow('sel2')}</span></th>
            <th class="col-volume sortable ${getActiveClass('volume')}" data-sort="volume" onclick="sortByColumn('volume')">${_t('app.tbl.volume','HACİM')} <span class="sort-arrow">${getArrow('volume')}</span></th>
        `;}else if(currentMarket.includes('btts')){table.setAttribute('data-selection-count','2');if(colgroup){colgroup.innerHTML=`
                <col class="col-fav">
                <col class="col-date">
                <col class="col-league">
                <col class="col-match">
                <col class="col-selection">
                <col class="col-selection">
                <col class="col-volume">
            `;}
thead.innerHTML=`
            <th class="col-fav"></th>
            <th class="col-date sortable ${getActiveClass('date')}" data-sort="date" onclick="sortByColumn('date')">${_t('app.tbl.date','TARİH')} <span class="sort-arrow">${getArrow('date')}</span></th>
            <th class="col-league sortable ${getActiveClass('league')}" data-sort="league" onclick="sortByColumn('league')">${_t('app.tbl.league','LİG')} <span class="sort-arrow">${getArrow('league')}</span></th>
            <th class="col-match sortable ${getActiveClass('match')}" data-sort="match" onclick="sortByColumn('match')">${_t('app.tbl.match','MAÇ')} <span class="sort-arrow">${getArrow('match')}</span></th>
            <th class="col-selection sortable ${getActiveClass('sel1')}" data-sort="sel1" onclick="sortByColumn('sel1')">YES <span class="sort-arrow">${getArrow('sel1')}</span></th>
            <th class="col-selection sortable ${getActiveClass('sel2')}" data-sort="sel2" onclick="sortByColumn('sel2')">NO <span class="sort-arrow">${getArrow('sel2')}</span></th>
            <th class="col-volume sortable ${getActiveClass('volume')}" data-sort="volume" onclick="sortByColumn('volume')">${_t('app.tbl.volume','HACİM')} <span class="sort-arrow">${getArrow('volume')}</span></th>
        `;}}
function getColorClass(pctValue){const num=parseFloat(String(pctValue).replace(/[^0-9.]/g,''));if(isNaN(num))return'color-normal';if(num>=90)return'color-red';if(num>=70)return'color-orange';if(num>=50)return'color-yellow';return'color-normal';}
function getDonutColor(pctValue){return'#22c55e';}
function getMoneyColor(moneyStr){if(!moneyStr)return'money-low';const numStr=String(moneyStr).replace(/[£€$,\s]/g,'');const num=parseFloat(numStr);if(isNaN(num))return'money-low';return num>=3000?'money-high':'money-low';}
function renderDonutSVG(percent,size=48){const num=parseFloat(String(percent).replace(/[^0-9.]/g,''))||0;const strokeWidth=size>40?5:4;const radius=(size-strokeWidth*2)/2;const circumference=2*Math.PI*radius;const offset=circumference-(num/100)*circumference;const trackColor='#2a2e33';const isHigh=num>=50;const fillColor=isHigh?'#22c55e':'#1a1d21';const textColor=isHigh?'#ffffff':'#9ca3af';const fontSize=size>40?11:9;return`
        <svg class="donut-svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
            <circle class="ring-track" cx="${size/2}" cy="${size/2}" r="${radius}" fill="none" stroke="${trackColor}" stroke-width="${strokeWidth}"/>
            <circle class="ring-fill" cx="${size/2}" cy="${size/2}" r="${radius}" fill="none" stroke="${fillColor}" stroke-width="${strokeWidth}"
                stroke-dasharray="${circumference}" stroke-dashoffset="${offset}"
                stroke-linecap="round" transform="rotate(-90 ${size/2} ${size/2})"/>
            <text class="percent-text" x="${size/2}" y="${size/2}" text-anchor="middle" dominant-baseline="central" 
                fill="${textColor}" font-size="${fontSize}" font-weight="600">${num.toFixed(0)}%</text>
        </svg>
    `;}
function renderMoneywayBlock(label,percent,odds,money){const donut=renderDonutSVG(percent,52);return`
        <div class="mw-outcome-block">
            <div class="mw-info-stack">
                <div class="mw-odds">${formatOdds(odds)}</div>
                ${money ? `<div class="mw-money">${formatVolume(money)}</div>` : ''}
            </div>
            <div class="mw-donut">${donut}</div>
        </div>
    `;}
function formatPct(val){if(!val||val==='-')return'-';const cleaned=String(val).replace(/[%\s]/g,'');const num=parseFloat(cleaned);if(isNaN(num))return'-';return num.toFixed(1)+'%';}
function cleanPct(val){if(!val||val==='-')return'';return String(val).replace(/%/g,'').trim();}
async function fetchAnalysisMatchHashes(){try{const resp=await fetch('/api/analyses/match-hashes');if(resp.ok){const data=await resp.json();_analysisMatchHashes=Array.isArray(data)?data:(data.hashes||[]);_analysisHashesFetched=true;const ac=(data&&typeof data.active_count==='number')?data.active_count:0;document.querySelectorAll('.analysis-active-badge').forEach(el=>{el.textContent=ac;el.style.display=ac>0?'':'none';});}}catch(e){}}
function getAnalysisStarHtml(matchId){if(!matchId||!_analysisMatchHashes.length)return'';if(_analysisMatchHashes.indexOf(matchId)===-1)return'';return'<span class="analysis-star" title="Bu maç ile ilgili analiz mevcut" onclick="event.stopPropagation(); openDeferredTrendsModal(\'analysis\');">★</span>';}
function _renderMatchRow(match,idx){const d=match.details||match.odds||{};const _star=getAnalysisStarHtml(match.match_id);const isDropping=currentMarket.startsWith('dropping');const isMoneyway=currentMarket.startsWith('moneyway');var _testBlur=(window.userPlan==='test'&&(currentMarket==='moneyway_1x2'||currentMarket==='dropping_1x2')&&!_isTestFreeMatch(match.match_id));var _blurCls=_testBlur?' test-blur-values':'';var _rowExtra=_testBlur?' test-locked-row-click':'';const _favTd=_buildFavCell(match);if(currentMarket.includes('1x2')){if(isMoneyway){const _lockSvg='<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#4a5068" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>';const _lockCell='<div class="test-lock-cell">'+_lockSvg+'</div>';const block1=_testBlur?'':renderMoneywayBlock('1',d.Pct1,d.Odds1||d['1'],d.Amt1);const blockX=_testBlur?'':renderMoneywayBlock('X',d.PctX,d.OddsX||d['X'],d.AmtX);const block2=_testBlur?'':renderMoneywayBlock('2',d.Pct2,d.Odds2||d['2'],d.Amt2);const _mwInner=_testBlur?(_lockCell+_lockCell+_lockCell):(block1+blockX+block2);const _mwVol=formatVolume(d.Volume);const matchStatus=getMatchStatus(match.date);const deskCapsule=getMatchLiveCapsuleDT(match.date,match.home_team,match.away_team,match.match_id);return`
                <tr class="${_rowExtra}" data-index="${idx}" onclick="openMatchModal(${idx})">
                    ${_favTd}
                    <td class="match-date">${deskCapsule || formatDateTwoLine(match.date)}</td>
                    <td class="match-league" title="${match.league || ''}">${match.league || '-'}</td>
                    <td class="match-teams">${match.home_team}<span class="vs">-</span>${match.away_team}${!deskCapsule ? matchStatus : ''}${_star}</td>
                    <td class="mw-outcomes-cell" colspan="3">
                        <div class="mw-grid mw-grid-3">
                            ${_mwInner}
                        </div>
                    </td>
                    <td class="volume-cell">${_mwVol}</td>
                </tr>
            `;}else{const _dpLockSvg='<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#4a5068" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>';const _dpLock='<div class="test-lock-cell">'+_dpLockSvg+'</div>';const trend1Data=buildTrendDataFromMatch(d.Odds1||d['1'],d.PrevOdds1||d.Odds1_prev,d.Trend1);const trendXData=buildTrendDataFromMatch(d.OddsX||d['X'],d.PrevOddsX||d.OddsX_prev,d.TrendX);const trend2Data=buildTrendDataFromMatch(d.Odds2||d['2'],d.PrevOdds2||d.Odds2_prev,d.Trend2);const cell1=_testBlur?'':renderDrop1X2Cell('1',d.Odds1||d['1'],trend1Data);const cellX=_testBlur?'':renderDrop1X2Cell('X',d.OddsX||d['X'],trendXData);const cell2=_testBlur?'':renderDrop1X2Cell('2',d.Odds2||d['2'],trend2Data);const _dpVol=formatVolume(d.Volume);const matchStatus=getMatchStatus(match.date);const deskCapsule=getMatchLiveCapsuleDT(match.date,match.home_team,match.away_team,match.match_id);return`
                <tr class="dropping-1x2-row${_rowExtra}" data-index="${idx}" onclick="openMatchModal(${idx})">
                    ${_favTd}
                    <td class="match-date">${deskCapsule || formatDateTwoLine(match.date)}</td>
                    <td class="match-league" title="${match.league || ''}">${match.league || '-'}</td>
                    <td class="match-teams">${match.home_team}<span class="vs">-</span>${match.away_team}${!deskCapsule ? matchStatus : ''}${_star}</td>
                    <td class="drop-cell">${_testBlur ? _dpLock : cell1}</td>
                    <td class="drop-cell">${_testBlur ? _dpLock : cellX}</td>
                    <td class="drop-cell">${_testBlur ? _dpLock : cell2}</td>
                    <td class="volume-cell">${_dpVol}</td>
                </tr>
            `;}}else if(currentMarket.includes('ou25')){if(isMoneyway){const blockUnder=renderMoneywayBlock(_t('app.dyn.alt','Alt'),d.PctUnder,d.Under,d.AmtUnder);const blockOver=renderMoneywayBlock(_t('app.dyn.ust','Üst'),d.PctOver,d.Over,d.AmtOver);const matchStatus=getMatchStatus(match.date);const deskCapsule=getMatchLiveCapsuleDT(match.date,match.home_team,match.away_team,match.match_id);return`
                <tr data-index="${idx}" onclick="openMatchModal(${idx})">
                    ${_favTd}
                    <td class="match-date">${deskCapsule || formatDateTwoLine(match.date)}</td>
                    <td class="match-league" title="${match.league || ''}">${match.league || '-'}</td>
                    <td class="match-teams">${match.home_team}<span class="vs">-</span>${match.away_team}${!deskCapsule ? matchStatus : ''}${_star}</td>
                    <td class="mw-outcomes-cell" colspan="2">
                        <div class="mw-grid mw-grid-2">
                            ${blockUnder}
                            ${blockOver}
                        </div>
                    </td>
                    <td class="volume-cell">${formatVolume(d.Volume)}</td>
                </tr>
            `;}else{const trendUnderData=buildTrendDataFromMatch(d.Under,d.PrevUnder||d.Under_prev,d.TrendUnder);const trendOverData=buildTrendDataFromMatch(d.Over,d.PrevOver||d.Over_prev,d.TrendOver);const cellUnder=renderOddsWithTrend(d.Under,trendUnderData);const cellOver=renderOddsWithTrend(d.Over,trendOverData);const matchStatus=getMatchStatus(match.date);const deskCapsule=getMatchLiveCapsuleDT(match.date,match.home_team,match.away_team,match.match_id);return`
                <tr data-index="${idx}" onclick="openMatchModal(${idx})">
                    ${_favTd}
                    <td class="match-date">${deskCapsule || formatDateTwoLine(match.date)}</td>
                    <td class="match-league" title="${match.league || ''}">${match.league || '-'}</td>
                    <td class="match-teams">${match.home_team}<span class="vs">-</span>${match.away_team}${!deskCapsule ? matchStatus : ''}${_star}</td>
                    <td class="selection-cell"><div>${cellUnder}</div></td>
                    <td class="selection-cell"><div>${cellOver}</div></td>
                    <td class="volume-cell">${formatVolume(d.Volume)}</td>
                </tr>
            `;}}else{if(isMoneyway){const blockYes=renderMoneywayBlock(_t('app.dyn.evet','Evet'),d.PctYes,d.OddsYes||d.Yes,d.AmtYes);const blockNo=renderMoneywayBlock(_t('app.dyn.hayir','Hayır'),d.PctNo,d.OddsNo||d.No,d.AmtNo);const matchStatus=getMatchStatus(match.date);const deskCapsule=getMatchLiveCapsuleDT(match.date,match.home_team,match.away_team,match.match_id);return`
                <tr data-index="${idx}" onclick="openMatchModal(${idx})">
                    ${_favTd}
                    <td class="match-date">${deskCapsule || formatDateTwoLine(match.date)}</td>
                    <td class="match-league" title="${match.league || ''}">${match.league || '-'}</td>
                    <td class="match-teams">${match.home_team}<span class="vs">-</span>${match.away_team}${!deskCapsule ? matchStatus : ''}${_star}</td>
                    <td class="mw-outcomes-cell" colspan="2">
                        <div class="mw-grid mw-grid-2">
                            ${blockYes}
                            ${blockNo}
                        </div>
                    </td>
                    <td class="volume-cell">${formatVolume(d.Volume)}</td>
                </tr>
            `;}else{const trendYesData=buildTrendDataFromMatch(d.OddsYes||d.Yes,d.PrevYes||d.OddsYes_prev||d.Yes_prev,d.TrendYes);const trendNoData=buildTrendDataFromMatch(d.OddsNo||d.No,d.PrevNo||d.OddsNo_prev||d.No_prev,d.TrendNo);const cellYes=renderOddsWithTrend(d.OddsYes||d.Yes,trendYesData);const cellNo=renderOddsWithTrend(d.OddsNo||d.No,trendNoData);const matchStatus=getMatchStatus(match.date);const deskCapsule=getMatchLiveCapsuleDT(match.date,match.home_team,match.away_team,match.match_id);return`
                <tr data-index="${idx}" onclick="openMatchModal(${idx})">
                    ${_favTd}
                    <td class="match-date">${deskCapsule || formatDateTwoLine(match.date)}</td>
                    <td class="match-league" title="${match.league || ''}">${match.league || '-'}</td>
                    <td class="match-teams">${match.home_team}<span class="vs">-</span>${match.away_team}${!deskCapsule ? matchStatus : ''}${_star}</td>
                    <td class="selection-cell"><div>${cellYes}</div></td>
                    <td class="selection-cell"><div>${cellNo}</div></td>
                    <td class="volume-cell">${formatVolume(d.Volume)}</td>
                </tr>
            `;}}}
function _renderMoreDesktop(){if(typeof _liveMode!=='undefined'&&_liveMode)return;if(_renderedCount>=_allFilteredMatches.length)return;const tbody=document.getElementById('matchesTableBody');if(!tbody)return;const end=Math.min(_renderedCount+_RENDER_BATCH,_allFilteredMatches.length);let html='';for(let i=_renderedCount;i<end;i++){html+=_renderMatchRow(_allFilteredMatches[i],i);}
var _prevEnd=_renderedCount;tbody.insertAdjacentHTML('beforeend',html);_renderedCount=end;_updateRenderedCount();if(currentMarket.startsWith('dropping')){setTimeout(()=>attachTrendTooltipListeners(),50);}
if(_favFilterActive)setTimeout(()=>_applyFavoritesFilter(),10);}
function _renderMoreMobile(){if(typeof _liveMode!=='undefined'&&_liveMode)return;if(_renderedCount>=_allFilteredMatches.length)return;const cardList=document.getElementById('matchCardList');if(!cardList)return;const end=Math.min(_renderedCount+_RENDER_BATCH,_allFilteredMatches.length);let html='';const isDropping=currentMarket.startsWith('dropping');const isMoneyway=currentMarket.startsWith('moneyway');for(let i=_renderedCount;i<end;i++){const match=_allFilteredMatches[i];const d=match.details||match.odds||{};const volume=formatVolumeCompact(d.Volume);const _mStar=getAnalysisStarHtml(match.match_id);let dateStr='';try{const dt=dayjs(match.date).tz('Europe/Istanbul');const day=dt.format('D');const monthIdx=dt.month();const time=dt.format('HH:mm');dateStr=`${day} ${_tms(monthIdx)} ${time}`;}catch(e){dateStr=match.date||'';}
if(isMoneyway){html+=renderMobileMoneywayCard(match,i,d,volume,dateStr,_mStar);}else if(isDropping){html+=renderMobileOddsCard(match,i,d,volume,dateStr,_mStar);}else{const matchStatus=getMatchStatus(match.date);const _mk=_getMatchKey(match);const _isFav=_userFavorites.has(_mk);const _fc=_favCounts[_mk]||0;html+=`
                <div class="match-card" data-index="${i}" onclick="openMatchModal(${i})">
                    ${_mobileFavLine(_mk, _isFav, _fc)}
                    <div class="match-card-left">
                        <div class="match-card-teams">${match.home_team}<span class="vs">-</span>${match.away_team}${_mStar}</div>
                        <div class="match-card-meta">
                            <span class="match-card-league">${match.league || '-'}</span>
                            <span class="match-card-separator">•</span>
                            <span class="match-card-datetime">${dateStr}</span>
                        </div>
                    </div>
                    <div class="match-card-right">
                        <span class="match-card-volume">${volume}</span>
                        <span class="match-card-arrow">›</span>
                    </div>
                </div>
            `;}}
var _prevEndM=_renderedCount;cardList.insertAdjacentHTML('beforeend',html);_renderedCount=end;_updateRenderedCount();if(_favFilterActive)setTimeout(()=>_applyFavoritesFilter(),10);}
function _updateRenderedCount(){const countEl=document.getElementById('matchCount');const mobileCountEl=document.getElementById('mobileMatchCount');const total=_allFilteredMatches.length;const shown=Math.min(_renderedCount,total);const text=shown<total?`${shown} / ${total}`:`${total}`;if(countEl)countEl.textContent=text;if(mobileCountEl)mobileCountEl.textContent=text;}
function _setupInfiniteScroll(){if(_scrollListenerAttached)return;_scrollListenerAttached=true;var container=document.querySelector('.table-container');if(container){container.addEventListener('scroll',function(){if(_renderedCount>=_allFilteredMatches.length)return;var scrollTop=container.scrollTop;var clientH=container.clientHeight;var scrollH=container.scrollHeight;if(scrollTop+clientH>=scrollH-300){var isMobile=window.innerWidth<=768;if(isMobile){_renderMoreMobile();}else{_renderMoreDesktop();}}},{passive:true});}
window.addEventListener('scroll',function(){if(_renderedCount>=_allFilteredMatches.length)return;var scrollY=window.scrollY||window.pageYOffset;var windowH=window.innerHeight;var docH=document.documentElement.scrollHeight;if(scrollY+windowH>=docH-300){var isMobile=window.innerWidth<=768;if(isMobile){_renderMoreMobile();}else{_renderMoreDesktop();}}},{passive:true});}
function renderMatches(data){if(typeof _liveMode!=='undefined'&&_liveMode)return;if(_isTestLockedMarket(currentMarket)){_showTestLockedToast();var _fallbackTab=document.querySelector('.market-tabs .tab[data-market="moneyway_1x2"]');if(_fallbackTab)_fallbackTab.click();return;}
void 0;_renderedCount=0;const tbody=document.getElementById('matchesTableBody');const countEl=document.getElementById('matchCount');const mobileCountEl=document.getElementById('mobileMatchCount');if(data.length===0){const colspan=currentMarket.includes('1x2')?8:7;const emptyMessage=isClientMode?"Bu market için veri bulunamadı. Scraper'ın Supabase'e veri gönderdiğinden emin olun.":"No matches found for this market. Click 'Scrape Now' to fetch data.";tbody.innerHTML=`
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
        `;if(countEl)countEl.textContent='0';if(mobileCountEl)mobileCountEl.textContent='0';return;}
tbody.innerHTML='';_allFilteredMatches=data;const firstBatch=data.slice(0,_RENDER_BATCH);let html='';for(var ri=0;ri<firstBatch.length;ri++){html+=_renderMatchRow(firstBatch[ri],ri);}
tbody.innerHTML=html;_renderedCount=firstBatch.length;_updateRenderedCount();_setupInfiniteScroll();if(currentMarket.startsWith('dropping')){setTimeout(()=>attachTrendTooltipListeners(),50);}
loadFavoriteCounts();if(_favFilterActive)setTimeout(()=>_applyFavoritesFilter(),50);}
function loadMoreMatches(){if(hasMoreMatches&&!_loadMatchesLock){loadMatches(true);}}
function isMobileView(){return window.innerWidth<=768;}
function renderMobileMatchCards(data){if(typeof _liveMode!=='undefined'&&_liveMode)return;if(_isTestLockedMarket(currentMarket)){_showTestLockedToast();_mobCurCat='moneyway';_mobCurMkt='1x2';document.querySelectorAll('#mobCatRow .mob-tab').forEach(function(b){b.classList.toggle('active',b.getAttribute('data-cat')==='moneyway');});_updateMobMktRow('moneyway');setMobileGroup('moneyway');return;}
const cardList=document.getElementById('matchCardList');if(!cardList)return;_allFilteredMatches=data;_renderedCount=0;if(data.length===0){cardList.innerHTML=`
            <div class="match-card" style="justify-content: center; padding: 40px 20px;">
                <div style="text-align: center; color: #7d848c;">
                    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="opacity: 0.4; margin-bottom: 8px;">
                        <circle cx="12" cy="12" r="10"/>
                        <path d="M12 6v6l4 2"/>
                    </svg>
                    <p style="font-size: 12px;">Bu market için veri bulunamadı</p>
                </div>
            </div>
        `;_updateRenderedCount();return;}
cardList.innerHTML='';_renderMoreMobile();_setupInfiniteScroll();}
function _mobileFavLine(mk,isFav,count){var txt=(count>0?count:0)+(window.SXFI18n?window.SXFI18n.t('app.dyn.kisi')+' '+window.SXFI18n.t('app.dyn.takip_ediyor'):' kişi takip ediyor');return'<div class="mobile-fav-line"><span class="fav-heart '+(isFav?'fav-active':'')+'" data-matchkey="'+mk.replace(/"/g,'&quot;')+'" onclick="event.stopPropagation(); toggleFavorite(this);">'+_heartSvg+'</span><span class="mobile-fav-count" data-matchkey="'+mk.replace(/"/g,'&quot;')+'">'+txt+'</span></div>';}
function renderMobileMoneywayCard(match,idx,d,volume,dateStr,starHtml){let oddsBlocks='';var _mTestBlur=(window.userPlan==='test'&&(currentMarket==='moneyway_1x2'||currentMarket==='dropping_1x2')&&!_isTestFreeMatch(match.match_id));var _mBlurCls=_mTestBlur?' test-blur-values':'';var tv=d.Volume;if(currentMarket.includes('1x2')){oddsBlocks=`
            ${renderMobileMoneywayBlock('1', d.Odds1 || d['1'], d.Pct1, tv)}
            ${renderMobileMoneywayBlock('X', d.OddsX || d['X'], d.PctX, tv)}
            ${renderMobileMoneywayBlock('2', d.Odds2 || d['2'], d.Pct2, tv)}
        `;}else if(currentMarket.includes('ou25')){oddsBlocks=`
            ${renderMobileMoneywayBlock(_t('app.dyn.alt','Alt'), d.Under, d.PctUnder, tv)}
            ${renderMobileMoneywayBlock(_t('app.dyn.ust','Üst'), d.Over, d.PctOver, tv)}
        `;}else{oddsBlocks=`
            ${renderMobileMoneywayBlock(_t('app.dyn.evet','Evet'), d.OddsYes || d.Yes, d.PctYes, tv)}
            ${renderMobileMoneywayBlock(_t('app.dyn.hayir','Hayır'), d.OddsNo || d.No, d.PctNo, tv)}
        `;}
const blockCount=currentMarket.includes('1x2')?'three':'two';const matchStatus=getMatchStatus(match.date);const liveCapsule=getMatchLiveCapsule(match.date,match.home_team,match.away_team,match.match_id);const _mk=_getMatchKey(match);const _isFav=_userFavorites.has(_mk);const _fc=_favCounts[_mk]||0;const _mobLockSvg='<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#4a5068" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>';const _mobLockCell='<div class="test-lock-cell test-lock-mob">'+_mobLockSvg+'</div>';const _mwGrayRow=_mTestBlur?(_mobLockCell+_mobLockCell+(blockCount==='three'?_mobLockCell:'')):oddsBlocks;return`
        <div class="match-card odds-card moneyway-card" data-index="${idx}" onclick="openMatchModal(${idx})">
            ${_mobileFavLine(_mk, _isFav, _fc)}
            <div class="odds-card-header">
                <div class="odds-card-teams">${match.home_team} – ${match.away_team}${liveCapsule || matchStatus}${starHtml || ''}</div>
                <div class="odds-card-volume">${volume}</div>
            </div>
            <div class="odds-card-meta">
                <span>${match.league || '-'}</span>
                <span class="meta-sep">•</span>
                <span>${dateStr}</span>
            </div>
            <div class="odds-card-row ${blockCount}">
                ${_mwGrayRow}
            </div>
        </div>
    `;}
function buildCardInsight(d,market){var parts=[];if(market.includes('1x2')){var p1=parseFloat(String(d.PctHome||d.Pct1||d.PctYes||'0').replace('%',''));var pX=parseFloat(String(d.PctDraw||d.PctX||'0').replace('%',''));var p2=parseFloat(String(d.PctAway||d.Pct2||d.PctNo||'0').replace('%',''));if(p1>0||pX>0||p2>0){var best=Math.max(p1,pX,p2);var leader=best===p1?'1':(best===pX?'X':'2');parts.push('<span class="insight-tag">Favori: <span class="insight-val">'+leader+'</span></span>');parts.push('<span class="insight-tag">Pay: <span class="insight-val positive">'+best.toFixed(0)+'%</span></span>');var spread=(best-Math.min(p1>0?p1:999,pX>0?pX:999,p2>0?p2:999)).toFixed(0);var label=parseInt(spread)>30?'Güçlü favori':(parseInt(spread)>10?'Favori açık':'Dengeli');parts.push('<span class="insight-label">'+label+'</span>');}}else if(market.includes('2.5')){var pOver=parseFloat(String(d.PctYes||d.PctOver||'0').replace('%',''));var pUnder=parseFloat(String(d.PctNo||d.PctUnder||'0').replace('%',''));if(pOver>0||pUnder>0){var lbl=pOver>pUnder?_t('app.dyn.ust','Üst'):_t('app.dyn.alt','Alt');var pct=Math.max(pOver,pUnder);parts.push('<span class="insight-tag">Lider: <span class="insight-val">'+lbl+'</span></span>');parts.push('<span class="insight-tag">Pay: <span class="insight-val positive">'+pct.toFixed(0)+'%</span></span>');}}else if(market.includes('kg')){var pY=parseFloat(String(d.PctYes||'0').replace('%',''));var pN=parseFloat(String(d.PctNo||'0').replace('%',''));if(pY>0||pN>0){var lbl=pY>pN?_t('app.dyn.evet','Evet'):_t('app.dyn.hayir','Hayır');var pct=Math.max(pY,pN);parts.push('<span class="insight-tag">KG: <span class="insight-val">'+lbl+'</span></span>');parts.push('<span class="insight-tag">Pay: <span class="insight-val positive">'+pct.toFixed(0)+'%</span></span>');}}
if(parts.length===0)return'';return'<div class="odds-card-insight">'+parts.join('')+'</div>';}
function _calcBlockMoney(pctNum,totalVol){if(!totalVol)return'';var rawVol=String(totalVol).replace(/[£€$,\s]/g,'');var mult=1;if(rawVol.toUpperCase().includes('M')){mult=1000000;rawVol=rawVol.replace(/M/gi,'');}
else if(rawVol.toUpperCase().includes('K')){mult=1000;rawVol=rawVol.replace(/K/gi,'');}
var totalNum=parseFloat(rawVol)*mult;if(isNaN(totalNum)||totalNum<=0)return'';var bm=totalNum*pctNum/100;return bm>=1000000?'£'+(bm/1000000).toFixed(1)+'M':bm>=1000?'£'+(bm/1000).toFixed(1)+'k':'£'+Math.round(bm);}
function renderMobileMoneywayBlock(label,oddsValue,pctValue,totalVol){const odds=formatOdds(oddsValue);var pct='';var moneyStr='';if(pctValue!==null&&pctValue!==undefined){var pctNum=parseFloat(String(pctValue).replace('%',''));if(!isNaN(pctNum)){pct=pctNum.toFixed(0)+'%';moneyStr=_calcBlockMoney(pctNum,totalVol);}}
return'<div class="odds-block mw-block">'+'<div class="odds-block-label">'+label+'</div>'+'<div class="ob-data-row">'+'<span class="ob-odds">'+odds+'</span>'+
(moneyStr?'<span class="ob-money">'+moneyStr+'</span>':'')+
(pct?'<span class="ob-pct">'+pct+'</span>':'')+'</div>'+'</div>';}
function renderMobileOddsCard(match,idx,d,volume,dateStr,starHtml){let oddsBlocks='';var _oTestBlur=(window.userPlan==='test'&&(currentMarket==='moneyway_1x2'||currentMarket==='dropping_1x2')&&!_isTestFreeMatch(match.match_id));var _oBlurCls=_oTestBlur?' test-blur-values':'';if(currentMarket.includes('1x2')){const trend1=buildTrendDataFromMatch(d.Odds1||d['1'],d.PrevOdds1||d.Odds1_prev,d.Trend1,d.DropPct1);const trendX=buildTrendDataFromMatch(d.OddsX||d['X'],d.PrevOddsX||d.OddsX_prev,d.TrendX,d.DropPctX);const trend2=buildTrendDataFromMatch(d.Odds2||d['2'],d.PrevOdds2||d.Odds2_prev,d.Trend2,d.DropPct2);oddsBlocks=`
            ${renderMobileOddsBlock('1', d.Odds1 || d['1'], trend1)}
            ${renderMobileOddsBlock('X', d.OddsX || d['X'], trendX)}
            ${renderMobileOddsBlock('2', d.Odds2 || d['2'], trend2)}
        `;}else if(currentMarket.includes('ou25')){const trendUnder=buildTrendDataFromMatch(d.Under,d.PrevUnder||d.Under_prev,d.TrendUnder,d.DropPctUnder);const trendOver=buildTrendDataFromMatch(d.Over,d.PrevOver||d.Over_prev,d.TrendOver,d.DropPctOver);oddsBlocks=`
            ${renderMobileOddsBlock(_t('app.dyn.alt','Alt'), d.Under, trendUnder)}
            ${renderMobileOddsBlock(_t('app.dyn.ust','Üst'), d.Over, trendOver)}
        `;}else{const trendYes=buildTrendDataFromMatch(d.OddsYes||d.Yes,d.PrevYes||d.OddsYes_prev||d.Yes_prev,d.TrendYes,d.DropPctYes);const trendNo=buildTrendDataFromMatch(d.OddsNo||d.No,d.PrevNo||d.OddsNo_prev||d.No_prev,d.TrendNo,d.DropPctNo);oddsBlocks=`
            ${renderMobileOddsBlock(_t('app.dyn.evet','Evet'), d.OddsYes || d.Yes, trendYes)}
            ${renderMobileOddsBlock(_t('app.dyn.hayir','Hayır'), d.OddsNo || d.No, trendNo)}
        `;}
const blockCount=currentMarket.includes('1x2')?'three':'two';const matchStatus=getMatchStatus(match.date);const liveCapsule=getMatchLiveCapsule(match.date,match.home_team,match.away_team,match.match_id);const _mk=_getMatchKey(match);const _isFav=_userFavorites.has(_mk);const _fc=_favCounts[_mk]||0;const _oddsLockSvg='<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#4a5068" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>';const _oddsLockCell='<div class="test-lock-cell test-lock-mob">'+_oddsLockSvg+'</div>';const _oGrayRow=_oTestBlur?(_oddsLockCell+_oddsLockCell+(blockCount==='three'?_oddsLockCell:'')):oddsBlocks;return`
        <div class="match-card odds-card dropping-card" data-index="${idx}" onclick="openMatchModal(${idx})">
            ${_mobileFavLine(_mk, _isFav, _fc)}
            <div class="odds-card-header">
                <div class="odds-card-teams">${match.home_team} – ${match.away_team}${liveCapsule || matchStatus}${starHtml || ''}</div>
                <div class="odds-card-volume">${volume}</div>
            </div>
            <div class="odds-card-meta">
                <span>${match.league || '-'}</span>
                <span class="meta-sep">•</span>
                <span>${dateStr}</span>
            </div>
            <div class="odds-card-row ${blockCount}">
                ${_oGrayRow}
            </div>
        </div>
    `;}
function renderMobileOddsBlock(label,oddsValue,trendData){const odds=formatOdds(oddsValue);var trendStr='';if(trendData&&trendData.pct_change!==null&&trendData.pct_change!==undefined){const pctChange=trendData.pct_change;if(pctChange!==0){const isDown=trendData.trend==='down';const arrow=isDown?'▼':'▲';const color=isDown?'#ef4444':'#22c55e';trendStr='<span class="ob-trend" style="color:'+color+'">'+arrow+' '+Math.abs(pctChange).toFixed(1)+'%</span>';}else{trendStr='<span class="ob-trend" style="color:#5c636b">— 0%</span>';}}else if(trendData&&trendData.trend&&(trendData.trend==='down'||trendData.trend==='up')){const isDown=trendData.trend==='down';const arrow=isDown?'▼':'▲';const color=isDown?'#ef4444':'#22c55e';trendStr='<span class="ob-trend" style="color:'+color+'">'+arrow+'</span>';}else{trendStr='<span class="ob-trend" style="color:#5c636b">— 0%</span>';}
return'<div class="odds-block mw-block">'+'<div class="odds-block-label">'+label+'</div>'+'<div class="ob-data-row">'+'<span class="ob-odds">'+odds+'</span>'+
trendStr+'</div>'+'</div>';}
let mobileGroup='moneyway';let mobileMarketType='1x2';function setMobileGroup(group){mobileGroup=group;document.querySelectorAll('.mobile-tab-row.group-row .mobile-tab-btn').forEach(btn=>{btn.classList.remove('active');if(btn.dataset.group===group){btn.classList.add('active');}});updateMobileMarket();}
function setMobileMarket(marketType){mobileMarketType=marketType;document.querySelectorAll('.mobile-tab-row.market-row .mobile-tab-btn').forEach(btn=>{btn.classList.remove('active');if(btn.dataset.marketType===marketType){btn.classList.add('active');}});updateMobileMarket();}
function updateMobileMarket(){const market=mobileGroup+'_'+mobileMarketType;const desktopTab=document.querySelector(`.market-tabs .tab[data-market="${market}"]`);if(desktopTab){document.querySelectorAll('.market-tabs .tab').forEach(t=>t.classList.remove('active'));desktopTab.classList.add('active');currentMarket=market;loadMatches();}}
let currentDayFilter='all';function toggleDayDropdown(){var dd=document.getElementById('dayFilterDropdown');if(dd)dd.classList.toggle('open');}
function selectDayOption(filter){var dd=document.getElementById('dayFilterDropdown');if(dd)dd.classList.remove('open');setDayFilter(filter);}
document.addEventListener('click',function(e){var dd=document.getElementById('dayFilterDropdown');if(dd&&!dd.contains(e.target)){dd.classList.remove('open');}});function setDayFilter(filter){if(currentDayFilter===filter){return;}
currentDayFilter=filter;var labelEl=document.getElementById('dayFilterLabel');if(labelEl)labelEl.textContent=_getDayFilterLabel(filter);document.querySelectorAll('.day-filter-option').forEach(function(opt){opt.classList.toggle('active',opt.getAttribute('data-value')===filter);});const todayBtn=document.getElementById('todayBtn');const yesterdayBtn=document.getElementById('yesterdayBtn');if(filter==='today'){dateFilterMode='TODAY';if(todayBtn)todayBtn.classList.add('active');if(yesterdayBtn)yesterdayBtn.classList.remove('active');}else if(filter==='yesterday'||filter==='d-1'){dateFilterMode=filter==='yesterday'?'YESTERDAY':'PAST_1';if(yesterdayBtn)yesterdayBtn.classList.add('active');if(todayBtn)todayBtn.classList.remove('active');}else if(filter==='future'){dateFilterMode='FUTURE';if(todayBtn)todayBtn.classList.remove('active');if(yesterdayBtn)yesterdayBtn.classList.remove('active');}else if(filter&&filter.startsWith('d-')){dateFilterMode='PAST_'+filter.slice(2);if(todayBtn)todayBtn.classList.remove('active');if(yesterdayBtn)yesterdayBtn.classList.remove('active');}else{dateFilterMode='ALL';if(todayBtn)todayBtn.classList.remove('active');if(yesterdayBtn)yesterdayBtn.classList.remove('active');}
loadMatches();}
function openMobileFilterModal(){var overlay=document.getElementById('mobileFilterOverlay');if(!overlay)return;var isPast=currentDayFilter&&currentDayFilter.startsWith('d-');document.querySelectorAll('.mf-chip[data-group="date"]').forEach(function(c){var val=c.getAttribute('data-value');if(val==='past'){c.classList.toggle('active',isPast);if(isPast)c.textContent=_getDayFilterLabel(currentDayFilter)+' ▾';else c.textContent='Geçmiş ▾';}else{c.classList.toggle('active',val===currentDayFilter);}});var pd=document.getElementById('mfPastDropdown');var pv=document.getElementById('mfPastSelectedValue');if(pd&&pv){if(isPast){pv.value=currentDayFilter;_buildMfPastDropdown(pd);pd.style.display='flex';}else{pv.value='';pd.style.display='none';}}
var sortVal=(currentSortColumn==='volume')?'volume':'date';document.querySelectorAll('.mf-chip[data-group="sort"]').forEach(function(c){c.classList.toggle('active',c.getAttribute('data-value')===sortVal);});document.querySelectorAll('.mf-sw[data-group="filter"]').forEach(function(c){var v=c.getAttribute('data-value');if(v==='hideEnded')c.classList.toggle('active',_mobileHideEnded);if(v==='hideLive')c.classList.toggle('active',_mobileHideLive);if(v==='onlyLive')c.classList.toggle('active',_mobileOnlyLive);});overlay.style.display='flex';}
function closeMobileFilterModal(){var overlay=document.getElementById('mobileFilterOverlay');if(overlay)overlay.style.display='none';}
function mfSelect(el){var group=el.getAttribute('data-group');el.closest('.mf-chips').querySelectorAll('.mf-chip[data-group="'+group+'"]').forEach(function(c){c.classList.remove('active');});el.classList.add('active');if(group==='date'){var pd=document.getElementById('mfPastDropdown');if(pd)pd.style.display='none';var pv=document.getElementById('mfPastSelectedValue');if(pv)pv.value='';}}
function mfSelectPast(el){var chips=el.closest('.mf-chips').querySelectorAll('.mf-chip[data-group="date"]');chips.forEach(function(c){c.classList.remove('active');});el.classList.add('active');var pd=document.getElementById('mfPastDropdown');if(!pd)return;if(pd.style.display==='flex'){pd.style.display='none';}else{_buildMfPastDropdown(pd);pd.style.display='flex';}}
function _buildMfPastDropdown(container){var nowTR=nowTurkey?nowTurkey():dayjs();var selectedVal=(document.getElementById('mfPastSelectedValue')||{}).value||'';container.innerHTML='';for(var i=1;i<=7;i++){var d=nowTR.subtract(i,'day');var label=i===1?_t('app.flt.yesterday','Dün'):(d.date()+' '+_tms(d.month()));var val='d-'+i;var btn=document.createElement('button');btn.className='mf-past-day-btn'+(selectedVal===val?' active':'');btn.textContent=label;btn.setAttribute('data-val',val);btn.setAttribute('data-label',label);btn.onclick=(function(v,lbl,b){return function(){container.querySelectorAll('.mf-past-day-btn').forEach(function(x){x.classList.remove('active');});b.classList.add('active');var pv=document.getElementById('mfPastSelectedValue');if(pv)pv.value=v;var toggle=document.querySelector('.mf-past-toggle');if(toggle)toggle.textContent=lbl+' ▾';};})(val,label,btn);container.appendChild(btn);}}
function mfToggle(el){var val=el.getAttribute('data-value');var list=el.closest('.mf-switch-list');if(val==='onlyLive'&&!el.classList.contains('active')){var hl=list?list.querySelector('.mf-sw[data-value="hideLive"]'):null;if(hl)hl.classList.remove('active');}
if(val==='hideLive'&&!el.classList.contains('active')){var ol=list?list.querySelector('.mf-sw[data-value="onlyLive"]'):null;if(ol)ol.classList.remove('active');}
el.classList.toggle('active');}
function applyMobileFilter(){var dateChip=document.querySelector('.mf-chip[data-group="date"].active');var sortChip=document.querySelector('.mf-chip[data-group="sort"].active');var dateChipVal=dateChip?dateChip.getAttribute('data-value'):'all';var sortVal=sortChip?sortChip.getAttribute('data-value'):'date';var dateVal=dateChipVal;if(dateChipVal==='past'){var pvEl=document.getElementById('mfPastSelectedValue');var pastVal=pvEl?pvEl.value:'';if(pastVal&&pastVal.startsWith('d-')){dateVal=pastVal;}else{dateVal='d-1';}}
_mobileHideEnded=!!document.querySelector('.mf-sw[data-value="hideEnded"].active');_mobileHideLive=!!document.querySelector('.mf-sw[data-value="hideLive"].active');_mobileOnlyLive=!!document.querySelector('.mf-sw[data-value="onlyLive"].active');var hasFilter=(dateVal!=='all')||_mobileHideEnded||_mobileHideLive||_mobileOnlyLive||(sortVal!=='date');var btn=document.getElementById('mobileFilterBtn');if(btn)btn.classList.toggle('has-filter',hasFilter);var dBtn=document.getElementById('desktopFilterBtn');if(dBtn)dBtn.classList.toggle('has-filter',hasFilter);closeMobileFilterModal();if(sortVal==='volume'){currentSortColumn='volume';currentSortDirection='desc';}else{currentSortColumn='date';currentSortDirection='desc';}
updateTrendSortButtons();updateTableHeaders();var modeMap={all:'ALL',today:'TODAY',yesterday:'YESTERDAY',future:'FUTURE'};if(dateVal.startsWith('d-')){dateFilterMode='PAST_'+dateVal.slice(2);}else{dateFilterMode=modeMap[dateVal]||'ALL';}
currentDayFilter=dateVal;var todayBtn=document.getElementById('todayBtn');var yesterdayBtn=document.getElementById('yesterdayBtn');if(todayBtn)todayBtn.classList.toggle('active',dateVal==='today');if(yesterdayBtn)yesterdayBtn.classList.toggle('active',dateVal==='d-1'||dateVal==='yesterday');var labelEl=document.getElementById('dayFilterLabel');if(labelEl)labelEl.textContent=_getDayFilterLabel(dateVal);delete _matchesMarketCache[currentMarket+'|'+dateFilterMode+'|'+currentSource];loadMatches();}
function _getDayFilterLabel(dateVal){if(!dateVal||dateVal==='all')return _t('app.flt.all','Tümü');if(dateVal==='today')return _t('app.flt.today','Bugün');if(dateVal==='yesterday'||dateVal==='d-1')return _t('app.flt.yesterday','Dün');if(dateVal==='future')return _t('app.flt.future','Gelecek');if(dateVal.startsWith('d-')){var n=parseInt(dateVal.slice(2));if(!isNaN(n)){var nowTR=nowTurkey?nowTurkey():dayjs();var d=nowTR.subtract(n,'day');return d.date()+' '+_tms(d.month());}}
return _t('app.flt.all','Tümü');}
const originalRenderMatches=renderMatches;window.renderMatches=function(data){if(_liveMode)return;const isMobile=window.innerWidth<=768;if(isMobile){renderMobileMatchCards(data);const tbody=document.getElementById('matchesTableBody');if(tbody)tbody.innerHTML='';}else{originalRenderMatches.call(this,data);const cardList=document.getElementById('matchCardList');if(cardList)cardList.innerHTML='';}};function getTableTrendArrow(current,previous){if(!current||!previous)return'';const curr=parseFloat(String(current).replace(/[^0-9.]/g,''));const prev=parseFloat(String(previous).replace(/[^0-9.]/g,''));if(isNaN(curr)||isNaN(prev))return'';const diff=Math.abs(curr-prev);if(diff<0.001)return'';if(curr>prev)return'<span class="trend-up">↑</span>';if(curr<prev)return'<span class="trend-down">↓</span>';return'';}
function buildTrendDataFromMatch(currentOdds,prevOdds,trendText,dropPct,openingOdds){const curr=parseFloat(String(currentOdds||'').replace(/[^0-9.]/g,''));const prev=parseFloat(String(prevOdds||'').replace(/[^0-9.]/g,''));const opening=parseFloat(String(openingOdds||'').replace(/[^0-9.]/g,''));const baseOdds=(!isNaN(opening)&&opening>0)?opening:prev;if(dropPct&&dropPct!==''){const pctVal=parseFloat(String(dropPct).replace(/[^0-9.-]/g,''));if(!isNaN(pctVal)){const trend=pctVal>0?'up':(pctVal<0?'down':'stable');return{trend:trend,pct_change:Math.abs(pctVal),old:baseOdds||null,new:curr||null,history:baseOdds&&curr?[baseOdds,curr]:[curr]};}}
if(isNaN(curr)||isNaN(baseOdds)||baseOdds===0){if(trendText){const t=String(trendText).trim().toLowerCase();if(t==='down'||t.includes('↓')){return{trend:'down',pct_change:null,old:null,new:curr||null,history:[curr]};}else if(t==='up'||t.includes('↑')){return{trend:'up',pct_change:null,old:null,new:curr||null,history:[curr]};}}
return null;}
const pctChange=((curr-baseOdds)/baseOdds)*100;let trend='stable';const threshold=0.5;if(pctChange<-threshold)trend='down';else if(pctChange>threshold)trend='up';return{trend:trend,pct_change:Math.round(pctChange*10)/10,old:baseOdds,new:curr,history:[baseOdds,curr]};}
function getDirectTrendArrow(trendValue){if(!trendValue)return'';const t=String(trendValue).trim().toLowerCase();if(t==='down'||t==='↓'||t.includes('↓'))return'<span class="trend-down">↓</span>';if(t==='up'||t==='↑'||t.includes('↑'))return'<span class="trend-up">↑</span>';return'';}
function formatOdds(value){if(!value||value==='-')return'-';const str=String(value);const firstLine=str.split('\n')[0];const num=parseFloat(firstLine);return isNaN(num)?firstLine:num.toFixed(2);}
function formatVolume(value){if(!value||value==='-')return'-';let str=String(value).replace(/[£€$,\s]/g,'');let multiplier=1;if(str.toUpperCase().includes('M')){multiplier=1000000;str=str.replace(/M/gi,'');}else if(str.toUpperCase().includes('K')){multiplier=1000;str=str.replace(/K/gi,'');}
const num=parseFloat(str)*multiplier;if(isNaN(num))return'-';return'£'+Math.round(num).toLocaleString('en-GB');}
function formatVolumeCompact(value){if(!value||value==='-')return'-';let str=String(value).replace(/[£€$,\s]/g,'');let multiplier=1;if(str.toUpperCase().includes('M')){multiplier=1000000;str=str.replace(/M/gi,'');}else if(str.toUpperCase().includes('K')){multiplier=1000;str=str.replace(/K/gi,'');}
const num=parseFloat(str)*multiplier;if(isNaN(num))return'-';if(num>=1000000){return'£'+(num/1000000).toFixed(1)+'M';}else if(num>=1000){return'£'+(num/1000).toFixed(1)+'k';}
return'£'+Math.round(num).toLocaleString('en-GB');}
function parseMoneyValue(value){if(!value||value==='-')return null;let str=String(value).replace(/[£€$,\s]/g,'');let multiplier=1;if(str.toUpperCase().includes('M')){multiplier=1000000;str=str.replace(/M/gi,'');}else if(str.toUpperCase().includes('K')){multiplier=1000;str=str.replace(/K/gi,'');}
str=str.replace(/[^0-9.]/g,'');const num=parseFloat(str)*multiplier;return isNaN(num)?null:num;}
function formatDateTwoLine(dateStr){if(!dateStr||dateStr==='-')return'<div class="date-line">-</div>';const dt=toTurkeyTime(dateStr);if(dt&&dt.isValid()){const day=dt.date();const month=_tms(dt.month());const time=dt.format('HH:mm');return`<div class="date-line">${day}.${month}</div><div class="time-line">${time}</div>`;}
return`<div class="date-line">${dateStr}</div>`;}
function hasValidMarketData(match,market){const d=match.details||match.odds||{};if(market.includes('1x2')){const odds1=d.Odds1||d['1'];const oddsX=d.OddsX||d['X'];const odds2=d.Odds2||d['2'];return isValidOdds(odds1)||isValidOdds(oddsX)||isValidOdds(odds2);}else if(market.includes('ou25')){const under=d.Under;const over=d.Over;return isValidOdds(under)||isValidOdds(over);}else if(market.includes('btts')){const yes=d.OddsYes||d.Yes;const no=d.OddsNo||d.No;return isValidOdds(yes)||isValidOdds(no);}
return false;}
function isValidOdds(value){if(!value||value==='-'||value==='')return false;const num=parseFloat(String(value).replace(/[^0-9.]/g,''));return!isNaN(num)&&num>0;}
function filterMatches(query){if(_liveMode){if(!_liveData||!_liveData.length)return;if(query){var lf=_liveData.filter(function(m){return(m.home_team&&m.home_team.toLowerCase().includes(query))||(m.away_team&&m.away_team.toLowerCase().includes(query))||(m.league&&m.league.toLowerCase().includes(query));});renderLiveMatches(lf);}else{renderLiveMatches(_liveData);}
return;}
let filtered=[...matches];filtered=filtered.filter(m=>hasValidMarketData(m,currentMarket));if(query){filtered=filtered.filter(m=>m.home_team.toLowerCase().includes(query)||m.away_team.toLowerCase().includes(query)||(m.league&&m.league.toLowerCase().includes(query)));}
filtered=applySorting(filtered);filteredMatches=filtered;renderMatches(filtered);}
function getMatchTrendPct(match,selection){const matchKey=`${match.home_team}|${match.away_team}`;const matchData=oddsTrendCache[matchKey];if(!matchData||!matchData.values)return 0;let selKey=selection;if(currentMarket.includes('1x2')){if(selection==='sel1')selKey='odds1';else if(selection==='selX')selKey='oddsx';else if(selection==='sel2')selKey='odds2';}else if(currentMarket.includes('ou25')){if(selection==='sel1')selKey='under';else if(selection==='sel2')selKey='over';}else if(currentMarket.includes('btts')){if(selection==='sel1')selKey='oddsyes';else if(selection==='sel2')selKey='oddsno';}
if(!matchData.values[selKey])return 0;return matchData.values[selKey].pct_change||0;}
function getMinTrendPct(match){const matchKey=`${match.home_team}|${match.away_team}`;const matchData=oddsTrendCache[matchKey];if(!matchData||!matchData.values)return 0;let minPct=0;for(const sel in matchData.values){const pct=matchData.values[sel].pct_change||0;if(pct<minPct){minPct=pct;}}
return minPct;}
function getMaxTrendPct(match){const matchKey=`${match.home_team}|${match.away_team}`;const matchData=oddsTrendCache[matchKey];if(!matchData||!matchData.values)return 0;let maxPct=0;for(const sel in matchData.values){const pct=matchData.values[sel].pct_change||0;if(pct>maxPct){maxPct=pct;}}
return maxPct;}
function getTrendFromCache(match,selectionKey){const matchKey=`${match.home_team}|${match.away_team}`;const matchData=oddsTrendCache[matchKey];if(!matchData||!matchData.values)return null;const selData=matchData.values[selectionKey];if(!selData)return null;return{trend:selData.trend||'stable',pct_change:selData.pct_change,old:selData.old,new:selData.new,history:selData.history||[selData.old,selData.new]};}
function applySorting(data){let sortedData=[...data];const nowTR=nowTurkey();const todayStr=nowTR.format('YYYY-MM-DD');const yesterdayStr=nowTR.subtract(1,'day').format('YYYY-MM-DD');function getMatchDateTR(dateStr){const dt=toTurkeyTime(dateStr);if(!dt||!dt.isValid())return null;return dt.format('YYYY-MM-DD');}
function isDateTodayOrFutureTR(dateStr){const dt=toTurkeyTime(dateStr);if(!dt||!dt.isValid())return false;return dt.format('YYYY-MM-DD')>=todayStr;}
if(dateFilterMode==='YESTERDAY'){sortedData=sortedData.filter(m=>{const matchDateStr=getMatchDateTR(m.date);if(!matchDateStr)return false;return matchDateStr===yesterdayStr;});}else if(dateFilterMode&&dateFilterMode.startsWith('PAST_')){const daysBack=parseInt(dateFilterMode.split('_')[1]);const targetStr=nowTR.subtract(daysBack,'day').format('YYYY-MM-DD');sortedData=sortedData.filter(m=>{const matchDateStr=getMatchDateTR(m.date);if(!matchDateStr)return false;return matchDateStr===targetStr;});}else if(dateFilterMode==='TODAY'){sortedData=sortedData.filter(m=>{const matchDateStr=getMatchDateTR(m.date);if(!matchDateStr)return false;return matchDateStr===todayStr;});}else if(dateFilterMode==='FUTURE'){sortedData=sortedData.filter(m=>{const dt=toTurkeyTime(m.date);if(!dt||!dt.isValid())return false;return dt.isAfter(nowTR);});}else{sortedData=sortedData.filter(m=>{const matchDateStr=getMatchDateTR(m.date);if(!matchDateStr)return false;return matchDateStr>=todayStr;});}
const isValidOdds=(val)=>{if(val===null||val===undefined)return false;if(typeof val==='number')return val!==0&&!isNaN(val);if(typeof val==='string'){let v=val.trim().toLowerCase();if(v===''||v==='-'||v==='--'||v==='—')return false;const cleaned=v.replace(/[%£€$,\s↓↑]/g,'').replace(/tl$/i,'').replace(/[^\d.\-]/g,'');const num=parseFloat(cleaned);if(isNaN(num))return false;return true;}
return false;};sortedData=sortedData.filter(m=>{const d=m.details||m.odds||{};const checkOdds=(obj)=>{if(!obj||typeof obj!=='object')return false;return isValidOdds(obj.Odds1)||isValidOdds(obj.Odds2)||isValidOdds(obj.OddsX)||isValidOdds(obj.OddsUnder)||isValidOdds(obj.OddsOver)||isValidOdds(obj.OddsYes)||isValidOdds(obj.OddsNo)||isValidOdds(obj['1'])||isValidOdds(obj['X'])||isValidOdds(obj['2'])||isValidOdds(obj.Under)||isValidOdds(obj.Over)||isValidOdds(obj.Yes)||isValidOdds(obj.No)||isValidOdds(obj.Pct1)||isValidOdds(obj.PctX)||isValidOdds(obj.Pct2)||isValidOdds(obj.PctUnder)||isValidOdds(obj.PctOver)||isValidOdds(obj.PctYes)||isValidOdds(obj.PctNo)||isValidOdds(obj.Amt1)||isValidOdds(obj.AmtX)||isValidOdds(obj.Amt2)||isValidOdds(obj.Volume)||isValidOdds(obj.open_odds)||isValidOdds(obj.current_odds)||isValidOdds(obj.drop_pct)||isValidOdds(obj.odds1)||isValidOdds(obj.odds2)||isValidOdds(obj.oddsx)||isValidOdds(obj.amt1)||isValidOdds(obj.amt2)||isValidOdds(obj.amtx)||isValidOdds(obj.pct1)||isValidOdds(obj.pct2)||isValidOdds(obj.pctx);};const checkCompleteOdds=(obj)=>{if(!obj||typeof obj!=='object')return false;if(currentMarket.includes('1x2')){return isValidOdds(obj.Odds1||obj['1'])&&isValidOdds(obj.OddsX||obj['X'])&&isValidOdds(obj.Odds2||obj['2']);}else if(currentMarket.includes('ou25')){return isValidOdds(obj.OddsUnder||obj.Under)&&isValidOdds(obj.OddsOver||obj.Over);}else if(currentMarket.includes('btts')){return isValidOdds(obj.OddsYes||obj.Yes)&&isValidOdds(obj.OddsNo||obj.No);}
return checkOdds(obj);};const checkHistoryArray=(arr)=>{if(!Array.isArray(arr)||arr.length===0)return false;const first=arr[0];let snapshot=first.snapshot||first.snapshot_json||first;if(typeof snapshot==='string'){try{snapshot=JSON.parse(snapshot);}catch(e){return false;}}
return checkOdds(snapshot);};let hasValidOdds=checkCompleteOdds(d)||checkCompleteOdds(m);if(!hasValidOdds&&(m.history?.length>0||m.history_count>0))hasValidOdds=true;if(!hasValidOdds&&m.history)hasValidOdds=checkHistoryArray(m.history);if(!hasValidOdds&&m.snapshots)hasValidOdds=checkHistoryArray(m.snapshots);return hasValidOdds;});
if(_mobileHideEnded||_mobileHideLive||_mobileOnlyLive){sortedData=sortedData.filter(m=>{const statusHtml=getMatchStatus(m.date);const isLive=statusHtml.includes('CANLI');const isEnded=statusHtml.includes('BİTTİ');if(_mobileOnlyLive&&!isLive)return false;if(_mobileHideEnded&&isEnded)return false;if(_mobileHideLive&&isLive)return false;return true;});}
return sortedData.sort((a,b)=>{let valA,valB;const d1=a.details||a.odds||{};const d2=b.details||b.odds||{};switch(currentSortColumn){case'date':valA=parseDate(a.date);valB=parseDate(b.date);break;case'league':valA=(a.league||'').toLowerCase();valB=(b.league||'').toLowerCase();break;case'match':valA=(a.home_team||'').toLowerCase();valB=(b.home_team||'').toLowerCase();break;case'sel1':if(currentMarket.startsWith('dropping_')){valA=getMatchTrendPct(a,'sel1');valB=getMatchTrendPct(b,'sel1');}else if(currentMarket.includes('1x2')){valA=parsePctValue(d1.Pct1);valB=parsePctValue(d2.Pct1);}else if(currentMarket.includes('ou25')){valA=parsePctValue(d1.PctUnder);valB=parsePctValue(d2.PctUnder);}else if(currentMarket.includes('btts')){valA=parsePctValue(d1.PctYes);valB=parsePctValue(d2.PctYes);}
break;case'selX':if(currentMarket.startsWith('dropping_')){valA=getMatchTrendPct(a,'selX');valB=getMatchTrendPct(b,'selX');}else{valA=parsePctValue(d1.PctX);valB=parsePctValue(d2.PctX);}
break;case'sel2':if(currentMarket.startsWith('dropping_')){valA=getMatchTrendPct(a,'sel2');valB=getMatchTrendPct(b,'sel2');}else if(currentMarket.includes('1x2')){valA=parsePctValue(d1.Pct2);valB=parsePctValue(d2.Pct2);}else if(currentMarket.includes('ou25')){valA=parsePctValue(d1.PctOver);valB=parsePctValue(d2.PctOver);}else if(currentMarket.includes('btts')){valA=parsePctValue(d1.PctNo);valB=parsePctValue(d2.PctNo);}
break;case'volume':valA=parseVolume(a);valB=parseVolume(b);break;case'trend_down':valA=getMinTrendPct(a);valB=getMinTrendPct(b);return valA-valB;case'trend_up':valA=getMaxTrendPct(a);valB=getMaxTrendPct(b);return valB-valA;default:valA=parseDate(a.date);valB=parseDate(b.date);}
valA=valA||0;valB=valB||0;if(typeof valA==='string'&&typeof valB==='string'){if(currentSortDirection==='asc'){return valA.localeCompare(valB);}else{return valB.localeCompare(valA);}}else{if(currentSortDirection==='asc'){return valA-valB;}else{return valB-valA;}}});}
function parseOddsValue(val){if(!val||val==='-')return 0;const values=String(val).replace(/[↑↓]/g,'').match(/[\d.,]+/g);if(!values||values.length===0)return 0;const last=values[values.length-1];const num=parseFloat(last.replace(',','.'));return isNaN(num)?0:num;}
function parsePctValue(val){if(!val||val==='-')return 0;const numMatch=String(val).match(/[\d.,]+/);if(!numMatch)return 0;const num=parseFloat(numMatch[0].replace(',','.'));return isNaN(num)?0:num;}
function getTodayDateString(){const now=new Date();const day=String(now.getDate()).padStart(2,'0');const month=String(now.getMonth()+1).padStart(2,'0');const year=now.getFullYear();return`${year}-${month}-${day}`;}
function extractDateOnly(dateStr){if(!dateStr)return'';const ddmmyyyyHHMM=dateStr.match(/(\d{2})\.(\d{2})\.(\d{4})\s+\d{2}:\d{2}/);if(ddmmyyyyHHMM){return`${ddmmyyyyHHMM[3]}-${ddmmyyyyHHMM[2]}-${ddmmyyyyHHMM[1]}`;}
const ddmmyyyy=dateStr.match(/(\d{2})\.(\d{2})\.(\d{4})/);if(ddmmyyyy){return`${ddmmyyyy[3]}-${ddmmyyyy[2]}-${ddmmyyyy[1]}`;}
const yyyymmdd=dateStr.match(/(\d{4})-(\d{2})-(\d{2})/);if(yyyymmdd){return`${yyyymmdd[1]}-${yyyymmdd[2]}-${yyyymmdd[3]}`;}
const isoMatch=dateStr.match(/(\d{4})-(\d{2})-(\d{2})T/);if(isoMatch){return`${isoMatch[1]}-${isoMatch[2]}-${isoMatch[3]}`;}
const dmySlash=dateStr.match(/(\d{1,2})\/(\d{1,2})\/(\d{4})/);if(dmySlash){const day=dmySlash[1].padStart(2,'0');const month=dmySlash[2].padStart(2,'0');return`${dmySlash[3]}-${month}-${day}`;}
return'';}
function sortByColumn(column){if(currentSortColumn===column){currentSortDirection=currentSortDirection==='asc'?'desc':'asc';}else{currentSortColumn=column;currentSortDirection=(column==='date'||column==='league'||column==='match')?'asc':'desc';}
updateTrendSortButtons();updateTableHeaders();filteredMatches=applySorting(matches);renderMatches(filteredMatches);}
function sortByTrend(direction){const downBtn=document.getElementById('trendDownBtn');const upBtn=document.getElementById('trendUpBtn');if(direction==='down'){if(currentSortColumn==='trend_down'){currentSortColumn='date';currentSortDirection='desc';}else{currentSortColumn='trend_down';currentSortDirection='desc';}}else{if(currentSortColumn==='trend_up'){currentSortColumn='date';currentSortDirection='desc';}else{currentSortColumn='trend_up';currentSortDirection='desc';}}
updateTrendSortButtons();updateTableHeaders();filteredMatches=applySorting(matches);renderMatches(filteredMatches);}
function updateTrendSortButtons(){const downBtn=document.getElementById('trendDownBtn');const upBtn=document.getElementById('trendUpBtn');if(downBtn){downBtn.classList.remove('active','down');if(currentSortColumn==='trend_down'){downBtn.classList.add('active','down');}}
if(upBtn){upBtn.classList.remove('active');if(currentSortColumn==='trend_up'){upBtn.classList.add('active');}}}
function showTrendSortButtons(show){const btns=document.getElementById('trendSortBtns');if(btns){btns.style.display=show?'flex':'none';}}
function toggleTodayFilter(skipLoad=false){const todayBtn=document.getElementById('todayBtn');const yesterdayBtn=document.getElementById('yesterdayBtn');if(dateFilterMode==='TODAY'){dateFilterMode='ALL';if(todayBtn)todayBtn.classList.remove('active');}else{dateFilterMode='TODAY';if(todayBtn)todayBtn.classList.add('active');if(yesterdayBtn)yesterdayBtn.classList.remove('active');}
void 0;if(!skipLoad)loadMatches();}
function toggleYesterdayFilter(skipLoad=false){const todayBtn=document.getElementById('todayBtn');const yesterdayBtn=document.getElementById('yesterdayBtn');if(dateFilterMode==='YESTERDAY'){dateFilterMode='ALL';if(yesterdayBtn)yesterdayBtn.classList.remove('active');}else{dateFilterMode='YESTERDAY';if(yesterdayBtn)yesterdayBtn.classList.add('active');if(todayBtn)todayBtn.classList.remove('active');}
void 0;if(!skipLoad)loadMatches();}
function parseDate(dateStr){if(!dateStr||dateStr==='-')return 0;const dt=toTurkeyTime(dateStr);return dt&&dt.isValid()?dt.valueOf():0;}
function parseVolume(match){const d=match.odds||match.details||{};let vol=d.Volume||'0';if(typeof vol==='string'){let str=vol.replace(/[£€$,\s]/g,'');let multiplier=1;if(str.toUpperCase().includes('M')){multiplier=1000000;str=str.replace(/M/gi,'');}else if(str.toUpperCase().includes('K')){multiplier=1000;str=str.replace(/K/gi,'');}
return parseFloat(str)*multiplier||0;}
return parseFloat(vol)||0;}
let previousOddsData=null;let modalOddsData=null;async function openMatchModalFromMatches(index){if(index>=0&&index<matches.length){const reqId=++_modalRequestId;resetModalState();selectedMatch=matches[index];selectedChartMarket=currentMarket;var modalTitleHtml=escapeHtml(selectedMatch.home_team)+' vs '+escapeHtml(selectedMatch.away_team);document.getElementById('modalMatchTitle').innerHTML=modalTitleHtml;var modalFtCapsule=_getModalFinishedCapsule(selectedMatch);var isFinishedMatch=modalFtCapsule!=='';const headerDt=toTurkeyTime(selectedMatch.date);let headerDateText='';if(headerDt&&headerDt.isValid()){headerDateText=headerDt.format('DD.MM HH:mm');}
var leagueHtml=escapeHtml(selectedMatch.league||'');if(isFinishedMatch)leagueHtml+=modalFtCapsule;if(headerDateText)leagueHtml+='<span class="modal-sub-sep"> \u2022 </span><span class="modal-sub-date">'+headerDateText+'</span>';document.getElementById('modalLeague').innerHTML=leagueHtml;document.querySelectorAll('#modalChartTabs .chart-tab').forEach(t=>{t.classList.remove('active');if(t.dataset.market===currentMarket){t.classList.add('active');}});document.getElementById('modalOverlay').classList.add('active');_setModalFavBtnState(_getMatchKey(selectedMatch));const home=selectedMatch.home_team;const away=selectedMatch.away_team;const league=selectedMatch.league||'';const matchIdHash=selectedMatch.match_id||'';const chartLibsPromise=window.loadChartLibs?window.loadChartLibs().then(()=>registerChartPlugins()):Promise.resolve();const marketsPromise=loadAllMarketsAtOnce(home,away,league,matchIdHash);const kickoff=selectedMatch.date||selectedMatch.kickoff_utc||'';const chartPipeline=Promise.all([marketsPromise,chartLibsPromise]).then(()=>{if(reqId!==_modalRequestId)return;return loadChartWithTrends(home,away,selectedChartMarket,league,reqId,matchIdHash);}).catch(e=>console.error('[Modal] Chart pipeline error:',e));const alarmsPipeline=renderMatchAlarmsSection(home,away,league,kickoff,matchIdHash,reqId);const livePipeline=_checkModalLiveData(home,away,matchIdHash,league,kickoff,reqId);await Promise.all([chartPipeline,alarmsPipeline,livePipeline]);}}
async function openMatchModalFromAPI(homeTeam,awayTeam,league,kickoff,matchIdHash=''){const reqId=++_modalRequestId;resetModalState();league=league||'';kickoff=kickoff||'';var apiHome=homeTeam;var apiAway=awayTeam;var apiLeague=league;var apiKickoff=kickoff;var prematchFound=null;var hLow=(homeTeam||'').toLowerCase().trim();var aLow=(awayTeam||'').toLowerCase().trim();function _pmSearch(arr){for(var si=0;si<arr.length;si++){var pmH=(arr[si].home_team||'').toLowerCase().trim();var pmA=(arr[si].away_team||'').toLowerCase().trim();var pmHash=_matchContextHash(arr[si]);if(matchIdHash&&pmHash===matchIdHash)return arr[si];if(matchIdHash)continue;if(pmH===hLow&&pmA===aLow)return arr[si];if((pmH.includes(hLow)||hLow.includes(pmH))&&(pmA.includes(aLow)||aLow.includes(pmA))&&pmH.length>2&&pmA.length>2){return arr[si];}}
return null;}
var fArr2=(typeof filteredMatches!=='undefined'&&filteredMatches.length>0)?filteredMatches:[];var mArr2=(typeof matches!=='undefined'&&matches.length>0)?matches:[];prematchFound=_pmSearch(fArr2);if(!prematchFound&&mArr2.length>fArr2.length){prematchFound=_pmSearch(mArr2);}
if(prematchFound){apiHome=prematchFound.home_team||homeTeam;apiAway=prematchFound.away_team||awayTeam;if(!league&&prematchFound.league)apiLeague=prematchFound.league;var _kHasTime=/T\d{2}:\d{2}|\s\d{2}:\d{2}/.test(String(kickoff||''));if((!kickoff||!_kHasTime)&&prematchFound.date)apiKickoff=prematchFound.date;void 0;}else{void 0;}
selectedMatch={home_team:apiHome,away_team:apiAway,league:apiLeague,date:apiKickoff,match_id:prematchFound?_matchContextHash(prematchFound):matchIdHash,history:[],history_count:0,odds:null,details:null};selectedChartMarket=currentMarket;var modalTitleHtml=escapeHtml(homeTeam)+' vs '+escapeHtml(awayTeam);document.getElementById('modalMatchTitle').innerHTML=modalTitleHtml;var modalFtCapsule=_getModalFinishedCapsule(selectedMatch);var isFinishedMatch=modalFtCapsule!=='';const headerDt=apiKickoff?toTurkeyTime(apiKickoff):null;let headerDateText='';if(headerDt&&headerDt.isValid()){headerDateText=headerDt.format('DD.MM HH:mm');}
var leagueHtml=escapeHtml(apiLeague||'');if(isFinishedMatch)leagueHtml+=modalFtCapsule;if(headerDateText)leagueHtml+='<span class="modal-sub-sep"> \u2022 </span><span class="modal-sub-date">'+headerDateText+'</span>';document.getElementById('modalLeague').innerHTML=leagueHtml||'';document.querySelectorAll('#modalChartTabs .chart-tab').forEach(t=>{t.classList.remove('active');if(t.dataset.market===currentMarket){t.classList.add('active');}});document.getElementById('modalOverlay').classList.add('active');_setModalFavBtnState(_getMatchKey(selectedMatch));const matchIdHash2=selectedMatch.match_id||'';const chartLibsPromise=window.loadChartLibs?window.loadChartLibs().then(()=>registerChartPlugins()):Promise.resolve();const marketsPromise=loadAllMarketsAtOnce(apiHome,apiAway,apiLeague,matchIdHash2);try{const chartPipeline=Promise.all([marketsPromise,chartLibsPromise]).then(()=>{if(reqId!==_modalRequestId)return;return loadChartWithTrends(apiHome,apiAway,selectedChartMarket,apiLeague,reqId,matchIdHash2);}).catch(e=>console.error('[Modal] Chart pipeline error:',e));const alarmsPipeline=renderMatchAlarmsSection(apiHome,apiAway,apiLeague,apiKickoff,matchIdHash2,reqId);const livePipeline=_checkModalLiveData(apiHome,apiAway,matchIdHash2,apiLeague,apiKickoff,reqId);await Promise.all([chartPipeline,alarmsPipeline,livePipeline]);}catch(error){console.error('[openMatchModalFromAPI] Error:',error);showToast('Maç bilgisi alınırken hata oluştu','error');}}
async function openMatchModal(index){const dataSource=_allFilteredMatches.length>0?_allFilteredMatches:(filteredMatches.length>0?filteredMatches:matches);if(index>=0&&index<dataSource.length){var _matchForCheck=dataSource[index];if(window.userPlan==='test'&&(currentMarket==='moneyway_1x2'||currentMarket==='dropping_1x2')&&!_isTestFreeMatch(_matchForCheck.match_id)){_showTestLockedToast();return;}
const reqId=++_modalRequestId;resetModalState();selectedMatch=dataSource[index];selectedChartMarket=currentMarket;var modalTitleHtml=escapeHtml(selectedMatch.home_team)+' vs '+escapeHtml(selectedMatch.away_team);document.getElementById('modalMatchTitle').innerHTML=modalTitleHtml;var modalFtCapsule=_getModalFinishedCapsule(selectedMatch);var isFinishedMatch=modalFtCapsule!=='';const headerDt=toTurkeyTime(selectedMatch.date);let headerDateText='';if(headerDt&&headerDt.isValid()){headerDateText=headerDt.format('DD.MM HH:mm');}
var leagueHtml=escapeHtml(selectedMatch.league||'');if(isFinishedMatch)leagueHtml+=modalFtCapsule;if(headerDateText)leagueHtml+='<span class="modal-sub-sep"> \u2022 </span><span class="modal-sub-date">'+headerDateText+'</span>';document.getElementById('modalLeague').innerHTML=leagueHtml;document.querySelectorAll('#modalChartTabs .chart-tab').forEach(t=>{t.classList.remove('active');if(t.dataset.market===currentMarket){t.classList.add('active');}});document.getElementById('modalOverlay').classList.add('active');_setModalFavBtnState(_getMatchKey(selectedMatch));const home=selectedMatch.home_team;const away=selectedMatch.away_team;const league=selectedMatch.league||'';const matchIdHash3=selectedMatch.match_id||'';const chartLibsPromise=window.loadChartLibs?window.loadChartLibs().then(()=>registerChartPlugins()):Promise.resolve();const marketsPromise=loadAllMarketsAtOnce(home,away,league,matchIdHash3);const kickoff=selectedMatch.date||selectedMatch.kickoff_utc||'';const chartPipeline=Promise.all([marketsPromise,chartLibsPromise]).then(()=>{if(reqId!==_modalRequestId)return;return loadChartWithTrends(home,away,selectedChartMarket,league,reqId,matchIdHash3);}).catch(e=>console.error('[Modal] Chart pipeline error:',e));const alarmsPipeline=renderMatchAlarmsSection(home,away,league,kickoff,matchIdHash3,reqId);const livePipeline=_checkModalLiveData(home,away,matchIdHash3,league,kickoff,reqId);await Promise.all([chartPipeline,alarmsPipeline,livePipeline]);}}
function resetModalState(){if(chart){chart.destroy();chart=null;}
currentChartHistoryData=[];modalOddsData=null;previousOddsData=null;bulkHistoryCache={};bulkHistoryCacheKey='';_modalLiveData=null;_modalLiveMarket='1x2';const card=document.getElementById('matchInfoCard');if(card)card.innerHTML='';const grid=document.getElementById('smartMoneyGrid');if(grid){grid.innerHTML='';grid.style.display='none';}
const empty=document.getElementById('smartMoneyEmpty');if(empty)empty.style.display='none';var liveTab=document.getElementById('modalLiveTab');if(liveTab)liveTab.style.display='none';var liveBody=document.getElementById('modalLiveBody');if(liveBody)liveBody.innerHTML='';var liveTabs=document.getElementById('modalLiveMarketTabs');if(liveTabs)liveTabs.innerHTML='';if(window.userPlan==='core'){if(liveTab)liveTab.style.display='';if(liveBody)liveBody.innerHTML=proLockPanelHtml();}
if(window.userPlan==='test'&&selectedMatch&&!_isTestFreeMatch(selectedMatch.match_id)){if(liveTab)liveTab.style.display='';if(liveBody)liveBody.innerHTML=proLockPanelHtml();}
const canvas=document.getElementById('oddsChart');if(canvas){const ctx=canvas.getContext('2d');ctx.clearRect(0,0,canvas.width,canvas.height);}
showSmartMoneyLoading();showChartLoading();}
function showSmartMoneyLoading(){const loading=document.getElementById('smartMoneyLoading');const grid=document.getElementById('smartMoneyGrid');const empty=document.getElementById('smartMoneyEmpty');if(loading)loading.style.display='flex';if(grid)grid.style.display='none';if(empty)empty.style.display='none';}
function hideSmartMoneyLoading(){const loading=document.getElementById('smartMoneyLoading');if(loading)loading.style.display='none';}
function showChartLoading(){const loading=document.getElementById('chartLoading');if(loading)loading.style.display='flex';}
function hideChartLoading(){const loading=document.getElementById('chartLoading');if(loading)loading.style.display='none';}
let bulkHistoryCache={};let bulkHistoryCacheKey='';const MODAL_CACHE_TTL=30000;let modalDataCache={};function getModalCacheKey(home,away,market,league='',matchIdHash=''){return`${home}|${away}|${league}|${market}|${matchIdHash}`.toLowerCase();}
function getModalCachedData(home,away,market,league='',matchIdHash=''){const key=getModalCacheKey(home,away,market,league,matchIdHash);const cached=modalDataCache[key];if(cached&&(Date.now()-cached.timestamp)<MODAL_CACHE_TTL){void 0;return cached.data;}
return null;}
function setModalCachedData(home,away,market,data,league='',matchIdHash=''){const key=getModalCacheKey(home,away,market,league,matchIdHash);modalDataCache[key]={data,timestamp:Date.now()};void 0;const keys=Object.keys(modalDataCache);if(keys.length>50){const sortedKeys=keys.sort((a,b)=>modalDataCache[a].timestamp-modalDataCache[b].timestamp);for(let i=0;i<keys.length-50;i++){delete modalDataCache[sortedKeys[i]];}}}
async function loadAllMarketsAtOnce(home,away,league='',matchIdHash=''){const cacheKey=`${home}|${away}|${league}|${matchIdHash}|${currentSource}`;if(bulkHistoryCacheKey===cacheKey&&Object.keys(bulkHistoryCache).length>0){void 0;return bulkHistoryCache;}
try{void 0;const startTime=performance.now();var url=`/api/match/history/bulk?home=${encodeURIComponent(home)}&away=${encodeURIComponent(away)}&league=${encodeURIComponent(league || '')}`;const response=await fetch(url);const data=await response.json();const elapsed=performance.now()-startTime;void 0;if(data.markets){bulkHistoryCache=data.markets;bulkHistoryCacheKey=cacheKey;}
return data.markets||{};}catch(e){console.error('[Bulk] Error fetching all markets:',e);return{};}}
async function loadChartWithTrends(home,away,market,league='',reqId,matchIdHash=''){try{let data={history:[]};const cachedData=getModalCachedData(home,away,market,league,matchIdHash);if(cachedData){data=cachedData;void 0;}
else{const cacheKey=`${home}|${away}|${league}|${currentSource}`;if(bulkHistoryCacheKey===cacheKey&&bulkHistoryCache[market]){data=bulkHistoryCache[market];void 0;setModalCachedData(home,away,market,data,league,matchIdHash);}else{try{const response=await fetch(`/api/match/history?home=${encodeURIComponent(home)}&away=${encodeURIComponent(away)}&market=${market}&league=${encodeURIComponent(league || '')}`);if(reqId&&reqId!==_modalRequestId)return;data=await response.json();void 0;setModalCachedData(home,away,market,data,league,matchIdHash);}catch(e){void 0;}}}
if(reqId&&reqId!==_modalRequestId)return;if(data.history&&data.history.length>=1){modalOddsData=data.history[data.history.length-1];}else{modalOddsData=null;}
if(data.history&&data.history.length>=2){previousOddsData=data.history[data.history.length-2];}else{previousOddsData=null;}
if(modalOddsData&&modalOddsData.Date){const leagueEl=document.getElementById('modalLeague');if(leagueEl&&leagueEl.innerHTML.indexOf(' • ')===-1){const dt=toTurkeyTime(modalOddsData.Date);if(dt&&dt.isValid()){leagueEl.innerHTML+=' • '+dt.format('DD.MM HH:mm');}}}
updateMatchInfoCard();await loadChart(home,away,market,league);hideChartLoading();}catch(e){console.error('Error loading chart with trends:',e);if(reqId&&reqId!==_modalRequestId)return;await loadChart(home,away,market,league);hideChartLoading();}}
function updateMatchInfoCard(){const card=document.getElementById('matchInfoCard');if(!selectedMatch){if(card)card.innerHTML='';return;}
const baseData=selectedMatch.odds||selectedMatch.details||{};const d=modalOddsData||baseData;const p=previousOddsData||{};const isMoneyway=selectedChartMarket.startsWith('moneyway');const isDropping=selectedChartMarket.startsWith('dropping');void 0;void 0;void 0;let html='';if(selectedChartMarket.includes('1x2')){const trend1=isDropping?getTrendArrow(d.Odds1||d['1'],p.Odds1||p['1']):'';const trendX=isDropping?getTrendArrow(d.OddsX||d['X'],p.OddsX||p['X']):'';const trend2=isDropping?getTrendArrow(d.Odds2||d['2'],p.Odds2||p['2']):'';if(isMoneyway){const c1=getColorClass(d.Pct1);const cX=getColorClass(d.PctX);const c2=getColorClass(d.Pct2);const pct1=parseFloat(d.Pct1)||0;const pctX=parseFloat(d.PctX)||0;const pct2=parseFloat(d.Pct2)||0;html=`
                <div class="info-columns info-columns-3">
                    <div class="info-column" data-selection="1">
                        <div class="column-header">1</div>
                        <div class="column-row">
                            <span class="row-label">${_t("app.mod.oran_row","Oran")}</span>
                            <span class="row-value odds">${formatOdds(d.Odds1 || d['1'])}</span>
                        </div>
                        <div class="column-row">
                            <span class="row-label">${_t("app.mod.amount","Miktar")}</span>
                            <span class="row-value money ${c1}">${formatVolumeCompact(d.Amt1)}</span>
                        </div>
                        <div class="column-row row-pct">
                            <span class="row-label label-pct">%</span>
                            <span class="row-value pct ${c1}">${formatPct(d.Pct1)}</span>
                        </div>
                        <div class="mobile-progress" style="width: ${pct1}%"></div>
                    </div>
                    <div class="info-column" data-selection="X">
                        <div class="column-header">X</div>
                        <div class="column-row">
                            <span class="row-label">${_t("app.mod.oran_row","Oran")}</span>
                            <span class="row-value odds">${formatOdds(d.OddsX || d['X'])}</span>
                        </div>
                        <div class="column-row">
                            <span class="row-label">${_t("app.mod.amount","Miktar")}</span>
                            <span class="row-value money ${cX}">${formatVolumeCompact(d.AmtX)}</span>
                        </div>
                        <div class="column-row row-pct">
                            <span class="row-label label-pct">%</span>
                            <span class="row-value pct ${cX}">${formatPct(d.PctX)}</span>
                        </div>
                        <div class="mobile-progress" style="width: ${pctX}%"></div>
                    </div>
                    <div class="info-column" data-selection="2">
                        <div class="column-header">2</div>
                        <div class="column-row">
                            <span class="row-label">${_t("app.mod.oran_row","Oran")}</span>
                            <span class="row-value odds">${formatOdds(d.Odds2 || d['2'])}</span>
                        </div>
                        <div class="column-row">
                            <span class="row-label">${_t("app.mod.amount","Miktar")}</span>
                            <span class="row-value money ${c2}">${formatVolumeCompact(d.Amt2)}</span>
                        </div>
                        <div class="column-row row-pct">
                            <span class="row-label label-pct">%</span>
                            <span class="row-value pct ${c2}">${formatPct(d.Pct2)}</span>
                        </div>
                        <div class="mobile-progress" style="width: ${pct2}%"></div>
                    </div>
                </div>
                <div class="volume-bar">
                    <span class="volume-label">${_t("app.dyn.toplam_hacim","TOPLAM HACİM")}</span>
                    <span class="volume-value">${formatVolume(d.Volume)}</span>
                </div>
            `;}else{html=`
                <div class="info-columns">
                    <div class="info-column">
                        <div class="column-header">1</div>
                        <div class="column-row">
                            <span class="row-label">${_t("app.mod.oran_row","Oran")}</span>
                            <span class="row-value odds">${formatOdds(d.Odds1 || d['1'])}${trend1}</span>
                        </div>
                    </div>
                    <div class="info-column">
                        <div class="column-header">X</div>
                        <div class="column-row">
                            <span class="row-label">${_t("app.mod.oran_row","Oran")}</span>
                            <span class="row-value odds">${formatOdds(d.OddsX || d['X'])}${trendX}</span>
                        </div>
                    </div>
                    <div class="info-column">
                        <div class="column-header">2</div>
                        <div class="column-row">
                            <span class="row-label">${_t("app.mod.oran_row","Oran")}</span>
                            <span class="row-value odds">${formatOdds(d.Odds2 || d['2'])}${trend2}</span>
                        </div>
                    </div>
                </div>
                <div class="volume-bar">
                    <span class="volume-label">Volume</span>
                    <span class="volume-value">${formatVolume(d.Volume)}</span>
                </div>
            `;}}else if(selectedChartMarket.includes('ou25')){const trendUnder=isDropping?getTrendArrow(d.Under,p.Under):'';const trendOver=isDropping?getTrendArrow(d.Over,p.Over):'';if(isMoneyway){const cU=getColorClass(d.PctUnder);const cO=getColorClass(d.PctOver);const pctU=parseFloat(d.PctUnder)||0;const pctO=parseFloat(d.PctOver)||0;html=`
                <div class="info-columns">
                    <div class="info-column" data-selection="Alt">
                        <div class="column-header">${_t('app.dyn.alt','Alt')}</div>
                        <div class="column-row">
                            <span class="row-label">${_t("app.mod.oran_row","Oran")}</span>
                            <span class="row-value odds">${formatOdds(d.Under)}</span>
                        </div>
                        <div class="column-row">
                            <span class="row-label">${_t("app.mod.amount","Miktar")}</span>
                            <span class="row-value money ${cU}">${formatVolumeCompact(d.AmtUnder)}</span>
                        </div>
                        <div class="column-row row-pct">
                            <span class="row-label label-pct">%</span>
                            <span class="row-value pct ${cU}">${formatPct(d.PctUnder)}</span>
                        </div>
                        <div class="mobile-progress" style="width: ${pctU}%"></div>
                    </div>
                    <div class="info-column" data-selection="Üst">
                        <div class="column-header">${_t('app.dyn.ust','Üst')}</div>
                        <div class="column-row">
                            <span class="row-label">${_t("app.mod.oran_row","Oran")}</span>
                            <span class="row-value odds">${formatOdds(d.Over)}</span>
                        </div>
                        <div class="column-row">
                            <span class="row-label">${_t("app.mod.amount","Miktar")}</span>
                            <span class="row-value money ${cO}">${formatVolumeCompact(d.AmtOver)}</span>
                        </div>
                        <div class="column-row row-pct">
                            <span class="row-label label-pct">%</span>
                            <span class="row-value pct ${cO}">${formatPct(d.PctOver)}</span>
                        </div>
                        <div class="mobile-progress" style="width: ${pctO}%"></div>
                    </div>
                </div>
                <div class="volume-bar">
                    <span class="volume-label">${_t("app.dyn.toplam_hacim","TOPLAM HACİM")}</span>
                    <span class="volume-value">${formatVolume(d.Volume)}</span>
                </div>
            `;}else{html=`
                <div class="info-columns">
                    <div class="info-column">
                        <div class="column-header">${_t('app.dyn.alt','Alt')}</div>
                        <div class="column-row">
                            <span class="row-label">${_t("app.mod.oran_row","Oran")}</span>
                            <span class="row-value odds">${formatOdds(d.Under)}${trendUnder}</span>
                        </div>
                    </div>
                    <div class="info-column">
                        <div class="column-header">${_t('app.dyn.ust','Üst')}</div>
                        <div class="column-row">
                            <span class="row-label">${_t("app.mod.oran_row","Oran")}</span>
                            <span class="row-value odds">${formatOdds(d.Over)}${trendOver}</span>
                        </div>
                    </div>
                </div>
                <div class="volume-bar">
                    <span class="volume-label">Volume</span>
                    <span class="volume-value">${formatVolume(d.Volume)}</span>
                </div>
            `;}}else if(selectedChartMarket.includes('btts')){const trendYes=isDropping?getTrendArrow(d.OddsYes||d.Yes,p.OddsYes||p.Yes):'';const trendNo=isDropping?getTrendArrow(d.OddsNo||d.No,p.OddsNo||p.No):'';if(isMoneyway){const cY=getColorClass(d.PctYes);const cN=getColorClass(d.PctNo);const pctY=parseFloat(d.PctYes)||0;const pctN=parseFloat(d.PctNo)||0;html=`
                <div class="info-columns">
                    <div class="info-column" data-selection="Evet">
                        <div class="column-header">${_t('app.dyn.evet','Evet')}</div>
                        <div class="column-row">
                            <span class="row-label">${_t("app.mod.oran_row","Oran")}</span>
                            <span class="row-value odds">${formatOdds(d.OddsYes || d.Yes)}</span>
                        </div>
                        <div class="column-row">
                            <span class="row-label">${_t("app.mod.amount","Miktar")}</span>
                            <span class="row-value money ${cY}">${formatVolumeCompact(d.AmtYes)}</span>
                        </div>
                        <div class="column-row row-pct">
                            <span class="row-label label-pct">%</span>
                            <span class="row-value pct ${cY}">${formatPct(d.PctYes)}</span>
                        </div>
                        <div class="mobile-progress" style="width: ${pctY}%"></div>
                    </div>
                    <div class="info-column" data-selection="Hayır">
                        <div class="column-header">${_t('app.dyn.hayir','Hayır')}</div>
                        <div class="column-row">
                            <span class="row-label">${_t("app.mod.oran_row","Oran")}</span>
                            <span class="row-value odds">${formatOdds(d.OddsNo || d.No)}</span>
                        </div>
                        <div class="column-row">
                            <span class="row-label">${_t("app.mod.amount","Miktar")}</span>
                            <span class="row-value money ${cN}">${formatVolumeCompact(d.AmtNo)}</span>
                        </div>
                        <div class="column-row row-pct">
                            <span class="row-label label-pct">%</span>
                            <span class="row-value pct ${cN}">${formatPct(d.PctNo)}</span>
                        </div>
                        <div class="mobile-progress" style="width: ${pctN}%"></div>
                    </div>
                </div>
                <div class="volume-bar">
                    <span class="volume-label">${_t("app.dyn.toplam_hacim","TOPLAM HACİM")}</span>
                    <span class="volume-value">${formatVolume(d.Volume)}</span>
                </div>
            `;}else{html=`
                <div class="info-columns">
                    <div class="info-column">
                        <div class="column-header">${_t('app.dyn.evet','Evet')}</div>
                        <div class="column-row">
                            <span class="row-label">${_t("app.mod.oran_row","Oran")}</span>
                            <span class="row-value odds">${formatOdds(d.OddsYes || d.Yes)}${trendYes}</span>
                        </div>
                    </div>
                    <div class="info-column">
                        <div class="column-header">${_t('app.dyn.hayir','Hayır')}</div>
                        <div class="column-row">
                            <span class="row-label">${_t("app.mod.oran_row","Oran")}</span>
                            <span class="row-value odds">${formatOdds(d.OddsNo || d.No)}${trendNo}</span>
                        </div>
                    </div>
                </div>
                <div class="volume-bar">
                    <span class="volume-label">Volume</span>
                    <span class="volume-value">${formatVolume(d.Volume)}</span>
                </div>
            `;}}
card.innerHTML=html;}
function getTrendArrow(current,previous){if(!current||!previous)return'';const curr=parseFloat(String(current).replace(/[^0-9.]/g,''));const prev=parseFloat(String(previous).replace(/[^0-9.]/g,''));if(isNaN(curr)||isNaN(prev))return'';if(curr>prev)return'<span class="trend-up">↑</span>';if(curr<prev)return'<span class="trend-down">↓</span>';return'';}
function switchMobileTab(tabName){if(tabName==='live'&&(window.userPlan==='core'||window.userPlan==='test')){document.querySelectorAll('.mobile-tab-bar .mob-tab').forEach(t=>{t.classList.remove('active');if(t.dataset.tab===tabName)t.classList.add('active');});document.querySelectorAll('.mobile-tab-content').forEach(c=>{c.classList.remove('active');});var _tc=document.getElementById('mobileTabLive');if(_tc)_tc.classList.add('active');var _lb=document.getElementById('modalLiveBody');if(_lb)_lb.innerHTML=proLockPanelHtml();var _lt=document.getElementById('modalLiveMarketTabs');if(_lt)_lt.innerHTML='';return;}
document.querySelectorAll('.mobile-tab-bar .mob-tab').forEach(t=>{t.classList.remove('active');if(t.dataset.tab===tabName)t.classList.add('active');});document.querySelectorAll('.mobile-tab-content').forEach(c=>{c.classList.remove('active');});const targetTab=document.getElementById('mobileTab'+tabName.charAt(0).toUpperCase()+tabName.slice(1));if(targetTab)targetTab.classList.add('active');}
function isMobile(){return window.innerWidth<=768;}
async function loadChartHistory(matchId,market){if(!selectedMatch)return;const home=selectedMatch.home_team;const away=selectedMatch.away_team;const league=selectedMatch.league||'';await loadChartWithTrends(home,away,market,league);}
function setMobileViewMode(mode){chartViewMode=mode;document.querySelectorAll('.mob-view-btn').forEach(btn=>{btn.classList.toggle('active',btn.dataset.view===mode);});if(selectedMatch&&isMobile()){loadChartHistory(selectedMatch.MatchId,selectedChartMarket);}}
function setMobileSelection(sel){mobileSelectedLine=sel;document.querySelectorAll('.mob-sel-btn').forEach(btn=>{btn.classList.toggle('active',btn.dataset.sel===sel);});if(selectedMatch&&isMobile()){loadChartHistory(selectedMatch.MatchId,selectedChartMarket);}}
function updateMobileSingleLine(){if(selectedMatch&&isMobile()){loadChartHistory(selectedMatch.MatchId,selectedChartMarket);}}
function toggleMobileTimeDropdown(){const menu=document.getElementById('mobTimeMenu');if(menu)menu.classList.toggle('open');}
function setMobileTimeRange(range){mobileTimeRange=range;const rangeMap={'10':'10min','30':'30min','60':'1hour','360':'6hour','720':'12hour','1440':'1day','all':'1day'};chartTimeRange=rangeMap[range]||'1day';const labels={'all':_t('app.dyn.tumu','Tümü'),'10':_t('app.dyn.10_dakika','10 dk'),'30':_t('app.dyn.30_dakika','30 dk'),'60':_t('app.dyn.1_saat','1 saat'),'360':_t('app.dyn.6_saat','6 saat'),'720':_t('app.dyn.12_saat','12 saat'),'1440':_t('app.dyn.1_gun','1 gün')};const mobTimeLabel=document.getElementById('mobTimeLabel');if(mobTimeLabel)mobTimeLabel.textContent=labels[range]||_t('app.flt.all','Tümü');document.querySelectorAll('.mob-time-option').forEach(opt=>{opt.classList.toggle('active',opt.dataset.range===range);});const mobTimeMenu=document.getElementById('mobTimeMenu');if(mobTimeMenu)mobTimeMenu.classList.remove('open');document.querySelectorAll('.time-pill').forEach(pill=>{pill.classList.toggle('active',pill.dataset.range===range);});if(selectedMatch&&isMobile()){loadChartHistory(selectedMatch.MatchId,selectedChartMarket);}}
let mobileChartHistoryData=[];const mobileBackgroundGridPlugin={id:'mobileBackgroundGrid',beforeDatasetsDraw:function(chart){if(!isMobile())return;const ctx=chart.ctx;const chartArea=chart.chartArea;if(!chartArea)return;const{left,right,top,bottom}=chartArea;const width=right-left;const height=bottom-top;const gridColor='rgba(255, 255, 255, 0.08)';ctx.save();ctx.strokeStyle=gridColor;ctx.lineWidth=1;ctx.setLineDash([]);const centerY=top+(height/2);ctx.beginPath();ctx.moveTo(left,centerY);ctx.lineTo(right,centerY);ctx.stroke();const centerX=left+(width/2);ctx.beginPath();ctx.moveTo(centerX,top);ctx.lineTo(centerX,bottom);ctx.stroke();ctx.restore();}};const mobileCrosshairPlugin={id:'mobileCrosshair',afterDatasetsDraw:function(chart){if(!isMobile())return;const ctx=chart.ctx;const chartArea=chart.chartArea;const ds=chart.data.datasets[0];if(!ds||!ds.data||ds.data.length===0)return;const activeElements=chart.getActiveElements();let idx;if(activeElements&&activeElements.length>0){idx=activeElements[0].index;}else if(chart.$crosshairIndex!==undefined&&chart.$crosshairIndex>=0){idx=chart.$crosshairIndex;}else{idx=ds.data.length-1;}
const meta=chart.getDatasetMeta(0);if(!meta||!meta.data||!meta.data[idx])return;const x=meta.data[idx].x;ctx.save();ctx.beginPath();ctx.moveTo(x,chartArea.top);ctx.lineTo(x,chartArea.bottom);ctx.lineWidth=1;ctx.strokeStyle='rgba(139, 148, 158, 0.35)';ctx.setLineDash([]);ctx.stroke();ctx.restore();}};function registerChartPlugins(){if(typeof Chart!=='undefined'){Chart.register(mobileBackgroundGridPlugin);Chart.register(mobileCrosshairPlugin);}}
if(typeof Chart!=='undefined'){registerChartPlugins();}
const mobileBigValueTween={currentText:'',element:null,duration:250,setTarget:function(element,newText){if(!element)return;this.element=element;const oldText=this.currentText||element.textContent||'';newText=String(newText||'--');if(oldText===newText)return;if(!oldText||oldText==='--'||newText==='--'){element.textContent=newText;this.currentText=newText;return;}
element.innerHTML=this.buildOdometerHtml(oldText,newText);this.currentText=newText;requestAnimationFrame(()=>{element.querySelectorAll('.odometer-digit.changing').forEach(digit=>{digit.classList.add('animate');});});},buildOdometerHtml:function(oldText,newText){const maxLen=Math.max(oldText.length,newText.length);const oldChars=oldText.padStart(maxLen,' ').split('');const newChars=newText.padStart(maxLen,' ').split('');let html='';for(let i=0;i<maxLen;i++){const oldChar=oldChars[i];const newChar=newChars[i];if(oldChar===newChar){html+=`<span class="odometer-digit static">${this.escapeHtml(newChar)}</span>`;}else{html+=`<span class="odometer-digit changing">`;html+=`<span class="odometer-old">${this.escapeHtml(oldChar)}</span>`;html+=`<span class="odometer-new">${this.escapeHtml(newChar)}</span>`;html+=`</span>`;}}
return html;},escapeHtml:function(char){if(char===' ')return'&nbsp;';if(char==='<')return'&lt;';if(char==='>')return'&gt;';if(char==='&')return'&amp;';return char;},reset:function(){this.currentText='';if(this.element){this.element.innerHTML='';}
this.element=null;}};function updateMobileValueHeader(dataIndex){if(!isMobile()||!chart)return;const ds=chart.data.datasets[0];if(!ds)return;let idx=dataIndex;if(idx===undefined||idx<0||idx>=ds.data.length){idx=ds.data.length-1;}
const timeLabel=chart.data.labels[idx]||'--:--';const lastTimeLabel=chart.data.labels[chart.data.labels.length-1]||'--:--';const value=ds.data[idx];const activeMarket=selectedChartMarket||currentMarket;const isMoneyway=activeMarket.startsWith('moneyway');const isDropping=activeMarket.startsWith('dropping');const parseStake=(val)=>{if(!val)return'--';const num=parseFloat(String(val).replace(/[£,\s]/g,''));return isNaN(num)?'--':'£'+Math.round(num).toLocaleString();};const parsePct=(val)=>{if(!val)return'--';const str=String(val).replace('%','').trim();const num=parseFloat(str);return isNaN(num)?'--':num.toFixed(1)+'%';};let oddsText='--';let stakeText='--';let pctText='--';let dropPctText='--';if(mobileChartHistoryData&&mobileChartHistoryData[idx]){const h=mobileChartHistoryData[idx];const pick=mobileSelectedLine;if(isDropping){stakeText=parseStake(h.Volume);let openingOdds=0,currentOdds=0;if(pick==='1'){oddsText=h.Odds1||h['1']||'--';openingOdds=parseFloat(h.Opening1||0);currentOdds=parseFloat(h.Odds1||h['1']||0);}else if(pick==='X'){oddsText=h.OddsX||h['X']||'--';openingOdds=parseFloat(h.OpeningX||0);currentOdds=parseFloat(h.OddsX||h['X']||0);}else if(pick==='2'){oddsText=h.Odds2||h['2']||'--';openingOdds=parseFloat(h.Opening2||0);currentOdds=parseFloat(h.Odds2||h['2']||0);}else if(pick==='Under'){oddsText=h.Under||h.OddsUnder||'--';openingOdds=parseFloat(h.OpeningUnder||0);currentOdds=parseFloat(h.Under||h.OddsUnder||0);}else if(pick==='Over'){oddsText=h.Over||h.OddsOver||'--';openingOdds=parseFloat(h.OpeningOver||0);currentOdds=parseFloat(h.Over||h.OddsOver||0);}else if(pick==='Yes'){oddsText=h.Yes||h.OddsYes||'--';openingOdds=parseFloat(h.OpeningYes||0);currentOdds=parseFloat(h.Yes||h.OddsYes||0);}else if(pick==='No'){oddsText=h.No||h.OddsNo||'--';openingOdds=parseFloat(h.OpeningNo||0);currentOdds=parseFloat(h.No||h.OddsNo||0);}
if(openingOdds>0&&currentOdds>0){const changeVal=((openingOdds-currentOdds)/openingOdds)*100;pctText=(changeVal>=0?'-':'+')+Math.abs(changeVal).toFixed(1)+'%';}
if(pctText==='--'&&mobileChartHistoryData&&mobileChartHistoryData.length>0&&currentOdds>0){const firstH=mobileChartHistoryData[0];let firstOdds=0;if(pick==='1')firstOdds=parseFloat(firstH.Odds1||firstH['1']||0);else if(pick==='X')firstOdds=parseFloat(firstH.OddsX||firstH['X']||0);else if(pick==='2')firstOdds=parseFloat(firstH.Odds2||firstH['2']||0);else if(pick==='Under')firstOdds=parseFloat(firstH.Under||firstH.OddsUnder||0);else if(pick==='Over')firstOdds=parseFloat(firstH.Over||firstH.OddsOver||0);else if(pick==='Yes')firstOdds=parseFloat(firstH.Yes||firstH.OddsYes||0);else if(pick==='No')firstOdds=parseFloat(firstH.No||firstH.OddsNo||0);if(firstOdds>0){const changeVal=((firstOdds-currentOdds)/firstOdds)*100;pctText=(changeVal>=0?'-':'+')+Math.abs(changeVal).toFixed(1)+'%';}}}else{if(pick==='1'){oddsText=h.Odds1||h['1']||'--';stakeText=parseStake(h.Amt1);pctText=parsePct(h.Pct1);}else if(pick==='X'){oddsText=h.OddsX||h['X']||'--';stakeText=parseStake(h.AmtX);pctText=parsePct(h.PctX);}else if(pick==='2'){oddsText=h.Odds2||h['2']||'--';stakeText=parseStake(h.Amt2);pctText=parsePct(h.Pct2);}else if(pick==='Under'){oddsText=h.Under||h.OddsUnder||'--';stakeText=parseStake(h.AmtUnder);pctText=parsePct(h.PctUnder);}else if(pick==='Over'){oddsText=h.Over||h.OddsOver||'--';stakeText=parseStake(h.AmtOver);pctText=parsePct(h.PctOver);}else if(pick==='Yes'){oddsText=h.Yes||h.OddsYes||'--';stakeText=parseStake(h.AmtYes);pctText=parsePct(h.PctYes);}else if(pick==='No'){oddsText=h.No||h.OddsNo||'--';stakeText=parseStake(h.AmtNo);pctText=parsePct(h.PctNo);}}}
let bigValueText='--';let secondaryText='--';let secondaryLabel='Para';if(isMoneyway){if(value!==null&&value!==undefined){if(chartViewMode==='money'){bigValueText='£'+Math.round(value).toLocaleString();secondaryText=pctText;secondaryLabel='Yüzde';}else{bigValueText=value.toFixed(1)+'%';secondaryText=stakeText;secondaryLabel='Para';}}}else if(isDropping){if(value!==null&&value!==undefined){bigValueText=value.toFixed(2);}else if(oddsText&&oddsText!=='--'){const cleanOdds=String(oddsText).replace(/[^0-9.]/g,'');bigValueText=cleanOdds||oddsText;}
secondaryText=pctText;secondaryLabel='Yüzde';}
void 0;const bigValueEl=document.getElementById('mvhBigValue');const changeEl=document.getElementById('mvhChange');const oddsEl=document.getElementById('mvhOdds');const oddsLabelEl=document.getElementById('mvhOddsLabel');const stakeEl=document.getElementById('mvhStake');const stakeLabelEl=document.getElementById('mvhStakeLabel');const timeEl=document.getElementById('mvhTime');if(bigValueEl){mobileBigValueTween.setTarget(bigValueEl,bigValueText);}
if(changeEl)changeEl.textContent='Son değer • '+lastTimeLabel;if(isDropping){if(oddsLabelEl)oddsLabelEl.textContent='Para';if(oddsEl){oddsEl.textContent=stakeText;oddsEl.classList.remove('moneyway-oran');oddsEl.classList.add('dropping-para');}
if(stakeLabelEl)stakeLabelEl.textContent='Değişim';if(stakeEl){stakeEl.textContent=pctText;stakeEl.classList.remove('moneyway-para');stakeEl.classList.remove('positive','negative');const pctStr=String(pctText).trim();if(pctStr.startsWith('+')||(pctStr.match(/^[0-9]/)&&parseFloat(pctStr)>0)){stakeEl.classList.add('positive');}else if(pctStr.startsWith('-')){stakeEl.classList.add('negative');}}}else{if(oddsLabelEl)oddsLabelEl.textContent='Oran';if(oddsEl){oddsEl.textContent=oddsText;oddsEl.classList.remove('dropping-para');oddsEl.classList.add('moneyway-oran');}
if(stakeLabelEl)stakeLabelEl.textContent=secondaryLabel;if(stakeEl){stakeEl.textContent=secondaryText;stakeEl.classList.remove('positive','negative');stakeEl.classList.add('moneyway-para');}}
if(timeEl)timeEl.textContent=timeLabel;}
function updateMobileValuePanel(dataIndex){updateMobileValueHeader(dataIndex);}
function updateMobileSelectionButtons(market){const toggle=document.getElementById('mobSelectionToggle');if(!toggle)return;let buttons=[];let validSelections=[];if(market.includes('1x2')){buttons=[{sel:'1',label:'1'},{sel:'X',label:'X'},{sel:'2',label:'2'}];validSelections=['1','X','2'];}else if(market.includes('ou25')){buttons=[{sel:'Under',label:_t('app.dyn.alt','Alt')},{sel:'Over',label:_t('app.dyn.ust','Üst')}];validSelections=['Under','Over'];}else if(market.includes('btts')){buttons=[{sel:'Yes',label:_t('app.dyn.evet','Evet')},{sel:'No',label:_t('app.dyn.hayir','Hayır')}];validSelections=['Yes','No'];}
if(!validSelections.includes(mobileSelectedLine)){mobileSelectedLine=validSelections[0]||'1';}
toggle.innerHTML=buttons.map((b)=>`<button class="mob-sel-btn ${b.sel === mobileSelectedLine ? 'active' : ''}" data-sel="${b.sel}" onclick="setMobileSelection('${b.sel}')">${b.label}</button>`).join('');}
document.addEventListener('click',function(e){const dropdown=document.querySelector('.mob-time-dropdown');const menu=document.getElementById('mobTimeMenu');if(dropdown&&menu&&!dropdown.contains(e.target)){menu.classList.remove('open');}});function closeModal(){++_modalRequestId;document.getElementById('modalOverlay').classList.remove('active');switchMobileTab('chart');desktopChartSectionOpen=true;const chartBody=document.getElementById('desktopChartBody');if(chartBody)chartBody.style.display='';const chartChevron=document.getElementById('desktopChartChevron');if(chartChevron)chartChevron.textContent='▼';const chartTooltip=document.getElementById('chartjs-tooltip');if(chartTooltip){chartTooltip.style.opacity=0;chartTooltip.style.visibility='hidden';chartTooltip.style.display='none';}
const trendTooltip=document.querySelector('.odds-trend-tooltip');if(trendTooltip){trendTooltip.classList.remove('visible');}
if(chart){chart.destroy();chart=null;}
selectedMatch=null;modalOddsData=null;previousOddsData=null;bulkHistoryCache={};bulkHistoryCacheKey='';currentChartHistoryData=[];}

function roundToBucket(timestamp){const dt=toTurkeyTime(timestamp);if(!dt||!dt.isValid())return dayjs().tz(APP_TIMEZONE);const config=getBucketConfig();const bucketMinutes=config.bucketMinutes;const minutes=dt.hour()*60+dt.minute();const roundedMinutes=Math.floor(minutes/bucketMinutes)*bucketMinutes;return dt.startOf('day').add(roundedMinutes,'minute');}

window._sxfModalChartRuntimePromise = window._sxfModalChartRuntimePromise || null;
function _getModalChartRuntimeUrl() {
    try {
        const scripts = document.getElementsByTagName('script');
        for (let i = scripts.length - 1; i >= 0; i--) {
            const src = scripts[i].src || '';
            if (src.indexOf('/static/js/app.js') !== -1) {
                const queryIndex = src.indexOf('?');
                const query = queryIndex >= 0 ? src.slice(queryIndex) : '';
                return '/static/js/modal-chart.js' + query;
            }
        }
    } catch (e) {}
    return '/static/js/modal-chart.js';
}

function loadModalChartRuntime() {
    if (typeof window.__sxfLoadChartImpl === 'function') return Promise.resolve();
    if (window._sxfModalChartRuntimePromise) return window._sxfModalChartRuntimePromise;

    window._sxfModalChartRuntimePromise = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = _getModalChartRuntimeUrl();
        script.async = true;
        script.onload = () => {
            if (typeof window.__sxfLoadChartImpl === 'function') {
                resolve();
                return;
            }
            window._sxfModalChartRuntimePromise = null;
            reject(new Error('Modal chart runtime loaded without implementation'));
        };
        script.onerror = () => {
            window._sxfModalChartRuntimePromise = null;
            reject(new Error('Modal chart runtime failed to load'));
        };
        document.head.appendChild(script);
    });
    return window._sxfModalChartRuntimePromise;
}

async function loadChart(...args) {
    await loadModalChartRuntime();
    return window.__sxfLoadChartImpl(...args);
}

let brushStartIndex=0;let brushEndIndex=100;let brushDataLength=0;

function resetBrushSlider(){const brushStart=document.querySelector('#brushStart');const brushEnd=document.querySelector('#brushEnd');if(brushStart&&brushEnd){brushStart.value=0;brushEnd.value=brushDataLength-1;const brushHighlight=document.querySelector('#brushHighlight');if(brushHighlight){brushHighlight.style.left='0%';brushHighlight.style.width='100%';}
const brushRangeInfo=document.querySelector('#brushRange');if(brushRangeInfo){brushRangeInfo.textContent='Tüm veri';}}}
function resetChartZoom(){if(chart){chart.resetZoom();chart.options.scales.x.min=undefined;chart.options.scales.x.max=undefined;chart.update('none');}
resetBrushSlider();}

function setChartTimeRange(range){chartTimeRange=range;document.querySelectorAll('.chart-time-btn').forEach(btn=>{btn.classList.remove('active');if(btn.dataset.range===range){btn.classList.add('active');}});if(selectedMatch){loadChart(selectedMatch.home_team,selectedMatch.away_team,selectedChartMarket,selectedMatch.league||'');}}
function setChartViewMode(mode){chartViewMode=mode;document.querySelectorAll('.chart-view-btn').forEach(btn=>{btn.classList.remove('active');if(btn.dataset.mode===mode){btn.classList.add('active');}});if(selectedMatch){loadChart(selectedMatch.home_team,selectedMatch.away_team,selectedChartMarket,selectedMatch.league||'');}}

function generateExportFilename(extension){const match=selectedMatch;if(!match)return`SmartXFlow_export.${extension}`;const now=new Date();const dateStr=now.getFullYear().toString()+
String(now.getMonth()+1).padStart(2,'0')+
String(now.getDate()).padStart(2,'0')+'_'+
String(now.getHours()).padStart(2,'0')+
String(now.getMinutes()).padStart(2,'0');const league=(match.league||'League').replace(/[^a-zA-Z0-9]/g,'');const home=(match.home_team||'Home').replace(/[^a-zA-Z0-9]/g,'');const away=(match.away_team||'Away').replace(/[^a-zA-Z0-9]/g,'');const marketMap={'moneyway_1x2':'MW1X2','moneyway_ou25':'MW25','moneyway_btts':'MWBTTS','dropping_1x2':'Drop1X2','dropping_ou25':'Drop25','dropping_btts':'DropBTTS'};const marketLabel=marketMap[selectedChartMarket]||'Chart';return`SmartXFlow_${league}_${home}-${away}_${marketLabel}_${dateStr}.${extension}`;}
function isEXEEnvironment(){return typeof window.pywebview!=='undefined'||window.location.protocol==='file:'||navigator.userAgent.toLowerCase().includes('pywebview');}
function showExportNotification(message,isError=false){const existing=document.querySelector('.export-notification');if(existing)existing.remove();const notification=document.createElement('div');notification.className='export-notification';notification.style.cssText=`
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
    `;notification.textContent=message;document.body.appendChild(notification);setTimeout(()=>notification.remove(),4000);}
async function savePNGViaAPI(canvasOrDataUrl,filename){if(isEXEEnvironment()){try{const imageData=(canvasOrDataUrl instanceof HTMLCanvasElement)?canvasOrDataUrl.toDataURL('image/png'):canvasOrDataUrl;const response=await fetch('/api/export/png',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({image:imageData,filename:filename})});const result=await response.json();if(result.success){showExportNotification(`PNG kaydedildi: ${result.path}`);return true;}}catch(err){console.error('[PNG Export] API error:',err);}}
try{let blob;if(canvasOrDataUrl instanceof HTMLCanvasElement){blob=await new Promise(resolve=>canvasOrDataUrl.toBlob(resolve,'image/png'));}else{blob=await(await fetch(canvasOrDataUrl)).blob();}
const blobUrl=URL.createObjectURL(blob);const link=document.createElement('a');link.download=filename;link.href=blobUrl;link.style.display='none';document.body.appendChild(link);link.click();setTimeout(()=>{document.body.removeChild(link);URL.revokeObjectURL(blobUrl);},200);showExportNotification('PNG indirildi');return true;}catch(downloadErr){console.error('[PNG Export] Download error:',downloadErr);showExportNotification('PNG indirme hatası',true);return false;}}
function exportChartPNG(){if(!selectedMatch){showExportNotification('Maç bulunamadı',true);return;}
const exportBtn=document.querySelector('.chart-export-btn');if(exportBtn)exportBtn.textContent='⏳';const resetButton=()=>{if(exportBtn){exportBtn.innerHTML=`
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                    <circle cx="8.5" cy="8.5" r="1.5"/>
                    <polyline points="21 15 16 10 5 21"/>
                </svg>
                PNG
            `;}
removeExportOverlay();};const filename=generateExportFilename('png');const modalContent=document.querySelector('.modal-content');if(!modalContent){showExportNotification('Modal bulunamadı',true);resetButton();return;}
showExportOverlay(modalContent);const closeBtn=document.querySelector('.modal-close');const exportBtns=document.querySelector('.chart-export-btns');if(closeBtn)closeBtn.style.visibility='hidden';if(exportBtns)exportBtns.style.visibility='hidden';const modalBody=document.querySelector('.modal-body');const originalStyles={modalContent:{maxHeight:modalContent.style.maxHeight,height:modalContent.style.height,overflow:modalContent.style.overflow},modalBody:modalBody?{maxHeight:modalBody.style.maxHeight,height:modalBody.style.height,overflow:modalBody.style.overflow}:null};modalContent.style.maxHeight='none';modalContent.style.height='auto';modalContent.style.overflow='visible';if(modalBody){modalBody.style.maxHeight='none';modalBody.style.height='auto';modalBody.style.overflow='visible';}
const restoreStyles=()=>{modalContent.style.maxHeight=originalStyles.modalContent.maxHeight;modalContent.style.height=originalStyles.modalContent.height;modalContent.style.overflow=originalStyles.modalContent.overflow;if(modalBody&&originalStyles.modalBody){modalBody.style.maxHeight=originalStyles.modalBody.maxHeight;modalBody.style.height=originalStyles.modalBody.height;modalBody.style.overflow=originalStyles.modalBody.overflow;}
if(closeBtn)closeBtn.style.visibility='';if(exportBtns)exportBtns.style.visibility='';};if(typeof html2canvas==='undefined'){restoreStyles();showExportNotification('PNG kütüphanesi yüklenemedi',true);resetButton();return;}
if(chart){chart.options.animation=false;chart.update('none');}
requestAnimationFrame(()=>{setTimeout(()=>{html2canvas(modalContent,{backgroundColor:'#1a1d21',scale:window.devicePixelRatio||1,useCORS:true,allowTaint:false,logging:false,imageTimeout:5000,onclone:function(clonedDoc){const clonedCanvas=clonedDoc.querySelector('#oddsChart');if(clonedCanvas)clonedCanvas.crossOrigin='anonymous';}}).then(async canvas=>{restoreStyles();await savePNGViaAPI(canvas,filename);resetButton();}).catch(err=>{restoreStyles();showExportNotification('PNG oluşturma hatası: '+err.message,true);resetButton();});},50);});}
function showExportOverlay(container){removeExportOverlay();const overlay=document.createElement('div');overlay.id='pngExportOverlay';overlay.style.cssText='position:absolute;top:0;left:0;right:0;bottom:0;background:rgba(21,32,43,0.7);display:flex;align-items:center;justify-content:center;z-index:9999;border-radius:12px;pointer-events:none;';overlay.innerHTML='<div style="color:#fff;font-size:14px;text-align:center;"><div style="margin-bottom:8px;font-size:24px;">⏳</div>PNG hazırlanıyor...</div>';container.style.position='relative';container.appendChild(overlay);}
function removeExportOverlay(){const existing=document.getElementById('pngExportOverlay');if(existing)existing.remove();}
function exportChartPNGFallback(filename,resetButton){const modalContent=document.querySelector('.modal-content');if(!modalContent){showExportNotification('Modal bulunamadı',true);resetButton();return;}
const closeBtn=document.querySelector('.modal-close');if(closeBtn)closeBtn.style.display='none';const modalBody=document.querySelector('.modal-body');const originalStyles={modalContent:{maxHeight:modalContent.style.maxHeight,height:modalContent.style.height,overflow:modalContent.style.overflow},modalBody:modalBody?{maxHeight:modalBody.style.maxHeight,height:modalBody.style.height,overflow:modalBody.style.overflow}:null};const fullHeight=modalContent.scrollHeight;modalContent.style.maxHeight='none';modalContent.style.height=fullHeight+'px';modalContent.style.overflow='visible';if(modalBody){modalBody.style.maxHeight='none';modalBody.style.height='auto';modalBody.style.overflow='visible';}
const restoreStyles=()=>{modalContent.style.maxHeight=originalStyles.modalContent.maxHeight;modalContent.style.height=originalStyles.modalContent.height;modalContent.style.overflow=originalStyles.modalContent.overflow;if(modalBody&&originalStyles.modalBody){modalBody.style.maxHeight=originalStyles.modalBody.maxHeight;modalBody.style.height=originalStyles.modalBody.height;modalBody.style.overflow=originalStyles.modalBody.overflow;}
if(closeBtn)closeBtn.style.display='';};if(typeof html2canvas==='undefined'){restoreStyles();showExportNotification('PNG kütüphanesi yüklenemedi',true);resetButton();return;}
if(chart){chart.options.animation=false;chart.update('none');}
requestAnimationFrame(()=>{setTimeout(()=>{html2canvas(modalContent,{backgroundColor:'#1c1f23',scale:window.devicePixelRatio||1,logging:false,useCORS:true,allowTaint:false,imageTimeout:5000,height:modalContent.scrollHeight,windowHeight:modalContent.scrollHeight,scrollY:0,scrollX:0,onclone:function(clonedDoc){const clonedCanvas=clonedDoc.querySelector('#oddsChart');if(clonedCanvas)clonedCanvas.crossOrigin='anonymous';}}).then(async canvas=>{restoreStyles();await savePNGViaAPI(canvas,filename);resetButton();}).catch(err=>{restoreStyles();showExportNotification('PNG oluşturma hatası',true);resetButton();});},50);});}
function exportChartCSV(){if(!chart||!selectedMatch)return;const market=selectedChartMarket;const isMoneyway=market.startsWith('moneyway');const datasets=chart.data.datasets;const labels=chart.data.labels;const visibleDatasets=datasets.filter(ds=>!ds.hidden);const visibleSeriesNames=visibleDatasets.map(ds=>ds.label).join(', ');const timeRangeLabels={'10min':_t('app.dyn.10_dakika','10 dakika'),'30min':_t('app.dyn.30_dakika','30 dakika'),'1hour':_t('app.dyn.1_saat','1 saat'),'6hour':_t('app.dyn.6_saat','6 saat'),'12hour':_t('app.dyn.12_saat','12 saat'),'1day':_t('app.dyn.1_gun','1 gün')};const timeRangeLabel=timeRangeLabels[chartTimeRange]||_t('app.dyn.1_gun','1 gün');const marketLabels={'moneyway_1x2':'Moneyway 1X2','moneyway_ou25':'Moneyway Alt/Üst 2.5','moneyway_btts':'Moneyway KG','dropping_1x2':'Oran 1X2','dropping_ou25':'Oran A/Ü 2.5','dropping_btts':'Oran KG'};const marketLabel=marketLabels[market]||market;let csvContent='\uFEFF';csvContent+=`# SmartXFlow - Odds Export\n`;csvContent+=`# Match: ${selectedMatch.home_team} vs ${selectedMatch.away_team}\n`;csvContent+=`# League: ${selectedMatch.league}\n`;csvContent+=`# Match Date: ${selectedMatch.start_time || 'N/A'}\n`;csvContent+=`# Chart Type: ${marketLabel}\n`;csvContent+=`# Time Range: ${timeRangeLabel}\n`;csvContent+=`# Visible Series: ${visibleSeriesNames}\n`;csvContent+=`# Export Date: ${nowTurkey().format('DD.MM.YYYY HH:mm')} (TR)\n`;csvContent+=`#\n`;let headers=['timestamp'];visibleDatasets.forEach(ds=>{headers.push(ds.label.toLowerCase().replace(/\s+/g,'_'));});csvContent+=headers.join(',')+'\n';for(let i=0;i<labels.length;i++){let row=[labels[i]];visibleDatasets.forEach(ds=>{const val=ds.data[i];row.push(val!==null&&val!==undefined?val:'');});csvContent+=row.map(cell=>{if(typeof cell==='string'&&(cell.includes(',')||cell.includes('"')||cell.includes('\n'))){return'"'+cell.replace(/"/g,'""')+'"';}
return cell;}).join(',')+'\n';}
const blob=new Blob([csvContent],{type:'text/csv;charset=utf-8;'});const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download=generateExportFilename('csv');link.click();URL.revokeObjectURL(link.href);}
async function exportFullMatchTXT(){if(!selectedMatch)return;const home=selectedMatch.home_team;const away=selectedMatch.away_team;const league=selectedMatch.league||'';const matchDate=selectedMatch.date||selectedMatch.start_time||'';const matchId=selectedMatch.match_id||'';const cacheKey=`${home}|${away}|${league}|${currentSource}`;let marketsData={};if(bulkHistoryCacheKey===cacheKey&&Object.keys(bulkHistoryCache).length>0){marketsData=bulkHistoryCache;}else{try{const resp=await fetch(`/api/match/history/bulk?home=${encodeURIComponent(home)}&away=${encodeURIComponent(away)}&league=${encodeURIComponent(league)}`);if(!resp.ok){alert('Veri yüklenemedi (HTTP '+resp.status+'). Lütfen tekrar deneyin.');return;}
const data=await resp.json();marketsData=data.markets||{};}catch(e){console.error('[FullTXT] Bulk fetch error:',e);alert('Veri yüklenirken hata oluştu. Lütfen tekrar deneyin.');return;}}
var totalSnapshots=0;Object.values(marketsData).forEach(function(m){if(m&&m.history)totalSnapshots+=m.history.length;});if(totalSnapshots===0){alert('Bu maç için henüz snapshot verisi bulunamadı.');return;}
let alarmsData={};if(matchId){try{const resp=await fetch(`/api/match/${matchId}/snapshot?include=alarms`);if(resp.ok){const data=await resp.json();alarmsData=data.alarms||{};}}catch(e){console.error('[FullTXT] Alarms fetch error:',e);}}
var txt='';txt+='================================================================================\n';txt+='SmartXFlow - Full Match Data Export\n';txt+='================================================================================\n';txt+='Mac: '+home+' vs '+away+'\n';txt+='Lig: '+league+'\n';txt+='Mac Tarihi: '+matchDate+'\n';txt+='Mac ID: '+matchId+'\n';txt+='Export Tarihi: '+nowTurkey().format('DD.MM.YYYY HH:mm')+' (TR)\n';txt+='Toplam Snapshot: '+totalSnapshots+'\n';txt+='================================================================================\n\n';var marketDefs=[{key:'moneyway_1x2',label:'Moneyway 1X2',cols:['ScrapedAt','Odds1','OddsX','Odds2','Pct1','PctX','Pct2','Amt1','AmtX','Amt2','Volume','Odds1_prev','OddsX_prev','Odds2_prev','Trend1','TrendX','Trend2','DropPct1','DropPctX','DropPct2']},{key:'moneyway_ou25',label:'Moneyway O/U 2.5',cols:['ScrapedAt','Over','Under','PctOver','PctUnder','AmtOver','AmtUnder','Volume','Line','Over_prev','Under_prev','TrendOver','TrendUnder','DropPctOver','DropPctUnder']},{key:'moneyway_btts',label:'Moneyway BTTS',cols:['ScrapedAt','OddsYes','OddsNo','PctYes','PctNo','AmtYes','AmtNo','Volume','OddsYes_prev','OddsNo_prev','TrendYes','TrendNo','DropPctYes','DropPctNo']},{key:'dropping_1x2',label:'Dropping Odds 1X2',cols:['ScrapedAt','Odds1','OddsX','Odds2','Odds1_prev','OddsX_prev','Odds2_prev','Trend1','TrendX','Trend2','DropPct1','DropPctX','DropPct2','Volume']},{key:'dropping_ou25',label:'Dropping Odds O/U 2.5',cols:['ScrapedAt','Over','Under','Over_prev','Under_prev','TrendOver','TrendUnder','DropPctOver','DropPctUnder','Volume','Line']},{key:'dropping_btts',label:'Dropping Odds BTTS',cols:['ScrapedAt','OddsYes','OddsNo','OddsYes_prev','OddsNo_prev','TrendYes','TrendNo','DropPctYes','DropPctNo','Volume']}];txt+='===== SNAPSHOT VERILERI =====\n\n';marketDefs.forEach(function(md){var mdata=marketsData[md.key];var rows=mdata?(mdata.history||[]):[];txt+='--- '+md.label+' ('+rows.length+' snapshot) ---\n';if(rows.length>0){rows.forEach(function(row){var ts=row['ScrapedAt']||'';var parts=[];md.cols.forEach(function(col){if(col!=='ScrapedAt'){var v=row[col];if(v!==null&&v!==undefined&&v!==''){parts.push(col+'='+v);}}});txt+='  '+ts+' | '+parts.join(' | ')+'\n';});}else{txt+='  (veri yok)\n';}
txt+='\n';});txt+='===== ALARM VERILERI =====\n\n';var alarmTypes=['sharp','bigmoney','volumeshock','dropping','volumeleader','mim'];var hasAlarms=false;alarmTypes.forEach(function(atype){var alarms=alarmsData[atype]||[];if(alarms.length>0)hasAlarms=true;});if(hasAlarms){alarmTypes.forEach(function(atype){var alarms=alarmsData[atype]||[];if(alarms.length===0)return;txt+='--- '+atype.toUpperCase()+' ('+alarms.length+' alarm) ---\n';alarms.forEach(function(a){var ts=a.trigger_at||a.triggered_at||a.created_at||a.scraped_at||'';var market=a.market||'';var side=a.selection||a.side||'';var odds=a.odds||a.current_odds||'';var vol=a.volume||a.total_volume||a.amount||'';var details='';if(atype==='sharp')details='score='+(a.sharp_score||a.score||'');else if(atype==='bigmoney')details='amount='+(a.incoming_amount||a.amount||'');else if(atype==='volumeshock')details='shock='+(a.shock_multiplier||a.shock||'')+'x';else if(atype==='dropping')details='drop='+(a.drop_pct||a.drop_percent||'')+'%';else if(atype==='volumeleader')details='from='+(a.from_side||'')+' to='+(a.to_side||'')+' pct='+(a.to_pct||'');else if(atype==='mim')details='impact='+(a.impact_score||a.impact||'');txt+='  '+ts+' | market='+market+' | side='+side+' | odds='+odds+' | vol='+vol+' | '+details+'\n';});txt+='\n';});}else{txt+='  Bu mac icin alarm verisi bulunamadi.\n';}
var blob=new Blob([txt],{type:'text/plain;charset=utf-8;'});var link=document.createElement('a');link.href=URL.createObjectURL(blob);var safeName=(home+'_vs_'+away).replace(/[^a-zA-Z0-9_\-]/g,'_');link.download=safeName+'_full_data.txt';link.click();URL.revokeObjectURL(link.href);}
function toggleChartSeries(market,seriesKey,btn){const stateKey=`${market}_${seriesKey}`;const wasVisible=chartVisibleSeries[stateKey]!==false;chartVisibleSeries[stateKey]=!wasVisible;if(btn){if(chartVisibleSeries[stateKey]){btn.classList.remove('inactive');btn.classList.add('active');}else{btn.classList.remove('active');btn.classList.add('inactive');}}
if(chart){const datasetIndex=chart.data.datasets.findIndex(ds=>ds.label===seriesKey);if(datasetIndex!==-1){chart.data.datasets[datasetIndex].hidden=!chartVisibleSeries[stateKey];chart.update();}}}
function getOddsFromHistory(historyPoint,label,market){if(!historyPoint)return 0;if(market.includes('1x2')){if(label==='1'){const val=historyPoint.Odds1||historyPoint['1'];return val?parseFloat(String(val).split('\n')[0])||0:0;}
if(label==='X'){const val=historyPoint.OddsX||historyPoint['X'];return val?parseFloat(String(val).split('\n')[0])||0:0;}
if(label==='2'){const val=historyPoint.Odds2||historyPoint['2'];return val?parseFloat(String(val).split('\n')[0])||0:0;}}else if(market.includes('ou25')){if(label==='Under'||label.toLowerCase().includes('under')){const val=historyPoint.Under;return val?parseFloat(String(val).split('\n')[0])||0:0;}
if(label==='Over'||label.toLowerCase().includes('over')){const val=historyPoint.Over;return val?parseFloat(String(val).split('\n')[0])||0:0;}}else if(market.includes('btts')){if(label==='Yes'||label.toLowerCase().includes('yes')){const val=historyPoint.OddsYes||historyPoint.Yes;return val?parseFloat(String(val).split('\n')[0])||0:0;}
if(label==='No'||label.toLowerCase().includes('no')){const val=historyPoint.OddsNo||historyPoint.No;return val?parseFloat(String(val).split('\n')[0])||0:0;}}
return 0;}
function getLatestOdds(latestData,label,market){if(market.includes('1x2')){if(label==='1')return parseFloat(latestData.Odds1||latestData['1'])||0;if(label==='X')return parseFloat(latestData.OddsX||latestData['X'])||0;if(label==='2')return parseFloat(latestData.Odds2||latestData['2'])||0;}else if(market.includes('ou25')){if(label==='Under'||label.toLowerCase().includes('under'))return parseFloat(latestData.Under)||0;if(label==='Over'||label.toLowerCase().includes('over'))return parseFloat(latestData.Over)||0;}else if(market.includes('btts')){if(label==='Yes'||label.toLowerCase().includes('yes'))return parseFloat(latestData.OddsYes||latestData.Yes)||0;if(label==='No'||label.toLowerCase().includes('no'))return parseFloat(latestData.OddsNo||latestData.No)||0;}
return 0;}
async function triggerScrape(){const btn=document.getElementById('scrapeBtn');const originalText=btn.innerHTML;btn.disabled=true;btn.innerHTML=`
        <div class="loading-spinner" style="width:14px;height:14px;margin:0;border-width:2px;"></div>
        Scraping...
    `;try{const response=await fetch('/api/scrape',{method:'POST'});const result=await response.json();if(result.status==='ok'){setTimeout(()=>{loadMatches();},3000);}}catch(error){console.error('Scrape error:',error);}
setTimeout(()=>{btn.disabled=false;btn.innerHTML=originalText;checkStatus();},5000);}
async function checkStatus(){try{const response=await fetch('/api/status');const status=await response.json();autoScrapeRunning=status.auto_running;isClientMode=status.mode==='client';const indicator=document.getElementById('statusIndicator');if(indicator){const dot=indicator.querySelector('.status-dot');const text=indicator.querySelector('.status-text');if(status.running){dot.classList.add('running');text.textContent='Scraping...';}else{dot.classList.remove('running');text.textContent=status.supabase_connected?'Ready':'Offline';}}
const lastUpdateTime=document.getElementById('lastUpdateTime');const mobileLastUpdateTime=document.getElementById('mobileLastUpdateTime');const updateText=status.last_data_update_tr||'--:--';if(lastUpdateTime){lastUpdateTime.textContent=updateText;}
if(mobileLastUpdateTime){mobileLastUpdateTime.textContent=updateText;}}catch(error){console.error('Status check error:',error);}}
async function toggleAutoScrape(){const autoBtn=document.getElementById('autoBtn');const intervalSelect=document.getElementById('intervalSelect');const interval=parseInt(intervalSelect.value)||5;autoBtn.disabled=true;try{const action=autoScrapeRunning?'stop':'start';const response=await fetch('/api/scrape/auto',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,interval})});const result=await response.json();autoScrapeRunning=result.auto_running;if(action==='start'&&result.auto_running){setTimeout(()=>loadMatches(),3000);}
checkStatus();}catch(error){console.error('Auto scrape toggle error:',error);}
autoBtn.disabled=false;}
async function updateInterval(){const intervalSelect=document.getElementById('intervalSelect');const newInterval=parseInt(intervalSelect.value)||5;try{const response=await fetch('/api/interval',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({interval:newInterval})});if(!response.ok){console.error('Interval API error:',response.status);return;}
const result=await response.json();void 0;checkStatus();}catch(error){console.error('Update interval error:',error);}}
document.addEventListener('keydown',(e)=>{if(e.key==='Escape'){closeModal();}});let oddsTrendCache={};let oddsTrendCacheByMarket={};let dropMarketsPreloaded=false;async function preloadDropMarkets(){if(dropMarketsPreloaded)return;dropMarketsPreloaded=true;const dropMarkets=['dropping_1x2','dropping_ou25','dropping_btts'];void 0;await Promise.all(dropMarkets.map(async(market)=>{if(!oddsTrendCacheByMarket[market]){try{const response=await fetch(`/api/odds-trend/${market}`);const result=await response.json();oddsTrendCacheByMarket[market]=result.data||{};void 0;}catch(e){console.warn(`[Preload] Failed ${market}:`,e.message);}}}));void 0;}
async function loadOddsTrend(market){if(!market.startsWith('dropping')){oddsTrendCache={};return;}
if(oddsTrendCacheByMarket[market]){oddsTrendCache=oddsTrendCacheByMarket[market];void 0;return;}
try{const response=await fetch(`/api/odds-trend/${market}`);const result=await response.json();oddsTrendCache=result.data||{};oddsTrendCacheByMarket[market]=oddsTrendCache;void 0;}catch(error){console.error('[Odds Trend] Error loading:',error);oddsTrendCache={};}}
function generateTrendIconSVG(trend,pctChange){let color,path;const absPct=Math.abs(pctChange||0);if(trend==='down'){color='#ff0000';if(absPct>=20){path='M2 1 L6 1 L6 4 L10 4 L10 7 L14 7 L14 10 L18 10 L18 11 L26 11';}else if(absPct>=10){path='M2 2 L8 2 L8 5 L14 5 L14 8 L20 8 L20 10 L26 10';}else if(absPct>=5){path='M2 3 L10 3 L10 6 L18 6 L18 9 L26 9';}else if(absPct>=2){path='M2 4 L12 4 L12 7 L26 7 L26 8';}else{path='M2 5 L14 5 L14 7 L26 7';}}else if(trend==='up'){color='#22c55e';if(absPct>=20){path='M2 11 L6 11 L6 8 L10 8 L10 5 L14 5 L14 2 L18 2 L18 1 L26 1';}else if(absPct>=10){path='M2 10 L8 10 L8 7 L14 7 L14 4 L20 4 L20 2 L26 2';}else if(absPct>=5){path='M2 9 L10 9 L10 6 L18 6 L18 3 L26 3';}else if(absPct>=2){path='M2 8 L12 8 L12 5 L26 5 L26 4';}else{path='M2 7 L14 7 L14 5 L26 5';}}else{color='#6B7280';path='M2 6 L26 6';}
return`<svg class="trend-icon-svg" width="28" height="12" viewBox="0 0 28 12">
        <path d="${path}" stroke="${color}" stroke-width="2" fill="none" stroke-linecap="square" stroke-linejoin="miter"/>
    </svg>`;}
function getTrendArrowHTML(trend,pctChange){if(trend==='down'){return`<span class="trend-arrow-drop trend-down-drop">↓</span>`;}else if(trend==='up'){return`<span class="trend-arrow-drop trend-up-drop">↑</span>`;}
return`<span class="trend-arrow-drop trend-stable-drop">↔</span>`;}
function formatPctChange(pctChange,trend){if(pctChange===0||pctChange===null||pctChange===undefined){return'';}
const sign=pctChange>0?'+':'';const absVal=Math.abs(pctChange).toFixed(1);let colorClass='pct-stable';if(trend==='down'){colorClass='pct-down';}else if(trend==='up'){colorClass='pct-up';}
return`<span class="pct-change ${colorClass}">${sign}${pctChange.toFixed(1)}%</span>`;}
function getOddsTrendData(home,away,selection){const key=`${home}|${away}`;const matchData=oddsTrendCache[key];if (!matchData || !matchData.values) { return null; }
return matchData.values[selection]||null;}
function renderOddsWithTrend(oddsValue,trendData){const formattedOdds=formatOdds(oddsValue);const hasHistory=trendData&&trendData.history&&trendData.history.length>=2;const hasTrendOnly=trendData&&trendData.trend&&(trendData.trend==='down'||trendData.trend==='up')&&!hasHistory;if(!hasHistory&&!hasTrendOnly){const trendIcon=generateTrendIconSVG('flat',0);return`
            <div class="odds-trend-cell odds-trend-no-data">
                <div class="trend-icon-container">${trendIcon}</div>
                <div class="odds-value-trend">${formattedOdds}</div>
            </div>
        `;}
const trendIcon=generateTrendIconSVG(trendData.trend,trendData.pct_change||0);const pctHtml=trendData.pct_change!==null&&trendData.pct_change!==undefined?formatPctChange(trendData.pct_change,trendData.trend):'';const tooltipData=JSON.stringify({old:trendData.old,new:trendData.new,pct:trendData.pct_change,trend:trendData.trend,first_scraped:trendData.first_scraped||null}).replace(/"/g,'&quot;');return`
        <div class="odds-trend-cell" data-tooltip="${tooltipData}">
            <div class="trend-icon-container">${trendIcon}</div>
            <div class="odds-value-trend">${formattedOdds}</div>
            ${pctHtml}
        </div>
    `;}
function renderDrop1X2Cell(label,oddsValue,trendData){const formattedOdds=formatOdds(oddsValue);const hasHistory=trendData&&trendData.history&&trendData.history.length>=2;const hasTrendOnly=trendData&&trendData.trend&&(trendData.trend==='down'||trendData.trend==='up')&&!hasHistory;if(!hasHistory&&!hasTrendOnly){const trendIcon=generateTrendIconSVG('flat',0);return`
            <div class="drop-mini-card">
                <div class="drop-trend-icon">${trendIcon}</div>
                <div class="drop-odds">${formattedOdds}</div>
            </div>
        `;}
const trendIcon=generateTrendIconSVG(trendData.trend,trendData.pct_change||0);const pctHtml=trendData.pct_change!==null&&trendData.pct_change!==undefined?formatPctChange(trendData.pct_change,trendData.trend):'';const tooltipData=JSON.stringify({old:trendData.old,new:trendData.new,pct:trendData.pct_change,trend:trendData.trend,first_scraped:trendData.first_scraped||null}).replace(/"/g,'&quot;');const changeClass=trendData.trend==='up'?'positive':(trendData.trend==='down'?'negative':'');return`
        <div class="drop-mini-card" data-tooltip="${tooltipData}">
            <div class="drop-trend-icon">${trendIcon}</div>
            <div class="drop-odds">${formattedOdds}</div>
            ${pctHtml ? `<div class="drop-change ${changeClass}">${pctHtml}</div>` : ''}
        </div>
    `;}
function generateFlatSparklineSVG(){const width=40;const height=16;const y=height/2;return`<svg class="sparkline-svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
        <line x1="2" y1="${y}" x2="${width - 2}" y2="${y}" stroke="#6b7280" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`;}
function createTrendTooltip(){let tooltip=document.getElementById('oddsTrendTooltip');if(!tooltip){tooltip=document.createElement('div');tooltip.id='oddsTrendTooltip';tooltip.className='odds-trend-tooltip';document.body.appendChild(tooltip);}
return tooltip;}
function showTrendTooltip(event){const cell=event.currentTarget;const tooltipData=cell.dataset.tooltip;if(!tooltipData)return;try{const data=JSON.parse(tooltipData);const tooltip=createTrendTooltip();const trendText=data.trend==='down'?'Oran düştü':data.trend==='up'?'Oran yükseldi':'Değişim yok';const trendClass=data.trend==='down'?'tooltip-down':data.trend==='up'?'tooltip-up':'tooltip-stable';const diff=data.new-data.old;const diffSign=diff>0?'+':'';let firstScrapedText='';if(data.first_scraped){const dt=toTurkeyTime(data.first_scraped);if(dt&&dt.isValid()){firstScrapedText=dt.format('DD.MM HH:mm');}}
tooltip.innerHTML=`
            <div class="tooltip-title">SON 24 SAAT DEĞİŞİM</div>
            <div class="tooltip-block">
                <div class="tooltip-row">
                    <span class="tooltip-label">24s önceki oran:</span>
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
        `;const rect=cell.getBoundingClientRect();tooltip.style.left=`${rect.left + rect.width / 2}px`;tooltip.style.top=`${rect.top - 10}px`;tooltip.classList.add('visible');}catch(e){console.error('[Tooltip] Parse error:',e);}}
function hideTrendTooltip(){const tooltip=document.getElementById('oddsTrendTooltip');if(tooltip){tooltip.classList.remove('visible');}}
function attachTrendTooltipListeners(){document.querySelectorAll('.odds-trend-cell, .drop-mini-card[data-tooltip]').forEach(cell=>{cell.addEventListener('mouseenter',showTrendTooltip);cell.addEventListener('mouseleave',hideTrendTooltip);});}
let alertBandData=[];let alertBandRenderTimeout=null;let lastAlertBandHash='';let lastTopAlarmKey=null;let isHighlightingNewAlarm=false;function getAlarmKey(alarm){if(!alarm)return null;const home=alarm.home||alarm.home_team||'';const type=alarm._type||'';const eventTime=alarm.trigger_at||alarm.event_time||alarm.created_at||'';return`${home}|${type}|${eventTime}`;}
function scheduleAlertBandRender(){if(alertBandRenderTimeout){clearTimeout(alertBandRenderTimeout);}
alertBandRenderTimeout=setTimeout(()=>{const newHash=JSON.stringify(alertBandData.slice(0,10).map(a=>a.home+a._type+(a.trigger_at||a.event_time||'')));const isFirstRender=lastAlertBandHash==='';const hashChanged=newHash!==lastAlertBandHash;if(isFirstRender||hashChanged){lastAlertBandHash=newHash;const currentTopKey=getAlarmKey(alertBandData[0]);const isNewTopAlarm=lastTopAlarmKey!==null&&currentTopKey!==lastTopAlarmKey;if(isNewTopAlarm&&alertBandData[0]&&!isHighlightingNewAlarm){highlightNewAlarm(alertBandData[0]);}else{renderAlertBand();}
lastTopAlarmKey=currentTopKey;}
updateAlertBandBadge();},100);}
function highlightNewAlarm(alarm){isHighlightingNewAlarm=true;const band=document.getElementById('alertBandTrack');if(!band){isHighlightingNewAlarm=false;return;}
band.classList.add('highlight-mode');const info=getAlertType(alarm);const home=alarm.home||alarm.home_team||'?';const away=alarm.away||alarm.away_team||'?';const rawSel=(alarm.selection||alarm.side||'').toUpperCase();const selMap={'U':_t('app.dyn.alt','Alt'),'O':_t('app.dyn.ust','Üst'),'Y':_t('app.dyn.evet','Evet'),'N':_t('app.dyn.hayir','Hayır'),'1':'1','X':'X','2':'2','UNDER':_t('app.dyn.alt','Alt'),'OVER':_t('app.dyn.ust','Üst'),'YES':_t('app.dyn.evet','Evet'),'NO':_t('app.dyn.hayir','Hayır')};const selection=selMap[rawSel]||rawSel;const alarmType=alarm._type||'sharp';let value='';if(alarmType==='sharp'){value=(alarm.sharp_score||0).toFixed(1);}else if(alarmType==='volumeshock'){value=`${(alarm.volume_shock_value || alarm.volume_shock || alarm.volume_shock_multiplier || 0).toFixed(1)}x`;}else if(alarmType==='bigmoney'){value=`£${Math.round(Number(alarm.incoming_money || alarm.stake || 0)).toLocaleString('en-GB')}`;}else if(alarmType==='dropping'){value=`▼ ${(alarm.drop_pct || 0).toFixed(1)}%`;}else if(alarmType==='publicmove'){value=`${(alarm.move_score || alarm.trap_score || alarm.sharp_score || 0).toFixed(0)}`;}else if(alarmType==='volumeleader'){value=`%${(alarm.new_leader_share || 0).toFixed(0)}`;}
let contentHtml='';if(alarmType==='volumeleader'){const oldLeader=alarm.old_leader||alarm.previous_leader||'?';const newLeader=alarm.new_leader||alarm.selection||'?';const isMobile=window.innerWidth<=768;const matchDisplay=isMobile?home:`${home} - ${away}`;contentHtml=`
            <span class="ab-dot dot-${info.pillClass}"></span>
            <span class="ab-type">${info.label}</span>
            <span class="ab-sep">—</span>
            <span class="ab-match">${matchDisplay}</span>
            <span class="ab-sep">—</span>
            <span class="ab-leader-change">${oldLeader} <span class="ab-arrow">▸</span> ${newLeader}</span>
        `;}else{const isMobile=window.innerWidth<=768;const matchDisplay=isMobile?home:`${home} - ${away}`;contentHtml=`
            <span class="ab-dot dot-${info.pillClass}"></span>
            <span class="ab-type">${info.label}</span>
            <span class="ab-sep">—</span>
            <span class="ab-match">${matchDisplay}</span>
            <span class="ab-sep">—</span>
            <span class="ab-sel">${selection}</span>
            <span class="ab-val">${value}</span>
        `;}
band.innerHTML=`
        <div class="new-alarm-highlight">
            <div class="ab-pill ${info.pillClass} highlight-pill">
                ${contentHtml}
            </div>
        </div>
    `;void 0;setTimeout(()=>{isHighlightingNewAlarm=false;band.classList.remove('highlight-mode');renderAlertBand();void 0;},5000);}
function parseAlarmTime(timeStr){if(!timeStr)return 0;try{const parts=timeStr.split(' ');if(parts.length<2)return 0;const dateParts=parts[0].split('.');const timeParts=parts[1].split(':');if(dateParts.length<3||timeParts.length<2)return 0;const day=parseInt(dateParts[0]);const month=parseInt(dateParts[1])-1;const year=parseInt(dateParts[2]);const hour=parseInt(timeParts[0]);const minute=parseInt(timeParts[1]);return new Date(year,month,day,hour,minute).getTime();}catch(e){return 0;}}
function formatMatchTime3(dateStr){if(!dateStr)return'-';const monthMap={'Jan':0,'Feb':1,'Mar':2,'Apr':3,'May':4,'Jun':5,'Jul':6,'Aug':7,'Sep':8,'Oct':9,'Nov':10,'Dec':11};const match1=dateStr.match(/^(\d{2})\.([A-Za-z]{3})\s+(\d{2}):(\d{2}):?(\d{2})?$/);if(match1){const[,day,monthStr,hour,min]=match1;const monthIdx=monthMap[monthStr]??0;const utcDate=dayjs.utc(`2025-${String(monthIdx + 1).padStart(2, '0')}-${day}T${hour}:${min}:00`);const trDate=utcDate.tz('Europe/Istanbul');const monthName=_tms(trDate.month());return`${trDate.format('DD')} ${monthName} • ${trDate.format('HH:mm')}`;}
const match2=dateStr.match(/^(\d{2})\.(\d{2})\.(\d{4})\s+(\d{2}):(\d{2})$/);if(match2){const[,day,month,year,hour,min]=match2;const utcDate=dayjs.utc(`${year}-${month}-${day}T${hour}:${min}:00`);const trDate=utcDate.tz('Europe/Istanbul');const monthName=_tms(trDate.month());return`${trDate.format('DD')} ${monthName} • ${trDate.format('HH:mm')}`;}
const matchISO=dateStr.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);if(matchISO){let dt;if(dateStr.includes('+')||dateStr.includes('Z')){dt=dayjs(dateStr).tz('Europe/Istanbul');}else{dt=dayjs.utc(dateStr).tz('Europe/Istanbul');}
const monthName=_tms(dt.month());return`${dt.format('DD')} ${monthName} • ${dt.format('HH:mm')}`;}
const matchISOSpace=dateStr.match(/^(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2})/);if(matchISOSpace){const[,year,month,day,hour,min]=matchISOSpace;const utcDate=dayjs.utc(`${year}-${month}-${day}T${hour}:${min}:00`);const trDate=utcDate.tz('Europe/Istanbul');const monthName=_tms(trDate.month());return`${trDate.format('DD')} ${monthName} • ${trDate.format('HH:mm')}`;}
const matchDateOnly=dateStr.match(/^(\d{4})-(\d{2})-(\d{2})$/);if(matchDateOnly){const[,year,month,day]=matchDateOnly;const dt=dayjs(`${year}-${month}-${day}`);const monthName=_tms(dt.month());return`${dt.format('DD')} ${monthName}`;}
return dateStr;}
function formatMatchDateShort(dateStr){if(!dateStr)return'';const monthMap={'Jan':0,'Feb':1,'Mar':2,'Apr':3,'May':4,'Jun':5,'Jul':6,'Aug':7,'Sep':8,'Oct':9,'Nov':10,'Dec':11};const match1=dateStr.match(/^(\d{2})\.([A-Za-z]{3})\s+(\d{2}):(\d{2}):?(\d{2})?$/);if(match1){const[,day,monthStr,hour,min]=match1;const monthIdx=monthMap[monthStr]??0;const utcDate=dayjs.utc(`2025-${String(monthIdx + 1).padStart(2, '0')}-${day}T${hour}:${min}:00`);const trDate=utcDate.tz('Europe/Istanbul');const monthName=_tms(trDate.month());return`${trDate.format('DD')} ${monthName} ${trDate.format('HH:mm')}`;}
const dt=toTurkeyTime(dateStr);if(dt&&dt.isValid()){const monthName=_tms(dt.month());return`${dt.format('DD')} ${monthName} ${dt.format('HH:mm')}`;}
return'';}
let _todayStrCache=null;let _todayCacheTime=0;function isMatchTodayOrFuture(alarm){const now=Date.now();if(!_todayStrCache||(now-_todayCacheTime)>60000){_todayStrCache=dayjs().tz('Europe/Istanbul').format('YYYY-MM-DD');_todayCacheTime=now;}
const matchDateStr=alarm.match_date||alarm.fixture_date||'';if(matchDateStr&&matchDateStr.length>=10){const dateStr=matchDateStr.substring(0,10);return dateStr>=_todayStrCache;}
const triggerAt=alarm.trigger_at||alarm.event_time||'';if(triggerAt&&triggerAt.length>=10){const dateStr=triggerAt.substring(0,10);return dateStr>=_todayStrCache;}
return false;}
function isMatchYesterdayOrLater(alarm){const matchDateStr=alarm.match_date||alarm.fixture_date||'';const nowTR=dayjs().tz('Europe/Istanbul');const yesterdayStr=nowTR.subtract(1,'day').format('YYYY-MM-DD');if(!matchDateStr){const triggerAt=alarm.trigger_at||alarm.event_time||alarm.created_at||'';if(triggerAt){const triggerTR=toTurkeyTime(triggerAt);if(triggerTR&&triggerTR.isValid()){const triggerDateStr=triggerTR.format('YYYY-MM-DD');return triggerDateStr>=yesterdayStr;}}
return false;}
const isoMatch=matchDateStr.match(/^(\d{4})-(\d{2})-(\d{2})/);if(isoMatch){const matchStr=isoMatch[0];return matchStr>=yesterdayStr;}
const ddMmmMatch=matchDateStr.match(/^(\d{1,2})\.([A-Za-z]{3})/);if(ddMmmMatch){const dayNum=parseInt(ddMmmMatch[1]);const monthStr=ddMmmMatch[2];const monthMap={'Jan':0,'Feb':1,'Mar':2,'Apr':3,'May':4,'Jun':5,'Jul':6,'Aug':7,'Sep':8,'Oct':9,'Nov':10,'Dec':11};const monthNum=monthMap[monthStr];if(monthNum!==undefined&&!isNaN(dayNum)){let year=nowTR.year();let matchDate=dayjs().tz('Europe/Istanbul').year(year).month(monthNum).date(dayNum);if(nowTR.diff(matchDate,'month')>6){year++;matchDate=dayjs().tz('Europe/Istanbul').year(year).month(monthNum).date(dayNum);}
const matchDateFormatted=matchDate.format('YYYY-MM-DD');return matchDateFormatted>=yesterdayStr;}}
return false;}
async function loadAlertBand(){try{const data=await fetchAlarmsBatch();let allAlarms=[];const sharp=(data.sharp||[]).slice();sharp.forEach(a=>{a._type='sharp';a._score=a.sharp_score||0;});allAlarms=allAlarms.concat(sharp);const bigmoney=(data.bigmoney||[]).slice();bigmoney.forEach(a=>{a._type='bigmoney';a._score=a.incoming_money||a.stake||a.volume||0;});allAlarms=allAlarms.concat(bigmoney);const volumeshock=(data.volumeshock||[]).slice();volumeshock.forEach(a=>{a._type='volumeshock';a._score=(a.volume_shock_value||a.volume_shock||a.volume_shock_multiplier||0)*100;});allAlarms=allAlarms.concat(volumeshock);const dropping=(data.dropping||[]).slice();dropping.forEach(a=>{a._type='dropping';a._score=a.drop_pct||0;});allAlarms=allAlarms.concat(dropping);const publicmove=(data.publicmove||[]).slice();publicmove.forEach(a=>{a._type='publicmove';a._score=a.trap_score||a.sharp_score||0;});allAlarms=allAlarms.concat(publicmove);const volumeleader=(data.volumeleader||[]).slice();volumeleader.forEach(a=>{a._type='volumeleader';a._score=a.new_leader_share||50;});allAlarms=allAlarms.concat(volumeleader);const mim=(data.mim||[]).slice();mim.forEach(a=>{a._type='mim';a._score=(a.impact||a.impact_score||a.money_impact||0)*100;});allAlarms=allAlarms.concat(mim);void 0;const filteredAlarms=allAlarms.filter(isMatchTodayOrFuture);void 0;const groupedForBand=groupAlarmsForBand(filteredAlarms);void 0;alertBandData=groupedForBand.sort((a,b)=>{const timeA=new Date(a.trigger_at||a.event_time||a.created_at||0).getTime();const timeB=new Date(b.trigger_at||b.event_time||b.created_at||0).getTime();return timeB-timeA;});void 0;if(lastAlertBandHash===''){void 0;renderAlertBand();updateAlertBandBadge();lastAlertBandHash=JSON.stringify(alertBandData.slice(0,10).map(a=>a.home+a._type+(a.trigger_at||a.event_time||'')));lastTopAlarmKey=getAlarmKey(alertBandData[0]);}else{scheduleAlertBandRender();}}catch(e){console.error('[AlertBand] Load error:',e);}}
function groupAlarmsForBand(alarms){const groups={};alarms.forEach((alarm,alarmIndex)=>{const home=(alarm.home||alarm.home_team||'').toLowerCase().trim();const away=(alarm.away||alarm.away_team||'').toLowerCase().trim();const league=(alarm.league||'').toLowerCase().trim();const market=(alarm.market||'').toLowerCase().trim();const selection=(alarm.selection||alarm.side||'').toLowerCase().trim();const type=alarm._type;const groupKey=`${type}|${home}|${away}|${league}|${market}|${selection}`;if(!groups[groupKey]){groups[groupKey]=alarm;}else{const currentBest=parseAlarmDate(groups[groupKey].trigger_at||groups[groupKey].event_time||groups[groupKey].created_at);const thisDate=parseAlarmDate(alarm.trigger_at||alarm.event_time||alarm.created_at);if(thisDate>currentBest){groups[groupKey]=alarm;}}});return Object.values(groups);}
function getAlertType(alarm){const type=alarm._type;if(type==='sharp')return{label:'SHARP MOVE',color:'green',pillClass:'sharp'};if(type==='bigmoney'){const stake=alarm.stake||alarm.volume||0;if(stake>=50000){return{label:'HUGE MONEY',color:'orange-red',pillClass:'hugemoney'};}
return{label:'BIG MONEY',color:'orange',pillClass:'bigmoney'};}
if(type==='volumeshock')return{label:_t('app.j.alarm_volume_shock','HACIM SOKU'),color:'gold',pillClass:'volumeshock'};if(type==='dropping'){const level=alarm.level||'L1';if(level==='L3')return{label:_t('app.j.alarm_drop_l3','DÜŞÜŞ L3'),color:'red',pillClass:'dropping-l3'};if(level==='L2')return{label:_t('app.j.alarm_drop_l2','DÜŞÜŞ L2'),color:'red',pillClass:'dropping-l2'};return{label:_t('app.j.alarm_drop_l1','DÜŞÜŞ L1'),color:'red',pillClass:'dropping-l1'};}
if(type==='publicmove')return{label:'PUBLIC MOVE',color:'gold',pillClass:'publicmove'};if(type==='volumeleader')return{label:_t('app.j.alarm_leader_changed','LIDER DEGISTI'),color:'cyan',pillClass:'volumeleader'};if(type==='mim'){const impact=alarm.impact||alarm.impact_score||alarm.money_impact||0;const impactPct=(impact*100).toFixed(0);return{label:`MIM ${impactPct}%`,color:'cyan',pillClass:'mim'};}
return{label:'ALERT',color:'green',pillClass:''};}
function formatAlertValue(alarm){const type=alarm._type;if(type==='sharp'){return'+'+(alarm.sharp_score||0).toFixed(0);}
if(type==='bigmoney'){const val=alarm.incoming_money||alarm.stake||alarm.volume||0;return'£'+Number(val).toLocaleString('en-GB');}
if(type==='volumeshock'){const shockValue=alarm.volume_shock_value||alarm.volume_shock||alarm.volume_shock_multiplier||0;return shockValue.toFixed(1)+'x';}
if(type==='dropping'){const dropPct=alarm.drop_pct||0;return'▼ '+dropPct.toFixed(1)+'%';}
if(type==='publicmove'){const score=alarm.move_score||alarm.trap_score||alarm.sharp_score||0;return score.toFixed(0);}
if(type==='volumeleader'){const share=alarm.new_leader_share||0;return'%'+share.toFixed(0);}
if(type==='mim'){const impact=alarm.impact||alarm.impact_score||alarm.money_impact||0;const level=alarm.mim_level||1;return`L${level} ${impact.toFixed(2)}`;}
return'';}
function renderAlertBand(){const track=document.getElementById('alertBandTrack');if(!track)return;if(!alertBandData||alertBandData.length===0){track.innerHTML='<span class="alert-band-empty">Alarm bekleniyor...</span>';return;}
const top=alertBandData.slice(0,10);const pillsHtml=top.map((alarm,idx)=>{const info=getAlertType(alarm);const home=alarm.home||alarm.home_team||'?';const away=alarm.away||alarm.away_team||'?';const rawSel=(alarm.selection||alarm.side||'').toUpperCase();const selMap={'U':_t('app.dyn.alt','Alt'),'O':_t('app.dyn.ust','Üst'),'Y':_t('app.dyn.evet','Evet'),'N':_t('app.dyn.hayir','Hayır'),'1':'1','X':'X','2':'2','UNDER':_t('app.dyn.alt','Alt'),'OVER':_t('app.dyn.ust','Üst'),'YES':_t('app.dyn.evet','Evet'),'NO':_t('app.dyn.hayir','Hayır')};const selection=selMap[rawSel]||rawSel;let value='';if(alarm._type==='sharp'){value=(alarm.sharp_score||0).toFixed(1);}else if(alarm._type==='volumeshock'){value=`${(alarm.volume_shock_value || alarm.volume_shock || alarm.volume_shock_multiplier || 0).toFixed(1)}x`;}else if(alarm._type==='bigmoney'){value=`£${Math.round(Number(alarm.incoming_money || alarm.stake || 0)).toLocaleString('en-GB')}`;}else if(alarm._type==='dropping'){value=`▼ ${(alarm.drop_pct || 0).toFixed(1)}%`;}else if(alarm._type==='publicmove'){value=`${(alarm.move_score || alarm.trap_score || alarm.sharp_score || 0).toFixed(0)}`;}else if(alarm._type==='volumeleader'){value=`%${(alarm.new_leader_share || 0).toFixed(0)}`;}else if(alarm._type==='mim'){const impact=alarm.impact||alarm.impact_score||alarm.money_impact||0;const prevVol=alarm.prev_volume||alarm.previous_volume||0;const currVol=alarm.current_volume||alarm.curr_volume||alarm.total_volume||alarm.volume||0;const incomingMoney=currVol-prevVol;value=incomingMoney>0?`+£${Math.round(Number(incomingMoney)).toLocaleString('en-GB')}`:`${(impact * 100).toFixed(0)}%`;}
const matchKey=`${home}_vs_${away}`.replace(/\s+/g,'_');const alarmType=alarm._type||'';const alarmMarket=(alarm.market||'').replace(/'/g,"\\'");const alarmLeague=(alarm.league||'').replace(/'/g,"\\'");const alarmKickoff=(alarm.kickoff_utc||alarm.match_date||alarm.fixture_date||'').replace(/'/g,"\\'");const alarmHash=(alarm.match_id_hash||alarm.match_id||'').replace(/'/g,"\\'");const isMobile=window.innerWidth<=768;const matchDisplay=isMobile?home:`${home} - ${away}`;var _alarmFree=_isTestFreeAlarm(home,away);var _blurClass=(window.userPlan==='test'&&!_alarmFree)?' test-blur-alarm':'';if(alarm._type==='volumeleader'){const oldLeader=alarm.old_leader||alarm.previous_leader||'?';const newLeader=alarm.new_leader||alarm.selection||'?';return`
                <div class="ab-pill ${info.pillClass}" onclick="goToMatchFromAlarm('${home.replace(/'/g, "\\'")}', '${away.replace(/'/g, "\\'")}', '${alarmType}', '${alarmMarket}', '${alarmLeague}', '${alarmKickoff}', '${alarmHash}')" style="cursor: pointer;">
                    <span class="ab-dot dot-${info.pillClass}"></span>
                    <span class="ab-type">${info.label}</span>
                    <span class="ab-sep">—</span>
                    <span class="ab-match">${matchDisplay}</span>
                    <span class="ab-sep">—</span>
                    <span class="ab-leader-change${_blurClass}">${oldLeader} <span class="ab-arrow">▸</span> ${newLeader}</span>
                </div>
            `;}
return`
            <div class="ab-pill ${info.pillClass}" onclick="goToMatchFromAlarm('${home.replace(/'/g, "\\'")}', '${away.replace(/'/g, "\\'")}', '${alarmType}', '${alarmMarket}', '${alarmLeague}', '${alarmKickoff}', '${alarmHash}')" style="cursor: pointer;">
                <span class="ab-dot dot-${info.pillClass}"></span>
                <span class="ab-type">${info.label}</span>
                <span class="ab-sep">—</span>
                <span class="ab-match">${matchDisplay}</span>
                <span class="ab-sep">—</span>
                <span class="ab-sel${_blurClass}">${selection}</span>
                <span class="ab-val${_blurClass}">${value}</span>
            </div>
        `;}).join('');track.innerHTML=`
        <div class="alert-band-track-inner">
            ${pillsHtml}${pillsHtml}
        </div>
    `;}
function updateAlertBandBadge(){const badge=document.getElementById('alarmsBadge');const mobileBadge=document.getElementById('mobileAlarmBadge');const count=alertBandData.length;if(badge){badge.textContent=count;badge.setAttribute('data-count',count);}
if(mobileBadge){mobileBadge.textContent=count;}}
function showAlertBandDetail(index){const alarm=alertBandData[index];if(!alarm)return;const info=getAlertType(alarm);const home=alarm.home||alarm.home_team||'-';const away=alarm.away||alarm.away_team||'-';const value=formatAlertValue(alarm);const modal=document.createElement('div');modal.className='modal-overlay';modal.id='alertBandModal';modal.onclick=(e)=>{if(e.target===modal)modal.remove();};let detailsHtml='';if(alarm._type==='sharp'){detailsHtml=`
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                <div style="background: #262a2f; border-radius: 8px; padding: 12px; text-align: center;">
                    <div style="color: #4ade80; font-size: 20px; font-weight: 700;">${alarm.volume ? '£' + Number(alarm.volume).toLocaleString('en-GB') : '-'}</div>
                    <div style="color: #7d848c; font-size: 11px;">Volume</div>
                </div>
                <div style="background: #262a2f; border-radius: 8px; padding: 12px; text-align: center;">
                    <div style="color: #f0883e; font-size: 20px; font-weight: 700;">${alarm.stake_share ? alarm.stake_share.toFixed(1) + '%' : '-'}</div>
                    <div style="color: #7d848c; font-size: 11px;">Stake Share</div>
                </div>
                <div style="background: #262a2f; border-radius: 8px; padding: 12px; text-align: center;">
                    <div style="color: #58a6ff; font-size: 20px; font-weight: 700;">${alarm.odds_move ? (alarm.odds_move > 0 ? '+' : '') + alarm.odds_move.toFixed(2) : '-'}</div>
                    <div style="color: #7d848c; font-size: 11px;">Odds Move</div>
                </div>
                <div style="background: #262a2f; border-radius: 8px; padding: 12px; text-align: center;">
                    <div style="color: #a371f7; font-size: 20px; font-weight: 700;">${alarm.volume_shock ? alarm.volume_shock.toFixed(1) + 'x' : '-'}</div>
                    <div style="color: #7d848c; font-size: 11px;">Volume Shock</div>
                </div>
            </div>
        `;}else{detailsHtml=`
            <div style="background: #262a2f; border-radius: 8px; padding: 16px; text-align: center;">
                <div style="color: #fbbf24; font-size: 28px; font-weight: 700;">${alarm.stake ? '£' + Math.round(Number(alarm.stake)).toLocaleString('en-GB') : (alarm.volume ? '£' + Math.round(Number(alarm.volume)).toLocaleString('en-GB') : '-')}</div>
                <div style="color: #7d848c; font-size: 12px; margin-top: 4px;">Stake Amount</div>
            </div>
        `;}
const typeColors={sharp:'#ef4444',bigmoney:'#fbbf24',volumeshock:'#F6C343',dropping:'#f85149',publicmove:'#FFCC00',volumeleader:'#06b6d4',mim:'#3B82F6'};modal.innerHTML=`
        <div class="modal-content" style="max-width: 480px;">
            <div class="modal-header">
                <h2 style="display: flex; align-items: center; gap: 10px;">
                    <span style="background: ${typeColors[alarm._type] || '#7d848c'}; width: 12px; height: 12px; border-radius: 50%;"></span>
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
                    <div style="font-size: 42px; font-weight: 700; color: ${typeColors[alarm._type] || '#7d848c'};">${value}</div>
                    <div style="color: #7d848c; font-size: 13px;">${alarm._type === 'sharp' ? 'Sharp Score' : 'Stake'}</div>
                </div>
                <div style="background: #141719; border-radius: 8px; padding: 16px; margin-bottom: 16px;">
                    <div style="font-size: 18px; font-weight: 600; color: #fff; text-align: center; margin-bottom: 8px;">
                        ${home} vs ${away}
                    </div>
                    <div style="text-align: center; color: #7d848c; font-size: 13px;">
                        ${(alarm.market || '-').replace(/O\/U/gi, 'A/Ü')} | <span style="color: #58a6ff;">${{'U': _t('app.dyn.alt','Alt'), 'O': _t('app.dyn.ust','Üst'), 'Y': _t('app.dyn.evet','Evet'), 'N': _t('app.dyn.hayir','Hayır'), 'UNDER': _t('app.dyn.alt','Alt'), 'OVER': _t('app.dyn.ust','Üst'), 'YES': _t('app.dyn.evet','Evet'), 'NO': _t('app.dyn.hayir','Hayır')}[(alarm.selection || alarm.side || '-').toUpperCase()] || (alarm.selection || alarm.side || '-')}</span>
                    </div>
                </div>
                ${detailsHtml}
            </div>
        </div>
    `;document.body.appendChild(modal);}
setInterval(()=>{if(_isLicensed)loadAlertBand();},120000);document.addEventListener('DOMContentLoaded',async()=>{await _licenseReady;if(!_isLicensed)return;setTimeout(loadAlertBand,500);});let currentAlarmFilter='all';let allAlarmsData=[];let groupedAlarmsData=[];let alarmsDataByType={sharp:[],bigmoney:[],volumeshock:[],dropping:[],publicmove:[],volumeleader:[],mim:[]};let alarmSearchQuery='';let alarmsDisplayCount=10;let alarmsSidebarOpen=false;let openAlarmId=null;var _mobMarkets={moneyway:[{v:'1x2',l:'1X2'},{v:'ou25',l:'2.5'},{v:'btts',l:'KG'}],dropping:[{v:'1x2',l:'1X2'},{v:'ou25',l:'2.5'},{v:'btts',l:'KG'}],live:[{v:'1x2',l:'1X2'},{v:'ou1.5',l:'1.5'},{v:'ou2.5',l:'2.5'},{v:'ou3.5',l:'3.5'},{v:'ou4.5',l:'4.5'}]};var _mobCurCat='moneyway';var _mobCurMkt='1x2';function selectMobCat(cat){_mobCurCat=cat;document.querySelectorAll('#mobCatRow .mob-tab').forEach(function(b){b.classList.toggle('active',b.getAttribute('data-cat')===cat);});_updateMobMktRow(cat);if(cat==='live'){switchToLive();}else{setMobileGroup(cat);}}
function _updateMobMktRow(cat){var row=document.getElementById('mobMktRow');if(!row)return;var opts=_mobMarkets[cat]||_mobMarkets.moneyway;var html='';opts.forEach(function(o,i){html+='<button class="mob-tab'+(i===0?' active':'')+'" data-mkt="'+o.v+'" onclick="selectMobMkt(\''+o.v+'\')">'+o.l+'</button>';});row.innerHTML=html;_mobCurMkt=opts[0].v;_addMobileMktLockIcons();if(cat==='live'){setLiveMarket(opts[0].v);}else{setMobileMarket(opts[0].v);}}
function selectMobMkt(mkt){if(window.userPlan==='test'&&mkt!=='1x2'){_showTestLockedToast(document.querySelector('#mobMktRow .mob-tab[data-mkt="'+mkt+'"]'));return;}
_mobCurMkt=mkt;document.querySelectorAll('#mobMktRow .mob-tab').forEach(function(b){b.classList.toggle('active',b.getAttribute('data-mkt')===mkt);});if(_mobCurCat==='live'){setLiveMarket(mkt);}else{setMobileMarket(mkt);}}
function toggleMobileOverflow(e){if(e)e.stopPropagation();var menu=document.getElementById('mobileOverflowMenu');if(!menu)return;menu.classList.toggle('show');if(menu.classList.contains('show')){setTimeout(function(){document.addEventListener('click',closeMobileOverflow,{once:true});},10);}}
function closeMobileOverflow(){var menu=document.getElementById('mobileOverflowMenu');if(menu)menu.classList.remove('show');}
function toggleAlarmsSidebar(){if(window.userPlan==='test'){_showTestLockedToast(document.getElementById('alarmsBtn'));return;}
if(alarmsSidebarOpen){closeAlarmsSidebar();}else{openAlarmsSidebar();}}
function openAlarmsSidebar(){if(window.userPlan==='test'){_showTestLockedToast(document.getElementById('alarmsBtn'));return;}
alarmsSidebarOpen=true;document.getElementById('alarmsSidebar').classList.add('open');document.getElementById('alarmsSidebarOverlay').classList.add('open');document.body.style.overflow='hidden';const btn=document.getElementById('alarmsBtn');if(btn)btn.classList.add('active');if(_alarmBatchCache&&(Date.now()-_alarmCacheTime)<ALARM_CACHE_TTL){loadAllAlarms(false);}else{loadAllAlarms(true);}}
function closeAlarmsSidebar(){alarmsSidebarOpen=false;document.getElementById('alarmsSidebar').classList.remove('open');document.getElementById('alarmsSidebarOverlay').classList.remove('open');document.body.style.overflow='';const btn=document.getElementById('alarmsBtn');if(btn)btn.classList.remove('active');}
async function loadAllAlarms(forceRefresh=false){const body=document.getElementById('alarmsList');body.innerHTML='<div class="alarms-loading">Alarmlar yukleniyor...</div>';try{const data=await fetchAlarmsBatch(forceRefresh);const rawSharp=data.sharp||[];const rawBigmoney=data.bigmoney||[];const rawVolumeshock=data.volumeshock||[];const rawDropping=data.dropping||[];const rawPublicmove=data.publicmove||[];const rawVolumeleader=data.volumeleader||[];const rawMim=data.mim||[];alarmsDataByType.sharp=rawSharp.filter(isMatchYesterdayOrLater);alarmsDataByType.bigmoney=rawBigmoney.filter(isMatchYesterdayOrLater);alarmsDataByType.volumeshock=rawVolumeshock.filter(isMatchYesterdayOrLater);alarmsDataByType.dropping=rawDropping.filter(isMatchYesterdayOrLater);alarmsDataByType.publicmove=rawPublicmove.filter(isMatchYesterdayOrLater);alarmsDataByType.volumeleader=rawVolumeleader.filter(isMatchYesterdayOrLater);alarmsDataByType.mim=rawMim.filter(isMatchYesterdayOrLater);const sharpWithType=alarmsDataByType.sharp.map(a=>({...a,_type:'sharp'}));const bigmoneyWithType=alarmsDataByType.bigmoney.map(a=>({...a,_type:'bigmoney'}));const volumeshockWithType=alarmsDataByType.volumeshock.map(a=>({...a,_type:'volumeshock'}));const droppingWithType=alarmsDataByType.dropping.map(a=>({...a,_type:'dropping'}));const publicmoveWithType=alarmsDataByType.publicmove.map(a=>({...a,_type:'publicmove'}));const volumeleaderWithType=alarmsDataByType.volumeleader.map(a=>({...a,_type:'volumeleader'}));const mimWithType=alarmsDataByType.mim.map(a=>({...a,_type:'mim'}));allAlarmsData=[...sharpWithType,...bigmoneyWithType,...volumeshockWithType,...droppingWithType,...publicmoveWithType,...volumeleaderWithType,...mimWithType];allAlarmsData.sort((a,b)=>{const dateA=parseAlarmDate(a.trigger_at||a.event_time||a.created_at);const dateB=parseAlarmDate(b.trigger_at||b.event_time||b.created_at);return dateB-dateA;});groupedAlarmsData=groupAlarmsByMatch(allAlarmsData);updateAlarmCounts();updateDateFilterCounts();alarmsDisplayCount=10;const labelEl=document.getElementById('dateLabelDisplay');if(labelEl){labelEl.textContent=dateFilterLabels[currentAlarmDateFilter]||_t('app.flt.all','Tümü');}
renderAlarmsList(currentAlarmFilter);}catch(error){console.error('Alarm yukleme hatasi:',error);body.innerHTML='<div class="alarms-empty"><p>Alarmlar yuklenirken hata olustu.</p></div>';}}
function groupAlarmsByMatch(alarms){const groups={};alarms.forEach(alarm=>{const home=(alarm.home||alarm.home_team||'').toLowerCase().trim();const away=(alarm.away||alarm.away_team||'').toLowerCase().trim();const league=(alarm.league||'').toLowerCase().trim();const market=(alarm.market||'').toLowerCase().trim();const selection=(alarm.selection||alarm.side||'').toLowerCase().trim();const type=alarm._type;const matchHash=(alarm.match_id_hash||alarm.match_id||alarm.matchIdHash||'').toString().trim();const alarmKickoff=alarm.kickoff_utc||alarm.kickoff||alarm.match_date||alarm.fixture_date||'';const kickoffMs=_matchContextTime(alarmKickoff);const matchContext=matchHash||(kickoffMs!==null?`kickoff:${kickoffMs}`:`legacy:${_matchContextLabel(alarmKickoff) || alarm.id || alarm.alarm_id || alarm.trigger_at || alarm.created_at || alarm.triggered_at || alarmIndex}`);const groupKey=`${type}|${matchContext}|${home}|${away}|${league}|${market}|${selection}`;if(!groups[groupKey]){groups[groupKey]={key:groupKey,type:type,home:alarm.home||alarm.home_team||'-',away:alarm.away||alarm.away_team||'-',home_team:alarm.home_team||alarm.home||'-',away_team:alarm.away_team||alarm.away||'-',match_id:matchHash,match_id_hash:matchHash,market:alarm.market||'',selection:alarm.selection||alarm.side||'',league:alarm.league||'',match_date:alarm.match_date||alarm.fixture_date||'',fixture_date:alarm.fixture_date||alarm.match_date||'',kickoff_utc:alarm.kickoff_utc||alarm.kickoff||'',latestAlarm:alarm,allAlarms:[],history:[],triggerCount:0};}
groups[groupKey].allAlarms.push(alarm);groups[groupKey].triggerCount++;const currentLatestTime=groups[groupKey].latestAlarm.trigger_at||groups[groupKey].latestAlarm.created_at||groups[groupKey].latestAlarm.triggered_at||'';const thisTime=alarm.trigger_at||alarm.created_at||alarm.triggered_at||'';if(thisTime.localeCompare(currentLatestTime)>0){groups[groupKey].latestAlarm=alarm;const latestHash=(alarm.match_id_hash||alarm.match_id||alarm.matchIdHash||'').toString().trim();groups[groupKey].match_id=latestHash||groups[groupKey].match_id;groups[groupKey].match_id_hash=latestHash||groups[groupKey].match_id_hash;groups[groupKey].match_date=alarm.match_date||alarm.fixture_date||groups[groupKey].match_date;groups[groupKey].fixture_date=alarm.fixture_date||alarm.match_date||groups[groupKey].fixture_date;groups[groupKey].kickoff_utc=alarm.kickoff_utc||alarm.kickoff||groups[groupKey].kickoff_utc;}});Object.values(groups).forEach(group=>{group.allAlarms.sort((a,b)=>{const aTime=a.trigger_at||a.created_at||a.triggered_at||'';const bTime=b.trigger_at||b.created_at||b.triggered_at||'';return bTime.localeCompare(aTime);});group.history=group.allAlarms.slice(1);});return Object.values(groups).sort((a,b)=>{const aTime=a.latestAlarm.trigger_at||a.latestAlarm.created_at||a.latestAlarm.triggered_at||'';const bTime=b.latestAlarm.trigger_at||b.latestAlarm.created_at||b.latestAlarm.triggered_at||'';return bTime.localeCompare(aTime);});}
function updateAlarmCounts(){const badge=document.getElementById('alarmsBadge');const mobileBadge=document.getElementById('mobileAlarmBadge');const filteredGroups=groupedAlarmsData.filter(g=>{if(currentAlarmDateFilter==='all'){const matchDateStr=g.match_date||g.fixture_date||getMatchDateFromAlarm(g.latestAlarm);if(!matchDateStr)return true;const{todayStr}=getDateFilterStrings();return matchDateStr>=todayStr;}
return true;});const totalCount=filteredGroups.length;if(badge)badge.textContent=totalCount;if(mobileBadge)mobileBadge.textContent=totalCount;const typeCounts={sharp:0,bigmoney:0,volumeshock:0,dropping:0,publicmove:0,volumeleader:0,mim:0};filteredGroups.forEach(g=>{if(typeCounts.hasOwnProperty(g.type))typeCounts[g.type]++;});const countAll=document.getElementById('countAll');const countSharp=document.getElementById('countSharp');const countBigmoney=document.getElementById('countBigmoney');const countVolumeshock=document.getElementById('countVolumeshock');const countDropping=document.getElementById('countDropping');const countPublicmove=document.getElementById('countPublicmove');const countVolumeleader=document.getElementById('countVolumeleader');const countMim=document.getElementById('countMim');if(countAll)countAll.textContent=totalCount;if(countSharp)countSharp.textContent=typeCounts.sharp;if(countBigmoney)countBigmoney.textContent=typeCounts.bigmoney;if(countVolumeshock)countVolumeshock.textContent=typeCounts.volumeshock;if(countDropping)countDropping.textContent=typeCounts.dropping;if(countPublicmove)countPublicmove.textContent=typeCounts.publicmove;if(countVolumeleader)countVolumeleader.textContent=typeCounts.volumeleader;if(countMim)countMim.textContent=typeCounts.mim;}
let currentAlarmDateFilter='all';const dateFilterLabels={get all(){return _t('app.flt.all','Tümü');},get today(){return _t('app.flt.today','Bugün');},get yesterday(){return _t('app.flt.yesterday','Dün');},get future(){return _t('app.flt.future','Gelecek');}};const dateFilterColors={all:'#ffffff',today:'#4ade80',yesterday:'#f85149',future:'#3B82F6'};function toggleDateFilterDropdown(){const dropdown=document.getElementById('alarmDateDropdown');const options=document.getElementById('alarmDateOptions');if(dropdown&&options){dropdown.classList.toggle('open');options.style.display=options.style.display==='block'?'none':'block';}}
function selectDateFilter(dateFilter){void 0;currentAlarmDateFilter=dateFilter;const labelEl=document.getElementById('dateLabelDisplay');if(labelEl){labelEl.textContent=dateFilterLabels[dateFilter]||_t('app.flt.all','Tümü');}
const dotEl=document.getElementById('dateDotDisplay');if(dotEl){dotEl.style.background=dateFilterColors[dateFilter]||'#ffffff';}
const dropdown=document.getElementById('alarmDateDropdown');const options=document.getElementById('alarmDateOptions');if(dropdown)dropdown.classList.remove('open');if(options)options.style.display='none';alarmsDisplayCount=10;renderAlarmsList(currentAlarmFilter);}
function getMatchDateFromAlarm(alarm){const matchDate=alarm.match_date||alarm.fixture_date||alarm.kickoff_utc||'';if(!matchDate)return null;try{if(/^\d{4}-\d{2}-\d{2}$/.test(matchDate)){return matchDate;}
const dt=dayjs(matchDate).tz('Europe/Istanbul');return dt.format('YYYY-MM-DD');}catch(e){return null;}}
function filterAlarmsByMatchDate(alarms){if(currentAlarmDateFilter==='all'){const today=dayjs().tz('Europe/Istanbul').format('YYYY-MM-DD');return alarms.filter(alarm=>{const matchDateStr=getMatchDateFromAlarm(alarm);if(!matchDateStr)return true;return matchDateStr>=today;});}
const today=dayjs().tz('Europe/Istanbul');const todayStr=today.format('YYYY-MM-DD');const yesterdayStr=today.subtract(1,'day').format('YYYY-MM-DD');const tomorrowStr=today.add(1,'day').format('YYYY-MM-DD');return alarms.filter(alarm=>{const matchDateStr=getMatchDateFromAlarm(alarm);if(!matchDateStr)return currentAlarmDateFilter==='all';if(currentAlarmDateFilter==='today'){return matchDateStr===todayStr;}else if(currentAlarmDateFilter==='yesterday'){return matchDateStr===yesterdayStr;}else if(currentAlarmDateFilter==='future'){return matchDateStr>=tomorrowStr;}
return true;});}
function updateDateFilterCounts(){const alarms=allAlarmsData||[];const today=dayjs().tz('Europe/Istanbul');const todayStr=today.format('YYYY-MM-DD');const yesterdayStr=today.subtract(1,'day').format('YYYY-MM-DD');const tomorrowStr=today.add(1,'day').format('YYYY-MM-DD');let countAll=0;let countToday=0;let countYesterday=0;let countFuture=0;alarms.forEach(alarm=>{const matchDateStr=getMatchDateFromAlarm(alarm);if(!matchDateStr)return;if(matchDateStr===todayStr){countToday++;countAll++;}else if(matchDateStr===yesterdayStr){countYesterday++;}else if(matchDateStr>=tomorrowStr){countFuture++;countAll++;}});const elAll=document.getElementById('dateCountAll');const elToday=document.getElementById('dateCountToday');const elYesterday=document.getElementById('dateCountYesterday');const elFuture=document.getElementById('dateCountFuture');if(elAll)elAll.textContent=countAll;if(elToday)elToday.textContent=countToday;if(elYesterday)elYesterday.textContent=countYesterday;if(elFuture)elFuture.textContent=countFuture;}
function parseAlarmDate(dateStr){if(!dateStr)return new Date(0);const str=String(dateStr).trim();const ddmmMatch=str.match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})\s*(\d{2}:\d{2})?$/);if(ddmmMatch){const[,day,month,year,time]=ddmmMatch;const[hour,min]=(time||'00:00').split(':');return new Date(parseInt(year),parseInt(month)-1,parseInt(day),parseInt(hour),parseInt(min));}
const turkeyTime=toTurkeyTime(str);if(turkeyTime&&turkeyTime.isValid()){return turkeyTime.toDate();}
return new Date(str)||new Date(0);}
const alarmFilterColors={all:null,sharp:'#4ade80',bigmoney:'#F08A24',volumeshock:'#F6C343',dropping:'#f85149',publicmove:'#FFCC00',volumeleader:'#06b6d4',mim:'#3B82F6'};const alarmFilterLabels={get all(){return _t('app.flt.all','Tümü');},sharp:'Sharp',bigmoney:'Buyuk Para',volumeshock:'Hacim Soku',dropping:'Oran Düşüşü',publicmove:'Public Move',volumeleader:'Lider Degisti',mim:'MIM'};function toggleAlarmFilterDropdown(){const dropdown=document.getElementById('alarmFilterDropdown');dropdown.classList.toggle('open');}
function selectAlarmFilter(type){const dropdown=document.getElementById('alarmFilterDropdown');const dotDisplay=document.getElementById('filterDotDisplay');const labelDisplay=document.getElementById('filterLabelDisplay');dropdown.classList.remove('open');document.querySelectorAll('.alarm-filter-option').forEach(opt=>{opt.classList.toggle('selected',opt.dataset.value===type);});labelDisplay.textContent=alarmFilterLabels[type]||_t('app.flt.all','Tümü');if(type==='all'){dotDisplay.className='filter-dot-display show';dotDisplay.style.background='#6b7280';dotDisplay.innerHTML='';}else{dotDisplay.className='filter-dot-display show';dotDisplay.style.background=alarmFilterColors[type]||'#7d848c';dotDisplay.innerHTML='';}
filterAlarms(type);}
document.addEventListener('click',function(e){const dropdown=document.getElementById('alarmFilterDropdown');if(dropdown&&!dropdown.contains(e.target)){dropdown.classList.remove('open');}});function filterAlarms(type){currentAlarmFilter=type;alarmsDisplayCount=10;document.querySelectorAll('.alarm-pill').forEach(btn=>{btn.classList.toggle('active',btn.dataset.type===type);});renderAlarmsList(type);}
function searchAlarms(query){alarmSearchQuery=query.toLowerCase().trim();alarmsDisplayCount=10;renderAlarmsList(currentAlarmFilter);}
let _dateFilterCache={todayStr:null,yesterdayStr:null,tomorrowStr:null,cacheTime:0};function getDateFilterStrings(){const now=Date.now();if(_dateFilterCache.todayStr&&(now-_dateFilterCache.cacheTime)<60000){return _dateFilterCache;}
const today=dayjs().tz('Europe/Istanbul');_dateFilterCache={todayStr:today.format('YYYY-MM-DD'),yesterdayStr:today.subtract(1,'day').format('YYYY-MM-DD'),tomorrowStr:today.add(1,'day').format('YYYY-MM-DD'),cacheTime:now};return _dateFilterCache;}
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
function formatTimeAgo(dateStr){if(!dateStr)return'';const date=parseAlarmDate(dateStr);const now=new Date();const diffMs=now-date;const diffMins=Math.floor(diffMs/60000);const diffHours=Math.floor(diffMins/60);const diffDays=Math.floor(diffHours/24);if(diffMins<1)return'Simdi';if(diffMins<60)return`${diffMins}dk once`;if(diffHours<24)return`${diffHours}sa once`;if(diffDays<7)return`${diffDays}g once`;return dateStr.split(' ')[0];}
function formatTimeAgoTR(dateStr){if(!dateStr)return'';const alarmDT=parseAlarmDateTR(dateStr);if(!alarmDT||!alarmDT.isValid())return'';return alarmDT.format('DD.MM HH:mm');}
function parseAlarmDateTR(dateStr){if(!dateStr)return null;if(dateStr.includes('.')&&dateStr.includes(' ')){const[datePart,timePart]=dateStr.split(' ');const dateParts=datePart.split('.');if(dateParts.length===3){const[day,month,year]=dateParts;const[hour,min]=(timePart||'00:00').split(':');const isoStr=`${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')}T${hour.padStart(2, '0')}:${min.padStart(2, '0')}:00`;return dayjs(isoStr).tz(APP_TIMEZONE,true);}}
if(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/.test(dateStr)){return dayjs(dateStr).tz(APP_TIMEZONE,true);}
return toTurkeyTime(dateStr);}
function formatTriggerTimeFull(dateStr){if(!dateStr)return'-';if(dateStr.includes('T')&&(dateStr.includes('+')||dateStr.includes('Z'))){const dt=dayjs(dateStr).tz(APP_TIMEZONE);if(dt&&dt.isValid()){const day=dt.format('DD');const month=_tms(dt.month());const time=dt.format('HH:mm');return`${day} ${month} • ${time}`;}}
if(dateStr.includes('.')&&dateStr.includes(' ')){const parts=dateStr.split(' ');if(parts.length>=2){const datePart=parts[0].split('.');if(datePart.length>=2){const day=datePart[0].padStart(2,'0');const monthIdx=parseInt(datePart[1])-1;const month=_tms(monthIdx)||datePart[1];const time=parts[1];return`${day} ${month} • ${time}`;}}}
return dateStr;}
function formatTriggerTime(dateStr){if(!dateStr)return'-';if(dateStr.includes('.')&&dateStr.includes(' ')){const parts=dateStr.split(' ');if(parts.length>=2&&parts[1].includes(':')){return parts[1];}}
if(dateStr.includes('+03:00')||dateStr.includes('+03')){const dt=dayjs(dateStr).tz(APP_TIMEZONE);if(dt&&dt.isValid()){return dt.format('HH:mm');}}
if(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/.test(dateStr)){const dt=dayjs(dateStr).tz(APP_TIMEZONE,true);if(dt&&dt.isValid()){return dt.format('HH:mm');}}
const dt=parseAlarmDateTR(dateStr);if(!dt||!dt.isValid())return'-';return dt.format('HH:mm');}
function formatTriggerTimeWithDay(dateStr){if(!dateStr)return'-';const str=String(dateStr).trim();if(str.includes('.')&&str.includes(' ')){const parts=str.split(' ');if(parts.length>=2&&parts[1].includes(':')){const dateParts=parts[0].split('.');if(dateParts.length>=2){return`${dateParts[0]}.${dateParts[1]} ${parts[1]}`;}}}
if(str.endsWith('Z')){const dt=dayjs.utc(str).tz(APP_TIMEZONE);if(dt&&dt.isValid()){return dt.format('DD.MM HH:mm');}}
if(str.includes('+00:00')){const dt=dayjs.utc(str.replace('+00:00','Z')).tz(APP_TIMEZONE);if(dt&&dt.isValid()){return dt.format('DD.MM HH:mm');}}
if(str.includes('+03:00')||str.includes('+03')){const dt=dayjs(str).tz(APP_TIMEZONE);if(dt&&dt.isValid()){return dt.format('DD.MM HH:mm');}}
if(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/.test(str)){const dt=dayjs(str).tz(APP_TIMEZONE,true);if(dt&&dt.isValid()){return dt.format('DD.MM HH:mm');}}
if(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+$/.test(str)){const dt=dayjs(str).tz(APP_TIMEZONE,true);if(dt&&dt.isValid()){return dt.format('DD.MM HH:mm');}}
const dt=parseAlarmDateTR(str);if(!dt||!dt.isValid())return'-';return dt.format('DD.MM HH:mm');}
function formatTriggerTimeShort(dateStr){if(!dateStr)return'-';const str=String(dateStr).trim();const ddmmMatch=str.match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})\s*(\d{2}:\d{2})?$/);if(ddmmMatch){const[,day,month,year,time]=ddmmMatch;const isoStr=`${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')}T${time || '00:00'}:00`;const dt=dayjs(isoStr).tz(APP_TIMEZONE,true);if(dt&&dt.isValid()){return dt.format('DD.MM HH:mm');}}
const dt=toTurkeyTime(str);if(!dt||!dt.isValid())return'-';return dt.format('DD.MM HH:mm');}
function goToMatchPage(matchKey,alarmType,alarmMarket){const parts=matchKey.split('_vs_');if(parts.length===2){const home=parts[0].replace(/_/g,' ');const away=parts[1].replace(/_/g,' ');goToMatchFromAlarm(home,away,alarmType,alarmMarket);}}
function goToMatchFromAlarm(homeTeam,awayTeam,alarmType,alarmMarket,league,kickoff,matchIdHash){if(window.userPlan==='test'){var _testFake={home_team:homeTeam,away_team:awayTeam};if(!_isTestFreeMatch(_testFake))return;}
openAlarmId=null;closeAlarmsSidebar();openMatchModalFromAPI(homeTeam.trim(),awayTeam.trim(),(league||'').trim(),(kickoff||'').trim(),(matchIdHash||'').trim());}
async function switchMarketAndFindMatch(targetMarket,homeLower,awayLower,homeTeam,awayTeam){const marketTab=document.querySelector(`[data-market="${targetMarket}"]`);if(marketTab){marketTab.click();}
const startTime=Date.now();const maxWait=1500;const pollInterval=100;let foundIndex=-1;while(Date.now()-startTime<maxWait){const dataSource=filteredMatches.length>0?filteredMatches:matches;for(let i=0;i<dataSource.length;i++){const m=dataSource[i];const mHome=(m.home_team||m.Home||'').toLowerCase().trim();const mAway=(m.away_team||m.Away||'').toLowerCase().trim();if((mHome.includes(homeLower)||homeLower.includes(mHome))&&(mAway.includes(awayLower)||awayLower.includes(mAway))){foundIndex=i;break;}}
if(foundIndex>=0)break;await new Promise(resolve=>setTimeout(resolve,pollInterval));}
if(foundIndex>=0){openMatchModal(foundIndex);}else{const tbody=document.getElementById('matchesTableBody');if(tbody){const rows=tbody.querySelectorAll('tr[onclick*="openMatchModal"]');for(let row of rows){const text=row.textContent.toLowerCase();if(text.includes(homeLower)&&text.includes(awayLower)){const onclickAttr=row.getAttribute('onclick');const indexMatch=onclickAttr?.match(/openMatchModal\((\d+)\)/);if(indexMatch){openMatchModal(parseInt(indexMatch[1]));return;}}}}
const marketLabels={'dropping_1x2':'Drop 1X2','dropping_ou25':'Drop 2.5','dropping_btts':'Drop KG'};showToast(`Maç henüz veritabanında yok. Alarm detayları kartta mevcut.`,'info');}}
let cachedAllAlarms=null;let smartMoneySectionOpen=true;let desktopChartSectionOpen=true;async function loadAllAlarmsOnce(forceRefresh=false){const data=await fetchAlarmsBatch(forceRefresh);cachedAllAlarms=getCachedAlarmsWithType();return cachedAllAlarms;}
function _matchContextHash(match){return(match&&(match.match_id_hash||match.match_id||match.matchIdHash||'')||'').toString().trim();}
function _matchContextLabel(value){return String(value||'').toLowerCase().replace(/\s+/g,' ').trim();}
function _alarmTeamPairMatches(alarm,homeTeam,awayTeam){const homeLower=_matchContextLabel(homeTeam);const awayLower=_matchContextLabel(awayTeam);const aHome=_matchContextLabel(alarm.home||alarm.home_team);const aAway=_matchContextLabel(alarm.away||alarm.away_team);return!!aHome&&!!aAway&&(aHome.includes(homeLower)||homeLower.includes(aHome))&&(aAway.includes(awayLower)||awayLower.includes(aAway));}
function _matchContextTime(value){if(!value)return null;const parsed=toTurkeyTime(value);return parsed&&parsed.isValid()?parsed.valueOf():null;}
function _alarmKickoffMatches(alarm,modalKickoff){const alarmKickoff=alarm.kickoff_utc||alarm.kickoff||alarm.match_date||alarm.fixture_date||'';const modalMs=_matchContextTime(modalKickoff);const alarmMs=_matchContextTime(alarmKickoff);if(modalMs===null||alarmMs===null)return false;return Math.abs(modalMs-alarmMs)<=30*60*1000;}
function _alarmBelongsToMatch(alarm,homeTeam,awayTeam,league,kickoff,matchIdHash){const alarmHash=(alarm.match_id_hash||alarm.match_id||alarm.matchIdHash||'').toString().trim();if(matchIdHash){return!!alarmHash&&alarmHash===matchIdHash;}
if(!_alarmTeamPairMatches(alarm,homeTeam,awayTeam))return false;const modalLeague=_matchContextLabel(league);const alarmLeague=_matchContextLabel(alarm.league);if(!modalLeague||!alarmLeague||modalLeague!==alarmLeague)return false;return _alarmKickoffMatches(alarm,kickoff);}
function getMatchAlarms(homeTeam,awayTeam,league='',kickoff='',matchIdHash=''){if(!cachedAllAlarms)return[];const result=cachedAllAlarms.filter(a=>_alarmBelongsToMatch(a,homeTeam,awayTeam,league,kickoff,matchIdHash));void 0;return result;}
function formatSmartMoneyTime(dateStr){if(!dateStr)return'-';const match1=dateStr.match(/^(\d{2})\.(\d{2})\.(\d{4})\s+(\d{2}):(\d{2})$/);if(match1){const[,day,month,year,hour,min]=match1;const dt=new Date(parseInt(year),parseInt(month)-1,parseInt(day),parseInt(hour),parseInt(min));dt.setHours(dt.getHours()+3);const monthName=_tms(dt.getMonth());const h=String(dt.getHours()).padStart(2,'0');const m=String(dt.getMinutes()).padStart(2,'0');const d=String(dt.getDate()).padStart(2,'0');return`${d} ${monthName} • ${h}:${m}`;}
const match2=dateStr.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);if(match2){const[,year,month,day,hour,min]=match2;const dt=new Date(parseInt(year),parseInt(month)-1,parseInt(day),parseInt(hour),parseInt(min));dt.setHours(dt.getHours()+3);const monthName=_tms(dt.getMonth());const h=String(dt.getHours()).padStart(2,'0');const m=String(dt.getMinutes()).padStart(2,'0');const d=String(dt.getDate()).padStart(2,'0');return`${d} ${monthName} • ${h}:${m}`;}
const dt=parseAlarmDateTR(dateStr);if(!dt||!dt.isValid())return'-';return dt.format('DD MMM • HH:mm');}
window._sxfModalAlarmsRuntimePromise = window._sxfModalAlarmsRuntimePromise || null;
function _getModalAlarmsRuntimeUrl() {
    try {
        const scripts = document.getElementsByTagName('script');
        for (let i = scripts.length - 1; i >= 0; i--) {
            const src = scripts[i].src || '';
            if (src.indexOf('/static/js/app.js') !== -1) {
                const queryIndex = src.indexOf('?');
                const query = queryIndex >= 0 ? src.slice(queryIndex) : '';
                return '/static/js/modal-alarms.js' + query;
            }
        }
    } catch (e) {}
    return '/static/js/modal-alarms.js';
}

function loadModalAlarmsRuntime() {
    if (typeof window.__sxfRenderMatchAlarmsSectionImpl === 'function') return Promise.resolve();
    if (window._sxfModalAlarmsRuntimePromise) return window._sxfModalAlarmsRuntimePromise;

    window._sxfModalAlarmsRuntimePromise = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = _getModalAlarmsRuntimeUrl();
        script.async = true;
        script.onload = () => {
            if (typeof window.__sxfRenderMatchAlarmsSectionImpl === 'function') {
                resolve();
                return;
            }
            window._sxfModalAlarmsRuntimePromise = null;
            reject(new Error('Modal alarms runtime loaded without implementation'));
        };
        script.onerror = () => {
            window._sxfModalAlarmsRuntimePromise = null;
            reject(new Error('Modal alarms runtime failed to load'));
        };
        document.head.appendChild(script);
    });
    return window._sxfModalAlarmsRuntimePromise;
}

async function renderMatchAlarmsSection(...args) {
    await loadModalAlarmsRuntime();
    return window.__sxfRenderMatchAlarmsSectionImpl(...args);
}

function toggleSmartMoneySection(){const grid=document.getElementById('smartMoneyGrid');const empty=document.getElementById('smartMoneyEmpty');const chevron=document.getElementById('smartMoneyChevron');smartMoneySectionOpen=!smartMoneySectionOpen;if(smartMoneySectionOpen){chevron.textContent='▼';const hasAlarms=grid.innerHTML.trim()!=='';if(hasAlarms){grid.style.display='grid';empty.style.display='none';}else{grid.style.display='none';empty.style.display='block';}}else{chevron.textContent='▲';grid.style.display='none';empty.style.display='none';}}
function toggleDesktopChartSection(){const body=document.getElementById('desktopChartBody');const chevron=document.getElementById('desktopChartChevron');if(!body||!chevron)return;desktopChartSectionOpen=!desktopChartSectionOpen;if(desktopChartSectionOpen){chevron.textContent='▼';body.style.display='';}else{chevron.textContent='▲';body.style.display='none';}}
document.addEventListener('DOMContentLoaded',async()=>{document.addEventListener('keydown',(e)=>{if(e.ctrlKey&&e.shiftKey&&e.key==='A'){e.preventDefault();openAdminPanel();}});await _licenseReady;if(!_isLicensed)return;try{await fetchAlarmsBatch();const counts=getCachedAlarmCounts();const badge=document.getElementById('tabAlarmBadge');if(badge)badge.textContent=counts.total;}catch(e){void 0;}});function openAdminPanel(){const overlay=document.getElementById('adminPanelOverlay');if(overlay){overlay.classList.add('open');loadAdminVolumeLeaderData();}}
function closeAdminPanel(){const overlay=document.getElementById('adminPanelOverlay');if(overlay){overlay.classList.remove('open');}}
let currentAdminTab='volumeleader';function switchAdminTab(tab){currentAdminTab=tab;document.querySelectorAll('.admin-tab').forEach(t=>{t.classList.toggle('active',t.dataset.tab===tab);});if(tab==='volumeleader'){loadAdminVolumeLeaderData();}else if(tab==='dropping'){loadAdminDroppingData();}else if(tab==='mim'){loadAdminMimData();}}
async function loadAdminVolumeLeaderData(){const body=document.getElementById('adminPanelBody');if(!body)return;body.innerHTML='<div style="text-align:center; padding:40px; color:#94a3b8;">Yükleniyor...</div>';try{const[configRes,statusRes]=await Promise.all([fetch('/api/volumeleader/config'),fetch('/api/volumeleader/status')]);const config=configRes.ok?await configRes.json():{};await fetchAlarmsBatch();const alarms=getCachedAlarmsByType('volumeleader');const status=statusRes.ok?await statusRes.json():{};let html=`
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
                    
                    <div id="vlCalcStatus" style="display:none; margin-top:12px; padding:8px; background:#141719; border-radius:4px; color:#7d848c; font-size:12px;"></div>
                </div>
            </div>
            
            <div class="admin-section" style="margin-top:24px;">
                <h3 style="color:#06b6d4; margin-bottom:16px;">📊 Alarmlar (${alarms.length})</h3>
        `;if(alarms.length===0){html+='<div class="admin-no-data">Henüz alarm yok. "Hesapla" butonuna tıklayın.</div>';}else{html+=`
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
            `;alarms.slice(0,50).forEach(alarm=>{const matchName=`${alarm.home || '-'} vs ${alarm.away || '-'}`;const market=alarm.market||'-';const oldLeader=`${alarm.old_leader || '-'} (%${(alarm.old_leader_share || 0).toFixed(0)})`;const newLeader=`${alarm.new_leader || '-'} (%${(alarm.new_leader_share || 0).toFixed(0)})`;const totalVol=`£${Number(alarm.total_volume || 0).toLocaleString('en-GB')}`;const eventTime=alarm.trigger_at||alarm.event_time||'-';html+=`
                    <tr>
                        <td class="match-col">${matchName}</td>
                        <td><span class="admin-badge volumeleader">${market}</span></td>
                        <td style="color:#f87171;">${oldLeader}</td>
                        <td style="color:#22d3ee;">${newLeader}</td>
                        <td>${totalVol}</td>
                        <td class="admin-value-muted">${eventTime}</td>
                    </tr>
                `;});html+='</tbody></table>';}
html+='</div>';body.innerHTML=html;}catch(e){console.error('Volume Leader admin veri hatası:',e);body.innerHTML='<div class="admin-no-data">Veri yüklenirken hata oluştu.</div>';}}
async function saveVolumeLeaderConfig(){const config={leader_threshold:parseInt(document.getElementById('vlLeaderThreshold').value)||50,min_volume_1x2:parseInt(document.getElementById('vlMinVolume1x2').value)||5000,min_volume_ou25:parseInt(document.getElementById('vlMinVolumeOu25').value)||2000,min_volume_btts:parseInt(document.getElementById('vlMinVolumeBtts').value)||1000};try{const res=await fetch('/api/volumeleader/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(config)});if(res.ok){showToast('Ayarlar kaydedildi','success');}else{showToast('Kaydetme hatası','error');}}catch(e){showToast('Bağlantı hatası','error');}}
async function calculateVolumeLeaderAlarms(){const btn=document.getElementById('vlCalcBtn');const statusDiv=document.getElementById('vlCalcStatus');if(btn)btn.disabled=true;if(statusDiv){statusDiv.style.display='block';statusDiv.textContent='Hesaplama başlatılıyor...';}
try{const res=await fetch('/api/volumeleader/calculate',{method:'POST'});const data=await res.json();if(data.success){showToast(`${data.count} yeni alarm bulundu!`,'success');loadAdminVolumeLeaderData();}else{showToast(data.error||'Hesaplama hatası','error');}}catch(e){showToast('Bağlantı hatası','error');}finally{if(btn)btn.disabled=false;}}
async function deleteVolumeLeaderAlarms(){if(!confirm('Tüm Hacim Lideri alarmlarını silmek istediğinize emin misiniz?'))return;try{const res=await fetch('/api/volumeleader/alarms',{method:'DELETE'});if(res.ok){showToast('Alarmlar silindi','success');loadAdminVolumeLeaderData();}else{showToast('Silme hatası','error');}}catch(e){showToast('Bağlantı hatası','error');}}
async function loadAdminDroppingData(){const body=document.getElementById('adminPanelBody');if(!body)return;body.innerHTML='<div style="text-align:center; padding:40px; color:#94a3b8;">Yükleniyor...</div>';try{const configRes=await fetch('/api/dropping/config');const config=configRes.ok?await configRes.json():{};await fetchAlarmsBatch();const alarms=getCachedAlarmsByType('dropping');let html=`
            <div class="admin-section">
                <h3 style="color:#f85149; margin-bottom:16px;">📉 Dropping Alarm - Max Oran Eşiği</h3>
                <p style="color:#7d848c; font-size:12px; margin-bottom:16px;">
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
                    
                    <div style="border-top: 1px solid #2e3238; margin-top: 16px; padding-top: 16px;">
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
                    
                    <div id="drCalcStatus" style="display:none; margin-top:12px; padding:8px; background:#141719; border-radius:4px; color:#7d848c; font-size:12px;"></div>
                </div>
            </div>
            
            <div class="admin-section" style="margin-top:24px;">
                <h3 style="color:#f85149; margin-bottom:16px;">📊 Alarmlar (${alarms.length})</h3>
        `;if(alarms.length===0){html+='<div class="admin-no-data">Henüz alarm yok.</div>';}else{html+=`
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
            `;alarms.slice(0,30).forEach(alarm=>{const matchName=`${alarm.home || '-'} vs ${alarm.away || '-'}`;const market=`${alarm.market || '-'} → ${alarm.selection || '-'}`;const level=alarm.level||'-';const odds=`${alarm.opening_odds?.toFixed(2) || '-'} → ${alarm.current_odds?.toFixed(2) || '-'}`;const dropPct=`${alarm.drop_pct?.toFixed(1) || 0}%`;const levelColor=level==='L3'?'#f85149':level==='L2'?'#ffa657':'#ffc107';html+=`
                    <tr>
                        <td class="match-col">${matchName}</td>
                        <td><span class="admin-badge dropping">${market}</span></td>
                        <td><span style="color:${levelColor}; font-weight:600;">${level}</span></td>
                        <td>${odds}</td>
                        <td class="admin-value-negative">${dropPct}</td>
                    </tr>
                `;});html+='</tbody></table>';if(alarms.length>30){html+=`<div style="text-align:center; padding:12px; color:#5c636b; font-size:12px;">+${alarms.length - 30} daha fazla alarm...</div>`;}}
html+='</div>';body.innerHTML=html;}catch(e){console.error('Dropping admin veri hatası:',e);body.innerHTML='<div class="admin-no-data">Veri yüklenirken hata oluştu.</div>';}}
async function saveDroppingConfig(){const config={max_odds_1x2:parseFloat(document.getElementById('drMaxOdds1x2').value)||5.0,max_odds_ou25:parseFloat(document.getElementById('drMaxOddsOu25').value)||3.0,max_odds_btts:parseFloat(document.getElementById('drMaxOddsBtts').value)||3.0,min_drop_l1:parseInt(document.getElementById('drMinDropL1').value)||10,max_drop_l1:parseInt(document.getElementById('drMaxDropL1').value)||17,min_drop_l2:parseInt(document.getElementById('drMinDropL2').value)||17,max_drop_l2:parseInt(document.getElementById('drMaxDropL2').value)||20,min_drop_l3:parseInt(document.getElementById('drMinDropL3').value)||20};try{const res=await fetch('/api/dropping/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(config)});if(res.ok){showToast('Dropping ayarları kaydedildi','success');}else{showToast('Kaydetme hatası','error');}}catch(e){showToast('Bağlantı hatası','error');}}
async function calculateDroppingAlarms(){const btn=document.getElementById('drCalcBtn');const statusDiv=document.getElementById('drCalcStatus');if(btn)btn.disabled=true;if(statusDiv){statusDiv.style.display='block';statusDiv.textContent='Dropping alarmları hesaplanıyor...';}
try{const res=await fetch('/api/dropping/calculate',{method:'POST'});const data=await res.json();if(data.success){showToast(`${data.count} dropping alarm bulundu!`,'success');loadAdminDroppingData();}else{showToast(data.error||'Hesaplama hatası','error');}}catch(e){showToast('Bağlantı hatası','error');}finally{if(btn)btn.disabled=false;}}
async function deleteDroppingAlarms(){if(!confirm('Tüm Dropping alarmlarını silmek istediğinize emin misiniz?'))return;try{const res=await fetch('/api/dropping/alarms',{method:'DELETE'});if(res.ok){showToast('Dropping alarmları silindi','success');loadAdminDroppingData();}else{showToast('Silme hatası','error');}}catch(e){showToast('Bağlantı hatası','error');}}
async function loadAdminMimData(){const body=document.getElementById('adminPanelBody');if(!body)return;body.innerHTML='<div style="text-align:center; padding:40px; color:#94a3b8;">Yükleniyor...</div>';try{const configRes=await fetch('/api/mim/config');const config=configRes.ok?await configRes.json():{};await fetchAlarmsBatch();const alarms=getCachedAlarmsByType('mim');let html=`
            <div class="admin-section">
                <h3 style="color:#3B82F6; margin-bottom:16px;">💰 MIM (Market Impact Money) - Ayarlar</h3>
                <p style="color:#7d848c; font-size:12px; margin-bottom:16px;">
                    MIM alarmı, piyasa etkisini ölçer. Impact değeri ne kadar yüksekse, o seçim için para akışı o kadar güçlüdür.
                </p>
                
                <div class="admin-config-form">
                    <div class="config-row">
                        <label>Min. Impact Eşiği</label>
                        <input type="number" id="mimMinImpact" value="${config.min_impact_threshold || 0.10}" min="0.01" max="1.0" step="0.01">
                        <span class="config-hint">Minimum impact değeri (varsayılan: 0.10)</span>
                    </div>
                    
                    <div class="config-row">
                        <label>Min. Hacim (£)</label>
                        <input type="number" id="mimMinVolume" value="${config.min_volume || 1000}" min="100" step="100">
                        <span class="config-hint">Minimum toplam hacim</span>
                    </div>
                    
                    <div class="config-actions">
                        <button class="admin-btn primary" onclick="saveMimConfig()">💾 Ayarları Kaydet</button>
                        <button class="admin-btn danger" onclick="deleteMimAlarms()">🗑️ Alarmları Sil</button>
                    </div>
                </div>
            </div>
            
            <div class="admin-section" style="margin-top:24px;">
                <h3 style="color:#3B82F6; margin-bottom:16px;">📊 Alarmlar (${alarms.length})</h3>
        `;if(alarms.length===0){html+='<div class="admin-no-data">Henüz MIM alarmı yok.</div>';}else{html+=`
                <table class="admin-table">
                    <thead>
                        <tr>
                            <th>Maç</th>
                            <th>Market</th>
                            <th>Seçim</th>
                            <th>Seviye</th>
                            <th>Impact</th>
                            <th>Hacim</th>
                            <th>Alarm Zamanı</th>
                        </tr>
                    </thead>
                    <tbody>
            `;alarms.slice(0,50).forEach(alarm=>{const matchName=`${alarm.home || '-'} vs ${alarm.away || '-'}`;const market=alarm.market||'-';const selection=alarm.selection||'-';const level=alarm.level||'-';const impact=(alarm.impact||alarm.impact_score||alarm.money_impact||0).toFixed(2);const volume=`£${Number(alarm.current_volume || alarm.curr_volume || alarm.total_volume || alarm.volume || 0).toLocaleString('en-GB')}`;const eventTime=alarm.trigger_at||alarm.event_time||'-';const levelColor=level>=3?'#3B82F6':level>=2?'#60a5fa':'#93c5fd';html+=`
                    <tr>
                        <td class="match-col">${matchName}</td>
                        <td><span class="admin-badge mim">${market}</span></td>
                        <td>${selection}</td>
                        <td><span style="color:${levelColor}; font-weight:600;">L${level}</span></td>
                        <td style="color:#3B82F6; font-weight:600;">${impact}</td>
                        <td>${volume}</td>
                        <td class="admin-value-muted">${eventTime}</td>
                    </tr>
                `;});html+='</tbody></table>';if(alarms.length>50){html+=`<div style="text-align:center; padding:12px; color:#5c636b; font-size:12px;">+${alarms.length - 50} daha fazla alarm...</div>`;}}
html+='</div>';body.innerHTML=html;}catch(e){console.error('MIM admin veri hatası:',e);body.innerHTML='<div class="admin-no-data">Veri yüklenirken hata oluştu.</div>';}}
async function saveMimConfig(){const config={min_impact_threshold:parseFloat(document.getElementById('mimMinImpact').value)||0.10,min_volume:parseInt(document.getElementById('mimMinVolume').value)||1000};try{const res=await fetch('/api/mim/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(config)});if(res.ok){showToast('MIM ayarları kaydedildi','success');}else{showToast('Kaydetme hatası','error');}}catch(e){showToast('Bağlantı hatası','error');}}
async function deleteMimAlarms(){if(!confirm('Tüm MIM alarmlarını silmek istediğinize emin misiniz?'))return;try{const res=await fetch('/api/mim/alarms',{method:'DELETE'});if(res.ok){showToast('MIM alarmları silindi','success');invalidateAlarmCache();loadAdminMimData();}else{showToast('Silme hatası','error');}}catch(e){showToast('Bağlantı hatası','error');}}
const WEB_LICENSE_KEY='smartxflow_web_license';const WEB_LICENSE_VALID_KEY='smartxflow_license_valid_until';const LEGACY_WEB_LICENSE_VALID_KEY='smartxflow_web_license_valid';const LEGACY_WEB_LICENSE_MIGRATION_MS=15*60*1000;window._testFreeHashes=[];window._testFreeTeams=[];function checkWebLicense(){if(localStorage.getItem('license_plan')==='test'){window.userPlan='test';window.userLicenseKey='';if(typeof _isPro!=='undefined')_isPro=false;return true;}
const savedKey=localStorage.getItem(WEB_LICENSE_KEY);let validUntil=localStorage.getItem(WEB_LICENSE_VALID_KEY);if(savedKey&&!validUntil&&localStorage.getItem(LEGACY_WEB_LICENSE_VALID_KEY)==='true'){validUntil=new Date(Date.now()+LEGACY_WEB_LICENSE_MIGRATION_MS).toISOString();localStorage.setItem(WEB_LICENSE_VALID_KEY,validUntil);localStorage.removeItem(LEGACY_WEB_LICENSE_VALID_KEY);}
if(savedKey&&validUntil){const validDate=new Date(validUntil);if(validDate>new Date()){window.userPlan=localStorage.getItem('license_plan')||'core';window.userLicenseKey=savedKey;if(typeof _isPro!=='undefined')_isPro=(window.userPlan==='pro');return true;}}
return false;}
function showLicenseGate(){const gate=document.getElementById('licenseGate');if(gate){gate.style.display='flex';document.body.style.overflow='hidden';}}
function hideLicenseGate(){const gate=document.getElementById('licenseGate');if(gate){gate.style.display='none';document.body.style.overflow='';}}
function updateLicenseDaysBadge(days){const badge=document.getElementById('licenseDaysBadge');const text=document.getElementById('licenseDaysText');if(!badge||!text)return;badge.classList.remove('warning','danger');if(days>=36500){text.textContent='Lifetime';}else if(days<=0){text.textContent=window.SXFI18n?window.SXFI18n.t('app.dyn.suresi_doldu'):'Süresi doldu';badge.classList.add('danger');}else{text.textContent=(window.SXFI18n?window.SXFI18n.t('app.dyn.kalan_pre'):'Kalan ')+days+(window.SXFI18n?window.SXFI18n.t('app.dyn.kalan_suf'):' gün');if(days<=3){badge.classList.add('danger');}else if(days<=7){badge.classList.add('warning');}}
badge.style.display='flex';}
window.addEventListener('i18n:change',function(){var savedDays=localStorage.getItem('license_days_remaining');if(savedDays!==null)updateLicenseDaysBadge(parseInt(savedDays,10));if(typeof _updateFavCountsInDOM==='function')_updateFavCountsInDOM();var si=document.getElementById('searchInput');if(si&&window.SXFI18n)si.placeholder=window.SXFI18n.t('idx.takim_veya_lig_ara')||si.placeholder;if(typeof filteredMatches!=='undefined'&&filteredMatches&&filteredMatches.length){try{renderMatches(filteredMatches);}catch(e){}}
var labelEl=document.getElementById('dayFilterLabel');if(labelEl&&typeof _getDayFilterLabel==='function'){labelEl.textContent=_getDayFilterLabel(typeof currentDayFilter!=='undefined'?currentDayFilter:'all');}
var pd=document.getElementById('mfPastDropdown');if(pd&&pd.style.display!=='none'&&typeof _buildMfPastDropdown==='function'){_buildMfPastDropdown(pd);}});async function validateWebLicense(){const input=document.getElementById('licenseKeyInput');const errorDiv=document.getElementById('licenseError');const successDiv=document.getElementById('licenseSuccess');const progressBar=document.getElementById('licenseProgressBar');const progressFill=document.getElementById('licenseProgressFill');const submitBtn=document.getElementById('licenseSubmitBtn');const btnText=submitBtn.querySelector('.license-btn-text');const btnLoading=document.getElementById('licenseBtnLoading');const key=input.value.trim().toUpperCase();if(!key){errorDiv.textContent='Lisans anahtari girin';errorDiv.style.display='block';return;}
errorDiv.style.display='none';successDiv.style.display='none';progressBar.style.display='block';progressFill.style.width='30%';btnText.style.opacity='0';btnLoading.style.display='block';submitBtn.disabled=true;try{progressFill.style.width='60%';const res=await fetch('/api/licenses/validate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:key,device_id:getWebDeviceId(),device_name:navigator.userAgent.substring(0,50)})});const data=await res.json();progressFill.style.width='90%';if(data.valid){progressFill.style.width='100%';localStorage.setItem(WEB_LICENSE_KEY,key);const validUntil=data.expires_at||new Date(Date.now()+24*60*60*1000).toISOString();localStorage.setItem(WEB_LICENSE_VALID_KEY,validUntil);window.userPlan=data.plan||'core';window.userLicenseKey=key;localStorage.setItem('license_plan',window.userPlan);if(typeof _isPro!=='undefined')_isPro=(window.userPlan==='pro');let daysRemaining=data.days_left||data.days_remaining;if(!daysRemaining&&data.expires_at){const expiresDate=new Date(data.expires_at);const now=new Date();daysRemaining=Math.ceil((expiresDate-now)/(1000*60*60*24));}
if(!daysRemaining||daysRemaining>9000)daysRemaining=36500;localStorage.setItem('license_days_remaining',daysRemaining);updateLicenseDaysBadge(daysRemaining);successDiv.innerHTML='<div style="font-size:24px;margin-bottom:8px;">✓</div>'+(window.SXFI18n?window.SXFI18n.t('app.dyn.lisans_aktif_kalan_gun'):'Lisans aktif! Kalan gün: ')+daysRemaining;successDiv.style.display='block';progressBar.style.display='none';setTimeout(()=>{hideLicenseGate();const _np=new URLSearchParams(window.location.search);const _next=_np.get('next');if(_next&&_next.startsWith('/')){window.location.href=_next;}else{window.location.reload();}},1500);}else{errorDiv.textContent=data.error||'Gecersiz lisans anahtari';errorDiv.style.display='block';progressBar.style.display='none';btnText.style.opacity='1';btnLoading.style.display='none';submitBtn.disabled=false;}}catch(e){errorDiv.textContent='Baglanti hatasi';errorDiv.style.display='block';progressBar.style.display='none';btnText.style.opacity='1';btnLoading.style.display='none';submitBtn.disabled=false;}}
async function activateTestMode(){try{var res=await fetch('/api/test/activate',{method:'POST'});var data=await res.json();if(data.success){localStorage.setItem('license_plan','test');localStorage.removeItem(WEB_LICENSE_KEY);localStorage.removeItem(WEB_LICENSE_VALID_KEY);window.userPlan='test';if(typeof _isPro!=='undefined')_isPro=false;hideLicenseGate();window.location.reload();}}catch(e){console.error('Test mode activate error:',e);}}
async function _loadTestFreeHashes(){if(window.userPlan!=='test')return;var controller=new AbortController();var timeoutId=setTimeout(function(){controller.abort();},5000);try{var res=await fetch('/api/test/free-matches',{cache:'no-store',signal:controller.signal});if(!res.ok)throw new Error('HTTP '+res.status);var data=await res.json();window._testFreeHashes=data.hashes||[];window._testFreeTeams=data.teams||[];}catch(e){window._testFreeHashes=[];window._testFreeTeams=[];console.warn('[TestMode] Free-match lookup failed; continuing without optional data:',e);}finally{clearTimeout(timeoutId);}}
function _isTestFreeAlarm(home,away){if(window.userPlan!=='test')return true;var h=(home||'').toLowerCase().trim();var a=(away||'').toLowerCase().trim();for(var ti=0;ti<window._testFreeTeams.length;ti++){var t=window._testFreeTeams[ti];var th=(t.home||'').toLowerCase().trim();var ta=(t.away||'').toLowerCase().trim();if(th&&ta&&th===h&&ta===a)return true;}
return false;}
function _isTestFreeMatch(matchId){if(window.userPlan!=='test')return true;return window._testFreeHashes.indexOf(matchId)!==-1;}
var _TEST_LOCKED_TOAST='Bu özellik lisans gerektirir';function _isTestLockedMarket(market){if(window.userPlan!=='test')return false;return market!=='moneyway_1x2'&&market!=='dropping_1x2';}
function _showTestLockedToast(anchorEl){showToast(_TEST_LOCKED_TOAST,'warning',anchorEl||null);}
function _addTestLockIcons(){if(window.userPlan!=='test')return;var lockSvg='<svg class="test-lock-icon-sm" width="10" height="10" viewBox="0 0 24 24" fill="#5c636b" stroke="none"><path d="M18 10V8A6 6 0 0 0 6 8v2H4a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-8a2 2 0 0 0-2-2h-2zm-8 0V8a2 2 0 1 1 4 0v2H10z"/></svg>';document.querySelectorAll('.market-tabs .tab').forEach(function(tab){var m=tab.dataset.market;if(m&&m!=='moneyway_1x2'&&m!=='dropping_1x2'&&m!=='live'){if(!tab.querySelector('.test-lock-icon-sm')){tab.insertAdjacentHTML('beforeend',lockSvg);}}});document.querySelectorAll('.btn-today').forEach(function(btn){if(btn.textContent.indexOf('Analizler')!==-1||btn.querySelector('.analysis-active-badge')){if(!btn.querySelector('.test-lock-icon-sm')){btn.insertAdjacentHTML('beforeend',lockSvg);}}});var alarmsBtn=document.getElementById('alarmsBtn');if(alarmsBtn&&!alarmsBtn.querySelector('.test-lock-icon-sm')){alarmsBtn.insertAdjacentHTML('beforeend',lockSvg);}
document.querySelectorAll('.mob-act-btn').forEach(function(btn){if(btn.textContent.indexOf('Alarmlar')!==-1){if(!btn.querySelector('.test-lock-icon-sm')){btn.insertAdjacentHTML('beforeend',lockSvg);}}});var overflowMenu=document.getElementById('mobileOverflowMenu');if(overflowMenu){overflowMenu.querySelectorAll('button').forEach(function(btn){if(btn.textContent.indexOf('Analizler')!==-1){if(!btn.querySelector('.test-lock-icon-sm')){btn.insertAdjacentHTML('beforeend',lockSvg);}}});}}
function _testGuardAnalysis(btn){if(window.userPlan==='test'){_showTestLockedToast(btn||null);return;}
openDeferredTrendsModal('analysis');}
function _addMobileMktLockIcons(){if(window.userPlan!=='test')return;var lockSvg='<svg class="test-lock-icon-sm" width="9" height="9" viewBox="0 0 24 24" fill="#5c636b" stroke="none"><path d="M18 10V8A6 6 0 0 0 6 8v2H4a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-8a2 2 0 0 0-2-2h-2zm-8 0V8a2 2 0 1 1 4 0v2H10z"/></svg>';document.querySelectorAll('#mobMktRow .mob-tab').forEach(function(tab){var mkt=tab.getAttribute('data-mkt');if(mkt&&mkt!=='1x2'){if(!tab.querySelector('.test-lock-icon-sm')){tab.insertAdjacentHTML('beforeend',' '+lockSvg);}}});}
async function _fetchAccountSessionStatus(){const controller=new AbortController();const timeoutId=setTimeout(function(){controller.abort();},5000);try{const response=await fetch('/api/auth/session-status',{credentials:'same-origin',cache:'no-store',signal:controller.signal});if(!response.ok)return null;return await response.json();}catch(error){return null;}finally{clearTimeout(timeoutId);}}
async function initLicenseCheck(){if(!checkWebLicense()){const accountStatus=await _fetchAccountSessionStatus();if(accountStatus&&accountStatus.status==='ok'){const plan=accountStatus.test_mode?'test':(accountStatus.plan||'core');window.userPlan=plan;window.userLicenseKey='';if(typeof _isPro!=='undefined')_isPro=(plan==='pro');localStorage.setItem('license_plan',plan);localStorage.removeItem(WEB_LICENSE_KEY);localStorage.removeItem(WEB_LICENSE_VALID_KEY);localStorage.removeItem('license_days_remaining');const logoutBtn=document.getElementById('logoutBtn');if(logoutBtn)logoutBtn.style.display='flex';_isLicensed=true;_licenseReadyResolve();if(plan==='test'){_loadTestFreeHashes();updateLicenseDaysBadge(-1);var daysBadge=document.getElementById('licenseDaysBadge');if(daysBadge){var daysText=document.getElementById('licenseDaysText');if(daysText)daysText.textContent='Test Modu';daysBadge.classList.add('warning');}
setTimeout(function(){_addTestLockIcons();_addMobileMktLockIcons();},100);}else if(accountStatus.subscription_expires_at){const expiresAt=new Date(accountStatus.subscription_expires_at);if(Number.isFinite(expiresAt.getTime())){const daysLeft=Math.ceil((expiresAt.getTime()-Date.now())/86400000);localStorage.setItem('license_days_remaining',String(daysLeft));updateLicenseDaysBadge(daysLeft);}}
return;}
if(accountStatus&&(accountStatus.status==='email_unverified'||accountStatus.status==='membership_required')){_isLicensed=false;_licenseReadyResolve();window.location.replace(accountStatus.status==='email_unverified'?'/verify-email':'/membership-required');return;}
if(accountStatus&&accountStatus.status==='session_expired'){_isLicensed=false;_licenseReadyResolve();window.location.replace('/login?next=/app');return;}
if(!accountStatus||accountStatus.status!=='login_required'){_isLicensed=false;_licenseReadyResolve();if(typeof renderMatchLoadError==='function'){renderMatchLoadError('Hesap oturumu doğrulanamadı. Sayfayı yenileyip tekrar deneyin.',true);}else{showLicenseGate();}
return;}
showLicenseGate();const logoutBtn=document.getElementById('logoutBtn');if(logoutBtn)logoutBtn.style.display='none';_isLicensed=false;_licenseReadyResolve();return;}
const logoutBtn=document.getElementById('logoutBtn');if(logoutBtn)logoutBtn.style.display='flex';if(window.userPlan==='test'){_isLicensed=true;_licenseReadyResolve();_loadTestFreeHashes();updateLicenseDaysBadge(-1);var daysBadge=document.getElementById('licenseDaysBadge');if(daysBadge){var daysText=document.getElementById('licenseDaysText');if(daysText)daysText.textContent='Test Modu';daysBadge.classList.add('warning');}
setTimeout(function(){_addTestLockIcons();_addMobileMktLockIcons();},100);return;}
const savedDays=localStorage.getItem('license_days_remaining');if(savedDays)updateLicenseDaysBadge(parseInt(savedDays));_isLicensed=true;_licenseReadyResolve();startLicenseStatusRefresh();const savedKey=localStorage.getItem(WEB_LICENSE_KEY);if(savedKey){fetch('/api/licenses/validate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:savedKey,device_id:getWebDeviceId(),device_name:navigator.userAgent.substring(0,50)})}).then(r=>r.json()).then(data=>{if(data.valid&&data.days_left!==undefined){localStorage.setItem('license_days_remaining',data.days_left);updateLicenseDaysBadge(data.days_left);}
if(data.plan){window.userPlan=data.plan;localStorage.setItem('license_plan',data.plan);if(typeof _isPro!=='undefined')_isPro=(window.userPlan==='pro');}}).catch(()=>{});}}
function logoutWebLicense(){if(confirm('Cikis yapmak istediginize emin misiniz?')){fetch('/api/licenses/logout',{method:'POST'}).catch(()=>{});localStorage.removeItem(WEB_LICENSE_KEY);localStorage.removeItem(WEB_LICENSE_VALID_KEY);localStorage.removeItem('license_days_remaining');localStorage.removeItem('license_plan');window.location.reload();}}
async function logoutAccount(){var logoutButton=document.getElementById('logoutBtn');if(logoutButton){logoutButton.disabled=true;logoutButton.setAttribute('aria-busy','true');}
var controller=new AbortController();var timeoutId=setTimeout(function(){controller.abort();},5000);try{await fetch('/api/auth/logout',{method:'POST',credentials:'same-origin',cache:'no-store',signal:controller.signal});}catch(error){console.warn('[Auth] Logout request failed; clearing local session state:',error);}finally{clearTimeout(timeoutId);localStorage.removeItem(WEB_LICENSE_KEY);localStorage.removeItem(WEB_LICENSE_VALID_KEY);localStorage.removeItem('license_days_remaining');localStorage.removeItem('license_plan');window.location.replace('/login');}}
function copyLicenseEmail(){const email='smartxflow29@gmail.com';const emailText=document.getElementById('licenseEmailText');navigator.clipboard.writeText(email).then(()=>{if(emailText){const original=emailText.textContent;emailText.textContent='Kopyalandi!';setTimeout(()=>{emailText.textContent=original;},1500);}}).catch(()=>{window.location.href='mailto:'+email;});}
document.addEventListener('DOMContentLoaded',function(){Promise.resolve().then(function(){return initLicenseCheck();}).catch(function(error){console.error('[License] Initialization failed:',error);_licenseReadyResolve();if(!_isLicensed){if(typeof renderMatchLoadError==='function'){renderMatchLoadError('Lisans doğrulaması tamamlanamadı. Sayfayı yenileyip tekrar deneyin.',true);}else{showLicenseGate();}}});});document.getElementById('licenseKeyInput')?.addEventListener('keypress',function(e){if(e.key==='Enter')validateWebLicense();});var _bgLiveInterval = null;
var _bgLiveStartScheduled = false;async function _fetchBackgroundLiveData(){if(_liveMode)return;try{var resp=await fetch('/api/live/matches');var data=await resp.json();_liveData=data.matches||[];_updateLiveCapsulesInDOM();}catch(e){}}
function _updateLiveCapsulesInDOM(){if(_liveMode)return;document.querySelectorAll('#matchesTableBody tr').forEach(function(row){var teamsCell=row.querySelector('.match-teams');var dateCell=row.querySelector('.match-date');if(!teamsCell||!dateCell)return;var capsuleEl=teamsCell.querySelector('.live-capsule');var deskCapsuleEl=dateCell.querySelector('.live-capsule-desk');var matchId=row.getAttribute('data-match-id')||'';var teamsText=teamsCell.textContent||'';var parts=teamsText.split(/\s*[-–]\s*/);if(parts.length<2)return;var home=parts[0].trim();var away=parts[parts.length-1].trim();var lm=_findLiveMatchByHash(matchId)||_findLiveMatch(home,away);if(!lm)return;if(_isFinishedLiveMatch(lm))return;if(capsuleEl){var rawMin=(lm.minute||'').trim();var sc=lm.score||'';if(rawMin||sc){var minDisp=rawMin||'';var scoreDisp='';if(sc){var sp=sc.split('-');if(sp.length===2){scoreDisp='<span class="lc-divider"></span><span class="lc-score-val"><span class="lc-score-h">'+sp[0].trim()+'</span><span class="lc-score-sep">-</span><span class="lc-score-a">'+sp[1].trim()+'</span></span>';}}
capsuleEl.innerHTML='<span class="lc-dot"></span><span class="lc-min">'+minDisp+'</span>'+scoreDisp;}}
if(deskCapsuleEl){var rawMin2=(lm.minute||'').trim();var sc2=lm.score||'';if(rawMin2||sc2){var scoreDisp2='';if(sc2){var sp2=sc2.split('-');if(sp2.length===2){scoreDisp2='<span class="lc-divider"></span><span class="lc-score-h">'+sp2[0].trim()+'</span><span class="lc-score-sep">-</span><span class="lc-score-a">'+sp2[1].trim()+'</span>';}}
deskCapsuleEl.innerHTML='<span class="lc-dot"></span><span class="lc-min">'+rawMin2+'</span>'+scoreDisp2;}}});}
function _startBackgroundLiveFetch() {
    if (_bgLiveInterval || _bgLiveStartScheduled) return;
    _bgLiveStartScheduled = true;

    function begin() {
        if (_bgLiveInterval) return;
        _bgLiveStartScheduled = false;
        _fetchBackgroundLiveData();
        _bgLiveInterval = setInterval(_fetchBackgroundLiveData, 60000);
    }

    if (typeof window.requestIdleCallback === 'function') {
        window.requestIdleCallback(begin, { timeout: 5000 });
    } else {
        window.setTimeout(begin, 2500);
    }
}
var _liveMode=false;var _liveInterval=null;var _liveData=[];var _liveMarket='1x2';var _modalLiveData=null;var _modalLiveMarket='1x2';var _liveDetailData=null;var _liveDetailMarket='1x2';var _prevLiveScores={};var _finishedScores={};function proLockPanelHtml(){return'<div class="smart-money-empty" style="display:block">'+_t('app.live.pro_periyot','Canlı periyot verileri için Pro üyelik gerektirir.')+'</div>';}
function _liveProBanner(){return'<div class="live-pro-banner">'+'<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="flex-shrink:0"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>'+' '+_t('app.live.pro_gerekli','Canlı veriler için <strong>Pro</strong> üyelik gerekmektedir')+' <a href="/pricing" class="live-pro-banner-btn">'+_t('app.live.proya_gec',"Pro'ya Geç →")+'</a>'+'</div>';}
async function _renderLiveProLock(){_liveMode=true;document.querySelectorAll('.tab').forEach(function(t){t.classList.remove('active');});document.querySelectorAll('.mobile-tab-btn').forEach(function(t){t.classList.remove('active');});var liveTab=document.querySelector('.tab-live');if(liveTab)liveTab.classList.add('active');var mobileLive=document.querySelector('.mobile-live-btn');if(mobileLive)mobileLive.classList.add('active');var mcLabel=document.getElementById('matchCountLabel');if(mcLabel)mcLabel.textContent=_t('app.live.canli_maclar','Canlı Maçlar')+' ';var mcSuffix=document.getElementById('matchCountSuffix');if(mcSuffix)mcSuffix.textContent='';var mcWrap=document.querySelector('.match-count');if(mcWrap)mcWrap.classList.add('mc-live');var lmt=document.getElementById('liveMarketTabs');if(lmt)lmt.style.display='none';var marketRow=document.querySelector('.mobile-tab-row.market-row');if(marketRow)marketRow.style.display='none';var table=document.querySelector('.matches-table');var tbody=document.getElementById('matchesTableBody');var thead=table?table.querySelector('thead'):null;var colgroup=table?table.querySelector('colgroup'):null;var cardList=document.getElementById('matchCardList');if(table)table.setAttribute('data-selection-count','3');if(colgroup)colgroup.innerHTML='<col class="col-fav"><col class="col-date"><col class="col-league"><col class="col-match">'+'<col class="col-selection"><col class="col-selection"><col class="col-selection"><col class="col-volume">';if(thead)thead.innerHTML='<tr>'+'<th class="col-fav"></th>'+'<th class="col-date">'+_t('app.live.dk','DK')+'</th>'+'<th class="col-league">'+_t('app.tbl.league','LİG')+'</th>'+'<th class="col-match">'+_t('app.tbl.match','MAÇ')+'</th>'+'<th class="col-selection">1</th>'+'<th class="col-selection">X</th>'+'<th class="col-selection">2</th>'+'<th class="col-volume">'+_t('app.tbl.volume','HACİM')+'</th>'+'</tr>';if(tbody)tbody.innerHTML='<tr><td colspan="8" style="text-align:center;padding:30px;"><div class="loading-spinner"></div></td></tr>';var matches=[];try{var resp=await fetch('/api/live/matches');var data=await resp.json();matches=data.matches||[];}catch(e){}
var nowMs=Date.now();var filtered=matches.filter(function(m){var min=(m.minute||'').trim().toUpperCase();if(min==='FT'||min==='MS'||min==='AET'||min==='PEN')return false;if((m.status||'').toLowerCase()==='ft')return false;if(m.kickoff_utc){var ko=new Date(m.kickoff_utc);if(!isNaN(ko.getTime())){var diffM=(nowMs-ko.getTime())/60000;if(diffM>=120)return false;if(diffM<0||diffM>130){if(!min&&!m.score)return false;}}}else if(!min&&!m.score){return false;}
if(_liveCalcVol1x2(m)<=0)return false;return true;});var _blurStyle='filter:blur(6px);-webkit-filter:blur(6px);user-select:none;pointer-events:none';var rowsHtml='';var cardsHtml='';for(var i=0;i<filtered.length;i++){var m=filtered[i];var o=m.odds||{};var matchMin=_calcLiveMatchMin(m);var scoreStr=m.score?escLiveHtml(m.score):'';var _liveFavTd=_buildLiveFavCell(m);var capHtml='<div class="live-capsule live-capsule-desk">'+'<span class="lc-dot"></span>'+'<span class="lc-min">'+escLiveHtml(matchMin)+'</span>';if(scoreStr){var sp=scoreStr.split('-');if(sp.length===2){capHtml+='<span class="lc-divider"></span>'+'<span class="lc-score-h">'+sp[0].trim()+'</span>'+'<span class="lc-score-sep">-</span>'+'<span class="lc-score-a">'+sp[1].trim()+'</span>';}else{capHtml+='<span class="lc-divider"></span><span class="lc-score-val">'+escLiveHtml(scoreStr)+'</span>';}}
capHtml+='</div>';var vol=_liveCalcVol1x2(m);var b1=_liveMwBlock('1',o['1']);var bX=_liveMwBlock('X',o['X']);var b2=_liveMwBlock('2',o['2']);rowsHtml+='<tr class="live-row">'+
_liveFavTd+'<td class="match-date">'+capHtml+'</td>'+'<td class="match-league" title="'+escLiveHtml(m.league)+'">'+escLiveHtml(m.league)+'</td>'+'<td class="match-teams">'+escLiveHtml(m.home_team)+'<span class="vs">-</span>'+escLiveHtml(m.away_team)+'</td>'+'<td class="mw-outcomes-cell" colspan="3" style="'+_blurStyle+'"><div class="mw-grid mw-grid-3">'+b1+bX+b2+'</div></td>'+'<td class="volume-cell" style="'+_blurStyle+'">'+formatLiveVol(vol)+'</td></tr>';var _lmk=_getMatchKey(m);var _lmkIsFav=_userFavorites.has(_lmk);var _lmkFc=_favCounts[_lmk]||0;var cardScore=m.score?escLiveHtml(m.score):(matchMin==='MS'?'-':'');var mobCapHtml='';if(matchMin||cardScore){mobCapHtml='<div class="live-capsule">'+'<span class="lc-dot"></span>'+'<span class="lc-min">'+escLiveHtml(matchMin)+'</span>'+
(cardScore?'<span class="lc-divider"></span><span class="lc-score-val">'+cardScore+'</span>':'')+'</div>';}
cardsHtml+='<div class="match-card odds-card moneyway-card" data-matchkey="'+_lmk.replace(/"/g,'&quot;')+'">'+
_mobileFavLine(_lmk,_lmkIsFav,_lmkFc)+'<div class="odds-card-header">'+'<div class="odds-card-teams">'+escLiveHtml(m.home_team)+' \u2013 '+escLiveHtml(m.away_team)+'</div>'+'<div class="odds-card-volume" style="'+_blurStyle+'">'+formatLiveVol(vol)+'</div>'+'</div>'+'<div class="odds-card-meta"><span>'+escLiveHtml(m.league)+'</span>'+mobCapHtml+'</div>'+'<div class="odds-card-row three" style="'+_blurStyle+'">'+
_liveMobileBlock('1',o['1'],vol)+
_liveMobileBlock('X',o['X'],vol)+
_liveMobileBlock('2',o['2'],vol)+'</div>'+'</div>';}
if(filtered.length===0){rowsHtml+='<tr><td colspan="8" style="text-align:center;padding:30px;color:#6b7280;">'+_t('app.live.bos','Şu an canlı maç bulunamadı')+'</td></tr>';}
if(tbody)tbody.innerHTML=rowsHtml;if(cardList)cardList.innerHTML=cardsHtml;var mc=document.getElementById('matchCount');if(mc)mc.textContent=filtered.length;if(_favFilterActive)setTimeout(function(){_applyFavoritesFilter();},10);}
function switchToLive(){if(window.userPlan==='core'){var _cTbody=document.getElementById('matchesTableBody');if(_cTbody)_cTbody.innerHTML='';var _cCards=document.getElementById('matchCardList');if(_cCards)_cCards.innerHTML='';_renderLiveProLock();return;}
_liveMode=true;document.querySelectorAll('.tab').forEach(function(t){t.classList.remove('active');});document.querySelectorAll('.mobile-tab-btn').forEach(function(t){t.classList.remove('active');});var liveTab=document.querySelector('.tab-live');if(liveTab)liveTab.classList.add('active');var mobileLive=document.querySelector('.mobile-live-btn');if(mobileLive)mobileLive.classList.add('active');var mcLabel=document.getElementById('matchCountLabel');if(mcLabel)mcLabel.textContent=_t('app.live.canli_maclar','Canlı Maçlar')+' ';var mcSuffix=document.getElementById('matchCountSuffix');if(mcSuffix)mcSuffix.textContent='';var mcWrap=document.querySelector('.match-count');if(mcWrap)mcWrap.classList.add('mc-live');var lmt=document.getElementById('liveMarketTabs');if(lmt)lmt.style.display='flex';var marketRow=document.querySelector('.mobile-tab-row.market-row');if(marketRow)marketRow.style.display='none';var tbody=document.getElementById('matchesTableBody');if(tbody)tbody.innerHTML='<tr><td colspan="8" style="text-align:center;padding:40px;"><div class="loading-spinner"></div> '+_t('app.live.yukleniyor','Canlı maçlar yükleniyor...')+'</td></tr>';var cardList=document.getElementById('matchCardList');if(cardList)cardList.innerHTML='<div style="text-align:center;padding:40px;"><div class="loading-spinner"></div> '+_t('app.live.yukleniyor','Canlı maçlar yükleniyor...')+'</div>';loadLiveMatches();if(_liveInterval)clearInterval(_liveInterval);_liveInterval=setInterval(loadLiveMatches,30000);}
function switchFromLive(){const wasLive=_liveMode;_liveMode=false;if(_liveInterval){clearInterval(_liveInterval);_liveInterval=null;}
_prevLiveScores={};var mcLabel=document.getElementById('matchCountLabel');if(mcLabel)mcLabel.textContent='';var mcSuffix=document.getElementById('matchCountSuffix');if(mcSuffix)mcSuffix.textContent=' '+_t('app.flt.match_count','Maç');var mcWrap=document.querySelector('.match-count');if(mcWrap)mcWrap.classList.remove('mc-live');var lmt=document.getElementById('liveMarketTabs');if(lmt)lmt.style.display='none';var marketRow=document.querySelector('.mobile-tab-row.market-row');if(marketRow)marketRow.style.display='';var thead=document.querySelector('.matches-table thead');if(thead&&!thead.querySelector('tr')){thead.innerHTML='<tr></tr>';}
updateTableHeaders();filteredMatches=applySorting(matches);renderMatches(filteredMatches);if(wasLive){void 0;setTimeout(()=>{if(_liveMode){void 0;return;}
loadMatches(false,true);},0);}}
if(typeof window.setTab==='function'){var _realSetTab=window.setTab;window.setTab=function(market){if(_liveMode)switchFromLive();_realSetTab(market);};}
if(typeof window.setMobileGroup==='function'){var _realSetMobileGroup=window.setMobileGroup;window.setMobileGroup=function(group){if(group==='live'){switchToLive();return;}
if(_liveMode)switchFromLive();_realSetMobileGroup(group);};}
document.addEventListener('click',function(e){var tab=e.target.closest('.tab[data-market]');if(tab&&tab.dataset.market!=='live'&&_liveMode){switchFromLive();}});function setLiveMarket(market){_liveMarket=market;document.querySelectorAll('.live-market-btn').forEach(function(b){b.classList.toggle('active',b.getAttribute('data-lmarket')===market);});document.querySelectorAll('.live-market-dropdown-item').forEach(function(b){b.classList.toggle('active',b.getAttribute('data-lmarket')===market);});renderLiveMatches(_liveData);}
function toggleLiveMarketDropdown(e){e.stopPropagation();var dd=document.getElementById('liveMarketTabs');if(dd)dd.classList.toggle('open');}
function setLiveMarketFromDropdown(market,label){setLiveMarket(market);var lbl=document.getElementById('liveMarketDropdownLabel');if(lbl)lbl.textContent=label;var dd=document.getElementById('liveMarketTabs');if(dd)dd.classList.remove('open');}
document.addEventListener('click',function(e){var dd=document.getElementById('liveMarketTabs');if(dd&&!dd.contains(e.target))dd.classList.remove('open');});async function loadLiveMatches(){try{var resp=await fetch('/api/live/matches');var data=await resp.json();_liveData=data.matches||[];var _goalHashes={};var _prevCount=Object.keys(_prevLiveScores).length;for(var gi=0;gi<_liveData.length;gi++){var gm=_liveData[gi];var gh=gm.match_id_hash;var gs=gm.score||'';if(gh&&gs&&_prevLiveScores[gh]&&_prevLiveScores[gh]!==gs){var oldParts=_prevLiveScores[gh].split('-');var newParts=gs.split('-');var oldH=parseInt(oldParts[0])||0;var oldA=parseInt(oldParts[1])||0;var newH=parseInt(newParts[0])||0;var newA=parseInt(newParts[1])||0;var side='both';if(newH>oldH&&newA===oldA)side='home';else if(newA>oldA&&newH===oldH)side='away';_goalHashes[gh]={side:side,oldScore:_prevLiveScores[gh]};void 0;}
if(gh&&gs)_prevLiveScores[gh]=gs;}
if(_prevCount===0)void 0;renderLiveMatches(_liveData,_goalHashes);var now=new Date();var lut=document.getElementById('liveUpdateTime');if(lut)lut.textContent=String(now.getHours()).padStart(2,'0')+':'+
String(now.getMinutes()).padStart(2,'0')+':'+
String(now.getSeconds()).padStart(2,'0');}catch(e){console.error('Live matches error:',e&&e.message?e.message:e);}}
function formatLiveVol(v){if(!v&&v!==0)return'-';if(v>=1000000)return'\u00A3'+(v/1000000).toFixed(1)+'M';if(v>=1000)return'\u00A3'+(v/1000).toFixed(0)+'K';return'\u00A3'+Math.round(v);}
function escLiveHtml(s){if(!s)return'';return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');}
function _liveDonut(pct,sz){sz=sz||44;var num=parseFloat(String(pct).replace(/[^0-9.]/g,''))||0;var sw=4;var r=(sz-sw*2)/2;var c=2*Math.PI*r;var off=c-(num/100)*c;var hi=num>=50;var fc=hi?'#22c55e':'#1a1d21';var tc=hi?'#ffffff':'#9ca3af';return'<svg width="'+sz+'" height="'+sz+'" viewBox="0 0 '+sz+' '+sz+'">'+'<circle cx="'+sz/2+'" cy="'+sz/2+'" r="'+r+'" fill="none" stroke="#2a2e33" stroke-width="'+sw+'"/>'+'<circle cx="'+sz/2+'" cy="'+sz/2+'" r="'+r+'" fill="none" stroke="'+fc+'" stroke-width="'+sw+'"'+' stroke-dasharray="'+c+'" stroke-dashoffset="'+off+'" stroke-linecap="round" transform="rotate(-90 '+sz/2+' '+sz/2+')"/>'+'<text x="'+sz/2+'" y="'+sz/2+'" text-anchor="middle" dominant-baseline="central" fill="'+tc+'" font-size="9" font-weight="600">'+num.toFixed(0)+'%</text>'+'</svg>';}
function _liveGetOu(m,line){var ols=m.ou_lines||{};return ols[line]||{};}
function _liveCalcVol1x2(m){var o=m.odds||{};var v=0;if(o['1'])v+=o['1'].volume||0;if(o['X'])v+=o['X'].volume||0;if(o['2'])v+=o['2'].volume||0;return v;}
function _liveCalcVolOU(ou){var v=0;if(ou['U'])v+=ou['U'].volume||0;if(ou['O'])v+=ou['O'].volume||0;return v;}
function renderLiveMatches(matches,goalHashes){if(!goalHashes)goalHashes={};var table=document.querySelector('.matches-table');var tbody=document.getElementById('matchesTableBody');var thead=table?table.querySelector('thead'):null;var colgroup=table?table.querySelector('colgroup'):null;var cardList=document.getElementById('matchCardList');var emptyHtml='<div class="live-empty">'+'<div class="live-empty-icon">\u26BD</div>'+'<div class="live-empty-text">'+_t('app.live.bos','Şu an canlı maç bulunamadı')+'</div>'+'<div class="live-empty-sub">'+_t('app.live.bos_sub','Canlı maçlar başladığında burada görünecek')+'</div>'+'</div>';if(!matches||matches.length===0){if(tbody)tbody.innerHTML='<tr><td colspan="8" style="text-align:center;padding:40px;">'+emptyHtml+'</td></tr>';if(thead)thead.innerHTML='<tr><th colspan="8" style="text-align:center;">'+_t('app.live.bos_tablo','Canlı maç bulunamadı')+'</th></tr>';if(cardList)cardList.innerHTML=emptyHtml;var mc=document.getElementById('matchCount');if(mc)mc.textContent='0';return;}
var is1x2=(_liveMarket==='1x2');var ouLine=is1x2?'':_liveMarket.replace('ou','');if(is1x2){if(table)table.setAttribute('data-selection-count','3');if(colgroup)colgroup.innerHTML='<col class="col-fav"><col class="col-date"><col class="col-league"><col class="col-match">'+'<col class="col-selection"><col class="col-selection"><col class="col-selection"><col class="col-volume">';if(thead)thead.innerHTML='<tr>'+'<th class="col-fav"></th>'+'<th class="col-date">'+_t('app.live.dk','DK')+'</th>'+'<th class="col-league">'+_t('app.tbl.league','LİG')+'</th>'+'<th class="col-match">'+_t('app.tbl.match','MAÇ')+'</th>'+'<th class="col-selection">1</th>'+'<th class="col-selection">X</th>'+'<th class="col-selection">2</th>'+'<th class="col-volume">'+_t('app.tbl.volume','HACİM')+'</th>'+'</tr>';}else{if(table)table.setAttribute('data-selection-count','2');if(colgroup)colgroup.innerHTML='<col class="col-fav"><col class="col-date"><col class="col-league"><col class="col-match">'+'<col class="col-selection"><col class="col-selection"><col class="col-volume">';if(thead)thead.innerHTML='<tr>'+'<th class="col-fav"></th>'+'<th class="col-date">'+_t('app.live.dk','DK')+'</th>'+'<th class="col-league">'+_t('app.tbl.league','LİG')+'</th>'+'<th class="col-match">'+_t('app.tbl.match','MAÇ')+'</th>'+'<th class="col-selection">'+_t('app.tbl.alt','ALT')+'</th>'+'<th class="col-selection">'+_t('app.tbl.over','ÜST')+'</th>'+'<th class="col-volume">'+_t('app.tbl.volume','HACİM')+'</th>'+'</tr>';}
var nowMs=Date.now();var filtered=matches.filter(function(m){var min=(m.minute||'').trim().toUpperCase();if(min==='FT'||min==='MS'||min==='AET'||min==='PEN')return false;if((m.status||'').toLowerCase()==='ft')return false;if(m.kickoff_utc){var ko=new Date(m.kickoff_utc);if(!isNaN(ko.getTime())){var diffM=(nowMs-ko.getTime())/60000;if(diffM>=120)return false;if(diffM<0||diffM>130){if(!min&&!m.score)return false;}}}else if(!min&&!m.score){return false;}
if(is1x2)return _liveCalcVol1x2(m)>0;return _liveCalcVolOU(_liveGetOu(m,ouLine))>0;});if(filtered.length===0){if(tbody)tbody.innerHTML='<tr><td colspan="8" style="text-align:center;padding:40px;">'+emptyHtml+'</td></tr>';if(cardList)cardList.innerHTML=emptyHtml;var mc0=document.getElementById('matchCount');if(mc0)mc0.textContent='0';return;}
var sorted=filtered.slice();sorted.sort(function(a,b){var va=is1x2?_liveCalcVol1x2(a):_liveCalcVolOU(_liveGetOu(a,ouLine));var vb=is1x2?_liveCalcVol1x2(b):_liveCalcVolOU(_liveGetOu(b,ouLine));return vb-va;});var rowsHtml='';var cardsHtml='';var _isTestLive=(window.userPlan==='test');var _lgLockSvg='<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#4a5068" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>';var _lgB='<div class="test-lock-cell">'+_lgLockSvg+'</div>';for(var i=0;i<sorted.length;i++){var m=sorted[i];var o=m.odds||{};var matchMin=_calcLiveMatchMin(m);var scoreStr=m.score?escLiveHtml(m.score):'';var onclickAttr='onclick="openLiveDetail(\''+m.match_id_hash+'\',\''+escLiveHtml(m.home_team)+'\',\''+escLiveHtml(m.away_team)+'\')"';var _liveMk=_getMatchKey(m);var _liveMkAttr=' data-matchkey="'+_liveMk.replace(/"/g,'&quot;')+'"';var showScore=(matchMin==='MS')?(scoreStr||'-'):scoreStr;var goalInfo=m.match_id_hash?goalHashes[m.match_id_hash]:null;var goalSide=goalInfo?goalInfo.side:null;var goalOldScore=goalInfo?goalInfo.oldScore:'';var scoreHtml='';if(showScore){var sp=showScore.split('-');if(sp.length===2){var hCls=goalSide==='home'||goalSide==='both'?' goal-pop':'';var aCls=goalSide==='away'||goalSide==='both'?' goal-pop':'';scoreHtml='<div class="time-line live-score-badge">'+'<span class="score-h'+hCls+'">'+sp[0].trim()+'</span>'+'<span class="score-sep">-</span>'+'<span class="score-a'+aCls+'">'+sp[1].trim()+'</span>'+'</div>';}else{scoreHtml='<div class="time-line live-score-badge">'+showScore+'</div>';}}
var minExtra='';if(/^HT$/i.test(matchMin)||/^MS$/i.test(matchMin))minExtra=' is-ht';else if(/\d+\+/.test(matchMin))minExtra=' is-extra';var goalData='';if(goalSide){goalData=' data-goal-side="'+goalSide+'" data-old-score="'+escLiveHtml(goalOldScore)+'" data-new-score="'+escLiveHtml(showScore)+'" data-real-min="'+escLiveHtml(matchMin)+'"';}
var minCell='<td class="match-date">'+'<div class="dk-cell-inner"'+goalData+'>'+'<div class="date-line live-min-badge'+minExtra+'" style="color:#e5484d;">'+escLiveHtml(matchMin)+'</div>'+
scoreHtml+'</div></td>';if(is1x2){var vol=_liveCalcVol1x2(m);var b1=_liveMwBlock('1',o['1']);var bX=_liveMwBlock('X',o['X']);var b2=_liveMwBlock('2',o['2']);var capGoalCls=goalSide?' lc-goal':'';var capMinText=goalSide?'GOL!':escLiveHtml(matchMin);var capScoreHtml='';if(showScore){var csp=showScore.split('-');if(csp.length===2&&goalSide){var hGoal=(goalSide==='home'||goalSide==='both');var aGoal=(goalSide==='away'||goalSide==='both');capScoreHtml='<span class="lc-divider"></span>'+'<span class="lc-score-h'+(hGoal?' lc-scored':'')+'">'+csp[0].trim()+'</span>'+'<span class="lc-score-sep">-</span>'+'<span class="lc-score-a'+(aGoal?' lc-scored':'')+'">'+csp[1].trim()+'</span>';}else{capScoreHtml='<span class="lc-divider"></span><span class="lc-score-val">'+escLiveHtml(showScore)+'</span>';}}
var deskLiveCap='<div class="live-capsule live-capsule-desk'+capGoalCls+'">'+'<span class="lc-dot"></span>'+'<span class="lc-min">'+capMinText+'</span>'+
capScoreHtml+'</div>';var _liveFavTd=_buildLiveFavCell(m);rowsHtml+='<tr class="live-row"'+_liveMkAttr+' '+onclickAttr+'>'+
_liveFavTd+'<td class="match-date">'+deskLiveCap+'</td>'+'<td class="match-league" title="'+escLiveHtml(m.league)+'">'+escLiveHtml(m.league)+'</td>'+'<td class="match-teams">'+escLiveHtml(m.home_team)+'<span class="vs">-</span>'+escLiveHtml(m.away_team)+'</td>'+'<td class="mw-outcomes-cell" colspan="3"><div class="mw-grid mw-grid-3">'+(_isTestLive?(_lgB+_lgB+_lgB):(b1+bX+b2))+'</div></td>'+'<td class="volume-cell">'+formatLiveVol(vol)+'</td></tr>';cardsHtml+=_liveMobileCard(m,'1x2',onclickAttr,goalSide);}else{var ou=_liveGetOu(m,ouLine);var volOU=_liveCalcVolOU(ou);var bU=_liveMwBlock(_t('app.dyn.alt','Alt'),ou['U']);var bO=_liveMwBlock('Ust',ou['O']);var capGoalClsOU=goalSide?' lc-goal':'';var capMinTextOU=goalSide?'GOL!':escLiveHtml(matchMin);var capScoreHtmlOU='';if(showScore){var cspOU=showScore.split('-');if(cspOU.length===2&&goalSide){var hGoalOU=(goalSide==='home'||goalSide==='both');var aGoalOU=(goalSide==='away'||goalSide==='both');capScoreHtmlOU='<span class="lc-divider"></span>'+'<span class="lc-score-h'+(hGoalOU?' lc-scored':'')+'">'+cspOU[0].trim()+'</span>'+'<span class="lc-score-sep">-</span>'+'<span class="lc-score-a'+(aGoalOU?' lc-scored':'')+'">'+cspOU[1].trim()+'</span>';}else{capScoreHtmlOU='<span class="lc-divider"></span><span class="lc-score-val">'+escLiveHtml(showScore)+'</span>';}}
var deskLiveCapOU='<div class="live-capsule live-capsule-desk'+capGoalClsOU+'">'+'<span class="lc-dot"></span>'+'<span class="lc-min">'+capMinTextOU+'</span>'+
capScoreHtmlOU+'</div>';var _liveFavTdOU=_buildLiveFavCell(m);rowsHtml+='<tr class="live-row"'+_liveMkAttr+' '+onclickAttr+'>'+
_liveFavTdOU+'<td class="match-date">'+deskLiveCapOU+'</td>'+'<td class="match-league" title="'+escLiveHtml(m.league)+'">'+escLiveHtml(m.league)+'</td>'+'<td class="match-teams">'+escLiveHtml(m.home_team)+'<span class="vs">-</span>'+escLiveHtml(m.away_team)+'</td>'+'<td class="mw-outcomes-cell" colspan="2"><div class="mw-grid mw-grid-2">'+(_isTestLive?(_lgB+_lgB):(bU+bO))+'</div></td>'+'<td class="volume-cell">'+formatLiveVol(volOU)+'</td></tr>';cardsHtml+=_liveMobileCard(m,ouLine,onclickAttr,goalSide);}}
if(tbody)tbody.innerHTML=rowsHtml;if(cardList)cardList.innerHTML=cardsHtml;document.querySelectorAll('.goal-pop').forEach(function(el){el.addEventListener('animationend',function(){el.classList.remove('goal-pop');},{once:true});});document.querySelectorAll('.goal-flash-card').forEach(function(el){el.addEventListener('animationend',function(){el.classList.remove('goal-flash-card');},{once:true});});document.querySelectorAll('.dk-cell-inner[data-goal-side]').forEach(function(cell){_startGoalTakeover(cell);});document.querySelectorAll('.live-min-badge[data-goal-min]').forEach(function(el){var realMin=el.getAttribute('data-goal-min');setTimeout(function(){if(el.parentNode){el.textContent=realMin;el.removeAttribute('data-goal-min');}},12000);});var mc=document.getElementById('matchCount');if(mc)mc.textContent=sorted.length;if(_favFilterActive)setTimeout(function(){_applyFavoritesFilter();},10);}
function _startGoalTakeover(cell){var goalSide=cell.getAttribute('data-goal-side');var oldScore=cell.getAttribute('data-old-score')||'0-0';var newScore=cell.getAttribute('data-new-score')||'0-0';var realMin=cell.getAttribute('data-real-min')||'';cell.classList.add('goal-takeover');var golEl=document.createElement('div');golEl.className='goal-takeover-text';golEl.textContent='GOL!';cell.appendChild(golEl);setTimeout(function(){if(!cell.parentNode)return;if(golEl.parentNode)golEl.remove();var oldParts=oldScore.split('-');var newParts=newScore.split('-');var oh=oldParts.length===2?oldParts[0].trim():'0';var oa=oldParts.length===2?oldParts[1].trim():'0';var nh=newParts.length===2?newParts[0].trim():'0';var na=newParts.length===2?newParts[1].trim():'0';var scoreEl=document.createElement('div');scoreEl.className='goal-takeover-score';var hClass=(oh!==nh)?' slide-up':'';var aClass=(oa!==na)?' slide-up':'';scoreEl.innerHTML='<span class="score-digit'+hClass+'">'+nh+'</span>'+'<span style="margin:0 2px;">-</span>'+'<span class="score-digit'+aClass+'">'+na+'</span>';cell.appendChild(scoreEl);setTimeout(function(){if(!cell.parentNode)return;cell.classList.remove('goal-takeover');if(scoreEl.parentNode)scoreEl.remove();cell.removeAttribute('data-goal-side');cell.removeAttribute('data-old-score');cell.removeAttribute('data-new-score');cell.removeAttribute('data-real-min');},6000);},6000);}
function _calcLiveMatchMin(m){if(m.status==='ft')return'MS';var rawMin=(m.minute||'').trim();if(!rawMin){if(m.kickoff_utc){var ko=new Date(m.kickoff_utc);if(!isNaN(ko.getTime())){var diff=Math.floor((Date.now()-ko.getTime())/60000);if(diff>=0&&diff<=130)return diff+"'";}}
return'';}
var upper=rawMin.toUpperCase();if(upper==='FT')return'MS';var markers=['HT','1H','2H','ET','PEN'];for(var k=0;k<markers.length;k++){if(upper===markers[k])return markers[k];}
var stoppage=rawMin.match(/^(\d{1,3})\+(\d{1,2})'?$/);if(stoppage){return stoppage[1]+'+'+stoppage[2]+"'";}
if(/^\d{1,3}'?$/.test(rawMin)){var n=parseInt(rawMin,10);if(n>=0&&n<=130){return n+"'";}}
if(/\d{1,2}:\d{2}/.test(rawMin))return'';return escLiveHtml(rawMin);}
function _liveMwBlock(label,d){if(!d)return renderMoneywayBlock(label,0,'-','');return renderMoneywayBlock(label,d.share||0,d.odds||'-',d.volume||'');}
function _liveMobileCard(m,marketOrLine,onclickAttr,goalSide){var is1x2=(marketOrLine==='1x2');var cardCls='match-card odds-card moneyway-card'+(goalSide?' goal-flash-card':'');var _lmk=_getMatchKey(m);var _lmkIsFav=_userFavorites.has(_lmk);var _lmkFc=_favCounts[_lmk]||0;var html='<div class="'+cardCls+'" data-matchkey="'+_lmk.replace(/"/g,'&quot;')+'" '+onclickAttr+'>';html+=_mobileFavLine(_lmk,_lmkIsFav,_lmkFc);html+='<div class="odds-card-header">';var cardMin=_calcLiveMatchMin(m);var cardScore=m.score?escLiveHtml(m.score):(cardMin==='MS'?'-':'');var liveCapHtml='';if(cardMin||cardScore){var minDisp=goalSide?'GOL!':cardMin;var scoreDisp='';if(cardScore){var csp=cardScore.split('-');if(csp.length===2&&goalSide){var chCls=goalSide==='home'||goalSide==='both'?' lc-scored':'';var caCls=goalSide==='away'||goalSide==='both'?' lc-scored':'';scoreDisp='<span class="lc-score-h'+chCls+'">'+csp[0].trim()+'</span><span class="lc-score-sep">-</span><span class="lc-score-a'+caCls+'">'+csp[1].trim()+'</span>';}else{scoreDisp='<span class="lc-score-val">'+cardScore+'</span>';}}
var mobCapGoalCls=goalSide?' lc-goal':'';liveCapHtml='<div class="live-capsule'+mobCapGoalCls+'">'+'<span class="lc-dot"></span>'+'<span class="lc-min"'+(goalSide?' data-goal-min="'+cardMin+'"':'')+'>'+minDisp+'</span>'+
(scoreDisp?'<span class="lc-divider"></span>'+scoreDisp:'')+'</div>';}
html+='<div class="odds-card-teams">'+escLiveHtml(m.home_team)+' \u2013 '+escLiveHtml(m.away_team)+'</div>';var vol=0;if(is1x2){vol=_liveCalcVol1x2(m);}else{var ou=_liveGetOu(m,marketOrLine);vol=_liveCalcVolOU(ou);}
var _isTestLc=(window.userPlan==='test');var _lcLockSvg='<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#4a5068" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>';var _lcLock='<div class="test-lock-cell test-lock-mob">'+_lcLockSvg+'</div>';html+='<div class="odds-card-volume">'+formatLiveVol(vol)+'</div>';html+='</div>';html+='<div class="odds-card-meta"><span>'+escLiveHtml(m.league)+'</span>'+liveCapHtml+'</div>';if(is1x2){var o=m.odds||{};html+='<div class="odds-card-row three">';if(_isTestLc){html+=_lcLock+_lcLock+_lcLock;}else{html+=_liveMobileBlock('1',o['1'],vol);html+=_liveMobileBlock('X',o['X'],vol);html+=_liveMobileBlock('2',o['2'],vol);}
html+='</div>';}else{var ouD=_liveGetOu(m,marketOrLine);var ouVol=_liveCalcVolOU(ouD);html+='<div class="odds-card-row two">';if(_isTestLc){html+=_lcLock+_lcLock;}else{html+=_liveMobileBlock(_t('app.dyn.alt','Alt'),ouD['U'],ouVol);html+=_liveMobileBlock('Ust',ouD['O'],ouVol);}
html+='</div>';}
html+='</div>';return html;}
function _liveMobileBlock(label,d,totalVol){var odds='-';if(d&&d.odds){odds=d.odds>=100?d.odds.toFixed(0):d.odds.toFixed(2);}
var pct='';var moneyStr='';if(d&&d.share!==null&&d.share!==undefined){var pn=parseFloat(String(d.share));if(!isNaN(pn)){pct=pn.toFixed(0)+'%';if(totalVol&&totalVol>0){var bm=totalVol*pn/100;moneyStr=bm>=1000000?'£'+(bm/1000000).toFixed(1)+'M':bm>=1000?'£'+(bm/1000).toFixed(1)+'k':'£'+Math.round(bm);}}}
return'<div class="odds-block mw-block">'+'<div class="odds-block-label">'+label+'</div>'+'<div class="ob-data-row">'+'<span class="ob-odds">'+odds+'</span>'+
(moneyStr?'<span class="ob-money">'+moneyStr+'</span>':'')+
(pct?'<span class="ob-pct">'+pct+'</span>':'')+'</div>'+'</div>';}
async function openLiveDetail(hash,home,away){_openLiveInMainModal(hash,home,away);}
async function _openLiveInMainModal(hash,home,away){var match=null;var matchIdx=-1;var usedSource='filtered';var homeLow=(home||'').toLowerCase().trim();var awayLow=(away||'').toLowerCase().trim();function _fuzzySearch(arr,label){for(var i=0;i<arr.length;i++){var mh=(arr[i].home_team||'').toLowerCase().trim();var ma=(arr[i].away_team||'').toLowerCase().trim();if(mh===homeLow&&ma===awayLow){return{m:arr[i],idx:i};}
if((mh.includes(homeLow)||homeLow.includes(mh))&&(ma.includes(awayLow)||awayLow.includes(ma))){void 0;return{m:arr[i],idx:i};}}
return null;}
var fArr=(typeof filteredMatches!=='undefined'&&filteredMatches.length>0)?filteredMatches:[];var mArr=(typeof matches!=='undefined'&&matches.length>0)?matches:[];void 0;var res=_fuzzySearch(fArr,'filteredMatches');if(res){match=res.m;matchIdx=res.idx;usedSource='filtered';}
if(!match&&mArr.length>fArr.length){res=_fuzzySearch(mArr,'matches');if(res){match=res.m;matchIdx=res.idx;usedSource='all';}}
if(match&&matchIdx>=0){if(usedSource==='all'&&typeof matches!=='undefined'){void 0;filteredMatches.push(match);matchIdx=filteredMatches.length-1;}
void 0;await openMatchModal(matchIdx);}else{void 0;await openMatchModalFromAPI(home,away,'','');}
setTimeout(function(){var liveTab=document.getElementById('modalLiveTab');if(liveTab&&liveTab.style.display!=='none'){switchMobileTab('live');}else{var waitCount=0;var waitInt=setInterval(function(){waitCount++;var lt=document.getElementById('modalLiveTab');if(lt&&lt.style.display!=='none'){clearInterval(waitInt);switchMobileTab('live');}else if(waitCount>20){clearInterval(waitInt);}},300);}},200);}
function _buildDetailTabs(snapshots){var tabsEl=document.getElementById('liveDetailTabs');var lines={};for(var i=0;i<snapshots.length;i++){var ols=snapshots[i].ou_lines||{};for(var k in ols){lines[k]=true;}}
var sortedLines=Object.keys(lines).sort(function(a,b){return parseFloat(a)-parseFloat(b);});var html='<button class="live-dtab'+(_liveDetailMarket==='1x2'?' active':'')+'" onclick="setLiveDetailMarket(\'1x2\')">1X2</button>';for(var j=0;j<sortedLines.length;j++){var ln=sortedLines[j];var mk='ou'+ln;html+='<button class="live-dtab'+(_liveDetailMarket===mk?' active':'')+'" onclick="setLiveDetailMarket(\''+mk+'\')">'+escLiveHtml(ln)+'</button>';}
tabsEl.innerHTML=html;}
function setLiveDetailMarket(market){_liveDetailMarket=market;document.querySelectorAll('.live-dtab').forEach(function(b){b.classList.toggle('active',false);});var label=market==='1x2'?'1X2':market.replace('ou','');document.querySelectorAll('.live-dtab').forEach(function(b){if((market==='1x2'&&b.textContent==='1X2')||(market!=='1x2'&&b.textContent===label)){b.classList.add('active');}});if(_liveDetailData)renderLiveDetail(_liveDetailData,market);}
function closeLiveDetail(){document.getElementById('liveDetailModal').style.display='none';_liveDetailData=null;}
function _minuteToNum(m){if(m===null||m===undefined||m==='')return-1;var s=String(m).replace(/'/g,'').trim();if(s==='HT')return 45.5;if(s==='FT')return 120;if(s==='ET')return 105;if(s==='PEN')return 115;var stop=s.match(/^(\d+)\+(\d+)$/);if(stop)return parseInt(stop[1])+parseInt(stop[2])*0.01;var n=parseInt(s);return isNaN(n)?-1:n;}
function renderLiveDetail(snapshots,market){var body=document.getElementById('liveDetailBody');if(!snapshots||snapshots.length===0){body.innerHTML='<div class="live-loading">'+_t('app.live.henuz_periyot','Henüz periyot verisi yok')+'</div>';return;}
snapshots=snapshots.slice().sort(function(a,b){var am=_minuteToNum(a.minute),bm=_minuteToNum(b.minute);if(am!==bm)return bm-am;return(a.snapshot_at||'')>(b.snapshot_at||'')?-1:1;});var is1x2=(market==='1x2');var ouLine=is1x2?'':market.replace('ou','');var sels=is1x2?['1','X','2']:['U','O'];var selLabels=is1x2?['1','X','2']:[escLiveHtml(ouLine)+' '+_t('app.tbl.alt','ALT'),escLiveHtml(ouLine)+' '+_t('app.tbl.over','ÜST')];var colsPerSel=3;var html='<div class="live-detail-table-wrap"><table class="live-period-table">';html+='<thead>';html+='<tr class="lpt-group-row">';html+='<th rowspan="2" class="lpt-dkskor-th"><span class="lpt-th-main">'+_t('app.live.dk','DK')+'</span><span class="lpt-th-sub">'+_t('app.live.skor','SKOR')+'</span></th>';for(var g=0;g<sels.length;g++){html+='<th colspan="'+colsPerSel+'" class="lpt-group-th">'+selLabels[g]+'</th>';}
html+='</tr>';html+='<tr class="lpt-col-row">';for(var h=0;h<sels.length;h++){html+='<th class="lpt-dual-th'+(h>0?' lpt-sel-divider':'')+'"><span class="lpt-th-main">'+_t('app.live.oran','ORAN')+'</span><span class="lpt-th-sub">'+_t('app.live.oran_degisim','Oran değişim')+'</span></th>';html+='<th class="lpt-dual-th"><span class="lpt-th-main">VOLUME</span><span class="lpt-th-sub">'+_t('app.live.gelen_para','Gelen para')+'</span></th>';html+='<th class="lpt-dual-th"><span class="lpt-th-main">'+_t('app.live.yuzde','YÜZDE')+'</span><span class="lpt-th-sub">'+_t('app.live.pct_degisimi','%değişimi')+'</span></th>';}
html+='</tr>';html+='</thead><tbody>';var totals={};sels.forEach(function(sel){totals[sel]=0;});for(var i=0;i<snapshots.length;i++){var s=snapshots[i];var prevS=(i<snapshots.length-1)?snapshots[i+1]:null;var minVal=s.minute;var minStr='-';if(minVal!==''&&minVal!==null&&minVal!==undefined){var mv=String(minVal);minStr=mv.endsWith("'")?mv:mv+"'";}
var scoreStr=s.score||'-';html+='<tr>';html+='<td class="period-dk-skor"><span class="dk-val">'+escLiveHtml(minStr)+'</span><span class="skor-val">'+escLiveHtml(scoreStr)+'</span></td>';var dataGroup=is1x2?(s['1x2']||{}):((s.ou_lines||{})[ouLine]||{});var prevDataGroup=prevS?(is1x2?(prevS['1x2']||{}):((prevS.ou_lines||{})[ouLine]||{})):null;for(var j=0;j<sels.length;j++){var sel=sels[j];var sd=dataGroup[sel]||{};var odds=(sd.odds!==undefined&&sd.odds!==null)?parseFloat(sd.odds):null;var pct=sd.share||0;var vol=sd.volume||0;totals[sel]+=vol;var oddsStr=odds!==null?odds.toFixed(2):'-';var pctStr=pct?pct.toFixed(1)+'%':'-';var deltaHtml='<span class="period-delta-neutral">-</span>';if(prevDataGroup&&odds!==null){var prevOdds=(prevDataGroup[sel]||{}).odds;if(prevOdds!==undefined&&prevOdds!==null){var delta=odds-parseFloat(prevOdds);if(Math.abs(delta)>=0.005){var dSign=delta>0?'+':'';var dCls=delta>0?'period-delta-up':'period-delta-down';deltaHtml='<span class="'+dCls+'">'+dSign+delta.toFixed(2)+'</span>';}}}
var prevPct=0;if(prevDataGroup){prevPct=(prevDataGroup[sel]||{}).share||0;}
var pctDelta=pct-prevPct;var pctDeltaHtml='<span class="period-delta-neutral">-</span>';if(prevS&&Math.abs(pctDelta)>=0.05){var pdSign=pctDelta>0?'+':'';pctDeltaHtml='<span class="pct-delta">'+pdSign+pctDelta.toFixed(1)+'%</span>';}
var prevVol=0;if(prevDataGroup){prevVol=(prevDataGroup[sel]||{}).volume||0;}
var volDiff=vol-prevVol;var volDiffStr='-';var volDiffHasVal=false;if(prevS&&volDiff!==0){volDiffStr=formatLiveVol(volDiff);volDiffHasVal=true;}
var hi=pct>=50;var divCls=j>0?' lpt-sel-divider':'';html+='<td class="period-dual'+divCls+'"><span class="dual-main period-odds">'+oddsStr+'</span><span class="dual-sub">'+deltaHtml+'</span></td>';html+='<td class="period-dual"><span class="dual-main period-vol">'+(vol?formatLiveVol(vol):'-')+'</span><span class="dual-sub vol-diff'+(volDiffHasVal?' has-val':'')+'">'+volDiffStr+'</span></td>';html+='<td class="period-dual"><span class="dual-main period-pct '+(hi?'pct-high':'pct-low')+'">'+pctStr+'</span><span class="dual-sub">'+pctDeltaHtml+'</span></td>';}
html+='</tr>';}
html+='</tbody></table></div>';body.innerHTML=html;}
window._sxfModalLiveRuntimePromise = window._sxfModalLiveRuntimePromise || null;
function _getModalLiveRuntimeUrl() {
    try {
        const scripts = document.getElementsByTagName('script');
        for (let i = scripts.length - 1; i >= 0; i--) {
            const src = scripts[i].src || '';
            if (src.indexOf('/static/js/app.js') !== -1) {
                const queryIndex = src.indexOf('?');
                const query = queryIndex >= 0 ? src.slice(queryIndex) : '';
                return '/static/js/modal-live.js' + query;
            }
        }
    } catch (e) {}
    return '/static/js/modal-live.js';
}

function loadModalLiveRuntime() {
    if (typeof window.__sxfCheckModalLiveDataImpl === 'function') return Promise.resolve();
    if (window._sxfModalLiveRuntimePromise) return window._sxfModalLiveRuntimePromise;

    window._sxfModalLiveRuntimePromise = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = _getModalLiveRuntimeUrl();
        script.async = true;
        script.onload = () => {
            if (typeof window.__sxfCheckModalLiveDataImpl === 'function') {
                resolve();
                return;
            }
            window._sxfModalLiveRuntimePromise = null;
            reject(new Error('Modal live runtime loaded without implementation'));
        };
        script.onerror = () => {
            window._sxfModalLiveRuntimePromise = null;
            reject(new Error('Modal live runtime failed to load'));
        };
        document.head.appendChild(script);
    });
    return window._sxfModalLiveRuntimePromise;
}

async function _checkModalLiveData(...args) {
    try {
        await loadModalLiveRuntime();
        return await window.__sxfCheckModalLiveDataImpl(...args);
    } catch (e) {
        console.error('[Modal] Live runtime load error:', e);
    }
}




