// Check active deferred modules with the actual runtime and seven locale dictionaries.
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const test=require('node:test');
const assert=require('node:assert/strict');
const root=path.join(__dirname,'..');
const live=fs.readFileSync(path.join(root,'static/js/live-tab.js'),'utf8');
const alarm=fs.readFileSync(path.join(root,'static/js/alarm-sidebar.js'),'utf8');
const langs=['tr','en','de','fr','nl','it','es'];
const dictionaries=Object.fromEntries(langs.map(l=>[l,JSON.parse(fs.readFileSync(path.join(root,'static/i18n',l+'.json'),'utf8'))]));
const lookup=(lang,key)=>key.split('.').reduce((value,part)=>value?.[part],dictionaries[lang]);

test('Live no-match panel re-renders into all seven languages without network',()=>{
  let language='tr';
  const handlers={};
  const label={textContent:''}, tbody={innerHTML:''},cardList={innerHTML:''},thead={innerHTML:''};
  const doc={
    getElementById(id){return {matchCountLabel:label,matchesTableBody:tbody,matchCardList:cardList,matchCount:{textContent:''}}[id]||null},
    querySelector(sel){if(sel==='.matches-table')return {querySelector(q){return q==='thead'?thead:null}};return null}
  };
  const ctx={
    window:{userPlan:'pro',addEventListener(name,fn){handlers[name]=fn}},
    document:doc,
    _liveMode:true,_liveData:[],_liveDetailData:null,
    _t(key,fb){return lookup(language,key)||fb},
    console,setTimeout(){},clearTimeout(){},
  };
  vm.runInNewContext(live,ctx);
  assert.equal(typeof handlers['i18n:change'],'function');
  for(let l of langs){
    language=l;
    handlers['i18n:change']();
    assert.equal(label.textContent.trim(),lookup(l,'app.live.canli_maclar').trim());
    assert.ok(cardList.innerHTML.includes(lookup(l,'app.live.bos')),l);
    assert.ok(thead.innerHTML.includes(lookup(l,'app.live.bos_tablo')),l);
  }
});

test('Alarm list empty state switches across seven languages with preserved cached filter',()=>{
  let language='tr';
  const handlers={};
  const list={innerHTML:'',isConnected:true};
  const ctx={
    window:{addEventListener(name,fn){handlers[name]=fn}},
    document:{getElementById(id){return id==='alarmsList'?list:null}},
    groupedAlarmsData:[],currentAlarmFilter:'all',currentAlarmDateFilter:'none',
    alarmSearchQuery:'',alarmsDisplayCount:10,
    _t(key,fb){return lookup(language,key)||fb},
    console,setTimeout(){},clearTimeout(){},
  };
  vm.runInNewContext(alarm,ctx);
  assert.equal(typeof handlers['i18n:change'],'function');
  for(let l of langs){
    language=l;
    handlers['i18n:change']();
    assert.ok(list.innerHTML.includes(lookup(l,'app.dyn.henuz_alarm_yok')),l);
  }
});
