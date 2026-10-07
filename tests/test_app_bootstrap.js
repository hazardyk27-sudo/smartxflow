const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const appJsPath = path.join(__dirname, '..', 'static', 'js', 'app.js');
const appJs = fs.readFileSync(appJsPath, 'utf8');
const appJsSrcPath = path.join(__dirname, '..', 'static', 'js', 'app.js.src');
const appJsSrc = fs.readFileSync(appJsSrcPath, 'utf8');
const loginTemplatePath = path.join(__dirname, '..', 'templates', 'login.html');
const loginTemplate = fs.readFileSync(loginTemplatePath, 'utf8');
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

function extractFunctionDeclaration(source, signature) {
  const start = source.indexOf(signature);
  assert.ok(start >= 0, `${signature} should exist`);
  const bodyStart = source.indexOf('{', start);
  assert.ok(bodyStart > start, `${signature} should have a body`);

  let depth = 0;
  for (let index = bodyStart; index < source.length; index += 1) {
    if (source[index] === '{') depth += 1;
    if (source[index] === '}') {
      depth -= 1;
      if (depth === 0) return source.slice(start, index + 1);
    }
  }

  assert.fail(`${signature} should have a closing brace`);
}

function createMatchesLoaderHarness(source, options = {}) {
  const timedFetch = extractFunctionDeclaration(source, 'async function _fetchMatchesWithTimeout(');
  const loaderStart = source.indexOf('async function loadMatches(');
  const loaderEnd = source.indexOf('async function loadAllRemainingMatches()', loaderStart);
  assert.ok(loaderStart >= 0 && loaderEnd > loaderStart, 'match loader should exist');
  const loader = source.slice(loaderStart, loaderEnd);
  const switchFromLive = extractFunctionDeclaration(source, 'function switchFromLive()');
  const state = {
    fetchUrls: [],
    timers: [],
    logs: [],
    warnings: [],
    errors: [],
    clearedIntervals: [],
    renderedMatches: [],
    tbody: { innerHTML: '' },
    cardList: { innerHTML: '' }
  };
  const context = vm.createContext({
    AbortController: class {
      constructor() { this.signal = {}; }
      abort() {}
    },
    setTimeout(callback, delay) {
      state.timers.push({ callback, delay });
      return state.timers.length;
    },
    clearTimeout() {},
    clearInterval(interval) {
      state.clearedIntervals.push(interval);
    },
    fetch: (url, requestOptions) => {
      state.fetchUrls.push(url);
      if (options.fetch) return options.fetch(url, requestOptions, state);
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({
          matches: [{ home_team: 'Home', away_team: 'Away' }],
          total: 1
        })
      });
    },
    document: {
      getElementById(id) {
        if (id === 'matchesTableBody') return state.tbody;
        if (id === 'matchCardList') return state.cardList;
        return null;
      },
      querySelector() {
        return null;
      }
    },
    window: { location: { reload() {} } },
    console: {
      log(...args) { state.logs.push(args.map(String).join(' ')); },
      warn(...args) { state.warnings.push(args.map(String).join(' ')); },
      error(...args) { state.errors.push(args.map(String).join(' ')); }
    },
    performance: { now: () => 1 },
    currentMarket: 'moneyway_1x2',
    currentSource: 'betfair',
    dateFilterMode: 'ALL',
    _liveMode: options.liveMode ?? false,
    _liveInterval: options.liveMode ? 7 : null,
    _prevLiveScores: { old: true },
    _loadMatchesLock: options.loadLock ?? false,
    _loadMatchesPending: options.loadPending ?? null,
    _loadMatchesPendingSince: options.pendingSince ?? 0,
    _loadMatchesRequestId: 0,
    _loadMatchesRequestKey: options.requestKey ?? null,
    _loadMatchesQueued: null,
    _LOAD_MATCHES_PENDING_STALE_MS: 45000,
    _matchesMarketCache: options.matchesCache ?? {},
    _MATCHES_CACHE_TTL: 90000,
    matches: [{ home_team: 'Old', away_team: 'Match' }],
    filteredMatches: [],
    totalMatchCount: 0,
    hasMoreMatches: false,
    currentOffset: 0,
    oddsTrendCache: {},
    _finishedScores: {},
    applySorting(items) { return items; },
    updateTableHeaders() {},
    attachTrendTooltipListeners() {},
    renderMatches(items) {
      state.renderedMatches = items;
      state.tbody.innerHTML = items.length ? '<tr class="match-row"></tr>' : '<tr class="empty-state"></tr>';
      state.cardList.innerHTML = items.length ? 'match-row' : 'empty-state';
    },
    renderMatchLoadError(message, reloadPage = false) {
      state.errors.push({ message, reloadPage });
    }
  });

  vm.runInContext(
    `${switchFromLive}\n${timedFetch}\n${loader}\n` +
      'window.__testSwitchFromLive = switchFromLive;\n' +
      'window.__testLoadMatches = loadMatches;',
    context
  );
  return { context, state };
}

function createLicenseBridgeContext(fetch) {
  let resolveLicenseReady;
  const licenseReady = new Promise((resolve) => {
    resolveLicenseReady = resolve;
  });
  const state = {
    stored: {},
    fetchUrls: [],
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
    fetch(...args) {
      state.fetchUrls.push(args[0]);
      return fetch(...args);
    },
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
    LEGACY_WEB_LICENSE_VALID_KEY: 'smartxflow_web_license_valid',
    LEGACY_WEB_LICENSE_MIGRATION_MS: 15 * 60 * 1000,
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

test('license-key login stores canonical dashboard keys and response metadata', () => {
  assert.match(
    loginTemplate,
    /storeValidatedLicenseState\(key,\s*data\);/,
    'successful license validation should persist state through the canonical helper'
  );
  const stored = { license_plan: 'stale', license_days_remaining: '0', smartxflow_web_license_valid: 'true' };
  const context = vm.createContext({
    localStorage: {
      setItem(key, value) { stored[key] = String(value); },
      getItem(key) { return stored[key] ?? null; },
      removeItem(key) { delete stored[key]; }
    }
  });
  const persistLoginState = vm.runInContext(
    extractFunctionDeclaration(loginTemplate, 'function storeValidatedLicenseState(') +
      '\nstoreValidatedLicenseState;',
    context
  );
  const response = {
    expires_at: '2031-04-05T06:07:08.000Z',
    plan: 'pro',
    days_left: 37
  };

  persistLoginState('SXF-TEST-KEY', response);

  assert.equal(stored.smartxflow_web_license, 'SXF-TEST-KEY');
  assert.equal(stored.smartxflow_license_valid_until, response.expires_at);
  assert.equal(stored.smartxflow_web_license_valid, undefined);
  assert.equal(stored.license_plan, 'pro');
  assert.equal(stored.license_days_remaining, '37');
});

test('license-key login uses a short ISO expiry fallback when expires_at is absent', () => {
  const stored = { license_plan: 'stale', license_days_remaining: '99' };
  const context = vm.createContext({
    localStorage: {
      setItem(key, value) { stored[key] = String(value); },
      getItem(key) { return stored[key] ?? null; },
      removeItem(key) { delete stored[key]; }
    }
  });
  const persistLoginState = vm.runInContext(
    extractFunctionDeclaration(loginTemplate, 'function storeValidatedLicenseState(') +
      '\nstoreValidatedLicenseState;',
    context
  );
  const before = Date.now();

  persistLoginState('SXF-TEST-KEY', { valid: true });

  const expiresAt = Date.parse(stored.smartxflow_license_valid_until);
  assert.ok(Number.isFinite(expiresAt), 'fallback expiry should be a valid ISO timestamp');
  assert.ok(expiresAt > before && expiresAt <= before + 15 * 60 * 1000 + 1000);
  assert.equal(stored.license_plan, undefined, 'missing plan must not leave stale plan metadata');
  assert.equal(stored.license_days_remaining, undefined, 'missing days must not leave stale expiry metadata');
});

for (const [bundleName, source] of appBundles) {
  test(`legacy license localStorage state migrates to the dashboard key (${bundleName})`, () => {
    const { context, state } = createLicenseBridgeContext(async () => {
      throw new Error('migration must not make an API request');
    });
    state.stored.smartxflow_web_license = 'SXF-LEGACY-KEY';
    state.stored.smartxflow_web_license_valid = 'true';

    const checkWebLicense = vm.runInContext(
      extractFunctionDeclaration(source, 'function checkWebLicense()') + '\ncheckWebLicense;',
      context
    );
    const before = Date.now();
    assert.equal(checkWebLicense(), true);

    const migratedExpiry = Date.parse(state.stored.smartxflow_license_valid_until);
    assert.ok(Number.isFinite(migratedExpiry), 'migration should write a valid canonical expiry');
    assert.ok(migratedExpiry > before && migratedExpiry <= before + 15 * 60 * 1000 + 1000);
    assert.equal(state.stored.smartxflow_web_license_valid, undefined);
    assert.equal(context.window.userLicenseKey, 'SXF-LEGACY-KEY');
    assert.deepEqual(state.fetchUrls, [], 'migration compatibility must not bypass server API authorization');

    const noKey = createLicenseBridgeContext(async () => {
      throw new Error('a legacy marker without its license key must not migrate');
    });
    noKey.state.stored.smartxflow_web_license_valid = 'true';
    const noKeyCheck = vm.runInContext(
      extractFunctionDeclaration(source, 'function checkWebLicense()') + '\ncheckWebLicense;',
      noKey.context
    );
    assert.equal(noKeyCheck(), false);
    assert.equal(noKey.state.stored.smartxflow_license_valid_until, undefined);
  });

  test(`license-key login reaches the Prematch bootstrap (${bundleName})`, async () => {
    const { context, state } = createLicenseBridgeContext(async (url) => {
      if (url === '/api/auth/session-status') {
        throw new Error('a valid legacy license must not fall into account-session gating');
      }
      assert.equal(url, '/api/licenses/validate');
      return {
        ok: true,
        json: async () => ({ valid: true, plan: 'pro', days_left: 37 })
      };
    });
    const persistLoginState = vm.runInContext(
      extractFunctionDeclaration(loginTemplate, 'function storeValidatedLicenseState(') +
        '\nstoreValidatedLicenseState;',
      context
    );
    persistLoginState('SXF-LOGIN-KEY', {
      expires_at: '2031-04-05T06:07:08.000Z',
      plan: 'pro',
      days_left: 37
    });
    context.getWebDeviceId = () => 'device-test';
    context.navigator = { userAgent: 'bootstrap regression test' };
    context.startLicenseStatusRefresh = () => {};

    const initLicenseCheck = vm.runInContext(
      extractFunctionDeclaration(source, 'function checkWebLicense()') +
        '\n' + extractAccountLicenseCheck(source),
      context
    );
    vm.runInContext(extractDashboardBootstrap(source), context);

    await initLicenseCheck();
    await state.domReadyHandler();

    assert.equal(context._isLicensed, true);
    assert.equal(state.stored.smartxflow_license_valid_until, '2031-04-05T06:07:08.000Z');
    assert.equal(state.stored.license_plan, 'pro');
    assert.equal(state.stored.license_days_remaining, '37');
    assert.equal(state.matchLoads, 1, 'verified license login should start the Prematch load');
    assert.deepEqual(state.fetchUrls, ['/api/licenses/validate']);
  });
}

for (const [bundleName, source] of appBundles) {
  test(`match loading starts without awaiting optional favorites (${bundleName})`, async () => {
    const bootstrap = extractDashboardBootstrap(source);
    const favoritesStart = bootstrap.indexOf('loadFavoritesBootstrap()');
    const matchesStart = bootstrap.indexOf('loadMatches();');

    assert.ok(bootstrap.includes('await _licenseReady'), 'license gating should remain');
    assert.ok(favoritesStart >= 0, 'favorites bootstrap should still start');
    assert.ok(matchesStart >= 0 && matchesStart < favoritesStart, 'Prematch loading should start before optional favorites');
    assert.doesNotMatch(
      bootstrap,
      /await\s+loadFavoritesBootstrap\(\)/,
      'matches must not wait for favorites bootstrap'
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
      loadFavoritesBootstrap: () => new Promise(() => {}),
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

for (const [bundleName, source] of appBundles) {
test(`match loading reaches a visible terminal state for every response (${bundleName})`, async () => {
  const timedFetch = extractFunctionDeclaration(source, 'async function _fetchMatchesWithTimeout(');
  const payloadHelperStart = source.indexOf('function _getMatchArrayFromPayload(');
  const payloadHelper = payloadHelperStart >= 0
    ? extractFunctionDeclaration(source, 'function _getMatchArrayFromPayload(')
    : '';
  const loaderStart = source.indexOf('async function loadMatches(');
  const loaderEnd = source.indexOf('async function loadAllRemainingMatches()', loaderStart);
  assert.ok(loaderStart >= 0 && loaderEnd > loaderStart, 'match loader should exist');
  const loader = source.slice(loaderStart, loaderEnd);

  const scenarios = [
    {
      name: 'matches',
      fetch: async () => ({ ok: true, status: 200, json: async () => ({ matches: [{ id: 'm1' }], total: 1 }) }),
      expected: 'match-row'
    },
    {
      name: 'empty response',
      fetch: async () => ({ ok: true, status: 200, json: async () => ({ matches: [], total: 0 }) }),
      expected: 'empty-state'
    },
    {
      name: '403 authorization response',
      fetch: async () => ({ ok: false, status: 403, json: async () => ({}) }),
      expected: 'role="alert"',
      reload: true
    },
    {
      name: 'HTTP failure',
      fetch: async () => ({ ok: false, status: 503, json: async () => ({}) }),
      expected: 'role="alert"'
    },
    {
      name: 'timed-out request after retry',
      fetch: async () => {
        const error = new Error('request timed out');
        error.name = 'AbortError';
        throw error;
      },
      expected: 'role="alert"',
      fetchCalls: 2
    },
    {
      name: 'invalid JSON',
      fetch: async () => ({
        ok: true,
        status: 200,
        json: async () => { throw new SyntaxError('invalid JSON'); }
      }),
      expected: 'role="alert"'
    },
    {
      name: 'malformed payload shape',
      fetch: async () => ({ ok: true, status: 200, json: async () => ({ matches: 'not-an-array' }) }),
      expected: 'role="alert"'
    }
  ];

  for (const scenario of scenarios) {
    const state = {
      errors: [],
      fetchCalls: 0,
      tbody: { innerHTML: '' },
      cardList: { innerHTML: '' }
    };
    const context = vm.createContext({
      AbortController: class {
        constructor() { this.signal = {}; }
        abort() {}
      },
      setTimeout(callback, delay) {
        if (delay === 1500) queueMicrotask(callback);
        return 1;
      },
      clearTimeout() {},
      fetch: async (...args) => {
        state.fetchCalls += 1;
        return scenario.fetch(...args);
      },
      document: {
        getElementById(id) {
          if (id === 'matchesTableBody') return state.tbody;
          if (id === 'matchCardList') return state.cardList;
          return null;
        }
      },
      window: { location: { reload() {} } },
      console: { log() {}, warn() {}, error() {} },
      performance: { now: () => 1 },
      currentMarket: 'moneyway_1x2',
      currentSource: 'betfair',
      dateFilterMode: 'ALL',
      _liveMode: false,
      _loadMatchesLock: false,
      _loadMatchesPending: null,
      _loadMatchesPendingSince: 0,
      _loadMatchesRequestId: 0,
      _loadMatchesRequestKey: null,
      _loadMatchesQueued: null,
      _LOAD_MATCHES_PENDING_STALE_MS: 45000,
      _matchesMarketCache: {},
      _MATCHES_CACHE_TTL: 90000,
      matches: [],
      filteredMatches: [],
      totalMatchCount: 0,
      hasMoreMatches: false,
      currentOffset: 0,
      oddsTrendCache: {},
      _finishedScores: {},
      applySorting: (items) => items,
      updateTableHeaders() {},
      attachTrendTooltipListeners() {},
      renderMatches(items) {
        const stateName = items.length ? 'match-row' : 'empty-state';
        state.tbody.innerHTML = `<tr class="${stateName}">${items.length || 'No matches found'}</tr>`;
        state.cardList.innerHTML = stateName;
      },
      renderMatchLoadError(message, reloadPage = false) {
        state.errors.push({ message, reloadPage });
        state.tbody.innerHTML = `<tr role="alert">${message}</tr>`;
        state.cardList.innerHTML = `<div role="alert">${message}</div>`;
      }
    });

    const helperCode = `${timedFetch}\n${payloadHelper}\n${loader}\nloadMatches;`;
    const loadMatches = vm.runInContext(helperCode, context);
    await loadMatches();

    assert.match(state.tbody.innerHTML, new RegExp(scenario.expected), scenario.name);
    assert.doesNotMatch(state.tbody.innerHTML, /loading-spinner/, `${scenario.name} must not leave a spinner`);
    if (scenario.reload) {
      assert.equal(state.errors[0]?.reloadPage, true, '403 should offer a page reload');
    } else if (scenario.expected === 'role="alert"') {
      assert.equal(state.errors.length, 1, `${scenario.name} should show an error`);
      assert.equal(state.errors[0].reloadPage, false, `${scenario.name} should offer retry`);
    } else {
      assert.equal(state.errors.length, 0, `${scenario.name} should not be treated as an error`);
    }
    if (scenario.fetchCalls) {
      assert.equal(state.fetchCalls, scenario.fetchCalls, 'timed-out requests should use one retry');
    }
  }
});
}

for (const [bundleName, source] of appBundles) {
  test(`leaving Live schedules a fresh Prematch request (${bundleName})`, async () => {
    const cacheKey = 'moneyway_1x2|ALL|betfair';
    const { context, state } = createMatchesLoaderHarness(source, {
      liveMode: true,
      matchesCache: {
        [cacheKey]: {
          matches: [{ home_team: 'Cached', away_team: 'Match' }],
          total: 1,
          ts: Date.now()
        }
      }
    });

    context.window.__testSwitchFromLive();
    assert.equal(context._liveMode, false, 'switching away from Live should clear live mode');
    assert.deepEqual(state.clearedIntervals, [7], 'the Live refresh interval should stop');

    const transitionTimer = state.timers.find((timer) => timer.delay === 0);
    assert.ok(transitionTimer, 'Prematch reload should be queued after the current click handler');
    transitionTimer.callback();
    await context._loadMatchesPending;

    assert.deepEqual(
      state.fetchUrls,
      ['/api/matches?market=moneyway_1x2&date_filter=today_future&bulk=1'],
      'leaving Live should fetch Prematch even when the client cache is still warm'
    );
    assert.match(state.logs.join('\n'), /bypassing client cache/);
    assert.equal(context._loadMatchesLock, false, 'the request should release its lock');
  });

  test(`match-load guards are observable and stale locks recover (${bundleName})`, async () => {
    const liveHarness = createMatchesLoaderHarness(source, { liveMode: true });
    await liveHarness.context.window.__testLoadMatches();
    assert.equal(liveHarness.state.fetchUrls.length, 0, 'Live mode should not request Prematch data');
    assert.match(liveHarness.state.logs.join('\n'), /blocked: liveMode/);

    const staleLockHarness = createMatchesLoaderHarness(source, { loadLock: true });
    await staleLockHarness.context.window.__testLoadMatches();
    assert.equal(staleLockHarness.state.fetchUrls.length, 1, 'a lock without a pending request should recover');
    assert.match(staleLockHarness.state.warnings.join('\n'), /stale load lock\/pending state; resetting/);
    assert.equal(staleLockHarness.context._loadMatchesLock, false);
  });
}

for (const [bundleName, source] of appBundles) {
test(`match response body is covered by the fetch timeout (${bundleName})`, async () => {
  const helperSource = extractFunctionDeclaration(source, 'async function _fetchMatchesWithTimeout(');
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
    helperSource + '\n_fetchMatchesWithTimeout;',
    context
  );

  await assert.rejects(fetchMatches('/api/matches', 5), { name: 'AbortError' });
});
}

for (const [bundleName, source] of appBundles) {
  test(`test-mode account readiness does not wait for optional free-match data (${bundleName})`, async () => {
    const { context, state } = createLicenseBridgeContext(async () => ({
      ok: true,
      json: async () => ({ status: 'ok', test_mode: true })
    }));
    let freeMatchLookupStarted = false;
    context._loadTestFreeHashes = () => {
      freeMatchLookupStarted = true;
      return new Promise(() => {});
    };

    const initLicenseCheck = vm.runInContext(extractAccountLicenseCheck(source), context);
    const initResult = await Promise.race([
      initLicenseCheck().then(() => 'resolved'),
      new Promise((resolve) => setTimeout(() => resolve('timed out'), 50))
    ]);

    assert.equal(initResult, 'resolved', 'license initialization must not await optional test data');
    assert.equal(state.licenseReady, true);
    assert.equal(context._isLicensed, true);
    assert.equal(context.window.userPlan, 'test');
    assert.equal(freeMatchLookupStarted, true);
  });
}

for (const [bundleName, source] of appBundles) {
test(`match loading error controls retry or reload on desktop and mobile (${bundleName})`, () => {
  const helperSource = extractFunctionDeclaration(source, 'function renderMatchLoadError(');

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
}

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

  let licenseReady = false;
  let licenseGateCalls = 0;
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
    document: {
      getElementById(id) {
        assert.equal(id, 'logoutBtn');
        return null;
      }
    },
    _licenseReadyResolve() { licenseReady = true; },
    checkWebLicense: () => false,
    showLicenseGate() { licenseGateCalls += 1; }
  };

  const initLicenseCheck = vm.runInNewContext(
    appJs.slice(helperStart, helperEnd) + '\ninitLicenseCheck;',
    context
  );
  await initLicenseCheck();
  assert.equal(licenseGateCalls, 1, 'unauthenticated legacy visitors should retain the existing license gate');
  assert.equal(licenseReady, true, 'the gate path should resolve dashboard readiness');
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

  test(`valid legacy session status starts Prematch loading (${bundleName})`, async () => {
    const { context, state } = createLicenseBridgeContext(async (url, options) => {
      assert.equal(url, '/api/auth/session-status');
      assert.equal(options.credentials, 'same-origin');
      assert.equal(options.cache, 'no-store');
      return {
        ok: true,
        json: async () => ({
          status: 'ok',
          legacy_license: true,
          plan: 'pro',
          days_left: 37
        })
      };
    });

    vm.runInContext(extractDashboardBootstrap(source), context);
    const initLicenseCheck = vm.runInContext(extractAccountLicenseCheck(source), context);
    await initLicenseCheck();
    await state.domReadyHandler();

    assert.equal(context._isLicensed, true);
    assert.equal(context.window.userPlan, 'pro');
    assert.equal(state.licenseReady, true);
    assert.equal(state.matchLoads, 1, 'a valid legacy session must start the Prematch request');
    assert.deepEqual(state.fetchUrls, ['/api/auth/session-status']);
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