const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const appJsPath = path.join(__dirname, '..', 'static', 'js', 'app.js');
const appJs = fs.readFileSync(appJsPath, 'utf8');

test('match loading starts without awaiting optional favorite requests', async () => {
  const start = appJs.indexOf("document.addEventListener('DOMContentLoaded',async()=>{");
  const end = appJs.indexOf('function updateLastRefreshDisplay()', start);

  assert.notEqual(start, -1, 'dashboard bootstrap listener should exist');
  assert.notEqual(end, -1, 'dashboard bootstrap listener should have an end');

  const bootstrap = appJs.slice(start, end);
  const favoritesStart = bootstrap.indexOf('Promise.all([loadUserFavorites(),loadFavoriteCounts()])');
  const matchesStart = bootstrap.indexOf('loadMatches();');

  assert.ok(bootstrap.includes('await _licenseReady'), 'license gating should remain');
  assert.ok(favoritesStart >= 0, 'favorite requests should still start');
  assert.ok(matchesStart > favoritesStart, 'matches should start after favorites have been launched');
  assert.doesNotMatch(
    bootstrap,
    /await\s+Promise\.all\(\[loadUserFavorites\(\),loadFavoriteCounts\(\)\]\)/,
    'matches must not wait for favorite requests'
  );

  let domReadyHandler;
  let matchLoads = 0;
  const context = {
    _isLicensed: true,
    _licenseReady: Promise.resolve(),
    document: {
      addEventListener(eventName, handler) {
        if (eventName === 'DOMContentLoaded') domReadyHandler = handler;
      },
      getElementById() {
        return null;
      },
      querySelectorAll() {
        return [];
      }
    },
    window: { setInterval: () => 1 },
    setupTabs() {},
    setupSearch() {},
    setupModalChartTabs() {},
    fetchAnalysisMatchHashes() {},
    loadFinishedScores() {},
    loadUserFavorites: () => new Promise(() => {}),
    loadFavoriteCounts: () => new Promise(() => {}),
    loadMatches() {
      matchLoads += 1;
    },
    _startBackgroundLiveFetch() {},
    checkStatus() {},
    setupAutoRefresh() {},
    handleVisibilityChange() {},
    registerChartPlugins() {}
  };

  vm.runInNewContext(bootstrap, context);
  assert.equal(typeof domReadyHandler, 'function');
  await domReadyHandler();
  assert.equal(matchLoads, 1, 'loadMatches should run while favorite requests remain pending');
});

test('match API failures render an actionable error instead of a spinner', () => {
  assert.match(appJs, /if\(response\.status===403\)\{[^}]*renderMatchLoadError\(/);
  assert.match(appJs, /if\(!response\.ok\)\{throw new Error\(/);
  assert.match(appJs, /catch\(error\)\{console\.error\('Error loading matches:',error\);matches=\[\];filteredMatches=\[\];renderMatchLoadError\(/);
  assert.match(appJs, /function renderMatchLoadError\(message,reloadPage=false\)/);
  assert.match(appJs, /class="match-load-retry"/);
});

test('match loading error controls retry or reload on desktop and mobile', () => {
  const helperStart = appJs.indexOf('function renderMatchLoadError(');
  const helperEnd = appJs.length;
  assert.ok(helperStart >= 0 && helperEnd > helperStart, 'error renderer should be defined');
  const helperSource = appJs.slice(helperStart, helperEnd);

  function createContainer() {
    const button = {
      handler: null,
      addEventListener(eventName, handler) {
        assert.equal(eventName, 'click');
        this.handler = handler;
      }
    };
    return {
      button,
      _html: '',
      set innerHTML(value) {
        this._html = value;
      },
      get innerHTML() {
        return this._html;
      },
      querySelector(selector) {
        return selector === '.match-load-retry' ? button : null;
      }
    };
  }

  const elements = {
    matchesTableBody: createContainer(),
    matchCardList: createContainer(),
    matchCount: { textContent: '' },
    mobileMatchCount: { textContent: '' }
  };
  let retries = 0;
  let reloads = 0;
  const context = {
    currentMarket: 'moneyway_1x2',
    document: { getElementById: (id) => elements[id] || null },
    loadMatches: () => { retries += 1; },
    window: { location: { reload: () => { reloads += 1; } } }
  };

  vm.runInNewContext(
    helperSource + '\nrenderMatchLoadError("Maçlar yüklenemedi.");',
    context
  );
  assert.match(elements.matchesTableBody.innerHTML, /role="alert"/);
  assert.match(elements.matchCardList.innerHTML, /Tekrar dene/);
  assert.equal(elements.matchCount.textContent, '0');
  assert.equal(elements.mobileMatchCount.textContent, '0');
  elements.matchesTableBody.button.handler();
  elements.matchCardList.button.handler();
  assert.equal(retries, 2);

  vm.runInNewContext(
    helperSource + '\nrenderMatchLoadError("Lisans doğrulanamadı.", true);',
    context
  );
  elements.matchesTableBody.button.handler();
  elements.matchCardList.button.handler();
  assert.equal(reloads, 2);
});