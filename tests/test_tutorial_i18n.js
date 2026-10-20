// The guided onboarding tooltip is localized at display time on desktop/mobile.
// Test the real localization helper extracted from both runtime and source files.
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const languages=['tr','en','de','fr','nl','it','es'];
const catalogs=Object.fromEntries(languages.map(l=>[l,JSON.parse(
 fs.readFileSync(path.join(root,'static/i18n',l+'.json'),'utf8'))]));
for(const file of ['inline.js','inline.js.src']){
 test('tutorial tooltip uses 7 locales for all desktop and mobile steps: '+file,()=>{
  const code=fs.readFileSync(path.join(root,'static/js',file),'utf8');
  const begin=code.indexOf('var tutorialTitleDesktopKeys=');
  const end=code.indexOf('var tutorialCurrentStep',begin);
  assert(begin>0&&end>begin,'actual runtime helper present');
  const snippet=code.slice(begin,end);
  let lang='en',mobile=false;
  const ctx={window:{addEventListener(){}},isMobileView:()=>mobile,
    _t(key,fallback){return key.split('.').reduce((obj,p)=>obj?.[p],catalogs[lang])??fallback}};
  vm.runInNewContext(snippet,ctx,{filename:file});
  for(const language of languages){
   lang=language;
   for(const mode of [false,true]){
    mobile=mode;
    const titleKeys=mode?ctx.tutorialTitleMobileKeys:ctx.tutorialTitleDesktopKeys;
    const descKeys=mode?ctx.tutorialDescMobileKeys:ctx.tutorialDescDesktopKeys;
    assert.equal(titleKeys.length,mode?8:9);
    assert.equal(descKeys.length,titleKeys.length);
    for(let i=0;i<titleKeys.length;i++){
     const rendered=ctx.translatedTutorialStep(i,{title:'missing title',desc:'missing description'});
     assert.equal(rendered.title,catalogs[lang].app.tutorial[titleKeys[i]]);
     assert.equal(rendered.desc,catalogs[lang].app.tutorial[descKeys[i]]);
     assert.notEqual(rendered.title,'missing title');
     assert.notEqual(rendered.desc,'missing description');
    }
   }
  }
  assert(code.includes("window.addEventListener('i18n:change',function()"),"active tooltip must respond to language switches");
  assert(code.includes("translatedTutorialStep(index,step)"),"render uses selected locale each time");
 });
}
