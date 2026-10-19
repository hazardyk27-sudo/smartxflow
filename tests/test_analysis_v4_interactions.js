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
    const out = [];
    const regex = new RegExp('<button[^>]*\\bdata-' + attribute + '="([^"]+)"[^>]*>', 'g');
    let match;
    while ((match = regex.exec(this.innerHTML))) {
      const node = new FakeNode(this.ownerDocument, match[1]);
      node.dataset[attribute] = match[1];
      out.push(node);
    }
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
      checkpoint:8, source_checkpoint:8, observed_at:kickoff };
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
