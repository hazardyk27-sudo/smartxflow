from pathlib import Path

START_MARKER = 'async function loadChart('
END_MARKER = 'let brushStartIndex'

LOADER_STUB = r'''window._sxfModalChartRuntimePromise = window._sxfModalChartRuntimePromise || null;
function _getModalChartRuntimeUrl() {
    try {
        const scripts = document.getElementsByTagName('script');
        for (let i = scripts.length - 1; i >= 0; i--) {
            const src = scripts[i].src || '';
            if (src.indexOf('/static/js/app.js') !== -1) {
                const queryIndex = src.indexOf('?');
                const query = queryIndex >= 0 ? src.slice(queryIndex) : '';
                return '/static/js/modal-chart.js' + query;
            }
        }
    } catch (e) {}
    return '/static/js/modal-chart.js';
}

function loadModalChartRuntime() {
    if (typeof window.__sxfLoadChartImpl === 'function') return Promise.resolve();
    if (window._sxfModalChartRuntimePromise) return window._sxfModalChartRuntimePromise;

    window._sxfModalChartRuntimePromise = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = _getModalChartRuntimeUrl();
        script.async = true;
        script.onload = () => {
            if (typeof window.__sxfLoadChartImpl === 'function') {
                resolve();
                return;
            }
            window._sxfModalChartRuntimePromise = null;
            reject(new Error('Modal chart runtime loaded without implementation'));
        };
        script.onerror = () => {
            window._sxfModalChartRuntimePromise = null;
            reject(new Error('Modal chart runtime failed to load'));
        };
        document.head.appendChild(script);
    });
    return window._sxfModalChartRuntimePromise;
}

async function loadChart(...args) {
    await loadModalChartRuntime();
    return window.__sxfLoadChartImpl(...args);
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
const deferredRuntime = fs.readFileSync(path.join(root, 'static/js/modal-chart.js'), 'utf8');
const deferredSource = fs.readFileSync(path.join(root, 'static/js/modal-chart.js.src'), 'utf8');
const template = fs.readFileSync(path.join(root, 'templates/index.html'), 'utf8');

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
  test(`main bundle keeps only the lazy loadChart stub (${name})`, () => {
    const fn = extractFunction(source, 'async function loadChart(');
    assert.match(fn, /loadModalChartRuntime\(\)/);
    assert.match(fn, /window\.__sxfLoadChartImpl/);
    assert.doesNotMatch(fn, /Error loading chart:/);
    assert.match(source, /function loadModalChartRuntime\(\)/);
  });
}

test('deferred chart implementation is not eagerly referenced by template', () => {
  assert.doesNotMatch(template, /modal-chart\.js/);
  assert.match(deferredRuntime, /window\.__sxfLoadChartImpl\s*=\s*async function loadChart/);
  assert.match(deferredSource, /window\.__sxfLoadChartImpl\s*=\s*async function loadChart/);
  assert.match(deferredRuntime, /Error loading chart:/);
});

test('modal chart loader deduplicates concurrent requests and inherits app asset version', async () => {
  const source = bundles[1][1];
  const urlFn = extractFunction(source, 'function _getModalChartRuntimeUrl(');
  const loaderFn = extractFunction(source, 'function loadModalChartRuntime(');
  const stubFn = extractFunction(source, 'async function loadChart(');
  const appended = [];
  const windowObj = {};
  const context = vm.createContext({
    window: windowObj,
    document: {
      getElementsByTagName(name) {
        assert.equal(name, 'script');
        return [{ src: 'https://preview.example/static/js/app.js?v=abc123' }];
      },
      createElement(name) {
        assert.equal(name, 'script');
        return {};
      },
      head: {
        appendChild(script) {
          appended.push(script);
          setImmediate(() => {
            windowObj.__sxfLoadChartImpl = async (...args) => args.join('|');
            script.onload();
          });
        }
      }
    },
    Promise,
    Error,
    setImmediate,
  });
  vm.runInContext(`${urlFn}\n${loaderFn}\n${stubFn}\nwindow.__testLoadChart = loadChart;`, context);

  const [a, b] = await Promise.all([
    windowObj.__testLoadChart('A', 'B'),
    windowObj.__testLoadChart('C', 'D'),
  ]);
  assert.equal(appended.length, 1, 'concurrent modal opens must share one script request');
  assert.equal(appended[0].src, '/static/js/modal-chart.js?v=abc123');
  assert.equal(a, 'A|B');
  assert.equal(b, 'C|D');
});
'''

before_sizes = {}
after_sizes = {}

for filename in ('static/js/app.js.src', 'static/js/app.js'):
    path = Path(filename)
    text = path.read_text(encoding='utf-8')
    before_sizes[filename] = len(text.encode('utf-8'))
    start = text.find(START_MARKER)
    end = text.find(END_MARKER, start)
    if start < 0 or end < 0 or end <= start:
        raise SystemExit(f'{filename}: loadChart extraction markers not found')
    segment = text[start:end].rstrip()
    if segment.count(START_MARKER) != 1:
        raise SystemExit(f'{filename}: unexpected nested loadChart marker')
    if not segment.endswith('}'):
        raise SystemExit(f'{filename}: extracted loadChart segment does not end with closing brace')

    deferred = segment.replace(
        START_MARKER,
        'window.__sxfLoadChartImpl = async function loadChart(',
        1,
    ) + ';\n'
    suffix = '.src' if filename.endswith('.src') else ''
    out = Path(f'static/js/modal-chart.js{suffix}')
    out.write_text(deferred, encoding='utf-8')

    new_text = text[:start] + LOADER_STUB + text[end:]
    path.write_text(new_text, encoding='utf-8')
    after_sizes[filename] = len(new_text.encode('utf-8'))

runtime_saved = before_sizes['static/js/app.js'] - after_sizes['static/js/app.js']
source_saved = before_sizes['static/js/app.js.src'] - after_sizes['static/js/app.js.src']
print(f'RUNTIME_BEFORE={before_sizes["static/js/app.js"]}')
print(f'RUNTIME_AFTER={after_sizes["static/js/app.js"]}')
print(f'RUNTIME_SAVED={runtime_saved}')
print(f'SOURCE_BEFORE={before_sizes["static/js/app.js.src"]}')
print(f'SOURCE_AFTER={after_sizes["static/js/app.js.src"]}')
print(f'SOURCE_SAVED={source_saved}')
if runtime_saved < 25000:
    raise SystemExit(f'Runtime bundle reduction too small: {runtime_saved}')
if source_saved < 45000:
    raise SystemExit(f'Source bundle reduction too small: {source_saved}')

Path('tests/test_modal_chart_code_split.js').write_text(TEST_CONTENT, encoding='utf-8')
