from pathlib import Path

SIGNATURE = 'async function renderMatchAlarmsSection('

LOADER_STUB = r'''window._sxfModalAlarmsRuntimePromise = window._sxfModalAlarmsRuntimePromise || null;
function _getModalAlarmsRuntimeUrl() {
    try {
        const scripts = document.getElementsByTagName('script');
        for (let i = scripts.length - 1; i >= 0; i--) {
            const src = scripts[i].src || '';
            if (src.indexOf('/static/js/app.js') !== -1) {
                const queryIndex = src.indexOf('?');
                const query = queryIndex >= 0 ? src.slice(queryIndex) : '';
                return '/static/js/modal-alarms.js' + query;
            }
        }
    } catch (e) {}
    return '/static/js/modal-alarms.js';
}

function loadModalAlarmsRuntime() {
    if (typeof window.__sxfRenderMatchAlarmsSectionImpl === 'function') return Promise.resolve();
    if (window._sxfModalAlarmsRuntimePromise) return window._sxfModalAlarmsRuntimePromise;

    window._sxfModalAlarmsRuntimePromise = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = _getModalAlarmsRuntimeUrl();
        script.async = true;
        script.onload = () => {
            if (typeof window.__sxfRenderMatchAlarmsSectionImpl === 'function') {
                resolve();
                return;
            }
            window._sxfModalAlarmsRuntimePromise = null;
            reject(new Error('Modal alarms runtime loaded without implementation'));
        };
        script.onerror = () => {
            window._sxfModalAlarmsRuntimePromise = null;
            reject(new Error('Modal alarms runtime failed to load'));
        };
        document.head.appendChild(script);
    });
    return window._sxfModalAlarmsRuntimePromise;
}

async function renderMatchAlarmsSection(...args) {
    await loadModalAlarmsRuntime();
    return window.__sxfRenderMatchAlarmsSectionImpl(...args);
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
const deferredRuntime = fs.readFileSync(path.join(root, 'static/js/modal-alarms.js'), 'utf8');
const deferredSource = fs.readFileSync(path.join(root, 'static/js/modal-alarms.js.src'), 'utf8');
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
    if (inLineComment) {
      if (c === '\n') inLineComment = false;
      continue;
    }
    if (inBlockComment) {
      if (c === '*' && n === '/') { inBlockComment = false; i += 1; }
      continue;
    }
    if (inSingle) {
      if (escaped) escaped = false;
      else if (c === '\\') escaped = true;
      else if (c === "'") inSingle = false;
      continue;
    }
    if (inDouble) {
      if (escaped) escaped = false;
      else if (c === '\\') escaped = true;
      else if (c === '"') inDouble = false;
      continue;
    }
    if (inTemplate) {
      if (escaped) escaped = false;
      else if (c === '\\') escaped = true;
      else if (c === '`') inTemplate = false;
      continue;
    }
    if (c === '/' && n === '/') { inLineComment = true; i += 1; continue; }
    if (c === '/' && n === '*') { inBlockComment = true; i += 1; continue; }
    if (c === "'") { inSingle = true; continue; }
    if (c === '"') { inDouble = true; continue; }
    if (c === '`') { inTemplate = true; continue; }
    if (c === '{') depth += 1;
    if (c === '}') {
      depth -= 1;
      if (depth === 0) return source.slice(start, i + 1);
    }
  }
  assert.fail(`${signature} should have a closing brace`);
}

for (const [name, source] of bundles) {
  test(`main bundle keeps only lazy match-alarm stub (${name})`, () => {
    const fn = extractFunction(source, 'async function renderMatchAlarmsSection(');
    assert.match(fn, /loadModalAlarmsRuntime\(\)/);
    assert.match(fn, /window\.__sxfRenderMatchAlarmsSectionImpl/);
    assert.doesNotMatch(fn, /groupBySelection/);
    assert.match(source, /function loadModalAlarmsRuntime\(\)/);
  });
}

test('modal alarm implementation is deferred and not eager in template', () => {
  assert.doesNotMatch(template, /modal-alarms\.js/);
  assert.match(deferredRuntime, /window\.__sxfRenderMatchAlarmsSectionImpl\s*=\s*async function renderMatchAlarmsSection/);
  assert.match(deferredSource, /window\.__sxfRenderMatchAlarmsSectionImpl\s*=\s*async function renderMatchAlarmsSection/);
  assert.match(deferredRuntime, /groupBySelection/);
});

test('modal alarm loader deduplicates concurrent requests and inherits app version', async () => {
  const source = bundles[1][1];
  const urlFn = extractFunction(source, 'function _getModalAlarmsRuntimeUrl(');
  const loaderFn = extractFunction(source, 'function loadModalAlarmsRuntime(');
  const stubFn = extractFunction(source, 'async function renderMatchAlarmsSection(');
  const appended = [];
  const windowObj = {};
  const context = vm.createContext({
    window: windowObj,
    document: {
      getElementsByTagName(name) {
        assert.equal(name, 'script');
        return [{ src: 'https://preview.example/static/js/app.js?v=alarm123' }];
      },
      createElement(name) {
        assert.equal(name, 'script');
        return {};
      },
      head: {
        appendChild(script) {
          appended.push(script);
          setImmediate(() => {
            windowObj.__sxfRenderMatchAlarmsSectionImpl = async (...args) => args.join('|');
            script.onload();
          });
        }
      }
    },
    Promise,
    Error,
    setImmediate,
  });
  vm.runInContext(`${urlFn}\n${loaderFn}\n${stubFn}\nwindow.__testRender = renderMatchAlarmsSection;`, context);
  const [a, b] = await Promise.all([
    windowObj.__testRender('A', 'B'),
    windowObj.__testRender('C', 'D'),
  ]);
  assert.equal(appended.length, 1);
  assert.equal(appended[0].src, '/static/js/modal-alarms.js?v=alarm123');
  assert.equal(a, 'A|B');
  assert.equal(b, 'C|D');
});
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
            if c == '\n':
                in_line = False
        elif in_block:
            if c == '*' and n == '/':
                in_block = False
                i += 1
        elif in_single:
            if escaped:
                escaped = False
            elif c == '\\':
                escaped = True
            elif c == "'":
                in_single = False
        elif in_double:
            if escaped:
                escaped = False
            elif c == '\\':
                escaped = True
            elif c == '"':
                in_double = False
        elif in_template:
            if escaped:
                escaped = False
            elif c == '\\':
                escaped = True
            elif c == '`':
                in_template = False
        else:
            if c == '/' and n == '/':
                in_line = True
                i += 1
            elif c == '/' and n == '*':
                in_block = True
                i += 1
            elif c == "'":
                in_single = True
            elif c == '"':
                in_double = True
            elif c == '`':
                in_template = True
            elif c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    return i + 1
        i += 1
    raise ValueError('function end not found')


before_sizes = {}
after_sizes = {}
for filename in ('static/js/app.js.src', 'static/js/app.js'):
    path = Path(filename)
    text = path.read_text(encoding='utf-8')
    before_sizes[filename] = len(text.encode('utf-8'))
    start = text.find(SIGNATURE)
    if start < 0:
        raise SystemExit(f'{filename}: renderMatchAlarmsSection not found')
    end = find_function_end(text, start)
    segment = text[start:end]
    deferred = segment.replace(
        SIGNATURE,
        'window.__sxfRenderMatchAlarmsSectionImpl = async function renderMatchAlarmsSection(',
        1,
    ) + ';\n'
    suffix = '.src' if filename.endswith('.src') else ''
    Path(f'static/js/modal-alarms.js{suffix}').write_text(deferred, encoding='utf-8')
    new_text = text[:start] + LOADER_STUB + text[end:]
    path.write_text(new_text, encoding='utf-8')
    after_sizes[filename] = len(new_text.encode('utf-8'))

runtime_saved = before_sizes['static/js/app.js'] - after_sizes['static/js/app.js']
source_saved = before_sizes['static/js/app.js.src'] - after_sizes['static/js/app.js.src']
print(f'ALARM_RUNTIME_BEFORE={before_sizes["static/js/app.js"]}')
print(f'ALARM_RUNTIME_AFTER={after_sizes["static/js/app.js"]}')
print(f'ALARM_RUNTIME_SAVED={runtime_saved}')
print(f'ALARM_SOURCE_BEFORE={before_sizes["static/js/app.js.src"]}')
print(f'ALARM_SOURCE_AFTER={after_sizes["static/js/app.js.src"]}')
print(f'ALARM_SOURCE_SAVED={source_saved}')
if runtime_saved < 10000:
    raise SystemExit(f'Runtime bundle reduction too small: {runtime_saved}')
if source_saved < 25000:
    raise SystemExit(f'Source bundle reduction too small: {source_saved}')

Path('tests/test_modal_alarm_code_split.js').write_text(TEST_CONTENT, encoding='utf-8')
