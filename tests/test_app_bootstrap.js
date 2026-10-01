const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const appJsPath = path.join(__dirname, '..', 'static', 'js', 'app.js');
const appJs = fs.readFileSync(appJsPath, 'utf8');
const appJsSrcPath = path.join(__dirname, '..', 'static', 'js', 'app.js.src');
const appJsSrc = fs.readFileSync(appJsSrcPath, 'utf8');
const appBundles = [
  ['runtime bundle', appJs],
  ['source bundle', appJsSrc]
];

function extractDashboardBootstrap(source) {
  const startMatch = /document\.addEventListener\('DOMContentLoaded',\s*async\s*\(\)\s*=>\s*\{/.exec(source);
  assert.ok(startMatch, 'dashboard bootstrap listener should exist');
  const end = source.indexOf('function updateLastRefreshDisplay()', startMatch.index);
  assert.ok(end > startMatch.index, 'dashboard bootstrap listener should have an end');
  return source.slice(startMatch.index, end);
}

function extractAccountLicenseCheck(source) {
  const start = source.indexOf('async function _fetchAccountSessionStatus()');
  const end = source.indexOf('function logoutWebLicense()', start);
  assert.ok(start >= 0 && end > start, 'account-session license bridge should exist');
  return source.slice(start, end) + '\ninitLicenseCheck;';
}

function createLicenseBridgeContext(fetch) {
  let resolveLicenseReady;
  const licenseReady = new Promise((resolve) => {
    resolveLicenseReady = resolve;
  });
  const state = {
    stored: {},
    licenseReady: false,
    legacyInitCalls: 0,
    matchLoads: 0,
    redirects: [],
    licenseGateCalls: 0,
    matchErrors: []
  };
  const context = vm.createContext({
    AbortController: class {
      constructor() {
        this.signal = {};
      }
      abort() {}
    },
    setTimeout: () => 1,
    clearTimeout() {},
    fetch,
    localStorage: {
      setItem(key, value) {
        state.stored[key] = String(value);
      },
      getItem(key) {
        return state.stored[key] || null;
      },
      removeItem(key) {
        delete state.stored[key];
      }
    },
    window: {
      location: {
        replace(path) {
          state.redirects.push(path);
        }
      },
      setInterval: () => 1
    },
    document: {
      addEventListener(eventName, handler) {
        if (eventName === 'DOMContentLoaded') state.domReadyHandler = handler;
      },
      getElementById: () => null,
      querySelectorAll: () => []
    },
    WEB_LICENSE_KEY: 'smartxflow_web_license',
    WEB_LICENSE_VALID_KEY: 'smartxflow_license_valid_until',
    _isLicensed: false,
    _isPro: false,
    _licenseReady: licenseReady,
    _licenseReadyResolve() {
      state.licenseReady = true;
      resolveLicenseReady();
    },
    checkWebLicense: () => false,
    initLicenseCheck() {
      state.legacyInitCalls += 1;
      state.licenseGateCalls += 1;
      state.licenseReady = true;
      resolveLicenseReady();
    },
    showLicenseGate() {
      state.licenseGateCalls += 1;
    },
    renderMatchLoadError(message, reloadPage) {
      state.matchErrors.push({ message, reloadPage });
    },
    setupTabs() {},
    setupSearch() {},
    setupModalChartTabs() {},
    fetchAnalysisMatchHashes() {},
    loadFinishedScores() {},
    loadUserFavorites: () => new Promise(() => {}),
    loadFavoriteCounts: () => new Promise(() => {}),
    loadMatches() {
      state.matchLoads += 1;
    },
    _startBackgroundLiveFetch() {},
    checkStatus() {},
    setupAutoRefresh() {},
    handleVisibilityChange() {},
    registerChartPlugins() {},
    updateLicenseDaysBadge() {},
    _loadTestFreeHashes() {},
    _addTestLockIcons() {},
    _addMobileMktLockIcons() {},
    _favFilterActive: false,
    currentMarket: 'moneyway_1x2'
  });
  return { context, state };
}

for (const [bundleName, source] of appBundles) {
  test(`match loading starts without awaiting optional favorites (${bundleName})`, async () => {
    const bootstrap = extractDashboardBootstrap(source);
    const favoritesStart = bootstrap.search(/Promise\.all\(\[loadUserFavorites\(\),\s*loadFavoriteCounts\(\)\]\)/);
    const matchesStart = bootstrap.indexOf('loadMatches();');

    assert.ok(bootstrap.includes('await _licenseReady'), 'license gating should remain');
    assert.ok(favoritesStart >= 0, 'favorite requests should still start');
    assert.ok(matchesStart > favoritesStart, 'matches should start after favorites have been launched');
    assert.doesNotMatch(
      bootstrap,
      /await\s+Promise\.all\(\[loadUserFavorites\(\),\s*loadFavoriteCounts\(\)\]\)/,
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
}

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
      getItem(key) { return stored[key] || null; },
      removeItem(key) { delete stored[key]; }
    },
    window: { location: { replace() {} } },
    document: { getElementById: () => null },
    WEB_LICENSE_KEY: 'smartxflow_web_license',
    WEB_LICENSE_VALID_KEY: 'smartxflow_license_valid_until',
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

for (const [bundleName, source] of appBundles) {
  test(`login-required status retains the legacy license gate (${bundleName})`, async () => {
    const { context, state } = createLicenseBridgeContext(async () => ({
      ok: true,
      json: async () => ({ status: 'login_required' })
    }));
    const initLicenseCheck = vm.runInContext(extractAccountLicenseCheck(source), context);

    await initLicenseCheck();

    assert.equal(state.licenseReady, true);
    assert.equal(state.licenseGateCalls, 1);
    assert.deepEqual(state.redirects, []);
    assert.equal(state.matchErrors.length, 0);
  });

  test(`active account session starts match loading (${bundleName})`, async () => {
    let requestedUrl = '';
    const { context, state } = createLicenseBridgeContext(async (url, options) => {
      requestedUrl = url;
      assert.equal(options.credentials, 'same-origin');
      assert.equal(options.cache, 'no-store');
      return { ok: true, json: async () => ({ status: 'ok', plan: 'pro' }) };
    });
    state.stored.smartxflow_web_license = 'expired-legacy-key';
    state.stored.smartxflow_license_valid_until = '2000-01-01T00:00:00Z';
    state.stored.license_days_remaining = '0';

    vm.runInContext(extractDashboardBootstrap(source), context);
    const initLicenseCheck = vm.runInContext(extractAccountLicenseCheck(source), context);
    await initLicenseCheck();
    await state.domReadyHandler();

    assert.equal(requestedUrl, '/api/auth/session-status');
    assert.equal(context._isLicensed, true);
    assert.equal(context.window.userPlan, 'pro');
    assert.equal(state.licenseReady, true);
    assert.equal(state.matchLoads, 1, 'a verified account must start the match request');
    assert.equal(state.stored.smartxflow_web_license, undefined, 'stale legacy keys must not be sent with account requests');
    assert.equal(state.stored.smartxflow_license_valid_until, undefined);
    assert.equal(state.stored.license_days_remaining, undefined);
  });

  test(`expired account session returns to login (${bundleName})`, async () => {
    const { context, state } = createLicenseBridgeContext(async () => ({
      ok: true,
      json: async () => ({ status: 'session_expired' })
    }));
    const initLicenseCheck = vm.runInContext(extractAccountLicenseCheck(source), context);

    await initLicenseCheck();

    assert.deepEqual(state.redirects, ['/login?next=/app']);
    assert.equal(state.licenseReady, true);
    assert.equal(state.licenseGateCalls, 0);
    assert.equal(state.matchErrors.length, 0);
  });

  for (const [status, expectedPath] of [
    ['email_unverified', '/verify-email'],
    ['membership_required', '/membership-required']
  ]) {
    test(`${status} account status routes correctly (${bundleName})`, async () => {
      const { context, state } = createLicenseBridgeContext(async () => ({
        ok: true,
        json: async () => ({ status })
      }));
      const initLicenseCheck = vm.runInContext(extractAccountLicenseCheck(source), context);

      await initLicenseCheck();

      assert.deepEqual(state.redirects, [expectedPath]);
      assert.equal(state.licenseReady, true);
      assert.equal(state.licenseGateCalls, 0);
    });
  }

  test(`session-status failures show a recoverable error (${bundleName})`, async () => {
    const { context, state } = createLicenseBridgeContext(async () => {
      throw new Error('temporary session-status failure');
    });
    const initLicenseCheck = vm.runInContext(extractAccountLicenseCheck(source), context);

    await initLicenseCheck();

    assert.equal(state.licenseReady, true);
    assert.equal(state.licenseGateCalls, 0);
    assert.equal(state.matchErrors.length, 1);
    assert.match(state.matchErrors[0].message, /oturumu doğrulanamadı/i);
    assert.equal(state.matchErrors[0].reloadPage, true);
  });

  test(`unknown session status shows a recoverable error (${bundleName})`, async () => {
    const { context, state } = createLicenseBridgeContext(async () => ({
      ok: true,
      json: async () => ({ status: 'unexpected_status' })
    }));
    const initLicenseCheck = vm.runInContext(extractAccountLicenseCheck(source), context);

    await initLicenseCheck();

    assert.equal(state.licenseReady, true);
    assert.equal(state.licenseGateCalls, 0);
    assert.equal(state.matchErrors.length, 1);
    assert.equal(state.matchErrors[0].reloadPage, true);
  });
}