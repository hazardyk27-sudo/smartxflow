// UI interaction smoke without a browser dependency: real V4 script in a DOM shim.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const js = fs.readFileSync(path.join(__dirname, '../static/js/base-signals.js'), 'utf8');

class FakeNode {
  constructor(document, id) {
    this.ownerDocument = document;
    this.id = id; this.innerHTML = ''; this.textContent = ''; this.dataset = {};
    this.hidden = false; this.value = ''; this.scrollTop = 0; this.listeners = {};
    this._queryCache = new Map();
    this.classList = { add() {}, remove() {} };
  }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  setAttribute(name, value) { this[name] = value; }
  click() { assert.ok(this.listeners.click, 'click handler for ' + this.id); this.listeners.click({ target: this }); }
  focus() { this.ownerDocument.activeElement = this; }
  closest() { return null; }
  scrollIntoView() { /* normal browser date auto-centering */ }
  querySelector(selector) {
    if (selector === '.is-active') return new FakeNode(this.ownerDocument, 'date-active');
    return this.querySelectorAll(selector)[0] || null;
  }
  querySelectorAll(selector) {
    const attribute = selector === '[data-day]' ? 'day' :
      selector === '[data-motor]' ? 'motor' : null;
    if (!attribute) return [];
    const key = selector + '\\u0000' + this.innerHTML;
    if (this._queryCache.has(key)) return this._queryCache.get(key);
    const out = [];
    const regex = new RegExp('<button[^>]*\\bdata-' + attribute + '="([^"]+)"[^>]*>', 'g');
    let match;
    while ((match = regex.exec(this.innerHTML))) {
      const node = new FakeNode(this.ownerDocument, match[1]);
      node.dataset[attribute] = match[1];
      out.push(node);
    }
    this._queryCache.set(key, out);
    return out;
  }
}
function setup(data) {
  const els = new Map();
  const document = {
    readyState: 'complete', activeElement: null,
    body: { classList: { add() {}, remove() {} } },
    addEventListener() {},
    getElementById(id) {
      if (!els.has(id)) els.set(id, new FakeNode(document, id));
      return els.get(id);
    }
  };
  const overlay = document.getElementById('sxfBaseSignalOverlay');
  overlay.hidden = true;
  const requests = [];
  const sandbox = {
    window: {}, document, console, Date, Intl, Map, Set, Array, String,
    fetch: async (url) => {
      requests.push(url);
      return { ok: true, json: async () => data };
    }
  };
  vm.runInNewContext(js, sandbox, { filename: 'base-signals.js' });
  return { els, document, requests, window: sandbox.window, get(id) { return document.getElementById(id); } };
}
function signals(day) {
  const kickoff = day + 'T18:00:00+00:00';
  function item(id, engine, uid, home, stage) {
    return { id, engine, uid, kickoff_utc:kickoff, day, home, away:'Deplasman',
      league:'Süper Lig', market:'1X2', selection:'1', odds:1.85,
      kind:'EARLY_SIGNAL', stage_status:stage||'AS_RECORDED',
      checkpoint:8, source_checkpoint:8, observed_at:kickoff,
      selection_status:'ELIGIBLE', review_state:'VALID_PREMATCH_RECORD' };
  }
  return { status:'ok', engines:['1X2_CONCENTRATION_V1','1X2_CONCENTRATION_V2'],
    items:[item(1,'1X2_CONCENTRATION_V1','uid-a','Takım V1'),
           item(2,'1X2_CONCENTRATION_V2','uid-b','Takım V2'),
           item(3,'1X2_CONCENTRATION_V1','uid-a','Takım V1','T8_HISTORICAL')] };
}
function todayTR() {
  const parts = new Intl.DateTimeFormat('en-GB', { timeZone:'Europe/Istanbul',year:'numeric',month:'2-digit',day:'2-digit' }).formatToParts(new Date());
  const p = Object.fromEntries(parts.map(x => [x.type,x.value]));
  return p.year+'-'+p.month+'-'+p.day;
}
async function flush() { await Promise.resolve(); await Promise.resolve(); await new Promise(resolve=>setImmediate(resolve)); }

test('home shows separate V1 and V2 tiles without horizontal tabs; opens only V1 matches', async () => {
  const mock = setup(signals(todayTR()));
  mock.window.openBaseSignalsPanel();
  await flush();
  let html = mock.get('sxfSignalContent').innerHTML;
  assert.match(html, /class="sxf-engine-grid"/);
  assert.match(html, /1X2 Concentration V1/);
  assert.match(html, /1X2 Concentration V2/);
  assert.match(html, /Premium Over · Min 1.70/);
  assert.match(html, /data-motor="PREMIUM_OVER_MIN1_70"[\s\S]*?<b>0<\/b> maç/);
  assert.doesNotMatch(html, /sxf-engine-box|sxf-motor-group/);
  const tiles = mock.get('sxfSignalContent').querySelectorAll('[data-motor]');
  const v1 = tiles.find(x => x.dataset.motor === '1X2_CONCENTRATION_V1');
  assert.ok(v1);
  v1.click();
  html = mock.get('sxfSignalContent').innerHTML;
  assert.match(html, /Takım V1/);
  assert.doesNotMatch(html, /Takım V2/);
  assert.equal((html.match(/class="sxf-signal-card"/g)||[]).length, 1, 'same match must have one card');
  assert.equal((html.match(/class="sxf-signal-row/g)||[]).length, 2, 'all signal events retained under match');
  assert.match(html, /Geçmiş T-8/);
  assert.equal(mock.get('sxfSearchWrap').hidden, false);
  assert.equal(mock.requests.length, 1, 'engine drill-down is local, no new DB call');

  mock.get('sxfSignalBack').click();
  html = mock.get('sxfSignalContent').innerHTML;
  assert.match(html, /class="sxf-engine-grid"/);
  assert.equal(mock.get('sxfSearchWrap').hidden, true);
});

test('day change inside V1 only shows V1 day results, never switches to V2', async () => {
  const mock=setup(signals(todayTR()));
  mock.window.openBaseSignalsPanel();
  await flush();
  const v1=mock.get('sxfSignalContent').querySelectorAll('[data-motor]')
    .find(x=>x.dataset.motor==='1X2_CONCENTRATION_V1');
  v1.click();
  const dates=mock.get('sxfSignalDateRail').querySelectorAll('[data-day]');
  const other=dates.find(x=>x.dataset.day!==todayTR());
  assert.ok(other);
  other.click();
  const html=mock.get('sxfSignalContent').innerHTML;
  assert.match(html,/1X2 Concentration V1/);
  assert.match(html,/Bu gün için maç bulunmuyor/);
  assert.doesNotMatch(html,/Takım V2/);
});

test('malicious team strings are escaped inside one fixture card', async () => {
  const data=signals(todayTR());
  data.items[0].home='<img src=x onerror=alert(1)>';
  const mock=setup(data);
  mock.window.openBaseSignalsPanel();
  await flush();
  mock.get('sxfSignalContent').querySelectorAll('[data-motor]')
    .find(x=>x.dataset.motor==='1X2_CONCENTRATION_V1').click();
  const html=mock.get('sxfSignalContent').innerHTML;
  assert.ok(!html.includes('<img src=x onerror=alert(1)>'));
  assert.ok(html.includes('&lt;img src=x onerror=alert(1)&gt;'));
});

test('confirmed 1-1 scoreboard marks home-pick LOSS; never mistakes selection for actual score', async () => {
  const data=signals(todayTR());
  Object.assign(data.items[0], { final_score:'1-1', result_state:'FT', outcome:'LOSS' });
  Object.assign(data.items[2], { final_score:'1-1', result_state:'FT', outcome:'LOSS' });
  const mock=setup(data);
  mock.window.openBaseSignalsPanel();
  await flush();
  mock.get('sxfSignalContent').querySelectorAll('[data-motor]')
    .find(x=>x.dataset.motor==='1X2_CONCENTRATION_V1').click();
  const html=mock.get('sxfSignalContent').innerHTML;
  assert.match(html,/MAÇ SONUCU <strong>MS 1-1<\/strong>/);
  assert.match(html,/KAYBETTİ/);
  assert.ok(html.includes('Maç Sonucu (1X2)'));
  assert.match(html,/Takım V1 kazanır/);
});

test('unconfirmed in-play score never appears as fulltime or a settled bet', async () => {
  const data=signals(todayTR());
  Object.assign(data.items[0], { final_score:null, result_state:'PENDING', outcome:null });
  const mock=setup(data);
  mock.window.openBaseSignalsPanel();
  await flush();
  mock.get('sxfSignalContent').querySelectorAll('[data-motor]')
    .find(x=>x.dataset.motor==='1X2_CONCENTRATION_V1').click();
  const html=mock.get('sxfSignalContent').innerHTML;
  assert.match(html,/Doğrulanmadı/);
  assert.doesNotMatch(html,/KAYBETTİ|KAZANDI|MAÇ SONUCU <strong>MS/);
});

test('zero-count motor tile reveals its last real day without changing the selected day', async () => {
  const prior = new Date(Date.parse(todayTR() + 'T12:00:00Z') - 86400000).toISOString().slice(0,10);
  const mock = setup(signals(prior));
  mock.window.openBaseSignalsPanel();
  await flush();
  let html = mock.get('sxfSignalContent').innerHTML;
  assert.match(html, /Son sinyal:/);
  assert.match(html, /<b>0<\/b> maç/);
  const v1 = mock.get('sxfSignalContent').querySelectorAll('[data-motor]')
    .find(x => x.dataset.motor === '1X2_CONCENTRATION_V1');
  v1.click();
  html = mock.get('sxfSignalContent').innerHTML;
  assert.match(html,/Bu gün için maç bulunmuyor/);
  assert.match(html,/id="sxfSignalShowLast"/);
  assert.doesNotMatch(html,/Takım V1/);
  mock.get('sxfSignalShowLast').click();
  html = mock.get('sxfSignalContent').innerHTML;
  assert.match(html,/Takım V1/);
  assert.doesNotMatch(html,/Takım V2/);
  assert.equal(mock.requests.length,1,'no extra request to browse cached real signals');
});
test('empty motor with no stored rows never fabricates a last recorded date', async () => {
  const mock = setup({status:'ok',engines:['1X2_CONCENTRATION_V1'],items:[]});
  mock.window.openBaseSignalsPanel();
  await flush();
  const v1 = mock.get('sxfSignalContent').querySelectorAll('[data-motor]')
    .find(x => x.dataset.motor === '1X2_CONCENTRATION_V1');
  v1.click();
  assert.doesNotMatch(mock.get('sxfSignalContent').innerHTML,/sxfSignalShowLast|Son sinyal:/);
});



test('unknown retired engines are excluded; archived Base evidence is preserved', async () => {
  const data = signals(todayTR());
  data.items.push({id:42, engine:'LEGACY_UNDERDOG',uid:'uid-old',
    day:todayTR(),kickoff_utc:todayTR()+'T18:00:00+00:00',
    home:'Retired Side',away:'Other Side',market:'1X2',selection:'1'});
  const mock=setup(data);
  mock.window.openBaseSignalsPanel(); await flush();
  const tiles=mock.get('sxfSignalContent').querySelectorAll('[data-motor]');
  assert.equal(tiles.length,10);
  assert.doesNotMatch(mock.get('sxfSignalContent').innerHTML,/LEGACY_UNDERDOG/);
  tiles.find(x=>x.dataset.motor==='1X2_CONCENTRATION_V1').click();
  const html=mock.get('sxfSignalContent').innerHTML;
  assert.match(html,/Takım V1/);
  assert.match(html,/Geçmiş T-8/);
  assert.doesNotMatch(html,/Retired Side/);
});

test('a selected V1 match also shows other engines on the exact same selection', async () => {
  const data=signals(todayTR());
  const shared=data.items[0];
  data.items[0].valid_on_time=true;
  data.items[2].valid_on_time=false;
  data.items.push(
    {...shared,id:4,engine:'1X2_CONCENTRATION_V2',odds:1.83,checkpoint:6,valid_on_time:true},
    {...shared,id:5,engine:'HEAVY_1X2_CONCENTRATION',odds:1.82,checkpoint:6,valid_on_time:true},
    {...shared,id:6,engine:'EARLY_MONEY_CORE',odds:1.91,checkpoint:72,valid_on_time:false},
    {...shared,id:7,engine:'EARLY_MONEY_CORE',odds:1.88,checkpoint:60,valid_on_time:false},
    {...shared,id:8,engine:'BTTS_YES',market:'BTTS',selection:'Y',odds:1.72,valid_on_time:true},
    {...shared,id:9,engine:'SURPRISE_TEAM',market:'1X2',selection:'2',odds:3.3,valid_on_time:true}
  );
  const mock=setup(data);
  mock.window.openBaseSignalsPanel(); await flush();
  mock.get('sxfSignalContent').querySelectorAll('[data-motor]')
    .find(x=>x.dataset.motor==='1X2_CONCENTRATION_V1').click();
  const html=mock.get('sxfSignalContent').innerHTML;
  assert.equal((html.match(/class="sxf-signal-card"/g)||[]).length,1);
  assert.equal((html.match(/class="sxf-direction-group"/g)||[]).length,3);
  const grouped=html.match(/<div class="sxf-direction-badges">([^]*?)<\/div>/);
  assert.ok(grouped);
  for(const name of ['V1','V2','HEAVY','EARLY CORE']) {
    assert.ok(grouped[1].includes('>'+name+'</span>'));
    assert.equal(grouped[1].split('>'+name+'</span>').length-1,1,
      name+' badge must not multiply with checkpoint count');
  }
  assert.match(html,/Deplasman kazanır/);
  assert.match(html,/KG Var/);
  assert.match(html,/Zamanında \+ arşiv/);
  assert.equal((html.match(/<details class="sxf-history">/g)||[]).length,3);
  assert.match(html,/checkpoint kaydı/);
  assert.equal(mock.requests.length,1,'no extra fetch required for cross-engine grouping');
});

test('recorded odds come from latest actual source observation, not an inferred live price', async()=>{
  const data=signals(todayTR());
  data.items.splice(1,1);
  Object.assign(data.items[0],{observed_at:'2026-10-21T09:00:00Z',odds:1.91});
  Object.assign(data.items[1],{observed_at:'2026-10-21T12:00:00Z',odds:1.75});
  const mock=setup(data);mock.window.openBaseSignalsPanel();await flush();
  mock.get('sxfSignalContent').querySelectorAll('[data-motor]')
    .find(x=>x.dataset.motor==='1X2_CONCENTRATION_V1').click();
  const html=mock.get('sxfSignalContent').innerHTML;
  assert.match(html,/Kayıtlı oran<\/small><b>1\.75<\/b>/);
  assert.doesNotMatch(html,/Kayıtlı oran<\/small><b>1\.91<\/b>/);
});


test('Lincoln Red Imps – FC Twente has zero visible cards when all records are price rejected', async () => {
  const data = signals(todayTR());
  const common=data.items[0];
  data.items=[
    {...common,id:11,uid:'lincoln-twente',home:'Lincoln Red Imps',
      away:'FC Twente',engine:'EARLY_MONEY_CORE',checkpoint:72,odds:1.27,
      selection:'2',selection_status:'PRICE_FILTER_REJECT',review_state:'PRICE_REJECTED'},
    {...common,id:12,uid:'lincoln-twente',home:'Lincoln Red Imps',
      away:'FC Twente',engine:'EARLY_MONEY_T12',checkpoint:12,odds:1.24,
      selection:'2',selection_status:'PRICE_FILTER_REJECT',review_state:'PRICE_REJECTED'},
    {...common,id:13,uid:'lincoln-twente',home:'Lincoln Red Imps',
      away:'FC Twente',engine:'HEAVY_1X2_CONCENTRATION',checkpoint:8,odds:1.25,
      selection:'2',selection_status:'PRICE_FILTER_REJECT',review_state:'PRICE_REJECTED'},
    {...common,id:14,uid:'lincoln-twente',home:'Lincoln Red Imps',
      away:'FC Twente',engine:'HEAVY_1X2_CONCENTRATION',checkpoint:6,odds:1.24,
      selection:'2',selection_status:'PRICE_FILTER_REJECT',review_state:'PRICE_REJECTED'}
  ];
  const mock=setup(data);
  mock.window.openBaseSignalsPanel();await flush();
  const index=mock.get('sxfSignalContent').innerHTML;
  assert.doesNotMatch(index,/Lincoln Red Imps|FC Twente/);
  for (const engine of ['EARLY_MONEY_CORE','EARLY_MONEY_T12','HEAVY_1X2_CONCENTRATION']) {
    mock.get('sxfSignalContent').querySelectorAll('[data-motor]')
      .find(x=>x.dataset.motor===engine).click();
    const detail=mock.get('sxfSignalContent').innerHTML;
    assert.match(detail,/Bu gün için maç bulunmuyor/);
    assert.doesNotMatch(detail,/sxf-signal-card|sxf-direction-badge|Lincoln Red Imps|FC Twente/);
    mock.get('sxfSignalBack').click();
  }
});

test('reject only the unsuitable engine of a match, not the valid supporting engines', async () => {
  const data=signals(todayTR());
  const good=data.items[0];
  data.items=[
    {...good,id:1,valid_on_time:true},
    {...good,id:2,engine:'1X2_CONCENTRATION_V2',odds:1.82,valid_on_time:true},
    {...good,id:3,engine:'HEAVY_1X2_CONCENTRATION',odds:1.24,
      review_state:'PRICE_REJECTED',selection_status:'PRICE_FILTER_REJECT'},
    {...good,id:4,engine:'EARLY_MONEY_CORE',odds:1.91,
      selection_status:'HISTORY_INCOMPLETE',review_state:'HISTORY_INCOMPLETE'},
    {...good,id:5,engine:'EARLY_MONEY_T12',odds:1.25,
      selection_status:'ELIGIBLE',review_state:'VALID_PREMATCH_RECORD'}
  ];
  const mock=setup(data);mock.window.openBaseSignalsPanel();await flush();
  mock.get('sxfSignalContent').querySelectorAll('[data-motor]')
    .find(x=>x.dataset.motor==='1X2_CONCENTRATION_V1').click();
  const html=mock.get('sxfSignalContent').innerHTML;
  const badges=[...html.matchAll(/class="sxf-direction-badge"[^>]*>(.*?)<\/span>/g)].map(x=>x[1]);
  assert.deepEqual(badges,['V1','V2']);
  assert.doesNotMatch(html,/Uygun değil|HEAVY|EARLY CORE|EARLY T12/);
  assert.match(html,/Takım V1 kazanır/);
  assert.equal((html.match(/class="sxf-history-entry/g)||[]).length,0,
    'history remains collapsed in DOM but as sxf-signal-row it is still present');
});

test('eligible archived checkpoint stays visible while rejected sibling is omitted', async () => {
  const data=signals(todayTR());
  const good=data.items[0];
  data.items=[
    {...good,id:1,valid_on_time:false,stage_status:'T8_HISTORICAL',odds:1.95},
    {...good,id:2,engine:'HEAVY_1X2_CONCENTRATION',odds:1.21,
      selection_status:'PRICE_FILTER_REJECT',review_state:'PRICE_REJECTED'}
  ];
  const mock=setup(data);mock.window.openBaseSignalsPanel();await flush();
  mock.get('sxfSignalContent').querySelectorAll('[data-motor]')
    .find(x=>x.dataset.motor==='1X2_CONCENTRATION_V1').click();
  const html=mock.get('sxfSignalContent').innerHTML;
  assert.match(html,/Arşiv/);
  assert.match(html,/V1/);
  assert.doesNotMatch(html,/HEAVY|Uygun değil/);
});
