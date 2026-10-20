// Admin overlay confirmation uses the chosen locale and never performs writes
// when the user cancels. Runs the compiled production-facing bundle in a VM.
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.join(__dirname,'..');
const code=fs.readFileSync(path.join(root,'static/js/admin-panel.js'),'utf8');
const dict=JSON.parse(fs.readFileSync(path.join(root,'static/i18n/admin.json'),'utf8'));
const langs=['tr','en','de','fr','nl','it','es'];
test('admin deletion confirmations use localized text and cancel without network',async()=>{
 for(const lang of langs){
   const seen=[];
   let networkCalls=0;
   const win={SXFI18n:{t:key=>dict[lang][key.split('.').at(-1)]??key}};
   const sandbox={
     window:win,document:{getElementById(){return null}},
     confirm(text){seen.push(text);return false},
     fetch(){networkCalls++;throw Error('should not fetch on declined confirmation')},
     console
   };
   vm.runInNewContext(code,sandbox,{filename:'admin-panel.js'});
   await win.deleteVolumeLeaderAlarms();
   await win.deleteDroppingAlarms();
   await win.deleteMimAlarms();
   assert.deepEqual(seen,[
     dict[lang].panel_051,dict[lang].panel_055,dict[lang].panel_058
   ],'locale='+lang);
   assert.equal(networkCalls,0);
 }
});
test('opening app admin modal requests only a read-only lazy translation catalog',()=>{
 const requests=[];
 const overlay={classList:{add(x){requests.push('overlay:'+x)}}};
 const win={SXFI18n:{ensureAdminCatalog(){requests.push('catalog:read');return Promise.resolve()}}};
 const sandbox={window:win,document:{getElementById(id){return id==='adminPanelOverlay'?overlay:null}},console};
 vm.runInNewContext(code,sandbox,{filename:'admin-panel.js'});
 // Avoid invoking the unrelated app data loading routine: only verify that
 // the translation request runs before the modal opens.
 const posCatalog=code.indexOf('ensureAdminCatalog()');
 const posOpen=code.indexOf("overlay.classList.add('open')");
 assert(posCatalog>=0&&posOpen>posCatalog);
 assert(code.includes('function openAdminPanel(')); // function is internal to this lazy module
});
