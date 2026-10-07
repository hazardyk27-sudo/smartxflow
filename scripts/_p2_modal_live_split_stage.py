from pathlib import Path
import re

CHECK_SIGNATURE = 'async function _checkModalLiveData('
SIGNATURES = [
    CHECK_SIGNATURE,
    'function _buildModalLiveTabs(',
    'function setModalLiveMarket(',
    'function renderModalLiveDetail(',
    'function _renderModalLiveMobile(',
]

LOADER_STUB = r'''window._sxfModalLiveRuntimePromise = window._sxfModalLiveRuntimePromise || null;
function _getModalLiveRuntimeUrl() {
    try {
        const scripts = document.getElementsByTagName('script');
        for (let i = scripts.length - 1; i >= 0; i--) {
            const src = scripts[i].src || '';
            if (src.indexOf('/static/js/app.js') !== -1) {
                const queryIndex = src.indexOf('?');
                const query = queryIndex >= 0 ? src.slice(queryIndex) : '';
                return '/static/js/modal-live.js' + query;
            }
        }
    } catch (e) {}
    return '/static/js/modal-live.js';
}

function loadModalLiveRuntime() {
    if (typeof window.__sxfCheckModalLiveDataImpl === 'function') return Promise.resolve();
    if (window._sxfModalLiveRuntimePromise) return window._sxfModalLiveRuntimePromise;

    window._sxfModalLiveRuntimePromise = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = _getModalLiveRuntimeUrl();
        script.async = true;
        script.onload = () => {
            if (typeof window.__sxfCheckModalLiveDataImpl === 'function') {
                resolve();
                return;
            }
            window._sxfModalLiveRuntimePromise = null;
            reject(new Error('Modal live runtime loaded without implementation'));
        };
        script.onerror = () => {
            window._sxfModalLiveRuntimePromise = null;
            reject(new Error('Modal live runtime failed to load'));
        };
        document.head.appendChild(script);
    });
    return window._sxfModalLiveRuntimePromise;
}

async function _checkModalLiveData(...args) {
    try {
        await loadModalLiveRuntime();
        return await window.__sxfCheckModalLiveDataImpl(...args);
    } catch (e) {
        console.error('[Modal] Live runtime load error:', e);
    }
}
'''

TEST_CONTENT = r'''const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.join(__dirname, '..');
const bundles = [
  ['runtime', fs.readFileSync(path.join(root, 'static/js/app.js'), 'utf8')],
  ['source', fs.readFileSync(path.join(root, 'static/js/app.js.src'), 'utf8')],
];
const deferredRuntime = fs.readFileSync(path.join(root, 'static/js/modal-live.js'), 'utf8');
const deferredSource = fs.readFileSync(path.join(root, 'static/js/modal-live.js.src'), 'utf8');
const template = fs.readFileSync(path.join(root, 'templates/index.html'), 'utf8');

function extractFunction(source, signature) {
  const start = source.indexOf(signature);
  assert.ok(start >= 0, `${signature} should exist`);
  const bodyStart = source.indexOf('{', start);
  let depth = 0;
  let inSingle = false;
  let inDouble = false;
  let inTemplate = false;
  let inLineComment = false;
  let inBlockComment = false;
  let escaped = false;
  for (let i = bodyStart; i < source.length; i += 1) {
    const c = source[i];
    const n = source[i + 1] || '';
    if (inLineComment) { if (c === '\n') inLineComment = false; continue; }
    if (inBlockComment) { if (c === '*' && n === '/') { inBlockComment = false; i += 1; } continue; }
    if (inSingle) { if (escaped) escaped = false; else if (c === '\\') escaped = true; else if (c === "'") inSingle = false; continue; }
    if (inDouble) { if (escaped) escaped = false; else if (c === '\\') escaped = true; else if (c === '"') inDouble = false; continue; }
    if (inTemplate) { if (escaped) escaped = false; else if (c === '\\') escaped = true; else if (c === '`') inTemplate = false; continue; }
    if (c === '/' && n === '/') { inLineComment = true; i += 1; continue; }
    if (c === '/' && n === '*') { inBlockComment = true; i += 1; continue; }
    if (c === "'") { inSingle = true; continue; }
    if (c === '"') { inDouble = true; continue; }
    if (c === '`') { inTemplate = true; continue; }
    if (c === '{') depth += 1;
    if (c === '}') { depth -= 1; if (depth === 0) return source.slice(start, i + 1); }
  }
  assert.fail(`${signature} should have a closing brace`);
}

for (const [name, source] of bundles) {
  test(`main bundle keeps only lazy modal-live entrypoint (${name})`, () => {
    const fn = extractFunction(source, 'async function _checkModalLiveData(');
    assert.match(fn, /loadModalLiveRuntime\(\)/);
    assert.match(fn, /window\.__sxfCheckModalLiveDataImpl/);
    assert.doesNotMatch(fn, /\/api\/live\/match\/history/);
    assert.match(source, /function loadModalLiveRuntime\(\)/);
    assert.doesNotMatch(source, /function _buildModalLiveTabs\(/);
    assert.doesNotMatch(source, /function setModalLiveMarket\(/);
    assert.doesNotMatch(source, /function renderModalLiveDetail\(/);
    assert.doesNotMatch(source, /function _renderModalLiveMobile\(/);
  });

  test(`shared live helpers remain in main bundle (${name})`, () => {
    assert.match(source, /function formatLiveVol\(/);
    assert.match(source, /function escLiveHtml\(/);
    assert.match(source, /function _minuteToNum\(/);
  });
}

test('modal-live implementation is deferred and not eager in template', () => {
  assert.doesNotMatch(template, /modal-live\.js/);
  for (const deferred of [deferredRuntime, deferredSource]) {
    assert.match(deferred, /window\.__sxfCheckModalLiveDataImpl\s*=\s*async function _checkModalLiveData/);
    assert.match(deferred, /function _buildModalLiveTabs\(/);
    assert.match(deferred, /function setModalLiveMarket\(/);
    assert.match(deferred, /function renderModalLiveDetail\(/);
    assert.match(deferred, /function _renderModalLiveMobile\(/);
    assert.match(deferred, /\/api\/live\/match\/history/);
    assert.doesNotMatch(deferred, /function formatLiveVol\(/);
    assert.doesNotMatch(deferred, /function escLiveHtml\(/);
    assert.doesNotMatch(deferred, /function _minuteToNum\(/);
  }
});

test('modal-live loader deduplicates concurrent requests and inherits app version', async () => {
  const source = bundles[1][1];
  const urlFn = extractFunction(source, 'function _getModalLiveRuntimeUrl(');
  const loaderFn = extractFunction(source, 'function loadModalLiveRuntime(');
  const stubFn = extractFunction(source, 'async function _checkModalLiveData(');
  const appended = [];
  const windowObj = {};
  const context = vm.createContext({
    window: windowObj,
    document: {
      getElementsByTagName(name) {
        assert.equal(name, 'script');
        return [{ src: 'https://preview.example/static/js/app.js?v=live123' }];
      },
      createElement(name) {
        assert.equal(name, 'script');
        return {};
      },
      head: {
        appendChild(script) {
          appended.push(script);
          setImmediate(() => {
            windowObj.__sxfCheckModalLiveDataImpl = async (...args) => args.join('|');
            script.onload();
          });
        }
      }
    },
    console: { error() {} },
    Promise,
    Error,
    setImmediate,
  });
  vm.runInContext(`${urlFn}\n${loaderFn}\n${stubFn}\nwindow.__testLive = _checkModalLiveData;`, context);
  const [a, b] = await Promise.all([
    windowObj.__testLive('A', 'B'),
    windowObj.__testLive('C', 'D'),
  ]);
  assert.equal(appended.length, 1);
  assert.equal(appended[0].src, '/static/js/modal-live.js?v=live123');
  assert.equal(a, 'A|B');
  assert.equal(b, 'C|D');
});
'''

PREFETCH_TEST_CONTENT = r'''const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.join(__dirname, '..');
const bundles = [
  ['runtime', fs.readFileSync(path.join(root, 'static/js/app.js'), 'utf8')],
  ['source', fs.readFileSync(path.join(root, 'static/js/app.js.src'), 'utf8')],
];

function extractFunction(source, signature) {
  const start = source.indexOf(signature);
  assert.ok(start >= 0, `${signature} should exist`);
  const bodyStart = source.indexOf('{', start);
  let depth = 0;
  for (let i = bodyStart; i < source.length; i += 1) {
    if (source[i] === '{') depth += 1;
    if (source[i] === '}') {
      depth -= 1;
      if (depth === 0) return source.slice(start, i + 1);
    }
  }
  assert.fail(`${signature} should have a closing brace`);
}

for (const [name, source] of bundles) {
  test(`dashboard schedules deferred modal prefetch (${name})`, () => {
    assert.match(source, /function scheduleDeferredModalRuntimePrefetch\(\)/);
    assert.match(source, /runOptionalStartupTask\('modal runtime prefetch',\s*scheduleDeferredModalRuntimePrefetch\)/);
  });

  test(`modal prefetch waits for idle and does not execute scripts (${name})`, () => {
    const fn = extractFunction(source, 'function scheduleDeferredModalRuntimePrefetch(');
    let idleCallback = null;
    const created = [];
    const appended = [];
    const windowObj = {
      requestIdleCallback(callback, options) {
        idleCallback = callback;
        assert.equal(options.timeout, 7000);
      }
    };
    const context = vm.createContext({
      window: windowObj,
      document: {
        createElement(tag) { created.push(tag); return { dataset: {} }; },
        head: { appendChild(node) { appended.push(node); } }
      },
      _getModalChartRuntimeUrl: () => '/static/js/modal-chart.js?v=test',
      _getModalAlarmsRuntimeUrl: () => '/static/js/modal-alarms.js?v=test',
      _getModalLiveRuntimeUrl: () => '/static/js/modal-live.js?v=test',
      setTimeout() { throw new Error('timer fallback should not run with requestIdleCallback'); },
    });
    vm.runInContext(`let _sxfDeferredModalPrefetchScheduled = false;\n${fn}\nwindow.__testPrefetch = scheduleDeferredModalRuntimePrefetch;`, context);
    windowObj.__testPrefetch();
    assert.equal(appended.length, 0);
    assert.equal(typeof idleCallback, 'function');
    idleCallback();
    assert.deepEqual(created, ['link', 'link', 'link']);
    assert.equal(appended.length, 3);
    assert.deepEqual(appended.map(x => x.rel), ['prefetch', 'prefetch', 'prefetch']);
    assert.deepEqual(appended.map(x => x.as), ['script', 'script', 'script']);
    assert.deepEqual(appended.map(x => x.href), [
      '/static/js/modal-chart.js?v=test',
      '/static/js/modal-alarms.js?v=test',
      '/static/js/modal-live.js?v=test'
    ]);
    windowObj.__testPrefetch();
    assert.equal(appended.length, 3);
  });

  test(`modal prefetch skips already loaded runtimes (${name})`, () => {
    const fn = extractFunction(source, 'function scheduleDeferredModalRuntimePrefetch(');
    let timerCallback = null;
    let timerDelay = null;
    const appended = [];
    const windowObj = {
      __sxfLoadChartImpl: () => {},
      __sxfCheckModalLiveDataImpl: () => {},
    };
    const context = vm.createContext({
      window: windowObj,
      document: {
        createElement() { return { dataset: {} }; },
        head: { appendChild(node) { appended.push(node); } }
      },
      _getModalChartRuntimeUrl: () => '/static/js/modal-chart.js?v=test',
      _getModalAlarmsRuntimeUrl: () => '/static/js/modal-alarms.js?v=test',
      _getModalLiveRuntimeUrl: () => '/static/js/modal-live.js?v=test',
      setTimeout(callback, delay) { timerCallback = callback; timerDelay = delay; },
    });
    vm.runInContext(`let _sxfDeferredModalPrefetchScheduled = false;\n${fn}\nwindow.__testPrefetch = scheduleDeferredModalRuntimePrefetch;`, context);
    windowObj.__testPrefetch();
    assert.equal(timerDelay, 4000);
    assert.equal(appended.length, 0);
    timerCallback();
    assert.equal(appended.length, 1);
    assert.equal(appended[0].href, '/static/js/modal-alarms.js?v=test');
  });
}
'''


def find_function_end(text: str, start: int) -> int:
    brace = text.find('{', start)
    if brace < 0:
        raise ValueError('function body not found')
    depth = 0
    i = brace
    in_single = in_double = in_template = False
    in_line = in_block = False
    escaped = False
    while i < len(text):
        c = text[i]
        n = text[i + 1] if i + 1 < len(text) else ''
        if in_line:
            if c == '\n': in_line = False
        elif in_block:
            if c == '*' and n == '/': in_block = False; i += 1
        elif in_single:
            if escaped: escaped = False
            elif c == '\\': escaped = True
            elif c == "'": in_single = False
        elif in_double:
            if escaped: escaped = False
            elif c == '\\': escaped = True
            elif c == '"': in_double = False
        elif in_template:
            if escaped: escaped = False
            elif c == '\\': escaped = True
            elif c == '`': in_template = False
        else:
            if c == '/' and n == '/': in_line = True; i += 1
            elif c == '/' and n == '*': in_block = True; i += 1
            elif c == "'": in_single = True
            elif c == '"': in_double = True
            elif c == '`': in_template = True
            elif c == '{': depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0: return i + 1
        i += 1
    raise ValueError('function end not found')


before_sizes = {}
after_sizes = {}
for filename in ('static/js/app.js.src', 'static/js/app.js'):
    path = Path(filename)
    text = path.read_text(encoding='utf-8')
    before_sizes[filename] = len(text.encode('utf-8'))

    spans = []
    deferred_parts = []
    for signature in SIGNATURES:
        if text.count(signature) != 1:
            raise SystemExit(f'{filename}: expected exactly one {signature!r}, got {text.count(signature)}')
        start = text.find(signature)
        end = find_function_end(text, start)
        segment = text[start:end]
        if signature == CHECK_SIGNATURE:
            segment = segment.replace(
                CHECK_SIGNATURE,
                'window.__sxfCheckModalLiveDataImpl = async function _checkModalLiveData(',
                1,
            ) + ';'
        deferred_parts.append(segment)
        spans.append((start, end, LOADER_STUB if signature == CHECK_SIGNATURE else ''))

    deferred_text = '\n\n'.join(deferred_parts) + '\n'
    suffix = '.src' if filename.endswith('.src') else ''
    Path(f'static/js/modal-live.js{suffix}').write_text(deferred_text, encoding='utf-8')

    for start, end, replacement in sorted(spans, reverse=True):
        text = text[:start] + replacement + text[end:]

    alarm_block = re.compile(
        r"if\s*\(typeof window\.__sxfRenderMatchAlarmsSectionImpl\s*!==\s*'function'\)\s*\{\s*"
        r"candidates\.push\(_getModalAlarmsRuntimeUrl\(\)\);\s*\}"
    )
    match = alarm_block.search(text)
    if not match:
        raise SystemExit(f'{filename}: modal alarm prefetch block not found')
    live_prefetch = "\n        if (typeof window.__sxfCheckModalLiveDataImpl !== 'function') {\n            candidates.push(_getModalLiveRuntimeUrl());\n        }"
    text = text[:match.end()] + live_prefetch + text[match.end():]

    path.write_text(text, encoding='utf-8')
    after_sizes[filename] = len(text.encode('utf-8'))

runtime_saved = before_sizes['static/js/app.js'] - after_sizes['static/js/app.js']
source_saved = before_sizes['static/js/app.js.src'] - after_sizes['static/js/app.js.src']
print(f'MODAL_LIVE_RUNTIME_BEFORE={before_sizes["static/js/app.js"]}')
print(f'MODAL_LIVE_RUNTIME_AFTER={after_sizes["static/js/app.js"]}')
print(f'MODAL_LIVE_RUNTIME_SAVED={runtime_saved}')
print(f'MODAL_LIVE_SOURCE_BEFORE={before_sizes["static/js/app.js.src"]}')
print(f'MODAL_LIVE_SOURCE_AFTER={after_sizes["static/js/app.js.src"]}')
print(f'MODAL_LIVE_SOURCE_SAVED={source_saved}')
if runtime_saved < 5000:
    raise SystemExit(f'Runtime bundle reduction too small to justify split: {runtime_saved}')
if source_saved < 10000:
    raise SystemExit(f'Source bundle reduction too small to justify split: {source_saved}')

Path('tests/test_modal_live_code_split.js').write_text(TEST_CONTENT, encoding='utf-8')
Path('tests/test_deferred_modal_prefetch.js').write_text(PREFETCH_TEST_CONTENT, encoding='utf-8')
