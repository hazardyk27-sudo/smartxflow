(function(){
function sxfAdminT(key, fallback) {
  var i18n = window.SXFI18n;
  var full = 'app.adminui.' + key;
  var translated = i18n && typeof i18n.t === 'function' ? i18n.t(full) : null;
  return translated && translated !== full ? translated : fallback;
}
function openAdminPanel(){const overlay=document.getElementById('adminPanelOverlay');if(overlay){if (window.SXFI18n && window.SXFI18n.ensureAdminCatalog) window.SXFI18n.ensureAdminCatalog();overlay.classList.add('open');loadAdminVolumeLeaderData();}}
function closeAdminPanel(){const overlay=document.getElementById('adminPanelOverlay');if(overlay){overlay.classList.remove('open');}}
let currentAdminTab='volumeleader';function switchAdminTab(tab){currentAdminTab=tab;document.querySelectorAll('.admin-tab').forEach(t=>{t.classList.toggle('active',t.dataset.tab===tab);});if(tab==='volumeleader'){loadAdminVolumeLeaderData();}else if(tab==='dropping'){loadAdminDroppingData();}else if(tab==='mim'){loadAdminMimData();}}
async function loadAdminVolumeLeaderData(){const body=document.getElementById('adminPanelBody');if(!body)return;
    if (window.SXFI18n && window.SXFI18n.ensureAdminCatalog) await window.SXFI18n.ensureAdminCatalog();body.innerHTML='<div data-i18n="app.j.loading" style="text-align:center; padding:40px; color:#94a3b8;">Yükleniyor...</div>';try{const[configRes,statusRes]=await Promise.all([fetch('/api/volumeleader/config'),fetch('/api/volumeleader/status')]);const config=configRes.ok?await configRes.json():{};await fetchAlarmsBatch();const alarms=getCachedAlarmsByType('volumeleader');const status=statusRes.ok?await statusRes.json():{};let html=`
            <div class="admin-section">
                <h3 data-i18n="app.adminui.panel_001" style="color:#06b6d4; margin-bottom:16px;">⚡ Hacim Lideri Değişti - Ayarlar</h3>
                
                <div class="admin-config-form">
                    <div class="config-row">
                        <label data-i18n="app.adminui.panel_002">Lider Eşiği (%)</label>
                        <input type="number" id="vlLeaderThreshold" value="${config.leader_threshold || 50}" min="40" max="70" step="1">
                        <span data-i18n="app.adminui.panel_003" class="config-hint">Minimum pay oranı (varsayılan: %50)</span>
                    </div>
                    
                    <div class="config-row">
                        <label data-i18n="app.adminui.panel_004">Min. Hacim 1X2 (£)</label>
                        <input type="number" id="vlMinVolume1x2" value="${config.min_volume_1x2 || 5000}" min="1000" step="500">
                    </div>
                    
                    <div class="config-row">
                        <label data-i18n="app.adminui.panel_005">Min. Hacim O/U (£)</label>
                        <input type="number" id="vlMinVolumeOu25" value="${config.min_volume_ou25 || 2000}" min="500" step="250">
                    </div>
                    
                    <div class="config-row">
                        <label data-i18n="app.adminui.panel_006">Min. Hacim BTTS (£)</label>
                        <input type="number" id="vlMinVolumeBtts" value="${config.min_volume_btts || 1000}" min="250" step="250">
                    </div>
                    
                    <div class="config-actions">
                        <button data-i18n="app.adminui.panel_007" class="admin-btn primary" onclick="saveVolumeLeaderConfig()">💾 Ayarları Kaydet</button>
                        <button data-i18n="app.adminui.panel_008" class="admin-btn success" onclick="calculateVolumeLeaderAlarms()" id="vlCalcBtn">🔍 Hesapla</button>
                        <button data-i18n="app.adminui.panel_009" class="admin-btn danger" onclick="deleteVolumeLeaderAlarms()">🗑️ Alarmları Sil</button>
                    </div>
                    
                    <div id="vlCalcStatus" style="display:none; margin-top:12px; padding:8px; background:#141719; border-radius:4px; color:#7d848c; font-size:12px;"></div>
                </div>
            </div>
            
            <div class="admin-section" style="margin-top:24px;">
                <h3 style="color:#06b6d4; margin-bottom:16px;">📊 ${sxfAdminT('panel_dyn_alarms','Alarmlar')} (${alarms.length})</h3>
        `;if(alarms.length===0){html+='<div data-i18n="app.adminui.panel_010" class="admin-no-data">Henüz alarm yok. "Hesapla" butonuna tıklayın.</div>';}else{html+=`
                <table class="admin-table">
                    <thead>
                        <tr>
                            <th data-i18n="app.adminui.panel_011">Maç</th>
                            <th data-i18n="app.adminui.panel_012">Market</th>
                            <th data-i18n="app.adminui.panel_013">Eski Lider</th>
                            <th data-i18n="app.adminui.panel_014">Yeni Lider</th>
                            <th data-i18n="app.adminui.panel_015">Toplam Hacim</th>
                            <th data-i18n="app.adminui.panel_016">Alarm Zamanı</th>
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
html+='</div>';body.innerHTML=html;
        if (window.SXFI18n) window.SXFI18n.apply();}catch(e){console.error('Volume Leader admin veri hatası:',e);body.innerHTML='<div data-i18n="app.adminui.panel_017" class="admin-no-data">Veri yüklenirken hata oluştu.</div>';}}
async function saveVolumeLeaderConfig(){const config={leader_threshold:parseInt(document.getElementById('vlLeaderThreshold').value)||50,min_volume_1x2:parseInt(document.getElementById('vlMinVolume1x2').value)||5000,min_volume_ou25:parseInt(document.getElementById('vlMinVolumeOu25').value)||2000,min_volume_btts:parseInt(document.getElementById('vlMinVolumeBtts').value)||1000};try{const res=await fetch('/api/volumeleader/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(config)});if(res.ok){showToast(sxfAdminT('panel_046','Ayarlar kaydedildi'),'success');}else{showToast(sxfAdminT('panel_047','Kaydetme hatası'),'error');}}catch(e){showToast(sxfAdminT('panel_048','Bağlantı hatası'),'error');}}
async function calculateVolumeLeaderAlarms(){const btn=document.getElementById('vlCalcBtn');const statusDiv=document.getElementById('vlCalcStatus');if(btn)btn.disabled=true;if(statusDiv){statusDiv.style.display='block';statusDiv.textContent=sxfAdminT('panel_049','Hesaplama başlatılıyor...');}
try{const res=await fetch('/api/volumeleader/calculate',{method:'POST'});const data=await res.json();if(data.success){showToast(`${data.count} yeni alarm bulundu!`,'success');loadAdminVolumeLeaderData();}else{showToast(data.error||sxfAdminT('panel_050','Hesaplama hatası'),'error');}}catch(e){showToast(sxfAdminT('panel_048','Bağlantı hatası'),'error');}finally{if(btn)btn.disabled=false;}}
async function deleteVolumeLeaderAlarms(){if(!confirm(sxfAdminT('panel_051','Tüm Hacim Lideri alarmlarını silmek istediğinize emin misiniz?')))return;try{const res=await fetch('/api/volumeleader/alarms',{method:'DELETE'});if(res.ok){showToast('Alarmlar silindi','success');loadAdminVolumeLeaderData();}else{showToast(sxfAdminT('panel_052','Silme hatası'),'error');}}catch(e){showToast(sxfAdminT('panel_048','Bağlantı hatası'),'error');}}
async function loadAdminDroppingData(){const body=document.getElementById('adminPanelBody');if(!body)return;
    if (window.SXFI18n && window.SXFI18n.ensureAdminCatalog) await window.SXFI18n.ensureAdminCatalog();body.innerHTML='<div data-i18n="app.j.loading" style="text-align:center; padding:40px; color:#94a3b8;">Yükleniyor...</div>';try{const configRes=await fetch('/api/dropping/config');const config=configRes.ok?await configRes.json():{};await fetchAlarmsBatch();const alarms=getCachedAlarmsByType('dropping');let html=`
            <div class="admin-section">
                <h3 data-i18n="app.adminui.panel_018" style="color:#f85149; margin-bottom:16px;">📉 Dropping Alarm - Max Oran Eşiği</h3>
                <p data-i18n="app.adminui.panel_019" style="color:#7d848c; font-size:12px; margin-bottom:16px;">
                    Açılış oranı bu eşiklerin üzerindeyse dropping alarmı tetiklenmez.
                </p>
                
                <div class="admin-config-form">
                    <div class="config-row">
                        <label data-i18n="app.adminui.panel_020">Max Oran 1X2</label>
                        <input type="number" id="drMaxOdds1x2" value="${config.max_odds_1x2 || 5.0}" min="1.5" max="20" step="0.5">
                        <span data-i18n="app.adminui.panel_021" class="config-hint">1X2 için max açılış oranı (varsayılan: 5.0)</span>
                    </div>
                    
                    <div class="config-row">
                        <label data-i18n="app.adminui.panel_022">Max Oran O/U 2.5</label>
                        <input type="number" id="drMaxOddsOu25" value="${config.max_odds_ou25 || 3.0}" min="1.5" max="10" step="0.25">
                        <span data-i18n="app.adminui.panel_023" class="config-hint">Alt/Üst için max açılış oranı (varsayılan: 3.0)</span>
                    </div>
                    
                    <div class="config-row">
                        <label data-i18n="app.adminui.panel_024">Max Oran BTTS</label>
                        <input type="number" id="drMaxOddsBtts" value="${config.max_odds_btts || 3.0}" min="1.5" max="10" step="0.25">
                        <span data-i18n="app.adminui.panel_025" class="config-hint">BTTS için max açılış oranı (varsayılan: 3.0)</span>
                    </div>
                    
                    <div style="border-top: 1px solid #2e3238; margin-top: 16px; padding-top: 16px;">
                        <h4 data-i18n="app.adminui.panel_026" style="color:#f85149; margin-bottom:12px; font-size:13px;">📊 Düşüş Yüzde Eşikleri</h4>
                        
                        <div class="config-row">
                            <label data-i18n="app.adminui.panel_027">L1 Min (%)</label>
                            <input type="number" id="drMinDropL1" value="${config.min_drop_l1 || 10}" min="5" max="30" step="1">
                        </div>
                        
                        <div class="config-row">
                            <label data-i18n="app.adminui.panel_028">L1 Max (%)</label>
                            <input type="number" id="drMaxDropL1" value="${config.max_drop_l1 || 17}" min="5" max="30" step="1">
                        </div>
                        
                        <div class="config-row">
                            <label data-i18n="app.adminui.panel_029">L2 Min (%)</label>
                            <input type="number" id="drMinDropL2" value="${config.min_drop_l2 || 17}" min="10" max="40" step="1">
                        </div>
                        
                        <div class="config-row">
                            <label data-i18n="app.adminui.panel_030">L2 Max (%)</label>
                            <input type="number" id="drMaxDropL2" value="${config.max_drop_l2 || 20}" min="10" max="40" step="1">
                        </div>
                        
                        <div class="config-row">
                            <label data-i18n="app.adminui.panel_031">L3 Min (%)</label>
                            <input type="number" id="drMinDropL3" value="${config.min_drop_l3 || 20}" min="15" max="50" step="1">
                            <span data-i18n="app.adminui.panel_032" class="config-hint">L3 ve üzeri düşüşler</span>
                        </div>
                    </div>
                    
                    <div class="config-actions">
                        <button data-i18n="app.adminui.panel_007" class="admin-btn primary" onclick="saveDroppingConfig()">💾 Ayarları Kaydet</button>
                        <button data-i18n="app.adminui.panel_008" class="admin-btn success" onclick="calculateDroppingAlarms()" id="drCalcBtn">🔍 Hesapla</button>
                        <button data-i18n="app.adminui.panel_009" class="admin-btn danger" onclick="deleteDroppingAlarms()">🗑️ Alarmları Sil</button>
                    </div>
                    
                    <div id="drCalcStatus" style="display:none; margin-top:12px; padding:8px; background:#141719; border-radius:4px; color:#7d848c; font-size:12px;"></div>
                </div>
            </div>
            
            <div class="admin-section" style="margin-top:24px;">
                <h3 style="color:#f85149; margin-bottom:16px;">📊 ${sxfAdminT('panel_dyn_alarms','Alarmlar')} (${alarms.length})</h3>
        `;if(alarms.length===0){html+='<div data-i18n="app.adminui.panel_033" class="admin-no-data">Henüz alarm yok.</div>';}else{html+=`
                <table class="admin-table">
                    <thead>
                        <tr>
                            <th data-i18n="app.adminui.panel_011">Maç</th>
                            <th data-i18n="app.adminui.panel_012">Market</th>
                            <th data-i18n="app.adminui.panel_034">Seviye</th>
                            <th data-i18n="app.adminui.panel_035">Açılış → Güncel</th>
                            <th data-i18n="app.adminui.panel_036">Düşüş %</th>
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
                `;});html+='</tbody></table>';if(alarms.length>30){html+=`<div style="text-align:center; padding:12px; color:#5c636b; font-size:12px;">+${alarms.length - 30} ${sxfAdminT('panel_dyn_more','diğer alarm...')}</div>`;}}
html+='</div>';body.innerHTML=html;
        if (window.SXFI18n) window.SXFI18n.apply();}catch(e){console.error('Dropping admin veri hatası:',e);body.innerHTML='<div data-i18n="app.adminui.panel_017" class="admin-no-data">Veri yüklenirken hata oluştu.</div>';}}
async function saveDroppingConfig(){const config={max_odds_1x2:parseFloat(document.getElementById('drMaxOdds1x2').value)||5.0,max_odds_ou25:parseFloat(document.getElementById('drMaxOddsOu25').value)||3.0,max_odds_btts:parseFloat(document.getElementById('drMaxOddsBtts').value)||3.0,min_drop_l1:parseInt(document.getElementById('drMinDropL1').value)||10,max_drop_l1:parseInt(document.getElementById('drMaxDropL1').value)||17,min_drop_l2:parseInt(document.getElementById('drMinDropL2').value)||17,max_drop_l2:parseInt(document.getElementById('drMaxDropL2').value)||20,min_drop_l3:parseInt(document.getElementById('drMinDropL3').value)||20};try{const res=await fetch('/api/dropping/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(config)});if(res.ok){showToast(sxfAdminT('panel_053','Dropping ayarları kaydedildi'),'success');}else{showToast(sxfAdminT('panel_047','Kaydetme hatası'),'error');}}catch(e){showToast(sxfAdminT('panel_048','Bağlantı hatası'),'error');}}
async function calculateDroppingAlarms(){const btn=document.getElementById('drCalcBtn');const statusDiv=document.getElementById('drCalcStatus');if(btn)btn.disabled=true;if(statusDiv){statusDiv.style.display='block';statusDiv.textContent=sxfAdminT('panel_054','Dropping alarmları hesaplanıyor...');}
try{const res=await fetch('/api/dropping/calculate',{method:'POST'});const data=await res.json();if(data.success){showToast(`${data.count} dropping alarm bulundu!`,'success');loadAdminDroppingData();}else{showToast(data.error||sxfAdminT('panel_050','Hesaplama hatası'),'error');}}catch(e){showToast(sxfAdminT('panel_048','Bağlantı hatası'),'error');}finally{if(btn)btn.disabled=false;}}
async function deleteDroppingAlarms(){if(!confirm(sxfAdminT('panel_055','Tüm Dropping alarmlarını silmek istediğinize emin misiniz?')))return;try{const res=await fetch('/api/dropping/alarms',{method:'DELETE'});if(res.ok){showToast(sxfAdminT('panel_056','Dropping alarmları silindi'),'success');loadAdminDroppingData();}else{showToast(sxfAdminT('panel_052','Silme hatası'),'error');}}catch(e){showToast(sxfAdminT('panel_048','Bağlantı hatası'),'error');}}
async function loadAdminMimData(){const body=document.getElementById('adminPanelBody');if(!body)return;
    if (window.SXFI18n && window.SXFI18n.ensureAdminCatalog) await window.SXFI18n.ensureAdminCatalog();body.innerHTML='<div data-i18n="app.j.loading" style="text-align:center; padding:40px; color:#94a3b8;">Yükleniyor...</div>';try{const configRes=await fetch('/api/mim/config');const config=configRes.ok?await configRes.json():{};await fetchAlarmsBatch();const alarms=getCachedAlarmsByType('mim');let html=`
            <div class="admin-section">
                <h3 data-i18n="app.adminui.panel_037" style="color:#3B82F6; margin-bottom:16px;">💰 MIM (Market Impact Money) - Ayarlar</h3>
                <p data-i18n="app.adminui.panel_038" style="color:#7d848c; font-size:12px; margin-bottom:16px;">
                    MIM alarmı, piyasa etkisini ölçer. Impact değeri ne kadar yüksekse, o seçim için para akışı o kadar güçlüdür.
                </p>
                
                <div class="admin-config-form">
                    <div class="config-row">
                        <label data-i18n="app.adminui.panel_039">Min. Impact Eşiği</label>
                        <input type="number" id="mimMinImpact" value="${config.min_impact_threshold || 0.10}" min="0.01" max="1.0" step="0.01">
                        <span data-i18n="app.adminui.panel_040" class="config-hint">Minimum impact değeri (varsayılan: 0.10)</span>
                    </div>
                    
                    <div class="config-row">
                        <label data-i18n="app.adminui.panel_041">Min. Hacim (£)</label>
                        <input type="number" id="mimMinVolume" value="${config.min_volume || 1000}" min="100" step="100">
                        <span data-i18n="app.adminui.panel_042" class="config-hint">Minimum toplam hacim</span>
                    </div>
                    
                    <div class="config-actions">
                        <button data-i18n="app.adminui.panel_007" class="admin-btn primary" onclick="saveMimConfig()">💾 Ayarları Kaydet</button>
                        <button data-i18n="app.adminui.panel_009" class="admin-btn danger" onclick="deleteMimAlarms()">🗑️ Alarmları Sil</button>
                    </div>
                </div>
            </div>
            
            <div class="admin-section" style="margin-top:24px;">
                <h3 style="color:#3B82F6; margin-bottom:16px;">📊 ${sxfAdminT('panel_dyn_alarms','Alarmlar')} (${alarms.length})</h3>
        `;if(alarms.length===0){html+='<div data-i18n="app.adminui.panel_dyn_no_mim" class="admin-no-data">Henüz MIM alarmı yok.</div>';}else{html+=`
                <table class="admin-table">
                    <thead>
                        <tr>
                            <th data-i18n="app.adminui.panel_011">Maç</th>
                            <th data-i18n="app.adminui.panel_012">Market</th>
                            <th data-i18n="app.adminui.panel_043">Seçim</th>
                            <th data-i18n="app.adminui.panel_034">Seviye</th>
                            <th data-i18n="app.adminui.panel_044">Impact</th>
                            <th data-i18n="app.adminui.panel_045">Hacim</th>
                            <th data-i18n="app.adminui.panel_016">Alarm Zamanı</th>
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
                `;});html+='</tbody></table>';if(alarms.length>50){html+=`<div style="text-align:center; padding:12px; color:#5c636b; font-size:12px;">+${alarms.length - 50} ${sxfAdminT('panel_dyn_more','diğer alarm...')}</div>`;}}
html+='</div>';body.innerHTML=html;
        if (window.SXFI18n) window.SXFI18n.apply();}catch(e){console.error('MIM admin veri hatası:',e);body.innerHTML='<div data-i18n="app.adminui.panel_017" class="admin-no-data">Veri yüklenirken hata oluştu.</div>';}}
async function saveMimConfig(){const config={min_impact_threshold:parseFloat(document.getElementById('mimMinImpact').value)||0.10,min_volume:parseInt(document.getElementById('mimMinVolume').value)||1000};try{const res=await fetch('/api/mim/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(config)});if(res.ok){showToast(sxfAdminT('panel_057','MIM ayarları kaydedildi'),'success');}else{showToast(sxfAdminT('panel_047','Kaydetme hatası'),'error');}}catch(e){showToast(sxfAdminT('panel_048','Bağlantı hatası'),'error');}}
async function deleteMimAlarms(){if(!confirm(sxfAdminT('panel_058','Tüm MIM alarmlarını silmek istediğinize emin misiniz?')))return;try{const res=await fetch('/api/mim/alarms',{method:'DELETE'});if(res.ok){showToast(sxfAdminT('panel_059','MIM alarmları silindi'),'success');invalidateAlarmCache();loadAdminMimData();}else{showToast(sxfAdminT('panel_052','Silme hatası'),'error');}}catch(e){showToast(sxfAdminT('panel_048','Bağlantı hatası'),'error');}}
window.__sxfOpenAdminPanelImpl=openAdminPanel;window.__sxfCloseAdminPanelImpl=closeAdminPanel;window.__sxfSwitchAdminTabImpl=switchAdminTab;window.saveVolumeLeaderConfig=saveVolumeLeaderConfig;window.calculateVolumeLeaderAlarms=calculateVolumeLeaderAlarms;window.deleteVolumeLeaderAlarms=deleteVolumeLeaderAlarms;window.saveDroppingConfig=saveDroppingConfig;window.calculateDroppingAlarms=calculateDroppingAlarms;window.deleteDroppingAlarms=deleteDroppingAlarms;window.saveMimConfig=saveMimConfig;window.deleteMimAlarms=deleteMimAlarms;})();