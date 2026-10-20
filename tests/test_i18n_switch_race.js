// Real i18n.js runtime: rapid language changes must commit only the latest fetch.
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const code=fs.readFileSync(require('node:path').join(__dirname,'../static/js/i18n.js'),'utf8');
function runtime(startLang='en'){
  const requests={};
  const storage=new Map([['sxf_lang',startLang]]);
  let langAttribute='';
  let changes=[];
  const document={
    readyState:'loading',head:{appendChild(){}},
    documentElement:{setAttribute(name,value){if(name==='lang')langAttribute=value;}},
    getElementById(){return {};},createElement(){return {setAttribute(){}};},
    addEventListener(){},querySelectorAll(){return [];},querySelector(){return null}
  };
  const window={location:{href:'https://sxf-preview.test/app'},dispatchEvent(event){changes.push(event.detail.lang)}};
  const api={window,document,localStorage:{
    getItem(key){return storage.get(key)||null;},
    setItem(key,value){storage.set(key,value)}
  }, CustomEvent:class{constructor(type,options){this.type=type;this.detail=options.detail}},
  fetch(url){
    const lang=url.match(/\/static\/i18n\/([a-z]+)\.json/)[1];
    return new Promise((resolve,reject)=>{requests[lang]={resolve,reject}});
  },URL,console,setTimeout(){},clearTimeout(){},MutationObserver:undefined};
  vm.runInNewContext(code,api,{filename:'i18n.js'});
  async function done(lang,value){
    requests[lang].resolve({ok:true,json:async()=>({app:{v4:{title:value}}})});
    await new Promise(resolve=>setImmediate(resolve));
  }
  return {window,requests,done,changes,getLocale:()=>langAttribute,storage};
}
test('latest selected locale wins even if startup and other fetches finish later',async()=>{
  const q=runtime('en');
  const german=q.window.SXFI18n.set('de');
  const italian=q.window.SXFI18n.set('it');
  await q.done('it','Analisi');
  await italian;
  await q.done('de','Analysen');
  await german;
  await q.done('en','Analyses');
  assert.equal(q.window.SXFI18n.current(),'it');
  assert.equal(q.window.SXFI18n.t('app.v4.title'),'Analisi');
  assert.equal(q.getLocale(),'it');
  assert.equal(q.storage.get('sxf_lang'),'it');
  assert.deepEqual(q.changes,['it']);
});
test('failed initial locale must not override a later successful selection',async()=>{
  const q=runtime('tr');
  const italian=q.window.SXFI18n.set('it');
  await q.done('it','Analisi');
  await italian;
  q.requests.tr.reject(Error('bad initial locale'));
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(q.window.SXFI18n.current(),'it');
  assert.equal(q.requests.en,undefined);
});
