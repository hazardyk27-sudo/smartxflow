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

test('match response body is covered by the fetch timeout', async () => {
  const helperStart = appJs.indexOf('async function _fetchMatchesWithTimeout(');
  const helperEnd = appJs.indexOf('let _matchesMarketCache=', helperStart);
  assert.ok(helperStart >= 0 && helperEnd > helperStart, 'timed fetch helper should exist');

  class TestAbortController {
    constructor() {
      this.signal = { aborted: false, onabort: null };
    }

    abort() {
      this.signal.aborted = true;
      if (this.signal.onabort) this.signal.onabort();
    }
  }

  const context = {
    AbortController: TestAbortController,
    setTimeout(callback) {
      callback();
      return 1;
    },
    clearTimeout() {},
    fetch: async (_url, { signal }) => ({
      ok: true,
      status: 200,
      json: () => {
        if (signal.aborted) {
          const error = new Error('aborted');
          error.name = 'AbortError';
          return Promise.reject(error);
        }
        return new Promise((resolve, reject) => {
          signal.onabort = () => {
            const error = new Error('aborted');
            error.name = 'AbortError';
            reject(error);
          };
        });
      }
    })
  };
  const fetchMatches = vm.runInNewContext(
    appJs.slice(helperStart, helperEnd) + '\n_fetchMatchesWithTimeout;',
    context
  );

  await assert.rejects(fetchMatches('/api/matches', 5), { name: 'AbortError' });
});

test('test-mode free-match lookup does not block dashboard readiness', () => {
  const helperStart = appJs.indexOf('async function _loadTestFreeHashes()');
  const helperEnd = appJs.indexOf('function _isTestFreeAlarm(', helperStart);
  assert.ok(helperStart >= 0 && helperEnd > helperStart, 'test-mode lookup helper should exist');

  let licenseReady = false;
  const context = {
    window: { userPlan: 'test' },
    AbortController: class {
      constructor() {
        this.signal = { aborted: false };
      }
      abort() {
        this.signal.aborted = true;
      }
    },
    setTimeout: () => 1,
    clearTimeout() {},
    _licenseReadyResolve() {
      licenseReady = true;
    },
    fetch: () => new Promise(() => {})
  };
  const loadTestFreeHashes = vm.runInNewContext(
    appJs.slice(helperStart, helperEnd) + '\n_loadTestFreeHashes;',
    context
  );

  loadTestFreeHashes();
  assert.equal(licenseReady, true, 'license readiness should resolve before optional network data');
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

test('authenticated Supabase accounts unlock the dashboard without a legacy license key', async () => {
  const helperStart = appJs.indexOf('async function _fetchAccountSessionStatus()');
  const helperEnd = appJs.indexOf('function logoutWebLicense()', helperStart);
  assert.ok(helperStart >= 0 && helperEnd > helperStart, 'account-session license bridge should exist');

  const stored = {};
  let licenseReady = false;
  let legacyInitCalls = 0;
  let requestedUrl = '';
  const context = {
    AbortController: class {
      constructor() { this.signal = {}; }
      abort() {}
    },
    setTimeout: () => 1,
    clearTimeout() {},
    fetch: async (url, options) => {
      requestedUrl = url;
      assert.equal(options.credentials, 'same-origin');
      assert.equal(options.cache, 'no-store');
      return { ok: true, json: async () => ({ status: 'ok', plan: 'pro' }) };
    },
    localStorage: {
      setItem(key, value) { stored[key] = String(value); },
      getItem(key) { return stored[key] || null; }
    },
    window: { location: { replace() {} } },
    document: { getElementById: () => null },
    _isLicensed: false,
    _isPro: false,
    _licenseReadyResolve() { licenseReady = true; },
    checkWebLicense: () => false,
    initLicenseCheck() { legacyInitCalls += 1; },
    updateLicenseDaysBadge() {},
    _loadTestFreeHashes() {},
    _addTestLockIcons() {},
    _addMobileMktLockIcons() {}
  };

  const initLicenseCheck = vm.runInNewContext(
    appJs.slice(helperStart, helperEnd) + '\ninitLicenseCheck;',
    context
  );
  await initLicenseCheck();

  assert.equal(requestedUrl, '/api/auth/session-status');
  assert.equal(context._isLicensed, true);
  assert.equal(context.window.userPlan, 'pro');
  assert.equal(context._isPro, true);
  assert.equal(stored.license_plan, 'pro');
  assert.equal(licenseReady, true);
  assert.equal(legacyInitCalls, 0, 'valid account sessions should not fall through to the key-based gate');
});

test('legacy license gate remains available when no authenticated account session exists', async () => {
  const helperStart = appJs.indexOf('async function _fetchAccountSessionStatus()');
  const helperEnd = appJs.indexOf('function logoutWebLicense()', helperStart);
  assert.ok(helperStart >= 0 && helperEnd > helperStart, 'account-session license bridge should exist');

  let legacyInitCalls = 0;
  const context = {
    AbortController: class {
      constructor() { this.signal = {}; }
      abort() {}
    },
    setTimeout: () => 1,
    clearTimeout() {},
    fetch: async () => ({ ok: true, json: async () => ({ status: 'login_required' }) }),
    localStorage: { setItem() {}, getItem: () => null },
    window: { location: { replace() {} } },
    document: { getElementById: () => null },
    _licenseReadyResolve() {},
    checkWebLicense: () => false,
    initLicenseCheck() { legacyInitCalls += 1; }
  };

  const initLicenseCheck = vm.runInNewContext(
    appJs.slice(helperStart, helperEnd) + '\ninitLicenseCheck;',
    context
  );
  await initLicenseCheck();
  assert.equal(legacyInitCalls, 1, 'unauthenticated legacy visitors should retain the existing license gate');
});